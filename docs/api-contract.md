# 공통 API 계약 0.1

이 문서는 비전, AICC, 프론트엔드가 독립적으로 개발할 때 사용하는 첫 번째 공통 계약이다. 변경이 필요하면 각 기능에서 임의로 수정하지 않고 팀에 제안한다.

기본 주소는 `http://localhost:8000`이다.

## GET /health

API와 PostgreSQL 연결 상태를 확인한다.

응답 예시:

```json
{
  "status": "ok",
  "environment": "development",
  "database": "ok"
}
```

`database` 값은 `ok`, `not_configured`, `unavailable` 중 하나다.

## POST /internal/store-states

비전 Worker 또는 시뮬레이터가 최신 매장 상태를 전송한다.

요청 예시는 `samples/store_state.json`을 사용한다.

주요 규칙:

- 인원 수는 0 이상의 정수다.
- `visible_person_count`는 CCTV에서 보이는 인원이며 정확한 고객 수로 단정하지 않는다.
- 시각은 ISO 8601 형식을 사용한다.
- `quality_status`는 `normal`, `low`, `stale`, `unknown` 중 하나다.

성공 상태 코드는 `201 Created`다.

## POST /internal/order-events

POS/KDS 또는 주문 시뮬레이터가 주문 상태 변경을 전송한다.

요청 예시는 `samples/order_event.json`을 사용한다.

허용 상태:

- `received`
- `preparing`
- `ready`
- `completed`
- `cancelled`
- `rejected`

성공 상태 코드는 `202 Accepted`다.

## GET /api/orders/{order_id}

주문번호의 가장 최근 주문 상태를 반환한다.

주문 이벤트가 여러 건이면 `occurred_at`이 가장 늦은 이벤트를 반환한다.
주문이 없으면 `404`를 반환한다.

응답 예시:

```json
{
  "event_id": "event-002",
  "order_id": "order-001",
  "store_id": "store-001",
  "occurred_at": "2026-07-20T10:33:00+09:00",
  "status": "ready",
  "items": [
    {
      "menu_id": "menu-001",
      "name": "아메리카노",
      "quantity": 1
    }
  ]
}
```

## GET /api/stores/{store_id}/state

해당 매장의 가장 최근 StoreState를 반환한다. 상태가 없으면 `404`를 반환한다.

기본 mock 매장은 `store-001`이다.

## GET /api/stores/{store_id}/eta

해당 매장의 임시 예상 대기시간을 반환한다.

현재 규칙:

`estimated_wait_minutes = queue_count_estimate * 3`

이 규칙은 기능 연결을 위한 mock이며 실제 ETA 기준은 DB·주문 흐름을 확정한 뒤 교체한다.

응답 예시:

```json
{
  "store_id": "store-001",
  "estimated_wait_minutes": 6,
  "calculation": "queue_count_estimate * 3",
  "data_source": "mock_rule"
}
```

## GET /api/stores/{store_id}/menus

`samples/menus.json`의 mock 메뉴를 반환한다.

응답에는 다음 필드가 포함된다.

- `store_id`
- `data_source`
- `menus`

## GET /api/stores/{store_id}/policies

`samples/policies.json`의 mock 정책을 반환한다.

현재 정책 범위는 영업시간, 주차, 주문 취소·환불, 포장, 반려동물이다.

## 오류 처리

- 입력 형식 오류: `422 Unprocessable Entity`
- 존재하지 않는 매장 상태: `404 Not Found`
- 샘플 파일 누락: `503 Service Unavailable`

## 공통 Schema

- `packages/contracts/store_state.schema.json`
- `packages/contracts/order_event.schema.json`
