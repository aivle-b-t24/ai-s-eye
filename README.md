# AI's Eye

매장 CCTV 영상과 주문 정보를 이용해 매장 상황을 알려주는 프로젝트입니다.

영상 분석 결과로 매장 인원과 대기 인원을 파악하고, 이 정보를 대시보드와 AICC에서 같이 사용하는 것을 목표로 하고 있습니다.

React, FastAPI, PostgreSQL, AICC와 샘플 데이터를 Docker Compose로 함께 실행할 수 있습니다. 실제 YOLO 모델은 Vision 담당 영역에서 연결합니다.

## 폴더 구성

```text
ai-s-eye/
├── apps/
│   └── dashboard/                 # React 대시보드
│       ├── src/
│       │   ├── App.jsx            # 화면과 API 호출
│       │   ├── App.css            # 화면 스타일
│       │   ├── index.css          # 공통 스타일
│       │   └── main.jsx           # React 시작 파일
│       ├── Dockerfile
│       ├── package.json
│       └── vite.config.js
├── services/
│   ├── api/                       # FastAPI 공통 서버
│   │   ├── app/
│   │   │   ├── main.py            # API 경로
│   │   │   ├── models.py          # 요청·응답 데이터 형식
│   │   │   ├── repository.py      # 임시 메모리 저장소
│   │   │   └── config.py          # 환경변수 설정
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── vision-worker/             # YOLO 담당 작업 영역
│   └── aicc/                      # 슈퍼바이저 AI 인사이트 API
├── packages/
│   └── contracts/                 # 공통 JSON Schema
├── samples/                       # 메뉴·정책·상태·주문 샘플
├── docs/                          # API 규격과 인수인계 문서
├── tests/                         # FastAPI 테스트
├── .gitattributes                 # 팀 공통 줄바꿈 설정
├── .env.example                   # 환경변수 예시
├── docker-compose.yml             # 전체 서비스 실행 설정
└── README.md
```

`vision-worker`는 담당자가 작업을 시작할 위치만 준비되어 있습니다. 실제 YOLO 모델은 아직 들어 있지 않습니다.

`aicc`에는 공통 API를 호출하는 Tool과 Vertex AI 기반 슈퍼바이저 인사이트 API가 들어 있습니다. 자세한 내용은 `services/aicc/README.md`를 참고하세요.

## 실행 방법

저장소를 받은 뒤 프로젝트 폴더로 이동합니다.

```bash
git clone https://github.com/aivle-b-t24/ai-s-eye.git
cd ai-s-eye
```

Docker가 설치되어 있으면 아래 명령어로 전체 서비스를 실행합니다. React나 Python, PostgreSQL은 따로 설치하지 않아도 됩니다.

```bash
cp .env.example .env
docker compose up --build -d
```

컨테이너가 잘 실행됐는지는 다음 명령어로 확인할 수 있습니다.

```bash
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8100/healthz
```

브라우저에서 대시보드와 API 문서를 확인할 수 있습니다.

