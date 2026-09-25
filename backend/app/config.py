import os
from pathlib import Path

from dotenv import load_dotenv


# Resolve the project .env independently of the server's working directory.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required. Copy .env.example to .env and configure it.")

STORAGE_DIR = Path(os.getenv('STORAGE_DIR', str(Path(__file__).resolve().parents[2] / 'data' / 'resumes'))).resolve()
