# API Service

FastAPI 기반 공통 백엔드다.

매장 상태와 주문 이벤트는 `DATABASE_URL`이 설정된 환경에서 PostgreSQL에
저장한다. `DATABASE_URL`이 없는 단위 테스트 환경에서는 메모리 저장소를
사용한다. 메뉴와 정책은 현재 `samples` JSON을 사용한다.

API 문서는 서버 실행 후 `http://localhost:8000/docs`에서 확인한다.

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
