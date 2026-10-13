#!/usr/bin/env bash
set -euo pipefail

# Maya API smoke test: readiness, model discovery, text, and OpenAI tool calling.
# Allow a generous window for the initial model download and engine load.
base_url="${MAYA_BASE_URL:-http://127.0.0.1:8080}"
base_url="${base_url%/}"
model="${MAYA_MODEL_ID:-}"
max_wait="${MAYA_HEALTH_TIMEOUT:-7200}"
if [[ ! "$max_wait" =~ ^[1-9][0-9]*$ ]]; then
  printf 'MAYA_HEALTH_TIMEOUT must be a positive integer in seconds\n' >&2
  exit 1
fi

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
curl_args=(--silent --show-error --connect-timeout 5)
if [[ -n "${MAYA_API_KEY:-}" ]]; then
  curl_args+=(-H "Authorization: Bearer ${MAYA_API_KEY}")
fi

request() {
  local name="$1"
  local url="$2"
  local timeout="$3"
  local body_file="${4:-}"
  local status
  local -a args
  args=("${curl_args[@]}" --max-time "$timeout" --output "$work_dir/$name.json" --write-out '%{http_code}')
  if [[ -n "$body_file" ]]; then
    args+=(-H 'Content-Type: application/json' --data-binary "@$body_file")
  fi
  if ! status="$(curl "${args[@]}" "$url")"; then
    status=000
  fi
  if [[ "$status" != 200 ]]; then
    printf '%s returned HTTP %s\n' "$url" "$status" >&2
    cat "$work_dir/$name.json" >&2 || true
    return 1
  fi
  printf '%s: HTTP %s\n' "$name" "$status"
}

# Maya also returns HTTP 200 while updating/reloading: require status=ok.
# Each probe and sleep is capped by the remaining readiness window.
deadline=$(( $(date +%s) + max_wait ))
while :; do
  remaining=$(( deadline - $(date +%s) ))
  if (( remaining <= 0 )); then
    printf 'Maya not healthy after %s s at %s (last HTTP %s)\n' "$max_wait" "$base_url" "${status:-000}" >&2
    cat "$work_dir/health.json" >&2 || true
    printf '\nCheck: docker compose -f docker/maya/compose.yaml logs maya\n' >&2
    exit 1
  fi
  probe_timeout=5
  if (( remaining < probe_timeout )); then
    probe_timeout="$remaining"
  fi
  if ! status="$(curl "${curl_args[@]}" --max-time "$probe_timeout" \
    --output "$work_dir/health.json" --write-out '%{http_code}' "${base_url}/health")"; then
    status=000
  fi
  if [[ "$status" == 200 ]] && python3 - "$work_dir/health.json" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as f:
        response = json.load(f)
    ready = isinstance(response, dict) and response.get("status") == "ok"
except (OSError, ValueError):
    ready = False
sys.exit(0 if ready else 1)
PY
  then
    printf 'health: HTTP 200, status=ok\n'
    break
  fi
  printf 'waiting for Maya (first start downloads and loads the model) ... %s (HTTP %s)\n' "$base_url" "$status"
  remaining=$(( deadline - $(date +%s) ))
  sleep_for=15
  if (( remaining < sleep_for )); then
    sleep_for="$remaining"
  fi
  if (( sleep_for > 0 )); then
    sleep "$sleep_for"
  fi
done

request models "${base_url}/v1/models" 30
if [[ -z "$model" ]]; then
  model="$(python3 - "$work_dir/models.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    response = json.load(f)
models = response.get("data")
if not isinstance(models, list):
    raise SystemExit("/v1/models did not return a model list")
model = next((m.get("id") for m in models if isinstance(m, dict)
              and isinstance(m.get("id"), str) and m["id"].strip()), None)
if model is None:
    raise SystemExit("/v1/models returned no loaded model; set MAYA_MODEL_ID only to override discovery")
print(model)
PY
)"
fi
printf 'model: %s\n' "$model"

# Serialize with Python so model IDs cannot break JSON. Thinking is explicitly
# off; the short limits exercise an answer, not an unbounded reasoning trace.
python3 - "$work_dir" "$model" <<'PY'
import json
import pathlib
import sys

work_dir = pathlib.Path(sys.argv[1])
common = {"model": sys.argv[2], "stream": False, "temperature": 0,
          "reasoning_effort": "none"}
chat = {**common, "messages": [{"role": "user", "content": "Reply with exactly MAYA_SMOKE_OK and nothing else."}],
        "max_tokens": 64}
tool = {**common, "messages": [{"role": "user", "content": "Call smoke_report now with message exactly smoke. Do not reply with prose."}],
        "tools": [{"type": "function", "function": {"name": "smoke_report",
                   "description": "Report the smoke-test status.",
                   "parameters": {"type": "object", "properties": {"message": {"type": "string"}},
                                  "required": ["message"], "additionalProperties": False}}}],
        "tool_choice": {"type": "function", "function": {"name": "smoke_report"}},
        "max_tokens": 256}
for name, body in (("chat-request", chat), ("tool-request", tool)):
    (work_dir / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")
PY

request chat "${base_url}/v1/chat/completions" 600 "$work_dir/chat-request.json"
python3 - "$work_dir/chat.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    response = json.load(f)
choice = response["choices"][0]
message = choice["message"]
if choice.get("finish_reason") != "stop":
    raise SystemExit(f"expected text finish_reason=stop, got {choice.get('finish_reason')!r}")
content = message.get("content")
if not isinstance(content, str) or content.strip() != "MAYA_SMOKE_OK":
    raise SystemExit(f"expected text MAYA_SMOKE_OK, got {content!r}")
if message.get("tool_calls"):
    raise SystemExit("text request unexpectedly returned tool calls")
print(f"text completion: {content.strip()}")
PY

request tool-call "${base_url}/v1/chat/completions" 600 "$work_dir/tool-request.json"
python3 - "$work_dir/tool-call.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    response = json.load(f)
choice = response["choices"][0]
message = choice["message"]
if choice.get("finish_reason") != "tool_calls":
    raise SystemExit(f"expected finish_reason=tool_calls, got {choice.get('finish_reason')!r}")
calls = message.get("tool_calls") or []
if not isinstance(calls, list) or len(calls) != 1:
    raise SystemExit(f"expected exactly one tool call, got {calls!r}")
call = calls[0]
if call.get("type") != "function" or not isinstance(call.get("id"), str) or not call["id"]:
    raise SystemExit(f"expected a function tool call with an ID, got {call!r}")
function = call.get("function") or {}
if function.get("name") != "smoke_report":
    raise SystemExit(f"expected smoke_report, got {function.get('name')!r}")
args = function.get("arguments")
if isinstance(args, str):
    args = json.loads(args)
if args != {"message": "smoke"}:
    raise SystemExit(f"expected tool arguments {{'message': 'smoke'}}, got {args!r}")
print(f"tool call: smoke_report({json.dumps(args, ensure_ascii=False)})")
PY

printf 'Maya API smoke test passed at %s\n' "$base_url"
