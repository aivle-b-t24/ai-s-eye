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
매장·카메라·측정 시각과 나머지 값까지 모두 같은 상태를 다시 보내면
PostgreSQL에 중복 이력을 추가하지 않는다.

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

## POST /internal/stores/{store_id}/vision-snapshot

Vision Worker가 사람 탐지 박스와 ROI를 표시한 최신 분석 이미지를 전송한다.
요청은 `multipart/form-data`이며 `image` 필드에 JPEG 또는 PNG 파일을 넣는다.

기본 지원 매장은 `store-001`, `store-002`이고 파일 최대 크기는 5MB다. 새 이미지를
받으면 해당 매장의 기존 최신 이미지를 교체한다. 이미지 파일은 PostgreSQL에
저장하지 않는다.

성공 상태 코드는 `201 Created`다.

## GET /api/stores/{store_id}/vision/latest

해당 매장의 가장 최근 Vision 분석 이미지를 반환한다. 아직 업로드된 이미지가
없으면 `404`를 반환한다. 브라우저 캐시로 이전 이미지가 계속 보이지 않도록
응답에 `Cache-Control: no-store`를 포함한다.

## POST /internal/stores/{store_id}/vision-raw

ROI 설정에 사용할 탐지 박스·기존 ROI 오버레이가 없는 원본 CCTV 프레임을 전송한다.
요청 형식과 용량 제한은 분석 이미지 업로드와 동일하다. 분석 이미지와 원본 이미지는
서로 다른 최신 파일로 보관하며 PostgreSQL에는 저장하지 않는다.

## GET /api/stores/{store_id}/vision/raw/latest

해당 매장의 최신 원본 CCTV 프레임을 반환한다. ROI 편집기는 이 주소만 사용하며,
원본이 없을 때 분석 이미지로 자동 대체하지 않는다.

## GET /api/stores/{store_id}/orders/{order_id}

매장 ID와 주문번호가 모두 일치하는 가장 최근 주문 상태를 반환한다.

서로 다른 매장에서 같은 주문번호를 사용해도 매장별로 구분해서 조회한다.
주문이 없으면 `404`를 반환한다.

## GET /api/orders/{order_id}

주문번호의 가장 최근 주문 상태를 반환한다.

주문 이벤트가 여러 건이면 `occurred_at`이 가장 늦은 이벤트를 반환한다.
주문이 없으면 `404`를 반환한다.

기존 연동을 위한 호환 API이며, 다중 매장 기능에서는 매장별 주문 조회 API를
사용한다.

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

## GET /api/stores/{store_id}/timeline

해당 매장의 상태와 신규 주문을 지정한 기간 동안 1시간 단위로 집계한다.

필수 쿼리:

- `start_at`: 시간대가 포함된 ISO 8601 시작 시각
- `end_at`: 시간대가 포함된 ISO 8601 종료 시각
- `interval`: 현재 `1h`만 지원하며 생략하면 `1h`

각 구간에는 관측 건수, 평균·피크 인원, 평균·피크 대기 인원, 신규 주문 수,
영상 이상 건수가 포함된다. 상태 데이터가 없는 구간은 관측값을 `null`로 반환해
실제 0명과 데이터 부재를 구분한다. 주문 수는 `received` 상태로 접수된 고유
주문번호를 센다. 조회 기간은 최대 31일이다.

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

`samples/menus.json`에서 해당 매장의 mock 메뉴만 반환한다.

응답에는 다음 필드가 포함된다.

- `store_id`
- `data_source`
- `menus`

해당 매장의 메뉴가 없으면 `menus`는 빈 목록이다.

## GET /api/stores/{store_id}/policies

`samples/policies.json`에서 해당 매장의 mock 정책만 반환한다.

현재 정책 범위는 영업시간, 주차, 주문 취소·환불, 포장, 반려동물이다.
해당 매장의 정책이 없으면 `policies`는 빈 목록이다.

## GET /api/stores/summary

PostgreSQL에 저장된 상태와 주문 이력을 기간별·매장별로 집계한다.
슈퍼바이저 대시보드와 AI 운영 분석이 함께 사용하는 사실 기반 응답이다.

선택 쿼리:

- `start_at`: 집계 시작 시각
- `end_at`: 집계 종료 시각

두 시각은 시간대를 포함한 ISO 8601 형식으로 함께 전달해야 한다. 둘 다 생략하면
현재 시각을 기준으로 최근 24시간을 집계한다. 전체 기간이나 다른 기간이 필요하면
`start_at`, `end_at`을 함께 지정한다.

