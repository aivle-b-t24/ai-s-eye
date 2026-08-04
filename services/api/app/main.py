import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
import psycopg
from pydantic import ValidationError

from .config import get_settings
from .auth import (
    CurrentUser,
    get_current_user,
    require_admin,
    require_internal_service,
    require_store_access,
)
from .db_repository import DatabaseRepository
from .models import (
    CameraRoiConfig,
    CameraRoiConfigInput,
    CameraSceneConfig,
    CameraSceneConfigInput,
    EtaResponse,
    FirebaseUserSummary,
    OrderEvent,
    OperationsSimulationResult,
    OperationsSimulationScenario,
    StoreListItem,
    StoreListResponse,
    StoreSettings,
    StoreSettingsInput,
    StoreState,
    StoreManagerAccountCreate,
    StoreManagerPasswordUpdate,
    StoreSummaryResponse,
    StoreTimelineResponse,
    TwinFrame,
    VisionSnapshotMetadata,
)
from .firebase_users import (
    FirebaseUserAlreadyExistsError,
    FirebaseUserNotFoundError,
    FirebaseUserNotStoreManagerError,
    create_store_manager_account,
    delete_store_manager_account,
    list_managed_accounts,
    update_store_manager_password,
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


@lru_cache(maxsize=1)
def _demo_waiting_table() -> dict[str, dict[str, int]]:
    """CAFE 라벨 backlog로 미리 계산한 프레임별 대기값(demo_waiting.json).

    파일이 없으면 빈 표를 돌려줘 데모 값이 없을 때 주문 기반 계산으로 넘어간다.
    """
    try:
        data = load_json_file("demo_waiting.json")
    except HTTPException:
        return {}
    return data if isinstance(data, dict) else {}


def _demo_waiting_for(frame_id: str | None) -> dict[str, int] | None:
    if not frame_id:
        return None
    return _demo_waiting_table().get(frame_id)


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


@app.get("/api/auth/me", tags=["auth"])
def get_authenticated_user(
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    return user.response()


@app.get(
    "/api/admin/users",
    response_model=list[FirebaseUserSummary],
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
def get_admin_users() -> list[FirebaseUserSummary]:
    return list_managed_accounts()


@app.post(
    "/api/admin/users",
    response_model=FirebaseUserSummary,
    status_code=status.HTTP_201_CREATED,
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
def create_admin_user(
    request: StoreManagerAccountCreate,
) -> FirebaseUserSummary:
    if request.store_id not in settings.vision_store_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="지원하지 않는 매장입니다",
        )
    try:
        return create_store_manager_account(request)
    except FirebaseUserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 이메일입니다",
        ) from exc


@app.delete(
    "/api/admin/users/{uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
def delete_admin_user(uid: str) -> None:
    try:
        delete_store_manager_account(uid)
    except FirebaseUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="계정을 찾을 수 없습니다",
        ) from exc
    except FirebaseUserNotStoreManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="점주 계정만 삭제할 수 있습니다",
        ) from exc


@app.patch(
    "/api/admin/users/{uid}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
def update_admin_user_password(
    uid: str,
    request: StoreManagerPasswordUpdate,
) -> None:
    try:
        update_store_manager_password(uid, request)
    except FirebaseUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="계정을 찾을 수 없습니다",
        ) from exc
    except FirebaseUserNotStoreManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="점주 계정 비밀번호만 변경할 수 있습니다",
        ) from exc


@app.post(
    "/internal/store-states",
    status_code=status.HTTP_201_CREATED,
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)
def save_store_state(state: StoreState) -> dict[str, Any]:
    saved = repository.save_store_state(state)
    return {"saved": True, "state": saved.model_dump(mode="json")}


@app.post(
    "/internal/stores/{store_id}/occupancy",
    status_code=status.HTTP_201_CREATED,
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
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
    dependencies=[Depends(require_internal_service)],
)
def save_order_event(event: OrderEvent) -> dict[str, Any]:
    saved = repository.save_order_event(event)
    return {"accepted": True, "event": saved.model_dump(mode="json")}


@app.post(
    "/internal/stores/{store_id}/vision-snapshot",
    status_code=status.HTTP_201_CREATED,
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
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
    dependencies=[Depends(require_internal_service)],
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
    dependencies=[Depends(require_store_access)],
)
def get_latest_vision_snapshot(store_id: str) -> FileResponse:
    validate_vision_store_id(store_id)
    return vision_snapshot_response(store_id)


