#!/usr/bin/env sh
# Runs the app with Python (no Docker for the app itself). Needs Python 3.12+ and a reachable Postgres:
# either set DATABASE_URL in .env (see .env.example) or start one with: docker compose up -d db
set -e
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet -r requirements-dev.txt
echo "Starting on http://localhost:8000 (users: admin / analyst1 / analyst2 / support, password demo1234)"
exec .venv/bin/python -m uvicorn app.main:app --port 8000
