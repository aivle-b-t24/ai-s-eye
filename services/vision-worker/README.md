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

- 모델: CAFE로 파인튜닝한 `yolo11s`(전신 라벨 → 발 위치·bbox 산출). 가중치 경로는
  `AISEYE_CAFE_MODEL`, 데이터 경로는 `AISEYE_CAFE_ROOT` 환경변수로 지정한다.
  기준 `best.pt`가 없거나 SHA-256이 다르면 실행을 중단하며 일반 모델로 대체하지 않는다.
- 집계: **인원수 = 파인튜닝 탐지 − 직원(손님)**, **대기 = 대기 구역 + 서있음(pose) +
  체류(ByteTrack)**, **직원 = 발 또는 bbox 하단이 직원 ROI에 들어오고 track 다수결을 통과한 사람**. 구역은
  승인 ROI(API)→`zones/<store_id>_zones.json` 순으로 불러온다.
- **매장을 늘리려면** `cafe_stores.py`의 `STORES`에 항목을 추가하고 해당 매장 zones를
  그린 뒤 다시 실행한다.

```bash
py services/vision-worker/cafe_stores.py             # 전체 클립 → samples/ 저장(재생용)
py services/vision-worker/cafe_stores.py --limit 60  # 앞 60세그만(빠른 확인)
```

약 5fps로 저장된 모든 프레임을 ByteTrack에 입력하고 영상 시간 기준 기본 1초마다 결과를
내보낸다. 번호가 연속인 원본 세그먼트는 같은 트래커와 epoch를 유지하고, 검수된 큰 장면
전환·누락 세그먼트·스트림 재연결에서만 이전 ID를 폐기한다. 결과는
매장별 영상 시간을 교차 배치해
`samples/cafe_stores_states.json`에 저장한다. 각 결과에는 `frame_id`,
`processed_at`, 승인 `roi_version`, 세그먼트 epoch가 포함된 ByteTrack `track_id`, 탐지
`bbox`·`confidence`와 자세 `state`가 들어간다.

> 참고: CAFE엔 촬영 시각이 없어 `captured_at`은 `ann.json`의 fps와 프레임 번호로 만든
> 합성 영상 시각이다. 실제 촬영 시각이 아니다.

## MVP 제공 값 / 미지원 값

대시보드가 참고하도록, 현재 Vision 모델이 **실제로 제공하는 값**과 **아직 제공하지
못하는 값**을 구분한다. StoreState에는 아래 "제공 값"만 채우고, 미지원 값은 넣지 않는다.

**제공 값 (안정적)**

| 값 | StoreState 필드 | 산출 |
|---|---|---|
| 전체(손님) 인원 | `visible_person_count` | 파인튜닝 탐지 − 직원 |
| 직원 인원 | `zone_counts.staff` | 카메라 5: 발 또는 bbox 80% 중첩, 카메라 21: 발 위치 + 최근 5회 중 3회 판정 + 같은 장면 가림 시 최대 10초 유지 |
| 대기 인원 | `queue_count_estimate` = `zone_counts.waiting` | 대기 구역 + 서있음 + 체류 |

**미지원 값 (현재 제공 못 함 — StoreState에 넣지 않음)**

- 좌석 점유(테이블별), 통로 인원, 카운터 주문 세부, **입·퇴장 이벤트**
- 대시보드에 이런 항목이 보이면 Vision 산출값이 아니라 UI 표현/목업이다.

**quality_status 기준** — "사람 0명"과 "영상 이상"을 구분한다.

- `normal`: 정상 프레임. **사람이 0명이어도 정상**(빈 매장).
- `low`: 프레임 디코드 실패 또는 거의 검은 화면(카메라 꺼짐·가림) = 영상 이상.

**ROI 기준** — 매장별 `zones/<store_id>_zones.json`에 지정.

