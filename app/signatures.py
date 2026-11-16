from typing import Any

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app import db
from app.validation import Text


class ConditionIn(BaseModel):
    field: Text  # dot-path, e.g. "process.name"
    value: Text


class SignatureIn(BaseModel):
    name: Text
    priority: int = Field(ge=1, le=5)
    conditions: list[ConditionIn] = Field(min_length=1)

    def conditions_json(self) -> Jsonb:
        return Jsonb([condition.model_dump() for condition in self.conditions])


def list_signatures() -> list[dict[str, Any]]:
    return db.query("SELECT * FROM signatures ORDER BY priority DESC, name")


def create_signature(signature: SignatureIn) -> dict[str, Any]:
    return db.query_one(
        "INSERT INTO signatures (name, priority, conditions) VALUES (%s, %s, %s) RETURNING *",
        (signature.name, signature.priority, signature.conditions_json()),
    )


def update_signature(signature_id: int, signature: SignatureIn) -> dict[str, Any]:
    row = db.query_one(
        "UPDATE signatures SET name = %s, priority = %s, conditions = %s WHERE id = %s RETURNING *",
        (signature.name, signature.priority, signature.conditions_json(), signature_id),
    )
    if row is None:
        raise HTTPException(404, "Signature not found")
    return row


def delete_signature(signature_id: int) -> None:
    if not db.execute("DELETE FROM signatures WHERE id = %s", (signature_id,)):
        raise HTTPException(404, "Signature not found")
