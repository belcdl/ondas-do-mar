# Decision 001

Owner uses UUID instead of integer IDs.

Reason:

- Public URLs
- Stripe metadata
- Avoid sequential IDs

Alternatives:

- Integer IDs

Status:

Accepted

# Decision 002

`/health` and `/health/db` are two separate endpoints instead of one combined check.

Reason:

- Liveness (process is up) and readiness (DB is reachable) answer different questions for an orchestrator
- A DB outage should not cause the backend process to be restarted — restarting doesn't fix Postgres
- Restart-looping a healthy process because of an external dependency makes an outage worse, not better

Alternatives:

- Single `/health` endpoint that also checks the database

Status:

Accepted

# Decision 003

Database errors are logged server-side (`logger.exception`) but the client only receives a generic message ("Database connection failed").

Reason:

- Exposing SQLAlchemy/psycopg internals (host, driver errors, stack traces) in an HTTP response is an information-disclosure risk
- The server log is the right place for the diagnostic detail; the client only needs to know that the dependency is unavailable

Alternatives:

- Return the raw exception message to the client

Status:

Accepted

# Decision 004

The backend's `.venv` is isolated with an anonymous Docker volume (`/app/.venv`) instead of living inside the `./backend:/app` bind mount.

Reason:

- Without isolation, the container's build-time `.venv` is shadowed by the bind mount at startup, forcing a re-`uv sync` on every `docker compose up` and leaking a container-built venv onto the Windows host
- `frontend` already used the equivalent pattern for `node_modules`; this makes `backend` consistent with it

Alternatives:

- Leave the bind mount as-is and accept the re-sync / host pollution

Status:

Accepted

# Decision 005

Removing an Owner is a soft delete (`is_active = false`), never a row deletion.

Reason:

- Apartments (and future Bookings) must keep referencing their historical owner even after the owner leaves the platform
- A hard delete would orphan or cascade-destroy related records

Alternatives:

- Hard delete (`DELETE FROM owners`)

Status:

Accepted

# Decision 006

Owner → Apartment will be a one-to-many relationship, with `apartment.owner_id` as `NOT NULL` and `ON DELETE RESTRICT`.

Reason:

- Every apartment must always have a responsible owner — a nullable FK would allow an invalid domain state
- `RESTRICT` (instead of `CASCADE`) enforces that an owner can only be deactivated, never deleted while apartments still reference them, at the database level, not just in application code

Alternatives:

- `ON DELETE CASCADE` (rejected — would silently destroy apartment data)
- Many-to-many (co-ownership) — not a stated requirement, would be speculative

Status:

Accepted

# Decision 007

`OwnerRepository` methods commit the session themselves; there is no separate Unit-of-Work / transaction-manager abstraction.

Reason:

- The app has no current requirement to compose multiple repository calls into one atomic transaction
- Introducing a Unit-of-Work pattern now, with a single entity and single-row writes, would be speculative architecture

Alternatives:

- Unit-of-Work pattern with explicit transaction boundaries owned by the service layer

Status:

Accepted (revisit before Booking — see Sprint 3.5 review, "Can wait")

# Decision 008

`OwnerService` receives an `OwnerRepository` instance via constructor injection; there is no abstract repository interface/ABC.

Reason:

- Only one concrete implementation (Postgres) exists or is planned
- Constructor injection alone already makes the service testable with a fake repository if ever needed, without the overhead of an abstract base class

Alternatives:

- Abstract `AbstractOwnerRepository` base class with a concrete Postgres implementation

Status:

Accepted

# Decision 009

`OwnerService` raises domain-specific exceptions (`OwnerNotFoundError`, `OwnerEmailAlreadyExistsError`) instead of returning `None` or letting SQLAlchemy exceptions propagate.

Reason:

- Gives calling code (and, later, the API layer) an explicit, typed contract for expected failure cases
- Keeps SQLAlchemy as an implementation detail invisible above the repository layer

Alternatives:

- Return `None` / raise `SQLAlchemyError` directly to callers

Status:

Accepted

# Decision 010

Deactivating an owner is exposed as `POST /owners/{id}/deactivate`, not `DELETE /owners/{id}`.

Reason:

- HTTP `DELETE` communicates resource removal to API consumers and to anyone reading the Swagger docs; here nothing is removed, only `is_active` changes
- An explicit action endpoint documents its own intent unambiguously

Alternatives:

- `DELETE /owners/{id}` implemented as a soft delete

Status:

Accepted

# Decision 011

Domain-error-to-HTTP-status translation is centralized in global FastAPI exception handlers (`main.py`), not repeated as `try/except` in each endpoint.

