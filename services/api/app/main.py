import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import psycopg

from .config import get_settings
from .models import EtaResponse, OrderEvent, StoreState
from .repository import InMemoryRepository


settings = get_settings()
repository = InMemoryRepository()


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
    "/internal/order-events",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["internal"],
)
def save_order_event(event: OrderEvent) -> dict[str, Any]:
    saved = repository.save_order_event(event)
    return {"accepted": True, "event": saved.model_dump(mode="json")}


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
    return {**menu_data, "store_id": store_id}


@app.get("/api/stores/{store_id}/policies", tags=["stores"])
def get_store_policies(store_id: str) -> dict[str, Any]:
    policy_data = load_json_file("policies.json")
    return {**policy_data, "store_id": store_id}
