#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
model_dir="${MODEL_DIR:-${NINFER_MODEL_DIR:-$root/models}}"
source_dir="$model_dir/dflash2-source"
mkdir -p -- "$source_dir"
MODEL_DIR="$source_dir" exec python3 "$root/scripts/download-model.py" \
  "$root/models/manifests/qwen3.8-27b-dflash2.json"
