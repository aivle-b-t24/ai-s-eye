import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
import psycopg
from pydantic import ValidationError

from .config import get_settings
from .db_repository import DatabaseRepository
from .models import (
    CameraRoiConfig,
    CameraRoiConfigInput,
    CameraSceneConfig,
    CameraSceneConfigInput,
    EtaResponse,
    OrderEvent,
    OperationsSimulationResult,
    OperationsSimulationScenario,
    StoreState,
    StoreSummaryResponse,
    StoreTimelineResponse,
    TwinFrame,
    VisionSnapshotMetadata,
)
from .operations_simulation import run_operations_simulation
from .order_export import KST, build_order_export_csv
from .occupancy import LatestOccupancyRepository
from .repository import InMemoryRepository
from .vision_snapshots import (
    InvalidImageError,
    detect_image_media_type,
    load_snapshot_metadata,
    save_snapshot,
    snapshot_path,
)


settings = get_settings()
DEFAULT_SUMMARY_WINDOW = timedelta(hours=24)
MAX_TIMELINE_WINDOW = timedelta(days=31)
repository = (
    DatabaseRepository()
    if settings.database_url
    else InMemoryRepository()
)
occupancy_repository = LatestOccupancyRepository()


def load_json_file(filename: str) -> Any:
    path = settings.sample_data_dir / filename
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Sample data is unavailable: {filename}",
        ) from exc


def preload_sample_state() -> None:
    path: Path = settings.sample_data_dir / "store_state.json"
    if not path.exists():
        return
    with path.open(encoding="utf-8") as file:
        repository.save_store_state(StoreState.model_validate(json.load(file)))


def database_status() -> str:
    if not settings.database_url:
        return "not_configured"
    try:
        with psycopg.connect(settings.database_url, connect_timeout=1) as connection:
            connection.execute("SELECT 1")
        return "ok"
    except psycopg.Error:
        return "unavailable"


def default_summary_period(
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """기간을 생략한 집계 요청에 사용할 최근 24시간 범위를 반환한다."""
    end_at = now or datetime.now(timezone.utc)
    return end_at - DEFAULT_SUMMARY_WINDOW, end_at


def validate_vision_store_id(store_id: str) -> None:
    if store_id not in settings.vision_store_ids:
        raise HTTPException(status_code=404, detail="Store not found")


async def read_snapshot_upload(image: UploadFile) -> bytes:
    content = await image.read(settings.vision_snapshot_max_bytes + 1)
    await image.close()
    if len(content) > settings.vision_snapshot_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image is too large",
        )
    try:
        detect_image_media_type(content)
    except InvalidImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    return content


def parse_snapshot_metadata(
    store_id: str,
    metadata: str | None,
) -> VisionSnapshotMetadata | None:
    if metadata is None:
        return None
    try:
        parsed = VisionSnapshotMetadata.model_validate_json(metadata)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=json.loads(exc.json()),
        ) from exc
    if parsed.store_id != store_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Path store_id and metadata store_id must match",
        )
    return parsed


if isinstance(repository, InMemoryRepository):
    preload_sample_state()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI's Eye 기능 연동을 위한 공통 API",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    db_status = database_status()
    return {
        "status": "ok" if db_status != "unavailable" else "degraded",
        "environment": settings.app_env,
        "database": db_status,
    }


@app.post(
    "/internal/store-states",
    status_code=status.HTTP_201_CREATED,
    tags=["internal"],
)
def save_store_state(state: StoreState) -> dict[str, Any]:
    saved = repository.save_store_state(state)
    return {"saved": True, "state": saved.model_dump(mode="json")}


@app.post(
    "/internal/stores/{store_id}/occupancy",
    status_code=status.HTTP_201_CREATED,
    tags=["internal"],
)
def save_store_occupancy(
    store_id: str,
    frame: TwinFrame,
) -> dict[str, Any]:
    validate_vision_store_id(store_id)
    if frame.store_id != store_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Path store_id and body store_id must match",
        )
    if frame.captured_at.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="captured_at must include a timezone",
        )
    saved = occupancy_repository.save(frame)
    return {
        "saved": True,
        "frame": saved.model_dump(mode="json", exclude_none=True),
    }


@app.post(
    "/internal/order-events",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["internal"],
)
def save_order_event(event: OrderEvent) -> dict[str, Any]:
    saved = repository.save_order_event(event)
    return {"accepted": True, "event": saved.model_dump(mode="json")}


