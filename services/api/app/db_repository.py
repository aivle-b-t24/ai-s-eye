"""PostgreSQL에 매장 상태와 주문 이벤트를 저장하는 Repository."""

from collections.abc import Callable, Collection
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .database import get_session_factory
from .db_models import (
    CameraRoiConfigRecord,
    CameraSceneConfigRecord,
    CurrentStoreStateRecord,
    HourlyStoreMetricRecord,
    OrderEventRecord,
    OrderItemRecord,
    StoreStateHistoryRecord,
    StoreStateRecord,
)
from .models import (
    CameraRoiConfig,
    CameraRoiConfigInput,
    CameraSceneConfig,
    CameraSceneConfigInput,
    OrderEvent,
    OrderItem,
    RoiConfigStatus,
    SceneConfigStatus,
    StoreState,
    StoreSummaryResponse,
    StoreTimelineResponse,
)
from .order_queue import build_waiting_intervals, concurrency_at
from .summary import build_store_summary
from .timeline import build_store_timeline


SessionFactory = Callable[[], Session]
HISTORY_SAMPLE_SECONDS = 30
# 주문 생애주기(접수~픽업)는 10분 안팎이라, 특정 시각에 진행 중인 주문을 모두
# 담으려면 앞뒤로 1시간이면 충분하다.
WAITING_LOOKUP_WINDOW = timedelta(hours=1)


