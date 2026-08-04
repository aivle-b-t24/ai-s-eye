"""매장 운영 설정(수용 인원) 테이블 추가

Revision ID: 20260730_08
Revises: 20260730_07
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260730_08"
down_revision: Union[str, Sequence[str], None] = "20260730_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "store_settings",
        sa.Column("store_id", sa.String(length=100), primary_key=True),
        sa.Column("max_capacity", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("store_settings")
