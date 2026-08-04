from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


class OrderDataSource(StrEnum):
    SYNTHETIC_ORDER_SIMULATOR = "synthetic_order_simulator"
    ORDER_EVENT = "order_event"


class StoreManagerAccountCreate(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    name: str = Field(min_length=1, max_length=100)
    store_id: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        local, separator, domain = normalized.partition("@")
        if not separator or not local or "." not in domain:
            raise ValueError("유효한 이메일 주소를 입력해 주세요")
        return normalized

    @field_validator("name", "store_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class StoreManagerPasswordUpdate(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class FirebaseUserSummary(BaseModel):
    uid: str
    email: str
    name: str
    role: str | None = None
    store_id: str | None = None
    disabled: bool = False


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
    frame_id: str | None = Field(default=None, min_length=1)
    captured_at: datetime
    processed_at: datetime | None = None
    roi_version: int | None = Field(default=None, ge=1)
    visible_person_count: int = Field(ge=0)
    queue_count_estimate: int = Field(ge=0)
    zone_counts: dict[str, int] = Field(default_factory=dict)
    quality_status: QualityStatus
    source: str = Field(min_length=1)
    model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_analysis_timestamps(self) -> "StoreState":
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must include a timezone")
        if self.processed_at is not None and self.processed_at.tzinfo is None:
            raise ValueError("processed_at must include a timezone")
        return self


# 매장 수용 인원 기본값(설정이 없을 때). 혼잡도 = 현재 인원 / 수용 인원.
DEFAULT_STORE_MAX_CAPACITY = 30


class StoreSettingsInput(BaseModel):
    """설정 페이지에서 저장하는 매장 운영 설정."""

    max_capacity: int = Field(ge=1, le=1000)


class StoreSettings(StoreSettingsInput):
    store_id: str = Field(min_length=1)
    max_capacity: int = Field(default=DEFAULT_STORE_MAX_CAPACITY, ge=1, le=1000)
    updated_at: datetime | None = None


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
    waiting_order_count: int = Field(default=0, ge=0)
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
    data_sources: list[OrderDataSource] = Field(default_factory=list)
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


class StoreListItem(BaseModel):
    store_id: str
    # 매장 표시명은 아직 백엔드에 없다. 소비 측(챗봇 등)에서 채우거나 store_id로 대체한다.
    name: str | None = None


class StoreListResponse(BaseModel):
    stores: list[StoreListItem]


class StoreTimelinePoint(BaseModel):
    start_at: datetime
    end_at: datetime
    observation_count: int = Field(ge=0)
    average_visible_person_count: float | None = Field(default=None, ge=0)
    peak_visible_person_count: int | None = Field(default=None, ge=0)
    average_queue_count_estimate: float | None = Field(default=None, ge=0)
    peak_queue_count_estimate: int | None = Field(default=None, ge=0)
    average_waiting_order_count: float | None = Field(default=None, ge=0)
    peak_waiting_order_count: int | None = Field(default=None, ge=0)
    order_count: int = Field(ge=0)
    quality_issue_count: int = Field(ge=0)


class StoreTimelineResponse(BaseModel):
    schema_version: str = "1.0"
    store_id: str
    interval: str
    period: SummaryPeriod
    points: list[StoreTimelinePoint]


class TwinBoundingBox(BaseModel):
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_corners(self) -> "TwinBoundingBox":
        if self.x2 < self.x1 or self.y2 < self.y1:
            raise ValueError("bbox max coordinates must be greater than min coordinates")
        return self


class TwinAgent(BaseModel):
    id: str | None = None
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    role: TwinAgentRole
    state: TwinAgentState = TwinAgentState.UNKNOWN
    zone: str | None = None
    bbox: TwinBoundingBox | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    occluded: bool | None = None


class TwinFrame(BaseModel):
    schema_version: str = "1.0"
    store_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    frame_id: str | None = Field(default=None, min_length=1)
    mode: TwinMode = TwinMode.LIVE
    captured_at: datetime
    published_at: datetime | None = None
    processed_at: datetime | None = None
    roi_version: int | None = Field(default=None, ge=1)
    source: str | None = Field(default=None, min_length=1)
    model_version: str | None = Field(default=None, min_length=1)
    coordinate_space: Literal["normalized_image"] = "normalized_image"
    tracking_epoch: int | None = Field(default=None, ge=0)
    tracking_reset: bool | None = None
    agents: list[TwinAgent] = Field(default_factory=list)


class VisionSnapshotMetadata(BaseModel):
    schema_version: str = "1.0"
    store_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    frame_id: str = Field(min_length=1)
    captured_at: datetime
    processed_at: datetime
    model_version: str = Field(min_length=1)
    roi_version: int | None = Field(default=None, ge=1)
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_timezone(self) -> "VisionSnapshotMetadata":
        if self.captured_at.tzinfo is None or self.processed_at.tzinfo is None:
            raise ValueError("captured_at and processed_at must include a timezone")
        return self


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


class ScenePerspectiveConfig(BaseModel):
    """카메라 영상 좌표에서 사람 아이콘 크기를 보정하는 2.5D 원근 설정."""

    far_y: int = Field(default=260, ge=0, le=999)
    near_y: int = Field(default=980, ge=1, le=1000)
    far_scale: float = Field(default=0.62, ge=0.35, le=1.0)
    near_scale: float = Field(default=1.35, ge=0.8, le=2.0)

    @model_validator(mode="after")
    def validate_depth_range(self) -> "ScenePerspectiveConfig":
        if self.far_y >= self.near_y:
            raise ValueError("far_y must be smaller than near_y")
        if self.far_scale > self.near_scale:
            raise ValueError("far_scale must not exceed near_scale")
        return self


class SceneSeatAnchor(BaseModel):
    """착석 상태의 화면 표시 위치. 원본 Vision 발 좌표와는 별도로 사용한다."""

    id: str = Field(min_length=1, max_length=100)
    x: int = Field(ge=0, le=1000)
    y: int = Field(ge=0, le=1000)
    table_id: str | None = Field(default=None, max_length=100)


class CameraSceneConfigInput(BaseModel):
    coordinate_space: Literal["normalized_1000"] = "normalized_1000"
    image_size: RoiImageSize
    objects: list[SceneObject] = Field(min_length=1)
    perspective: ScenePerspectiveConfig = Field(
        default_factory=ScenePerspectiveConfig,
    )
    seat_anchors: list[SceneSeatAnchor] = Field(default_factory=list)
    source: SceneConfigSource = SceneConfigSource.MANUAL

    @model_validator(mode="after")
    def validate_unique_object_ids(self) -> "CameraSceneConfigInput":
        object_ids = [item.id for item in self.objects]
        if len(object_ids) != len(set(object_ids)):
            raise ValueError("scene object ids must be unique")
        seat_ids = [item.id for item in self.seat_anchors]
        if len(seat_ids) != len(set(seat_ids)):
            raise ValueError("seat anchor ids must be unique")
        object_id_set = set(object_ids)
        if any(
            seat.table_id is not None and seat.table_id not in object_id_set
            for seat in self.seat_anchors
        ):
            raise ValueError("seat anchor table_id must reference a scene object")
        return self


class CameraSceneConfig(CameraSceneConfigInput):
    store_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    version: int = Field(gt=0)
    status: SceneConfigStatus
    created_at: datetime
    approved_at: datetime | None = None


class OperationsSimulationScenario(BaseModel):
    name: str = Field(default="기본 시나리오", min_length=1, max_length=60)
    store_id: str = Field(default="store-001", min_length=1)
    duration_minutes: int = Field(default=180, ge=30, le=480)
    staff_count: int = Field(default=1, ge=1, le=6)
    arrivals_per_hour: float = Field(default=24, ge=1, le=180)
    event_multiplier: float = Field(default=1, ge=0.5, le=4)
    average_service_minutes: float = Field(default=4, ge=0.5, le=20)
    service_variability: float = Field(default=0.25, ge=0, le=1)
    patience_minutes: float = Field(default=8, ge=1, le=60)
    seat_count: int = Field(default=16, ge=0, le=100)
    dine_in_rate: float = Field(default=0.65, ge=0, le=1)
    seed: int = Field(default=20260730, ge=0, le=2_147_483_647)


class OperationsSimulationMetrics(BaseModel):
    visitors: int = Field(ge=0)
    completed_orders: int = Field(ge=0)
    abandoned_orders: int = Field(ge=0)
    in_progress_orders: int = Field(ge=0)
    average_wait_minutes: float = Field(ge=0)
    max_queue: int = Field(ge=0)
    staff_utilization_percent: float = Field(ge=0, le=100)
    seat_utilization_percent: float = Field(ge=0, le=100)


class OperationsSimulationFrame(BaseModel):
    at_minute: float = Field(ge=0)
    queue_count: int = Field(ge=0)
    in_service_count: int = Field(ge=0)
    seated_count: int = Field(ge=0)
    completed_orders: int = Field(ge=0)
    abandoned_orders: int = Field(ge=0)
    agents: list[TwinAgent] = Field(default_factory=list)


class OperationsSimulationResult(BaseModel):
    schema_version: str = "1.0"
    source: Literal["simulation"] = "simulation"
    run_id: str = Field(min_length=1)
    generated_at: datetime
    scenario: OperationsSimulationScenario
    metrics: OperationsSimulationMetrics
    frames: list[OperationsSimulationFrame]
    assumptions: list[str]