매장별 응답에는 다음 묶음이 포함된다.

- `traffic_summary`: 최신·평균·최대 인원과 대기 인원
- `order_summary`: 실제 주문 수, 이벤트 수, 최신 상태 분포, 인기 메뉴
- `video_summary`: 최신 영상 상태와 이상 상태 횟수

실제 주문 수와 인기 메뉴는 주문별 최신 이벤트를 기준으로 계산해
접수·제조·완료 상태 변경에 따른 중복을 제거한다.
취소되거나 거절된 주문은 인기 메뉴 수량에서 제외한다.

PostgreSQL이 설정되지 않은 환경에서는 `503`을 반환한다.

## 두 매장 데모 시나리오 적재

Docker의 API와 PostgreSQL을 빌드해 실행한 뒤 다음 명령으로
`samples/franchise_scenario.json`의 상태 8건과 주문 6건을 적재한다.

```bash
docker compose up -d --build db api
docker compose exec api alembic upgrade head
docker compose exec api python -m app.scenario_loader
```

도구는 파일 전체를 공통 모델로 먼저 검증하고, 기존 내부 API를 통해 데이터를
전송한다. 전송 후에는 같은 기간의 집계 API를 확인해 매장별 최대 인원과
최대 대기 인원을 출력한다.

동일한 시나리오를 다시 실행해도 같은 상태와 주문 이벤트는 중복 저장하지 않는다.
`expected_insights`는 AI 결과 검증용이므로 PostgreSQL에 넣지 않는다.

## 오류 처리

- 입력 형식 오류: `422 Unprocessable Entity`
- 존재하지 않는 매장 상태: `404 Not Found`
- 샘플 파일 누락: `503 Service Unavailable`

## 공통 Schema

- `packages/contracts/store_state.schema.json`
- `packages/contracts/order_event.schema.json`
- `packages/contracts/camera_roi_config.schema.json`
## 카메라 ROI 설정

ROI 좌표는 이미지 해상도와 무관한 `normalized_1000` 좌표계를 사용한다.
왼쪽 위가 `(0, 0)`, 오른쪽 아래가 `(1000, 1000)`이다.

- `GET /api/stores/{store_id}/cameras/{camera_id}/roi-config`: 현재 승인본
- `PUT /api/stores/{store_id}/cameras/{camera_id}/roi-config`: 새 버전 저장·적용
- `GET /api/stores/{store_id}/cameras/{camera_id}/roi-configs`: 버전 이력
- `POST /api/stores/{store_id}/cameras/{camera_id}/roi-configs/{version}/approve`: 이전 버전 재적용
- `GET /internal/stores/{store_id}/cameras/{camera_id}/roi-config`: Vision용 승인본

지원 구역은 `staff`, `waiting`, `entrance`, `seating`이다. 폴리곤은 꼭짓점
3~20개로 구성하며 좌표 범위, 면적, 자기 교차 여부를 API가 검증한다.

점주는 원본 프레임 위에서 구역을 직접 그린다. `waiting`은 이미지 한 장만으로
결정하지 않고 사람 추적·체류 자료와 실제 매장 운영 기준을 함께 참고한다.

```json
{
  "coordinate_space": "normalized_1000",
  "image_size": {"width": 1920, "height": 1080},
  "source": "manual",
  "zones": [
    {
      "id": "staff-1",
      "type": "staff",
      "label": "직원 구역",
      "polygon": [
        {"x": 530, "y": 20},
        {"x": 995, "y": 20},
        {"x": 995, "y": 540}
      ]
    }
  ]
}
```

## CCTV 디지털 트윈

별도 매장 도면을 가정하지 않고 원본 CCTV 화면을 공간 기준으로 사용한다.
Vision Worker는 사람의 발 좌표를 이미지 너비·높이에 대한 `0~1` 좌표로 정규화해
`POST /internal/stores/{store_id}/occupancy`로 보낸다.

`GET /api/stores/{store_id}/occupancy/latest`는 해당 카메라의 최신 위치를 반환한다.
각 사람에는 `track_id`, 역할, 상태와 ROI 구역이 포함된다. 대시보드는 승인된 ROI,
발 좌표와 최근 이동 궤적을 원본 CCTV 이미지 위에 표시한다.

도면 좌표 변환이나 여러 카메라 위치의 공간 통합은 현재 범위에 포함하지 않는다.
