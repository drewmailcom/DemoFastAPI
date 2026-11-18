"""Turns an incoming incident into a detection (or stores it as unmatched), and retries unmatched ones later."""

from dataclasses import dataclass
from typing import Any

from psycopg.types.json import Jsonb

from app import db
from app.matching import Condition, Signature, find_matches
from app.priority import detection_priority

# created_at: the time the incident was received, so a reprocessed incident keeps its place in the queue.
INSERT_DETECTION = """
  INSERT INTO detections
    (customer_id, signature_id, matched_signature_ids, customer_importance, signature_priority, priority, payload,
     created_at)
  VALUES (%s, %s, %s, %s, %s, %s, %s, COALESCE(%s::timestamptz, now())) RETURNING id"""


@dataclass
class Match:
    customer: dict[str, Any]
    signatures: list[Signature]  # best first

    @property
    def best(self) -> Signature:
        return self.signatures[0]

    @property
    def priority(self) -> int:
        return detection_priority(self.customer["importance"], self.best.priority)

    def insert_params(self, payload: dict[str, Any], received_at: Any = None) -> tuple:
        return (
            self.customer["id"],
            self.best.id,
            [signature.id for signature in self.signatures],
            self.customer["importance"],
            self.best.priority,
            self.priority,
            Jsonb(payload),
            received_at,
        )


def evaluate(payload: dict[str, Any], customer: dict[str, Any] | None, signatures: list[Signature]) -> Match | str:
    """A Match, or the reason the incident cannot become a detection ("UNKNOWN_CUSTOMER" / "NO_SIGNATURE")."""
    if customer is None:
        return "UNKNOWN_CUSTOMER"
    matches = find_matches(signatures, payload)
    if not matches:
        return "NO_SIGNATURE"
    return Match(customer, matches)


def ingest_incident(payload: dict[str, Any]) -> dict[str, Any]:
    """
    1. find the customer (payload["customer_id"])
    2. find matching signatures and keep the best one
    3. priority = customer importance x signature priority
    4. insert the detection; status OPEN puts it in the queue
    Incidents without a known customer or a matching signature go to `unmatched_incidents`.
    """
    outcome = evaluate(payload, find_customer(payload.get("customer_id")), load_signatures())
    if isinstance(outcome, str):
        return store_unmatched(payload, outcome)

    row = db.query_one(INSERT_DETECTION, outcome.insert_params(payload))
    return {
        "outcome": "detection",
        "detection_id": row["id"],
        "signature_id": outcome.best.id,
        "matched_signature_ids": [signature.id for signature in outcome.signatures],
        "priority": outcome.priority,
    }


def reprocess_unmatched() -> int:
    """
    Retries every unmatched incident against the current customers and signatures; called after a signature
    is created or edited and after a customer is added. Each incident that now matches becomes a detection
    (with its original receive time) and leaves `unmatched_incidents`, in one transaction. FOR UPDATE SKIP
    LOCKED makes concurrent runs skip rows another run is handling, so no incident becomes two detections.
    Returns how many detections were created.
    """
    signatures = load_signatures()
    created = 0
    with db.pool.connection() as conn, conn.transaction():
        customers = {row["id"]: row for row in conn.execute("SELECT id, importance FROM customers")}
        incidents = conn.execute(
            "SELECT id, reason, payload, received_at FROM unmatched_incidents ORDER BY id FOR UPDATE SKIP LOCKED"
        ).fetchall()
        for incident in incidents:
            payload = incident["payload"]
            customer_id = payload.get("customer_id") if isinstance(payload, dict) else None
            customer = customers.get(customer_id) if is_customer_id(customer_id) else None
            outcome = evaluate(payload, customer, signatures)
            if isinstance(outcome, str):
                if outcome != incident["reason"]:  # e.g. the customer now exists but no signature matches yet
                    conn.execute("UPDATE unmatched_incidents SET reason = %s WHERE id = %s", (outcome, incident["id"]))
                continue
            conn.execute(INSERT_DETECTION, outcome.insert_params(payload, incident["received_at"]))
            conn.execute("DELETE FROM unmatched_incidents WHERE id = %s", (incident["id"],))
            created += 1
    return created


def is_customer_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def find_customer(customer_id: Any) -> dict[str, Any] | None:
    if not is_customer_id(customer_id):
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
