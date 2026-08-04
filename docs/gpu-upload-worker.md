# 업로드형 온보딩 + GPU 워커

미니PC는 API·저장·대시보드를 맡고, **본인 GPU 서버**에서 업로드 미디어를 분석한다.

## 역할

| 구성 | 위치 |
|------|------|
| 미디어 업로드 / analysis job 큐 | 미니PC API |
| Scene/ROI 온보딩 UI | 대시보드 |
| 장면 초안 (`/internal/scene-suggestions`) | GPU `:8200` |
| job pull + state/snapshot POST | GPU `upload_job_worker.py` |

## 미니PC `.env`

GPU Tailscale IP를 `GPU_TAILSCALE_IP`라고 하면:

```bash
# AICC → GPU 장면 초안
AICC_VISION_SCENE_URL=http://GPU_TAILSCALE_IP:8200/internal/scene-suggestions

# 점주 업로드 용량(기본 200MB)
STORE_MEDIA_MAX_BYTES=209715200
```

적용 후:

```bash
docker compose up -d api aicc
docker compose exec api alembic upgrade head
```

## 비전 재생 역할 분리

| 매장 | 재생 방식 |
|------|-----------|
| store-001 / 002 | 미니PC `vision-replay` (compose DNS `http://api:8000`, 상시) |
| store-003+ 업로드 | GPU `upload_job_worker.py` (발표 시에만) |

`vision-replay`는 API 재시작 중 DNS flake에 대비해 전송 재시도를 한다. 외부에서 돌릴 때만 `.env`에 `VISION_REPLAY_API_URL=http://100.86.5.67:8000`처럼 오버라이드한다.

## GPU 서버

1. Tailscale으로 미니PC API(`http://MINIPC_TAILSCALE:8000`)에 접근 가능한지 확인
2. 동일 `INTERNAL_API_KEY` 공유
3. (선택) 장면 초안 서비스를 `:8200`에 listen
4. 워커 실행:

```bash
cd services/vision-worker
export AISEYE_API=http://MINIPC_TAILSCALE:8000
export INTERNAL_API_KEY=...   # 미니PC와 동일
export AISEYE_CAFE_MODEL=/path/to/best.pt   # 사람 추적(없으면 empty ingest)
export AISEYE_API_BASE_URL=$AISEYE_API      # ROI 조회
# 영상 추출 시
pip install opencv-python-headless ultralytics
python upload_job_worker.py --loop --interval 5 --model "$AISEYE_CAFE_MODEL"
```

워커는

1. `GET /internal/analysis-jobs/next` 로 job claim  
2. `GET /internal/analysis-jobs/{id}/media` 로 파일 다운로드  
3. ZIP/영상에서 프레임 추출  
4. `POST /internal/store-states` + vision snapshot  
5. `PATCH ... status=completed|failed`

모델 가중치는 GPU 로컬에만 두고 Git/미니PC에 올리지 않는다.

## 온보딩 UX

1. 점주: 영상 또는 프레임 ZIP 업로드  
2. 대표 프레임으로 Scene/ROI 설정  
3. 저장 시 analysis job 생성  
4. GPU 워커가 처리하면 대시보드 폴링에 반영  

## 브라우저 업로드 경로 (Cloudflare 우회)

Cloudflare Free/Pro는 요청 본문 약 100MB 제한이 있어, **대용량 미디어 업로드는 CF를 타지 않는다.**

| 트래픽 | 경로 |
|--------|------|
| UI + 작은 API 조회 | `https://aiseye.ldhcloud.com` → CF → 미니PC |
| 미디어 업로드 / analysis-jobs | 브라우저 → Tailscale HTTPS → 미니PC API |

### 미니PC: Tailscale Serve

1. [DNS 관리 콘솔](https://login.tailscale.com/admin/dns)에서 **HTTPS Certificates** 활성화  
2. 미니PC에서 (API가 `100.86.5.67:8000`에 bind된 경우):

```bash
sudo tailscale serve --bg --https=443 http://100.86.5.67:8000
sudo tailscale serve status
curl -fsS https://docker-test.tail0c814d.ts.net/health
```

결과 URL: `https://docker-test.tail0c814d.ts.net`

### 대시보드

- 클라우드 호스트(`aiseye.ldhcloud.com`)에서는 `UPLOAD_API_BASE_URL` 기본값이 위 Tailscale HTTPS
- Tailscale에 연결되지 않으면 업로드 입력을 비활성화하고 안내 문구 표시
- 오버라이드: `VITE_UPLOAD_API_BASE_URL`
- CORS에 `https://aiseye.ldhcloud.com` 포함 필요 (이미 `.env` 권장값)

데모 PC에서 Tailscale이 없으면 `http://100.86.5.67:5173` 온보딩으로 같은 HTTP API에 올리면 된다.

### store-003+ 데모 재생 (자동)

권장: job 폴링 + 온보딩 완료 후 자동 루프 + 기동 시 캐시 resume

```bash
python upload_job_worker.py --loop --auto-replay --play-interval 1.0 --model "$AISEYE_CAFE_MODEL"
```

- 온보딩 analysis job 완료 후 해당 매장 재생 스레드 시작
- 워커 재시작 시 `outputs/upload-replay/<store_id>/` 캐시로 재생 resume
- occupancy는 API `current_store_occupancy`에 영속화 (API recreate 후에도 agents 복구)

단일 매장만 수동 재생:

```bash
python upload_job_worker.py --replay-store store-003 --play-interval 1.0 --model "$AISEYE_CAFE_MODEL"
```
