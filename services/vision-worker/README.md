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
대표 매장 2곳(`store-001`, `store-002`)을 운영한다. 배경은 [CAFE 데이터셋 적합성 검토](성능평가/CAFE_데이터셋_적합성_검토.md).

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

## MVP 제공 값 / 미지원 값

대시보드가 참고하도록, 현재 Vision 모델이 **실제로 제공하는 값**과 **아직 제공하지
못하는 값**을 구분한다. StoreState에는 아래 "제공 값"만 채우고, 미지원 값은 넣지 않는다.

**제공 값 (안정적)**

| 값 | StoreState 필드 | 산출 |
|---|---|---|
| 전체(손님) 인원 | `visible_person_count` | 파인튜닝 탐지 − 직원 |
| 직원 인원 | `zone_counts.staff` | 직원 구역(카운터 뒤) 탐지 |
| 대기 인원 | `queue_count_estimate` = `zone_counts.waiting` | 대기 구역 + 서있음 + 체류 |

**미지원 값 (현재 제공 못 함 — StoreState에 넣지 않음)**

- 좌석 점유(테이블별), 통로 인원, 카운터 주문 세부, **입·퇴장 이벤트**
- 대시보드에 이런 항목이 보이면 Vision 산출값이 아니라 UI 표현/목업이다.

**quality_status 기준** — "사람 0명"과 "영상 이상"을 구분한다.

- `normal`: 정상 프레임. **사람이 0명이어도 정상**(빈 매장).
- `low`: 프레임 디코드 실패 또는 거의 검은 화면(카메라 꺼짐·가림) = 영상 이상.

**ROI 기준** — 매장별 `zones/<store_id>_zones.json`에 지정.

- **대기** = 대기 구역(카운터 앞) 안에서 서있고 N프레임 이상 체류한 사람.
- **직원** = 직원 구역(카운터 뒤) 탐지(손님 수에서 제외).

**모델·가중치**

- 모델: `yolo11s-cafe-ft`(탐지) + `yolo11s-pose`(서있음/추적). `model_version` 필드에 기록.
- 가중치(`best.pt`)와 원본 이미지·영상은 **GitHub에 올리지 않는다**(드라이브 공유).
  경로는 `AISEYE_CAFE_MODEL`(가중치) / `AISEYE_CAFE_ROOT`(이미지) 환경변수로 지정.

## 대시보드용 분석 이미지(스냅샷)

