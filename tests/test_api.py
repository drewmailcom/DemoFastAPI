from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from app import config


@pytest.fixture
def ingest(users):
    def send(incident, api_key=config.INGEST_API_KEY) -> httpx.Response:
        return users["anonymous"].post("/api/ingest", json=incident, headers={"X-API-Key": api_key})

    return send


@pytest.fixture
def new_detection(ingest):
    def create() -> int:
        return ingest({"customer_id": 3, "process": {"name": "mimikatz.exe"}}).json()["detection_id"]

    return create


def close_active(client: httpx.Client) -> None:
    active = client.get("/api/me").json()["active_detection"]
    if active:
        client.post(f"/api/detections/{active['id']}/close", json={"resolution": "test cleanup"})


# ---- authentication and authorization (enforced by the API) ---------------------------------


def test_wrong_password_is_rejected(users):
    response = users["anonymous"].post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401


def test_requires_a_session(users):
    assert users["anonymous"].get("/api/queue").status_code == 401


@pytest.mark.parametrize("user", ["admin", "analyst1", "support"])
def test_every_role_can_read(users, user):
    assert users[user].get("/api/detections").status_code == 200


@pytest.mark.parametrize(
    "user, method, path",
    [
        ("support", "POST", "/api/detections/1/claim"),
        ("support", "POST", "/api/customers"),
        ("support", "PUT", "/api/signatures/1"),
        ("analyst1", "POST", "/api/customers"),
        ("analyst1", "DELETE", "/api/signatures/1"),
        ("admin", "POST", "/api/detections/1/claim"),
        ("admin", "POST", "/api/detections/1/close"),
    ],
)
def test_role_is_forbidden(users, user, method, path):
    assert users[user].request(method, path, json={}).status_code == 403


def test_ingestion_requires_the_api_key(ingest):
    assert ingest({"customer_id": 1}, api_key="wrong-key").status_code == 401


# ---- ingestion ------------------------------------------------------------------------------


def test_unknown_customer_is_stored_as_unmatched(ingest):
    response = ingest({"customer_id": 999, "process": {"name": "mimikatz.exe"}})
    assert response.status_code == 202
    assert response.json()["reason"] == "UNKNOWN_CUSTOMER"


def test_incident_without_matching_signature_is_stored_as_unmatched(ingest, users):
    response = ingest({"customer_id": 1, "process": {"name": "notepad.exe"}})
    assert response.status_code == 202
    assert response.json()["reason"] == "NO_SIGNATURE"
    assert users["support"].get("/api/unmatched").json()[0]["payload"]["process"]["name"] == "notepad.exe"


def test_best_of_several_matching_signatures_and_combined_priority(ingest):
    # Matches "Encoded PowerShell command" (priority 3, id 3) and "PowerShell execution" (priority 2, id 5).
    response = ingest({"customer_id": 1, "process": {"name": "powershell.exe", "encoded_command": True}})
    assert response.status_code == 201
    body = response.json()
    assert body["signature_id"] == 3
    assert body["matched_signature_ids"] == [3, 5]
    assert body["priority"] == 5 * 3  # Alpha Bank importance 5 x signature priority 3


def test_queue_is_ordered_by_priority(users):
    priorities = [d["priority"] for d in users["support"].get("/api/queue").json()]
    assert priorities == sorted(priorities, reverse=True)


# ---- claiming and closing -------------------------------------------------------------------


def test_exactly_one_of_many_simultaneous_claims_wins(users, new_detection):
    detection_id = new_detection()
    analysts = [users["analyst1"], users["analyst2"]] * 5
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(lambda client: client.post(f"/api/detections/{detection_id}/claim"), analysts))

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200] + [409] * 9
    close_active(users["analyst1"])
    close_active(users["analyst2"])


def test_analyst_cannot_take_two_detections_even_concurrently(users, new_detection):
    first, second = new_detection(), new_detection()
    client = users["analyst1"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda d: client.post(f"/api/detections/{d}/claim"), [first, second]))

    assert sorted(r.status_code for r in responses) == [200, 409]
    close_active(client)


def test_full_lifecycle(users, new_detection):
    detection_id = new_detection()
    analyst1, analyst2 = users["analyst1"], users["analyst2"]

    assert analyst1.post(f"/api/detections/{detection_id}/claim").status_code == 200
    assert analyst1.get("/api/me").json()["active_detection"]["id"] == detection_id

    # Another analyst cannot close it, and a resolution is mandatory.
    assert analyst2.post(f"/api/detections/{detection_id}/close", json={"resolution": "x"}).status_code == 409
    assert analyst1.post(f"/api/detections/{detection_id}/close", json={"resolution": "  "}).status_code == 422

    closed = analyst1.post(f"/api/detections/{detection_id}/close", json={"resolution": "False positive"})
    assert closed.status_code == 200
    assert analyst1.get("/api/me").json()["active_detection"] is None

    assert detection_id not in [d["id"] for d in analyst1.get("/api/queue").json()]
    closed_list = users["support"].get("/api/detections", params={"status": "CLOSED"}).json()
    assert next(d for d in closed_list if d["id"] == detection_id)["resolution"] == "False positive"


