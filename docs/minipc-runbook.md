# 미니PC 공용 테스트 서버 운영

미니PC에서 PostgreSQL, 공통 API와 AICC를 함께 실행하고, 팀원은 Tailscale을 통해
API와 AICC에 접속한다. PostgreSQL 포트는 팀원 PC나 외부 인터넷에 직접 공개하지 않는다.

```text
팀원 PC
  └─ Tailscale
       ├─ 미니PC API:8000 → PostgreSQL:5432
       └─ 미니PC AICC:8100
            ├─ Docker 내부망 → API:8000
            └─ 읽기 전용 ADC → Vertex AI
```

## 적용 시점

노경민의 슈퍼바이저 분석 작업을 포함한 최신 `develop`이 준비된 뒤 적용한다.
미니PC에서는 기능을 직접 개발하지 않고, 팀이 합친 코드를 실행하고 검증한다.

## 1. 준비

미니PC와 접속할 팀원 PC를 같은 Tailscale 네트워크에 연결한다.

Ubuntu에서 Tailscale을 설치하고 로그인한다.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale status
tailscale ip
```

서버 용도로 계속 켜둘 경우 Tailscale 관리 화면의 해당 장비 설정에서
키 만료를 해제할 수 있다. 팀 프로젝트가 끝나면 다시 활성화하거나 장비를 제거한다.

Docker Engine과 Compose 플러그인이 설치돼 있는지 확인한다.

```bash
docker --version
docker compose version
sudo systemctl enable --now docker
```

설치가 필요하면 Docker와 Tailscale의 공식 Ubuntu 설치 문서를 따른다.

- Docker: https://docs.docker.com/engine/install/ubuntu/
- Tailscale: https://tailscale.com/docs/install/linux

## 2. 저장소와 환경변수 준비

```bash
git clone https://github.com/aivle-b-t24/ai-s-eye.git
cd ai-s-eye
git switch develop
git pull --ff-only origin develop
cp .env.example .env
```

다음 명령으로 미니PC의 Tailscale IPv4 주소를 확인한다.

```bash
tailscale ip -4
```

`.env`에서 다음 값을 미니PC 환경에 맞게 변경한다.

```env
APP_ENV=integration

API_BIND_HOST=100.x.x.x
API_PORT=8000

DASHBOARD_BIND_HOST=100.x.x.x
DASHBOARD_PORT=5173
VITE_API_BASE_URL=http://100.x.x.x:8000

POSTGRES_USER=store
POSTGRES_PASSWORD=충분히_긴_개발용_비밀번호
POSTGRES_DB=store

CORS_ORIGINS=http://localhost:5173,http://100.x.x.x:5173

AICC_BIND_HOST=100.x.x.x
AICC_PORT=8100
AICC_CORS_ORIGINS=http://localhost:5173,http://100.x.x.x:5173
AICC_VERTEX_PROJECT=project-511b6816-d61a-47ab-b67
AICC_VERTEX_LOCATION=us-central1
AICC_GEMINI_MODEL=gemini-2.5-flash
GOOGLE_APPLICATION_CREDENTIALS_HOST_PATH=/home/ubuntu/.config/gcloud/application_default_credentials.json
```

`100.x.x.x`는 실제 Tailscale IPv4 주소로 바꾼다. `.env`는 GitHub에 올리지 않는다.

`docker-compose.yml`에서 PostgreSQL은 항상 `127.0.0.1`에만 연결된다.
팀원에게 DB 주소나 5432 포트를 공유하지 않는다.

`GOOGLE_APPLICATION_CREDENTIALS_HOST_PATH`에는 미니PC에서
`gcloud auth application-default login`으로 만든 ADC 파일의 절대 경로를 넣는다.
파일은 AICC 컨테이너에 읽기 전용으로 연결되며 GitHub에 올리지 않는다.

## 3. 최초 실행

먼저 DB와 API만 실행한다.

```bash
docker compose up -d --build db api
docker compose exec api alembic upgrade head
docker compose exec api python -m app.scenario_loader
```

상태를 확인한다.

```bash
docker compose ps
curl http://100.x.x.x:8000/health
curl http://100.x.x.x:8000/api/stores/summary
```

정상 기준은 다음과 같다.

- `/health`의 `database`가 `ok`
- 시나리오 상태 8건과 주문 6건 적재 성공
- 집계 결과에 `store-001`, `store-002`가 모두 표시

대시보드도 미니PC에서 운영할 때만 추가로 실행한다.

```bash
docker compose up -d --build dashboard
```

팀원이 각자 로컬 대시보드를 실행하는 동안에는 미니PC의 대시보드 컨테이너가
필수는 아니다.

## 4. 팀원 연결

팀원 PC도 같은 Tailscale 네트워크에 로그인한 뒤 다음 주소를 확인한다.

```text
http://100.x.x.x:8000/health
http://100.x.x.x:8000/docs
http://100.x.x.x:8100/docs
```

AICC도 미니PC에서 운영할 때 실행한다. Compose가 내부 API 주소
`http://api:8000`을 자동으로 지정하므로 외부 API 주소를 따로 넣지 않는다.