- 대시보드: [http://localhost:5173](http://localhost:5173)
- API 문서: [http://localhost:8000/docs](http://localhost:8000/docs)
- AICC 문서: [http://localhost:8100/docs](http://localhost:8100/docs)

작업 중 API 로그를 보고 싶을 때는 아래 명령어를 사용합니다.

```bash
docker compose logs -f api aicc
```

실행을 끝낼 때는 다음과 같이 종료합니다.

```bash
docker compose down
```

`docker compose down -v`를 사용하면 PostgreSQL 데이터도 같이 지워지므로 DB를 처음부터 다시 만들 때만 사용합니다.

## 지금 만들어진 범위

아직 실제 CCTV 영상이나 주문 시스템이 연결된 상태는 아닙니다. 각 담당자가 개발을 시작할 수 있도록 가상의 매장 `store-001`과 샘플 데이터를 넣어두었습니다.

현재 서버에서 확인할 수 있는 내용은 다음과 같습니다.

| 내용 | 현재 상태 |
|---|---|
| 매장 인원과 대기 인원 | React 화면에서 샘플 값 조회 가능 |
| 예상 대기시간 | 대기 인원 1명당 3분으로 임시 계산 |
| 메뉴와 품절 여부 | 샘플 메뉴 10개 중 2개 품절 처리 |
| 매장 정책 | 샘플 정책 5개 조회 가능 |
| 영상 분석 결과 받기 | StoreState JSON과 매장별 최신 분석 이미지 업로드·조회 API 준비 |
| 카메라 ROI 설정 | 점주가 CCTV 화면에서 구역을 직접 설정하고 PostgreSQL에 버전별 저장 |
| CCTV 디지털 트윈 | 구역 현황에서 CCTV 시점 가상 매장에 ROI·사람 위치·이동 궤적 표시(V2 기능 플래그) |
| 주문 이벤트 받기 | 주문 시스템이 나중에 보낼 JSON 형식만 준비 |
| 슈퍼바이저 AI 인사이트 | 두 매장 집계 결과를 Vertex AI로 분석하는 API 준비 |

서버를 실행한 뒤 [http://localhost:8000/docs](http://localhost:8000/docs)에 들어가면 위 기능을 직접 눌러서 확인할 수 있습니다.

`docs/api-contract.md`에는 담당자들이 서로 다른 이름이나 형식으로 데이터를 보내지 않도록, API에서 주고받을 값의 이름을 정리해 두었습니다.

## PostgreSQL 사용 방식

개발할 때는 한 곳의 DB를 여러 명이 같이 쓰지 않고, 각자 PC에서 Docker로 PostgreSQL을 실행합니다. 같은 설정으로 실행되기 때문에 따로 설치하거나 테이블을 직접 만들 필요는 없습니다.

팀 기능을 합칠 때는 미니PC에 같은 Docker 구성을 올려 공용 테스트 서버로 사용하고, 최종 배포 단계에서 클라우드 환경으로 옮길 예정입니다.

현재 PostgreSQL은 API 연결 상태만 확인하고 있습니다. 메뉴와 주문 같은 실제 테이블은 기능을 합치는 과정에서 추가합니다. 그전까지는 `samples` 폴더의 JSON을 기준으로 개발하면 됩니다.

미니PC에서 공용 API와 PostgreSQL을 운영하는 절차는
[`docs/minipc-runbook.md`](docs/minipc-runbook.md)에 정리되어 있습니다.

## AICC에서 Vertex AI 사용

AICC 컨테이너는 공통 API를 Docker 내부 주소 `http://api:8000`으로 호출합니다.
Vertex AI를 사용하려면 먼저 호스트에서 ADC 로그인을 하고 `.env`에 인증 파일의
절대 경로를 지정합니다.

```bash
gcloud auth application-default login
```

```env
GOOGLE_APPLICATION_CREDENTIALS_HOST_PATH=/home/user/.config/gcloud/application_default_credentials.json
```

인증 파일은 컨테이너에 읽기 전용으로 연결되며 이미지나 GitHub에는 들어가지 않습니다.
설정 후 `docker compose up -d --build aicc`로 실행하고
`http://localhost:8100/healthz`에서 상태를 확인합니다. 인증 설정이 없더라도
컨테이너와 상태 확인 API는 실행되지만 실제 `/insights` 호출은 실패합니다.

## 카메라 ROI 설정

점주 계정으로 로그인한 뒤 `설정`의 `카메라 구역 설정`에서 사용할 수 있습니다.

1. 최신 CCTV 이미지 또는 별도 JPEG·PNG 이미지를 선택합니다.
2. 직원·대기·출입구·좌석 구역을 직접 그립니다.
3. 꼭짓점을 이동하거나 추가·삭제해 경계를 맞춥니다.
4. `저장 및 적용`을 누르면 새 버전이 PostgreSQL에 저장됩니다.

Vision은 다음 분석 실행 시 API의 승인본을 먼저 사용하고, API 장애 시 마지막 캐시,
그마저 없으면 기존 `zones/*.json`을 사용합니다. 기존에 만들어 둔 재생 JSON은
ROI만 저장한다고 다시 계산되지 않으므로 Vision 분석을 재실행해야 수치가 바뀝니다.

개발 중에는 다음 명령으로 Vision LIVE 분석을 계속 실행할 수 있습니다.

```bash
services/vision-worker/live_control.sh start
services/vision-worker/live_control.sh status
services/vision-worker/live_control.sh logs
services/vision-worker/live_control.sh stop
```

LIVE 실행 중에는 승인된 ROI 버전을 2초마다 확인합니다. `저장 및 적용`을 누르면
별도 재시작 없이 다음 분석 구간부터 새 ROI가 사용됩니다. 마지막 구간까지 끝나면
처음부터 반복하므로 대시보드의 인원, 위치, 분석 이미지도 계속 갱신됩니다. 기존
JSON 기반 `vision-replay`는 같은 데이터를 덮어쓰지 않도록 LIVE 시작 시 중지합니다.

## 테스트

API 코드만 따로 테스트하려면 Python 가상환경을 만든 뒤 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r services/api/requirements.txt
pytest
```

React 코드는 실행 중인 컨테이너에서 확인할 수 있습니다.

```bash
docker compose exec dashboard npm run lint
docker compose exec dashboard npm run build
```

## Git 작업 방법

브랜치는 다음 용도로 나눕니다.

- `main`: 발표하거나 배포해도 되는 확인된 상태
- `develop`: 팀원 작업을 매일 합치고 통합하는 상태
- `feature/작업이름`: 각자 기능을 개발하는 상태

평소에는 `develop`에서 개인 브랜치를 만든 뒤, 작업이 끝나면 `develop`을 대상으로 PR을 만듭니다. 담당 폴더만 수정했다면 직접 실행해 본 뒤 본인이 병합할 수 있습니다. 별도의 승인 인원은 강제하지 않습니다.

공통 API, Docker, `packages/contracts`를 바꿨다면 바로 병합하지 않고 팀원에게 먼저 알립니다. `main`에는 개인 작업을 바로 합치지 않고, 통합 확인이 끝난 `develop`만 기능 단위나 발표 전 시점에 반영합니다.

PR을 만들면 `.github/pull_request_template.md`의 작업 내용과 확인 항목이 본문에 자동으로 나타납니다. 템플릿은 작성 기준을 알려주는 용도이며 체크 여부를 강제하지 않습니다.

```bash
git switch develop
git pull
git switch -c feature/작업이름
```

## 작업할 때 주의할 점

- `.env`와 API 키, 비밀번호는 GitHub에 올리지 않습니다.
- 영상, 데이터셋, 모델 가중치와 학습 결과는 이 저장소에 올리지 않습니다.
- 공통 JSON 형식을 바꿔야 한다면 `packages/contracts`와 `samples`를 같이 수정합니다.
- 아직 매장 상태와 주문 이벤트는 메모리에 저장되기 때문에 API를 다시 실행하면 추가한 값이 사라집니다.

## 현재 개발 단계의 공통 규칙

- 수·목에는 DB 테이블이나 마이그레이션을 새로 만들지 않습니다. 필요한 항목이 생기면 내용을 기록해 두고 통합할 때 함께 결정합니다.
- 담당 기능은 현재 API와 `samples` 폴더의 JSON을 기준으로 개발합니다.
- Docker 실행에 문제가 생기면 로그와 오류를 기록하고, 임시로 샘플 JSON을 사용해 화면·RAG·데이터 변환 작업을 계속합니다.
- 샘플 JSON으로 동작한 것은 임시 확인이며, Docker가 정상화된 뒤 API 연결을 다시 확인해야 완료로 봅니다.
- `docker-compose.yml`, `services/api`, `packages/contracts` 변경이 필요하면 바로 수정하지 않고 팀에 먼저 공유합니다.
