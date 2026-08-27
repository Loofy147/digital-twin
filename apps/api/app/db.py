from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_HERE = Path(__file__).resolve()
ROOT = Path(os.getenv("DIGITAL_TWIN_ROOT", str(_HERE.parents[3] if len(_HERE.parents) > 3 else _HERE.parents[1])))
DEFAULT_DB = ROOT / "data" / "digital_twin.sqlite3"
SCHEMA_PATH = ROOT / "supabase" / "migrations" / "00001_initial_schema.sql"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


class Database:
    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("DIGITAL_TWIN_DB", str(DEFAULT_DB))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript("""
            create table if not exists app_users (id text primary key, email text unique not null, display_name text not null default '', created_at text not null, deleted_at text);
            create table if not exists twin_profiles (id text primary key, user_id text not null references app_users(id) on delete cascade, name text not null, description text not null default '', status text not null default 'draft', created_at text not null, updated_at text not null, unique(user_id,name));
            create table if not exists dimensions (id text primary key, key text unique not null, label text not null, description text not null, weight real not null);
            create table if not exists assessment_questions (id text primary key, dimension_id text not null references dimensions(id), version integer not null, prompt text not null, response_type text not null, choices text not null, active integer not null default 1);
            create table if not exists assessment_answers (id text primary key, user_id text not null references app_users(id) on delete cascade, profile_id text not null references twin_profiles(id) on delete cascade, question_id text not null references assessment_questions(id), value text not null, source text not null, confidence real not null, answered_at text not null, unique(profile_id,question_id));
            create table if not exists profile_dimensions (id text primary key, profile_id text not null references twin_profiles(id) on delete cascade, dimension_id text not null references dimensions(id), score real not null, confidence real not null, evidence text not null, updated_at text not null, unique(profile_id,dimension_id));
            create table if not exists data_sources (id text primary key, user_id text not null references app_users(id) on delete cascade, provider text not null, status text not null, scopes text not null, created_at text not null, unique(user_id,provider));
            create table if not exists consents (id text primary key, user_id text not null references app_users(id) on delete cascade, profile_id text references twin_profiles(id) on delete cascade, purpose text not null, provider text, granted integer not null, policy_version text not null, granted_at text, revoked_at text, created_at text not null);
            create table if not exists observations (id text primary key, user_id text not null references app_users(id) on delete cascade, profile_id text not null references twin_profiles(id) on delete cascade, source_id text, kind text not null, occurred_at text not null, normalized text not null, retention_until text, created_at text not null);
            create table if not exists scenario_runs (id text primary key, user_id text not null references app_users(id) on delete cascade, profile_id text not null references twin_profiles(id) on delete cascade, prompt text not null, context text not null, result text, model_version text not null, status text not null, created_at text not null);
            create table if not exists training_jobs (id text primary key, user_id text not null references app_users(id) on delete cascade, profile_id text not null references twin_profiles(id) on delete cascade, status text not null, config text not null, progress real not null default 0, error_message text, idempotency_key text not null, created_at text not null, unique(user_id,idempotency_key));
            create table if not exists audit_events (id text primary key, user_id text, action text not null, resource_type text not null, resource_id text, metadata text not null, request_id text, created_at text not null);
            create index if not exists idx_profiles_user on twin_profiles(user_id);
            create index if not exists idx_answers_profile on assessment_answers(profile_id);
            create index if not exists idx_audit_user_time on audit_events(user_id,created_at desc);
            """)

    def seed_questions(self, bank: dict[str, Any]) -> None:
        with self.connection() as conn:
            dimension_ids: dict[str, str] = {}
            for d in bank["dimensions"]:
                existing = conn.execute("select id from dimensions where key=?", (d["key"],)).fetchone()
                did = existing["id"] if existing else new_id()
                conn.execute("insert or replace into dimensions(id,key,label,description,weight) values(?,?,?,?,?)", (did,d["key"],d["label"],d["description"],d["weight"]))
                dimension_ids[d["key"]] = did
            for q in bank["questions"]:
                conn.execute("insert or replace into assessment_questions(id,dimension_id,version,prompt,response_type,choices,active) values(?,?,?,?,?,?,1)", (q["id"],dimension_ids[q["dimension"]],1,q["prompt"],q["response_type"],json.dumps(q["choices"])))

    def audit(self, user_id: str | None, action: str, resource_type: str, resource_id: str | None = None, metadata: dict[str, Any] | None = None, request_id: str | None = None) -> None:
        with self.connection() as conn:
            conn.execute("insert into audit_events values(?,?,?,?,?,?,?,?)", (new_id(), user_id, action, resource_type, resource_id, json.dumps(metadata or {}), request_id, now_iso()))

    def user_by_email(self, email: str) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute("select * from app_users where email=? and deleted_at is null", (email.lower().strip(),)).fetchone()

    def create_user(self, email: str, display_name: str = "") -> sqlite3.Row:
        uid = new_id()
        with self.connection() as conn:
            conn.execute("insert into app_users values(?,?,?,?,?)", (uid,email.lower().strip(),display_name,now_iso(),None))
            return conn.execute("select * from app_users where id=?", (uid,)).fetchone()

    def profile(self, user_id: str, profile_id: str) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute("select * from twin_profiles where id=? and user_id=?", (profile_id,user_id)).fetchone()

    def rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return list(conn.execute(sql, params).fetchall())

    def one(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.connection() as conn:
            conn.execute(sql, params)

    def delete_user_data(self, user_id: str) -> None:
        with self.connection() as conn:
            conn.execute("delete from app_users where id=?", (user_id,))
