# Vision Worker

기존 YOLO 추론 결과를 StoreState 형식으로 변환하고 공통 API로 전송하는 영역이다.

공통 계약:

- Schema: `packages/contracts/store_state.schema.json`
- 샘플: `samples/store_state.json`
- 전송 API: `POST /internal/store-states`

영상과 모델 가중치는 이 저장소에 추가하지 않는다.

