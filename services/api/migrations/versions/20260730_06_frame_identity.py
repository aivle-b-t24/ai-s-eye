"""프레임 ID를 출처와 무관한 분석 신원으로 사용.

Revision ID: 20260730_06
Revises: 20260730_05
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260730_06"
down_revision: str | Sequence[str] | None = "20260730_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "uq_store_states_source_frame",
        table_name="store_states",
    )
    op.create_index(
        "uq_store_states_frame",
        "store_states",
        ["store_id", "camera_id", "frame_id"],
        unique=True,
        postgresql_where=sa.text("frame_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_store_states_frame",
        table_name="store_states",
    )
    op.create_index(
        "uq_store_states_source_frame",
        "store_states",
        ["store_id", "camera_id", "source", "frame_id"],
        unique=True,
        postgresql_where=sa.text("frame_id IS NOT NULL"),
    )
