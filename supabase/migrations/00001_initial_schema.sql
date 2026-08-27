-- Digital Twin initial schema
-- PostgreSQL / Supabase compatible. Every user-owned table is scoped by user_id.

create extension if not exists pgcrypto;

create table if not exists app_users (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  display_name text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table if not exists twin_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app_users(id) on delete cascade,
  name text not null,
  description text not null default '',
  status text not null default 'draft' check (status in ('draft','active','archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, name)
);

create table if not exists dimensions (
  id uuid primary key default gen_random_uuid(),
  key text not null unique,
  label text not null,
  description text not null default '',
  weight numeric(6,3) not null default 1.0 check (weight > 0),
  created_at timestamptz not null default now()
);

create table if not exists assessment_questions (
  id uuid primary key default gen_random_uuid(),
  dimension_id uuid not null references dimensions(id) on delete restrict,
  version integer not null default 1 check (version > 0),
  prompt text not null,
  response_type text not null default 'scale' check (response_type in ('scale','choice','text','boolean')),
  choices jsonb not null default '[]'::jsonb,
  is_sensitive boolean not null default false,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  unique(dimension_id, version, prompt)
);

create table if not exists assessment_answers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app_users(id) on delete cascade,
  profile_id uuid not null references twin_profiles(id) on delete cascade,
  question_id uuid not null references assessment_questions(id) on delete restrict,
  value jsonb not null,
  source text not null default 'self_report' check (source in ('self_report','integration','imported')),
  confidence numeric(5,4) not null default 1.0 check (confidence >= 0 and confidence <= 1),
  answered_at timestamptz not null default now(),
  unique(profile_id, question_id)
);

create table if not exists profile_dimensions (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references twin_profiles(id) on delete cascade,
  dimension_id uuid not null references dimensions(id) on delete restrict,
  score numeric(7,4) not null check (score >= 0 and score <= 1),
  confidence numeric(5,4) not null check (confidence >= 0 and confidence <= 1),
  evidence jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now(),
  unique(profile_id, dimension_id)
);

create table if not exists data_sources (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app_users(id) on delete cascade,
  provider text not null,
  status text not null default 'disconnected' check (status in ('connected','disconnected','error','revoked')),
  scopes jsonb not null default '[]'::jsonb,
  encrypted_credentials text,
  last_sync_at timestamptz,
  created_at timestamptz not null default now(),
  unique(user_id, provider)
);

create table if not exists consents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app_users(id) on delete cascade,
  profile_id uuid references twin_profiles(id) on delete cascade,
  purpose text not null,
  provider text,
  granted boolean not null default false,
  policy_version text not null,
  granted_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists observations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app_users(id) on delete cascade,
  profile_id uuid not null references twin_profiles(id) on delete cascade,
  source_id uuid references data_sources(id) on delete set null,
  kind text not null,
  occurred_at timestamptz not null,
  normalized jsonb not null,
  raw_payload jsonb,
  retention_until timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists scenario_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app_users(id) on delete cascade,
  profile_id uuid not null references twin_profiles(id) on delete cascade,
  prompt text not null,
  context jsonb not null default '{}'::jsonb,
  result jsonb,
  model_version text not null default 'baseline-heuristic-v1',
  status text not null default 'completed' check (status in ('queued','completed','failed')),
  created_at timestamptz not null default now()
);

create table if not exists training_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app_users(id) on delete cascade,
  profile_id uuid not null references twin_profiles(id) on delete cascade,
  status text not null default 'queued' check (status in ('queued','running','succeeded','failed','cancelled')),
  config jsonb not null default '{}'::jsonb,
  progress numeric(5,4) not null default 0 check (progress >= 0 and progress <= 1),
  error_message text,
  idempotency_key text not null,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  unique(user_id, idempotency_key)
);

create table if not exists model_versions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app_users(id) on delete cascade,
  profile_id uuid not null references twin_profiles(id) on delete cascade,
  version text not null,
  algorithm text not null,
  metrics jsonb not null default '{}'::jsonb,
  artifact_uri text,
  active boolean not null default false,
  created_at timestamptz not null default now(),
  unique(profile_id, version)
);

create table if not exists audit_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references app_users(id) on delete set null,
  action text not null,
  resource_type text not null,
  resource_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  request_id text,
  created_at timestamptz not null default now()
);

create index if not exists idx_profiles_user on twin_profiles(user_id);
create index if not exists idx_answers_profile on assessment_answers(profile_id);
create index if not exists idx_observations_profile_time on observations(profile_id, occurred_at desc);
create index if not exists idx_scenarios_profile_time on scenario_runs(profile_id, created_at desc);
create index if not exists idx_jobs_profile_time on training_jobs(profile_id, created_at desc);
create index if not exists idx_audit_user_time on audit_events(user_id, created_at desc);

-- RLS policies are enabled in Supabase deployments. The API also enforces ownership.
alter table twin_profiles enable row level security;
alter table assessment_answers enable row level security;
alter table data_sources enable row level security;
alter table consents enable row level security;
alter table observations enable row level security;
alter table scenario_runs enable row level security;
alter table training_jobs enable row level security;
alter table model_versions enable row level security;
alter table audit_events enable row level security;

-- Owner-scoped policies for Supabase deployments where app_users.id mirrors auth.uid().
create policy profiles_owner_select on twin_profiles for select using (auth.uid() = user_id);
create policy profiles_owner_write on twin_profiles for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy answers_owner_access on assessment_answers for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy sources_owner_access on data_sources for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy consents_owner_access on consents for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy observations_owner_access on observations for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy scenarios_owner_access on scenario_runs for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy jobs_owner_access on training_jobs for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy models_owner_access on model_versions for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy audit_owner_access on audit_events for select using (auth.uid() = user_id);
