"""카메라 디지털 트윈 장면 설정 테이블 추가

Revision ID: 20260730_04
Revises: 20260728_03
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260730_04"
down_revision: Union[str, Sequence[str], None] = "20260728_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "camera_scene_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("store_id", sa.String(length=100), nullable=False),
        sa.Column("camera_id", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "coordinate_space",
            sa.String(length=30),
            server_default="normalized_1000",
            nullable=False,
        ),
        sa.Column("image_width", sa.Integer(), nullable=False),
        sa.Column("image_height", sa.Integer(), nullable=False),
        sa.Column("objects", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id",
            "camera_id",
            "version",
            name="uq_camera_scene_configs_store_camera_version",
        ),
    )
    op.create_index(
        "uq_camera_scene_configs_one_approved",
        "camera_scene_configs",
        ["store_id", "camera_id"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_camera_scene_configs_one_approved",
        table_name="camera_scene_configs",
    )
    op.drop_table("camera_scene_configs")
