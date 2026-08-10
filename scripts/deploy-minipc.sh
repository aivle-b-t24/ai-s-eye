#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${AISEYE_APP_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="${AISEYE_ENV_FILE:-.env}"
LOCK_FILE="${AISEYE_DEPLOY_LOCK_FILE:-/tmp/ai-s-eye-minipc-deploy.lock}"

cd "$ROOT"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[deploy-minipc] another deployment is already running" >&2
  exit 1
fi

compose() {
  docker compose --env-file "$ENV_FILE" "$@"
}

remove_stateless_service_containers() {
  local service
  local -a container_ids

  for service in order-simulator api aicc dashboard store-state-cleanup; do
    mapfile -t container_ids < <(compose ps -aq "$service")
    if (( ${#container_ids[@]} > 0 )); then
      echo "[deploy-minipc] replacing $service containers: ${container_ids[*]}"
      docker rm -f "${container_ids[@]}"
    fi
  done
}

diagnose() {
  local exit_code=$?
  if (( exit_code != 0 )); then
    echo "[deploy-minipc] deployment failed (exit=$exit_code)" >&2
    compose ps >&2 || true
    compose --profile demo logs --tail=80 api aicc dashboard order-simulator >&2 || true
  fi
  exit "$exit_code"
}
trap diagnose EXIT

wait_for_url() {
  local name=$1
  local url=$2
  local attempt
  for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null; then
      echo "[deploy-minipc] $name healthy: $url"
      return 0
    fi
    sleep 2
  done
  echo "[deploy-minipc] $name health check failed: $url" >&2
  return 1
}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[deploy-minipc] missing environment file: $ROOT/$ENV_FILE" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "[deploy-minipc] tracked files are modified on the server; refusing deployment" >&2
  git status --short >&2
  exit 1
fi

if [[ "${AISEYE_SKIP_GIT_UPDATE:-false}" != "true" ]]; then
  git fetch --prune origin develop
  git switch develop
  git pull --ff-only origin develop
fi

deployed_sha=$(git rev-parse HEAD)
echo "[deploy-minipc] deploying $deployed_sha"

compose config --quiet
compose up -d db

mkdir -p backups
backup_path="backups/minipc-predeploy-$(date -u +%Y%m%dT%H%M%SZ)-${deployed_sha:0:8}.dump"
compose exec -T db sh -lc \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  >"$backup_path"
chmod 600 "$backup_path"
echo "[deploy-minipc] database backup: $backup_path"

compose --profile demo build api aicc dashboard store-state-cleanup order-simulator
compose run --rm --no-deps api alembic upgrade head
remove_stateless_service_containers
compose --profile demo up -d --no-build db api aicc dashboard store-state-cleanup order-simulator

api_address=$(compose port api 8000)
aicc_address=$(compose port aicc 8100)
dashboard_address=$(compose port dashboard 5173)

wait_for_url "API" "http://$api_address/health"
wait_for_url "AICC" "http://$aicc_address/healthz"
wait_for_url "Dashboard" "http://$dashboard_address/"

compose --profile demo ps
printf '%s\n' "$deployed_sha" >.deployed-minipc-sha
echo "[deploy-minipc] completed $deployed_sha"