- **대기** = 대기 구역(카운터 앞) 안에서 서있고 N프레임 이상 체류한 사람.
- **직원** = 현재 승인된 직원 구역(카운터 뒤) 안에서 탐지된 사람. 직원 수를
  미리 고정하지 않으며 해당 구역 안의 탐지를 손님 수에서 제외한다. 직원 구역은
  좌석과 겹치지 않게 설정해야 한다.

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
python services/vision-worker/cafe_stores.py --roi-api http://localhost:8000
#    → samples/cafe_stores_states.json          (상태 시계열)
#    → outputs/snapshots/frames/<store_id>/{i:04d}.jpg  (매장별 폴더, 매장별 순서의 분석 이미지)
#    → outputs/snapshots/raw-frames/<store_id>/{i:04d}.jpg (ROI 설정용 원본)

# 2) 재생: 상태 POST + 해당 이미지를 API로 업로드
python services/vision-worker/replay_states.py \
    --frames-dir services/vision-worker/outputs/snapshots/frames \
    --raw-frames-dir services/vision-worker/outputs/snapshots/raw-frames \
    --loop
```
- replay가 상태를 보낼 때마다 **그 인덱스의 이미지와 동일한 메타데이터를
  `POST .../vision-snapshot`로 업로드** → 이미지·숫자·프레임 신원 동기.
- 원본 프레임이 준비된 경우 `--raw-frames-dir`로 `POST .../vision-raw`에도 전송한다.
- 대시보드: `<img src="{API}/api/stores/store-001/vision/latest">` (매장별 store_id).
- ROI 편집기: `{API}/api/stores/store-001/vision/raw/latest`를 사용한다.
- 이미지 옵션 없이 재생하면 **숫자만** 전송한다.

**실시간(`--live`)** — 모델·GPU·데이터 있는 머신에서 5fps 분석+1초 상태 POST+이미지 업로드:
```bash
python services/vision-worker/cafe_stores.py \
  --live --post http://localhost:8000 --output-interval 1 --speed 2
```

`--output-interval`은 영상 분석 시간축, `--speed`는 실제 재생 배속이다. 배속을 바꿔도
ByteTrack 입력 프레임과 결과의 영상 시간 간격은 바뀌지 않는다.

정식 IDF1 검증에서 저신뢰 후보가 합격 기준을 통과하지 못했으므로 운영은 `baseline`을
사용한다. 로컬 A/B 확인용으로만 `AISEYE_TRACKING_PROFILE=candidate`를 지정할 수 있다.
두 프로필 모두 연속 세그먼트 5fps 입력·1초 출력·실제 장면 전환 epoch 리셋을 동일하게 적용한다.

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
  --live --limit 1 --post http://localhost:8000 --output-interval 1 --speed 2

# 로그에서 아래처럼 API 버전을 확인한 뒤 전체 재분석
# ROI store-001/store-001-cam1: api v5
python services/vision-worker/cafe_stores.py --roi-api http://localhost:8000

# 새 JSON과 frames/ 결과 재생
docker compose --profile demo up -d --force-recreate vision-replay
```

파인튜닝 가중치가 없거나 기준 해시와 다르면 분석은 즉시 실패한다. `--live` Vision과
`vision-replay`는 승인 ROI를 2초마다 다시 확인하므로 프로세스를 재시작하지 않아도
새 승인 버전을 적용한다.

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
| `--preserve-timestamps` | `frame_id`가 없는 레거시 JSON도 원본 시각 유지 | 꺼짐 |
| `--roi-refresh-seconds` | 승인 ROI를 다시 확인하는 간격 | `2` |
| `--no-roi-reclassify` | 저장 당시 판정을 그대로 재생 | 꺼짐 |

신규 결과는 `frame_id`가 있으므로 옵션과 관계없이 원래 `captured_at`을 보존한다.
반복 재생은 `source=demo-replay`로 표시되고 동일 프레임은 원본 DB 이력에 중복
저장하지 않는다.

기본 재생 모드는 API에서 승인 ROI를 2초마다 확인한다. ROI 버전이 바뀌면 저장된
YOLO·ByteTrack 좌표를 새 ROI에 다시 넣어 `zone`, `role`, `state`, StoreState
집계를 즉시 갱신한다. 이 과정은 사람을 다시 탐지하는 것이 아니라 이미 생성된
좌표의 공간 판정만 다시 수행한다. 대시보드의 분석 화면도 원본 CCTV 위에 현재 ROI와
재판정 위치를 겹쳐 표시하므로 과거 ROI가 그려진 이미지를 새 결과처럼 사용하지 않는다.

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