# ---- customers and signatures -----------------------------------------------------------------


def test_admin_can_change_customer_importance(users):
    response = users["admin"].put("/api/customers/5", json={"name": "Epsilon Blog", "importance": 2})
    assert response.status_code == 200
    assert response.json()["importance"] == 2


def test_invalid_input_is_rejected(users):
    admin = users["admin"]
    assert admin.post("/api/customers", json={"name": "X", "importance": 9}).status_code == 422
    assert admin.post("/api/signatures", json={"name": "X", "priority": 3, "conditions": []}).status_code == 422


def test_new_signature_is_used_for_matching_right_away(users, ingest):
    created = users["admin"].post(
        "/api/signatures",
        json={"name": "Netcat listener", "priority": 4, "conditions": [{"field": "process.name", "value": "nc.exe"}]},
    )
    assert created.status_code == 201
    body = ingest({"customer_id": 2, "process": {"name": "nc.exe"}}).json()
    assert body["signature_id"] == created.json()["id"]
    assert body["priority"] == 4 * 4


def test_cannot_delete_a_signature_that_has_detections(users):
    assert users["admin"].delete("/api/signatures/1").status_code == 409


# ---- reprocessing unmatched incidents ---------------------------------------------------------


def unmatched_payloads(users) -> list[dict]:
    return [incident["payload"] for incident in users["support"].get("/api/unmatched").json()]


def test_signature_created_later_turns_earlier_incidents_into_detections(users, ingest):
    incident = {"customer_id": 1, "process": {"name": "rclone.exe"}, "test": "late-signature"}
    assert ingest(incident).json()["reason"] == "NO_SIGNATURE"
    unmatched_before = users["support"].get("/api/unmatched").json()
    received_at = next(i["received_at"] for i in unmatched_before if i["payload"] == incident)

    created = users["admin"].post(
        "/api/signatures",
        json={"name": "Rclone exfiltration", "priority": 5, "conditions": [{"field": "process.name", "value": "rclone.exe"}]},
    )
    assert created.status_code == 201
    assert created.json()["reprocessed"] >= 1

    assert incident not in unmatched_payloads(users)
    detection = next(d for d in users["support"].get("/api/detections").json() if d["payload"] == incident)
    assert detection["signature_id"] == created.json()["id"]
    assert detection["status"] == "OPEN"
    assert detection["priority"] == 5 * 5  # Alpha Bank importance 5 x signature priority 5
    assert detection["created_at"] == received_at  # keeps its place in the queue

    # Running it again creates nothing new: the incident is no longer unmatched.
    edited = users["admin"].put(f"/api/signatures/{created.json()['id']}", json=created.json() | {"name": "Rclone"})
    assert edited.json()["reprocessed"] == 0


def test_edited_signature_also_reprocesses(users, ingest):
    incident = {"customer_id": 2, "process": {"name": "procdump.exe"}, "test": "edited-signature"}
    assert ingest(incident).json()["reason"] == "NO_SIGNATURE"
    signature = users["admin"].post(
        "/api/signatures",
        json={"name": "Procdump", "priority": 3, "conditions": [{"field": "process.name", "value": "procdump64.exe"}]},
    ).json()
    assert incident in unmatched_payloads(users)

    fixed = signature | {"conditions": [{"field": "process.name", "value": "procdump.exe"}]}
    assert users["admin"].put(f"/api/signatures/{signature['id']}", json=fixed).json()["reprocessed"] >= 1
    assert incident not in unmatched_payloads(users)


def test_customer_added_later_turns_earlier_incidents_into_detections(users, ingest):
    customers = users["admin"].get("/api/customers").json()
    next_id = max(c["id"] for c in customers) + 1  # serial ids: the next customer gets this one
    matching = {"customer_id": next_id, "process": {"name": "mimikatz.exe"}, "test": "late-customer"}
    no_signature = {"customer_id": next_id, "process": {"name": "calc.exe"}, "test": "late-customer"}
    assert ingest(matching).json()["reason"] == "UNKNOWN_CUSTOMER"
    assert ingest(no_signature).json()["reason"] == "UNKNOWN_CUSTOMER"

    created = users["admin"].post("/api/customers", json={"name": "Late Customer", "importance": 2})
    assert created.json()["id"] == next_id
    assert created.json()["reprocessed"] >= 1

    unmatched = users["support"].get("/api/unmatched").json()
    assert matching not in [i["payload"] for i in unmatched]
    # The other incident still has no signature, and now says so.
    assert next(i for i in unmatched if i["payload"] == no_signature)["reason"] == "NO_SIGNATURE"
