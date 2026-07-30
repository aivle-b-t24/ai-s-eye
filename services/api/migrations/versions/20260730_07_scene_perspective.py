"""장면 원근 보정과 좌석 앵커 추가

Revision ID: 20260730_07
Revises: 20260730_06
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260730_07"
down_revision: Union[str, Sequence[str], None] = "20260730_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "camera_scene_configs",
        sa.Column(
            "perspective",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(
                "jsonb_build_object('far_y', 260, 'near_y', 980, "
                "'far_scale', 0.62, 'near_scale', 1.35)"
            ),
            nullable=False,
        ),
    )
    op.add_column(
        "camera_scene_configs",
        sa.Column(
            "seat_anchors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("camera_scene_configs", "seat_anchors")
    op.drop_column("camera_scene_configs", "perspective")
