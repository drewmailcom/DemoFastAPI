"""The queue, the detections list, and the race-safe claim / close operations."""

from typing import Any

from fastapi import HTTPException
from psycopg import errors

from app import db

SELECT_DETECTIONS = """
  SELECT d.*, c.name AS customer_name, s.name AS signature_name, u.username AS assignee
  FROM detections d
  JOIN customers c ON c.id = d.customer_id
  JOIN signatures s ON s.id = d.signature_id
  LEFT JOIN users u ON u.id = d.assigned_to"""


def get_queue() -> list[dict[str, Any]]:
    """Only OPEN detections, most urgent first, oldest first within the same priority."""
    return db.query(f"{SELECT_DETECTIONS} WHERE d.status = 'OPEN' ORDER BY d.priority DESC, d.created_at, d.id")


def list_detections(
    status: str | None = None,
    customer_id: int | None = None,
    signature_id: int | None = None,
    min_priority: int | None = None,
) -> list[dict[str, Any]]:
    """Everything (open, in progress, closed), newest first, with optional filters."""
    filters = {
        "d.status = %s": status,
        "d.customer_id = %s": customer_id,
        "d.signature_id = %s": signature_id,
        "d.priority >= %s": min_priority,
    }
    active = {condition: value for condition, value in filters.items() if value is not None}
    where = f"WHERE {' AND '.join(active)}" if active else ""
    return db.query(
        f"{SELECT_DETECTIONS} {where} ORDER BY d.created_at DESC, d.id DESC LIMIT 500",
        tuple(active.values()),
    )


def get_active_detection(user_id: int) -> dict[str, Any] | None:
    return db.query_one(f"{SELECT_DETECTIONS} WHERE d.assigned_to = %s AND d.status = 'IN_PROGRESS'", (user_id,))


def claim_detection(detection_id: int, user_id: int) -> dict[str, Any]:
    """
    Race-safe claim. The UPDATE only succeeds while the row is still OPEN; Postgres locks the row,
    so when two analysts claim at once the second UPDATE re-checks `status = 'OPEN'`, finds it
    false and changes nothing. The unique index `one_active_detection_per_analyst` makes the
    database reject a second active detection for the same analyst.
    """
    try:
        claimed = db.execute(
            """UPDATE detections SET status = 'IN_PROGRESS', assigned_to = %s, assigned_at = now()
               WHERE id = %s AND status = 'OPEN'""",
            (user_id, detection_id),
        )
    except errors.UniqueViolation as error:
        if error.diag.constraint_name == "one_active_detection_per_analyst":
            raise HTTPException(409, "You already have an active detection. Close it before claiming another one.")
        raise

    if claimed:
        return get_active_detection(user_id)

    # Nothing was updated: explain why.
    current = db.query_one(
        "SELECT d.status, u.username FROM detections d LEFT JOIN users u ON u.id = d.assigned_to WHERE d.id = %s",
        (detection_id,),
    )
    if current is None:
        raise HTTPException(404, "Detection not found")
    if current["status"] == "CLOSED":
        raise HTTPException(409, "This detection is already closed.")
    raise HTTPException(409, f"Too late: this detection was already claimed by {current['username']}.")


def close_detection(detection_id: int, user_id: int, resolution: str) -> dict[str, Any]:
    """Closes the analyst's own active detection; same conditional-UPDATE approach as claiming."""
    closed = db.execute(
        """UPDATE detections SET status = 'CLOSED', resolution = %s, closed_at = now()
           WHERE id = %s AND assigned_to = %s AND status = 'IN_PROGRESS'""",
        (resolution, detection_id, user_id),
    )
    if not closed:
        raise HTTPException(409, "You can only close the detection you are currently working on.")
    return {"id": detection_id, "status": "CLOSED"}
