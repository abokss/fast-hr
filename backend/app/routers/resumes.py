from fastapi import APIRouter, UploadFile, File, HTTPException
from ..services.resume_parser import extract_pdf, ResumeParseError, MAX_BYTES

router = APIRouter(prefix='/resumes', tags=['Resumes'])


@router.post('/upload')
def upload_resume(file: UploadFile = File(...)):
    try:
        return {'filename': file.filename, 'text': extract_pdf(file.file.read(MAX_BYTES + 1))}
    except ResumeParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        file.file.close()
