from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Candidate
from ..schemas import CandidateCreate


class DuplicateEmailError(Exception):
    """The candidate email already exists in the database."""


def create_candidate(db: Session, candidate: CandidateCreate) -> Candidate:
    new_candidate = Candidate(**candidate.model_dump())
    db.add(new_candidate)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # PostgreSQL unique_violation; don't disguise unrelated DB failures as 409.
        if getattr(exc.orig, "pgcode", None) == "23505":
            existing = db.query(Candidate).filter(Candidate.email == candidate.email).first()
            if existing is not None:
                raise DuplicateEmailError from exc
        raise
    db.refresh(new_candidate)
    return new_candidate
