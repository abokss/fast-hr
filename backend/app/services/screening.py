import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from ..config import STORAGE_DIR
from ..models import Vacancy, Resume, MatchResult, utcnow
from ..nlp.matching import score_batch
from .resume_parser import MAX_BYTES, ResumeParseError, extract_pdf, parse_information

MAX_RESUMES = 200
MAX_BATCH = 100


def get_vacancy(db, vacancy_id, lock=False):
    query = db.query(Vacancy).filter(Vacancy.id == vacancy_id)
    if lock:
        query = query.with_for_update()
    vacancy = query.first()
    if vacancy is None:
        raise HTTPException(404, 'Вакансия не найдена')
    return vacancy


def get_resume(db, vacancy_id, resume_id):
    resume = db.query(Resume).filter_by(id=resume_id, vacancy_id=vacancy_id).first()
    if resume is None:
        raise HTTPException(404, 'Резюме не найдено в этой вакансии')
    return resume


def import_resumes(db, vacancy_id, files):
    vacancy = get_vacancy(db, vacancy_id, lock=True)
    if not 1 <= len(files) <= MAX_BATCH:
        raise HTTPException(400, 'За один раз загрузите от 1 до 100 PDF.')
    existing = db.query(Resume).filter_by(vacancy_id=vacancy_id).all()
    hashes = {r.sha256 for r in existing}
    count = len(existing)
    accepted, errors, saved_paths = [], [], []
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for upload in files:
            filename = Path((upload.filename or 'resume.pdf').replace('\\', '/')).name[:255]
            try:
                if count >= MAX_RESUMES:
                    raise ResumeParseError('Достигнут лимит: 200 резюме в одной вакансии.')
                contents = upload.file.read(MAX_BYTES + 1)
                digest = hashlib.sha256(contents).hexdigest()
                if digest in hashes:
                    errors.append({'filename': filename, 'error': 'Этот PDF уже загружен.', 'code': 'duplicate'})
                    continue
                text = extract_pdf(contents)
                key = uuid4().hex + '.pdf'
                path = STORAGE_DIR / key
                saved_paths.append(path)
                path.write_bytes(contents)
                resume = Resume(vacancy_id=vacancy_id, filename=filename, storage_key=key,
                                sha256=digest, extracted_text=text, parsed=parse_information(text))
                db.add(resume)
                db.flush()
                accepted.append({'id': resume.id, 'filename': filename, 'parsed': resume.parsed})
                hashes.add(digest)
                count += 1
            except ResumeParseError as exc:
                errors.append({'filename': filename, 'error': str(exc), 'code': 'invalid_pdf'})
            finally:
                upload.file.close()
        if accepted:
            # Every upload changes the TF-IDF corpus, so old scores are invalid.
            db.query(MatchResult).filter_by(vacancy_id=vacancy_id).delete(synchronize_session=False)
            vacancy.analyzed_at = None
        db.commit()
    except Exception:
        db.rollback()
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise
    return {'accepted': accepted, 'errors': errors, 'requires_analysis': vacancy.analyzed_at is None}


def analyze(db, vacancy_id):
    vacancy = get_vacancy(db, vacancy_id, lock=True)
    resumes = db.query(Resume).filter_by(vacancy_id=vacancy_id).order_by(Resume.id).all()
    if not resumes:
        raise HTTPException(400, 'Сначала загрузите хотя бы одно резюме с текстом.')
    scores = score_batch(vacancy.description, vacancy.required_skills, [r.extracted_text for r in resumes])
    try:
        db.query(MatchResult).filter_by(vacancy_id=vacancy_id).delete(synchronize_session=False)
        vacancy.analysis_version += 1
        for resume, result in zip(resumes, scores):
            db.add(MatchResult(resume_id=resume.id, vacancy_id=vacancy_id,
                               analysis_version=vacancy.analysis_version, **result))
        vacancy.analyzed_at = utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'analyzed': len(resumes), 'analysis_version': vacancy.analysis_version}


def resume_summary(resume):
    return {'id': resume.id, 'filename': resume.filename, 'name': resume.parsed.get('name'),
            'email': resume.parsed.get('email'), 'shortlisted': resume.shortlisted}


def result_summary(result):
    return {key: getattr(result, key) for key in (
        'overall_score', 'skills_score', 'cosine_score', 'matching_skills', 'missing_skills',
        'evidence', 'algorithm', 'analysis_version', 'created_at')}


def ranking(db, vacancy_id, shortlisted_only=False):
    vacancy = get_vacancy(db, vacancy_id)
    if vacancy.analyzed_at is None:
        raise HTTPException(409, 'Рейтинг ещё не рассчитан или устарел. Запустите анализ.')
    query = db.query(Resume, MatchResult).join(MatchResult, MatchResult.resume_id == Resume.id).filter(Resume.vacancy_id == vacancy_id)
    rows = query.order_by(MatchResult.overall_score.desc(), MatchResult.cosine_score.desc(), Resume.id).all()
    return [{'rank': i, **resume_summary(resume), **result_summary(result)}
            for i, (resume, result) in enumerate(rows, 1) if not shortlisted_only or resume.shortlisted]
