"""Settings from environment variables (or a .env file). Defaults are for local development only."""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/detections")
INGEST_API_KEY = os.environ.get("INGEST_API_KEY", "dev-ingest-key")
SECURE_COOKIES = os.environ.get("ENV") == "production"
