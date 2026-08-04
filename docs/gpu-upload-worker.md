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

## GPU 서버

1. Tailscale으로 미니PC API(`http://MINIPC_TAILSCALE:8000`)에 접근 가능한지 확인
2. 동일 `INTERNAL_API_KEY` 공유
3. (선택) 장면 초안 서비스를 `:8200`에 listen
4. 워커 실행:

```bash
cd services/vision-worker
export AISEYE_API=http://MINIPC_TAILSCALE:8000
export INTERNAL_API_KEY=...   # 미니PC와 동일
# 영상 추출 시
pip install opencv-python-headless
python upload_job_worker.py --loop --interval 5
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
