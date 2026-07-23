"""실제 PostgreSQL을 사용하는 Repository 통합 테스트."""

from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db_models import OrderEventRecord, StoreStateRecord
from app.db_repository import DatabaseRepository
from app.models import OrderEvent, OrderItem, OrderStatus, QualityStatus, StoreState


def _test_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL이 없어 PostgreSQL 통합 테스트를 건너뜁니다.")
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


@pytest.fixture
def database_repository() -> tuple[DatabaseRepository, sessionmaker[Session], str]:
    engine = create_engine(_test_database_url(), pool_pre_ping=True)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    test_id = f"pytest-{uuid4().hex}"
    repository = DatabaseRepository(session_factory)

    try:
        yield repository, session_factory, test_id
    finally:
        with session_factory() as session:
            session.execute(
                delete(OrderEventRecord).where(
                    OrderEventRecord.event_id.like(f"{test_id}%")
                )
            )
            session.execute(
                delete(StoreStateRecord).where(
                    StoreStateRecord.store_id.like(f"{test_id}%")
                )
            )
            session.commit()
        engine.dispose()


def test_latest_store_state_is_returned(
    database_repository: tuple[DatabaseRepository, sessionmaker[Session], str],
) -> None:
    repository, _, test_id = database_repository
    captured_at = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)
    older_state = StoreState(
        store_id=test_id,
        camera_id="cam-test",
        captured_at=captured_at,
        visible_person_count=2,
        queue_count_estimate=1,
        zone_counts={"waiting": 1, "seating": 1},
        quality_status=QualityStatus.NORMAL,
        source="pytest",
        model_version="test-v1",
    )
    newer_state = older_state.model_copy(
        update={
            "captured_at": captured_at + timedelta(seconds=2),
            "visible_person_count": 6,
            "queue_count_estimate": 3,
        }
    )

    repository.save_store_state(older_state)
    repository.save_store_state(newer_state)

    saved_state = repository.get_store_state(test_id)

    assert saved_state is not None
    assert saved_state.captured_at == newer_state.captured_at
    assert saved_state.visible_person_count == 6
    assert saved_state.queue_count_estimate == 3


def test_same_store_state_payload_is_not_saved_twice(
    database_repository: tuple[DatabaseRepository, sessionmaker[Session], str],
) -> None:
    repository, session_factory, test_id = database_repository
    state = StoreState(
        store_id=test_id,
        camera_id="cam-idempotent",
        captured_at=datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc),
        visible_person_count=8,
        queue_count_estimate=2,
        zone_counts={"waiting": 2, "seating": 6},
        quality_status=QualityStatus.NORMAL,
        source="scenario-test",
        model_version="test-v1",
    )

    repository.save_store_state(state)
    repository.save_store_state(state)

    with session_factory() as session:
        state_count = session.scalar(
            select(func.count())
            .select_from(StoreStateRecord)
            .where(
                StoreStateRecord.store_id == state.store_id,
                StoreStateRecord.camera_id == state.camera_id,
                StoreStateRecord.captured_at == state.captured_at,
            )
        )

    assert state_count == 1


def test_duplicate_order_event_is_ignored_and_latest_event_is_returned(
    database_repository: tuple[DatabaseRepository, sessionmaker[Session], str],
) -> None:
    repository, session_factory, test_id = database_repository
    occurred_at = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)
    received_event = OrderEvent(
        event_id=f"{test_id}-received",
        order_id=test_id,
        store_id=test_id,
        occurred_at=occurred_at,
        status=OrderStatus.RECEIVED,
        items=[OrderItem(menu_id="menu-test", name="테스트 메뉴", quantity=1)],
    )

    repository.save_order_event(received_event)
    duplicate_result = repository.save_order_event(
        received_event.model_copy(update={"status": OrderStatus.CANCELLED})
    )

    with session_factory() as session:
        event_count = session.scalar(
            select(func.count())
            .select_from(OrderEventRecord)
            .where(OrderEventRecord.event_id == received_event.event_id)
        )

    assert event_count == 1
    assert duplicate_result.status == OrderStatus.RECEIVED

    ready_event = received_event.model_copy(
        update={
            "event_id": f"{test_id}-ready",
            "occurred_at": occurred_at + timedelta(minutes=3),
            "status": OrderStatus.READY,
        }
    )
    repository.save_order_event(ready_event)

    latest_event = repository.get_latest_order_event(test_id)

    assert latest_event is not None
    assert latest_event.event_id == ready_event.event_id
    assert latest_event.status == OrderStatus.READY
    assert latest_event.items == ready_event.items