@app.post(
    "/internal/stores/{store_id}/vision-snapshot",
    status_code=status.HTTP_201_CREATED,
    tags=["internal"],
)
async def save_vision_snapshot(
    store_id: str,
    image: UploadFile = File(...),
    metadata: str | None = Form(default=None),
) -> dict[str, Any]:
    validate_vision_store_id(store_id)
    content = await read_snapshot_upload(image)
    media_type = detect_image_media_type(content)
    parsed_metadata = parse_snapshot_metadata(store_id, metadata)
    save_snapshot(
        settings.vision_snapshot_dir,
        store_id,
        content,
        metadata=(
            parsed_metadata.model_dump(mode="json")
            if parsed_metadata is not None
            else None
        ),
    )
    return {
        "saved": True,
        "store_id": store_id,
        "content_type": media_type,
        "size_bytes": len(content),
        "image_url": f"/api/stores/{store_id}/vision/latest",
        "metadata": (
            parsed_metadata.model_dump(mode="json")
            if parsed_metadata is not None
            else None
        ),
    }


@app.post(
    "/internal/stores/{store_id}/vision-raw",
    status_code=status.HTTP_201_CREATED,
    tags=["internal"],
)
async def save_raw_vision_snapshot(
    store_id: str,
    image: UploadFile = File(...),
    metadata: str | None = Form(default=None),
) -> dict[str, Any]:
    """ROI 설정에 사용할 오버레이 없는 원본 CCTV 프레임을 저장한다."""
    validate_vision_store_id(store_id)
    content = await read_snapshot_upload(image)
    media_type = detect_image_media_type(content)
    parsed_metadata = parse_snapshot_metadata(store_id, metadata)
    save_snapshot(
        settings.vision_snapshot_dir,
        store_id,
        content,
        raw=True,
        metadata=(
            parsed_metadata.model_dump(mode="json")
            if parsed_metadata is not None
            else None
        ),
    )
    return {
        "saved": True,
        "store_id": store_id,
        "content_type": media_type,
        "size_bytes": len(content),
        "image_url": f"/api/stores/{store_id}/vision/raw/latest",
        "metadata": (
            parsed_metadata.model_dump(mode="json")
            if parsed_metadata is not None
            else None
        ),
    }


def vision_snapshot_response(store_id: str, *, raw: bool = False) -> FileResponse:
    path = snapshot_path(settings.vision_snapshot_dir, store_id, raw=raw)
    if not path.is_file():
        label = "Raw vision snapshot" if raw else "Vision snapshot"
        raise HTTPException(status_code=404, detail=f"{label} not found")
    try:
        with path.open("rb") as image_file:
            media_type = detect_image_media_type(image_file.read(8))
    except InvalidImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored vision snapshot is invalid",
        ) from exc
    headers = {"Cache-Control": "no-store"}
    metadata = load_snapshot_metadata(
        settings.vision_snapshot_dir,
        store_id,
        raw=raw,
    )
    if metadata is not None:
        header_mapping = {
            "X-Vision-Frame-Id": metadata.get("frame_id"),
            "X-Vision-Captured-At": metadata.get("captured_at"),
            "X-Vision-Processed-At": metadata.get("processed_at"),
            "X-Vision-Model-Version": metadata.get("model_version"),
            "X-Vision-Roi-Version": metadata.get("roi_version"),
            "X-Vision-Source": metadata.get("source"),
        }
        headers.update(
            {
                key: str(value)
                for key, value in header_mapping.items()
                if value is not None
            }
        )
    return FileResponse(
        path,
        media_type=media_type,
        headers=headers,
    )


def get_vision_snapshot_metadata(
    store_id: str,
    *,
    raw: bool = False,
) -> VisionSnapshotMetadata:
    metadata = load_snapshot_metadata(
        settings.vision_snapshot_dir,
        store_id,
        raw=raw,
    )
    if metadata is None:
        raise HTTPException(status_code=404, detail="Vision metadata not found")
    return VisionSnapshotMetadata.model_validate(metadata)


@app.get(
    "/api/stores/{store_id}/vision/latest",
    response_class=FileResponse,
    tags=["stores"],
)
def get_latest_vision_snapshot(store_id: str) -> FileResponse:
    validate_vision_store_id(store_id)
    return vision_snapshot_response(store_id)


@app.get(
    "/api/stores/{store_id}/vision/raw/latest",
    response_class=FileResponse,
    tags=["stores"],
)
def get_latest_raw_vision_snapshot(store_id: str) -> FileResponse:
    """ROI 설정용 원본 CCTV 프레임을 반환한다."""
    validate_vision_store_id(store_id)
    return vision_snapshot_response(store_id, raw=True)


@app.get(
    "/api/stores/{store_id}/vision/metadata",
    response_model=VisionSnapshotMetadata,
    tags=["stores"],
)
def get_latest_vision_metadata(store_id: str) -> VisionSnapshotMetadata:
    validate_vision_store_id(store_id)
    return get_vision_snapshot_metadata(store_id)


