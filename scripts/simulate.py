"""Sends a random demo incident to /api/ingest every few seconds: python -m scripts.simulate"""

import json
import os
import random
import time

import httpx

from app.demo_data import INCIDENTS

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
API_KEY = os.environ.get("INGEST_API_KEY", "dev-ingest-key")
INTERVAL_SECONDS = float(os.environ.get("INTERVAL_SECONDS", "3"))

print(f"Sending an incident to {BASE_URL} every {INTERVAL_SECONDS}s (Ctrl+C to stop)")
while True:
    try:
        response = httpx.post(f"{BASE_URL}/api/ingest", json=random.choice(INCIDENTS), headers={"X-API-Key": API_KEY})
        print(response.status_code, json.dumps(response.json()))
    except httpx.HTTPError as error:
        print("Request failed:", error)
    time.sleep(INTERVAL_SECONDS)
