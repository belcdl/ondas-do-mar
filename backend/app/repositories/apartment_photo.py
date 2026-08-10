import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.apartment_photo import ApartmentPhoto


class ApartmentPhotoRepository:
    """Database access for ApartmentPhoto. No business rules live here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, photo: ApartmentPhoto) -> ApartmentPhoto:
        self.db.add(photo)
        await self.db.commit()
        await self.db.refresh(photo)
        return photo

    async def get_by_id(self, photo_id: uuid.UUID) -> ApartmentPhoto | None:
        return await self.db.get(ApartmentPhoto, photo_id)

    async def list_by_apartment(self, apartment_id: uuid.UUID) -> Sequence[ApartmentPhoto]:
        stmt = (
            select(ApartmentPhoto)
            .where(ApartmentPhoto.apartment_id == apartment_id)
            .order_by(ApartmentPhoto.position)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def delete(self, photo: ApartmentPhoto) -> None:
        await self.db.delete(photo)
        await self.db.commit()

    async def count_by_apartment(self, apartment_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(ApartmentPhoto).where(
            ApartmentPhoto.apartment_id == apartment_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()
