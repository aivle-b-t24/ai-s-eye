# Vision Worker

기존 YOLO 추론 결과를 StoreState 형식으로 변환하고 공통 API로 전송하는 영역이다.

공통 계약:

- Schema: `packages/contracts/store_state.schema.json`
- 샘플: `samples/store_state.json`
- 전송 API: `POST /internal/store-states`

영상과 모델 가중치는 이 저장소에 추가하지 않는다.

## 팀원용: 영상 없이 매장 상태 재생하기

영상·YOLO·GPU 없이도 실제 분석 결과를 API에 흘려보낼 수 있다. 대시보드나 AICC를
개발할 때 매장 인원이 계속 변하는 상황을 만들 수 있다.

미리 분석해 둔 결과가 `results/merged_all_states.json`에 있고,
`replay_states.py`가 그 값을 순서대로 API에 전송한다.
파이썬 표준 라이브러리만 사용하므로 따로 설치할 패키지가 없다.

```bash
docker compose up -d                              # API 먼저 실행
python services/vision-worker/replay_states.py
```

주요 옵션:

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--file` | 재생할 결과 JSON 경로 | `results/merged_all_states.json` |
| `--api` | API 주소 | `http://localhost:8000` |
| `--interval` | 전송 간격(초) | `2` |
| `--limit` | 앞에서 N건만 전송 | 전체 |
| `--loop` | 끝나면 처음부터 반복 | 꺼짐 |

상황별 실행 예시:

```bash
# 잘 동작하는지 빠르게 확인 (5건만, 0.5초 간격)
python services/vision-worker/replay_states.py --limit 5 --interval 0.5

# 한 건만 보내고 값을 고정해 두기 (화면 확인용)
python services/vision-worker/replay_states.py --limit 1

# 개발 중 값이 계속 바뀌게 두기 (2초 간격, 끝나면 반복)
python services/vision-worker/replay_states.py --interval 2 --loop

# 시연용 - 원본 촬영 속도(2fps)와 동일, 약 5분 20초마다 반복
python services/vision-worker/replay_states.py --interval 0.5 --loop

중단은 `Ctrl+C`.

전송한 값은 다음으로 확인한다.

```bash
curl http://localhost:8000/api/stores/store-001/state
curl http://localhost:8000/api/stores/store-001/eta
```

대시보드는 화면을 열 때 값을 한 번 읽어오므로, 재생 중 값이 바뀌는 것을 보려면
새로고침하거나 대시보드에 주기적 재조회를 넣어야 한다.

## 분석 결과 데이터

`results/merged_all_states.json`은 카페 매장 CCTV 4대를 분석해 매장 단위로
합친 결과 636건이다. 인원은 17~36명, 대기 인원은 1~14명 범위로 변한다.

`zone_counts` 키는 `구역_층` 형식이다.

| 키 | 뜻 |
|---|---|
| `waiting_out` | 매장 외부 대기 줄 인원 |
| `seating_1f` / `seating_2f` | 1층 / 2층 좌석 구역 인원 |
| `counter_1f` | 1층 주문(카운터) 구역 인원 |
| `aisle_1f` / `aisle_2f` | 1층 / 2층 통로 인원 |
| `staff_1f` | 1층 직원 구역 인원 |

`queue_count_estimate`는 외부 대기 구역 인원이며, API의 예상 대기시간 계산에 쓰인다.

주의: 원본 데이터셋에 촬영 시각이 없어 `captured_at`은 프레임 간격(0.5초)만큼
증가하도록 만든 합성값이다. 실제 촬영 시각이 아니므로 시간대별 분석에 그대로
쓰지 않는다.