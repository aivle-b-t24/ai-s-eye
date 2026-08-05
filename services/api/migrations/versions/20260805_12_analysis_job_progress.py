"""AnalysisJob 진행률 컬럼 추가

Revision ID: 20260805_12
Revises: 20260804_11
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260805_12"
down_revision: Union[str, Sequence[str], None] = "20260804_11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_jobs",
        sa.Column(
            "progress_percent",
            sa.Float(),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
    )
    op.add_column(
        "analysis_jobs",
        sa.Column("processed_frames", sa.Integer(), nullable=True),
    )
    op.add_column(
        "analysis_jobs",
        sa.Column("total_frames", sa.Integer(), nullable=True),
    )
    op.add_column(
        "analysis_jobs",
        sa.Column("stage_message", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_jobs", "stage_message")
    op.drop_column("analysis_jobs", "total_frames")
    op.drop_column("analysis_jobs", "processed_frames")
    op.drop_column("analysis_jobs", "progress_percent")
