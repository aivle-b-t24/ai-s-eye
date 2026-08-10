# GCP CPU VM 배포 절차

이 구성은 GPU 분석을 포함하지 않는다. Dashboard, API, AICC, PostgreSQL, cleanup과
저장된 Vision 결과 재생만 Compute Engine에서 실행한다. YOLO/YOLOE는 필요할 때 별도
GPU 환경에서 수행한다.

## 1. 준비

- Ubuntu Compute Engine `e2-medium` 이상
- Docker Engine과 Docker Compose plugin
- Vertex AI와 Firebase 접근 권한이 있는 VM 서비스 계정
- 저장소 clone과 `.env.gcp` 작성

```bash
cp .env.gcp.example .env.gcp
docker compose --env-file .env.gcp -f compose.gcp.yml config --quiet
```

`.env.gcp`에는 실제 비밀번호와 공개 URL을 넣고 Git에 올리지 않는다. GCE에서는
서비스 계정의 Application Default Credentials를 사용하므로 로컬 ADC JSON을 마운트하지
않는다.

## 2. 이미지 빌드와 마이그레이션

```bash
docker compose --env-file .env.gcp -f compose.gcp.yml build
docker compose --env-file .env.gcp -f compose.gcp.yml --profile tools run --rm migrate
```

기존 DB를 복원할 때는 먼저 `db`만 시작하고 dump를 복원한 다음 마이그레이션을 실행한다.

## 3. 시작과 확인

```bash
docker compose --env-file .env.gcp -f compose.gcp.yml up -d
docker compose --env-file .env.gcp -f compose.gcp.yml ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8100/healthz
curl -fsS http://127.0.0.1/
```

외부에는 Cloudflare Tunnel의 HTTPS 주소만 노출한다. 현재 운영 호스트 매핑은 다음과
같고, GCP 방화벽에서 80/8000/8100 인바운드는 열지 않는다.

- `aiseye.ldhcloud.com` → `http://127.0.0.1:80`
- `aiseye-api.ldhcloud.com` → `http://127.0.0.1:8000`
- `aiseye-ai.ldhcloud.com` → `http://127.0.0.1:8100`

Tunnel credential JSON은 저장소에 넣지 않고 `/etc/cloudflared`에 권한 `0600`으로 둔다.
GCP 커넥터의 HTTPS 검증이 끝난 뒤 이전 서버의 커넥터를 중지한다. 이전 커넥터를 다시
시작하면 즉시 롤백할 수 있으므로, GCP 검증 전에는 기존 애플리케이션과 DB를 삭제하지
않는다.

## 4. 데이터와 종료

Compose volume 이름은 프로젝트 디렉터리가 바뀌어도 동일하게 유지된다.

- `ai-s-eye-gcp-postgres`
- `ai-s-eye-gcp-vision-snapshots`
- `ai-s-eye-gcp-store-media`

일반 배포에서는 `docker compose down`까지만 사용한다. `down -v`는 PostgreSQL과 업로드
파일을 삭제하므로 DB를 완전히 폐기할 때만 사용한다.

발표가 끝나 장시간 사용하지 않을 때는 Compute Engine VM을 중지한다. VM을 다시 시작한
뒤에는 Docker와 `cloudflared`가 자동 시작되며, 아래 명령으로 상태를 확인한다.

```bash
docker compose --env-file .env.gcp -f compose.gcp.yml ps
systemctl status cloudflared --no-pager
```

## 5. main 자동 배포

GCP 운영 서버는 `main` 브랜치만 배포한다. `main` 병합 시
`.github/workflows/deploy-gcp.yml`이 GitHub OIDC와 GCP Workload Identity Federation으로
단기 인증하고, IAP와 OS Login을 통해 `ai-s-eye-prod`에 접속한다. 서비스 계정 JSON 키와
장기 SSH 개인키는 사용하지 않는다.

배포 서버에서는 `scripts/deploy-gcp.sh`가 다음 순서로 실행된다.

1. 운영 저장소의 추적 파일 변경 여부 확인
2. PostgreSQL custom-format 백업 생성
3. API·AICC·Dashboard 이미지 빌드
4. Alembic 마이그레이션
5. 컨테이너 갱신
6. 로컬 및 Cloudflare 공개 주소 헬스체크

GitHub 저장소 Variable에는 프로젝트, Workload Identity Provider, 배포 서비스 계정,
인스턴스·Zone과 서버 경로만 둔다. 실제 운영 비밀값은 계속 GCP VM의 `.env.gcp`와
`/etc/cloudflared`에만 보관한다.

SSH는 `35.235.240.0/20`의 IAP 주소에서만 허용한다. 기본 `0.0.0.0/0` SSH·RDP 규칙은
비활성화하고, 애플리케이션 80·8000·8100 포트도 인터넷에 직접 공개하지 않는다.