```bash
docker compose up -d --build aicc
curl http://100.x.x.x:8100/healthz
```

브라우저 대시보드는 `VITE_API_BASE_URL`을 같은 API 주소로 지정해 실행한다.

Tailscale에 연결하지 않은 PC, 일반 LAN 주소, 외부 인터넷에서는 접근되지 않는지
함께 확인한다.

## 5. 코드 업데이트

팀 작업이 `develop`에 병합되면 미니PC에서 다음 순서로 갱신한다.

```bash
git switch develop
git pull --ff-only origin develop
docker compose up -d --build db api aicc
docker compose exec api alembic upgrade head
docker compose ps
```

DB 볼륨은 유지되므로 일반적인 이미지 재빌드로 데이터가 삭제되지 않는다.
`docker compose down -v`는 PostgreSQL 데이터를 전부 지우므로 사용하지 않는다.

### 5.1 develop 자동 배포

`develop`에 병합되면 `.github/workflows/deploy-develop.yml`이 GitHub-hosted Runner를
Tailscale의 임시 `tag:ci` 장비로 연결하고 미니PC에 SSH 접속한다. 미니PC는 외부 SSH나
Cloudflare에 노출하지 않는다.

필요한 GitHub Actions Secret은 다음과 같다.

- `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`: `Auth Keys: Write`, `tag:ci`로 제한한
  Tailscale OAuth Credential
- `MINIPC_DEPLOY_SSH_KEY`: 미니PC 배포 전용 Ed25519 개인키
- `MINIPC_KNOWN_HOSTS`: 미니PC SSH 호스트 공개키

저장소 Variable은 다음과 같다.

- `MINIPC_HOST=100.86.5.67`
- `MINIPC_USER=ubuntu`
- `MINIPC_APP_PATH=/home/ubuntu/ai-s-eye`

서버에서는 `scripts/deploy-minipc.sh`가 동시 배포 잠금, 배포 전 DB 백업, 이미지 빌드,
마이그레이션, API·AICC·Dashboard 상태 검사를 수행한다. 서버의 추적 파일이 수정돼 있으면
덮어쓰지 않고 배포를 중단한다.

## 6. 백업과 복구

백업 폴더를 만들고 PostgreSQL 덤프를 저장한다.

```bash
mkdir -p backups
docker compose exec -T db pg_dump -U store -d store --format=custom \
  > "backups/store_$(date +%Y%m%d_%H%M%S).dump"
```

백업 파일은 `.gitignore` 대상이며 GitHub에 올리지 않는다.

복구가 필요하면 먼저 현재 DB를 별도로 백업하고 API 쓰기를 멈춘 뒤 진행한다.

```bash
docker compose stop api
docker compose exec -T db pg_restore -U store -d store --clean --if-exists \
  < backups/백업파일.dump
docker compose start api
docker compose exec api alembic upgrade head
```

복구 후 `/health`와 `/api/stores/summary`를 다시 확인한다.

## 7. 재부팅과 장애 확인

Docker 서비스와 컨테이너에는 자동 재시작 설정이 적용돼 있다. 미니PC를 재부팅한
뒤 다음 항목을 확인한다.

```bash
docker compose ps
docker compose logs --tail=100 api aicc
curl http://100.x.x.x:8000/health
curl http://100.x.x.x:8100/healthz
```

API가 열리지 않으면 다음 순서로 확인한다.

1. `tailscale status`에서 미니PC가 연결돼 있는지 확인
2. `.env`의 `API_BIND_HOST`가 현재 Tailscale IPv4와 같은지 확인
3. `docker compose ps`에서 DB, API와 AICC 상태 확인
4. `docker compose logs --tail=100 db api aicc`로 오류 확인
5. 마이그레이션이 필요한지 확인

## 운영 원칙

- 팀원은 PostgreSQL에 직접 접속하지 않고 API만 사용한다.
- `.env`, 비밀번호, Google 인증 파일은 저장소에 올리지 않는다.
- 미니PC에 기능 브랜치를 바로 배포하지 않고 `develop` 병합 후 갱신한다.
- 대용량 영상·모델 가중치는 미니PC DB나 GitHub에 넣지 않는다.
- 업로드형 온보딩 분석·장면 초안은 본인 GPU 서버에서 돌린다. 절차는 [gpu-upload-worker.md](./gpu-upload-worker.md) 참고.
- 외부 공개, HTTPS, 도메인, 최종 클라우드 배포는 별도 단계에서 진행한다.