@app.get(
    "/api/stores/{store_id}/vision/raw/latest",
    response_class=FileResponse,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def get_latest_raw_vision_snapshot(store_id: str) -> FileResponse:
    """ROI 설정용 원본 CCTV 프레임을 반환한다."""
    validate_vision_store_id(store_id)
    return vision_snapshot_response(store_id, raw=True)


@app.get(
    "/api/stores/{store_id}/vision/metadata",
    response_model=VisionSnapshotMetadata,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def get_latest_vision_metadata(store_id: str) -> VisionSnapshotMetadata:
    validate_vision_store_id(store_id)
    return get_vision_snapshot_metadata(store_id)


@app.get(
    "/api/stores/{store_id}/vision/raw/metadata",
    response_model=VisionSnapshotMetadata,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def get_latest_raw_vision_metadata(store_id: str) -> VisionSnapshotMetadata:
    validate_vision_store_id(store_id)
    return get_vision_snapshot_metadata(store_id, raw=True)


@app.get(
    "/api/stores/{store_id}/occupancy/latest",
    response_model=TwinFrame,
    response_model_exclude_none=True,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_internal_service)],
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
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_admin)],
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
    dependencies=[Depends(require_admin)],
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
    dependencies=[Depends(require_admin)],
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
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_admin)],
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
    "/internal/stores",
    response_model=StoreListResponse,
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)
def list_stores() -> StoreListResponse:
    """상태가 등록된 매장 ID 목록. AICC 챗봇이 안내 가능한 매장을 자동으로 알기 위해 쓴다.

    매장 표시명은 아직 백엔드에 없어 name은 비워 둔다(소비 측에서 채운다).
    """
    return StoreListResponse(
        stores=[StoreListItem(store_id=store_id) for store_id in repository.list_store_ids()]
    )


@app.get(
    "/api/stores/{store_id}/timeline",
    response_model=StoreTimelineResponse,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_store_access)],
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
    dependencies=[Depends(require_store_access)],
)
def get_store_eta(store_id: str) -> EtaResponse:
    state_value = repository.get_store_state(store_id)
    if state_value is None:
        raise HTTPException(status_code=404, detail="Store state not found")
    # 데모: 현재 프레임에 CAFE 라벨 기반 backlog 대기값이 있으면 그대로 표시한다.
    # (주문 1건=2분 작업, 직원이 1분당 1분 처리하는 단일 창구 큐로 미리 계산.)
    demo = _demo_waiting_for(state_value.frame_id)
    if demo is not None:
        return EtaResponse(
            store_id=store_id,
            estimated_wait_minutes=demo["wait_minutes"],
            waiting_order_count=demo["waiting"],
            calculation="cafe_label_backlog(2min/person, one-per-person)",
            data_source="cafe_label_demo",
        )
    # 실데이터: 화면 프레임 시각에 진행 중인 주문 수(주문 로그 기반).
    waiting_orders = repository.count_waiting_orders_at(
        store_id, state_value.captured_at
    )
    estimated_minutes = waiting_orders * 3
    return EtaResponse(
        store_id=store_id,
        estimated_wait_minutes=estimated_minutes,
        waiting_order_count=waiting_orders,
        calculation="waiting_order_count * 3",
        data_source="order_lifecycle",
    )


@app.get(
    "/api/stores/{store_id}/settings",
    response_model=StoreSettings,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def get_store_settings(store_id: str) -> StoreSettings:
    """매장 운영 설정(수용 인원 등). 저장된 값이 없으면 기본값을 돌려준다."""
    settings_value = repository.get_store_settings(store_id)
    if settings_value is None:
        return StoreSettings(store_id=store_id)
    return settings_value


@app.put(
    "/api/stores/{store_id}/settings",
    response_model=StoreSettings,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def update_store_settings(
    store_id: str,
    payload: StoreSettingsInput,
) -> StoreSettings:
    if store_id not in settings.vision_store_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="지원하지 않는 매장입니다",
        )
    return repository.save_store_settings(store_id, payload.max_capacity)


@app.get(
    "/api/stores/{store_id}/menus",
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def get_store_menus(store_id: str) -> dict[str, Any]:
    menu_data = load_json_file("menus.json")
    menus = [
        menu
        for menu in menu_data.get("menus", [])
        if menu.get("store_id") == store_id
    ]
    return {**menu_data, "store_id": store_id, "menus": menus}


@app.get(
    "/api/stores/{store_id}/policies",
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def get_store_policies(store_id: str) -> dict[str, Any]:
    policy_data = load_json_file("policies.json")
    policies = [
        policy
        for policy in policy_data.get("policies", [])
        if policy.get("store_id") == store_id
    ]
    return {**policy_data, "store_id": store_id, "policies": policies}
