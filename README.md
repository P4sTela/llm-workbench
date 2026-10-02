# LLM Workbench

A personal workbench for running and comparing open-weight LLMs across different machines.

This is a public collection of Docker configurations, machine-specific settings, and notes from real runs. It is intentionally practical rather than a general-purpose framework or a production platform.

## Current focus

- Qwen3.8-Flash-Next on an NVIDIA RTX 4090 as the primary inference runtime
- Strata as the canonical engine; NInfer and llama.cpp configurations remain available for historical runs and comparisons
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

## Canonical runtime: Strata / Qwen3.8-Flash-Next / RTX 4090

`docker/strata/` builds the official Strata engine (MIT) at a pinned commit and serves Qwen3.8-Flash-Next on the RTX 4090. Strata is the primary runtime configuration for this workbench, not a side-by-side A/B service. Its expert weights live in system RAM, with the active working set on the GPU. The VM205 image build, first model download, and API smoke test have not yet been run; runtime performance is therefore unverified (see [`notes/strata-qwen38-flash-next-4090.md`](notes/strata-qwen38-flash-next-4090.md)).

On a Linux host with an RTX 4090, an NVIDIA driver >= 580, Docker, and the NVIDIA Container Toolkit:

```bash
cp .env.example .env
```

For VM205, edit the local `.env` to bind the service only to its NetBird address (`STRATA_BIND_ADDRESS=100.0.0.159`) and set `STRATA_PORT=8080`. Set a non-empty `STRATA_API_KEY` before exposing the API over the VPN. Keep `.env` untracked; the compose file maps that key to Strata's API authentication. Do not start another inference engine on the same GPU at the same time.

```bash
docker compose -f docker/strata/compose.yaml up --build -d
```

Follow the first-start model setup/download:

```bash
docker compose -f docker/strata/compose.yaml logs -f strata
```

The default profile is `configs/strata-qwen38-flash-next-4090.env` (`IQ3_S`, 131072-token context, vision enabled, GPU 0). Model data and setup state are stored outside Git in `models/strata-data` by default; set `STRATA_DATA_DIR` in `.env` to move them elsewhere. The optional `configs/strata-qwen38-flash-next-4090-iq2xs.env` profile is a smaller-memory alternative, not a second service.

Run the API smoke test from the host. Set/export `STRATA_API_KEY` in the shell if API authentication is enabled:

```bash
STRATA_BASE_URL=http://127.0.0.1:8080 bash scripts/smoke-strata.sh
```

The smoke test checks health, model/status endpoints, a text completion, and an OpenAI-compatible tool call. The API model id is `qwen3.8-flash-next`. If connecting from another NetBird peer, use `http://100.0.0.159:8080` and provide the API key through the client's secret/config mechanism.

## Verified historical runtime: NInfer V2 / Qwen3.8-27B / RTX 4090

The previous primary runtime is a verified 245760-token long-context run on VM205 with an NVIDIA RTX 4090. Its files are retained for reference and repeatability; NInfer is no longer the workbench's default runtime. It builds the P4sTela fork of `ninfer-4090` at commit `a889ce4377d0f88093bb491d851d29eb1555e4f8` and uses the `ninfer-4090:dflash2` image. The model stays on the host and is mounted read-only; it is not part of the image.

### Reproducing the historical NInfer run

On a Linux host with an RTX 4090, a recent NVIDIA driver, Docker, and the NVIDIA Container Toolkit:

```bash
export MODEL_DIR=/path/to/ninfer-models
python3 scripts/download-model.py models/manifests/qwen3.8-27b-ninfer-v2.json
bash scripts/download-qwen38-dflash2.sh
bash scripts/graft-qwen38-dflash2.sh
MODEL_DIR="$MODEL_DIR" docker compose -f docker/ninfer/compose.yaml up --build
```

The manifest-driven command uses `MODEL_DIR`, then `NINFER_MODEL_DIR`, and otherwise `models/`. Each exact quantization or artifact gets its own manifest. The compatibility command `NINFER_MODEL_DIR="$MODEL_DIR" bash scripts/download-qwen38-27b.sh` continues to use the same base-artifact manifest.

In another terminal, run the local API check:

```bash
bash scripts/smoke-ninfer.sh
```

The NInfer compose file defaults to `127.0.0.1:8080`; override it with `NINFER_BIND_ADDRESS` and `NINFER_PORT`. Compose selects `configs/ninfer-v2-qwen38-4090-245760-e8-dflash2.env` by default. Do not run this service concurrently with Strata on the same GPU.

### Verified NInfer DFlash2 runtime

The VM205 run uses these runtime reservations: `MAX_CONTEXT=245760`, `KV_CAPACITY=245760`, `PREFILL_CHUNK=512`, `KV_DTYPE=rk4v4-e8`, `SPEC=dflash2`, `DRAFT_TOKENS=7`, `LM_HEAD_DRAFT=false`, `PRESERVE_THINKING=true`, `DEFAULT_MAX_TOKENS=16384`, `HOST_KV_MIB=32768`, `HOST_STATE_SLOTS=16`, `MAX_CONCURRENCY=1`, `MAX_PENDING_REQUESTS=16`, and `PENDING_TIMEOUT_MS=600000`. The artifact is `qwen3_8_27b-v2-dflash2.ninfer`, with 20,437,336,576 bytes and SHA-256 `0634abb07024221de141456cf04a42ab74b18bc38e1b781c6eb2e062a467eec3`.

`notes/qwen38-dflash2.md` records the drafter inputs, graft provenance, and measured VM205 artifact metadata. The generated graft report is local metadata and must not be committed.

## NInfer MTP3 comparison and legacy 262k profiles

`configs/ninfer-v2-qwen38-4090-245760-e8-mtp3.env` is the 245760-token MTP3 comparison profile. It uses the base `qwen3_8_27b.ninfer`, three draft tokens, and `LM_HEAD_DRAFT=true`; GPU validation is pending for this comparison.

The existing NInfer `262k` profile files remain for historical reference. `262144` is an unsupported/failed-capacity experiment for the RTX 4090 NInfer runtime, not the default for this workbench.

## License

No repository license has been selected yet. Until a license is added, the contents should not be assumed to be available for reuse. Model and dependency licenses remain the responsibility of their respective upstream projects.