대시보드 카메라 영역에 목업 대신 **실제 분석 이미지**(사람 탐지 + 직원/대기 ROI)를 띄운다.
백엔드 이미지 API(#85)와 연동한다.

**API 계약(백엔드 #85)**

- 업로드(vision → 서버): `POST /internal/stores/{store_id}/vision-snapshot` (multipart, form field `image`)
- 조회(대시보드): `GET /api/stores/{store_id}/vision/latest` → `image/jpeg`
- 매장별 **최신 1장만** 보관(이력 없음), 최대 5MB.

**생성 + 재생(이미지·숫자 동기)** — 미리 생성해 두고 재생하며 업로드(재생엔 GPU 불필요):
```bash
# 1) GPU 머신에서 상태 + 분석 이미지 배치 생성 (1회)
python services/vision-worker/cafe_stores.py
#    → samples/cafe_stores_states.json          (상태 시계열)
#    → outputs/snapshots/frames/<store_id>/{i:04d}.jpg  (매장별 폴더, 매장별 순서의 분석 이미지)
#    → outputs/snapshots/raw-frames/<store_id>/{i:04d}.jpg (ROI 설정용 원본)

# 2) 재생: 상태 POST + 해당 이미지를 API로 업로드
python services/vision-worker/replay_states.py \
    --frames-dir services/vision-worker/outputs/snapshots/frames \
    --raw-frames-dir services/vision-worker/outputs/snapshots/raw-frames \
    --loop
```
- replay가 상태를 보낼 때마다 **그 인덱스의 이미지를 `POST .../vision-snapshot`로 업로드** → 이미지·숫자 동기.
- 원본 프레임이 준비된 경우 `--raw-frames-dir`로 `POST .../vision-raw`에도 전송한다.
- 대시보드: `<img src="{API}/api/stores/store-001/vision/latest">` (매장별 store_id).
- ROI 편집기: `{API}/api/stores/store-001/vision/raw/latest`를 사용한다.
- 이미지 옵션 없이 재생하면 **숫자만** 전송한다.

**실시간(`--live`)** — 모델·GPU·데이터 있는 머신에서 세그먼트마다 생성+상태 POST+이미지 업로드:
```bash
py services/vision-worker/cafe_stores.py --live --post http://localhost:8000 --interval 3
```

> **주의:** 분석 이미지는 CAFE 원본 프레임을 포함하므로 **GitHub에 올리지 않는다**(원본·가중치 미업로드).
> `frames/`는 데모 머신/드라이브로 옮기고, replay가 API로 업로드한다. (`--snapshot`은 로컬 1장 빠른 확인용.)

### 승인 ROI로 다시 분석하기

ROI 편집 화면에서 `저장 및 적용`한 설정은 Vision 분석을 새로 시작할 때 API에서
한 번 불러온다. 기존 JSON과 분석 이미지는 자동으로 다시 계산되지 않는다.

```bash
python3 -m venv .venv-vision
source .venv-vision/bin/activate
pip install -r services/vision-worker/requirements.txt

export AISEYE_CAFE_ROOT=/home/kokdo/datasets/ai-s-eye/cafe-selected/Cafe_Dataset/Dataset/cafe
export AISEYE_CAFE_MODEL=/path/to/best.pt
export AISEYE_API_BASE_URL=http://localhost:8000

# 기존 재생 결과가 테스트 값을 덮지 않게 중지
docker compose --profile demo stop vision-replay

# 매장별 한 구간으로 승인 ROI 연결 확인
python services/vision-worker/cafe_stores.py \
  --live --limit 1 --post http://localhost:8000 --interval 0

# 로그에서 아래처럼 API 버전을 확인한 뒤 전체 재분석
# ROI store-001/store-001-cam1: api v5
python services/vision-worker/cafe_stores.py

# 새 JSON과 frames/ 결과 재생
docker compose --profile demo up -d --force-recreate vision-replay
```

파인튜닝 가중치가 없으면 일반 `yolo11s.pt`로 대체되므로 연결 확인에는 사용할 수
있지만 기존 성능평가 결과와 같은 모델로 취급하면 안 된다. ROI를 다시 저장한 뒤에는
Vision 프로세스를 재시작해야 새 승인 버전을 읽는다.

## 팀원용: 영상 없이 매장 상태 재생하기

영상·YOLO·GPU 없이도 실제 분석 결과를 API에 흘려보낼 수 있다. 대시보드나 AICC를
개발할 때 매장 인원이 계속 변하는 상황을 만들 수 있다.

미리 분석해 둔 결과(`samples/cafe_stores_states.json`, CAFE 다매장 2개 매장)를
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
| `--preserve-timestamps` | JSON의 원본 측정 시각 유지 | 꺼짐 |

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
```

중단은 `Ctrl+C`.

재생할 때는 PostgreSQL에서 매번 최신 상태가 되도록 `captured_at`을 현재 UTC 시각으로
바꿔 전송한다. 과거 시각을 유지한 채 자료를 적재해야 할 때만
`--preserve-timestamps`를 사용한다. 이 옵션을 사용한 반복 재생은 첫 바퀴 이후
대시보드의 최신 상태를 바꾸지 못할 수 있다.

미니PC에서 시연하는 동안 계속 재생하려면 Docker의 `demo` 프로필을 사용한다.

```bash
# 백그라운드 반복 재생 시작
docker compose --profile demo up -d vision-replay

# 재생 상태와 로그 확인
docker compose --profile demo ps
docker compose --profile demo logs -f vision-replay

# 재생만 종료
docker compose --profile demo stop vision-replay
```

`outputs/snapshots/raw-frames`가 준비되어 있으면 Compose 재생기가 분석 이미지와
ROI 표시가 없는 원본 CCTV 이미지를 같은 순서로 함께 전송한다. 원본 폴더가 없으면
상태·사람 위치·분석 이미지만 계속 재생한다.

`vision-replay`는 상태를 보낼 때마다 PostgreSQL에 이력을 추가한다. 팀원 여러 명이
동시에 실행하지 않고 시연 담당자 한 명만 실행하며, 시연이 끝나면 중지한다.

전송한 값은 다음으로 확인한다.

```bash
curl http://localhost:8000/api/stores/store-001/state
curl http://localhost:8000/api/stores/store-001/eta
```

대시보드는 매장 화면에서 상태를 2초마다 다시 조회하므로 재생 중 값이 바뀐다.
현재 ETA와 본사 화면의 갱신 방식은 대시보드 이슈 #57에서 함께 정리한다.

## 분석 결과 데이터

`samples/cafe_stores_states.json`은 CAFE 데이터셋의 서로 다른 카페를 프랜차이즈
매장으로 보고 집계한 결과다. 현재는 `store-001`, `store-002` 2곳이다.

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
