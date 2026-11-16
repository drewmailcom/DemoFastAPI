"""HTTP layer: every route, and the role each one requires. Business logic lives in the other modules."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Cookie, Depends, FastAPI, Path as PathParam, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg import errors
from pydantic import BaseModel

from app import auth, db
from app.auth import Role, User, current_user, require_ingest_key, require_role
from app.customers import CustomerIn, create_customer, delete_customer, list_customers, update_customer
from app.detections import claim_detection, close_detection, get_active_detection, get_queue, list_detections
from app.ingest import ingest_incident, list_unmatched
from app.seed import seed_if_empty
from app.signatures import SignatureIn, create_signature, delete_signature, list_signatures, update_signature
from app.validation import Text

AnyUser = Annotated[User, Depends(current_user)]
Analyst = Annotated[User, Depends(require_role(Role.ANALYST))]
ADMIN_ONLY = [Depends(require_role(Role.ADMIN))]
Id = Annotated[int, PathParam(ge=1, le=2_147_483_647)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.pool.open(wait=True, timeout=10)  # fail fast if Postgres is not reachable
    db.init_schema()
    seed_if_empty()
    yield
    db.pool.close()


app = FastAPI(title="Detection Console", lifespan=lifespan)


# ---- Public endpoints -------------------------------------------------------------------------


@app.post("/api/ingest", dependencies=[Depends(require_ingest_key)])
def ingest(incident: dict[str, Any], response: Response):
    """External sources push incidents here with an API key (machine-to-machine, no user session)."""
    result = ingest_incident(incident)
    response.status_code = 201 if result["outcome"] == "detection" else 202
    return result


class LoginIn(BaseModel):
    username: Text
    password: Text


@app.post("/api/auth/login")
def login(body: LoginIn, response: Response) -> User:
    return auth.login(response, body.username, body.password)


# ---- Everything below requires a logged-in user -----------------------------------------------
# Reads are open to every role; each write states which role may do it.

api = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


@api.post("/auth/logout", status_code=204)
def logout(response: Response, sid: str | None = Cookie(default=None)):
    auth.logout(response, sid)


@api.get("/me")
def me(user: AnyUser):
    return {"user": user, "active_detection": get_active_detection(user.id)}


@api.get("/queue")
def queue():
    return get_queue()


@api.get("/detections")
def detections(
    status: Literal["OPEN", "IN_PROGRESS", "CLOSED"] | None = None,
    customer_id: int | None = None,
    signature_id: int | None = None,
    min_priority: int | None = None,
):
    return list_detections(status, customer_id, signature_id, min_priority)


@api.get("/unmatched")
def unmatched():
    return list_unmatched()


@api.post("/detections/{detection_id}/claim")
def claim(detection_id: Id, user: Analyst):
    return claim_detection(detection_id, user.id)


class CloseIn(BaseModel):
    resolution: Text


@api.post("/detections/{detection_id}/close")
def close(detection_id: Id, body: CloseIn, user: Analyst):
    return close_detection(detection_id, user.id, body.resolution)


@api.get("/customers")
def customers():
    return list_customers()


@api.post("/customers", status_code=201, dependencies=ADMIN_ONLY)
def add_customer(customer: CustomerIn):
    return create_customer(customer)


@api.put("/customers/{customer_id}", dependencies=ADMIN_ONLY)
def edit_customer(customer_id: Id, customer: CustomerIn):
    return update_customer(customer_id, customer)


@api.delete("/customers/{customer_id}", status_code=204, dependencies=ADMIN_ONLY)
def remove_customer(customer_id: Id):
    delete_customer(customer_id)


@api.get("/signatures")
def signatures():
    return list_signatures()


@api.post("/signatures", status_code=201, dependencies=ADMIN_ONLY)
def add_signature(signature: SignatureIn):
    return create_signature(signature)


@api.put("/signatures/{signature_id}", dependencies=ADMIN_ONLY)
def edit_signature(signature_id: Id, signature: SignatureIn):
    return update_signature(signature_id, signature)


@api.delete("/signatures/{signature_id}", status_code=204, dependencies=ADMIN_ONLY)
def remove_signature(signature_id: Id):
    delete_signature(signature_id)


app.include_router(api)


# ---- Database errors that are the client's fault, as readable 409s ---------------------------


@app.exception_handler(errors.ForeignKeyViolation)
async def still_referenced(_request, _error):
    return JSONResponse({"detail": "This record is still used by existing detections"}, status_code=409)


@app.exception_handler(errors.UniqueViolation)
async def duplicate(_request, _error):
    return JSONResponse({"detail": "A record with this name already exists"}, status_code=409)


# The UI: static files served from the same origin, so the session cookie just works.
app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "public", html=True), name="ui")
