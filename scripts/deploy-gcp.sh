#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${AISEYE_APP_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="${AISEYE_ENV_FILE:-.env.gcp}"
COMPOSE_FILE="${AISEYE_COMPOSE_FILE:-compose.gcp.yml}"
LOCK_FILE="${AISEYE_DEPLOY_LOCK_FILE:-/tmp/ai-s-eye-gcp-deploy.lock}"

cd "$ROOT"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[deploy-gcp] another deployment is already running" >&2
  exit 1
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

remove_stateless_service_containers() {
  local service
  local -a container_ids

  for service in order-simulator api aicc dashboard store-state-cleanup; do
    mapfile -t container_ids < <(compose ps -aq "$service")
    if (( ${#container_ids[@]} > 0 )); then
      echo "[deploy-gcp] replacing $service containers: ${container_ids[*]}"
      docker rm -f "${container_ids[@]}"
    fi
  done
}

diagnose() {
  local exit_code=$?
  if (( exit_code != 0 )); then
    echo "[deploy-gcp] deployment failed (exit=$exit_code)" >&2
    compose ps >&2 || true
    compose --profile demo logs --tail=100 api aicc dashboard order-simulator >&2 || true
  fi
  exit "$exit_code"
}
trap diagnose EXIT

wait_for_url() {
  local name=$1
  local url=$2
  local attempt
  for attempt in $(seq 1 45); do
    if curl --fail --silent --show-error --max-time 8 "$url" >/dev/null; then
      echo "[deploy-gcp] $name healthy: $url"
      return 0
    fi
    sleep 2
  done
  echo "[deploy-gcp] $name health check failed: $url" >&2
  return 1
}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[deploy-gcp] missing environment file: $ROOT/$ENV_FILE" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "[deploy-gcp] tracked files are modified on the server; refusing deployment" >&2
  git status --short >&2
  exit 1
fi

if [[ "${AISEYE_SKIP_GIT_UPDATE:-false}" != "true" ]]; then
  git fetch --prune origin main
  git switch main
  git pull --ff-only origin main
fi

deployed_sha=$(git rev-parse HEAD)
echo "[deploy-gcp] deploying $deployed_sha"

compose config --quiet
compose up -d db

mkdir -p backups
backup_path="backups/gcp-predeploy-$(date -u +%Y%m%dT%H%M%SZ)-${deployed_sha:0:8}.dump"
compose exec -T db sh -lc \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  >"$backup_path"
chmod 600 "$backup_path"
echo "[deploy-gcp] database backup: $backup_path"

compose --profile demo build api aicc dashboard store-state-cleanup order-simulator migrate
compose --profile tools run --rm migrate
remove_stateless_service_containers
compose --profile demo up -d --no-build --remove-orphans

wait_for_url "local API" "http://127.0.0.1:8000/health"
wait_for_url "local AICC" "http://127.0.0.1:8100/healthz"
wait_for_url "local Dashboard" "http://127.0.0.1/"
wait_for_url "public API" "https://aiseye-api.ldhcloud.com/health"
wait_for_url "public AICC" "https://aiseye-ai.ldhcloud.com/healthz"
wait_for_url "public Dashboard" "https://aiseye.ldhcloud.com/"

compose --profile demo ps
printf '%s\n' "$deployed_sha" >.deployed-gcp-sha
echo "[deploy-gcp] completed $deployed_sha"
