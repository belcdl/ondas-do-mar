"""add booking overlap exclusion constraint

Revision ID: 7c4446bc8a36
Revises: 71df480aa928
Create Date: 2026-07-17 13:21:31.795804

Hand-written: alembic --autogenerate does not detect PostgreSQL EXCLUDE
constraints, so this migration is written directly rather than generated.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7c4446bc8a36'
down_revision: Union[str, None] = '71df480aa928'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # btree_gist lets a plain equality column (apartment_id) participate in a
    # GiST index alongside a range-overlap operator, which is what the
    # exclusion constraint below needs.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE bookings
        ADD CONSTRAINT ex_bookings_no_overlap_confirmed
        EXCLUDE USING gist (
            apartment_id WITH =,
            daterange(check_in_date, check_out_date, '[)') WITH &&
        )
        WHERE (status = 'confirmed')
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT ex_bookings_no_overlap_confirmed")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
