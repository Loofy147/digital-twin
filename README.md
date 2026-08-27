# Digital Twin

A privacy-first, interpretable digital-twin platform for personal decision support. The repository now contains a runnable FastAPI service, a Next.js dashboard, a versioned assessment bank, a relational schema for Supabase/PostgreSQL, consent and audit primitives, scenario simulation, and an asynchronous training-job foundation.

> This system is decision support, not a factual replica of a person. Predictions include confidence, evidence, and limitations. It must not be used as a clinical, financial, legal, employment, or safety-critical decision-maker.

## Current implementation

| Area | Status |
|---|---|
| FastAPI backend | Implemented locally with typed validation and ownership checks |
| Authentication | Implemented as a development token flow; replace with Supabase/OAuth before production |
| Assessment | Implemented with a versioned 20-question seed bank across 10 dimensions |
| Profile inference | Implemented as an interpretable weighted baseline with evidence and confidence |
| Scenario simulation | Implemented with explicit heuristic limitations |
| Training jobs | Implemented as idempotent queued background validation jobs; SB3/Ray worker remains a production extension |
| Integrations | Provider-neutral contracts and consent-gated normalized observation ingestion; provider OAuth adapters remain configuration-dependent |
| Privacy | Export, account deletion, consent records, audit events, and retention fields implemented |
| Web client | Implemented as a responsive Next.js dashboard |
| Production auth and secrets | Deployment prerequisite; never commit secrets |

## Run locally

The backend requires Python 3.11+ and the frontend requires Node.js 20+.

```bash
# Terminal 1: API
python3 -m pip install -r apps/api/requirements.txt
PYTHONPATH=apps/api uvicorn app.main:app --app-dir apps/api --reload --port 8000

# Terminal 2: web client
pnpm --dir apps/web install
NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm --dir apps/web dev
```

Open `http://localhost:3000`. The local development login creates a local account using only an email address. It is intentionally not a production authentication mechanism.

## Verification

```bash
PYTHONPATH=apps/api pytest -q apps/api/tests
pnpm --dir apps/web build
```

The backend test suite covers authentication, profile ownership boundaries, assessment inference, scenario evidence, idempotent training jobs, export, and deletion.

## Docker Compose

```bash
docker compose up --build
```

The API is exposed on port 8000 and the dashboard on port 3000. For production, use the supplied PostgreSQL-compatible migration under `supabase/migrations/00001_initial_schema.sql`, replace development tokens with a managed identity provider, configure an encrypted secret store, and run the worker separately from the web API.

## Production hardening checklist

Before accepting real personal data, configure Supabase row-level security policies for the deployed auth claims, provider-specific OAuth with least-privilege scopes, encrypted credential storage, backup and restore drills, retention enforcement, rate limits, structured logs with redaction, Sentry/PostHog with consent-aware telemetry, and a real queue worker for long-running training. Review the threat model and data-processing terms with qualified security and privacy professionals.

## Repository guide

`FULL_IMPLEMENTATION_PLAN.md` defines scope and acceptance criteria. `apps/api/app/main.py` contains the HTTP contracts. `apps/api/app/db.py` contains the local persistence layer. `apps/api/app/domain.py` contains inference and typed payloads. `apps/api/app/integrations.py` contains provider-neutral connector contracts. `data/question_bank.json` is the versioned seed bank. `supabase/migrations/00001_initial_schema.sql` is the PostgreSQL/Supabase migration.