#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RUN_DIR="${SCRIPT_DIR}/outputs/gpu_worker"
WORKER_PID="${RUN_DIR}/upload_job_worker.pid"
WORKER_LOG="${RUN_DIR}/upload_job_worker.log"
FURNITURE_SCENE_CONTROL="${SCRIPT_DIR}/furniture_scene_control.sh"

VISION_PYTHON="${VISION_PYTHON:-${PROJECT_ROOT}/.venv-vision/bin/python}"
AISEYE_API_BASE_URL="${AISEYE_API_BASE_URL:-http://100.86.5.67:8000}"
AISEYE_CAFE_MODEL="${AISEYE_CAFE_MODEL:-/home/kokdo/datasets/ai-s-eye/models/best.pt}"

if [[ -z "${INTERNAL_API_KEY:-}" && -f "${PROJECT_ROOT}/.env" ]]; then
  INTERNAL_API_KEY="$(sed -n 's/^INTERNAL_API_KEY=//p' "${PROJECT_ROOT}/.env" | tail -n 1)"
fi
INTERNAL_API_KEY="${INTERNAL_API_KEY:-}"

mkdir -p "${RUN_DIR}"

is_worker_running() {
  [[ -s "${WORKER_PID}" ]] && kill -0 "$(cat "${WORKER_PID}")" 2>/dev/null
}

run_furniture_scene_control() {
  local action=$1
  if [[ -x "${FURNITURE_SCENE_CONTROL}" ]]; then
    INTERNAL_API_KEY="${INTERNAL_API_KEY}" "${FURNITURE_SCENE_CONTROL}" "${action}"
  else
    echo "가구/장면 분석 API 선택 기능이 설치되지 않아 건너뜁니다."
  fi
}

start_all() {
  if [[ -z "${INTERNAL_API_KEY}" ]]; then
    echo "INTERNAL_API_KEY is required; set it in the environment or ${PROJECT_ROOT}/.env" >&2
    return 1
  fi

  echo "=== 1. 가구/장면 분석 API (포트 8200) 시작 ==="
  run_furniture_scene_control start || true

  echo "=== 2. 업로드 영상 및 실시간 리플레이 워커 시작 ==="
  if is_worker_running; then
    echo "upload_job_worker가 이미 실행 중입니다. PID=$(cat "${WORKER_PID}")"
  else
    (
      cd "${SCRIPT_DIR}"
      nohup env \
        PYTHONUNBUFFERED=1 \
        AISEYE_API="${AISEYE_API_BASE_URL}" \
        INTERNAL_API_KEY="${INTERNAL_API_KEY}" \
        "${VISION_PYTHON}" upload_job_worker.py \
        --api "${AISEYE_API_BASE_URL}" \
        --api-key "${INTERNAL_API_KEY}" \
        --loop --auto-replay --play-interval 2 \
        --model "${AISEYE_CAFE_MODEL}" \
        >>"${WORKER_LOG}" 2>&1 &
      echo "$!" >"${WORKER_PID}"
    )
    sleep 2
    if is_worker_running; then
      echo "upload_job_worker 시작 완료 (PID=$(cat "${WORKER_PID}") / 로그: ${WORKER_LOG})"
    else
      echo "upload_job_worker 시작 실패. 로그를 확인하세요: ${WORKER_LOG}" >&2
    fi
  fi
}

stop_all() {
  echo "=== 1. 가구/장면 분석 API (포트 8200) 종료 ==="
  run_furniture_scene_control stop || true

  echo "=== 2. 업로드 영상 및 실시간 리플레이 워커 종료 ==="
  if is_worker_running; then
    pid="$(cat "${WORKER_PID}")"
    kill "${pid}" 2>/dev/null || true
    rm -f "${WORKER_PID}"
    echo "upload_job_worker 종료 (PID=${pid})"
  else
    echo "실행 중인 upload_job_worker가 없습니다."
    rm -f "${WORKER_PID}"
  fi
}

status_all() {
  echo "--- 1. 가구/장면 분석 API 상태 ---"
  run_furniture_scene_control status || true
  echo ""
  echo "--- 2. 업로드 영상 및 실시간 리플레이 워커 상태 ---"
  if is_worker_running; then
    echo "upload_job_worker 실행 중: PID=$(cat "${WORKER_PID}")"
    echo "대상 API: ${AISEYE_API_BASE_URL}"
    echo "로그: ${WORKER_LOG}"
  else
    echo "upload_job_worker 중지됨"
  fi
}

case "${1:-status}" in
  start) start_all ;;
  stop) stop_all ;;
  restart) stop_all; start_all ;;
  status) status_all ;;
  logs) tail -f "${WORKER_LOG}" ;;
  *)
    echo "사용법: $0 {start|stop|restart|status|logs}" >&2
    exit 1
    ;;
esac
