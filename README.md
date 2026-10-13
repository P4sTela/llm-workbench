# LLM Workbench

A personal workbench for running and comparing open-weight LLMs across different machines.

This is a public collection of Docker configurations, machine-specific settings, and notes from real runs. It is intentionally practical rather than a general-purpose framework or a production platform.

## Current focus

- GLM-5.3-Flash Maya-M-Derisked on an NVIDIA RTX 4090 as VM205's active runtime
- Project Maya for GLM; Strata/Qwen recipes retained for rollback, and NInfer/llama.cpp for historical comparisons
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
- Record non-secret machine defaults in recipes; use environment overrides for other hosts and keep secrets in untracked local configuration.
- Mark results as tested, experimental, or failed instead of presenting guesses as benchmarks.
- Do not commit API keys, personal prompts, session logs, or private tool definitions.

## Maya / GLM-5.3-Flash Maya-M-Derisked / RTX 4090

`docker/maya/compose.yaml` is a standalone alternative to Strata, not an overlay or
a second service to run on the same GPU. It builds Project Maya v1.1.0 at
`77697c37be6944e8971e91a4f494332f12a8e31d` for CUDA architecture 89, using upstream's
compiler and build-reuse metadata. The default profile
`configs/maya-glm53-flash-m-derisked-4090-dflash2.env` selects Maya-M-Derisked,
262144 context, GPU 0, one concurrent request, text only, and DFlash2.
Its PCIe share of `0.00` is measured on VM205; recalibrate on other hardware.
The retained `configs/maya-glm53-flash-m-derisked-4090.env` is the 32768-context
comparison profile: `DRAFT=mtp` uses ordinary decode on a single GPU.

The [model manifest](models/manifests/glm53-flash-maya-m-derisked.json) pins all
three GGUF shards to Hugging Face revision
`b0a5474568ab4322ba4b74be5f34308fb4592d57`, exact sizes, and SHA-256 hashes.
Weights total 116,003,563,168 bytes (about 108 GiB); allow additional space for the
pack, image/build cache, and conversation slots. The refusal-reduction edit is
experimental: its method is not public and general capability preservation has
not been established. This is not a guarantee of an entirely uncensored model.
An earlier 256-token Japanese Tiananmen-protests response did not refuse, but
hit the output cap; that single response is not a comprehensive censorship or
quality evaluation.

