from psycopg.types.json import Jsonb

from app import db
from app.auth import hash_password
from app.demo_data import CUSTOMERS, DEMO_PASSWORD, INCIDENTS, SIGNATURES, USERS
from app.ingest import ingest_incident


def seed() -> None:
    """Wipes all data and loads the demo users, customers, signatures and a few incidents."""
    db.execute("TRUNCATE users, sessions, customers, signatures, detections, unmatched_incidents RESTART IDENTITY CASCADE")
    password_hash = hash_password(DEMO_PASSWORD)
    for username, role in USERS:
        db.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)", (username, password_hash, role))
    for name, importance in CUSTOMERS:
        db.execute("INSERT INTO customers (name, importance) VALUES (%s, %s)", (name, importance))
    for name, priority, conditions in SIGNATURES:
        condition_list = [{"field": field, "value": value} for field, value in conditions.items()]
        db.execute(
            "INSERT INTO signatures (name, priority, conditions) VALUES (%s, %s, %s)",
            (name, priority, Jsonb(condition_list)),
        )
    for incident in INCIDENTS:
        ingest_incident(incident)


def seed_if_empty() -> None:
    if db.query_one("SELECT count(*) AS count FROM users")["count"] == 0:
        seed()
