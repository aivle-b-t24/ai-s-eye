"""매장 업로드 미디어와 분석 job 테이블

Revision ID: 20260804_10
Revises: 20260804_09
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260804_10"
down_revision: Union[str, Sequence[str], None] = "20260804_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "store_media",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("store_id", sa.String(length=100), nullable=False),
        sa.Column("media_type", sa.String(length=30), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_store_media_store_id_created_at",
        "store_media",
        ["store_id", "created_at"],
    )

    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("store_id", sa.String(length=100), nullable=False),
        sa.Column(
            "media_id",
            sa.String(length=36),
            sa.ForeignKey("store_media.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(length=120), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_analysis_jobs_status_created_at",
        "analysis_jobs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_analysis_jobs_store_id_created_at",
        "analysis_jobs",
        ["store_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_jobs_store_id_created_at", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_status_created_at", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_index("ix_store_media_store_id_created_at", table_name="store_media")
    op.drop_table("store_media")
