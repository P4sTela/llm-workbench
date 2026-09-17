#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
model_dir="${MODEL_DIR:-${NINFER_MODEL_DIR:-$root/models}}"
artifact="$model_dir/qwen3_8_27b-v2.ninfer"
dflash2_dir="${DFlash2_MODEL_DIR:-$model_dir/dflash2-source}"
out="$model_dir/qwen3_8_27b-v2-dflash2.ninfer"
device="${DFlash2_DEVICE:-cpu}"

[[ -f "$artifact" ]] || { printf 'missing source artifact: %s\n' "$artifact" >&2; exit 1; }
[[ -f "$dflash2_dir/config.json" ]] || { printf 'missing DFlash2 config: %s\n' "$dflash2_dir/config.json" >&2; exit 1; }
[[ -f "$dflash2_dir/model.safetensors" ]] || { printf 'missing DFlash2 weights: %s\n' "$dflash2_dir/model.safetensors" >&2; exit 1; }

cd -- "$root"
exec python3 -m tools.artifact.graft_dflash2_w8 \
  --artifact "$artifact" \
  --dflash2-model "$dflash2_dir" \
  --out "$out" \
  --device "$device"
