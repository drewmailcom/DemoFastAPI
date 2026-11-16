# Runs the app with Python (no Docker for the app itself). Needs Python 3.12+ and a reachable Postgres:
# either set DATABASE_URL in .env (see .env.example) or start one with: docker compose up -d db
$ErrorActionPreference = "Stop"
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install --quiet -r requirements-dev.txt
Write-Host "Starting on http://localhost:8000 (users: admin / analyst1 / analyst2 / support, password demo1234)"
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
