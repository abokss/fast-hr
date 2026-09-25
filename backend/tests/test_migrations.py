import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from sqlalchemy import create_engine, inspect, text


class MigrationTests(unittest.TestCase):
    def migrate(self, legacy):
        with tempfile.TemporaryDirectory() as directory:
            url = 'sqlite:///' + str(Path(directory) / 'test.db')
            engine = create_engine(url)
            if legacy:
                with engine.begin() as conn:
                    conn.execute(text('CREATE TABLE candidates (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, email VARCHAR NOT NULL UNIQUE, skills VARCHAR)'))
                    conn.execute(text("INSERT INTO candidates VALUES (1, 'Preserved', 'test@example.com', NULL)"))
            env = dict(os.environ, DATABASE_URL=url, PYTHONDONTWRITEBYTECODE='1')
            for _ in range(2):
                run = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(set(inspect(engine).get_table_names()), {'alembic_version', 'candidates', 'vacancies', 'resumes', 'match_results'})
            if legacy:
                with engine.connect() as conn:
                    self.assertEqual(conn.execute(text('SELECT name FROM candidates WHERE id=1')).scalar(), 'Preserved')
            engine.dispose()

    def test_fresh_database(self):
        self.migrate(False)

    def test_existing_candidates_preserved(self):
        self.migrate(True)
