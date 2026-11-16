"""Users, passwords, sessions and the FastAPI dependencies that enforce roles."""

import hashlib
import hmac
import secrets
from enum import StrEnum

from fastapi import Cookie, Depends, Header, HTTPException, Response
from pydantic import BaseModel

from app import config, db

SESSION_COOKIE = "sid"
SESSION_HOURS = 12


class Role(StrEnum):
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    READ_ONLY = "READ_ONLY"


class User(BaseModel):
    id: int
    username: str
    role: Role


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split(":")
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(candidate.hex(), digest)


def login(response: Response, username: str, password: str) -> User:
    """Checks the credentials, stores a server-side session and sets it as an httpOnly cookie."""
    row = db.query_one("SELECT id, username, role, password_hash FROM users WHERE username = %s", (username,))
    if row is None or not verify_password(password, row["password_hash"]):
        raise HTTPException(401, "Invalid username or password")

    session_id = secrets.token_hex(32)
    db.execute(
        "INSERT INTO sessions (id, user_id, expires_at) VALUES (%s, %s, now() + make_interval(hours => %s))",
        (session_id, row["id"], SESSION_HOURS),
    )
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        secure=config.SECURE_COOKIES,
        max_age=SESSION_HOURS * 3600,
    )
    return User(id=row["id"], username=row["username"], role=row["role"])


def logout(response: Response, session_id: str | None) -> None:
    db.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
    response.delete_cookie(SESSION_COOKIE)


# ---- FastAPI dependencies ---------------------------------------------------------------------


def current_user(sid: str | None = Cookie(default=None)) -> User:
    """Loads the logged-in user from the session cookie, or answers 401."""
    row = sid and db.query_one(
        """SELECT u.id, u.username, u.role FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.id = %s AND s.expires_at > now()""",
        (sid,),
    )
    if not row:
        raise HTTPException(401, "Please log in")
    return User(**row)


def require_role(*roles: Role):
    """Only lets through users with one of the given roles (403 otherwise)."""

    def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Your role is not allowed to do this")
        return user

    return check


def require_ingest_key(x_api_key: str = Header(default="")) -> None:
    """Machine-to-machine ingestion: external sources send an API key, not a user session."""
    if not hmac.compare_digest(x_api_key, config.INGEST_API_KEY):
        raise HTTPException(401, "Invalid API key")
