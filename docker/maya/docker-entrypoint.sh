#!/bin/sh
# Keep upstream's per-model setup flow, with pinned workbench downloads.
set -eu
cd /opt/maya

MODEL="${MODEL:-Maya-M-Derisked}"
CONTEXT="${CONTEXT:-32768}"
GPUS="${GPUS:-0}"
PARALLEL="${PARALLEL:-1}"
DRAFT="${DRAFT:-mtp}"
VISION="${VISION:-no}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"
API_KEY="${API_KEY:-}"
# Upstream's calibration key does not include the drafter. Separate its home
# per draft mode so a DFlash setup cannot reuse MTP-only tuning (or vice versa).
HOME="/data/home/$DRAFT"
XDG_CONFIG_HOME="$HOME/.config"
export MODEL CONTEXT GPUS PARALLEL DRAFT VISION HOST PORT API_KEY HOME XDG_CONFIG_HOME

if [ "$MODEL" != "Maya-M-Derisked" ] || [ "$VISION" != "no" ]; then
  echo "This recipe supports MODEL=Maya-M-Derisked, VISION=no only." >&2
  exit 1
fi
case "$DRAFT" in
  mtp|dflash2) ;;
  *) echo "DRAFT must be mtp or dflash2." >&2; exit 1 ;;
esac
case "${REINSTALL:-0}" in
  0|1) ;;
  *) echo "REINSTALL must be 0 or 1." >&2; exit 1 ;;
esac

# Only the selected external drafter is fetched; MTP is in the target weights.
download() {
  MODEL_DIR="/data/models/$MODEL" .venv/bin/python /opt/workbench/download-model.py /opt/workbench/model.json
  if [ "$DRAFT" = "dflash2" ]; then
    MODEL_DIR=/data/models/GLM-5.3-Flash-DFlash2 .venv/bin/python /opt/workbench/download-model.py /opt/workbench/dflash2.json
  fi
}
command="${1:-serve}"
if [ "$#" -gt 1 ]; then
  echo "Usage: docker-entrypoint.sh [serve|download|prepare|calibrate|check]" >&2
  exit 1
fi
case "$command" in
  download) download; exit 0 ;;
  check) exec .venv/bin/python maya.py --check --plain ;;
  serve|prepare|calibrate) ;;
  *) echo "Usage: docker-entrypoint.sh [serve|download|prepare|calibrate|check]" >&2; exit 1 ;;
esac

mkdir -p /data/config /data/logs "$HOME"
tag="maya-maya-m-derisked"
cfg="/data/config/$tag.json"
local_cfg="/opt/maya/$tag.json"

# Do not accidentally label an installed drafter as another profile. Context,
# GPU/auth choices and dashboard settings remain persisted until explicit setup.
if [ -f "$cfg" ] && [ "${REINSTALL:-0}" != "1" ]; then
  .venv/bin/python - "$cfg" <<'PY'
import json
import os
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    cfg = json.load(stream)
args = cfg["args"]

expected = {
    "MODEL": (cfg.get("installer") or {}).get("quant"),
    "DRAFT": "dflash2" if "--dflash" in args else "mtp",
}
changed = [name for name, installed in expected.items() if installed != os.environ[name]]
if changed:
    sys.exit("Installed config differs for " + ", ".join(changed) +
             "; stop Maya and run prepare with REINSTALL=1 to change it.")
PY
fi

# Calibration operates on an already prepared config, never implicitly runs setup.
if [ "$command" = "calibrate" ]; then
  if [ "${REINSTALL:-0}" = "1" ] || [ ! -f "$cfg" ]; then
    echo "Run prepare first (REINSTALL=1 there if changing the profile), then calibrate without REINSTALL." >&2
    exit 1
  fi
  exec .venv/bin/python /opt/workbench/calibrate.py --config "$cfg" --no-start
fi

if [ "${REINSTALL:-0}" = "1" ] || [ ! -f "$cfg" ]; then
  if [ -f "$cfg" ]; then
    mkdir -p /data/config/backups
    backup="$(mktemp -d "/data/config/backups/$tag.XXXXXX")"
    cp "$cfg" "$backup/$tag.json"
    if [ -f "/data/config/$tag.shared-settings.json" ]; then
      cp "/data/config/$tag.shared-settings.json" "$backup/"
    fi
    echo "Preserved installed config/dashboard snapshot: $backup"
  fi
  download
  # Upstream writes this fixed filename during setup. Use a regular working copy,
  # never a symlink to persisted state: a failed setup must leave it untouched.
  if [ -L "$local_cfg" ]; then
    rm "$local_cfg"
  fi
  if [ -f "$cfg" ]; then
    cp "$cfg" "$local_cfg"
  fi
  .venv/bin/python maya.py --setup --yes --no-start --plain \
    --model "$MODEL" --models-dir /data/models --no-vision --draft "$DRAFT" \
    --context "$CONTEXT" --gpus "$GPUS" --parallel "$PARALLEL" \
    --host "$HOST" --port "$PORT" --api-key "$API_KEY"
  # Install only after upstream has successfully generated a regular config.
  test -f "$local_cfg" && test ! -L "$local_cfg"
  cp "$local_cfg" "$cfg.tmp"
  mv "$cfg.tmp" "$cfg"
fi

# Upstream stats every config it finds. Link only AFTER the target exists; logs
# and dashboard state are kept beside the selected config on the mounted volume.
ln -sf "$cfg" "$local_cfg"
ln -sf "/data/logs/$tag.log" "/opt/maya/$tag.log"
if [ "$command" = "prepare" ]; then
  echo "Prepared $cfg (DRAFT=$DRAFT); no server started."
  exit 0
fi
# An explicit config avoids upstream's most-recent-model selection. No manifest
# verification/download/setup is performed on an installed normal restart.
exec .venv/bin/python maya.py --plain --config "$cfg"
