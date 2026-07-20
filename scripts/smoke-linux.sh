#!/usr/bin/env bash
set -euo pipefail
base="${PHANTOM_URL:-http://127.0.0.1:5100}"
data="${PHANTOM_DATA_DIR:-}"
token="${PHANTOM_TOKEN:-}"
if [[ -z "$token" && -n "$data" && -r "$data/runtime/.api_token" ]]; then token="$(<"$data/runtime/.api_token")"; fi
curl --fail --silent --show-error "$base/healthz" >/dev/null
if [[ -z "$token" ]]; then
  echo "healthz OK; set PHANTOM_TOKEN or PHANTOM_DATA_DIR for authenticated readyz" >&2
  exit 2
fi
auth_header="Authorization: Bearer ${token}"
curl --fail --silent --show-error -H "$auth_header" "$base/readyz" >/dev/null
curl --fail --silent --show-error -H "$auth_header" "$base/v1/profiles" >/dev/null
printf 'Linux control-plane smoke PASS (%s)\n' "$base"
