# CLAUDE.md

Guidance for Claude Code (and future contributors) working in this repo.

## Project

Ondas do Mar — a web application for renting and managing vacation
apartments. The Owner entity is implemented end-to-end (model, repository,
service, CRUD API) as the first domain slice and the template for future
ones. Do not assume any other domain entities (bookings, apartments, etc.)
exist until they're actually added.

## Stack

- Frontend: Vue 3 + Nuxt (SSR/SSG) + TypeScript. Nuxt's built-in file-based
  router is used instead of a standalone router library. `@nuxtjs/i18n` for
  ES/EN. Chosen over plain Vite+Vue for SEO (direct-booking discoverability)
  and because SSR was already a hard requirement — see `docs/architecture.md`.
- Backend: FastAPI, SQLAlchemy 2 (async), Alembic, `pydantic-settings`.
- DB: PostgreSQL 16 via the `pgvector/pgvector:pg16` image (extension
  pre-enabled for the future RAG integration — see `docker/postgres/init.sql`).
- Python dependency management: `uv` (not pip/poetry). `backend/pyproject.toml`
  has `[tool.uv] package = false` — this is an application, not a distributable
  package, so there's no build backend.
- Containers: Docker Compose orchestrates `db`, `backend`, `frontend` for
  local development, with bind mounts for hot reload.

Full rationale for these choices: `docs/architecture.md`.

## Directory layout

```
backend/app/
  core/         settings (Settings/get_settings in config.py)
  db/           base.py (DeclarativeBase), session.py (async engine + get_db dep)
  api/          route modules + deps.py (shared FastAPI dependency providers,
                one get_<entity>_service per entity — see owners.py/deps.py)
  models/       SQLAlchemy models (import new modules in alembic/env.py
                so autogenerate picks them up)
  schemas/      Pydantic request/response schemas (Create/Update/Read per entity)
  repositories/ DB access only, one class per entity, no business rules
  services/     business rules only, one class per entity, raises
                domain-specific exceptions instead of leaking SQLAlchemy errors
backend/alembic/    migration environment; env.py reads DATABASE_URL from Settings
backend/tests/      pytest tests
frontend/           Nuxt app (pages/, components/, composables/, locales/)
docker/             cross-cutting Docker assets not owned by one service
docs/               architecture/decision notes
```

## Conventions

- **Python**: type hints everywhere, `ruff` for linting (config in
  `backend/pyproject.toml`), async SQLAlchemy sessions via `app.db.session.get_db`
  as a FastAPI dependency — don't create ad-hoc sync sessions.
- **Settings**: all configuration goes through `app.core.config.Settings`
  (env-var backed via `pydantic-settings`). Don't read `os.environ` directly
  in application code.
- **Migrations**: every schema change goes through Alembic
  (`uv run alembic revision --autogenerate -m "..."`). Never hand-edit the
  database schema or use `Base.metadata.create_all()` outside of tests.
  New model modules must be imported in `backend/alembic/env.py` (see the
  comment there) so autogenerate detects them.
- **Frontend**: Composition API with `<script setup lang="ts">`. Routing is
  file-based via Nuxt's `pages/` directory — don't add `vue-router` directly.
  Path alias `@/` maps to `frontend/`. API calls go through a single
  composable wrapping `$fetch`/`useFetch`, not ad-hoc `fetch` calls per
  component.
- **Environment files**: `.env.example` is the committed template; `.env` is
  local-only (gitignored) and must never contain real secrets, even in this
  early stage. Add new variables to *both* files when introduced.
- **Docker**: `docker/` holds assets shared across or external to services
  (e.g. DB init scripts). Service-specific config (Dockerfile, .dockerignore)
  lives inside `backend/` and `frontend/` themselves.

## Guidelines for upcoming work

- **Stripe Connect**: settings placeholders already exist
  (`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`).
  Keep webhook handling isolated in its own `app/api` route module; verify
  webhook signatures before trusting payloads.
- **iCal sync**: treat as a separate integration module under a future
  `app/services/` (or similar) package rather than embedding fetch/parse
  logic directly in route handlers.
- **pgvector / RAG**: the extension is already enabled at the DB level
  (`docker/postgres/init.sql`). When adding vector columns, use SQLAlchemy
  models with the `pgvector.sqlalchemy` `Vector` type and a normal Alembic
  migration — no infra changes needed.
- Don't add dependencies, abstractions, or scaffolding beyond what a task
  actually needs — this repo intentionally stayed minimal at the
  infrastructure stage; keep that bar as features land.

## Running locally

```bash
docker compose up --build
```

Frontend: http://localhost:5173 · Backend: http://localhost:8000/health ·
Postgres: localhost:5432 (credentials in `.env`).
