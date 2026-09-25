import re
from io import BytesIO
from pypdf import PdfReader
from ..nlp.skills import extract_skills

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 30
MAX_TEXT = 200000


class ResumeParseError(ValueError):
    pass


def extract_pdf(contents):
    if not contents or len(contents) > MAX_BYTES:
        raise ResumeParseError('PDF должен быть непустым и не превышать 10 МБ.')
    if not contents.startswith(b'%PDF-'):
        raise ResumeParseError('Файл не является PDF.')
    try:
        reader = PdfReader(BytesIO(contents))
        if reader.is_encrypted:
            raise ResumeParseError('PDF защищён паролем. Загрузите незашифрованную копию.')
        if len(reader.pages) > MAX_PAGES:
            raise ResumeParseError('В одном CV допускается не более 30 страниц.')
        parts = []
        size = 0
        for page in reader.pages:
            part = page.extract_text() or ''
            size += len(part)
            if size > MAX_TEXT:
                raise ResumeParseError('В PDF слишком много текста для одного резюме.')
            parts.append(part)
        text = '\n'.join(parts).replace('\x00', '').strip()
    except ResumeParseError:
        raise
    except Exception as exc:
        raise ResumeParseError('Не удалось прочитать PDF: файл повреждён или не поддерживается.') from exc
    if not re.search(r'\w', text):
        raise ResumeParseError('Текст не найден. Для скана нужен OCR; загрузите PDF с текстовым слоем.')
    return text


def parse_information(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    email = re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', text)
    phones = re.findall(r'(?<!\w)\+?\d[\d ()-]{7,}\d', text)
    phone = next((p.strip() for p in phones if 10 <= len(re.sub(r'\D', '', p)) <= 15), None)
    name = None
    for line in lines[:3]:
        words = line.split()
        if 2 <= len(words) <= 4 and all(w.replace('-', '').replace("'", '').isalpha() and w[0].isupper() for w in words):
            if not re.search(r'developer|engineer|resume|curriculum|vitae|резюме|разработчик|инженер', line, re.I):
                name = line
                break
    sections = {'experience': [], 'education': [], 'projects': []}
    active = None
    headers = {'experience': r'^(work experience|experience|employment|опыт работы|опыт)$',
               'education': r'^(education|образование)$',
               'projects': r'^(projects|проекты)$'}
    for line in lines:
        heading = line.strip(' :').casefold()
        found = next((k for k, pattern in headers.items() if re.match(pattern, heading)), None)
        if found:
            active = found
        elif re.match(r'^(skills|навыки|languages|языки|certifications|сертификаты|summary|о себе)$', heading):
            active = None
        elif active and sum(len(x) for x in sections[active]) < 3000:
            sections[active].append(line)
    return {'name': name, 'name_is_inferred': name is not None,
            'email': email.group(0) if email else None, 'phone': phone,
            'skills': extract_skills(text),
            'sections': {k: '\n'.join(v) for k, v in sections.items()}}
