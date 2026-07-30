"""매장 상태 최신본·샘플 이력·시간 집계 구조 추가.

Revision ID: 20260730_05
Revises: 20260730_04
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260730_05"
down_revision: str | Sequence[str] | None = "20260730_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "store_states",
        sa.Column("frame_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "store_states",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "store_states",
        sa.Column("roi_version", sa.Integer(), nullable=True),
    )
    op.create_index(
        "uq_store_states_source_frame",
        "store_states",
        ["store_id", "camera_id", "source", "frame_id"],
        unique=True,
        postgresql_where=sa.text("frame_id IS NOT NULL"),
    )

    op.create_table(
        "current_store_states",
        sa.Column("store_id", sa.String(length=100), nullable=False),
        sa.Column("camera_id", sa.String(length=200), nullable=False),
        sa.Column("frame_id", sa.String(length=200), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("roi_version", sa.Integer(), nullable=True),
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
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("store_id", "camera_id"),
    )

    op.create_table(
        "store_state_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("store_id", sa.String(length=100), nullable=False),
        sa.Column("camera_id", sa.String(length=200), nullable=False),
        sa.Column("bucket_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frame_id", sa.String(length=200), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("roi_version", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint(
            "store_id",
            "camera_id",
            "bucket_at",
            name="uq_store_state_history_store_camera_bucket",
        ),
    )
    op.create_index(
        "ix_store_state_history_store_id_bucket_at",
        "store_state_history",
        ["store_id", "bucket_at"],
    )

    op.create_table(
        "hourly_store_metrics",
        sa.Column("store_id", sa.String(length=100), nullable=False),
        sa.Column("camera_id", sa.String(length=200), nullable=False),
        sa.Column("bucket_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("visible_person_sum", sa.Integer(), nullable=False),
        sa.Column("queue_count_sum", sa.Integer(), nullable=False),
        sa.Column("peak_visible_person_count", sa.Integer(), nullable=False),
        sa.Column(
            "peak_visible_person_count_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("peak_queue_count_estimate", sa.Integer(), nullable=False),
        sa.Column(
            "peak_queue_count_estimate_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("quality_issue_count", sa.Integer(), nullable=False),
        sa.Column("latest_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_visible_person_count", sa.Integer(), nullable=False),
        sa.Column("latest_queue_count_estimate", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("store_id", "camera_id", "bucket_at"),
    )
    op.create_index(
        "ix_hourly_store_metrics_store_id_bucket_at",
        "hourly_store_metrics",
        ["store_id", "bucket_at"],
    )

    op.execute(
        """
        INSERT INTO current_store_states (
            store_id, camera_id, frame_id, captured_at, processed_at, roi_version,
            visible_person_count, queue_count_estimate, zone_counts,
            quality_status, source, model_version
        )
        SELECT DISTINCT ON (store_id, camera_id)
            store_id, camera_id, frame_id, captured_at, processed_at, roi_version,
            visible_person_count, queue_count_estimate, zone_counts,
            quality_status, source, model_version
        FROM store_states
        ORDER BY store_id, camera_id, captured_at DESC, id DESC
        """
    )
    op.execute(
        """
        INSERT INTO store_state_history (
            store_id, camera_id, bucket_at, frame_id, captured_at, processed_at,
            roi_version, visible_person_count, queue_count_estimate, zone_counts,
            quality_status, source, model_version
        )
        SELECT DISTINCT ON (store_id, camera_id, bucket_at)
            store_id, camera_id, bucket_at, frame_id, captured_at, processed_at,
            roi_version, visible_person_count, queue_count_estimate, zone_counts,
            quality_status, source, model_version
        FROM (
            SELECT
                store_states.*,
                date_bin(
                    INTERVAL '30 seconds',
                    captured_at,
                    TIMESTAMPTZ '1970-01-01 00:00:00+00'
                ) AS bucket_at
            FROM store_states
        ) sampled
        ORDER BY store_id, camera_id, bucket_at, captured_at DESC, id DESC
        """
    )
    op.execute(
        """
        WITH bucketed AS (
            SELECT
                store_states.*,
                date_trunc('hour', captured_at) AS bucket_at
            FROM store_states
        )
        INSERT INTO hourly_store_metrics (
            store_id, camera_id, bucket_at, observation_count,
            visible_person_sum, queue_count_sum,
            peak_visible_person_count, peak_visible_person_count_at,
            peak_queue_count_estimate, peak_queue_count_estimate_at,
            quality_issue_count, latest_captured_at,
            latest_visible_person_count, latest_queue_count_estimate
        )
        SELECT
            store_id,
            camera_id,
            bucket_at,
            COUNT(*)::integer,
            SUM(visible_person_count)::integer,
            SUM(queue_count_estimate)::integer,
            MAX(visible_person_count),
            (ARRAY_AGG(
                captured_at
                ORDER BY visible_person_count DESC, captured_at DESC, id DESC
            ))[1],
            MAX(queue_count_estimate),
            (ARRAY_AGG(
                captured_at
                ORDER BY queue_count_estimate DESC, captured_at DESC, id DESC
            ))[1],
            COUNT(*) FILTER (WHERE quality_status <> 'normal')::integer,
            MAX(captured_at),
            (ARRAY_AGG(
                visible_person_count
                ORDER BY captured_at DESC, id DESC
            ))[1],
            (ARRAY_AGG(
                queue_count_estimate
                ORDER BY captured_at DESC, id DESC
            ))[1]
        FROM bucketed
        GROUP BY store_id, camera_id, bucket_at
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_hourly_store_metrics_store_id_bucket_at",
        table_name="hourly_store_metrics",
    )
    op.drop_table("hourly_store_metrics")
    op.drop_index(
        "ix_store_state_history_store_id_bucket_at",
        table_name="store_state_history",
    )
    op.drop_table("store_state_history")
    op.drop_table("current_store_states")
    op.drop_index(
        "uq_store_states_source_frame",
        table_name="store_states",
    )
    op.drop_column("store_states", "roi_version")
    op.drop_column("store_states", "processed_at")
    op.drop_column("store_states", "frame_id")