class DatabaseRepository:
    """SQLAlchemy 세션을 이용해 PostgreSQL에 데이터를 저장하고 조회한다."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    def save_store_state(self, state: StoreState) -> StoreState:
        """최신본을 갱신하고 원본·30초 샘플·시간 집계를 함께 저장한다."""
        with self._session_factory() as session:
            _upsert_current_store_state(session, state)

            existing = _find_raw_store_state(session, state)
            if existing is not None:
                session.commit()
                return state

            record = StoreStateRecord(**_store_state_values(state))
            session.add(record)
            _upsert_history_sample(session, state)
            _upsert_hourly_metric(session, state)
            session.commit()

        return state

    def get_store_state(self, store_id: str) -> StoreState | None:
        """매장에서 마지막으로 수신한 카메라 상태를 반환한다."""
        statement = (
            select(CurrentStoreStateRecord)
            .where(CurrentStoreStateRecord.store_id == store_id)
            .order_by(CurrentStoreStateRecord.updated_at.desc())
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

    def list_order_events(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        store_id: str | None = None,
    ) -> list[OrderEvent]:
        """CSV 내보내기에 사용할 기간 내 주문 이벤트를 반환한다."""
        statement = (
            select(OrderEventRecord)
            .options(selectinload(OrderEventRecord.items))
            .where(
                OrderEventRecord.occurred_at >= start_at,
                OrderEventRecord.occurred_at < end_at,
            )
            .order_by(
                OrderEventRecord.occurred_at,
                OrderEventRecord.store_id,
                OrderEventRecord.order_id,
                OrderEventRecord.event_id,
            )
        )
        if store_id is not None:
            statement = statement.where(OrderEventRecord.store_id == store_id)

        with self._session_factory() as session:
            records = list(session.scalars(statement))
            return [_order_event_from_record(record) for record in records]

    def count_waiting_orders_at(self, store_id: str, at: datetime) -> int:
        """주어진 시각에 진행 중(접수~픽업 전)인 주문 수 = 그 순간 대기 인원.

        라이브 화면이 보여주는 프레임 시각(state.captured_at)에 맞춰, 그때 아직
        완료되지 않은 주문을 센다. 주문 로그의 정확한 시각만 쓰므로 비전 추적과
        무관하다. 데이터가 합성이면 값은 생성기 재현이다(실 POS면 실측 대기).
        """
        orders = self.list_order_events(
            start_at=at - WAITING_LOOKUP_WINDOW,
            end_at=at + WAITING_LOOKUP_WINDOW,
            store_id=store_id,
        )
        intervals = build_waiting_intervals(orders)
        return concurrency_at(intervals, at)

    def get_store_summary(
        self,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> StoreSummaryResponse:
        """기간에 포함된 상태와 주문 이력을 매장별로 집계한다."""
        state_statement = select(StoreStateHistoryRecord).order_by(
            StoreStateHistoryRecord.store_id,
            StoreStateHistoryRecord.captured_at,
            StoreStateHistoryRecord.id,
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
                StoreStateHistoryRecord.captured_at >= start_at
            )
            order_statement = order_statement.where(
                OrderEventRecord.occurred_at >= start_at
            )
        if end_at is not None:
            state_statement = state_statement.where(
                StoreStateHistoryRecord.captured_at < end_at
            )
            order_statement = order_statement.where(
                OrderEventRecord.occurred_at < end_at
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

    def get_store_timeline(
        self,
        store_id: str,
        *,
        start_at: datetime,
        end_at: datetime,
        interval: str = "1h",
    ) -> StoreTimelineResponse:
        """한 매장의 상태와 신규 주문을 요청 기간의 시간대별로 집계한다."""
        state_statement = (
            select(StoreStateHistoryRecord)
            .where(
                StoreStateHistoryRecord.store_id == store_id,
                StoreStateHistoryRecord.captured_at >= start_at,
                StoreStateHistoryRecord.captured_at < end_at,
            )
            .order_by(
                StoreStateHistoryRecord.captured_at,
                StoreStateHistoryRecord.id,
            )
        )
        order_statement = (
            select(OrderEventRecord)
            .options(selectinload(OrderEventRecord.items))
            .where(
                OrderEventRecord.store_id == store_id,
                OrderEventRecord.occurred_at >= start_at,
                OrderEventRecord.occurred_at < end_at,
            )
            .order_by(OrderEventRecord.occurred_at, OrderEventRecord.event_id)
        )

        with self._session_factory() as session:
            state_records = list(session.scalars(state_statement))
            order_records = list(session.scalars(order_statement))
            states = [_store_state_from_record(record) for record in state_records]
            orders = [_order_event_from_record(record) for record in order_records]

        return build_store_timeline(
            store_id,
            states,
            orders,
            start_at=start_at,
            end_at=end_at,
            interval=interval,
        )

    def count_expired_store_states(
        self,
        cutoff: datetime,
        store_ids: Collection[str] | None = None,
    ) -> int:
        """보관기간이 지난 원본 이력 수를 반환한다."""
        expired_ids = _expired_store_state_ids(cutoff, store_ids)
        statement = (
            select(func.count())
            .select_from(StoreStateRecord)
            .where(StoreStateRecord.id.in_(expired_ids))
        )
        with self._session_factory() as session:
            return int(session.scalar(statement) or 0)

    def delete_expired_store_states(
        self,
        cutoff: datetime,
        store_ids: Collection[str] | None = None,
    ) -> int:
        """보관기간이 지난 원본 이력을 삭제한다.

        최신 상태는 ``current_store_states``에 별도로 유지된다.
        """
        expired_ids = _expired_store_state_ids(cutoff, store_ids)
        statement = delete(StoreStateRecord).where(
            StoreStateRecord.id.in_(expired_ids)
        )
        with self._session_factory() as session:
            result = session.execute(statement)
            session.commit()
            return int(result.rowcount or 0)

    def save_roi_config(
        self,
        store_id: str,
        camera_id: str,
        config: CameraRoiConfigInput,
    ) -> CameraRoiConfig:
        """새 승인 버전을 저장하고 이전 승인본은 보관 상태로 바꾼다."""
        with self._session_factory() as session:
            existing_statement = (
                select(CameraRoiConfigRecord)
                .where(
                    CameraRoiConfigRecord.store_id == store_id,
                    CameraRoiConfigRecord.camera_id == camera_id,
                )
                .order_by(CameraRoiConfigRecord.version)
                .with_for_update()
            )
            existing = list(session.scalars(existing_statement))
            next_version = max((item.version for item in existing), default=0) + 1
            session.execute(
                update(CameraRoiConfigRecord)
                .where(
                    CameraRoiConfigRecord.store_id == store_id,
                    CameraRoiConfigRecord.camera_id == camera_id,
                    CameraRoiConfigRecord.status == RoiConfigStatus.APPROVED.value,
                )
                .values(status=RoiConfigStatus.ARCHIVED.value)
            )
            now = datetime.now(timezone.utc)
            record = CameraRoiConfigRecord(
                store_id=store_id,
                camera_id=camera_id,
                version=next_version,
                coordinate_space=config.coordinate_space,
                image_width=config.image_size.width,
                image_height=config.image_size.height,
                zones=[
                    zone.model_dump(mode="json")
                    for zone in config.zones
                ],
                source=config.source.value,
                status=RoiConfigStatus.APPROVED.value,
                approved_at=now,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return _roi_config_from_record(record)

    def get_approved_roi_config(
        self,
        store_id: str,
        camera_id: str,
    ) -> CameraRoiConfig | None:
        statement = (
            select(CameraRoiConfigRecord)
            .where(
                CameraRoiConfigRecord.store_id == store_id,
                CameraRoiConfigRecord.camera_id == camera_id,
                CameraRoiConfigRecord.status == RoiConfigStatus.APPROVED.value,
            )
            .limit(1)
        )
        with self._session_factory() as session:
            record = session.scalar(statement)
            return _roi_config_from_record(record) if record is not None else None

    def list_roi_configs(
        self,
        store_id: str,
        camera_id: str,
    ) -> list[CameraRoiConfig]:
        statement = (
            select(CameraRoiConfigRecord)
            .where(
                CameraRoiConfigRecord.store_id == store_id,
                CameraRoiConfigRecord.camera_id == camera_id,
            )
            .order_by(CameraRoiConfigRecord.version.desc())
        )
        with self._session_factory() as session:
            return [
                _roi_config_from_record(record)
                for record in session.scalars(statement)
            ]

    def approve_roi_config(
        self,
        store_id: str,
        camera_id: str,
        version: int,
    ) -> CameraRoiConfig | None:
        with self._session_factory() as session:
            target_statement = (
                select(CameraRoiConfigRecord)
                .where(
                    CameraRoiConfigRecord.store_id == store_id,
                    CameraRoiConfigRecord.camera_id == camera_id,
                    CameraRoiConfigRecord.version == version,
                )
                .with_for_update()
            )
            target = session.scalar(target_statement)
            if target is None:
                return None
            session.execute(
                update(CameraRoiConfigRecord)
                .where(
                    CameraRoiConfigRecord.store_id == store_id,
                    CameraRoiConfigRecord.camera_id == camera_id,
                    CameraRoiConfigRecord.status == RoiConfigStatus.APPROVED.value,
                )
                .values(status=RoiConfigStatus.ARCHIVED.value)
            )
            target.status = RoiConfigStatus.APPROVED.value
            target.approved_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(target)
            return _roi_config_from_record(target)

    def save_scene_config(
        self,
        store_id: str,
        camera_id: str,
        config: CameraSceneConfigInput,
    ) -> CameraSceneConfig:
        """새 장면 설정을 승인하고 이전 승인본은 보관한다."""
        with self._session_factory() as session:
            existing_statement = (
                select(CameraSceneConfigRecord)
                .where(
                    CameraSceneConfigRecord.store_id == store_id,
                    CameraSceneConfigRecord.camera_id == camera_id,
                )
                .order_by(CameraSceneConfigRecord.version)
                .with_for_update()
            )
            existing = list(session.scalars(existing_statement))
            next_version = max((item.version for item in existing), default=0) + 1
            session.execute(
                update(CameraSceneConfigRecord)
                .where(
                    CameraSceneConfigRecord.store_id == store_id,
                    CameraSceneConfigRecord.camera_id == camera_id,
                    CameraSceneConfigRecord.status == SceneConfigStatus.APPROVED.value,
                )
                .values(status=SceneConfigStatus.ARCHIVED.value)
            )
            now = datetime.now(timezone.utc)
            record = CameraSceneConfigRecord(
                store_id=store_id,
                camera_id=camera_id,
                version=next_version,
                coordinate_space=config.coordinate_space,
                image_width=config.image_size.width,
                image_height=config.image_size.height,
                objects=[
                    item.model_dump(mode="json")
                    for item in config.objects
                ],
                perspective=config.perspective.model_dump(mode="json"),
                seat_anchors=[
                    item.model_dump(mode="json", exclude_none=True)
                    for item in config.seat_anchors
                ],
                source=config.source.value,
                status=SceneConfigStatus.APPROVED.value,
                approved_at=now,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return _scene_config_from_record(record)

    def get_approved_scene_config(
        self,
        store_id: str,
        camera_id: str,
    ) -> CameraSceneConfig | None:
        statement = (
            select(CameraSceneConfigRecord)
            .where(
                CameraSceneConfigRecord.store_id == store_id,
                CameraSceneConfigRecord.camera_id == camera_id,
                CameraSceneConfigRecord.status == SceneConfigStatus.APPROVED.value,
            )
            .limit(1)
        )
        with self._session_factory() as session:
            record = session.scalar(statement)
            return _scene_config_from_record(record) if record is not None else None

    def list_scene_configs(
        self,
        store_id: str,
        camera_id: str,
    ) -> list[CameraSceneConfig]:
        statement = (
            select(CameraSceneConfigRecord)
            .where(
                CameraSceneConfigRecord.store_id == store_id,
                CameraSceneConfigRecord.camera_id == camera_id,
            )
            .order_by(CameraSceneConfigRecord.version.desc())
        )
        with self._session_factory() as session:
            return [
                _scene_config_from_record(record)
                for record in session.scalars(statement)
            ]

    def approve_scene_config(
        self,
        store_id: str,
        camera_id: str,
        version: int,
    ) -> CameraSceneConfig | None:
        with self._session_factory() as session:
            target_statement = (
                select(CameraSceneConfigRecord)
                .where(
                    CameraSceneConfigRecord.store_id == store_id,
                    CameraSceneConfigRecord.camera_id == camera_id,
                    CameraSceneConfigRecord.version == version,
                )
                .with_for_update()
            )
            target = session.scalar(target_statement)
            if target is None:
                return None
            session.execute(
                update(CameraSceneConfigRecord)
                .where(
                    CameraSceneConfigRecord.store_id == store_id,
                    CameraSceneConfigRecord.camera_id == camera_id,
                    CameraSceneConfigRecord.status == SceneConfigStatus.APPROVED.value,
                )
                .values(status=SceneConfigStatus.ARCHIVED.value)
            )
            target.status = SceneConfigStatus.APPROVED.value
            target.approved_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(target)
            return _scene_config_from_record(target)


def _store_state_values(state: StoreState) -> dict:
    return {
        "store_id": state.store_id,
        "camera_id": state.camera_id,
        "frame_id": state.frame_id,
        "captured_at": state.captured_at,
        "processed_at": state.processed_at,
        "roi_version": state.roi_version,
        "visible_person_count": state.visible_person_count,
        "queue_count_estimate": state.queue_count_estimate,
        "zone_counts": state.zone_counts,
        "quality_status": state.quality_status.value,
        "source": state.source,
        "model_version": state.model_version,
    }


def _copy_store_state_values(record, state: StoreState) -> None:
    for key, value in _store_state_values(state).items():
        setattr(record, key, value)


def _find_raw_store_state(
    session: Session,
    state: StoreState,
) -> StoreStateRecord | None:
    if state.frame_id is not None:
        statement = select(StoreStateRecord).where(
            StoreStateRecord.store_id == state.store_id,
            StoreStateRecord.camera_id == state.camera_id,
            StoreStateRecord.frame_id == state.frame_id,
        )
        return session.scalar(statement)

    statement = select(StoreStateRecord).where(
        StoreStateRecord.store_id == state.store_id,
        StoreStateRecord.camera_id == state.camera_id,
        StoreStateRecord.captured_at == state.captured_at,
    )
    for existing in session.scalars(statement):
        if _store_state_from_record(existing) == state:
            return existing
    return None


def _upsert_current_store_state(session: Session, state: StoreState) -> None:
    key = (state.store_id, state.camera_id)
    current = session.get(CurrentStoreStateRecord, key)
    if current is None:
        current = CurrentStoreStateRecord(**_store_state_values(state))
        session.add(current)
        return
    _copy_store_state_values(current, state)
    current.updated_at = datetime.now(timezone.utc)


def _sample_bucket(captured_at: datetime) -> datetime:
    captured_utc = captured_at.astimezone(timezone.utc)
    second = (
        captured_utc.second // HISTORY_SAMPLE_SECONDS
    ) * HISTORY_SAMPLE_SECONDS
    return captured_utc.replace(second=second, microsecond=0)


def _hour_bucket(captured_at: datetime) -> datetime:
    return captured_at.astimezone(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )


def _upsert_history_sample(session: Session, state: StoreState) -> None:
    bucket_at = _sample_bucket(state.captured_at)
    statement = select(StoreStateHistoryRecord).where(
        StoreStateHistoryRecord.store_id == state.store_id,
        StoreStateHistoryRecord.camera_id == state.camera_id,
        StoreStateHistoryRecord.bucket_at == bucket_at,
    )
    history = session.scalar(statement)
    if history is None:
        history = StoreStateHistoryRecord(
            bucket_at=bucket_at,
            **_store_state_values(state),
        )
        session.add(history)
        return
    if state.captured_at >= history.captured_at:
        _copy_store_state_values(history, state)


def _upsert_hourly_metric(session: Session, state: StoreState) -> None:
    bucket_at = _hour_bucket(state.captured_at)
    key = (state.store_id, state.camera_id, bucket_at)
    metric = session.get(HourlyStoreMetricRecord, key)
    quality_issue = int(state.quality_status.value != "normal")
    if metric is None:
        session.add(
            HourlyStoreMetricRecord(
                store_id=state.store_id,
                camera_id=state.camera_id,
                bucket_at=bucket_at,
                observation_count=1,
                visible_person_sum=state.visible_person_count,
                queue_count_sum=state.queue_count_estimate,
                peak_visible_person_count=state.visible_person_count,
                peak_visible_person_count_at=state.captured_at,
                peak_queue_count_estimate=state.queue_count_estimate,
                peak_queue_count_estimate_at=state.captured_at,
                quality_issue_count=quality_issue,
                latest_captured_at=state.captured_at,
                latest_visible_person_count=state.visible_person_count,
                latest_queue_count_estimate=state.queue_count_estimate,
            )
        )
        return

    metric.observation_count += 1
    metric.visible_person_sum += state.visible_person_count
    metric.queue_count_sum += state.queue_count_estimate
    metric.quality_issue_count += quality_issue
    if (
        state.visible_person_count > metric.peak_visible_person_count
        or (
            state.visible_person_count == metric.peak_visible_person_count
            and state.captured_at >= metric.peak_visible_person_count_at
        )
    ):
        metric.peak_visible_person_count = state.visible_person_count
        metric.peak_visible_person_count_at = state.captured_at
    if (
        state.queue_count_estimate > metric.peak_queue_count_estimate
        or (
            state.queue_count_estimate == metric.peak_queue_count_estimate
            and state.captured_at >= metric.peak_queue_count_estimate_at
        )
    ):
        metric.peak_queue_count_estimate = state.queue_count_estimate
        metric.peak_queue_count_estimate_at = state.captured_at
    if state.captured_at >= metric.latest_captured_at:
        metric.latest_captured_at = state.captured_at
        metric.latest_visible_person_count = state.visible_person_count
        metric.latest_queue_count_estimate = state.queue_count_estimate
    metric.updated_at = datetime.now(timezone.utc)


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


def _expired_store_state_ids(
    cutoff: datetime,
    store_ids: Collection[str] | None = None,
):
    statement = select(StoreStateRecord.id).where(
        StoreStateRecord.captured_at < cutoff
    )
    if store_ids is not None:
        statement = statement.where(
            StoreStateRecord.store_id.in_(store_ids)
        )
    return statement


def _store_state_from_record(record) -> StoreState:
    return StoreState(
        store_id=record.store_id,
        camera_id=record.camera_id,
        frame_id=record.frame_id,
        captured_at=record.captured_at,
        processed_at=record.processed_at,
        roi_version=record.roi_version,
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


def _roi_config_from_record(record: CameraRoiConfigRecord) -> CameraRoiConfig:
    return CameraRoiConfig(
        store_id=record.store_id,
        camera_id=record.camera_id,
        version=record.version,
        coordinate_space=record.coordinate_space,
        image_size={
            "width": record.image_width,
            "height": record.image_height,
        },
        zones=record.zones,
        source=record.source,
        status=record.status,
        created_at=record.created_at,
        approved_at=record.approved_at,
    )


def _scene_config_from_record(record: CameraSceneConfigRecord) -> CameraSceneConfig:
    return CameraSceneConfig(
        store_id=record.store_id,
        camera_id=record.camera_id,
        version=record.version,
        coordinate_space=record.coordinate_space,
        image_size={
            "width": record.image_width,
            "height": record.image_height,
        },
        objects=record.objects,
        perspective=record.perspective,
        seat_anchors=record.seat_anchors,
        source=record.source,
        status=record.status,
        created_at=record.created_at,
        approved_at=record.approved_at,
    )
