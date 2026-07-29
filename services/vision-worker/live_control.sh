#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RUN_DIR="${SCRIPT_DIR}/outputs/live"
PID_FILE="${RUN_DIR}/vision-live.pid"
LOG_FILE="${RUN_DIR}/vision-live.log"

VISION_PYTHON="${VISION_PYTHON:-${PROJECT_ROOT}/.venv-vision/bin/python}"
AISEYE_CAFE_ROOT="${AISEYE_CAFE_ROOT:-/home/kokdo/datasets/ai-s-eye/cafe-selected/Cafe_Dataset/Dataset/cafe}"
AISEYE_CAFE_MODEL="${AISEYE_CAFE_MODEL:-/home/kokdo/datasets/ai-s-eye/models/best.pt}"
AISEYE_API_BASE_URL="${AISEYE_API_BASE_URL:-http://localhost:8000}"
AISEYE_ROI_REFRESH_SECONDS="${AISEYE_ROI_REFRESH_SECONDS:-2}"
VISION_LIVE_INTERVAL="${VISION_LIVE_INTERVAL:-0.5}"

mkdir -p "${RUN_DIR}"

is_running() {
  [[ -s "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null
}

start_live() {
  if is_running; then
    echo "Vision LIVE가 이미 실행 중입니다. PID=$(cat "${PID_FILE}")"
    return
  fi

  [[ -x "${VISION_PYTHON}" ]] || {
    echo "Vision 가상환경을 찾을 수 없습니다: ${VISION_PYTHON}" >&2
    exit 1
  }
  [[ -d "${AISEYE_CAFE_ROOT}" ]] || {
    echo "CAFE 이미지 경로를 찾을 수 없습니다: ${AISEYE_CAFE_ROOT}" >&2
    exit 1
  }
  [[ -f "${AISEYE_CAFE_MODEL}" ]] || {
    echo "Vision 모델을 찾을 수 없습니다: ${AISEYE_CAFE_MODEL}" >&2
    exit 1
  }
  curl --fail --silent "${AISEYE_API_BASE_URL}/health" >/dev/null || {
    echo "API가 응답하지 않습니다: ${AISEYE_API_BASE_URL}/health" >&2
    exit 1
  }

  (
    cd "${PROJECT_ROOT}"
    docker compose --profile demo stop vision-replay >/dev/null 2>&1 || true
    nohup env \
      PYTHONUNBUFFERED=1 \
      AISEYE_CAFE_ROOT="${AISEYE_CAFE_ROOT}" \
      AISEYE_CAFE_MODEL="${AISEYE_CAFE_MODEL}" \
      AISEYE_API_BASE_URL="${AISEYE_API_BASE_URL}" \
      AISEYE_ROI_REFRESH_SECONDS="${AISEYE_ROI_REFRESH_SECONDS}" \
      "${VISION_PYTHON}" "${SCRIPT_DIR}/cafe_stores.py" \
      --live --loop --post "${AISEYE_API_BASE_URL}" \
      --interval "${VISION_LIVE_INTERVAL}" \
      >>"${LOG_FILE}" 2>&1 &
    echo "$!" >"${PID_FILE}"
  )

  sleep 2
  if ! is_running; then
    echo "Vision LIVE 시작에 실패했습니다." >&2
    tail -n 30 "${LOG_FILE}" >&2 || true
    exit 1
  fi
  echo "Vision LIVE를 시작했습니다. PID=$(cat "${PID_FILE}")"
  echo "로그: ${LOG_FILE}"
}

stop_live() {
  if ! is_running; then
    echo "실행 중인 Vision LIVE가 없습니다."
    rm -f "${PID_FILE}"
    return
  fi

  pid="$(cat "${PID_FILE}")"
  kill "${pid}"
  for _ in {1..20}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      rm -f "${PID_FILE}"
      echo "Vision LIVE를 종료했습니다."
      return
    fi
    sleep 0.25
  done
  kill -9 "${pid}"
  rm -f "${PID_FILE}"
  echo "Vision LIVE를 강제 종료했습니다."
}

show_status() {
  if is_running; then
    echo "Vision LIVE 실행 중: PID=$(cat "${PID_FILE}")"
  else
    echo "Vision LIVE 중지됨"
  fi
  echo "API: ${AISEYE_API_BASE_URL}"
  echo "ROI 확인 주기: ${AISEYE_ROI_REFRESH_SECONDS}초"
  echo "로그: ${LOG_FILE}"
}

case "${1:-status}" in
  start) start_live ;;
  stop) stop_live ;;
  restart) stop_live; start_live ;;
  status) show_status ;;
  logs) tail -f "${LOG_FILE}" ;;
  *)
    echo "사용법: $0 {start|stop|restart|status|logs}" >&2
    exit 1
    ;;
esac
