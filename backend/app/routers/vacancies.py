from typing import List
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..config import STORAGE_DIR
from ..database import get_db
from ..models import Vacancy, Resume, MatchResult
from ..schemas import VacancyCreate, VacancyRead, ShortlistUpdate
from ..services import screening

router = APIRouter(prefix='/vacancies', tags=['Vacancies'])


@router.post('', response_model=VacancyRead, status_code=201)
def create_vacancy(body: VacancyCreate, db: Session = Depends(get_db)):
    vacancy = Vacancy(**body.model_dump())
    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)
    return vacancy


@router.get('', response_model=List[VacancyRead])
def list_vacancies(db: Session = Depends(get_db)):
    return db.query(Vacancy).order_by(Vacancy.id.desc()).all()


@router.get('/{vacancy_id}', response_model=VacancyRead)
def read_vacancy(vacancy_id: int, db: Session = Depends(get_db)):
    return screening.get_vacancy(db, vacancy_id)


@router.post('/{vacancy_id}/resumes')
def upload_batch(vacancy_id: int, files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    return screening.import_resumes(db, vacancy_id, files)


@router.get('/{vacancy_id}/resumes')
def list_resumes(vacancy_id: int, db: Session = Depends(get_db)):
    screening.get_vacancy(db, vacancy_id)
    return [screening.resume_summary(r) for r in db.query(Resume).filter_by(vacancy_id=vacancy_id).order_by(Resume.id)]


@router.post('/{vacancy_id}/analyze')
def analyze(vacancy_id: int, db: Session = Depends(get_db)):
    return screening.analyze(db, vacancy_id)


@router.get('/{vacancy_id}/ranking')
def ranking(vacancy_id: int, shortlisted_only: bool = False, db: Session = Depends(get_db)):
    return screening.ranking(db, vacancy_id, shortlisted_only)


@router.get('/{vacancy_id}/resumes/{resume_id}')
def detail(vacancy_id: int, resume_id: int, db: Session = Depends(get_db)):
    resume = screening.get_resume(db, vacancy_id, resume_id)
    result = db.query(MatchResult).filter_by(resume_id=resume.id).first()
    return {**screening.resume_summary(resume), 'parsed': resume.parsed,
            'text': resume.extracted_text, 'analysis': screening.result_summary(result) if result else None}


@router.patch('/{vacancy_id}/resumes/{resume_id}/shortlist')
def shortlist(vacancy_id: int, resume_id: int, body: ShortlistUpdate, db: Session = Depends(get_db)):
    screening.get_vacancy(db, vacancy_id, lock=True)
    resume = screening.get_resume(db, vacancy_id, resume_id)
    resume.shortlisted = body.shortlisted
    db.commit()
    return screening.resume_summary(resume)


@router.get('/{vacancy_id}/resumes/{resume_id}/file')
def original(vacancy_id: int, resume_id: int, db: Session = Depends(get_db)):
    resume = screening.get_resume(db, vacancy_id, resume_id)
    path = STORAGE_DIR / resume.storage_key
    if not path.is_file():
        raise HTTPException(404, 'Оригинал PDF отсутствует в хранилище')
    return FileResponse(path, media_type='application/pdf', filename=resume.filename)
