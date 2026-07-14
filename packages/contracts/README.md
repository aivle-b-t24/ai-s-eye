# 공통 데이터 계약

비전, 백엔드, AICC, 프론트엔드가 공유하는 JSON 형식을 관리한다.

- `store_state.schema.json`: 비전 또는 시뮬레이터가 전송하는 매장 상태
- `order_event.schema.json`: POS/KDS가 전송하는 주문 이벤트

공통 필드 변경이 필요하면 구현 코드보다 계약 문서를 먼저 검토한다.