@app.get(
    "/api/stores/{store_id}/vision/raw/metadata",
    response_model=VisionSnapshotMetadata,
    tags=["stores"],
)
def get_latest_raw_vision_metadata(store_id: str) -> VisionSnapshotMetadata:
    validate_vision_store_id(store_id)
    return get_vision_snapshot_metadata(store_id, raw=True)


@app.get(
    "/api/stores/{store_id}/occupancy/latest",
    response_model=TwinFrame,
    response_model_exclude_none=True,
    tags=["stores"],
)
def get_latest_store_occupancy(store_id: str) -> TwinFrame:
    validate_vision_store_id(store_id)
    frame = occupancy_repository.get(store_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="Occupancy not found")
    return frame


@app.get(
    "/api/stores/{store_id}/cameras/{camera_id}/roi-config",
    response_model=CameraRoiConfig,
    tags=["roi"],
)
def get_camera_roi_config(store_id: str, camera_id: str) -> CameraRoiConfig:
    validate_vision_store_id(store_id)
    config = repository.get_approved_roi_config(store_id, camera_id)
    if config is None:
        raise HTTPException(status_code=404, detail="ROI config not found")
    return config


@app.put(
    "/api/stores/{store_id}/cameras/{camera_id}/roi-config",
    response_model=CameraRoiConfig,
    tags=["roi"],
)
def save_camera_roi_config(
    store_id: str,
    camera_id: str,
    config: CameraRoiConfigInput,
) -> CameraRoiConfig:
    validate_vision_store_id(store_id)
    return repository.save_roi_config(store_id, camera_id, config)


@app.get(
    "/api/stores/{store_id}/cameras/{camera_id}/roi-configs",
    response_model=list[CameraRoiConfig],
    tags=["roi"],
)
def list_camera_roi_configs(
    store_id: str,
    camera_id: str,
) -> list[CameraRoiConfig]:
    validate_vision_store_id(store_id)
    return repository.list_roi_configs(store_id, camera_id)


@app.post(
    "/api/stores/{store_id}/cameras/{camera_id}/roi-configs/{version}/approve",
    response_model=CameraRoiConfig,
    tags=["roi"],
)
def approve_camera_roi_config(
    store_id: str,
    camera_id: str,
    version: int,
) -> CameraRoiConfig:
    validate_vision_store_id(store_id)
    config = repository.approve_roi_config(store_id, camera_id, version)
    if config is None:
        raise HTTPException(status_code=404, detail="ROI config version not found")
    return config


@app.get(
    "/internal/stores/{store_id}/cameras/{camera_id}/roi-config",
    response_model=CameraRoiConfig,
    tags=["internal"],
)
def get_internal_camera_roi_config(
    store_id: str,
    camera_id: str,
) -> CameraRoiConfig:
    validate_vision_store_id(store_id)
    config = repository.get_approved_roi_config(store_id, camera_id)
    if config is None:
        raise HTTPException(status_code=404, detail="ROI config not found")
    return config


@app.get(
    "/api/stores/{store_id}/cameras/{camera_id}/scene-config",
    response_model=CameraSceneConfig,
    tags=["scene"],
)
def get_camera_scene_config(store_id: str, camera_id: str) -> CameraSceneConfig:
    validate_vision_store_id(store_id)
    config = repository.get_approved_scene_config(store_id, camera_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Scene config not found")
    return config


@app.put(
    "/api/stores/{store_id}/cameras/{camera_id}/scene-config",
    response_model=CameraSceneConfig,
    tags=["scene"],
)
def save_camera_scene_config(
    store_id: str,
    camera_id: str,
    config: CameraSceneConfigInput,
) -> CameraSceneConfig:
    validate_vision_store_id(store_id)
    return repository.save_scene_config(store_id, camera_id, config)


@app.get(
    "/api/stores/{store_id}/cameras/{camera_id}/scene-configs",
    response_model=list[CameraSceneConfig],
    tags=["scene"],
)
def list_camera_scene_configs(
    store_id: str,
    camera_id: str,
) -> list[CameraSceneConfig]:
    validate_vision_store_id(store_id)
    return repository.list_scene_configs(store_id, camera_id)


@app.post(
    "/api/stores/{store_id}/cameras/{camera_id}/scene-configs/{version}/approve",
    response_model=CameraSceneConfig,
    tags=["scene"],
)
def approve_camera_scene_config(
    store_id: str,
    camera_id: str,
    version: int,
) -> CameraSceneConfig:
    validate_vision_store_id(store_id)
    config = repository.approve_scene_config(store_id, camera_id, version)
    if config is None:
        raise HTTPException(status_code=404, detail="Scene config version not found")
    return config


@app.get(
    "/api/orders/{order_id}",
    response_model=OrderEvent,
    tags=["orders"],
)
def get_order_status(order_id: str) -> OrderEvent:
    event = repository.get_latest_order_event(order_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return event


@app.get(
    "/api/exports/orders.csv",
    response_class=Response,
    tags=["orders"],
)
def export_orders_csv(
    start_at: datetime,
    end_at: datetime,
    store_id: str | None = None,
) -> Response:
    """기간 내 주문을 주문 한 건당 한 행인 CSV 파일로 내려준다."""
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_at and end_at must include a timezone",
        )
    if start_at >= end_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_at must be earlier than end_at",
        )
    if end_at - start_at > MAX_TIMELINE_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="order export period must not exceed 31 days",
        )
    if store_id is not None:
        validate_vision_store_id(store_id)

    events = repository.list_order_events(
        start_at=start_at,
        end_at=end_at,
        store_id=store_id,
    )
    content = build_order_export_csv(events).encode("utf-8")
    start_label = start_at.astimezone(KST).date().isoformat()
    end_label = (end_at - timedelta(microseconds=1)).astimezone(
        KST
    ).date().isoformat()
    filename = f"orders_{start_label}_{end_label}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.post(
    "/api/simulations/operations",
    response_model=OperationsSimulationResult,
    tags=["simulations"],
)
def simulate_operations(
    scenario: OperationsSimulationScenario,
) -> OperationsSimulationResult:
    """DB를 변경하지 않고 한 개 운영 조건의 What-if 결과를 계산한다."""
    validate_vision_store_id(scenario.store_id)
    return run_operations_simulation(scenario)


