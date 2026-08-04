"""매장 마스터(stores) 테이블 추가

Revision ID: 20260804_09
Revises: 20260730_08
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260804_09"
down_revision: Union[str, Sequence[str], None] = "20260730_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_stores_name"),
    )
    stores = sa.table(
        "stores",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
    )
    op.bulk_insert(
        stores,
        [
            {"id": "store-001", "name": "동명점"},
            {"id": "store-002", "name": "수완점"},
        ],
    )


def downgrade() -> None:
    op.drop_table("stores")
