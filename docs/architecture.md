# Architecture

## Overview

Ondas do Mar is a vacation rental / apartment management platform. This
document tracks infrastructure-level decisions; day-to-day conventions live
in [`CLAUDE.md`](../CLAUDE.md).

## Services

| Service  | Tech                                  | Container | Port |
|----------|---------------------------------------|-----------|------|
| frontend | Vue 3 + Nuxt 3 (SSR/SSG) + TypeScript | frontend  | 5173 |
| backend  | FastAPI + SQLAlchemy 2 (async)        | backend   | 8000 |
| db       | PostgreSQL 16 + pgvector              | db        | 5432 |

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
- **`GET /owners/{id}/apartments`**: lives on the owners router (`app/api/owners.py`),
  not the apartments router, since the URL is nested under the owner
  resource. The handler composes both `OwnerService` (to 404 on a
  nonexistent owner) and `ApartmentService` (to list, reusing
  `list_apartments_by_owner`, unchanged since Sprint 4) — this is the API
  layer orchestrating two services for one read, not a Service depending on
  another Service.
- **Booking (Sprint 5.2)**: belongs to exactly one Apartment (`apartment_id`,
  `ON DELETE RESTRICT`). `owner_id` is copied from the apartment's current
  owner once, at creation, and is never updated afterwards — a deliberate
  historical snapshot, not a live relationship (Decision 022). `status` is a
  4-state machine (`pending`/`confirmed`/`cancelled`/`completed`) stored as
  `VARCHAR` + `CHECK` constraint (`native_enum=False, create_constraint=True`)
  rather than a native Postgres `ENUM`, specifically so adding a 5th state
  later is a normal migration, not an `ALTER TYPE`. Status changes only
  happen through `POST /bookings/{id}/{confirm,cancel,complete}`, never
  through the generic `PATCH` (Decision 023).
- **Double-booking protection (Sprint 5.3)**: enforced entirely by Postgres,
  not application code — a partial `EXCLUDE USING gist` constraint on
  `bookings` (`apartment_id WITH =`, `daterange(check_in_date, check_out_date,
  '[)') WITH &&`, `WHERE status = 'confirmed'`), backed by the `btree_gist`
  extension. An `EXCLUDE` constraint is checked as part of the write itself
  (like `UNIQUE`, via an index), so there is no time-of-check-to-time-of-use
  gap the way there would be with a "search overlapping bookings, then
  insert" check in the service — that pattern was deliberately rejected for
  exactly the reason it caused the Owner email race in Sprint 3.6. Verified
  under real concurrency: 5 simultaneous `POST /bookings/{id}/confirm` calls
  for overlapping dates produced exactly one `200` and four `409`s, never a
  `500`. Because a booking is only ever inserted as `pending`, the
  constraint can't fire at creation — it fires at `confirm_booking`, which is
  why that method (not just `create_booking`/`update_booking`) now also
  catches `IntegrityError` and translates it to `ConflictError` (Decision 027).
  `alembic --autogenerate` does not detect `ExcludeConstraint` changes (confirmed
  empirically), so its migration is hand-written; the constraint is still
  declared on the `Booking` model for documentation accuracy.
- **`confirmation_code` as the public booking identifier**: guests have no
  account and no other practical way to self-identify a booking, so
  `GET /bookings/by-confirmation/{code}` exists alongside `GET /bookings/{id}`
  as a separate, guest-facing lookup path (Decision 028). The two identifiers
  serve different audiences — `id` for the internal/owner-facing routes,
  `confirmation_code` for anyone without platform access.
- **Booking list filters live in `BookingRepository.list_all`** as composable
  optional `WHERE` clauses (`apartment_id`, `owner_id`, `status`,
  `check_in_from`, `check_in_to`, `guest_email`), not as separate methods —
  continuing the direction set for Apartment listing in Decision 024
  (Decision 029).
- **Authentication (Sprint 6.1)**: `User` is a standalone entity (JWT
  identity, `admin`/`owner` role), separate from `Owner` (the business
  entity). Linked via `owner.user_id` (nullable, unique) — no `relationship()`
  between them, deliberately (Decision 033). JWT access tokens (`core/security.py`,
  PyJWT + passlib/bcrypt), validated by `get_current_user` →
  `get_current_active_user` → `require_admin`/`require_owner`, a layered
  dependency chain in `app/api/deps.py` reused by any router. Two new
  exception branches (`AuthenticationError` 401, `PermissionDeniedError` 403)
  slot into the existing centralized handler with zero changes to
  `main.py` (Decision 036) — the same payoff Decision 018 was designed for.
  Every login/token failure mode returns an identical generic message
  within its category, closing the email-enumeration pattern QA-1 found on
  Owner creation (Decision 035). No endpoint yet creates or links Users —
  `POST /auth/login`, `POST /auth/logout`, and `GET /auth/me` are the only
  auth surface this sprint; user management and applying `require_admin`/
  `require_owner` to the existing Owner/Apartment/Booking routers are
  follow-up work.
- **Ownership authorization (Sprint 6.2)**: every Owner/Apartment/Booking
  endpoint except `POST /bookings` and `GET /bookings/by-confirmation/{code}`
  (which stay public — guests have no accounts, Decision 040) now requires
  authentication and enforces "an owner only touches their own resources,
  an admin touches anything." Centralized as one comparison helper
  (`authorize_owner_match`) plus fetch-then-authorize dependencies
  (`get_authorized_owner`/`get_authorized_apartment`/`get_authorized_booking`)
  in `app/api/deps.py` (Decision 041) — no per-router duplication, and 404
  is structurally impossible to use for hiding a resource that exists but
  isn't the caller's, since the dependency always fetches (real 404 first)
  before comparing ownership (403 second) (Decision 042). List endpoints
  (`GET /apartments`, `GET /bookings`) filter rather than allow/deny,
  reusing the already-existing scoped service methods. `owner.user_id`
  linking still has no public endpoint (Decision 039) — tests link directly
  at the ORM level, same as `test_owner_apartment_relationship.py`.

## Planned integrations (not yet implemented)

- **Stripe Connect** — for owner payouts/marketplace payments across the 6
  independent owners. Note: single-account Stripe Checkout (hosted page) for
  guest payments *is* already implemented (`app/services/payment.py`,
  `app/api/payments.py`) — Connect is only about splitting a payout across
  owners, not payments in general.
- **iCal synchronization** — for external calendar availability sync.
- **pgvector-based RAG** — semantic search / assistant features.
