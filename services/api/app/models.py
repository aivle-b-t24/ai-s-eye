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

