from sqlalchemy import Column, Integer, String
from .database import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    skills = Column(String)

from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, Text, UniqueConstraint


def utcnow():
    return datetime.now(timezone.utc)


class Vacancy(Base):
    __tablename__ = 'vacancies'
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    required_skills = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    analyzed_at = Column(DateTime(timezone=True))
    analysis_version = Column(Integer, default=0, nullable=False)


class Resume(Base):
    __tablename__ = 'resumes'
    __table_args__ = (UniqueConstraint('vacancy_id', 'sha256', name='uq_resume_vacancy_hash'),)
    id = Column(Integer, primary_key=True)
    vacancy_id = Column(Integer, ForeignKey('vacancies.id'), nullable=False, index=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'), nullable=True)
    filename = Column(String(255), nullable=False)
    storage_key = Column(String(40), nullable=False, unique=True)
    sha256 = Column(String(64), nullable=False)
    extracted_text = Column(Text, nullable=False)
    parsed = Column(JSON, nullable=False)
    shortlisted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class MatchResult(Base):
    __tablename__ = 'match_results'
    id = Column(Integer, primary_key=True)
    resume_id = Column(Integer, ForeignKey('resumes.id'), nullable=False, unique=True)
    vacancy_id = Column(Integer, ForeignKey('vacancies.id'), nullable=False, index=True)
    overall_score = Column(Float, nullable=False)
    cosine_score = Column(Float, nullable=False)
    skills_score = Column(Float)
    matching_skills = Column(JSON, nullable=False)
    missing_skills = Column(JSON, nullable=False)
    evidence = Column(JSON, nullable=False)
    algorithm = Column(String(80), nullable=False)
    analysis_version = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
