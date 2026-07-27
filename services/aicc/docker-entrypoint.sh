#!/bin/sh
set -eu

mounted_credentials="/run/secrets/google_adc.json"
runtime_credentials="/run/aicc/google_adc.json"

if [ -s "$mounted_credentials" ]; then
    chown appuser:appuser /run/aicc
    chmod 0700 /run/aicc
    install -m 0400 -o appuser -g appuser "$mounted_credentials" "$runtime_credentials"
    export GOOGLE_APPLICATION_CREDENTIALS="$runtime_credentials"
else
    unset GOOGLE_APPLICATION_CREDENTIALS
fi

exec gosu appuser "$@"
