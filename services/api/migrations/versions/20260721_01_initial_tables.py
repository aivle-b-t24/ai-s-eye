"""초기 테이블 생성

Revision ID: 20260721_01
Revises:
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260721_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Vision 상태와 주문 이벤트를 저장하는 초기 테이블을 만든다."""
    op.create_table(
        "store_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("store_id", sa.String(length=100), nullable=False),
        sa.Column("camera_id", sa.String(length=200), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visible_person_count", sa.Integer(), nullable=False),
        sa.Column("queue_count_estimate", sa.Integer(), nullable=False),
        sa.Column(
            "zone_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("quality_status", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_store_states_store_id_captured_at",
        "store_states",
        ["store_id", "captured_at"],
        unique=False,
    )

    op.create_table(
        "order_events",
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("order_id", sa.String(length=100), nullable=False),
        sa.Column("store_id", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_order_events_order_id_occurred_at",
        "order_events",
        ["order_id", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("menu_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["order_events.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """외래키 의존성의 역순으로 초기 테이블을 제거한다."""
    op.drop_table("order_items")
    op.drop_index("ix_order_events_order_id_occurred_at", table_name="order_events")
    op.drop_table("order_events")
    op.drop_index("ix_store_states_store_id_captured_at", table_name="store_states")
    op.drop_table("store_states")
