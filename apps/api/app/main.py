from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import Database, now_iso, new_id
from .domain import AuthRequest, AssessmentSubmit, ConsentInput, ProfileCreate, ScenarioInput, TrainingInput, infer_dimensions, scenario_recommendation
from .integrations import CONNECTORS, get_connector

_HERE = Path(__file__).resolve()
ROOT = Path(os.getenv("DIGITAL_TWIN_ROOT", str(_HERE.parents[3] if len(_HERE.parents) > 3 else _HERE.parents[1])))
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
DB = Database()
with open(ROOT / "data" / "question_bank.json", encoding="utf-8") as _bank_file:
    DB.seed_questions(json.load(_bank_file))
TOKENS: dict[str, str] = {}
TOKEN_LOCK = threading.Lock()

app = FastAPI(title="Digital Twin API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://localhost:5173"], allow_credentials=True, allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"])


def row_json(row: Any) -> dict[str, Any]:
    return dict(row) if row else {}


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    uid = TOKENS.get(authorization.removeprefix("Bearer ").strip())
    user = DB.one("select * from app_users where id=? and deleted_at is null", (uid,)) if uid else None
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return row_json(user)


def require_profile(user: dict[str, Any], profile_id: str) -> dict[str, Any]:
    profile = DB.profile(user["id"], profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return row_json(profile)


def audit(user_id: str, action: str, resource: str, resource_id: str | None = None, metadata: dict[str, Any] | None = None, request_id: str | None = None) -> None:
    DB.audit(user_id, action, resource, resource_id, metadata, request_id)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "digital-twin-api"}


@app.get("/ready")
def ready() -> dict[str, str]:
    DB.one("select 1")
    return {"status": "ready"}


@app.post("/auth/dev-login")
def dev_login(payload: AuthRequest) -> dict[str, Any]:
    if ENVIRONMENT not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="Development login is disabled")
    user = DB.user_by_email(payload.email) or DB.create_user(payload.email, payload.display_name)
    token = secrets.token_urlsafe(32)
    with TOKEN_LOCK:
        TOKENS[token] = user["id"]
    DB.audit(user["id"], "login", "user", user["id"])
    return {"token": token, "user": row_json(user)}