주의: 원본 데이터셋에 촬영 시각이 없어 `captured_at`은 메타데이터 기반 영상 시간만큼
증가하도록 만든 합성값이다. 실제 촬영 시각이 아니므로 시간대별 분석에 그대로
쓰지 않는다.

## 성능 평가

동일 모델로 기존 `conf=0.30 + 기본 ByteTrack + 세그먼트 리셋 없음`과 개선 파이프라인을
비교한다. CAFE GT가 있으면 IoU 0.5 탐지 지표도 함께 계산한다.

```bash
python services/vision-worker/benchmark_tracking.py \
  --cafe-root "$AISEYE_CAFE_ROOT" \
  --model "$AISEYE_CAFE_MODEL" \
  --gt-zip /mnt/d/AI-S-Eye/Cafe_Dataset.zip
```

결과는 `outputs/benchmarks/tracking_ab.json`에 저장된다. CAFE 공개 GT에는 사람별 전역
ID가 없는 텍스트 파일과, 각 원본 세그먼트 안에서만 사람 ID를 유지하는 `gt_tracks.pkl`이
함께 있다. 픽셀 경계 검사 결과 번호가 연속인 세그먼트는 실제로 이어지므로 트래커를
유지해야 하지만, GT ID는 세그먼트마다 다시 시작한다. 따라서 세그먼트 사이 사람 ID를
연결한 별도 정답표가 없으면 이 결과를 IDF1/HOTA로 표현할 수 없다. 아래 정식 평가는
고정 구간의 일반 경계 ID를 위치 기반으로 연결하고 contact sheet로 검수한 정답을 사용한다.

정식 MOT 평가는 고정된 15초 구간 16개(총 1,200프레임)를 사용한다. 카메라별로 일반 3개,
혼잡·가림 3개, 장면 전환 2개이며, 절반은 8개 설정 선택용, 절반은 최종 테스트용이다.
기존에 원본 ID에 세그먼트 epoch를 결합한 MOT 결과는 연속 클립의 실제 사람까지 분리해
점수를 부풀렸으므로 폐기했다. 현재 평가는 32개 일반 경계의 344명을 전역 ID로 연결하고
1명을 새 등장으로 분리한 수정 정답을 사용한다.

```bash
python services/vision-worker/evaluate_mot_tracking.py \
  --cafe-root "$AISEYE_CAFE_ROOT" \
  --model "$AISEYE_CAFE_MODEL" \
  --gt-zip /mnt/d/AI-S-Eye/Cafe_Dataset.zip
```

결과는 `outputs/mot_validation/`에 생성된다.

- `dataset/`: MOT 형식 GT, 원본 이미지 symlink, 원본 프레임 매핑
- `predictions/`: 설정별 추적 결과
- `videos/`: 테스트 구간의 기존/후보 비교 영상
- `audit/`: 연속 경계 ID 연결 JSON과 사람이 대조하는 contact sheet
- `miss_analysis/`: 활동·가림·카메라별 미탐지 분석과 contact sheet
- `mot_tracking_report.json`: IDF1, HOTA, ID Switch, Fragmentation과 판정

현재 운영 기본은 `baseline`이다. 연속 세그먼트에서는 ID를 유지하고 검수된 장면 전환과
세그먼트 누락에서만 epoch를 바꾼다. 저신뢰 후보는 IDF1 `+3%p`와 ID Switch `30% 감소`
기준을 통과하지 못해 채택하지 않았다. 상세 수치는 아래 성능평가 문서를 본다.

탐지 미스 원인은 다음 명령으로 별도 분석할 수 있다.

```bash
python services/vision-worker/analyze_missed_detections.py \
  --cafe-root "$AISEYE_CAFE_ROOT" \
  --gt-zip /mnt/d/AI-S-Eye/Cafe_Dataset.zip
```

- [추적 파이프라인 A/B 성능평가](성능평가/추적_파이프라인_성능평가.md)
- [4주차 YOLO 성능평가](성능평가/4주차_YOLO_성능평가.md)
