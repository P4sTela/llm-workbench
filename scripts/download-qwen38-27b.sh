#!/usr/bin/env bash
set -euo pipefail

# This is the revision recorded in models/qwen3.8-27b.md. No Hugging Face
# credentials or private endpoints are needed for this public artifact.
readonly MODEL_REPO="neroued/Qwen3.8-27B-NInfer"
readonly MODEL_REVISION="3526913"
readonly MODEL_FILE="qwen3_8_27b-v2.ninfer"
readonly MODEL_BYTES=18210531328
readonly MODEL_SHA256="eec39564993d6e9c7d5e383382a760f093465c9d163ec9a1bd6b80199514bf3e"
readonly MODEL_URL="https://huggingface.co/${MODEL_REPO}/resolve/${MODEL_REVISION}/${MODEL_FILE}?download=true"

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
model_dir="${NINFER_MODEL_DIR:-$root/models}"
model_path="$model_dir/$MODEL_FILE"
partial_path="$model_path.part"

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

check_model() {
  [ -f "$1" ] || return 1
  [ "$(wc -c <"$1" | tr -d '[:space:]')" = "$MODEL_BYTES" ] || return 1
  [ "$(sha256_file "$1")" = "$MODEL_SHA256" ]
}

mkdir -p -- "$model_dir"
if check_model "$model_path"; then
  printf 'Model already verified: %s\n' "$model_path"
  exit 0
fi

printf 'Downloading %s at HF revision %s...\n' "$MODEL_FILE" "$MODEL_REVISION"
if ! curl --fail --location --retry 3 --retry-delay 2 --continue-at - \
  --output "$partial_path" "$MODEL_URL"; then
  printf 'Download failed; rerun to resume: %s\n' "$partial_path" >&2
  exit 1
fi

if ! check_model "$partial_path"; then
  printf 'Checksum or size mismatch for %s\n' "$partial_path" >&2
  printf 'Expected %s bytes, SHA-256 %s\n' "$MODEL_BYTES" "$MODEL_SHA256" >&2
  exit 1
fi

mv -- "$partial_path" "$model_path"
printf 'Model ready and verified: %s\n' "$model_path"
