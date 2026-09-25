"""Adopt the existing candidate table and add the V1 screening tables."""
from alembic import op
import sqlalchemy as sa

revision = '001_screening'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # The legacy project created candidates manually. Preserve it and its rows.
    if not sa.inspect(bind).has_table('candidates'):
        op.create_table('candidates', sa.Column('id', sa.Integer, primary_key=True),
                        sa.Column('name', sa.String, nullable=False),
                        sa.Column('email', sa.String, nullable=False, unique=True),
                        sa.Column('skills', sa.String))
        op.create_index('ix_candidates_id', 'candidates', ['id'])
    op.create_table('vacancies', sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(200), nullable=False), sa.Column('description', sa.Text, nullable=False),
        sa.Column('required_skills', sa.JSON, nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('analyzed_at', sa.DateTime(timezone=True)), sa.Column('analysis_version', sa.Integer, nullable=False))
    op.create_table('resumes', sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('vacancy_id', sa.Integer, sa.ForeignKey('vacancies.id'), nullable=False),
        sa.Column('candidate_id', sa.Integer, sa.ForeignKey('candidates.id')),
        sa.Column('filename', sa.String(255), nullable=False), sa.Column('storage_key', sa.String(40), nullable=False, unique=True),
        sa.Column('sha256', sa.String(64), nullable=False), sa.Column('extracted_text', sa.Text, nullable=False),
        sa.Column('parsed', sa.JSON, nullable=False), sa.Column('shortlisted', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('vacancy_id', 'sha256', name='uq_resume_vacancy_hash'))
    op.create_index('ix_resumes_vacancy_id', 'resumes', ['vacancy_id'])
    op.create_table('match_results', sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('resume_id', sa.Integer, sa.ForeignKey('resumes.id'), nullable=False, unique=True),
        sa.Column('vacancy_id', sa.Integer, sa.ForeignKey('vacancies.id'), nullable=False),
        sa.Column('overall_score', sa.Float, nullable=False), sa.Column('cosine_score', sa.Float, nullable=False),
        sa.Column('skills_score', sa.Float), sa.Column('matching_skills', sa.JSON, nullable=False),
        sa.Column('missing_skills', sa.JSON, nullable=False), sa.Column('evidence', sa.JSON, nullable=False),
        sa.Column('algorithm', sa.String(80), nullable=False), sa.Column('analysis_version', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_match_results_vacancy_id', 'match_results', ['vacancy_id'])


def downgrade():
    raise RuntimeError('Destructive downgrade disabled: restore a verified backup instead.')
