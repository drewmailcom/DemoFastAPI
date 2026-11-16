"""Integration tests run a real server against a real Postgres test database (never the dev database)."""

import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/detections_test"
)

import socket
import threading
import time

import httpx
import pytest
import uvicorn

from app.demo_data import DEMO_PASSWORD


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    from app.main import app
    from app.seed import seed

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():
            pytest.exit("Test server failed to start. Is Postgres running? (docker compose up -d db)", returncode=1)
        time.sleep(0.05)
    seed()  # fresh demo data for every test run
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()


@pytest.fixture(scope="session")
def users(base_url) -> dict[str, httpx.Client]:
    """One logged-in HTTP client per demo user, plus "anonymous" without a session."""
    clients = {"anonymous": httpx.Client(base_url=base_url)}
    for username in ["admin", "analyst1", "analyst2", "support"]:
        client = httpx.Client(base_url=base_url)
        client.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD}).raise_for_status()
        clients[username] = client
    return clients