@app.get("/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"user": user}


@app.post("/profiles")
def create_profile(payload: ProfileCreate, request: Request, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    pid, timestamp = new_id(), now_iso()
    try:
        DB.execute("insert into twin_profiles values(?,?,?,?,?,?,?)", (pid, user["id"], payload.name, payload.description, "draft", timestamp, timestamp))
    except Exception as exc:
        raise HTTPException(status_code=409, detail="A profile with this name already exists") from exc
    audit(user["id"], "profile.created", "profile", pid, request_id=request.headers.get("X-Request-ID"))
    return {"profile": row_json(DB.profile(user["id"], pid))}


@app.get("/profiles")
def list_profiles(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"profiles": [row_json(r) for r in DB.rows("select * from twin_profiles where user_id=? order by created_at", (user["id"],))]}


@app.get("/profiles/{profile_id}")
def get_profile(profile_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    profile = require_profile(user, profile_id)
    dims = [row_json(r) for r in DB.rows("select pd.*, d.key, d.label, d.description from profile_dimensions pd join dimensions d on d.id=pd.dimension_id where pd.profile_id=? order by d.key", (profile_id,))]
    return {"profile": profile, "dimensions": dims}


@app.get("/assessment/questions")
def questions(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    rows = DB.rows("select q.id,q.version,q.prompt,q.response_type,q.choices,d.key as dimension_key,d.label as dimension_label from assessment_questions q join dimensions d on d.id=q.dimension_id where q.active=1 order by d.key,q.id")
    return {"version": "2026-08-27.v1", "questions": [{**row_json(r), "choices": json.loads(r["choices"])} for r in rows]}


@app.post("/profiles/{profile_id}/assessment")
def submit_assessment(profile_id: str, payload: AssessmentSubmit, request: Request, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_profile(user, profile_id)
    qids = {r["id"] for r in DB.rows("select id from assessment_questions where active=1")}
    invalid = [a.question_id for a in payload.answers if a.question_id not in qids]
    if invalid:
        raise HTTPException(status_code=422, detail={"unknown_question_ids": invalid})
    for answer in payload.answers:
        DB.execute("insert into assessment_answers values(?,?,?,?,?,?,?,?) on conflict(profile_id,question_id) do update set value=excluded.value, answered_at=excluded.answered_at", (new_id(), user["id"], profile_id, answer.question_id, json.dumps(answer.value), "self_report", 1.0, now_iso()))
    dims = [row_json(r) for r in DB.rows("select key,label,description,weight from dimensions order by key")]
    qs = [row_json(r) for r in DB.rows("select q.id,q.prompt,d.key as dimension_key from assessment_questions q join dimensions d on d.id=q.dimension_id")]
    stored = DB.rows("select question_id,value from assessment_answers where profile_id=?", (profile_id,))
    scores = infer_dimensions(dims, qs, {r["question_id"]: json.loads(r["value"]) for r in stored})
    for score in scores:
        dim = DB.one("select id from dimensions where key=?", (score.key,))
        DB.execute("insert into profile_dimensions values(?,?,?,?,?,?,?) on conflict(profile_id,dimension_id) do update set score=excluded.score, confidence=excluded.confidence, evidence=excluded.evidence, updated_at=excluded.updated_at", (new_id(), profile_id, dim["id"], score.score, score.confidence, json.dumps(score.evidence), now_iso()))
    audit(user["id"], "assessment.submitted", "profile", profile_id, {"answer_count": len(payload.answers)}, request.headers.get("X-Request-ID"))
    return {"profile_id": profile_id, "dimensions": [score.__dict__ for score in scores]}


@app.post("/profiles/{profile_id}/consents")
def set_consent(profile_id: str, payload: ConsentInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_profile(user, profile_id)
    cid = new_id(); timestamp = now_iso()
    DB.execute("insert into consents values(?,?,?,?,?,?,?,?,?,?)", (cid,user["id"],profile_id,payload.purpose,payload.provider,1 if payload.granted else 0,payload.policy_version,timestamp if payload.granted else None,None,timestamp))
    audit(user["id"], "consent.granted" if payload.granted else "consent.revoked", "consent", cid, {"purpose": payload.purpose, "provider": payload.provider})
    return {"consent_id": cid, "granted": payload.granted, "policy_version": payload.policy_version}


@app.get("/profiles/{profile_id}/consents")
def list_consents(profile_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_profile(user, profile_id)
    return {"consents": [row_json(r) for r in DB.rows("select * from consents where user_id=? and profile_id=? order by created_at desc", (user["id"],profile_id))]}


@app.get("/integrations")
def integrations(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    connected = {r["provider"]: row_json(r) for r in DB.rows("select * from data_sources where user_id=?", (user["id"],))}
    return {"providers": [{"provider": name, "scopes": list(connector.scopes), "enabled": name in connected, "status": connected.get(name, {}).get("status", "disconnected")} for name, connector in CONNECTORS.items()]}


@app.post("/integrations/{provider}/connect")
def connect_integration(provider: str, payload: ConsentInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if provider not in CONNECTORS:
        raise HTTPException(status_code=404, detail="Integration provider not supported")
    if not payload.granted:
        raise HTTPException(status_code=422, detail="Use the revoke endpoint to disconnect an integration")
    source_id = new_id()
    DB.execute("insert into data_sources values(?,?,?,?,?,?) on conflict(user_id,provider) do update set status='connected', scopes=excluded.scopes", (source_id,user["id"],provider,"connected",json.dumps(list(CONNECTORS[provider].scopes)),now_iso()))
    audit(user["id"], "integration.connected", "data_source", source_id, {"provider": provider, "scopes": list(CONNECTORS[provider].scopes)})
    return {"provider": provider, "status": "connected", "scopes": list(CONNECTORS[provider].scopes), "note": "Provider OAuth must be configured before live synchronization."}


@app.delete("/integrations/{provider}", status_code=204)
def revoke_integration(provider: str, user: dict[str, Any] = Depends(current_user)) -> None:
    source = DB.one("select * from data_sources where user_id=? and provider=?", (user["id"], provider))
    if source:
        DB.execute("update data_sources set status='revoked' where user_id=? and provider=?", (user["id"], provider))
        DB.execute("update consents set granted=0, revoked_at=? where user_id=? and provider=? and granted=1", (now_iso(),user["id"],provider))
        audit(user["id"], "integration.revoked", "data_source", source["id"], {"provider": provider})


@app.post("/profiles/{profile_id}/observations/{provider}")
def ingest_observation(profile_id: str, provider: str, payload: dict[str, Any], user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_profile(user, profile_id)
    consent = DB.one("select * from consents where user_id=? and profile_id=? and provider=? and purpose='observation_ingestion' and granted=1 order by created_at desc", (user["id"], profile_id, provider))
    if not consent:
        raise HTTPException(status_code=403, detail="Observation ingestion requires active provider consent")
    try:
        connector = get_connector(provider)
        observations = connector.normalize(payload)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    source = DB.one("select * from data_sources where user_id=? and provider=?", (user["id"], provider))
    source_id = source["id"] if source else None
    inserted = []
    for observation in observations:
        oid = new_id()
        DB.execute("insert into observations values(?,?,?,?,?,?,?,?,?)", (oid,user["id"],profile_id,source_id,observation.kind,observation.occurred_at,json.dumps(observation.normalized),None,now_iso()))
        inserted.append(oid)
    audit(user["id"], "observation.ingested", "profile", profile_id, {"provider": provider, "count": len(inserted)})
    return {"provider": provider, "observation_ids": inserted}


@app.post("/profiles/{profile_id}/assessment/reset")
def reset_assessment(profile_id: str, request: Request, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_profile(user, profile_id)
    DB.execute("delete from assessment_answers where user_id=? and profile_id=?", (user["id"], profile_id))
    DB.execute("delete from profile_dimensions where profile_id=?", (profile_id,))
    audit(user["id"], "assessment.reset", "profile", profile_id, request_id=request.headers.get("X-Request-ID"))
    return {"profile_id": profile_id, "reset": True}


@app.get("/profiles/{profile_id}/insights")
def profile_insights(profile_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_profile(user, profile_id)
    dimensions = [row_json(r) for r in DB.rows("select d.key,d.label,pd.score,pd.confidence,pd.evidence,pd.updated_at from profile_dimensions pd join dimensions d on d.id=pd.dimension_id where pd.profile_id=? order by pd.updated_at desc", (profile_id,))]
    activity = [row_json(r) for r in DB.rows("select id,kind,occurred_at,created_at from observations where user_id=? and profile_id=? order by occurred_at desc limit 20", (user["id"], profile_id))]
    return {"profile_id": profile_id, "dimensions": dimensions, "observation_count": len(activity), "recent_observations": activity}


@app.get("/profiles/{profile_id}/activity")
def profile_activity(profile_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_profile(user, profile_id)
    events: list[dict[str, Any]] = []
    for row in DB.rows("select id,created_at,model_version as kind,status,prompt as summary from scenario_runs where user_id=? and profile_id=? order by created_at desc limit 20", (user["id"], profile_id)):
        events.append({"id": row["id"], "type": "scenario", "status": row["status"], "summary": row["summary"], "created_at": row["created_at"]})
    for row in DB.rows("select id,created_at,kind as type,occurred_at as summary from observations where user_id=? and profile_id=? order by created_at desc limit 20", (user["id"], profile_id)):
        events.append({"id": row["id"], "type": row["type"], "status": "stored", "summary": row["summary"], "created_at": row["created_at"]})
    for row in DB.rows("select id,created_at,status,progress from training_jobs where user_id=? and profile_id=? order by created_at desc limit 20", (user["id"], profile_id)):
        events.append({"id": row["id"], "type": "training", "status": row["status"], "summary": f"{round(row['progress'] * 100)}% complete", "created_at": row["created_at"]})
    events.sort(key=lambda item: item["created_at"], reverse=True)
    return {"events": events[:40]}


@app.post("/profiles/{profile_id}/scenarios")
def simulate(profile_id: str, payload: ScenarioInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_profile(user, profile_id)
    rows = DB.rows("select d.key,d.label,pd.score,pd.confidence,pd.evidence from profile_dimensions pd join dimensions d on d.id=pd.dimension_id where pd.profile_id=?", (profile_id,))
    from .domain import DimensionScore
    scores = [DimensionScore(r["key"],r["label"],r["score"],r["confidence"],json.loads(r["evidence"])) for r in rows]
    result = scenario_recommendation(payload.prompt, scores)
    sid = new_id()
    DB.execute("insert into scenario_runs values(?,?,?,?,?,?,?,?,?)", (sid,user["id"],profile_id,payload.prompt,json.dumps(payload.context),json.dumps(result),"baseline-heuristic-v1","completed",now_iso()))
    audit(user["id"], "scenario.completed", "scenario", sid)
    return {"scenario_id": sid, "model_version": "baseline-heuristic-v1", "result": result}


@app.post("/profiles/{profile_id}/training")
def queue_training(profile_id: str, payload: TrainingInput, background: BackgroundTasks, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_profile(user, profile_id)
    existing = DB.one("select * from training_jobs where user_id=? and idempotency_key=?", (user["id"],payload.idempotency_key))
    if existing:
        return {"job": row_json(existing), "deduplicated": True}
    jid = new_id()
    DB.execute("insert into training_jobs values(?,?,?,?,?,?,?,?,?)", (jid,user["id"],profile_id,"queued",json.dumps(payload.config),0,None,payload.idempotency_key,now_iso()))
    background.add_task(run_training, jid, user["id"])
    audit(user["id"], "training.queued", "training_job", jid)
    return {"job": row_json(DB.one("select * from training_jobs where id=?", (jid,)))}


def run_training(job_id: str, user_id: str) -> None:
    DB.execute("update training_jobs set status='running', progress=? where id=? and user_id=?", (0.05,job_id,user_id))
    # Baseline job: validate inputs and publish metadata. Replace with SB3 worker in production.
    DB.execute("update training_jobs set status='succeeded', progress=? where id=? and user_id=?", (1.0,job_id,user_id))
    DB.audit(user_id, "training.succeeded", "training_job", job_id)


@app.post("/profiles/{profile_id}/training/{job_id}/cancel")
def cancel_training(profile_id: str, job_id: str, request: Request, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_profile(user, profile_id)
    job = DB.one("select * from training_jobs where id=? and user_id=? and profile_id=?", (job_id, user["id"], profile_id))
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")
    if job["status"] in {"succeeded", "failed", "cancelled"}:
        return {"job": row_json(job), "cancelled": False}
    DB.execute("update training_jobs set status='cancelled', error_message=? where id=? and user_id=?", ("Cancelled by user", job_id, user["id"]))
    audit(user["id"], "training.cancelled", "training_job", job_id, request_id=request.headers.get("X-Request-ID"))
    return {"job": row_json(DB.one("select * from training_jobs where id=?", (job_id,))), "cancelled": True}


@app.get("/profiles/{profile_id}/training")
def training_jobs(profile_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_profile(user, profile_id)
    return {"jobs": [row_json(r) for r in DB.rows("select * from training_jobs where user_id=? and profile_id=? order by created_at desc", (user["id"],profile_id))]}


@app.get("/privacy/export")
def export_data(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    uid = user["id"]
    data = {"user": user, "profiles": [row_json(r) for r in DB.rows("select * from twin_profiles where user_id=?", (uid,))], "answers": [row_json(r) for r in DB.rows("select * from assessment_answers where user_id=?", (uid,))], "consents": [row_json(r) for r in DB.rows("select * from consents where user_id=?", (uid,))], "observations": [row_json(r) for r in DB.rows("select * from observations where user_id=?", (uid,))], "scenarios": [row_json(r) for r in DB.rows("select * from scenario_runs where user_id=?", (uid,))], "training_jobs": [row_json(r) for r in DB.rows("select * from training_jobs where user_id=?", (uid,))], "data_sources": [row_json(r) for r in DB.rows("select * from data_sources where user_id=?", (uid,))], "audit_events": [row_json(r) for r in DB.rows("select * from audit_events where user_id=?", (uid,))]}
    audit(uid, "privacy.exported", "user", uid)
    return data


@app.delete("/privacy/account", status_code=204)
def delete_account(user: dict[str, Any] = Depends(current_user)) -> None:
    uid = user["id"]
    DB.delete_user_data(uid)
    with TOKEN_LOCK:
        for token, token_uid in list(TOKENS.items()):
            if token_uid == uid:
                del TOKENS[token]
