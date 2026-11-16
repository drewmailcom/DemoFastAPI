"""Fires many simultaneous claims for the same detection; exactly one must win: python -m scripts.race"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.demo_data import DEMO_PASSWORD, INCIDENTS

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
API_KEY = os.environ.get("INGEST_API_KEY", "dev-ingest-key")
ATTEMPTS = 10
ANALYSTS = ["analyst1", "analyst2"]


def login(username: str) -> httpx.Client:
    client = httpx.Client(base_url=BASE_URL)
    client.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD}).raise_for_status()
    return client


clients = [login(username) for username in ANALYSTS]

# Free both analysts first, so the only thing competing is the claim itself.
for client in clients:
    active = client.get("/api/me").json()["active_detection"]
    if active:
        client.post(f"/api/detections/{active['id']}/close", json={"resolution": "Closed by race demo"})

ingested = httpx.post(f"{BASE_URL}/api/ingest", json=INCIDENTS[0], headers={"X-API-Key": API_KEY}).json()
detection_id = ingested["detection_id"]
print(f"New detection #{detection_id}. Sending {ATTEMPTS} simultaneous claims...\n")

attempts = [(ANALYSTS[i % 2], clients[i % 2]) for i in range(ATTEMPTS)]
with ThreadPoolExecutor(max_workers=ATTEMPTS) as pool:
    responses = list(pool.map(lambda a: a[1].post(f"/api/detections/{detection_id}/claim"), attempts))

for (username, _), response in zip(attempts, responses):
    outcome = "CLAIMED" if response.status_code == 200 else response.json()["detail"]
    print(f"{username:<9} -> {response.status_code} {outcome}")

winners = sum(response.status_code == 200 for response in responses)
print(f"\nWinners: {winners} (expected exactly 1)")
sys.exit(0 if winners == 1 else 1)
