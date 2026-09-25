import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ['DATABASE_URL'] = 'sqlite://'

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Candidate
from app.routers.candidates import add_candidate
from app.schemas import CandidateCreate
from app.services.candidates import create_candidate


async def request(method, path, body=None):
    messages = []
    payload = json.dumps(body).encode() if body is not None else b''
    scope = {
        'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
        'method': method, 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
        'query_string': b'', 'root_path': '',
        'headers': [(b'content-type', b'application/json')],
        'server': ('test', 80), 'client': ('test', 123),
    }
    async def receive():
        return {'type': 'http.request', 'body': payload, 'more_body': False}
    async def send(message):
        messages.append(message)
    await app(scope, receive, send)
    status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
    data = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
    return status, json.loads(data)


class CandidateAPITests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        def override_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = override_db

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_create_list_and_response_contract(self):
        body = {'name': 'Alex', 'email': 'alex@example.com', 'skills': 'Python'}
        status, result = asyncio.run(request('POST', '/candidates', body))
        self.assertEqual(status, 200)
        self.assertEqual(result, dict(body, id=1))
        status, result = asyncio.run(request('GET', '/candidates'))
        self.assertEqual(status, 200)
        self.assertEqual(result, [dict(body, id=1)])

    def test_existing_null_skills_can_be_read(self):
        with self.sessions() as db:
            db.add(Candidate(name='Legacy', email='legacy@example.com', skills=None))
            db.commit()
        status, result = asyncio.run(request('GET', '/candidates'))
        self.assertEqual(status, 200)
        self.assertIsNone(result[0]['skills'])

    def test_invalid_request_does_not_write(self):
        for body in ({'name': '', 'email': 'a@b.com', 'skills': ''}, {'name': 'Alex'}):
            status, _ = asyncio.run(request('POST', '/candidates', body))
            self.assertEqual(status, 422)
        _, result = asyncio.run(request('GET', '/candidates'))
        self.assertEqual(result, [])

    def test_root_and_existing_upload_route(self):
        status, result = asyncio.run(request('GET', '/'))
        self.assertEqual(status, 200)
        self.assertEqual(result, {'message': 'Fast HR API is running'})
        self.assertIn('/resumes/upload', app.openapi()['paths'])


class DatabaseErrorTests(unittest.TestCase):
    def setUp(self):
        self.candidate = CandidateCreate(name='Alex', email='alex@example.com', skills='Python')

    def failing_session(self, code, exists):
        db = Mock()
        original = Exception('database error')
        original.pgcode = code
        error = IntegrityError('INSERT', {}, original)
        db.commit.side_effect = error
        def lookup():
            db.rollback.assert_called_once()
            return SimpleNamespace(id=1) if exists else None
        db.query.return_value.filter.return_value.first.side_effect = lookup
        return db, error

    def test_duplicate_email_returns_409_and_rolls_back(self):
        db, _ = self.failing_session('23505', True)
        with self.assertRaises(HTTPException) as caught:
            add_candidate(self.candidate, db)
        self.assertEqual(caught.exception.status_code, 409)
        db.rollback.assert_called_once()
        db.refresh.assert_not_called()

    def test_other_integrity_error_is_not_disguised(self):
        db, error = self.failing_session('23502', False)
        with self.assertRaises(IntegrityError) as caught:
            create_candidate(db, self.candidate)
        self.assertIs(caught.exception, error)
        db.rollback.assert_called_once()
        db.query.assert_not_called()

    def test_unique_error_without_duplicate_email_is_not_disguised(self):
        db, error = self.failing_session('23505', False)
        with self.assertRaises(IntegrityError) as caught:
            create_candidate(db, self.candidate)
        self.assertIs(caught.exception, error)
        db.rollback.assert_called_once()


if __name__ == '__main__':
    unittest.main()
