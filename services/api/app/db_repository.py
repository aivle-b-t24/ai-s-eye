"""PostgreSQL에 매장 상태와 주문 이벤트를 저장하는 Repository."""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .database import get_session_factory
from .db_models import OrderEventRecord, OrderItemRecord, StoreStateRecord
from .models import OrderEvent, OrderItem, StoreState, StoreSummaryResponse
from .summary import build_store_summary


SessionFactory = Callable[[], Session]


class DatabaseRepository:
    """SQLAlchemy 세션을 이용해 PostgreSQL에 데이터를 저장하고 조회한다."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    def save_store_state(self, state: StoreState) -> StoreState:
        """매장 상태를 이력으로 추가한다."""
        record = StoreStateRecord(
            store_id=state.store_id,
            camera_id=state.camera_id,
            captured_at=state.captured_at,
            visible_person_count=state.visible_person_count,
            queue_count_estimate=state.queue_count_estimate,
            zone_counts=state.zone_counts,
            quality_status=state.quality_status.value,
            source=state.source,
            model_version=state.model_version,
        )

        with self._session_factory() as session:
            session.add(record)
            session.commit()

        return state

    def get_store_state(self, store_id: str) -> StoreState | None:
        """매장의 측정 시각이 가장 최근인 상태를 반환한다."""
        statement = (
            select(StoreStateRecord)
            .where(StoreStateRecord.store_id == store_id)
            .order_by(StoreStateRecord.captured_at.desc(), StoreStateRecord.id.desc())
            .limit(1)
        )

        with self._session_factory() as session:
            record = session.scalar(statement)
            if record is None:
                return None
            return _store_state_from_record(record)

    def save_order_event(self, event: OrderEvent) -> OrderEvent:
        """주문 이벤트와 메뉴를 함께 저장하며 event_id 중복을 허용하지 않는다."""
        with self._session_factory() as session:
            existing = _get_order_event_record(session, event.event_id)
            if existing is not None:
                return _order_event_from_record(existing)

            record = OrderEventRecord(
                event_id=event.event_id,
                order_id=event.order_id,
                store_id=event.store_id,
                occurred_at=event.occurred_at,
                status=event.status.value,
                items=[
                    OrderItemRecord(
                        menu_id=item.menu_id,
                        name=item.name,
                        quantity=item.quantity,
                    )
                    for item in event.items
                ],
            )
            session.add(record)

            try:
                session.commit()
            except IntegrityError:
                # 같은 이벤트가 거의 동시에 다시 들어온 경우에도 한 건만 유지한다.
                session.rollback()
                existing = _get_order_event_record(session, event.event_id)
                if existing is None:
                    raise
                return _order_event_from_record(existing)

            return _order_event_from_record(record)

    def get_latest_order_event(self, order_id: str) -> OrderEvent | None:
        """주문번호에 해당하는 가장 최근 상태 이벤트를 반환한다."""
        statement = (
            select(OrderEventRecord)
            .options(selectinload(OrderEventRecord.items))
            .where(OrderEventRecord.order_id == order_id)
            .order_by(
                OrderEventRecord.occurred_at.desc(),
                OrderEventRecord.created_at.desc(),
                OrderEventRecord.event_id.desc(),
            )
            .limit(1)
        )

        with self._session_factory() as session:
            record = session.scalar(statement)
            if record is None:
                return None
            return _order_event_from_record(record)

    def get_latest_store_order_event(
        self,
        store_id: str,
        order_id: str,
    ) -> OrderEvent | None:
        """매장과 주문번호가 모두 일치하는 가장 최근 이벤트를 반환한다."""
        statement = (
            select(OrderEventRecord)
            .options(selectinload(OrderEventRecord.items))
            .where(
                OrderEventRecord.store_id == store_id,
                OrderEventRecord.order_id == order_id,
            )
            .order_by(
                OrderEventRecord.occurred_at.desc(),
                OrderEventRecord.created_at.desc(),
                OrderEventRecord.event_id.desc(),
            )
            .limit(1)
        )

        with self._session_factory() as session:
            record = session.scalar(statement)
            if record is None:
                return None
            return _order_event_from_record(record)

    def get_store_summary(
        self,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> StoreSummaryResponse:
        """기간에 포함된 상태와 주문 이력을 매장별로 집계한다."""
        state_statement = select(StoreStateRecord).order_by(
            StoreStateRecord.store_id,
            StoreStateRecord.captured_at,
            StoreStateRecord.id,
        )
        order_statement = (
            select(OrderEventRecord)
            .options(selectinload(OrderEventRecord.items))
            .order_by(
                OrderEventRecord.store_id,
                OrderEventRecord.occurred_at,
                OrderEventRecord.event_id,
            )
        )

        if start_at is not None:
            state_statement = state_statement.where(
                StoreStateRecord.captured_at >= start_at
            )
            order_statement = order_statement.where(
                OrderEventRecord.occurred_at >= start_at
            )
        if end_at is not None:
            state_statement = state_statement.where(
                StoreStateRecord.captured_at <= end_at
            )
            order_statement = order_statement.where(
                OrderEventRecord.occurred_at <= end_at
            )

        with self._session_factory() as session:
            state_records = list(session.scalars(state_statement))
            order_records = list(session.scalars(order_statement))
            states = [_store_state_from_record(record) for record in state_records]
            orders = [_order_event_from_record(record) for record in order_records]

        return build_store_summary(
            states,
            orders,
            start_at=start_at,
            end_at=end_at,
        )


def _get_order_event_record(
    session: Session,
    event_id: str,
) -> OrderEventRecord | None:
    statement = (
        select(OrderEventRecord)
        .options(selectinload(OrderEventRecord.items))
        .where(OrderEventRecord.event_id == event_id)
    )
    return session.scalar(statement)


def _store_state_from_record(record: StoreStateRecord) -> StoreState:
    return StoreState(
        store_id=record.store_id,
        camera_id=record.camera_id,
        captured_at=record.captured_at,
        visible_person_count=record.visible_person_count,
        queue_count_estimate=record.queue_count_estimate,
        zone_counts=record.zone_counts,
        quality_status=record.quality_status,
        source=record.source,
        model_version=record.model_version,
    )


def _order_event_from_record(record: OrderEventRecord) -> OrderEvent:
    return OrderEvent(
        event_id=record.event_id,
        order_id=record.order_id,
        store_id=record.store_id,
        occurred_at=record.occurred_at,
        status=record.status,
        items=[
            OrderItem(
                menu_id=item.menu_id,
                name=item.name,
                quantity=item.quantity,
            )
            for item in sorted(record.items, key=lambda item: item.id or 0)
        ],
    )
