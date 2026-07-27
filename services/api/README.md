# API Service

FastAPI 기반 공통 백엔드다.

매장 상태와 주문 이벤트는 `DATABASE_URL`이 설정된 환경에서 PostgreSQL에
저장한다. `DATABASE_URL`이 없는 단위 테스트 환경에서는 메모리 저장소를
사용한다. 메뉴와 정책은 현재 `samples` JSON을 사용한다.

API 문서는 서버 실행 후 `http://localhost:8000/docs`에서 확인한다.

## Vision 분석 이미지

Vision Worker는 분석이 끝난 JPEG 또는 PNG 한 장을 매장별 업로드 API로 보낸다.
서버는 이 이미지를 PostgreSQL에 넣지 않고 매장별 최신 파일 하나로 관리한다.

```bash
curl -X POST \
  -F "image=@annotated.jpg" \
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

슈퍼바이저 집계의 기본 기간은 최근 24시간이며 원본 StoreState의 MVP 보관 기준은
7일이다. 정리 도구는 기본적으로 삭제하지 않고 대상 건수만 보여준다.

```bash
docker compose exec api python -m app.cleanup_store_states
```

백업과 대상 건수를 확인한 다음에만 `--apply`를 사용한다.

```bash
docker compose exec api python -m app.cleanup_store_states --apply
```

자세한 운영 기준은
[`docs/data-retention.md`](../../docs/data-retention.md)에서 확인한다.
