# API Service

FastAPI 기반 공통 백엔드다.

현재 API는 메모리와 `samples` JSON을 사용한다. PostgreSQL 초기 테이블과
마이그레이션은 준비되어 있지만, Repository를 PostgreSQL로 교체하는 작업은
다음 단계에서 진행한다.

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
