#!/usr/bin/env bash
# 미니PC에서 develop을 받아 dashboard / api / aicc를 갱신한다.
# GitHub Actions(deploy-develop.yml) 또는 cron / 수동 실행용.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[deploy-minipc] repo: $ROOT"
git fetch --prune origin
git switch develop
git pull --ff-only origin develop

# dashboard는 ./apps/dashboard 볼륨 + npm run dev 이므로 pull 후 소스 반영이 기본이다.
# API/AICC 이미지와 Vite 환경변수(env.js) 반영을 위해 compose 재기동을 함께 수행한다.
docker compose up -d --build dashboard api aicc
docker compose exec -T api alembic upgrade head
docker compose restart dashboard
docker compose ps

echo "[deploy-minipc] done"