The [DFlash2 manifest](models/manifests/glm53-flash-dflash2.json) pins
`Anbeeld/GLM-5.3-Flash-DFlash2-GGUF` revision
`f3569acb7f9cee95e66d24442d75536eb00ab842`, its 697,017,248-byte Q4_K_M file,
and SHA-256. Its [CC BY-NC-ND 4.0 license](https://huggingface.co/Anbeeld/GLM-5.3-Flash-DFlash2-GGUF#license)
requires noncommercial use; the VM205 operator confirmed personal noncommercial
use. Select the ordinary-decode profile below if this drafter is unsuitable.

VM205 defaults match the existing recipes: NetBird-only `100.0.0.159:8080`, no
API key, NVIDIA driver >= 580, Docker, and NVIDIA Container Toolkit. Never expose
this keyless API publicly. Elsewhere override `MAYA_BIND_ADDRESS` (for example
`127.0.0.1`), `MAYA_PORT`, and `MAYA_DATA_DIR`; authentication uses `MAYA_API_KEY`.
Compose overrides can be supplied in the shell or an untracked
`docker/maya/.env`. Optional API credentials are persisted during setup.

Run from the repository root. Build and pre-download while the old service is
still running; the download command does not allocate GPU memory:

```bash
docker compose -f docker/maya/compose.yaml build maya
docker compose -f docker/maya/compose.yaml run --rm --no-deps maya check
docker compose -f docker/maya/compose.yaml run --rm --no-deps maya download
```

`download` uses the existing manifest downloader: resumable `.part` files become
final filenames only after size and SHA-256 verification. The first normal
start can also download the model, but pre-downloading avoids stopping Qwen for
the transfer. Upstream setup, pack generation and model loading finish before
the API is ready. The engine is already compiled in the image.

Switch exclusively from the current UD-IQ4_XS Strata recipe:

```bash
docker compose -f docker/strata/compose.iq4xs.yaml stop strata
docker compose -f docker/maya/compose.yaml up -d maya
docker compose -f docker/maya/compose.yaml logs -f maya
# In another shell:
MAYA_BASE_URL=http://100.0.0.159:8080 bash scripts/smoke-maya.sh
```

The smoke checks ready `status=ok`, discovers the model ID (`glm-5.3-flash`),
generates text, and validates an OpenAI-compatible tool call and its arguments.
Export `MAYA_API_KEY` into the smoke shell if enabled. Clients use
`http://100.0.0.159:8080/v1` for OpenAI-compatible requests, or
`http://100.0.0.159:8080/v1/messages` for Anthropic-compatible requests.

To return to the existing Qwen service without deleting either model:

```bash
docker compose -f docker/maya/compose.yaml stop maya
docker compose -f docker/strata/compose.iq4xs.yaml up -d strata
```

`MAYA_DATA_DIR` defaults to `/opt/models/maya`, separate from Strata's data:
`models/Maya-M-Derisked/` holds target weights, pack and expert usage;
`models/GLM-5.3-Flash-DFlash2/` holds the optional drafter;
`config/maya-maya-m-derisked.json` and sibling shared settings hold runtime state;
`logs/` holds engine output. `home/mtp/` and `home/dflash2/` hold separate upstream
settings/calibration: upstream's hardware key does not distinguish draft modes.
Maya starts this exact config, not the most recently modified model. Normal
restarts retain dashboard context/settings and calibration, without setup or
weight downloads. The dashboard context control reloads the engine and persists
the new context; requests are unavailable while it reloads.

After changing the profile's draft/context/GPU/parallel settings or API key,
explicitly prepare the new config while Maya is stopped. Setup snapshots the
previous config/shared settings under `config/backups/`:

```bash
docker compose -f docker/maya/compose.yaml stop maya
docker compose -f docker/maya/compose.yaml run --rm --no-deps \
  -e REINSTALL=1 maya prepare
docker compose -f docker/maya/compose.yaml up -d maya
```

For ordinary decode, export this before **all** commands in that sequence:

```bash
export MAYA_PROFILE=../../configs/maya-glm53-flash-m-derisked-4090.env
```

Unset `MAYA_PROFILE` and repeat the sequence to return to the default DFlash2
profile. `prepare` verifies pinned weights and performs setup without starting
the API. To calibrate an already prepared profile, stop the server and run:

```bash
docker compose -f docker/maya/compose.yaml stop maya
docker compose -f docker/maya/compose.yaml run --rm --no-deps maya calibrate
docker compose -f docker/maya/compose.yaml up -d maya
```

Calibration requires an idle GPU, saves measured settings to the runtime config
and the selected draft's upstream calibration store, and fails if measurements
fail. Do not run Strata, ComfyUI, or another GPU consumer during calibration.
Maya sizes its pinned RAM tier automatically. Source-update checks are disabled:
update the pinned recipe and rebuild instead of updating container code from
the dashboard. Compose uses `restart: unless-stopped` and a 120-second graceful
shutdown timeout; an explicit `stop` intentionally disables automatic restart.

### VM205 verification

Recorded at remote clock `2026-10-13`: Threadripper 7970X (32 VM CPUs, AVX-512),
215.9 GiB RAM, RTX 4090, driver 595.84. Image build, Compose validation, hardware
check, and pinned target/drafter hashes passed. No expert trimming was enabled.

At 32768 context, CPU calibration retained the automatically selected 21
threads: 16, 14 and 10 were slower. Ordinary decode selected PCIe share `0.10`;
DFlash2 selected `0.00`. The standard uncalibrated DFlash2 settings were slower
than ordinary decode. Increasing draft length/lowering its confidence threshold
did not improve the two generation probes, so upstream draft defaults are kept.

Each generation probe below uses temperature 0, thinking disabled, uncached
input, and a 512-token output cap. These are single throughput probes per cell,
not semantic grading of the truncated explanations or a general speed guarantee:

| Configuration | Japanese explanation, tok/s | Code explanation, tok/s |
| --- | ---: | ---: |
| Calibrated ordinary decode, 32K | 39.7 | 35.5 |
| Uncalibrated DFlash2, 32K | 35.8 | 31.0 |
| Calibrated DFlash2, 32K | 42.4 | 41.1 |
| Calibrated DFlash2, 128K | 40.3 | 38.8 |
| Calibrated DFlash2, 256K, selected | 39.2 | 39.0 |
| Calibrated DFlash2, 512K | 37.8 | 36.4 |

`scripts/bench-maya.py` checks Japanese arithmetic/filtering, executable
semantics of two restricted Python functions, and synthetic-document fact
retrieval. Ordinary decode, uncalibrated DFlash2, calibrated DFlash2, and the
final recreated/recovered service each passed all 10 short/8K checks. DFlash2
greedy text was not byte-identical to ordinary decode in the two explanation
probes; the checks above are not proof of general capability preservation.

Long-document retrieval places distinct facts at the beginning, middle and end.
Each size below passed twice with zero cached prompt tokens. All use FP16 latent
KV except the explicitly marked 1M INT8 run. Token counts include the rendered
chat template and were checked through Maya's `/api/tokens`:

| Configured context | Actual prompt tokens | Retrieval passes | Median first token, s | Median uncached prefill, tok/s |
| --- | ---: | ---: | ---: | ---: |
| 65536 | 65015–65016 | 2/2 | 28.44 | 2297.2 |
| 131072 | 130552 | 2/2 | 59.43 | 2205.4 |
| 262144 | 261624 | 2/2 | 133.00 | 1973.5 |
| 524288 | 523767 | 2/2 | 341.64 | 1536.8 |
| 1048576 (INT8) | 1048055–1048056 | 2/2 | 1468.68 | 714.2 |

This proves near-capacity input and these fact-retrieval cases, not arbitrary
long-context comprehension. The 1M FP16 attempt failed before readiness:
`not enough VRAM for the expert pool (5 slots per layer)`. Maya automatically
reloaded the preceding 512K context. Thus 512K is the largest tested FP16 size,
not an exact memory ceiling; intermediate sizes above it were not tested.
INT8 latent KV allowed the full 1M input, but changes numerical precision and
has not received broad quality evaluation. Its uncached first read is very slow;
it is not the default. Expert trimming remains disabled.

Engine logs showed all 12096 experts warmed and zero disk reads/token in the
measured requests; no forced RAM-residency override was needed. Raw prompts,
responses, timing traces and configuration snapshots remain private outside Git:
`/opt/models/maya/experiments/maya-tuning-20261013/` for initial calibration,
`/opt/models/maya/experiments/context-expansion-20261013/` for the larger contexts.

To rerun short/8K checks against the active service:

```bash
MAYA_BASE_URL=http://100.0.0.159:8080 python3 scripts/bench-maya.py \
  --label local-check --seed 41 --repeat 2 \
  --output /opt/models/maya/experiments/local-check.json
```

For near-capacity retrieval, add `--scenarios retrieval --retrieval-sizes 256k
--context-size 256k` with the default server. Use `512k` for both flags after
changing the dashboard context to 524288. For 1M, use integer `1048576` for both
flags and the explicit INT8 profile below. Use fresh seeds to avoid confusing
conversation-cache hits with prefill performance.

The optional `configs/maya-glm53-flash-m-derisked-4090-1m-int8.env` reproduces
the tested 1M/INT8 environment; do not run it alongside the default service:

```bash
export MAYA_PROFILE=../../configs/maya-glm53-flash-m-derisked-4090-1m-int8.env
docker compose -f docker/maya/compose.yaml stop maya
docker compose -f docker/maya/compose.yaml run --rm --no-deps \
  -e REINSTALL=1 maya prepare
docker compose -f docker/maya/compose.yaml up -d maya
```

To return to default 256K/FP16, unset `MAYA_PROFILE` and repeat stop/prepare/up.
This explicit preparation resets the persisted context; changing only the
environment does not overwrite dashboard settings on an ordinary restart.

The earlier 128K service passed OpenAI text/tool calling and Anthropic text plus
a tool-use/tool-result round trip. Killing its Maya main process with SIGKILL
increased Docker's restart count from 0 to 1 and recovered a healthy 128K API
in 78.6 seconds, without setup or download. After the larger-context experiments,
the temporary INT8 container was stopped/removed and explicit preparation
restored FP16 at 256K. A normal restart retained 256K without setup/download;
all 10 Japanese/code/8K checks, OpenAI text/tool calls, and Anthropic
text/tool-use/tool-result checks passed again.
Docker and NetBird host services are enabled/active. A whole-VM reboot was not
exercised; the NetBird address must exist before Docker publishes the bound port,
and host boot ordering was not changed.

Final state: `maya-maya-1` healthy at `100.0.0.159:8080`, DFlash2 enabled, context
262144, FP16 latent KV, PCIe share `0.00`, parallel 1, default reasoning `high`.
Clients may set `reasoning_effort: "none"` for fast non-thinking replies.
Container RAM was 98.88 GiB, GPU usage 23954 MiB, available host RAM about
112 GiB, and filesystem free space about 42 GiB. Strata remains stopped with
restart disabled; original
ComfyUI and Qwen/GLM model data are retained. Capacity was sufficient without
deleting ComfyUI. Check space before adding models or retaining more slots.

## Retained runtime: Strata / Qwen3.8-Flash-Next / RTX 4090

`docker/strata/` builds the official Strata engine (MIT) at pinned commits and serves Qwen3.8-Flash-Next on the RTX 4090. These recipes are retained for rollback and must not run alongside Maya. Expert weights live in system RAM, with the active working set on the GPU. The retained IQ3_S recipe uses 262144 context; its RTX 4090 performance remains unmeasured (see [`notes/strata-qwen38-flash-next-4090.md`](notes/strata-qwen38-flash-next-4090.md)).

On VM205 (RTX 4090, NVIDIA driver >= 580, Docker, NVIDIA Container Toolkit), no `.env` is needed: Compose defaults to NetBird-only `100.0.0.159:8080`, host data directory `/opt/models`, and no API key. Do not expose this keyless API outside NetBird or run another inference engine on the same GPU.

On another host, override `STRATA_BIND_ADDRESS` (for example `127.0.0.1`), `STRATA_PORT`, and `STRATA_DATA_DIR` through environment variables or an optional untracked `.env` based on `.env.example`. Optional `STRATA_API_KEY` must be set before first setup; never commit secrets.

```bash
docker compose -f docker/strata/compose.yaml up --build -d
```

Follow the first-start model setup/download:

```bash
docker compose -f docker/strata/compose.yaml logs -f strata
```

The default profile is `configs/strata-qwen38-flash-next-4090.env` (`IQ3_S`, 262144-token native context, vision enabled, GPU 0). Model data and per-model setup state are stored outside Git in `/opt/models` by default. The optional `configs/strata-qwen38-flash-next-4090-iq2xs.env` profile is a smaller-memory alternative, not a second service.

The annotated tag `canonical-strata-iq3s-262k` freezes the pre-change IQ3_S/262144 recipe at Strata pin `1678de33`; `docker/strata/compose.yaml` retains that pin. The new `configs/strata-qwen38-flash-next-4090-ud-iq4xs.env` and `docker/strata/compose.iq4xs.yaml` select UD-IQ4_XS/262144 with Strata v0.1.39 (`a1641e9f`) in a separate image and a 60 GiB resident expert budget. Both use the same NetBird port 8080 and must be switched exclusively; see [switching instructions](docker/strata/README.md#exclusive-iq3_s--ud-iq4_xs-switching).

Run the API smoke test from the host. Set/export `STRATA_API_KEY` in the shell if API authentication is enabled:

```bash
STRATA_BASE_URL=http://100.0.0.159:8080 bash scripts/smoke-strata.sh
```

The smoke test checks health, model/status endpoints, a text completion, and an OpenAI-compatible tool call. The IQ3_S API model id is `qwen3.8-flash-next`; for the Unsloth profile also set `STRATA_MODEL_ID=qwen3.8-flash-next-unsloth`. Other NetBird peers connect to `http://100.0.0.159:8080`; no API key is required by default.

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
