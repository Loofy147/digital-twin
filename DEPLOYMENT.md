# Deployment Runbook

## Local validation

Run the API and web client locally first. The local API uses SQLite and a development bearer token. It is suitable for development only.

```bash
python3 -m pip install -r apps/api/requirements.txt
PYTHONPATH=apps/api pytest -q apps/api/tests
pnpm --dir apps/web install
pnpm --dir apps/web build
docker compose up --build
```

## Production topology

Use the web client as a stateless frontend, the FastAPI API as an authenticated control plane, a separate worker for long-running training jobs, Supabase PostgreSQL for durable metadata, and encrypted object storage for model artifacts. Keep provider OAuth secrets and service-role credentials server-side. Do not expose them through `NEXT_PUBLIC_*` variables.

| Component | Required production configuration |
|---|---|
| Web | `NEXT_PUBLIC_API_URL` points to the HTTPS API origin; configure CSP, TLS, and allowed origins |
| API | Replace `/auth/dev-login` with Supabase/OIDC validation; set explicit CORS origins and rate limits |
| Database | Apply `supabase/migrations/00001_initial_schema.sql`; verify RLS policies with authenticated test users |
| Worker | Move training from FastAPI background tasks into a durable queue worker; cap CPU, memory, and job duration |
| Artifacts | Store model files in private object storage with short-lived signed URLs |
| Integrations | Configure one provider at a time, request least-privilege scopes, persist only normalized data by default |
| Observability | Redact payloads; enable error tracking and product analytics only after telemetry consent |
| Recovery | Schedule database backups, test restore, and document retention/deletion verification |

## Safety gates before real data

The production deployment must reject development login in non-development environments. It must enforce ownership at the API and database policy layers, require a current consent record before ingestion, support account export and deletion, redact logs, and provide a visible explanation that scenarios are heuristic simulations. Any sensitive-data connector should undergo a separate privacy and security review.

## Training rollout

The current job handler is a validation stub that demonstrates state transitions and idempotency. The production worker should load only consented observations, create a reproducible dataset manifest, train a bounded Stable-Baselines3 environment, checkpoint to private storage, record metrics, and publish a model version only after evaluation against a holdout set. A failed or low-quality run must not replace the active baseline.
