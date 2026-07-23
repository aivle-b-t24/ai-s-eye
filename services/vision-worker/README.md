# Vision Worker

기존 YOLO 추론 결과를 StoreState 형식으로 변환하고 공통 API로 전송하는 영역이다.

공통 계약:

- Schema: `packages/contracts/store_state.schema.json`
- 샘플: `samples/store_state.json`
- 전송 API: `POST /internal/store-states`

영상과 모델 가중치는 이 저장소에 추가하지 않는다.

## CAFE 다매장(프랜차이즈) 파이프라인

프로젝트 방향이 "카페노아 단일 매장" → "프랜차이즈 본점의 다매장 실내 혼잡도 관리"로
바뀌면서, CAFE 데이터셋의 서로 다른 카페를 franchise 매장으로 보고 집계한다. 현재는
대표 매장 2곳(`store-102`, `store-106`)을 운영한다. 배경은 [CAFE 데이터셋 적합성 검토](성능평가/CAFE_데이터셋_적합성_검토.md).

- 모델: CAFE로 파인튜닝한 `yolo11s`(전신 라벨 → 발 위치 산출). 가중치 경로는
  `AISEYE_CAFE_MODEL`, 데이터 경로는 `AISEYE_CAFE_ROOT` 환경변수로 지정.
- 집계: **인원수 = 파인튜닝 탐지 − 직원(손님)**, **대기 = 대기 구역 + 서있음(pose) +
  체류(ByteTrack)**, **직원 = 직원 구역(카운터 뒤)**. 구역은 `zones/<store_id>_zones.json`.
- **매장을 늘리려면** `cafe_stores.py`의 `STORES`에 항목을 추가하고 해당 매장 zones를
  그린 뒤 다시 실행한다.

```bash
py services/vision-worker/cafe_stores.py             # 전체 클립 → samples/ 저장(재생용)
py services/vision-worker/cafe_stores.py --limit 60  # 앞 60세그만(빠른 확인)
```

결과는 세그먼트 순서를 시간축으로 매장을 교차 배치해
`samples/cafe_stores_states.json`에 저장한다(아래 재생에 사용).

> 참고: CAFE엔 촬영 시각이 없어 `captured_at`은 세그먼트 간격(0.5초)만큼 증가시킨
> 합성값이다. 대기는 서있음+체류라 추적(ByteTrack)이 필요해 전체 생성에 시간이 걸린다.

## 팀원용: 영상 없이 매장 상태 재생하기

영상·YOLO·GPU 없이도 실제 분석 결과를 API에 흘려보낼 수 있다. 대시보드나 AICC를
개발할 때 매장 인원이 계속 변하는 상황을 만들 수 있다.

미리 분석해 둔 결과(`samples/cafe_stores_states.json`, CAFE 다매장 6개 매장)를
`replay_states.py`가 순서대로 API에 전송한다.
파이썬 표준 라이브러리만 사용하므로 따로 설치할 패키지가 없다.

```bash
docker compose up -d                              # API 먼저 실행
python services/vision-worker/replay_states.py    # 기본: samples/cafe_stores_states.json
```

주요 옵션:

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--file` | 재생할 결과 JSON 경로 | `samples/cafe_stores_states.json` |
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
curl http://localhost:8000/api/stores/store-102/state
curl http://localhost:8000/api/stores/store-102/eta
```

대시보드는 화면을 열 때 값을 한 번 읽어오므로, 재생 중 값이 바뀌는 것을 보려면
새로고침하거나 대시보드에 주기적 재조회를 넣어야 한다.

## 분석 결과 데이터

`samples/cafe_stores_states.json`은 CAFE 데이터셋의 서로 다른 카페를 프랜차이즈
매장으로 보고 집계한 결과다. 현재는 `store-102`, `store-106` 2곳이다.

| 키 | 뜻 |
|---|---|
| `waiting` | 카운터 앞 대기 인원 (구역+서있음+체류) |
| `staff` | 직원(카운터 뒤) 인원 — 손님 수에서 제외 |

`visible_person_count`는 손님 수(전체 탐지 − 직원), `queue_count_estimate`는 대기 인원이다.

`queue_count_estimate`는 외부 대기 구역 인원이며, API의 예상 대기시간 계산에 쓰인다.

주의: 원본 데이터셋에 촬영 시각이 없어 `captured_at`은 프레임 간격(0.5초)만큼
증가하도록 만든 합성값이다. 실제 촬영 시각이 아니므로 시간대별 분석에 그대로
쓰지 않는다.

## 성능 평가

- [4주차 YOLO 성능평가](성능평가/4주차_YOLO_성능평가.md)