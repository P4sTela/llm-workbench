#!/usr/bin/env bash
set -euo pipefail

# llama.cpp API smoke test: health, model list, text completion, and an
# OpenAI-compatible tool call. --jinja must be on for the tool check to pass;
# a failure here usually means the chat template or the tool parser is wrong.
base_url="${LLAMA_BASE_URL:-http://127.0.0.1:8081}"
base_url="${base_url%/}"
model="${LLAMA_MODEL_ID:-qwen3.8-27b-base}"
max_wait="${LLAMA_HEALTH_TIMEOUT:-900}"

request() {
  local name="$1"
  local url="$2"
  local body="${3:-}"
  local expected_tool="${4:-}"
  local status out
  out="$(mktemp)"

  local -a curl_args=(--silent --show-error --output "$out" --write-out '%{http_code}')
  if [[ -n "${LLAMA_API_KEY:-}" ]]; then
    curl_args+=(-H "Authorization: Bearer ${LLAMA_API_KEY}")
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
calls = choice["message"].get("tool_calls") or []
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

deadline=$(( $(date +%s) + max_wait ))
while :; do
  if curl --max-time 5 --silent --output /dev/null "${base_url}/health"; then
    break
  fi
  if [[ "$(date +%s)" -ge "$deadline" ]]; then
    printf 'llama.cpp not healthy after %s s at %s\n' "$max_wait" "$base_url" >&2
    printf 'Check: docker compose -f docker/llama/compose.yaml logs llama\n' >&2
    exit 1
  fi
  printf 'waiting for llama.cpp (model load) ... %s\n' "$base_url"
  sleep 10
done

request health "${base_url}/health"
request models "${base_url}/v1/models"
request chat "${base_url}/v1/chat/completions" \
  "{\"model\":\"${model}\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with OK.\"}],\"max_tokens\":16}"
request tool-call "${base_url}/v1/chat/completions" \
  "{\"model\":\"${model}\",\"messages\":[{\"role\":\"user\",\"content\":\"Call smoke_report now with message exactly smoke. Do not reply with prose.\"}],\"tools\":[{\"type\":\"function\",\"function\":{\"name\":\"smoke_report\",\"description\":\"Report the smoke-test status.\",\"parameters\":{\"type\":\"object\",\"properties\":{\"message\":{\"type\":\"string\"}},\"required\":[\"message\"],\"additionalProperties\":false}}}],\"max_tokens\":128}" \
  smoke_report

printf 'llama.cpp API smoke test passed at %s\n' "$base_url"
