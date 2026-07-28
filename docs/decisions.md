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

# Decision 019

`GET /owners/{id}/apartments` is defined on the owners router, not the apartments router, and 404s if the owner doesn't exist rather than silently returning an empty list.

Reason:

- The URL is nested under the owner resource, so it belongs with the other `/owners/{id}/...` routes for discoverability
- Distinguishing "owner has zero apartments" (200, `[]`) from "owner doesn't exist" (404) is more correct REST semantics than collapsing both into an empty list
- `ApartmentService.list_apartments_by_owner` already existed unchanged since Sprint 4 (written but never wired to a route) — this endpoint only adds the HTTP layer

Alternatives:

- Define it on the apartments router instead, as a query filter (`GET /apartments?owner_id=...`)

Status:

Accepted

# Decision 020

`Booking.guest_count` is required (`NOT NULL`), not optional as originally proposed in the Sprint 5.1 design.

Reason:

- User feedback: guest count is contractual data agreed at booking time, not just derivable metadata — treating it as optional would undersell its importance and allow bookings with no record of how many people are staying

Alternatives:

- Nullable `guest_count`, treated as purely informational (rejected per user feedback)

Status:

Accepted

# Decision 021

`Booking.status` has four values: `pending`, `confirmed`, `cancelled`, `completed` — not the three (`pending`/`confirmed`/`cancelled`) originally proposed in the Sprint 5.1 design.

Reason:

- User decision to track completion explicitly as a stored state, not derive it from `check_out_date < today`
- Trade-off worth recording: since there is no scheduled job in this sprint, a booking only becomes `completed` when something explicitly calls `POST /bookings/{id}/complete` — it will not happen automatically when the stay ends. If that's needed later, it's an additive scheduler, not a model change

Alternatives:

- Three states, with "completed" computed from dates rather than stored (rejected per user feedback)

Status:

Accepted

# Decision 022

`Booking.owner_id` is captured once from `apartment.owner_id` at creation time and is never updated afterwards, even if the apartment's ownership later changes.

Reason:

- Ownership history was deliberately excluded from the Apartment domain (Decision 017) — without a snapshot on Booking, reassigning an apartment's owner would silently and permanently lose the answer to "who owned this apartment when this booking was made," which matters for future payout attribution (Stripe Connect)
- This is the same "freeze the transaction terms" principle already applied to `total_price`: what was true at booking time must stay true for that booking, regardless of what changes later
- No service method ever assigns to `Booking.owner_id` after `create_booking` — the immutability guarantee lives in the code (nothing writes to it), not in a database trigger

Alternatives:

- Derive the booking's owner live via `booking.apartment.owner_id` on every read (rejected — loses historical accuracy the moment ownership changes)
- No `owner_id` on Booking at all, only `apartment_id` (rejected — same reason)

Status:

Accepted

# Decision 023

Booking status changes (`confirm`, `cancel`, `complete`) are exposed only through dedicated `POST /bookings/{id}/{action}` endpoints. `status` is deliberately absent from `BookingUpdate` — it cannot be changed via `PATCH /bookings/{id}`.

Reason:

- Unlike Owner/Apartment's `is_active` (a single boolean, safely settable via generic PATCH in addition to the dedicated `/deactivate` action), Booking has four states with real transition rules (e.g. a completed booking can't be cancelled) and side effects (`confirmed_at`/`cancelled_at` timestamps). A generic "set any field" PATCH can't safely encode either of those without special-casing status inside the update path anyway
- Keeping transitions to dedicated endpoints means each one has a single, auditable place enforcing its own validity rules

Alternatives:

- Include `status` in `BookingUpdate` alongside the action endpoints, mirroring Owner/Apartment's `is_active` (rejected — invites bypassing transition validation and timestamp side effects through PATCH)

Status:

Accepted

# Decision 024

`BookingRepository.list_all` takes composable optional filters (`apartment_id`, `owner_id`, `status`) instead of separate methods like `ApartmentRepository.list_by_owner`.

Reason:

- Booking has more realistic filter dimensions than Apartment did; a separate method per dimension (`list_by_apartment`, `list_by_owner`, `list_by_status`, and combinations) would multiply faster than it's worth
- `GET /bookings` exposes all three as independent, combinable query parameters

Alternatives:

- Mirror `ApartmentRepository` exactly with one method per relationship (rejected as the pattern doesn't scale as cleanly here)

Status:

Accepted

# Decision 025

A confirmation-code collision on `Booking` creation surfaces as a generic `ConflictError`, with no retry loop.

Reason:

- `confirmation_code` is an 8-character random hex string (~4.3 billion combinations); at this application's realistic scale, retry logic would be defensive complexity for a practically negligible probability
- Unlike the Owner email race (Sprint 3.6, `Must fix now` — driven by real concurrent user input), a code collision isn't caused by anything a client did, so surfacing it as a clean `ConflictError` rather than a raw 500 is enough for now

Alternatives:

- Retry code generation a fixed number of times on collision (deferred, not rejected — cheap to add later if it's ever observed)

Status:

Accepted

# Decision 026

Sprint 5.2 implements only the `CHECK (check_out_date > check_in_date)` constraint. No mechanism prevents two `confirmed` bookings from overlapping on the same apartment — that is explicitly deferred to Sprint 5.3 (`EXCLUDE USING gist` with the `btree_gist` extension, as proposed in the Sprint 5.1 design).

Reason:

- Explicit sprint scope: "Do NOT implement availability checking yet" / "Do NOT implement the EXCLUDE constraint yet"
- Flagging this loudly here because it's the single biggest gap left in the Booking domain: nothing today stops double-booking the same apartment for overlapping dates

Alternatives:

- None — this is a scope boundary, not a design choice between alternatives

Status:

Accepted (scope deferred to Sprint 5.3)

# Decision 027

Double-booking is prevented with a partial `EXCLUDE USING gist` constraint on `bookings` (`apartment_id WITH =`, `daterange(check_in_date, check_out_date, '[)') WITH &&`, `WHERE status = 'confirmed'`), enabled by the `btree_gist` extension. This replaces the "search then insert" application-level check that was explicitly ruled out for this sprint.

Reason:

- A "search overlapping bookings, then insert if none found" check in the service has the same time-of-check-to-time-of-use gap that caused the Owner email race (Sprint 3.6) — under READ COMMITTED, two concurrent transactions can both see "no conflict" before either has written. No amount of careful application code closes that gap; only the database checking the write itself, atomically, can
- `EXCLUDE` constraints are enforced by the same mechanism as `UNIQUE` — via an index (GiST here, since `&&` overlap isn't a B-tree-comparable operator) — so a conflicting `INSERT`/`UPDATE` is rejected as part of the single write statement, not a separate step. There is no gap to race
- `btree_gist` is required because `apartment_id` (a UUID equality comparison) needs a GiST operator class to participate in the same exclusion constraint as the date-range overlap operator; without it, `apartment_id WITH =` isn't valid inside a GiST index
- The constraint is **partial** (`WHERE status = 'confirmed'`) so `pending` and `cancelled` bookings never block dates — only bookings that have actually been confirmed compete for the same date range
- Verified under real concurrency, not just sequential test assertions: 5 concurrent `POST /bookings/{id}/confirm` calls for overlapping dates on the same apartment produced exactly one `200` and four clean `409`s, zero `500`s
- Alembic's `--autogenerate` does not detect `ExcludeConstraint` (confirmed empirically — it produced an empty migration), so this migration is hand-written. The `ExcludeConstraint` is still declared in the `Booking` model's `__table_args__` so the code accurately documents the real schema, even though autogenerate can't compare against it
- Any `IntegrityError` this constraint raises is caught in `BookingService` (in `create_booking`, `update_booking`, and — critically — `confirm_booking`, since a booking is only ever inserted as `pending` and the constraint can't fire until the status transition to `confirmed`) and translated to `ConflictError`. The translation inspects `exc.orig.diag.constraint_name` (a psycopg diagnostic field, accessed via `getattr` rather than importing a psycopg-specific exception class) to give an accurate message distinguishing an overlap conflict from a confirmation-code collision

Alternatives:

- Application-level overlap check before insert (rejected — the exact race this decision exists to close)
- `SELECT ... FOR UPDATE` row locking to serialize access per apartment (rejected — more complex, and still weaker than a constraint the database enforces unconditionally, including against writes the application layer didn't anticipate)

Status:

Accepted

# Decision 028

`confirmation_code` is the public identifier for a booking (`GET /bookings/by-confirmation/{code}`), not the UUID `id`.

Reason:

- Guests don't have accounts (an explicit MVP requirement) and have no other way to self-identify a booking than something they can read over the phone or retype from an email — a UUID is impractical for that, an 8-character code is not
- Keeping `id` as the internal/URL-path identifier for the authenticated-owner-facing endpoints (`GET/PATCH /bookings/{id}`, the action endpoints) and `confirmation_code` as the separate guest-facing lookup key avoids conflating "internal primary key" with "identifier meant to be shared externally" — the same reasoning that motivated UUIDs over sequential ints in the first place (Decision 001) applies again one layer up
- The lookup normalizes input (trims whitespace, uppercases) before querying, since a human is expected to type this value

Alternatives:

- Use the UUID `id` for guest-facing lookup too (rejected — impractical for guests to read/type/quote)

Status:

Accepted

# Decision 029

Booking's list filters (`apartment_id`, `owner_id`, `status`, `check_in_from`, `check_in_to`, `guest_email`) live entirely in `BookingRepository.list_all` as composable optional `WHERE` clauses, not as separate repository methods or as filtering logic in the service.

Reason:

- Continues the direction set in Decision 024: as filter dimensions grow, one method per combination doesn't scale, but one method with independent optional clauses does
- Filtering is a data-access concern (which `WHERE` clauses to add to a `SELECT`), not a business rule — it belongs in the repository, the same way the service never builds SQL and the repository never decides what a "conflict" means
- `guest_email` is compared case-insensitively (`func.lower(...)`) directly in the query rather than fetching all rows and filtering in Python — keeps the query itself the source of truth and avoids loading unfiltered data into memory

Alternatives:

- Build the filtered list in the service by calling `list_all()` unfiltered and filtering in Python (rejected — pulls a data-access concern into the business-logic layer, and scales worse)

Status:

Accepted

# Decision 030

The "owner exists and is active" race (QA-1 audit finding) is closed with `SELECT ... FOR UPDATE` (`OwnerRepository.get_by_id_for_update`), not a database constraint.

Reason:

- Owner's own race (email uniqueness) and Booking's overlap race were both closed with a constraint the database rejects and the app catches. "Is this referenced row currently active" has no equivalent constraint to violate — it's a precondition on another table's row, not a uniqueness/range property of the row being written
- Row locking is the standard database-native answer to the same underlying problem (don't trust a plain read of another row across a write): the lock held during the check blocks a concurrent `deactivate_owner()` until the transaction referencing that owner commits, so the two can never interleave
- Verified live: 5 consecutive concurrent `create_apartment` + `deactivate_owner` runs against the same owner, no 500s, no apartment ever left referencing an owner that was already inactive at commit time

Alternatives:

- A trigger enforcing owner.is_active on insert/update of Apartment/Booking (rejected — Postgres CHECK constraints can't reference another table, and a trigger is more invasive than this problem warrants)
- Leave the race open (rejected — same failure class the project already treated as worth fixing twice)

Status:

Accepted

# Decision 031

"Owner exists and is active" is extracted into `app.services.owner_guard.ensure_owner_is_active`, shared by `ApartmentService` and `BookingService`. `InactiveOwnerError` moved from `services/apartment.py` to this new module; no backwards-compatible re-export was kept — all call sites (services and tests) were updated directly.

Reason:

- QA-1 found this rule duplicated independently in both services, with a real inconsistency: `BookingService` used to collapse "owner not found" and "owner inactive" into a single error, unlike `ApartmentService`. The shared helper removes both the duplication and the inconsistency in one change
- Keeping a re-exported alias in `apartment.py` for compatibility was considered and rejected — nothing outside this codebase depends on the old import path, so a shim would only be dead weight

Status:

Accepted

# Decision 032

`DataError` (e.g. a string longer than its column's `VARCHAR(n)`) is now caught alongside `IntegrityError` in all three repositories, and translated to `ValidationError` in the services that write user-supplied text (`OwnerService`, `ApartmentService`, `BookingService`'s create/update — not its status-transition methods, which never write client-controlled fields).

Reason:

- QA-1 found this was the single most severe gap: `DataError` is a sibling of `IntegrityError`, not a subclass, so the existing `except IntegrityError` blocks never caught it — any client sending an over-long string in any text field on any of the three entities got a raw 500
- Deliberately scoped to catching the DB-level error, not adding `max_length` to every Pydantic field — that's a complementary fix, not what this sprint asked for

Status:

Accepted

# Decision 033

`User` is a standalone entity, not a subtype or extension of `Owner`. The link is `owner.user_id` (nullable, unique) — an Owner may have zero or one User; a User belongs to at most one Owner. No `relationship()` objects were added between them.

Reason:

- Owners are business entities (who owns a property); Users are authentication identities (who can log in). Conflating them would make it impossible to have an owner without portal access, or an admin who isn't an owner at all — both are explicit requirements here
- `relationship()` was deliberately omitted per the QA-1 audit finding: every existing relationship (`Owner.apartments`, `Booking.owner`, etc.) is declared but never traversed anywhere in application code, and carries a real `MissingGreenlet` risk under async sessions with the default `lazy="select"`. This sprint applies that lesson from the start instead of repeating the pattern a fourth time
- No endpoint sets `owner.user_id` yet — deliberately out of scope. Requirement 2 asked for the column/constraint (a data-model requirement), not a linking workflow; nothing in the endpoint list (`/auth/login`, `/auth/logout`, `/auth/me`) needs one. Tests that need a User-linked Owner set `user_id` directly on the ORM object, the same way `test_owner_apartment_relationship.py` already does for constraint testing

Alternatives:

- Store role/auth fields directly on `Owner` (rejected in Decision 014 already, before User existed)
- Add `relationship()` objects for consistency with Owner/Apartment/Booking (rejected — QA-1 already flagged this as a real risk, no reason to add a fourth instance of it)

Status:

Accepted

# Decision 034

Login uses `OAuth2PasswordRequestForm` (form-encoded `username`/`password`) rather than a JSON body, and `POST /auth/login` is the only login mechanism — no parallel JSON endpoint.

Reason:

- `OAuth2PasswordBearer(tokenUrl="auth/login")` is what makes Swagger's "Authorize" button work out of the box (requirement 9) — it specifically expects a form-encoded password-flow login endpoint at that URL
- Building a second, JSON-based login endpoint alongside it would duplicate the same logic behind two routes for no real gain at this stage (requirement 6 explicitly asks not to duplicate logic between routers). A JSON-friendly frontend can still call this endpoint by sending `application/x-www-form-urlencoded` instead of JSON — a client detail, not a reason for a second server-side code path

Alternatives:

- JSON body login (`{"email": ..., "password": ...}`) instead of, or alongside, the OAuth2 form (rejected for now — revisit if a JSON-only frontend integration makes the form encoding genuinely painful)

Status:

Accepted

# Decision 035

Login, "current user or inactive", and JWT decoding all return the exact same generic error for every failure mode within their category — `authenticate()` always raises `InvalidCredentialsError("Incorrect email or password")` whether the email doesn't exist, the password is wrong, or the account is inactive; `get_user_from_token()` always raises `AuthenticationError("Could not validate credentials")` whether the token is malformed, expired, or references a deleted user.

Reason:

- This is the direct, deliberate fix for the email-enumeration gap QA-1 found on `POST /owners` (a 409 there reveals whether an email is registered), applied to the much more sensitive login surface from the start rather than discovered later
- Verified explicitly in tests: `test_authenticate_nonexistent_email_raises_same_error` and `test_authenticate_inactive_user_raises_same_error` both assert the identical exception type and message as a wrong password

Alternatives:

- Distinct messages per failure mode (e.g. "no such user" vs "wrong password") — rejected, this is exactly the enumeration vector being closed

Status:

Accepted

# Decision 036

Two new branches were added to the exception hierarchy — `AuthenticationError` (401) and `PermissionDeniedError` (403), both direct children of `ApplicationError` in `core/exceptions.py`. `InvalidCredentialsError` (in `services/user.py`) subclasses `AuthenticationError`. No `WWW-Authenticate` header is added to 401 responses.

Reason:

- Neither existing branch (`NotFoundError`/`ConflictError`/`ValidationError`/`BusinessRuleError`) maps to 401/403 — those are genuinely new HTTP semantics (who are you / you can't do this), not a shade of an existing one
- Adding them required exactly two new entries in `_STATUS_CODES` and zero changes to `register_exception_handlers` itself or to `main.py` — the design from Decision 018 (Sprint 4.2) absorbed a whole new domain (auth) without any change to the registration mechanism, which is the point of that design
- `require_admin`/`require_owner` raise `PermissionDeniedError` directly rather than each having their own leaf exception type — requirement 8 explicitly asked for only these 3 new exceptions, and a distinct `AdminRequiredError`/`OwnerRequiredError` pair wasn't asked for and isn't needed for a single boolean role check
- `WWW-Authenticate: Bearer` on 401s is the "more correct" HTTP behavior but would require special-casing one exception type inside the otherwise-uniform generic handler, which Decision 018 deliberately kept simple ("not an exception framework"). Left as a documented gap rather than special-cased

Alternatives:

- Add `WWW-Authenticate` header handling into `register_exception_handlers` (deferred — noted as technical debt, not worth complicating the generic handler for one header on one status code)

Status:

Accepted

# Decision 037

`passlib` bcrypt backend requires pinning `bcrypt>=4.0.1,<4.1` explicitly, alongside `passlib[bcrypt]`.

Reason:

- `passlib` 1.7.4 (its last release, 2020) is incompatible with `bcrypt` 4.1+: a self-test passlib runs at import time trips a stricter 72-byte-password check that newer bcrypt enforces as a hard error instead of silently truncating, breaking `hash_password()`/`verify_password()` entirely. Confirmed by hitting the actual `ValueError: password cannot be longer than 72 bytes` during implementation, not a hypothetical
- Pinning `bcrypt` is the standard, documented workaround for this well-known passlib/bcrypt version conflict. `passlib` itself has had no release since 2020 and is effectively unmaintained — this pin is a known constraint of the requested stack (requirement 4 mandates passlib+bcrypt specifically), not a choice made freely

Alternatives:

- Drop passlib, call `bcrypt` directly (rejected — requirement 4 explicitly mandates passlib)
- Switch to `argon2` or another passlib-supported scheme (rejected — requirement 4 explicitly mandates bcrypt)

Status:

Accepted

# Decision 038

The Alembic migration adding `users` and `owners.user_id` (`9597099776e8`) was autogenerated and then hand-corrected: the generated `downgrade()` called `op.drop_constraint(None, 'owners', ...)` for the new unique constraint and foreign key, which cannot work — `None` is not a valid constraint name to drop. Both constraints were given explicit names (`owners_user_id_key`, `owners_user_id_fkey`, matching Postgres's own default naming convention) in both `upgrade()` and `downgrade()`.

Reason:

- Verified by actually running `alembic downgrade -1` on this migration (not assumed) — this is exactly the kind of bug Sprint 5.4's audit finding ("the EXCLUDE migration's downgrade had never been run") warned about: an unverified downgrade path is a real risk, not a theoretical one. This migration's downgrade was run and confirmed working before being trusted
- Unlike the `EXCLUDE`/`CHECK` constraints in earlier sprints, autogenerate handles unique constraints and foreign keys correctly — the bug here was in the unnamed-constraint pattern autogenerate emits by default, not in autogenerate's detection

Status:

Accepted

# Decision 039

`owner.user_id` stays nullable (unchanged from Decision 033); there is still no public endpoint to link a User to an Owner. `OwnerUpdate.user_id` was added so an admin *can* set it through the existing `PATCH /owners/{id}`, but a non-admin caller is rejected (403) if `user_id` is present in the request at all — whether setting or unsetting it.

Reason:

- "Cada Owner tendrá exactamente un User" describes the target steady state, not a constraint the schema can enforce today without inventing a combined registration flow nobody asked for — `OwnerCreate` still doesn't take a `user_id`/credentials, and adding that is a distinct feature (self-registration) this sprint's endpoint list doesn't include
- Letting an owner set their *own* `user_id` would be a real vulnerability — an owner could relink their profile to a different account, or unlink themselves, entirely client-side. Restricting the field to admin-only, rather than the whole endpoint, keeps `PATCH /owners/{id}` usable for an owner's own profile edits (phone, name) while closing that hole
- Tests link Owner↔User directly at the ORM level (`owner.user_id = user.id`), the same pattern `test_owner_apartment_relationship.py` already used for constraint testing — consistent with the project's existing convention for "needed for tests, not yet exposed via API"

Alternatives:

- Extend `OwnerCreate` to optionally accept credentials and provision both rows atomically (deferred — real feature, not asked for this sprint)
- A dedicated `POST /owners/{id}/link-user` endpoint (deferred — `PATCH` already covers it once the field-level restriction exists; a separate endpoint would be one more thing to keep in sync with the same rule)

Status:

Accepted

# Decision 040

Booking creation (`POST /bookings`) and confirmation-code lookup (`GET /bookings/by-confirmation/{code}`) remain fully public — no authentication. Every other Booking endpoint (list, get-by-id, update, confirm/cancel/complete) requires authentication and is owner/admin-scoped.

Reason:

- Sprint 5.1 established "guests have no accounts" as a foundational requirement — `confirmation_code` exists specifically because guests need a way to create and later look up a booking without logging in (Decision 028). Sprint 6.2 doesn't revisit that decision, so gating these two endpoints behind auth would silently break the guest-facing design without being asked to
- Everything else on Booking is a property-management action (viewing the guest list, confirming a booking, editing details) — plausibly something only the owner/admin should do, and squarely covered by "el owner únicamente podrá acceder a reservas pertenecientes a apartamentos de su propiedad"

Alternatives:

- Require authentication on all Booking endpoints including create/lookup (rejected — breaks the guest-facing design from Sprint 5.1 without being asked to)

Status:

Accepted

# Decision 041

Authorization is centralized as: one comparison helper (`authorize_owner_match`), one resolver dependency (`get_current_owner_or_none`), and three "fetch-then-authorize" dependencies (`get_authorized_owner`, `get_authorized_apartment`, `get_authorized_booking`) in `app/api/deps.py`. Each resource-scoped endpoint depends on the relevant one instead of writing its own comparison.

Reason:

- The fetch-then-authorize dependencies reuse each service's existing `get_owner`/`get_apartment`/`get_booking` (which already 404 correctly) and only add the ownership comparison on top — no duplicated fetch logic, and the 404-before-403 ordering (Decision 042) falls out naturally from calling the existing method first
- `GET /apartments` and `GET /bookings` (list endpoints) can't use these — a list isn't a single resource to authorize, it needs to be *filtered*. Those two routers call `get_current_owner_or_none` directly and choose between the existing unscoped/owner-scoped service methods based on role — no new service code, since `list_apartments_by_owner` and `list_bookings(owner_id=...)` already existed
- `POST /apartments` also can't use a fetch-then-authorize dependency (there's no existing resource yet to fetch) — it calls `authorize_owner_match` directly against the request body's `owner_id` after resolving the caller's own Owner via the same `get_current_owner_or_none`
- Field-level restrictions (`owner_id` reassignment on Apartment, `user_id` linking on Owner) are deliberately *not* generalized into the shared helpers — each is a one-line `if field in data.model_fields_set and not admin: raise` in the specific router, since generalizing a two-instance pattern into a framework would be exactly the "ACL compleja" this sprint explicitly excludes (requirement 8)

Alternatives:

- A generic resource-authorization framework/decorator covering all cases including lists and field-level rules (rejected — requirement 8 explicitly excludes complex ACL machinery; three small dependencies plus a couple of inline field checks is proportionate to three entities and two field-level rules, not a system)

Status:

Accepted

# Decision 042

Ownership-based denial always returns 403, never 404, for a resource that genuinely exists but belongs to someone else. A resource that truly doesn't exist still returns 404. This is enforced by construction, not by convention: every fetch-then-authorize dependency calls the service's existing `get_owner`/`get_apartment`/`get_booking` (which raises the real `NotFoundError` first) *before* comparing ownership.

Reason:

- Requirement 5 explicitly forbids using 404 to hide a resource's existence from someone who isn't allowed to see it
- Because the check is structural (fetch first, authorize second, using the exact same "does it exist" logic every other endpoint already relies on) rather than a rule someone has to remember to apply per-endpoint, there's no way for a future endpoint built on `get_authorized_apartment`/`get_authorized_booking`/`get_authorized_owner` to accidentally get this backwards
- Verified directly: `test_authenticated_owner_without_permission_returns_403_not_404` and `test_genuinely_missing_resource_still_returns_404` in `test_authorization.py` assert both halves of this explicitly, not just the happy path

Alternatives:

- Return 404 for both "doesn't exist" and "not yours" (rejected — requirement 5 explicitly forbids this; it's also strictly worse UX for the legitimate owner debugging their own integration)

Status:

Accepted

# Decision 043

All business routers (`owners`, `apartments`, `bookings`, `rate_rules`, `availability`, `payments`, `auth`) are now mounted under `/api/v1`, via `prefix=settings.api_v1_str` on each `app.include_router(...)` call in `main.py` rather than by changing any router's own internal `prefix`. `/health` and `/health/db` stay unversioned, at the root.

Reason:

- `Settings.api_v1_str` has existed since the initial scaffold as a declared-but-unused field — this sprint is the first time anything actually reads it, closing a small piece of dead configuration rather than introducing new config surface
- Right now is the cheapest this will ever be to do: there are no external API consumers yet (the only client is this repo's own Nuxt frontend, updated in the same change), so there's no deprecation window, no dual-routing period, and no coordination with anyone outside this repo. Adding versioning later, once a mobile app or a partner integration depends on unversioned paths, would mean either breaking them or running two route trees side by side
- Applying the prefix at `include_router(...)` time, instead of editing each router's own `prefix=`, keeps every router module honest about its own path structure (`/owners`, `/apartments`, etc.) independent of where it happens to be mounted — `rate_rules` and `payments`, which declare full paths per-endpoint instead of a router-level `prefix`, needed no changes at all
- `/health` and `/health/db` are deliberately excluded: they're infrastructure liveness/readiness checks (read by orchestrators, load balancers, uptime monitors), not business API surface. Versioning them would force every external monitor to know about and track API version bumps for a check that has nothing to do with the business API's contract — the standard convention (Kubernetes, most cloud load balancers) is an unversioned, stable healthcheck path

Alternatives:

- Version `/health`/`/health/db` too, for consistency with every other route (rejected — infrastructure tooling that polls a healthcheck shouldn't need to change its target when the business API's version bumps to v2; keeping it stable is the point)
- Set each router's own `prefix` to include `/api/v1` directly instead of passing `prefix=` to `include_router` (rejected — would leave the version baked into every router module instead of in the one place, `main.py`, that actually decides how the app is mounted; also wouldn't have worked uniformly, since `rate_rules` and `payments` don't have a router-level `prefix` to edit)

Status:

Accepted
