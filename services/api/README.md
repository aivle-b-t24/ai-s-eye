# API Service

FastAPI 기반 공통 백엔드다.

매장 상태와 주문 이벤트는 `DATABASE_URL`이 설정된 환경에서 PostgreSQL에
저장한다. `DATABASE_URL`이 없는 단위 테스트 환경에서는 메모리 저장소를
사용한다. 메뉴와 정책은 현재 `samples` JSON을 사용한다.

API 문서는 서버 실행 후 `http://localhost:8000/docs`에서 확인한다.

기간별 매장 집계의 `order_summary.data_sources`는 합성 주문과 일반 주문 이벤트를
구분한다. 매장 타임라인은 `interval=1h`와 `interval=1d`를 지원한다.

## 주문 CSV 다운로드

기간 내 주문 상태 이벤트를 주문 한 건당 한 행으로 합쳐 CSV로 내려받는다. 시간은
한국시간으로 표시하며 합성 주문은 `data_source=synthetic_order_simulator`와
`simulation_run_id`로 구분한다. 한 번에 최대 31일까지 요청할 수 있다.

```bash
curl --get http://localhost:8000/api/exports/orders.csv \
  --data-urlencode 'start_at=2026-07-01T00:00:00+09:00' \
  --data-urlencode 'end_at=2026-07-31T00:00:00+09:00' \
  --output synthetic_orders_2026-07.csv
```

## 합성 데모 주문 생성기

주문 시뮬레이터는 DB에 직접 접근하지 않고 실제 POS/KDS가 사용할
`POST /internal/order-events`로 주문 상태를 보낸다. 매장별 메뉴 API에서
판매 가능한 메뉴만 읽어 `received → preparing → ready → completed` 순서로
저장한다.

실시간 데모 주문은 프로젝트 루트에서 실행한다.

```bash
docker compose up -d db api
docker compose exec api alembic upgrade head
docker compose --profile demo up -d --build order-simulator
docker compose logs -f order-simulator
```

완전히 새 DB라면 Alembic 적용이 선행되어야 한다. 시뮬레이터는 시작할 때
PostgreSQL 연결뿐 아니라 집계 테이블 조회까지 확인하고, 스키마가 준비되지
않았으면 주문을 생성하지 않고 종료한다.

본사 기간 분석용 과거 7일 데이터는 먼저 미리보기로 생성 건수만 확인한다.

```bash
docker compose --profile demo run --rm order-simulator \
  python -m app.order_simulator seed \
  --days 7 \
  --seed 20260730
```

실제 적재는 데모 DB임을 확인한 뒤 `--apply`를 붙여 실행한다.

```bash
docker compose --profile demo run --rm order-simulator \
  python -m app.order_simulator seed \
  --days 7 \
  --seed 20260730 \
  --apply
```

기본적으로 한국시간 기준 어제까지 생성한다. 같은 기간과 seed로 다시 실행하면
같은 `event_id`가 만들어지므로 중복 저장되지 않는다. 다른 데이터 세트를 만들
때만 `--seed` 또는 `--run-id`를 바꾼다.

```bash
docker compose --profile demo run --rm order-simulator \
  python -m app.order_simulator seed \
  --days 30 \
  --end-date 2026-07-29 \
  --run-id seed-july \
  --apply
```

실시간 주문 간격은 `ORDER_SIM_SCENARIO=normal|lunch_peak`, 재생 속도는
`ORDER_SIM_SPEED`로 조정한다. 시뮬레이터는 `demo` 프로필 서비스라 로컬의 일반
`docker compose up -d`에는 포함되지 않지만 미니PC와 GCP 데모 배포에서는
자동으로 실행한다.

생성 주문은 `sim-` 접두사로 식별되지만 현재 본사 집계에서는 실제 주문과 함께
계산된다. 실제 POS 실적이 아닌 합성 데모 데이터라는 표시를 유지해야 한다. 이
모듈은 주문 이벤트 생성기이며 직원, 제조 자원, 대기열, 좌석, 이탈을 계산하는
What-if 운영 시뮬레이터는 아니다.

## What-if 운영 시뮬레이션

`POST /api/simulations/operations`는 직원 수, 방문율, 행사 배수, 평균 제조시간,
대기 인내시간, 좌석 수를 입력받아 SimPy로 운영 결과를 계산한다. 결과에는 완료·포기
주문, 평균 대기, 최대 대기열, 직원·좌석 가동률과 디지털 트윈 재생 프레임이 포함된다.

동일한 입력과 `seed`는 동일한 가상 고객과 결과를 만든다. 서로 다른 직원 수를
비교해도 방문 시각과 고객별 서비스 성향은 동일하게 유지한다. 엔드포인트는 계산만
수행하며 PostgreSQL이나 실제 `StoreState`, `OrderEvent`에는 기록하지 않는다.

## Vision 분석 이미지

Vision Worker는 분석이 끝난 JPEG 또는 PNG 한 장과 프레임 메타데이터를 매장별
업로드 API로 보낸다.
서버는 이 이미지를 PostgreSQL에 넣지 않고 매장별 최신 파일 하나로 관리한다.

```bash
curl -X POST \
  -F "image=@annotated.jpg" \
  -F 'metadata={"store_id":"store-001","camera_id":"store-001-cam1","frame_id":"store-001-0001","captured_at":"2026-07-30T09:00:00+09:00","processed_at":"2026-07-30T09:01:00+09:00","model_version":"yolo11s-cafe-ft+pose-dwell","roi_version":7,"source":"demo-replay"}' \
  http://localhost:8000/internal/stores/store-001/vision-snapshot
```

대시보드는 아래 주소를 이미지 `src`로 사용한다.

```text
http://localhost:8000/api/stores/store-001/vision/latest
```

기본 지원 매장은 `store-001`, `store-002`이며 한 파일의 최대 크기는 5MB다.
Docker에서는 `vision_snapshot_data` 볼륨에 최신 파일을 저장하므로 API 컨테이너를
다시 만들어도 유지된다. 새 이미지가 들어오면 이전 이미지는 교체하며 이력을
쌓지는 않는다.

이미지 신원은 아래 주소에서 확인한다.

```text
http://localhost:8000/api/stores/store-001/vision/metadata
```

## PostgreSQL 마이그레이션

프로젝트 루트에서 API와 DB를 먼저 실행한다.

```bash
docker compose up -d --build db api
docker compose exec api alembic upgrade head
```

현재 적용된 버전과 테이블은 아래 명령으로 확인한다.

```bash
docker compose exec api alembic current
docker compose exec db psql -U store -d store -c '\\dt'
```

새로운 스키마 변경은 기존 마이그레이션 파일을 수정하지 않고 새 파일로 추가한다.

```bash
docker compose exec api alembic revision -m "변경 내용"
```

## StoreState 보관

`current_store_states`는 마지막 수신 상태, `store_state_history`는 30초 샘플,
`hourly_store_metrics`는 시간 집계, `store_states`는 7일 보관 원본이다.
슈퍼바이저 집계는 샘플 이력을 사용한다.

```bash
docker compose exec api python -m app.cleanup_store_states
```

백업과 대상 건수를 확인한 다음에만 `--apply`를 사용한다.

```bash
docker compose exec api python -m app.cleanup_store_states --apply
```

Docker의 `store-state-cleanup` 서비스는 같은 정리를 기본 6시간마다 자동 실행한다.

자세한 운영 기준은
[`docs/data-retention.md`](../../docs/data-retention.md)에서 확인한다.
