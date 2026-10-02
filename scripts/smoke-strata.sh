#!/usr/bin/env bash
set -euo pipefail

# Strata API smoke test: basic API, text completion, and OpenAI tool calling.
# The health wait allows for the first model download/setup and load.
base_url="${STRATA_BASE_URL:-http://127.0.0.1:8080}"
base_url="${base_url%/}"
model="${STRATA_MODEL_ID:-qwen3.8-flash-next}"
max_wait="${STRATA_HEALTH_TIMEOUT:-3600}"

request() {
  local name="$1"
  local url="$2"
  local body="${3:-}"
  local expected_tool="${4:-}"
  local status out
  local -a curl_args

  out="$(mktemp)"
  curl_args=(--silent --show-error --output "$out" --write-out '%{http_code}')
  if [[ -n "${STRATA_API_KEY:-}" ]]; then
    curl_args+=(-H "Authorization: Bearer ${STRATA_API_KEY}")
  fi
  if [[ -n "$body" ]]; then
    curl_args+=(-H 'Content-Type: application/json' --data "$body")
  fi
  if ! status="$(curl "${curl_args[@]}" "$url")"; then
    status=000
  fi
  if [[ "$status" != 200 ]]; then
    printf '%s returned HTTP %s\n' "$url" "$status" >&2
    cat "$out" >&2 || true
    rm -f "$out"
    return 1
  fi
  printf '%s: HTTP %s\n' "$name" "$status"

  if [[ -n "$expected_tool" ]]; then
    python3 - "$out" "$expected_tool" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    response = json.load(f)
expected = sys.argv[2]
choice = response["choices"][0]
message = choice["message"]
calls = message.get("tool_calls") or []
if choice.get("finish_reason") != "tool_calls":
    raise SystemExit(f"expected finish_reason=tool_calls, got {choice.get('finish_reason')!r}")
call = next((c for c in calls if c.get("function", {}).get("name") == expected), None)
if call is None:
    raise SystemExit(f"expected tool call {expected!r}; got {[c.get('function', {}).get('name') for c in calls]!r}")
args = call["function"].get("arguments", {})
if isinstance(args, str):
    args = json.loads(args)
if not isinstance(args, dict):
    raise SystemExit(f"tool arguments must be a JSON object, got {type(args).__name__}")
print(f"tool call: {expected}({json.dumps(args, ensure_ascii=False)})")
PY
  fi
  rm -f "$out"
}

# Wait for the server to come up (download + model load + API open).
deadline=$(( $(date +%s) + max_wait ))
while :; do
  if curl --max-time 5 --silent --output /dev/null "${base_url}/health"; then
    break
  fi
  if [[ "$(date +%s)" -ge "$deadline" ]]; then
    printf 'Strata not healthy after %s s at %s\n' "$max_wait" "$base_url" >&2
    printf 'Check: docker compose -f docker/strata/compose.yaml logs strata\n' >&2
    exit 1
  fi
  printf 'waiting for Strata (first start downloads the model) ... %s\n' "$base_url"
  sleep 15
done

request health "${base_url}/health"
request models "${base_url}/v1/models"
request status "${base_url}/v1/status"
request chat "${base_url}/v1/chat/completions" \
  "{\"model\":\"${model}\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with OK.\"}],\"max_tokens\":16}"
request tool-call "${base_url}/v1/chat/completions" \
  "{\"model\":\"${model}\",\"messages\":[{\"role\":\"user\",\"content\":\"Call smoke_report now with message exactly smoke. Do not reply with prose.\"}],\"tools\":[{\"type\":\"function\",\"function\":{\"name\":\"smoke_report\",\"description\":\"Report the smoke-test status.\",\"parameters\":{\"type\":\"object\",\"properties\":{\"message\":{\"type\":\"string\"}},\"required\":[\"message\"],\"additionalProperties\":false}}}],\"max_tokens\":128}" \
  smoke_report

printf 'Strata API smoke test passed at %s\n' "$base_url"
