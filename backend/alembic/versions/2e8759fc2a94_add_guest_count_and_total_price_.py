"""add guest_count and total_price positivity checks

Revision ID: 2e8759fc2a94
Revises: 7c4446bc8a36
Create Date: 2026-07-20 17:56:19.917732

Hand-written: like the EXCLUDE constraint in 7c4446bc8a36, autogenerate does
not detect CheckConstraint additions on an existing table.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2e8759fc2a94'
down_revision: Union[str, None] = '7c4446bc8a36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_bookings_guest_count_positive", "bookings", "guest_count > 0"
    )
    op.create_check_constraint(
        "ck_bookings_total_price_positive", "bookings", "total_price > 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_bookings_total_price_positive", "bookings", type_="check")
    op.drop_constraint("ck_bookings_guest_count_positive", "bookings", type_="check")
