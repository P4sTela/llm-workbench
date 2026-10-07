#!/bin/sh
# Based on the pinned Strata entrypoint (1678de33 / v0.1.39, MIT).
# Keep per-model setup configs on /data; the compiled engine lives in the image.
set -e
cd /opt/strata || exit 1

STRATA_DATA="${STRATA_DATA:-/data}"
FAMILY="${FAMILY:-qwen}"
MODEL="${MODEL:-IQ2_XS}"
CONTEXT="${CONTEXT:-32768}"
VISION="${VISION:-no}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"
API_KEY="${API_KEY:-}"
KV="${KV:-}"                    # empty keeps setup.py's int8 default
GPUS="${GPUS:-}"
GPU="${GPU:-}"
LAYER_SPLIT="${LAYER_SPLIT:-}"
LOW_RAM="${LOW_RAM:-auto}"
RESIDENT_BUDGET_GIB="${RESIDENT_BUDGET_GIB:-}"

# setup.py starts the newest strata-*.json it finds. Link only the selected
# model's recorded config, not every config on the shared data volume.
case "$FAMILY" in qwen) prefix="" ;; *) prefix="${FAMILY}-" ;; esac
tag="${prefix}$(printf '%s' "$MODEL" | tr 'A-Z' 'a-z')"
cfg="$STRATA_DATA/config/strata-$tag.json"
mkdir -p "$STRATA_DATA/config"

# Existing setup decisions are persisted. Changing context, vision, KV, API key
# or resident budget requires a setup pass (REINSTALL=1 inside the container).
# Optional flags follow upstream's KV/GPU convention: pass only when nonempty.
if [ "${REINSTALL:-0}" = "1" ] || [ ! -f "$cfg" ]; then
  echo "Setting up $tag: downloading the model (the engine is already in the image)."
  set -- --family "$FAMILY" --model "$MODEL" --context "$CONTEXT" --vision "$VISION" \
    --data-dir "$STRATA_DATA" --host "$HOST" --api-key "$API_KEY" \
    --port "$PORT" --no-start --low-ram "$LOW_RAM"
  if [ -n "$KV" ]; then set -- "$@" --kv "$KV"; fi
  if [ -n "$GPUS" ]; then set -- "$@" --gpus "$GPUS"; fi
  if [ -n "$GPU" ]; then set -- "$@" --gpu "$GPU"; fi
  if [ -n "$LAYER_SPLIT" ]; then set -- "$@" --layer-split "$LAYER_SPLIT"; fi
  if [ -n "$RESIDENT_BUDGET_GIB" ]; then set -- "$@" --resident-budget-gib "$RESIDENT_BUDGET_GIB"; fi
  .venv/bin/python setup.py --setup --yes "$@"
  [ -e "/opt/strata/strata-$tag.json" ] && { cmp -s "/opt/strata/strata-$tag.json" "$cfg" || cp -f "/opt/strata/strata-$tag.json" "$cfg"; }
else
  [ -e "/opt/strata/strata-$tag.json" ] || ln -s "$cfg" "/opt/strata/strata-$tag.json"
fi

# GPU selection is also passed on restart, as in upstream; setup.py serves
# using the persisted config, including its resident budget.
set -- --port "$PORT"
if [ -n "$GPUS" ]; then set -- "$@" --gpus "$GPUS"; fi
if [ -n "$GPU" ]; then set -- "$@" --gpu "$GPU"; fi
if [ -n "$LAYER_SPLIT" ]; then set -- "$@" --layer-split "$LAYER_SPLIT"; fi
exec .venv/bin/python setup.py "$@"
