from fastapi import APIRouter, Depends, status

from app.api.deps import (
    get_authorized_apartment,
    get_authorized_rate_rule,
    get_rate_rule_service,
)
from app.models.apartment import Apartment
from app.models.rate_rule import RateRule
from app.schemas.rate_rule import RateRuleBase, RateRuleCreate, RateRuleRead, RateRuleUpdate
from app.services.rate_rule import RateRuleService

router = APIRouter(tags=["rate-rules"])


@router.post(
    "/apartments/{apartment_id}/rate-rules",
    response_model=RateRuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_rate_rule(
    data: RateRuleBase,
    apartment: Apartment = Depends(get_authorized_apartment),
    service: RateRuleService = Depends(get_rate_rule_service),
) -> RateRule:
    """Create a rate rule for an apartment. The request body has no
    apartment_id of its own (RateRuleBase, not RateRuleCreate) — it always
    comes from the URL, which is also what authorization is checked against,
    so a caller can never authorize against one apartment and create the
    rule under another. 409 if the date range overlaps an existing rule for
    this apartment, 422 if end_date is before start_date."""
    return await service.create_rate_rule(
        RateRuleCreate(apartment_id=apartment.id, **data.model_dump())
    )


@router.get("/apartments/{apartment_id}/rate-rules", response_model=list[RateRuleRead])
async def list_rate_rules(
    apartment: Apartment = Depends(get_authorized_apartment),
    service: RateRuleService = Depends(get_rate_rule_service),
) -> list[RateRule]:
    """List rate rules for an apartment. Same ownership rule as create."""
    return await service.list_rate_rules_by_apartment(apartment.id)


@router.patch("/rate-rules/{rate_rule_id}", response_model=RateRuleRead)
async def update_rate_rule(
    data: RateRuleUpdate,
    rate_rule: RateRule = Depends(get_authorized_rate_rule),
    service: RateRuleService = Depends(get_rate_rule_service),
) -> RateRule:
    """Partially update a rate rule. 404 if it doesn't exist, 403 if it
    exists but isn't the caller's, 409 if the new range overlaps another
    rule for the same apartment."""
    return await service.update_rate_rule(rate_rule.id, data)


@router.delete("/rate-rules/{rate_rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rate_rule(
    rate_rule: RateRule = Depends(get_authorized_rate_rule),
    service: RateRuleService = Depends(get_rate_rule_service),
) -> None:
    """Hard-delete a rate rule — unlike apartments/owners, a rate rule has no
    history to preserve once nothing has priced against it. 409 if a
    confirmed booking's stay falls inside its date range."""
    await service.delete_rate_rule(rate_rule.id)
