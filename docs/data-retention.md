# StoreState 적재 및 보관 기준

## 목적

점주 화면은 매장의 가장 최근 상태가 필요하고, 슈퍼바이저 화면은 일정 기간의
변화와 특이사항을 분석할 이력이 필요하다. 두 용도를 구분하면서 개발용 반복
재생 데이터가 PostgreSQL에 무제한 쌓이지 않도록 기준을 정한다.

## 현재 적재량

2026년 7월 27일 미니PC 기준으로 반복 재생을 약 5일 실행한 결과는 다음과 같다.

| 매장 | StoreState 건수 |
|---|---:|
| store-001 | 68,646건 |
| store-002 | 51,004건 |
| 합계 | 119,650건 |

2초마다 한 건을 저장하면 매장 하나당 하루 최대 43,200건, 두 매장은 하루 최대
86,400건이 추가된다. 데이터가 계속 쌓인 상태에서 전체 기간 집계를 호출하면
확인 당시 약 2초가 걸렸다.

## MVP 운영 기준

- 점주 화면은 `GET /api/stores/{store_id}/state`에서 매장별 최신 상태 한 건을
  사용한다.
- 슈퍼바이저 기본 집계 기간은 최근 24시간이다.
- `GET /api/stores/summary`에 기간을 생략하면 서버가 현재 시각을 기준으로 최근
  24시간을 조회한다.
- 필요한 경우 `start_at`, `end_at`을 함께 전달해 다른 기간을 명시할 수 있다.
- 개발용 Vision replay는 기능 개발·통합 테스트·시연 중에만 실행한다.
- 평소 개발 확인에는 5~10초 간격을 사용할 수 있고, 2초 간격은 실시간 변화
  시연이 필요할 때 사용한다.
- 원본 StoreState의 MVP 보관 기준은 7일이다.
- `current_store_states`에는 매장·카메라별 마지막 수신 상태 한 건만 유지한다.
- `store_state_history`에는 30초 구간별 마지막 상태 한 건을 유지한다.
- `hourly_store_metrics`에는 시간 단위 합계·평균 계산값을 누적한다.
- 원본 2초 상태인 `store_states`만 7일 뒤 자동 정리한다.

## 안전한 정리 방법

정리 전에는 먼저 PostgreSQL을 백업한다. 다음 명령은 삭제하지 않고 7일보다
오래된 정리 대상 건수만 보여준다.

```bash
docker compose exec api python -m app.cleanup_store_states
```

출력 건수와 백업을 확인한 다음에만 실제 정리를 실행한다.

```bash
docker compose exec api python -m app.cleanup_store_states --apply
```

보관기간을 다르게 확인하려면 다음처럼 지정한다.

```bash
docker compose exec api python -m app.cleanup_store_states \
  --older-than-days 14
```

`--apply`가 없으면 데이터는 삭제되지 않는다. Docker Compose에서는
`store-state-cleanup` 서비스가 기본 6시간마다 실행되고, 보관일수와 주기는
`STORE_STATE_RETENTION_DAYS`, `STORE_STATE_CLEANUP_INTERVAL_SECONDS`로 변경한다.

장기 운영 시에는 시간 집계를 일·주·월 집계로 한 번 더 압축하고, 삭제 작업
실패를 모니터링 대상으로 추가한다.
