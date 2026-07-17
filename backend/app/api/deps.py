from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.apartment import ApartmentRepository
from app.repositories.owner import OwnerRepository
from app.services.apartment import ApartmentService
from app.services.owner import OwnerService


def get_owner_repository(db: AsyncSession = Depends(get_db)) -> OwnerRepository:
    return OwnerRepository(db)


def get_owner_service(
    repository: OwnerRepository = Depends(get_owner_repository),
) -> OwnerService:
    return OwnerService(repository)


def get_apartment_repository(db: AsyncSession = Depends(get_db)) -> ApartmentRepository:
    return ApartmentRepository(db)


def get_apartment_service(
    repository: ApartmentRepository = Depends(get_apartment_repository),
    owner_repository: OwnerRepository = Depends(get_owner_repository),
) -> ApartmentService:
    return ApartmentService(repository, owner_repository)
