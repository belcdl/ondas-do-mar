import uuid

from sqlalchemy.exc import DataError, IntegrityError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.ical_source import IcalSource
from app.repositories.ical_source import IcalSourceRepository
from app.schemas.ical_source import IcalSourceCreate, IcalSourceUpdate


class IcalSourceNotFoundError(NotFoundError):
    """Raised when no iCal source exists for the given id."""


class IcalSourceService:
    """Business rules for IcalSource. Delegates all persistence to
    IcalSourceRepository. URL format validation is handled by the
    IcalSourceBase/Update schemas' AnyHttpUrl field, not here."""

    def __init__(self, repository: IcalSourceRepository) -> None:
        self.repository = repository

    async def create_ical_source(self, data: IcalSourceCreate) -> IcalSource:
        ical_source = IcalSource(
            apartment_id=data.apartment_id,
            platform_name=data.platform_name,
            ical_url=str(data.ical_url),
        )
        try:
            return await self.repository.create(ical_source)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise ConflictError("Could not create iCal source") from exc

    async def get_ical_source(self, ical_source_id: uuid.UUID) -> IcalSource:
        ical_source = await self.repository.get_by_id(ical_source_id)
        if ical_source is None:
            raise IcalSourceNotFoundError(f"iCal source {ical_source_id} not found")
        return ical_source

    async def list_ical_sources_by_apartment(self, apartment_id: uuid.UUID) -> list[IcalSource]:
        ical_sources = await self.repository.list_by_apartment(apartment_id)
        return list(ical_sources)

    async def update_ical_source(
        self, ical_source_id: uuid.UUID, data: IcalSourceUpdate
    ) -> IcalSource:
        ical_source = await self.get_ical_source(ical_source_id)

        updates = data.model_dump(exclude_unset=True)
        if updates.get("ical_url") is not None:
            updates["ical_url"] = str(updates["ical_url"])

        for field, value in updates.items():
            setattr(ical_source, field, value)

        try:
            return await self.repository.update(ical_source)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise ConflictError("Could not update iCal source") from exc

    async def delete_ical_source(self, ical_source_id: uuid.UUID) -> None:
        # Deleting a source cascades (FK ondelete=CASCADE) to remove any
        # BlockedDate rows imported from it — no manual cleanup needed here.
        ical_source = await self.get_ical_source(ical_source_id)
        await self.repository.delete(ical_source)
