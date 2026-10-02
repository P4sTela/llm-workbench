#!/usr/bin/env bash
set -euo pipefail

# Strata API smoke test.
#
# Strata opens no port until the model is loaded, and the first start spends
# most of its time downloading the ~70 GB model into the /data volume. The
# health poll below therefore tolerates a closed port (download phase) and a
# long load, not just a slow API.
base_url="${STRATA_BASE_URL:-http://127.0.0.1:8090}"
base_url="${base_url%/}"
model="${STRATA_MODEL_ID:-qwen3.8-flash-next}"
max_wait="${STRATA_HEALTH_TIMEOUT:-3600}"

request() {
  local name="$1"
  local url="$2"
  local body="${3:-}"
  local status
  local out

  out="$(mktemp)"
  if [ -n "$body" ]; then
    status="$(curl --silent --show-error --output "$out" \
      --write-out '%{http_code}' -H 'Content-Type: application/json' \
      --data "$body" "$url" || echo 000)"
  else
    status="$(curl --silent --show-error --output "$out" \
      --write-out '%{http_code}' "$url" || echo 000)"
  fi
  if [ "$status" != 200 ]; then
    printf '%s returned HTTP %s\n' "$url" "$status" >&2
    cat "$out" >&2 || true
    rm -f "$out"
    return 1
  fi
  printf '%s: HTTP %s\n' "$name" "$status"
  rm -f "$out"
}

# Wait for the server to come up (download + model load + API open).
deadline=$(( $(date +%s) + max_wait ))
while :; do
  if curl --max-time 5 --silent --output /dev/null "${base_url}/health"; then
    break
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    printf 'Strata not healthy after %s s at %s\n' "$max_wait" "$base_url" >&2
    printf 'Check: docker compose -f docker/strata/compose.yaml logs strata\n' >&2
    exit 1
  fi
  printf 'waiting for Strata (first start downloads ~70 GB) ... %s\n' "$base_url"
  sleep 15
done

request health "${base_url}/health"
request models "${base_url}/v1/models"
request status "${base_url}/v1/status"
request chat "${base_url}/v1/chat/completions" \
  "{\"model\":\"${model}\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with OK.\"}],\"max_tokens\":8}"

printf 'Strata API smoke test passed at %s\n' "$base_url"
