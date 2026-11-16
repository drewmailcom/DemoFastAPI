"""Signature matching: pure functions, no database access."""

from dataclasses import dataclass
from typing import Any


@dataclass
class Condition:
    field: str  # dot-path into the incident, e.g. "process.name"
    value: str


@dataclass
class Signature:
    id: int
    name: str
    priority: int
    conditions: list[Condition]


def get_field(payload: Any, path: str) -> Any:
    """Reads a value by dot-path: get_field({"process": {"name": "x"}}, "process.name") == "x"."""
    current = payload
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def as_text(value: Any) -> str | None:
    """A scalar as it is written in JSON (True -> "true", 3389 -> "3389"); None for objects, arrays and null."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def signature_matches(signature: Signature, payload: dict[str, Any]) -> bool:
    """
    A signature matches when EVERY condition's field exists in the incident with exactly that value.
    Values are compared as text, case-sensitively. Objects and arrays never match.
    """
    return bool(signature.conditions) and all(
        as_text(get_field(payload, condition.field)) == condition.value for condition in signature.conditions
    )


def find_matches(signatures: list[Signature], payload: dict[str, Any]) -> list[Signature]:
    """
    All matching signatures, best first: highest priority, then the most specific
    (more conditions), then the lowest id so the result is always deterministic.
    """
    matches = [signature for signature in signatures if signature_matches(signature, payload)]
    return sorted(matches, key=lambda s: (-s.priority, -len(s.conditions), s.id))
