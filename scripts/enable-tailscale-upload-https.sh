#!/usr/bin/env bash
# Enable Tailscale Serve HTTPS → mini-PC API for browser media uploads.
# Prerequisite: HTTPS Certificates enabled at https://login.tailscale.com/admin/dns
set -euo pipefail

API_UPSTREAM="${API_UPSTREAM:-http://100.86.5.67:8000}"
HOSTNAME="${TAILSCALE_HOSTNAME:-docker-test.tail0c814d.ts.net}"

if ! command -v tailscale >/dev/null; then
  echo "tailscale CLI not found" >&2
  exit 1
fi

if ! curl -fsS --max-time 3 "${API_UPSTREAM}/health" >/dev/null; then
  echo "API upstream not healthy: ${API_UPSTREAM}/health" >&2
  exit 1
fi

echo "Configuring Tailscale Serve: https://${HOSTNAME} → ${API_UPSTREAM}"
sudo timeout 15 tailscale serve reset >/dev/null 2>&1 || true

# Serve prompts/hangs when HTTPS Certificates are not enabled on the tailnet.
set +e
serve_out="$(sudo timeout 20 tailscale serve --bg --https=443 "${API_UPSTREAM}" 2>&1)"
serve_rc=$?
set -e
echo "${serve_out}"

if echo "${serve_out}" | grep -qiE 'does not support getting TLS|Serve is not enabled|enable HTTPS|login.tailscale.com'; then
  echo >&2
  echo "Tailscale HTTPS Certificates are not enabled for this tailnet." >&2
  echo "1) Open https://login.tailscale.com/admin/dns" >&2
  echo "2) Enable MagicDNS (if needed) and HTTPS Certificates" >&2
  echo "3) Re-run this script" >&2
  exit 2
fi

if [[ "${serve_rc}" -ne 0 ]]; then
  echo "tailscale serve failed (exit ${serve_rc})" >&2
  exit "${serve_rc}"
fi

sudo tailscale serve status
echo
echo "Smoke:"
curl -fsS --max-time 8 "https://${HOSTNAME}/health"
echo