def test_same_order_id_is_read_separately_by_store(
    database_repository: tuple[DatabaseRepository, sessionmaker[Session], str],
) -> None:
    repository, _, test_id = database_repository
    occurred_at = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)
    store_one_event = OrderEvent(
        event_id=f"{test_id}-store-001",
        order_id=test_id,
        store_id="store-001",
        occurred_at=occurred_at,
        status=OrderStatus.RECEIVED,
        items=[OrderItem(menu_id="menu-test", name="테스트 메뉴", quantity=1)],
    )
    store_two_event = store_one_event.model_copy(
        update={
            "event_id": f"{test_id}-store-002",
            "store_id": "store-002",
            "occurred_at": occurred_at + timedelta(minutes=3),
            "status": OrderStatus.READY,
        }
    )

    repository.save_order_event(store_one_event)
    repository.save_order_event(store_two_event)

    store_one_result = repository.get_latest_store_order_event(
        "store-001",
        test_id,
    )
    store_two_result = repository.get_latest_store_order_event(
        "store-002",
        test_id,
    )

    assert store_one_result is not None
    assert store_one_result.store_id == "store-001"
    assert store_one_result.status == OrderStatus.RECEIVED
    assert store_two_result is not None
    assert store_two_result.store_id == "store-002"
    assert store_two_result.status == OrderStatus.READY


def test_store_summary_uses_period_and_separates_stores(
    database_repository: tuple[DatabaseRepository, sessionmaker[Session], str],
) -> None:
    repository, _, test_id = database_repository
    store_one = f"{test_id}-store-001"
    store_two = f"{test_id}-store-002"
    unique_offset = int(test_id[-12:], 16)
    start_at = datetime(2200, 1, 1, tzinfo=timezone.utc) + timedelta(
        microseconds=unique_offset
    )
    end_at = start_at + timedelta(days=1)

    for store_id, hour, person_count, queue_count in (
        (store_one, 1, 8, 1),
        (store_one, 3, 28, 9),
        (store_two, 1, 10, 0),
        (store_two, 5, 22, 4),
    ):
        repository.save_store_state(
            StoreState(
                store_id=store_id,
                camera_id="cam-summary",
                captured_at=start_at + timedelta(hours=hour),
                visible_person_count=person_count,
                queue_count_estimate=queue_count,
                zone_counts={"waiting": queue_count},
                quality_status=QualityStatus.NORMAL,
                source="pytest",
                model_version="test-v1",
            )
        )

    received_event = OrderEvent(
        event_id=f"{test_id}-summary-received",
        order_id=f"{test_id}-order-001",
        store_id=store_one,
        occurred_at=start_at + timedelta(hours=2),
        status=OrderStatus.RECEIVED,
        items=[OrderItem(menu_id="menu-001", name="아메리카노", quantity=2)],
    )
    ready_event = received_event.model_copy(
        update={
            "event_id": f"{test_id}-summary-ready",
            "occurred_at": start_at + timedelta(hours=4),
            "status": OrderStatus.READY,
        }
    )
    store_two_event = OrderEvent(
        event_id=f"{test_id}-summary-store-002",
        order_id=f"{test_id}-order-002",
        store_id=store_two,
        occurred_at=start_at + timedelta(hours=6),
        status=OrderStatus.COMPLETED,
        items=[OrderItem(menu_id="menu-021", name="크루아상", quantity=3)],
    )
    repository.save_order_event(received_event)
    repository.save_order_event(ready_event)
    repository.save_order_event(store_two_event)

    response = repository.get_store_summary(start_at=start_at, end_at=end_at)
    stores = {store.store_id: store for store in response.stores}

    assert set(stores) == {store_one, store_two}
    assert stores[store_one].traffic_summary is not None
    assert stores[store_one].traffic_summary.average_visible_person_count == 18
    assert stores[store_one].traffic_summary.peak_queue_count_estimate == 9
    assert stores[store_one].order_summary.total_order_count == 1
    assert stores[store_one].order_summary.order_event_count == 2
    assert stores[store_one].order_summary.latest_status_counts.ready == 1
    assert stores[store_one].order_summary.top_menu_items[0].quantity == 2
    assert stores[store_two].traffic_summary is not None
    assert stores[store_two].traffic_summary.peak_visible_person_count == 22
    assert stores[store_two].order_summary.total_order_count == 1
    assert stores[store_two].order_summary.top_menu_items[0].menu_id == "menu-021"

    filtered = repository.get_store_summary(
        start_at=start_at + timedelta(hours=3, minutes=30),
        end_at=end_at,
    )
    filtered_stores = {store.store_id: store for store in filtered.stores}

    assert filtered_stores[store_one].traffic_summary is None
    assert filtered_stores[store_one].order_summary.total_order_count == 1
    assert filtered_stores[store_one].order_summary.order_event_count == 1
