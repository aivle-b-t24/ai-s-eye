"""주문 매장별 기간 조회 인덱스 추가

Revision ID: 20260723_02
Revises: 20260721_01
Create Date: 2026-07-23
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260723_02"
down_revision: Union[str, Sequence[str], None] = "20260721_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """매장과 발생 시각을 함께 사용하는 집계 조회를 빠르게 한다."""
    op.create_index(
        "ix_order_events_store_id_occurred_at",
        "order_events",
        ["store_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    """주문 집계 조회용 인덱스를 제거한다."""
    op.drop_index(
        "ix_order_events_store_id_occurred_at",
        table_name="order_events",
    )
