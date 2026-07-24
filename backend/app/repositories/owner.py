import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.owner import Owner


class OwnerRepository:
    """Database access for Owner. No business rules live here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, owner: Owner) -> Owner:
        self.db.add(owner)
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(owner)
        return owner

    async def get_by_id(self, owner_id: uuid.UUID) -> Owner | None:
        return await self.db.get(Owner, owner_id)

    async def get_by_id_for_update(self, owner_id: uuid.UUID) -> Owner | None:
        """Same as get_by_id but locks the row (SELECT ... FOR UPDATE).

        Used when another entity is about to be created/updated referencing
        this owner, so a concurrent deactivate_owner() can't slip in between
        the "is it active" check and the write — see app.services.owner_guard.
        """
        result = await self.db.execute(select(Owner).where(Owner.id == owner_id).with_for_update())
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Owner | None:
        result = await self.db.execute(select(Owner).where(Owner.email == email))
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: uuid.UUID) -> Owner | None:
        result = await self.db.execute(select(Owner).where(Owner.user_id == user_id))
        return result.scalar_one_or_none()

    async def list_all(self, *, include_inactive: bool = False) -> Sequence[Owner]:
        stmt = select(Owner).order_by(Owner.full_name)
        if not include_inactive:
            stmt = stmt.where(Owner.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update(self, owner: Owner, *, commit: bool = True) -> Owner:
        """commit=False stages the change (flush only) without ending the
        transaction — used by OwnerService.accept_invitation, which commits
        once at the end across three repositories so the whole operation is
        atomic. Every other caller keeps the default and behaves exactly as
        before."""
        try:
            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(owner)
        return owner

    async def commit(self) -> None:
        """Explicit final commit for multi-repository atomic operations (see
        update()'s commit=False) — the transaction itself is shared across
        every repository built from the same request's AsyncSession, so
        committing once here commits everything staged via commit=False on
        any of them."""
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
