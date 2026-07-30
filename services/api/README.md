# API Service

FastAPI 기반 공통 백엔드다.

매장 상태와 주문 이벤트는 `DATABASE_URL`이 설정된 환경에서 PostgreSQL에
저장한다. `DATABASE_URL`이 없는 단위 테스트 환경에서는 메모리 저장소를
사용한다. 메뉴와 정책은 현재 `samples` JSON을 사용한다.

API 문서는 서버 실행 후 `http://localhost:8000/docs`에서 확인한다.

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
