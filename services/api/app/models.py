from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class QualityStatus(StrEnum):
    NORMAL = "normal"
    LOW = "low"
    STALE = "stale"
    UNKNOWN = "unknown"


class OrderStatus(StrEnum):
    RECEIVED = "received"
    PREPARING = "preparing"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class StoreState(BaseModel):
    schema_version: str = "1.0"
    store_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    captured_at: datetime
    visible_person_count: int = Field(ge=0)
    queue_count_estimate: int = Field(ge=0)
    zone_counts: dict[str, int] = Field(default_factory=dict)
    quality_status: QualityStatus
    source: str = Field(min_length=1)
    model_version: str = Field(min_length=1)


class OrderItem(BaseModel):
    menu_id: str = Field(min_length=1)
    name: str | None = None
    quantity: int = Field(gt=0)


class OrderEvent(BaseModel):
    event_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    occurred_at: datetime
    status: OrderStatus
    items: list[OrderItem] = Field(min_length=1)


class EtaResponse(BaseModel):
    store_id: str
    estimated_wait_minutes: int = Field(ge=0)
    calculation: str
    data_source: str


class SummaryPeriod(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None


class TrafficSummary(BaseModel):
    observation_count: int = Field(ge=0)
    latest_captured_at: datetime
    latest_visible_person_count: int = Field(ge=0)
    latest_queue_count_estimate: int = Field(ge=0)
    average_visible_person_count: float = Field(ge=0)
    average_queue_count_estimate: float = Field(ge=0)
    peak_visible_person_count: int = Field(ge=0)
    peak_visible_person_count_at: datetime
    peak_queue_count_estimate: int = Field(ge=0)
    peak_queue_count_estimate_at: datetime


class OrderStatusCounts(BaseModel):
    received: int = Field(default=0, ge=0)
    preparing: int = Field(default=0, ge=0)
    ready: int = Field(default=0, ge=0)
    completed: int = Field(default=0, ge=0)
    cancelled: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)


class MenuItemSummary(BaseModel):
    menu_id: str
    name: str | None = None
    quantity: int = Field(ge=0)


class OrderSummary(BaseModel):
    total_order_count: int = Field(ge=0)
    order_event_count: int = Field(ge=0)
    latest_status_counts: OrderStatusCounts
    top_menu_items: list[MenuItemSummary]


class VideoSummary(BaseModel):
    latest_quality_status: QualityStatus
    quality_issue_count: int = Field(ge=0)


class StoreOperatingSummary(BaseModel):
    store_id: str
    traffic_summary: TrafficSummary | None
    order_summary: OrderSummary
    video_summary: VideoSummary | None


class StoreSummaryResponse(BaseModel):
    schema_version: str = "1.0"
    generated_at: datetime
    data_source: str
    period: SummaryPeriod
    stores: list[StoreOperatingSummary]


class StoreTimelinePoint(BaseModel):
    start_at: datetime
    end_at: datetime
    observation_count: int = Field(ge=0)
    average_visible_person_count: float | None = Field(default=None, ge=0)
    peak_visible_person_count: int | None = Field(default=None, ge=0)
    average_queue_count_estimate: float | None = Field(default=None, ge=0)
    peak_queue_count_estimate: int | None = Field(default=None, ge=0)
    order_count: int = Field(ge=0)
    quality_issue_count: int = Field(ge=0)


class StoreTimelineResponse(BaseModel):
    schema_version: str = "1.0"
    store_id: str
    interval: str
    period: SummaryPeriod
    points: list[StoreTimelinePoint]
