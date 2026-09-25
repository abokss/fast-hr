from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CandidateCreate(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=1)
    skills: str


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    skills: Optional[str] = None


from datetime import datetime
from typing import List
from pydantic import field_validator
from .nlp.skills import clean_skills


class VacancyCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=50000)
    required_skills: List[str] = Field(default_factory=list, max_length=100)

    @field_validator('title', 'description')
    @classmethod
    def strip_nonempty(cls, value):
        if not value.strip():
            raise ValueError('Поле не может быть пустым')
        return value.strip()

    @field_validator('required_skills')
    @classmethod
    def normalize_skills(cls, value):
        if any(len(skill) > 100 for skill in value):
            raise ValueError('Название навыка не должно превышать 100 символов')
        return clean_skills(value)


class VacancyRead(VacancyCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    analyzed_at: Optional[datetime]
    analysis_version: int


class ShortlistUpdate(BaseModel):
    shortlisted: bool
