from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Candidate
from ..schemas import CandidateCreate, CandidateRead
from ..services.candidates import DuplicateEmailError, create_candidate


router = APIRouter(prefix="/candidates", tags=["Candidates"])


@router.post("", response_model=CandidateRead)
def add_candidate(candidate: CandidateCreate, db: Session = Depends(get_db)):
    try:
        return create_candidate(db, candidate)
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=409, detail="A candidate with this email already exists") from exc


@router.get("", response_model=List[CandidateRead])
def get_candidates(db: Session = Depends(get_db)):
    return db.query(Candidate).order_by(Candidate.id).all()
