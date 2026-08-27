import os
from pathlib import Path

TEST_DB = "/tmp/digital-twin-api-test.sqlite3"
Path(TEST_DB).unlink(missing_ok=True)
os.environ["DIGITAL_TWIN_DB"] = TEST_DB

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def login(email: str):
    response = client.post("/auth/dev-login", json={"email": email, "display_name": "Test User"})
    assert response.status_code == 200
    body = response.json()
    return body["token"], body["user"]["id"]


def auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_auth_profile_assessment_and_scenario_flow():
    token, _ = login("alice@example.com")
    assert client.get("/me", headers=auth(token)).status_code == 200
    profile = client.post("/profiles", headers=auth(token), json={"name": "Alice Twin", "description": "Local test"}).json()["profile"]
    questions = client.get("/assessment/questions", headers=auth(token)).json()["questions"]
    answers = [{"question_id": q["id"], "value": 5 if i % 2 else 3} for i, q in enumerate(questions)]
    result = client.post(f"/profiles/{profile['id']}/assessment", headers=auth(token), json={"answers": answers})
    assert result.status_code == 200
    assert len(result.json()["dimensions"]) >= 10
    scenario = client.post(f"/profiles/{profile['id']}/scenarios", headers=auth(token), json={"prompt": "Should I start a new project?"})
    assert scenario.status_code == 200
    assert scenario.json()["result"]["evidence"]


def test_cross_user_profile_access_is_denied():
    token_a, _ = login("bob@example.com")
    token_b, _ = login("carol@example.com")
    profile = client.post("/profiles", headers=auth(token_a), json={"name": "Bob Twin"}).json()["profile"]
    assert client.get(f"/profiles/{profile['id']}", headers=auth(token_b)).status_code == 404
    assert client.post(f"/profiles/{profile['id']}/scenarios", headers=auth(token_b), json={"prompt": "test"}).status_code == 404


def test_training_is_idempotent_and_privacy_export_delete():
    token, _ = login("dana@example.com")
    profile = client.post("/profiles", headers=auth(token), json={"name": "Dana Twin"}).json()["profile"]
    first = client.post(f"/profiles/{profile['id']}/training", headers=auth(token), json={"idempotency_key": "same-job"})
    second = client.post(f"/profiles/{profile['id']}/training", headers=auth(token), json={"idempotency_key": "same-job"})
    assert first.status_code == second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert client.get("/privacy/export", headers=auth(token)).status_code == 200
    assert client.delete("/privacy/account", headers=auth(token)).status_code == 204
    assert client.get("/me", headers=auth(token)).status_code == 401


def test_observation_ingestion_requires_explicit_consent():
    token, _ = login("erin@example.com")
    profile = client.post("/profiles", headers=auth(token), json={"name": "Erin Twin"}).json()["profile"]
    payload = {"event": "focused_work", "duration_minutes": 45}
    blocked = client.post(f"/profiles/{profile['id']}/observations/calendar", headers=auth(token), json=payload)
    assert blocked.status_code == 403
    consent = client.post(f"/profiles/{profile['id']}/consents", headers=auth(token), json={"purpose": "observation_ingestion", "provider": "calendar", "granted": True, "policy_version": "2026-08-27.v1"})
    assert consent.status_code == 200
    allowed = client.post(f"/profiles/{profile['id']}/observations/calendar", headers=auth(token), json=payload)
    assert allowed.status_code == 200
    assert len(allowed.json()["observation_ids"]) == 1


def test_integration_connect_and_revoke():
    token, _ = login("frank@example.com")
    connected = client.post("/integrations/calendar/connect", headers=auth(token), json={"purpose": "observation_ingestion", "provider": "calendar", "granted": True, "policy_version": "2026-08-27.v1"})
    assert connected.status_code == 200
    providers = client.get("/integrations", headers=auth(token)).json()["providers"]
    assert next(item for item in providers if item["provider"] == "calendar")["status"] == "connected"
    assert client.delete("/integrations/calendar", headers=auth(token)).status_code == 204


def test_profile_workflow_insights_activity_and_training_cancel():
    token, _ = login("workflow@example.com")
    profile = client.post("/profiles", headers=auth(token), json={"name": "Workflow Twin", "description": "test"}).json()["profile"]
    profile_id = profile["id"]
    questions = client.get("/assessment/questions", headers=auth(token)).json()["questions"]
    answers = [{"question_id": q["id"], "value": 4} for q in questions]
    assert client.post(f"/profiles/{profile_id}/assessment", headers=auth(token), json={"answers": answers}).status_code == 200
    insights = client.get(f"/profiles/{profile_id}/insights", headers=auth(token))
    assert insights.status_code == 200
    assert insights.json()["dimensions"]
    scenario = client.post(f"/profiles/{profile_id}/scenarios", headers=auth(token), json={"prompt": "Should I test a new plan?"})
    assert scenario.status_code == 200
    activity = client.get(f"/profiles/{profile_id}/activity", headers=auth(token))
    assert activity.status_code == 200
    assert any(event["type"] == "scenario" for event in activity.json()["events"])
    job = client.post(f"/profiles/{profile_id}/training", headers=auth(token), json={"idempotency_key": "cancel-me", "config": {}}).json()["job"]
    cancelled = client.post(f"/profiles/{profile_id}/training/{job['id']}/cancel", headers=auth(token))
    assert cancelled.status_code == 200
    assert cancelled.json()["cancelled"] is False or cancelled.json()["job"]["status"] in {"cancelled", "succeeded"}
    reset = client.post(f"/profiles/{profile_id}/assessment/reset", headers=auth(token))
    assert reset.status_code == 200
    assert client.get(f"/profiles/{profile_id}/insights", headers=auth(token)).json()["dimensions"] == []
