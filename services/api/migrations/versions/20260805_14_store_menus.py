"""매장 메뉴 테이블 생성

Revision ID: 20260805_14
Revises: 20260805_13
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260805_14"
down_revision: Union[str, Sequence[str], None] = "20260805_13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.create_table(
            "store_menus",
            sa.Column("menu_id", sa.String(length=36), primary_key=True),
            sa.Column("store_id", sa.String(length=100), nullable=False),
            sa.Column(
                "category",
                sa.String(length=50),
                server_default="coffee",
                nullable=False,
            ),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("price", sa.Integer(), server_default="0", nullable=False),
            sa.Column(
                "prep_minutes",
                sa.Integer(),
                server_default="3",
                nullable=False,
            ),
            sa.Column(
                "available",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.Column(
                "sold_out_reason",
                sa.String(length=255),
                nullable=True,
            ),
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
        )
    except Exception:
        pass

    try:
        op.create_index(
            "ix_store_menus_store_id",
            "store_menus",
            ["store_id"],
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_index("ix_store_menus_store_id", table_name="store_menus")
    except Exception:
        pass
    try:
        op.drop_table("store_menus")
    except Exception:
        pass
