# LLM Workbench

A personal workbench for experimenting with open-weight LLMs across different machines.

This is a public collection of Docker configurations, machine-specific settings, and notes from real runs. It is intentionally practical and experimental rather than a general-purpose framework or a production platform.

## Current focus

- Qwen3.8-27B on an NVIDIA RTX 4090
- NInfer and llama.cpp
- Long-context, KV-cache, speculative decoding, reasoning, and tool-use experiments
- Reproducible configurations that can move to another Linux GPU host

## Repository layout

- `docker/` — container definitions and compose files
- `configs/` — reusable runtime profiles
- `models/` — model metadata and download instructions; weights are not committed
- `notes/` — short notes and results from actual runs
- `scripts/` — small helpers for fetching, checking, and smoke-testing

## Principles

- Pin model revisions and record checksums when a run matters.
- Keep model weights outside Git and mount them into containers.
- Keep host-specific values such as bind addresses in local `.env` files.
- Mark results as tested, experimental, or failed instead of presenting guesses as benchmarks.
- Do not commit API keys, personal prompts, session logs, or private tool definitions.

## Canonical runtime: NInfer V2 / Qwen3.8-27B / RTX 4090

The canonical runtime is a verified 245760-token long-context run on VM205 with an
NVIDIA RTX 4090. It builds the P4sTela fork of `ninfer-4090` at the full commit
`a889ce4377d0f88093bb491d851d29eb1555e4f8` and uses the
`ninfer-4090:dflash2` image. The model stays on the host and is mounted read-only; it
is not part of the image.

### Clean-checkout workflow

On a Linux host with an RTX 4090, a recent NVIDIA driver, Docker, and the NVIDIA
Container Toolkit:

```bash
export MODEL_DIR=/path/to/ninfer-models
python3 scripts/download-model.py models/manifests/qwen3.8-27b-ninfer-v2.json
bash scripts/download-qwen38-dflash2.sh
bash scripts/graft-qwen38-dflash2.sh
MODEL_DIR="$MODEL_DIR" docker compose -f docker/ninfer/compose.yaml up --build
```

The manifest-driven command is canonical. It uses `MODEL_DIR`, then
`NINFER_MODEL_DIR`, and otherwise `models/`. Each exact quantization or artifact
gets its own manifest so future multi-file downloads do not need a new downloader.
The compatibility command `NINFER_MODEL_DIR="$MODEL_DIR" bash scripts/download-qwen38-27b.sh`
continues to use the same base-artifact manifest.

In another terminal, run the small local API check:

```bash
bash scripts/smoke-ninfer.sh
```

The published port defaults to `127.0.0.1:8080`; override it with
`NINFER_BIND_ADDRESS` and `NINFER_PORT` when needed. `MODEL_DIR` remains a host
mount override. Compose selects
`configs/ninfer-v2-qwen38-4090-245760-e8-dflash2.env` by default.

### Verified DFlash2 runtime

The VM205 run uses these canonical runtime reservations: `MAX_CONTEXT=245760`,
`KV_CAPACITY=245760`, `PREFILL_CHUNK=512`, `KV_DTYPE=rk4v4-e8`,
`SPEC=dflash2`, `DRAFT_TOKENS=7`, `LM_HEAD_DRAFT=false`,
`PRESERVE_THINKING=true`, `DEFAULT_MAX_TOKENS=16384`, `HOST_KV_MIB=32768`,
`HOST_STATE_SLOTS=16`, `MAX_CONCURRENCY=1`, `MAX_PENDING_REQUESTS=16`, and
`PENDING_TIMEOUT_MS=600000`. The artifact is
`qwen3_8_27b-v2-dflash2.ninfer`, with 20,437,336,576 bytes and SHA-256
`0634abb07024221de141456cf04a42ab74b18bc38e1b781c6eb2e062a467eec3`.

`notes/qwen38-dflash2.md` records the drafter inputs, graft provenance, and the
measured VM205 artifact metadata. The generated graft report is local metadata and
must not be committed.

## MTP3 comparison and legacy 262k profiles

`configs/ninfer-v2-qwen38-4090-245760-e8-mtp3.env` is the 245760-token MTP3
comparison profile. It uses the base `qwen3_8_27b.ninfer`, three draft tokens, and
`LM_HEAD_DRAFT=true`; GPU validation is pending for this A/B comparison.

The existing `262k` profile files remain in the repository for historical reference.
`262144` is an unsupported/failed-capacity experiment for the RTX 4090 canonical
runtime, not a default or a replacement for the verified 245760-token profile.

## License

No repository license has been selected yet. Until a license is added, the contents should not be assumed to be available for reuse. Model and dependency licenses remain the responsibility of their respective upstream projects.
