# Architecture

## Overview

Ondas do Mar is a vacation rental / apartment management platform. This
document tracks infrastructure-level decisions; day-to-day conventions live
in [`CLAUDE.md`](../CLAUDE.md).

## Services

| Service  | Tech                          | Container | Port |
|----------|-------------------------------|-----------|------|
| frontend | Vue 3 + Vite + TypeScript     | frontend  | 5173 |
| backend  | FastAPI + SQLAlchemy 2 (async)| backend   | 8000 |
| db       | PostgreSQL 16 + pgvector      | db        | 5432 |

## Key decisions

- **Single DB driver (`psycopg` v3)**: used for both Alembic's synchronous
  migrations and the app's async SQLAlchemy engine, avoiding the need for
  two separate driver dependencies (`asyncpg` + `psycopg2`).
- **`pgvector/pgvector:pg16` as the base Postgres image**: pgvector is a
  planned future integration (RAG). Using the extension-enabled image now,
  with `CREATE EXTENSION IF NOT EXISTS vector` run on first init, means no
  infrastructure migration is needed when RAG work starts.
- **`uv` for Python dependency management**: fast, lockfile-based, and the
  backend Dockerfile installs it via the official Astral image layer so no
  host installation is required to build.
- **Dev-only `.env`**: `.env.example` is committed as the template; the real
  `.env` holds dummy local credentials and is gitignored, per standard
  practice, even though it currently contains no real secrets.
- **Backend layering (API → Service → Repository → Model)**: established
  with the Owner domain and intended to repeat for every future entity.
  `app/api/*` handles HTTP concerns and dependency wiring only; `app/services/*`
  holds business rules and raises domain-specific exceptions; `app/repositories/*`
  is the only layer that talks to SQLAlchemy. Dependency providers are
  centralized in `app/api/deps.py` rather than duplicated per router.
  Individual decisions (why UUIDs, why soft delete, why no Unit of Work yet,
  etc.) are logged in [`decisions.md`](decisions.md) as they're made.
- **Owner → Apartment (one-to-many)**: every Apartment has exactly one
  current owner via `owner_id`, enforced with `ON DELETE RESTRICT` at the
  database level — Postgres itself refuses to delete an Owner row that still
  has Apartments, independent of anything the application layer does. Owner
  removal is only ever the existing soft delete (`is_active = false`); the
  app never issues a hard delete. Cross-entity business rules (an Apartment
  can only be assigned to an owner that exists and is active) live in
  `ApartmentService`, which depends on `OwnerRepository` directly — not on
  `OwnerService` — since the only thing needed is a lookup, not Owner's own
  business rules.
- **Ownership history is out of scope for the MVP by design**: `owner_id` on
  Apartment represents only the current owner. Adding a history later is
  purely additive — a new `apartment_ownership_periods` table
  (`apartment_id`, `owner_id`, `started_at`, `ended_at`) populated by the
  service whenever `owner_id` changes — with no redesign of the `Apartment`
  table itself.
- **Centralized exception handling (`app/core/exceptions.py`)**: a small
  hierarchy (`ApplicationError` → `NotFoundError` / `ConflictError` /
  `ValidationError` / `BusinessRuleError`) plus one `register_exception_handlers(app)`
  called once from `main.py`. Domain exceptions (`OwnerNotFoundError`,
  `ApartmentNotFoundError`, `InactiveOwnerError`, etc.) subclass one of the
  four base errors instead of getting their own handler — Starlette matches
  handlers by walking the exception's MRO, so registering a handler for
  `NotFoundError` automatically catches every subclass of it. New entities
  never register their own exception handlers; they just subclass the right
  base. `ValidationError` and `BusinessRuleError` both map to 422 — that's
  intentional, not an oversight: the HTTP status is coarse-grained on
  purpose, the Python exception type is what gives calling code (and future
  API consumers reading `detail`) the precise reason.

## Planned integrations (not yet implemented)

- **Stripe Connect** — for owner payouts/marketplace payments.
- **iCal synchronization** — for external calendar availability sync.
- **pgvector-based RAG** — semantic search / assistant features.
