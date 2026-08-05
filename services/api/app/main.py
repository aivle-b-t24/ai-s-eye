import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
import io
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
from .db_repository import DatabaseRepository, StoreNameAlreadyExistsError
from .models import (
    AnalysisJobClaim,
    AnalysisJobCreate,
    AnalysisJobInfo,
    AnalysisJobStatus,
    AnalysisJobStatusUpdate,
    CameraRoiConfig,
    CameraRoiConfigInput,
    CameraSceneConfig,
    CameraSceneConfigInput,
    EtaResponse,
    FirebaseUserSummary,
    OrderEvent,
    OperationsSimulationResult,
    OperationsSimulationScenario,
    QualityStatus,
    StoreInfo,
    StoreListItem,
    StoreListResponse,
    StoreMediaInfo,
    StoreMediaType,
    StoreMenuInput,
    StoreMenuItem,
    StoreMenuListResponse,
    StoreMenuToggleInput,
    StorePolicyInput,
    StorePolicyItem,
    StorePolicyListResponse,
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
from .store_media_storage import (
    media_absolute_path,
    new_media_id,
    save_media_bytes,
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
    if store_id in settings.vision_store_ids:
        return
    if repository.store_exists(store_id):
        return
    raise HTTPException(status_code=404, detail="Store not found")


def empty_store_state(store_id: str) -> StoreState:
    """비전 상태가 아직 없는 등록 매장용 빈 스냅샷."""
    now = datetime.now(timezone.utc)
    return StoreState(
        store_id=store_id,
        camera_id=f"{store_id}-cam1",
        frame_id=None,
        captured_at=now,
        processed_at=None,
        visible_person_count=0,
        queue_count_estimate=0,
        zone_counts={},
        quality_status=QualityStatus.UNKNOWN,
        source="empty",
        model_version="none",
    )


def attach_store_names(
    users: list[FirebaseUserSummary],
) -> list[FirebaseUserSummary]:
    names = {store.id: store.name for store in repository.list_stores()}
    return [
        user.model_copy(update={"store_name": names.get(user.store_id)})
        if user.store_id
        else user
        for user in users
    ]


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
) -> dict[str, str | None]:
    payload: dict[str, str | None] = dict(user.response())
    if user.store_id and user.store_id != "head-office":
        store = repository.get_store(user.store_id)
        if store is not None:
            payload["storeName"] = store.name
    return payload


@app.get(
    "/api/admin/stores",
    response_model=list[StoreInfo],
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
def get_admin_stores() -> list[StoreInfo]:
    return repository.list_stores()


@app.get(
    "/api/admin/users",
    response_model=list[FirebaseUserSummary],
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
def get_admin_users() -> list[FirebaseUserSummary]:
    return attach_store_names(list_managed_accounts())


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
    try:
        store = repository.create_store(request.store_name)
    except StoreNameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 매장명입니다",
        ) from exc

    try:
        return create_store_manager_account(
            email=request.email,
            name=request.name,
            password=request.password,
            store_id=store.id,
            store_name=store.name,
        )
    except FirebaseUserAlreadyExistsError as exc:
        repository.delete_store(store.id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 이메일입니다",
        ) from exc
    except Exception:
        repository.delete_store(store.id)
        raise


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
def get_internal_stores() -> StoreListResponse:
    """매장 마스터 목록(ID + 표시명). AICC 챗봇이 안내 가능한 매장을 자동으로 알기 위해 쓴다.

    admin 전용인 /api/admin/stores와 달리 서비스 간 호출용(internal key)이다. 매장 마스터가
    단일 출처라, 본사에서 매장을 등록하면 챗봇 선택지에 이름과 함께 자동 반영된다.
    """
    return StoreListResponse(
        stores=[
            StoreListItem(store_id=store.id, name=store.name)
            for store in repository.list_stores()
        ]
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
    if state_value is not None:
        return state_value
    if repository.store_exists(store_id):
        return empty_store_state(store_id)
    raise HTTPException(status_code=404, detail="Store state not found")


@app.get(
    "/api/stores/{store_id}/eta",
    response_model=EtaResponse,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def get_store_eta(store_id: str) -> EtaResponse:
    state_value = repository.get_store_state(store_id)
    if state_value is None:
        if repository.store_exists(store_id):
            return EtaResponse(
                store_id=store_id,
                estimated_wait_minutes=0,
                waiting_order_count=0,
                calculation="no_vision_state",
                data_source="empty",
            )
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


def _detect_media_type(filename: str, content_type: str) -> StoreMediaType:
    lowered = filename.lower()
    ctype = (content_type or "").lower()
    if lowered.endswith((".mp4", ".webm", ".mov")) or ctype.startswith("video/"):
        return StoreMediaType.VIDEO
    if lowered.endswith(".zip") or ctype in {
        "application/zip",
        "application/x-zip-compressed",
    }:
        return StoreMediaType.FRAMES_ZIP
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="mp4/webm/mov 영상 또는 프레임 ZIP만 업로드할 수 있습니다.",
    )


@app.post(
    "/api/stores/{store_id}/media",
    response_model=StoreMediaInfo,
    status_code=status.HTTP_201_CREATED,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
async def upload_store_media(
    store_id: str,
    file: UploadFile = File(...),
) -> StoreMediaInfo:
    """온보딩·분석용 영상/프레임 ZIP을 등록한다."""
    if not repository.store_exists(store_id):
        raise HTTPException(status_code=404, detail="Store not found")
    filename = file.filename or "upload.bin"
    content_type = file.content_type or "application/octet-stream"
    media_type = _detect_media_type(filename, content_type)
    content = await file.read(settings.store_media_max_bytes + 1)
    await file.close()
    if len(content) > settings.store_media_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"파일은 {settings.store_media_max_bytes} bytes 이하여야 합니다.",
        )
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다.")

    media_id = new_media_id()
    abs_path = media_absolute_path(
        settings.store_media_dir,
        store_id,
        media_id,
        filename,
    )
    if settings.database_url:
        save_media_bytes(abs_path, content)
    return repository.save_store_media(
        store_id=store_id,
        media_type=media_type,
        filename=filename,
        content_type=content_type,
        content=content,
        storage_path=str(abs_path),
        media_id=media_id,
    )


@app.get(
    "/api/stores/{store_id}/media",
    response_model=list[StoreMediaInfo],
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def list_store_media(store_id: str) -> list[StoreMediaInfo]:
    return repository.list_store_media(store_id)


@app.post(
    "/api/stores/{store_id}/analysis-jobs",
    response_model=AnalysisJobInfo,
    status_code=status.HTTP_201_CREATED,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def create_analysis_job(
    store_id: str,
    payload: AnalysisJobCreate | None = None,
) -> AnalysisJobInfo:
    """온보딩 완료 후 GPU 워커가 가져갈 분석 job을 큐에 넣는다."""
    media_id = payload.media_id if payload else None
    media_list = repository.list_store_media(store_id)
    if not media_list:
        raise HTTPException(
            status_code=422,
            detail="분석할 업로드 미디어가 없습니다. 먼저 영상/ZIP을 등록해 주세요.",
        )
    if media_id is None:
        media_id = media_list[0].id
    try:
        return repository.create_analysis_job(store_id, media_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Media not found") from exc


@app.get(
    "/api/stores/{store_id}/analysis-jobs",
    response_model=list[AnalysisJobInfo],
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def list_analysis_jobs(store_id: str) -> list[AnalysisJobInfo]:
    return repository.list_analysis_jobs(store_id)


@app.get(
    "/internal/analysis-jobs/next",
    response_model=AnalysisJobClaim,
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)
def claim_next_analysis_job(worker_id: str = "gpu-worker") -> AnalysisJobClaim:
    job = repository.claim_next_analysis_job(worker_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No queued analysis jobs")
    media = repository.get_store_media(job.media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found for job")
    return AnalysisJobClaim(
        job=job,
        media=media,
        download_path=f"/internal/analysis-jobs/{job.id}/media",
    )


@app.get(
    "/internal/analysis-jobs/{job_id}/media",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)
def download_analysis_job_media(job_id: str) -> Response:
    job = repository.get_analysis_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    media = repository.get_store_media(job.media_id)
    content = repository.get_store_media_bytes(job.media_id)
    if media is None or content is None:
        raise HTTPException(status_code=404, detail="Media bytes not found")
    # HTTP header values must be latin-1; keep ASCII fallback + RFC 5987 filename*.
    safe_name = Path(media.filename).suffix.lower() or ".bin"
    ascii_name = f"download{safe_name}"
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(media.filename)}"
    )
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media.content_type,
        headers={"Content-Disposition": disposition},
    )


@app.patch(
    "/internal/analysis-jobs/{job_id}",
    response_model=AnalysisJobInfo,
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)
def patch_analysis_job(
    job_id: str,
    payload: AnalysisJobStatusUpdate,
) -> AnalysisJobInfo:
    if payload.status == AnalysisJobStatus.QUEUED:
        raise HTTPException(status_code=422, detail="Cannot revert job to queued")
    updated = repository.update_analysis_job(
        job_id,
        status=payload.status,
        progress_percent=payload.progress_percent,
        processed_frames=payload.processed_frames,
        total_frames=payload.total_frames,
        stage_message=payload.stage_message,
        error_message=payload.error_message,
        worker_id=payload.worker_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return updated


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
    response_model=StoreMenuListResponse,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def get_store_menus(store_id: str) -> StoreMenuListResponse:
    menus = repository.get_store_menus(store_id)
    if not menus:
        menu_data = load_json_file("menus.json")
        raw_menus = [
            m for m in menu_data.get("menus", [])
            if m.get("store_id") == store_id
        ]
        for m in raw_menus:
            inp = StoreMenuInput(
                category=m.get("category", "coffee"),
                name=m.get("name", ""),
                price=m.get("price", 0),
                prep_minutes=m.get("prep_minutes", 3),
                available=m.get("available", True),
                sold_out_reason=m.get("sold_out_reason"),
            )
            repository.save_store_menu(store_id, inp, menu_id=m.get("menu_id"))
        menus = repository.get_store_menus(store_id)
    return StoreMenuListResponse(
        data_source="db",
        store_id=store_id,
        menus=menus,
    )


@app.post(
    "/api/stores/{store_id}/menus",
    response_model=StoreMenuItem,
    status_code=status.HTTP_201_CREATED,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def create_store_menu(
    store_id: str,
    payload: StoreMenuInput,
) -> StoreMenuItem:
    return repository.save_store_menu(store_id, payload)


@app.put(
    "/api/stores/{store_id}/menus/{menu_id}",
    response_model=StoreMenuItem,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def update_store_menu(
    store_id: str,
    menu_id: str,
    payload: StoreMenuInput,
) -> StoreMenuItem:
    return repository.save_store_menu(store_id, payload, menu_id=menu_id)


@app.patch(
    "/api/stores/{store_id}/menus/{menu_id}/toggle-sold-out",
    response_model=StoreMenuItem,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def toggle_store_menu_sold_out(
    store_id: str,
    menu_id: str,
    payload: StoreMenuToggleInput,
) -> StoreMenuItem:
    updated = repository.toggle_store_menu_sold_out(
        store_id,
        menu_id,
        available=payload.available,
        sold_out_reason=payload.sold_out_reason,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Menu not found")
    return updated


@app.delete(
    "/api/stores/{store_id}/menus/{menu_id}",
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def delete_store_menu(store_id: str, menu_id: str) -> dict[str, Any]:
    deleted = repository.delete_store_menu(store_id, menu_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Menu not found")
    return {"deleted": True, "menu_id": menu_id}


@app.get(
    "/api/stores/{store_id}/policies",
    response_model=StorePolicyListResponse,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def get_store_policies(store_id: str) -> StorePolicyListResponse:
    policies = repository.get_store_policies(store_id)
    if not policies:
        policy_data = load_json_file("policies.json")
        raw_policies = [
            p for p in policy_data.get("policies", [])
            if p.get("store_id") == store_id
        ]
        for p in raw_policies:
            inp = StorePolicyInput(
                category=p.get("category", "general"),
                title=p.get("title", ""),
                content=p.get("content", ""),
                keywords=p.get("keywords", []),
            )
            repository.save_store_policy(store_id, inp, policy_id=p.get("policy_id"))
        policies = repository.get_store_policies(store_id)
    return StorePolicyListResponse(
        data_source="db",
        store_id=store_id,
        policies=policies,
    )


@app.post(
    "/api/stores/{store_id}/policies",
    response_model=StorePolicyItem,
    status_code=status.HTTP_201_CREATED,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def create_store_policy(
    store_id: str,
    payload: StorePolicyInput,
) -> StorePolicyItem:
    return repository.save_store_policy(store_id, payload)


@app.put(
    "/api/stores/{store_id}/policies/{policy_id}",
    response_model=StorePolicyItem,
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def update_store_policy(
    store_id: str,
    policy_id: str,
    payload: StorePolicyInput,
) -> StorePolicyItem:
    return repository.save_store_policy(store_id, payload, policy_id=policy_id)


@app.delete(
    "/api/stores/{store_id}/policies/{policy_id}",
    tags=["stores"],
    dependencies=[Depends(require_store_access)],
)
def delete_store_policy(store_id: str, policy_id: str) -> dict[str, Any]:
    deleted = repository.delete_store_policy(store_id, policy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"deleted": True, "policy_id": policy_id}
