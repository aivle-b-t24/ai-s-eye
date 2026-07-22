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
                delete(OrderEventRecord).where(OrderEventRecord.order_id == test_id)
            )
            session.execute(
                delete(StoreStateRecord).where(StoreStateRecord.store_id == test_id)
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
