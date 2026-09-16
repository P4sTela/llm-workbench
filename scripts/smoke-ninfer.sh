#!/usr/bin/env bash
set -euo pipefail

base_url="${NINFER_BASE_URL:-http://127.0.0.1:8080}"
base_url="${base_url%/}"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

request() {
  local name="$1"
  local url="$2"
  local body="${3:-}"
  local status

  if [ -n "$body" ]; then
    status="$(curl --fail --silent --show-error --output "$work_dir/$name.json" \
      --write-out '%{http_code}' -H 'Content-Type: application/json' \
      --data "$body" "$url")"
  else
    status="$(curl --fail --silent --show-error --output "$work_dir/$name.json" \
      --write-out '%{http_code}' "$url")"
  fi
  [ "$status" = 200 ] || {
    printf '%s returned HTTP %s\n' "$url" "$status" >&2
    cat "$work_dir/$name.json" >&2 || true
    return 1
  }
  printf '%s: HTTP %s\n' "$name" "$status"
}

request health "$base_url/health"
request models "$base_url/v1/models"
request chat "$base_url/v1/chat/completions" \
  '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"Reply with OK."}],"max_tokens":8,"reasoning_effort":"none"}'

printf 'NInfer API smoke test passed at %s\n' "$base_url"
