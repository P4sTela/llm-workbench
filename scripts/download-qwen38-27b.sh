#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$root/scripts/download-model.py" \
  "$root/models/manifests/qwen3.8-27b-ninfer-v2.json"