@app.get(
    "/api/stores/{store_id}/orders/{order_id}",
    response_model=OrderEvent,
    tags=["orders"],
)
def get_store_order_status(store_id: str, order_id: str) -> OrderEvent:
    event = repository.get_latest_store_order_event(store_id, order_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return event


@app.get(
    "/api/stores/summary",
    response_model=StoreSummaryResponse,
    tags=["stores"],
)
def get_stores_summary(
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> StoreSummaryResponse:
    if start_at is None and end_at is None:
        start_at, end_at = default_summary_period()
    if (start_at is None) != (end_at is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_at and end_at must be provided together",
        )
    if start_at is not None and end_at is not None:
        if start_at.tzinfo is None or end_at.tzinfo is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="start_at and end_at must include a timezone",
            )
        if start_at >= end_at:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="start_at must be earlier than end_at",
            )
    if not isinstance(repository, DatabaseRepository):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL is required for store summary",
        )
    return repository.get_store_summary(start_at=start_at, end_at=end_at)


@app.get(
    "/api/stores/{store_id}/timeline",
    response_model=StoreTimelineResponse,
    tags=["stores"],
)
def get_store_timeline(
    store_id: str,
    start_at: datetime,
    end_at: datetime,
    interval: Literal["1h", "1d"] = "1h",
) -> StoreTimelineResponse:
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_at and end_at must include a timezone",
        )
    if start_at >= end_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_at must be earlier than end_at",
        )
    if end_at - start_at > MAX_TIMELINE_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="timeline period must not exceed 31 days",
        )
    if not isinstance(repository, DatabaseRepository):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL is required for store timeline",
        )
    return repository.get_store_timeline(
        store_id,
        start_at=start_at,
        end_at=end_at,
        interval=interval,
    )


@app.get(
    "/api/stores/{store_id}/state",
    response_model=StoreState,
    tags=["stores"],
)
def get_store_state(store_id: str) -> StoreState:
    state_value = repository.get_store_state(store_id)
    if state_value is None:
        raise HTTPException(status_code=404, detail="Store state not found")
    return state_value


@app.get(
    "/api/stores/{store_id}/eta",
    response_model=EtaResponse,
    tags=["stores"],
)
def get_store_eta(store_id: str) -> EtaResponse:
    state_value = repository.get_store_state(store_id)
    if state_value is None:
        raise HTTPException(status_code=404, detail="Store state not found")
    estimated_minutes = state_value.queue_count_estimate * 3
    return EtaResponse(
        store_id=store_id,
        estimated_wait_minutes=estimated_minutes,
        calculation="queue_count_estimate * 3",
        data_source="mock_rule",
    )


@app.get("/api/stores/{store_id}/menus", tags=["stores"])
def get_store_menus(store_id: str) -> dict[str, Any]:
    menu_data = load_json_file("menus.json")
    menus = [
        menu
        for menu in menu_data.get("menus", [])
        if menu.get("store_id") == store_id
    ]
    return {**menu_data, "store_id": store_id, "menus": menus}


@app.get("/api/stores/{store_id}/policies", tags=["stores"])
def get_store_policies(store_id: str) -> dict[str, Any]:
    policy_data = load_json_file("policies.json")
    policies = [
        policy
        for policy in policy_data.get("policies", [])
        if policy.get("store_id") == store_id
    ]
    return {**policy_data, "store_id": store_id, "policies": policies}
