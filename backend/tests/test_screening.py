import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ['DATABASE_URL'] = 'sqlite://'
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import Base, get_db
from app.models import MatchResult, Resume
from app.nlp.matching import score_batch, tokens
from app.nlp.skills import clean_skills, extract_skills
from app.services.resume_parser import extract_pdf, ResumeParseError


def pdf(text):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    escape = lambda s: s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    commands = ['BT /F1 12 Tf 40 740 Td 16 TL'] + [f'({escape(line)}) Tj T*' for line in text.splitlines()] + ['ET']
    stream = DecodedStreamObject(); stream.set_data('\n'.join(commands).encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO(); writer.write(output)
    return output.getvalue()


class MatchingTests(unittest.TestCase):
    def test_skill_fraction_missing_and_evidence(self):
        scores = score_batch('Python FastAPI Docker AWS', ['Python', 'FastAPI', 'Docker', 'AWS'], ['Python FastAPI Docker', 'Photoshop design'])
        self.assertEqual(scores[0]['overall_score'], 75)
        self.assertEqual(scores[0]['missing_skills'], ['AWS'])
        self.assertEqual(scores[1]['overall_score'], 0)
        self.assertEqual(set(scores[0]['evidence']), {'Python', 'FastAPI', 'Docker'})
        self.assertGreater(scores[0]['cosine_score'], scores[1]['cosine_score'])

    def test_aliases_boundaries_custom_skills_and_tokens(self):
        self.assertEqual(clean_skills([' postgres ', 'PostgreSQL', 'python']), ['PostgreSQL', 'Python'])
        self.assertNotIn('Java', extract_skills('JavaScript GitHub'))
        self.assertNotIn('Git', extract_skills('GitHub'))
        self.assertIn('C++', extract_skills('C++, C#'))
        self.assertIn('c++', tokens('C++ C# Node.js'))
        self.assertEqual(score_batch('Figma', ['Figma'], ['Figma'])[0]['overall_score'], 100)

    def test_no_skills_and_empty_vocabulary(self):
        score = score_batch('Python Docker', [], ['Python Docker'])[0]
        self.assertIsNone(score['skills_score']); self.assertAlmostEqual(score['overall_score'], 100)
        self.assertEqual(score_batch('!!!', [], ['???'])[0]['overall_score'], 0)

    def test_scan_and_encrypted_pdf_errors(self):
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
        output = io.BytesIO(); writer.write(output)
        with self.assertRaisesRegex(ResumeParseError, 'OCR'): extract_pdf(output.getvalue())
        writer.encrypt('secret'); output = io.BytesIO(); writer.write(output)
        with self.assertRaisesRegex(ResumeParseError, 'паролем'): extract_pdf(output.getvalue())


class ScreeningAPITests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        def get_test_db():
            with self.sessions() as db: yield db
        app.dependency_overrides[get_db] = get_test_db
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch('app.services.screening.STORAGE_DIR', Path(self.tmp.name)), patch('app.routers.vacancies.STORAGE_DIR', Path(self.tmp.name))]
        for p in self.patches: p.start()
        self.client = TestClient(app); self.client.__enter__()
        result = self.client.post('/vacancies', json={'title': 'Backend', 'description': 'Python FastAPI Docker AWS', 'required_skills': ['Python', 'FastAPI', 'Docker', 'AWS']})
        self.assertEqual(result.status_code, 201)
        self.base = '/vacancies/' + str(result.json()['id'])

    def tearDown(self):
        self.client.__exit__(None, None, None); app.dependency_overrides.clear()
        for p in self.patches: p.stop()
        self.tmp.cleanup(); self.engine.dispose()

    def upload(self, contents):
        return self.client.post(self.base + '/resumes', files=[('files', ('resume.pdf', contents, 'application/pdf'))])

    def test_workflow_partial_failure_shortlist_and_invalidation(self):
        strong = pdf('Alex Example\nalex@example.com\nPython FastAPI Docker\nExperience\nBuilt APIs')
        response = self.client.post(self.base + '/resumes', files=[('files', ('strong.pdf', strong, 'application/pdf')), ('files', ('weak.pdf', pdf('Taylor Example\nDesign Photoshop'), 'application/pdf')), ('files', ('broken.pdf', b'not a pdf', 'application/pdf'))])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['accepted']), 2); self.assertEqual(len(response.json()['errors']), 1)
        self.assertEqual(self.client.get(self.base + '/ranking').status_code, 409)
        self.assertEqual(self.client.post(self.base + '/analyze').json()['analyzed'], 2)
        ranking = self.client.get(self.base + '/ranking').json()
        self.assertEqual([r['overall_score'] for r in ranking], [75, 0])
        rid = ranking[0]['id']
        detail = self.client.get(self.base + f'/resumes/{rid}').json()
        self.assertEqual(detail['parsed']['email'], 'alex@example.com')
        self.assertIn('Built APIs', detail['parsed']['sections']['experience'])
        self.assertEqual(self.client.get(self.base + f'/resumes/{rid}/file').content, strong)
        self.client.patch(self.base + f'/resumes/{rid}/shortlist', json={'shortlisted': True})
        self.assertEqual(len(self.client.get(self.base + '/ranking?shortlisted_only=true').json()), 1)
        self.assertEqual(self.upload(strong).json()['errors'][0]['code'], 'duplicate')
        self.assertEqual(self.client.get(self.base + '/ranking').status_code, 200)
        self.upload(pdf('Morgan Example\nAWS Python'))
        self.assertEqual(self.client.get(self.base + '/ranking').status_code, 409)
        self.assertEqual(self.client.post(self.base + '/analyze').json()['analysis_version'], 2)
        self.assertEqual(len(self.client.get(self.base + '/ranking?shortlisted_only=true').json()), 1)
        with self.sessions() as db: self.assertEqual(db.query(MatchResult).count(), 3)

    def test_missing_ids_empty_analysis_wrong_vacancy(self):
        self.assertEqual(self.client.post(self.base + '/analyze').status_code, 400)
        self.assertEqual(self.client.get('/vacancies/9999').status_code, 404)
        rid = self.upload(pdf('Alex Example\nPython')).json()['accepted'][0]['id']
        self.assertEqual(self.client.get(f'/vacancies/9999/resumes/{rid}').status_code, 404)
        self.assertEqual(self.client.get(f'/vacancies/9999/resumes/{rid}/file').status_code, 404)

    def test_batch_100_and_repeat_analysis(self):
        started = time.perf_counter()
        files = [('files', (f'cv-{i}.pdf', pdf(f'Candidate Number\nID {i}\n' + ('Python FastAPI Docker AWS' if i % 2 else 'Python')), 'application/pdf')) for i in range(100)]
        response = self.client.post(self.base + '/resumes', files=files)
        self.assertEqual(len(response.json()['accepted']), 100)
        self.assertEqual(self.client.post(self.base + '/analyze').json()['analyzed'], 100)
        ranking = self.client.get(self.base + '/ranking').json()
        self.assertEqual(len(ranking), 100); self.assertEqual(ranking[0]['overall_score'], 100); self.assertEqual(ranking[-1]['overall_score'], 25)
        self.client.post(self.base + '/analyze')
        rerun = self.client.get(self.base + '/ranking').json()
        self.assertEqual([r['id'] for r in ranking], [r['id'] for r in rerun])
        with self.sessions() as db: self.assertEqual(db.query(MatchResult).count(), 100)
        print(f'100 synthetic PDFs: upload + two analyses {time.perf_counter()-started:.2f}s')

    def test_failure_rolls_back_and_cleans_files(self):
        with patch('app.services.screening.parse_information', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError): self.upload(pdf('Alex Example\nPython'))
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])
        with self.sessions() as db: self.assertEqual(db.query(Resume).count(), 0)

    def test_validation_limits(self):
        self.assertEqual(self.client.post('/vacancies', json={'title': ' ', 'description': 'x'}).status_code, 422)
        with patch('app.services.screening.MAX_RESUMES', 0): self.assertEqual(len(self.upload(pdf('Alex Example\nPython')).json()['errors']), 1)
        with patch('app.services.screening.MAX_BYTES', 5): self.assertEqual(len(self.upload(pdf('Alex Example')).json()['errors']), 1)
