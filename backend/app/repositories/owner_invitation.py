from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.owner_invitation import OwnerInvitation


class OwnerInvitationRepository:
    """Database access for OwnerInvitation. No business rules live here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, invitation: OwnerInvitation) -> OwnerInvitation:
        self.db.add(invitation)
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(invitation)
        return invitation

    async def get_by_token_hash(self, token_hash: str) -> OwnerInvitation | None:
        result = await self.db.execute(
            select(OwnerInvitation).where(OwnerInvitation.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, invitation: OwnerInvitation, *, commit: bool = True) -> OwnerInvitation:
        """commit=False stages the change (flush only) without ending the
        transaction — used by OwnerService.accept_invitation, which commits
        once at the end across three repositories so the whole operation is
        atomic. Every other caller keeps the default and behaves exactly as
        every other repository's write methods do."""
        try:
            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(invitation)
        return invitation
