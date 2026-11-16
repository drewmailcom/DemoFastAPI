"""Turns an incoming incident into a detection (or stores it as unmatched)."""

from typing import Any

from psycopg.types.json import Jsonb

from app import db
from app.matching import Condition, Signature, find_matches
from app.priority import detection_priority


def ingest_incident(payload: dict[str, Any]) -> dict[str, Any]:
    """
    1. find the customer (payload["customer_id"])
    2. find matching signatures and keep the best one
    3. priority = customer importance x signature priority
    4. insert the detection; status OPEN puts it in the queue
    Incidents without a known customer or a matching signature go to `unmatched_incidents`.
    """
    customer = find_customer(payload.get("customer_id"))
    if customer is None:
        return store_unmatched(payload, "UNKNOWN_CUSTOMER")

    matches = find_matches(load_signatures(), payload)
    if not matches:
        return store_unmatched(payload, "NO_SIGNATURE")

    best = matches[0]
    priority = detection_priority(customer["importance"], best.priority)
    matched_ids = [signature.id for signature in matches]
    row = db.query_one(
        """INSERT INTO detections
             (customer_id, signature_id, matched_signature_ids, customer_importance, signature_priority, priority, payload)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (customer["id"], best.id, matched_ids, customer["importance"], best.priority, priority, Jsonb(payload)),
    )
    return {
        "outcome": "detection",
        "detection_id": row["id"],
        "signature_id": best.id,
        "matched_signature_ids": matched_ids,
        "priority": priority,
    }


def find_customer(customer_id: Any) -> dict[str, Any] | None:
    if not isinstance(customer_id, int) or isinstance(customer_id, bool):
        return None
    return db.query_one("SELECT id, importance FROM customers WHERE id = %s", (customer_id,))


def load_signatures() -> list[Signature]:
    return [
        Signature(
            id=row["id"],
            name=row["name"],
            priority=row["priority"],
            conditions=[Condition(**condition) for condition in row["conditions"]],
        )
        for row in db.query("SELECT id, name, priority, conditions FROM signatures")
    ]


def store_unmatched(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    db.execute("INSERT INTO unmatched_incidents (reason, payload) VALUES (%s, %s)", (reason, Jsonb(payload)))
    return {"outcome": "unmatched", "reason": reason}


def list_unmatched() -> list[dict[str, Any]]:
    return db.query("SELECT * FROM unmatched_incidents ORDER BY received_at DESC, id DESC LIMIT 200")
