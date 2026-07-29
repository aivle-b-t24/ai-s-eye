"""PostgreSQL에 저장하는 매장 상태와 주문 이벤트 테이블 구조.

Pydantic API 모델과 구분하기 위해 DB 모델 이름에는 Record 접미사를 사용한다.
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class StoreStateRecord(Base):
    """Vision이 측정한 매장 상태 이력."""

    __tablename__ = "store_states"
    __table_args__ = (
        sa.Index("ix_store_states_store_id_captured_at", "store_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    camera_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    visible_person_count: Mapped[int] = mapped_column(nullable=False)
    queue_count_estimate: Mapped[int] = mapped_column(nullable=False)
    zone_counts: Mapped[dict[str, int]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    quality_status: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    source: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


class OrderEventRecord(Base):
    """POS/KDS에서 들어오는 주문 상태 변경 이벤트."""

    __tablename__ = "order_events"
    __table_args__ = (
        sa.Index("ix_order_events_order_id_occurred_at", "order_id", "occurred_at"),
        sa.Index("ix_order_events_store_id_occurred_at", "store_id", "occurred_at"),
    )

    event_id: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    order_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    store_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    items: Mapped[list["OrderItemRecord"]] = relationship(
        back_populates="order_event",
        cascade="all, delete-orphan",
    )


class OrderItemRecord(Base):
    """주문 이벤트에 포함된 메뉴와 수량."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        sa.String(100),
        sa.ForeignKey("order_events.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    menu_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    name: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    quantity: Mapped[int] = mapped_column(nullable=False)

    order_event: Mapped[OrderEventRecord] = relationship(back_populates="items")


class CameraRoiConfigRecord(Base):
    """매장·카메라별 ROI 설정 버전."""

    __tablename__ = "camera_roi_configs"
    __table_args__ = (
        sa.UniqueConstraint(
            "store_id",
            "camera_id",
            "version",
            name="uq_camera_roi_configs_store_camera_version",
        ),
        sa.Index(
            "uq_camera_roi_configs_one_approved",
            "store_id",
            "camera_id",
            unique=True,
            postgresql_where=sa.text("status = 'approved'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    camera_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    coordinate_space: Mapped[str] = mapped_column(
        sa.String(30),
        nullable=False,
        server_default="normalized_1000",
    )
    image_width: Mapped[int] = mapped_column(nullable=False)
    image_height: Mapped[int] = mapped_column(nullable=False)
    zones: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
