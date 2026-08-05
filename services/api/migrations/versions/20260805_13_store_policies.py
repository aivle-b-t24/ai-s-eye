"""매장 정책 테이블 생성

Revision ID: 20260805_13
Revises: 20260805_12
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260805_13"
down_revision: Union[str, Sequence[str], None] = "20260805_12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "store_policies",
        sa.Column("policy_id", sa.String(length=36), primary_key=True),
        sa.Column("store_id", sa.String(length=100), nullable=False),
        sa.Column(
            "category",
            sa.String(length=50),
            server_default="general",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
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
    op.create_index(
        "ix_store_policies_store_id",
        "store_policies",
        ["store_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_store_policies_store_id", table_name="store_policies")
    op.drop_table("store_policies")
