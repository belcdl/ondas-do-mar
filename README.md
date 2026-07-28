# Ondas do Mar

Aplicación web de alquiler y gestión de apartamentos vacacionales.

## Stack

- **Frontend**: Vue 3 + Nuxt (SSR/SSG) + TypeScript
- **Backend**: FastAPI (async SQLAlchemy 2, `psycopg` v3 driver)
- **Database**: PostgreSQL 16 with the `pgvector` extension pre-enabled
- **Migrations**: Alembic
- **Python package manager**: `uv`
- **Containers**: Docker / Docker Compose

Planned future integrations: Stripe Connect, iCal synchronization, pgvector-based RAG.

See [`docs/architecture.md`](docs/architecture.md) for infrastructure decisions
and [`CLAUDE.md`](CLAUDE.md) for project conventions and guidelines.

## Getting started

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

   (A `.env` with dev defaults is already included for local use — only do
   this if you've deleted or need to reset it.)

2. Start all services:

   ```bash
   docker compose up --build
   ```

3. Available at:
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
     - `/health` — liveness (process is up)
     - `/health/db` — readiness (verifies PostgreSQL connectivity)
     - `/api/v1/owners` — Owner CRUD (includes `GET /api/v1/owners/{id}/apartments`)
     - `/api/v1/apartments` — Apartment CRUD
     - `/api/v1/bookings` — Booking CRUD + confirm/cancel/complete actions (see `/docs` for the full Swagger schema)
   - PostgreSQL: localhost:5432

## Project structure

```
.
├── backend/        # FastAPI app, Alembic migrations, tests
├── frontend/        # Vue 3 + Nuxt + TypeScript app
├── docker/          # Shared Docker assets (e.g. Postgres init scripts)
├── docs/            # Architecture notes
├── docker-compose.yml
├── .env.example
└── CLAUDE.md
```

## Common commands

**Backend** (inside `backend/`, requires `uv`):

```bash
uv sync                                    # install dependencies
uv run uvicorn app.main:app --reload       # run locally (outside Docker)
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
uv run pytest                              # requires Postgres reachable, e.g. `docker compose up -d db`
```

Tests requiring a database run inside a transaction that is rolled back at
the end of each test (see `backend/tests/conftest.py`) — they never leave
data behind in the database they connect to.

**Frontend** (inside `frontend/`):

```bash
npm install
npm run dev
npm run type-check
```

## Status

Infrastructure verified end-to-end (FastAPI, SQLAlchemy async, Alembic,
Pydantic Settings). Owner, Apartment, Booking, RateRule, User (JWT auth), and
OwnerInvitation are all implemented end-to-end — model, repository, service,
and a full CRUD/API layer each, following the same layering established by
the original Owner slice. See [`docs/decisions.md`](docs/decisions.md) for
the reasoning behind individual choices.
