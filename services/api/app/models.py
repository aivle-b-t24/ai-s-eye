from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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


class TwinMode(StrEnum):
    LIVE = "live"


class TwinAgentRole(StrEnum):
    CUSTOMER = "customer"
    STAFF = "staff"


class TwinAgentState(StrEnum):
    ENTERING = "entering"
    QUEUE = "queue"
    ORDERING = "ordering"
    WAITING = "waiting"
    SEATED = "seated"
    EXITING = "exiting"
    WORKING = "working"
    UNKNOWN = "unknown"


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


class TwinAgent(BaseModel):
    id: str | None = None
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    role: TwinAgentRole
    state: TwinAgentState = TwinAgentState.UNKNOWN
    zone: str | None = None


class TwinFrame(BaseModel):
    schema_version: str = "1.0"
    store_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    mode: TwinMode = TwinMode.LIVE
    captured_at: datetime
    coordinate_space: Literal["normalized_image"] = "normalized_image"
    agents: list[TwinAgent] = Field(default_factory=list)


class RoiZoneType(StrEnum):
    STAFF = "staff"
    WAITING = "waiting"
    ENTRANCE = "entrance"
    SEATING = "seating"


class RoiConfigSource(StrEnum):
    MANUAL = "manual"
    AI_ASSISTED = "ai_assisted"


class RoiConfigStatus(StrEnum):
    APPROVED = "approved"
    ARCHIVED = "archived"


class RoiPoint(BaseModel):
    x: int = Field(ge=0, le=1000)
    y: int = Field(ge=0, le=1000)


class RoiImageSize(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


def _orientation(a: RoiPoint, b: RoiPoint, c: RoiPoint) -> int:
    value = (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y)
    if value == 0:
        return 0
    return 1 if value > 0 else 2


def _on_segment(a: RoiPoint, b: RoiPoint, c: RoiPoint) -> bool:
    return (
        min(a.x, c.x) <= b.x <= max(a.x, c.x)
        and min(a.y, c.y) <= b.y <= max(a.y, c.y)
    )


def _segments_intersect(
    a: RoiPoint,
    b: RoiPoint,
    c: RoiPoint,
    d: RoiPoint,
) -> bool:
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and _on_segment(a, c, b))
        or (o2 == 0 and _on_segment(a, d, b))
        or (o3 == 0 and _on_segment(c, a, d))
        or (o4 == 0 and _on_segment(c, b, d))
    )


def _validate_polygon_points(points: list[RoiPoint]) -> None:
    if len({(point.x, point.y) for point in points}) != len(points):
        raise ValueError("polygon points must be unique")

    twice_area = abs(
        sum(
            point.x * points[(index + 1) % len(points)].y
            - points[(index + 1) % len(points)].x * point.y
            for index, point in enumerate(points)
        )
    )
    if twice_area == 0:
        raise ValueError("polygon must have a non-zero area")

    edge_count = len(points)
    for first in range(edge_count):
        a = points[first]
        b = points[(first + 1) % edge_count]
        for second in range(first + 1, edge_count):
            if second in {first, (first + 1) % edge_count}:
                continue
            if first == 0 and second == edge_count - 1:
                continue
            c = points[second]
            d = points[(second + 1) % edge_count]
            if _segments_intersect(a, b, c, d):
                raise ValueError("polygon edges must not intersect")


class RoiZone(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    type: RoiZoneType
    label: str = Field(min_length=1, max_length=100)
    polygon: list[RoiPoint] = Field(min_length=3, max_length=20)

    @model_validator(mode="after")
    def validate_polygon(self) -> "RoiZone":
        _validate_polygon_points(self.polygon)
        return self


class CameraRoiConfigInput(BaseModel):
    coordinate_space: Literal["normalized_1000"] = "normalized_1000"
    image_size: RoiImageSize
    zones: list[RoiZone] = Field(min_length=1)
    source: RoiConfigSource = RoiConfigSource.MANUAL

    @model_validator(mode="after")
    def validate_unique_zone_ids(self) -> "CameraRoiConfigInput":
        zone_ids = [zone.id for zone in self.zones]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("zone ids must be unique")
        return self


class CameraRoiConfig(CameraRoiConfigInput):
    store_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    version: int = Field(gt=0)
    status: RoiConfigStatus
    created_at: datetime
    approved_at: datetime | None = None


class SceneObjectType(StrEnum):
    FLOOR = "floor"
    WALL = "wall"
    TABLE = "table"
    COUNTER = "counter"
    ENTRANCE = "entrance"
    OCCLUDER = "occluder"


class SceneConfigSource(StrEnum):
    MANUAL = "manual"
    DEFAULT_IMPORT = "default_import"


class SceneConfigStatus(StrEnum):
    APPROVED = "approved"
    ARCHIVED = "archived"


class SceneObject(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    type: SceneObjectType
    label: str = Field(default="", max_length=100)
    polygon: list[RoiPoint] = Field(min_length=3, max_length=20)

    @model_validator(mode="after")
    def validate_polygon(self) -> "SceneObject":
        _validate_polygon_points(self.polygon)
        return self


class CameraSceneConfigInput(BaseModel):
    coordinate_space: Literal["normalized_1000"] = "normalized_1000"
    image_size: RoiImageSize
    objects: list[SceneObject] = Field(min_length=1)
    source: SceneConfigSource = SceneConfigSource.MANUAL

    @model_validator(mode="after")
    def validate_unique_object_ids(self) -> "CameraSceneConfigInput":
        object_ids = [item.id for item in self.objects]
        if len(object_ids) != len(set(object_ids)):
            raise ValueError("scene object ids must be unique")
        return self


class CameraSceneConfig(CameraSceneConfigInput):
    store_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    version: int = Field(gt=0)
    status: SceneConfigStatus
    created_at: datetime
    approved_at: datetime | None = None