Reason:

- `OwnerNotFoundError` → 404 and `OwnerEmailAlreadyExistsError` → 409 apply to multiple endpoints; centralizing avoids duplicating the same block five times
- Keeps endpoint functions focused on orchestration, not error-code mapping

Alternatives:

- `try/except` + `HTTPException` inline in every endpoint

Status:

Accepted

# Decision 012

`PATCH /owners/{id}` is used for partial updates; `PUT` is not implemented.

Reason:

- `OwnerUpdate` already models every field as optional — a full-resource-replacement semantic (`PUT`) doesn't match how the endpoint is actually used
- Avoids offering two endpoints for the same operation

Alternatives:

- `PUT /owners/{id}` requiring the full resource body

Status:

Accepted

# Decision 013

`Owner.email` is typed as plain `str` in the Pydantic schemas, not `EmailStr`.

Reason:

- `EmailStr` requires the `email-validator` package, which is not yet a project dependency
- No endpoint existed yet to exercise that validation when the schemas were first written; adding an unused dependency ahead of need conflicts with the project's stated minimalism

Alternatives:

- `EmailStr` (add `email-validator` as a dependency now)

Status:

Accepted (deferred — trivial to upgrade when justified by real invalid-input handling needs)

# Decision 014

Stripe/legal fields (`tax_id`, billing address) and authentication credentials are not part of the `Owner` model.

Reason:

- Not required until Stripe Connect / an owner login portal are actually built (CLAUDE.md marks Stripe Connect as a planned integration, not a current one)
- Adding nullable columns later via Alembic is a trivial, low-risk change — there is no cost to deferring them
- Conflating "business owner record" with "authentication identity" now would be premature coupling; whether auth becomes fields on `Owner` or a separate `User` table is an open decision for when it's actually needed

Alternatives:

- Add the columns now, nullable, for future use

Status:

Accepted

# Decision 015

`ApartmentService` depends on `OwnerRepository` directly, not `OwnerService`, to validate that an apartment's owner exists and is active.

Reason:

- The only thing needed is a lookup (`get_by_id`) and a status check, not Owner's own business rules (email uniqueness, etc.)
- Keeps the dependency direction as Service → Repository throughout, rather than introducing Service → Service coupling between domains

Alternatives:

- `ApartmentService` depends on `OwnerService` instead

Status:

Accepted

# Decision 016

Apartments can only be created for, or reassigned to, an owner that is both existing and active (`is_active = true`).

Reason:

- If a deactivated owner could still receive new apartments, deactivation (Decision 005) wouldn't mean much operationally
- Two distinct failure cases are surfaced as two distinct exceptions: `OwnerNotFoundError` (reused from the Owner domain) for a nonexistent owner, and a new `InactiveOwnerError` for an existing-but-inactive one — mixing them into one error would hide which situation actually occurred

Alternatives:

- Allow assigning apartments to any owner regardless of `is_active`

Status:

Accepted

# Decision 017

Ownership history (who owned an Apartment over time) is explicitly out of scope for the MVP; `Apartment.owner_id` represents only the current owner.

Reason:

- No current requirement needs a historical view of ownership
- The field can't paint the app into a corner: adding history later is purely additive (a new `apartment_ownership_periods` table populated when `owner_id` changes), with no redesign of the `Apartment` table itself

Alternatives:

- Model ownership as a versioned/history table from the start

Status:

Accepted

# Decision 018

Exception handling is centralized in `app/core/exceptions.py`: a 4-class hierarchy (`NotFoundError`, `ConflictError`, `ValidationError`, `BusinessRuleError`, all under `ApplicationError`) plus a single `register_exception_handlers(app)` called once from `main.py`. Domain exceptions subclass one of the four instead of getting their own `@app.exception_handler`.

Reason:

- By Sprint 4.2, Owner and Apartment had each grown their own near-identical `@app.exception_handler` blocks in `main.py` — visible duplication that would repeat again for every future entity
- Starlette dispatches exception handlers by walking the raised exception's MRO, so registering a handler for the 4 base classes is sufficient to catch every subclass automatically — no per-entity registration needed, ever
- `ValidationError` and `BusinessRuleError` both map to HTTP 422 deliberately — the distinction exists for the Python call site (which one to catch/raise), not to create a fifth or sixth HTTP status code nobody asked for

Alternatives:

- Keep one `@app.exception_handler` per concrete exception type per entity (status quo, rejected as the source of the duplication)
- A full exception-to-status mapping registry/framework with dynamic lookup (rejected as overengineering — 4 fixed classes and one loop is enough)

Status:

Accepted
