from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app import db
from app.validation import Text


class CustomerIn(BaseModel):
    name: Text
    importance: int = Field(ge=1, le=5)


def list_customers() -> list[dict[str, Any]]:
    return db.query("SELECT * FROM customers ORDER BY importance DESC, name")


def create_customer(customer: CustomerIn) -> dict[str, Any]:
    return db.query_one(
        "INSERT INTO customers (name, importance) VALUES (%s, %s) RETURNING *",
        (customer.name, customer.importance),
    )


def update_customer(customer_id: int, customer: CustomerIn) -> dict[str, Any]:
    row = db.query_one(
        "UPDATE customers SET name = %s, importance = %s WHERE id = %s RETURNING *",
        (customer.name, customer.importance, customer_id),
    )
    if row is None:
        raise HTTPException(404, "Customer not found")
    return row


def delete_customer(customer_id: int) -> None:
    if not db.execute("DELETE FROM customers WHERE id = %s", (customer_id,)):
        raise HTTPException(404, "Customer not found")
