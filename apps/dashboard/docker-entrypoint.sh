#!/bin/sh
set -eu

# Compose의 node_modules named volume은 이미지보다 오래 살아남는다. package-lock이
# 바뀌었거나 필수 패키지가 빠졌을 때만 다시 설치해 새 이미지의 의존성을 가리지 않게 한다.
lock_hash="$(sha256sum package-lock.json | awk '{print $1}')"
stamp_file="node_modules/.ai-s-eye-package-lock.sha256"
installed_hash=""

if [ -f "$stamp_file" ]; then
  installed_hash="$(sed -n '1p' "$stamp_file")"
fi

if [ "$installed_hash" != "$lock_hash" ] || [ ! -d node_modules/react-router-dom ]; then
  npm ci
  printf '%s\n' "$lock_hash" > "$stamp_file"
fi

exec "$@"
