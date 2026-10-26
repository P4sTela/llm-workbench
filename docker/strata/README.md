# Strata (Qwen3.8-Flash-Next)

This is the workbench's Strata runtime for Qwen3.8-Flash-Next on one RTX 4090 (sm_89), not a side-by-side A/B service. It has two generations: the pinned 0.1.45 recipes built from this directory's Dockerfile, and the 0.2.2 recipes on the official image. Only one may hold the GPU, and [Maya / GLM-5.3-Flash](../../README.md#maya--glm-53-flash-maya-m-derisked--rtx-4090) owns the same card as an exclusive alternative. VM205 currently serves the 0.2.2 OrcaRouter Q4_K_M recipe; stop the active service before starting another one. The 0.1.45 build follows the official Strata engine (MIT, [`Niko1221/Strata`](https://github.com/Niko1221/Strata)) at a pinned commit. The Dockerfile follows the upstream build, replacing `COPY . .` with a pinned shallow fetch and removing GeForce-incompatible forward-compatibility libraries. A local entrypoint preserves upstream's per-model setup flow and forwards optional `RESIDENT_BUDGET_GIB` to `setup.py --resident-budget-gib` only during setup. The engine is compiled during image build; the first container start downloads the selected model and starts the OpenAI- and Anthropic-compatible API on container port 8080.

## Main setup

On VM205 with an RTX 4090, an NVIDIA driver >= 580, Docker, and the NVIDIA Container Toolkit, no `.env` is needed for the pinned 0.1.45 files. Both of them default to `100.0.0.159:8080` (VM205's NetBird address), `/opt/models` for host data, and an empty API key; the 0.2.2 files always require `STRATA_API_KEY`. Access control is NetBird membership: never publish or proxy this keyless API outside NetBird. These defaults contain no secrets. On another host, override `STRATA_BIND_ADDRESS` (for example `127.0.0.1`), `STRATA_PORT`, and `STRATA_DATA_DIR` through environment variables or an optional untracked `.env` copied from `.env.example`. Optional `STRATA_API_KEY` must be set before first setup because Strata persists it in the model's setup config.

Ensure no other inference service or GPU workload is using the RTX 4090, then start the canonical service:

```bash
docker compose -f docker/strata/compose.yaml up --build -d
```

The first start includes model download and setup. Follow startup with:

```bash
docker compose -f docker/strata/compose.yaml logs -f strata
```

The default profile is `configs/strata-qwen38-flash-next-4090.env`: `FAMILY=qwen`, `MODEL=IQ3_S`, 262144-token native context, vision enabled, default int8 KV, and GPU 0. `configs/strata-qwen38-flash-next-4090-iq2xs.env` remains an optional lower-memory alternative for this pinned service, selected with `STRATA_PROFILE=../../configs/strata-qwen38-flash-next-4090-iq2xs.env`.

The annotated tag `canonical-strata-iq3s-262k` freezes the pre-change IQ3_S/262144 configuration at Strata `1678de333d0e0711bc414ad992b640e1a37dd814`; the current `compose.yaml` retains that pin and image `strata-qwen38:4090`. The new `compose.iq4xs.yaml` uses Strata v0.1.45 at `477ac13cbe8e582c20484871ce459d20d82df09d`, image `strata-qwen38:4090-iq4xs`, and profile `configs/strata-qwen38-flash-next-4090-ud-iq4xs.env` (`FAMILY=unsloth`, `MODEL=UD-IQ4_XS`, 262144 context, vision enabled, default int8 KV, GPU 0, `RESIDENT_BUDGET_GIB=60`). The old pin does not support this model; use the separate image, not a profile override on the IQ3_S compose file.

For an already-installed model, profile edits do not change the persisted `/data/config/strata-<family-and-model>.json`. Rerun setup explicitly or, with both services stopped, run the selected entrypoint with `docker compose -f docker/strata/compose.iq4xs.yaml run --rm -e REINSTALL=1 --no-deps --service-ports strata` (foreground; stop it before starting `up -d`). This forwards the profile's resident budget and other setup choices and preserves the generated config. Neither Compose file forwards a host-shell `REINSTALL=1` prefix.

The IQ3_S API model id is `qwen3.8-flash-next`; UD-IQ4_XS uses `qwen3.8-flash-next-unsloth`. Run the smoke test at the actual NetBird listener; when authentication is enabled, export `STRATA_API_KEY` into the shell:

```bash
STRATA_BASE_URL=http://100.0.0.159:8080 bash scripts/smoke-strata.sh
```

The smoke test exercises health, model/status endpoints, a text completion, and OpenAI-compatible tool calling. For UD-IQ4_XS, also set `STRATA_MODEL_ID=qwen3.8-flash-next-unsloth`. Other NetBird peers use the same address; no key is required by default.

Without a key the server applies DNS-rebinding protection: IP addresses and `localhost` pass, other names get `403 Host ... is not allowed`. To reach it as `comfy-vm.netbird.selfhosted` (or any reverse-proxy name), set `STRATA_ALLOWED_HOSTS=comfy-vm.netbird.selfhosted` in the environment or `"allowed_hosts": ["comfy-vm.netbird.selfhosted"]` in `/data/config/strata-<model>.json` (`.example.com` covers its subdomains, `*` disables the check), then restart the container; `api_key` also disables it. Clients can keep using `http://100.0.0.159:8080` unchanged.

## Strata 0.2.2 recipes

`compose.022.yaml` and `compose.orca.yaml` run the official image `ghcr.io/niko1221/strata:0.2.2-cuda13` instead of building `Dockerfile`. Both use service `strata`, the same Compose project, GPU, host port 8080, and `/opt/models` as `/data`, so they replace the 0.1.45 recipes rather than extend them. 0.2.2 always serves with a key and would otherwise generate one, so both files require it before Compose starts:

```bash
export STRATA_API_KEY=...   # shell or untracked .env; never commit it
```

`compose.022.yaml` is the ordinary path: it loads `configs/strata-qwen38-flash-next-4090-ud-q4kxl-022.env` through its `env_file` and serves UD-Q4_K_XL at 524288 context with `PARALLEL=1`, `VISION=on`, `KV=int8`, and `STRATA_SET=resident-budget-gib=80 vram-reserve-mib=1024`.

```bash
docker compose -f docker/strata/compose.022.yaml up -d
docker compose -f docker/strata/compose.022.yaml logs -f strata
```

`compose.orca.yaml` serves the OrcaRouter Q4_K_M pack, which `strata launch` does not know, so the service runs `serve.server` directly against `/data/config/orca-q4_k_m.json`. That config, the pack, and the GGUF shards must already exist under `STRATA_DATA_DIR`; the file does not prepare them. The health endpoint reports the served model id, which is how the running recipe is identified.

```bash
docker compose -f docker/strata/compose.orca.yaml up -d
```

Verified on VM205 on 2026-10-26: `/health` returned `200` with `"model": "orcarouter-qwen3.8-flash-next-uncensored-q4_k_m"`, `"max_context": 524288`, `"api_key": true`, and `"images": true`. Other endpoints returned `401` without the key. With a key set, `STRATA_ALLOWED_HOSTS` is irrelevant because authentication already disables the DNS-rebinding check.

Both 0.2.2 files ignore the 0.1.x-only `LOW_RAM` and `RESIDENT_BUDGET_GIB` variables and keep their own setup state under `/data/config`, so switching back to a 0.1.45 recipe restores that recipe's persisted config.

## Exclusive switching between Strata recipes

Run commands from the repository root. The files are standalone alternatives, not mergeable overlays: all four use service `strata`, the same Compose project, the same GPU, and host port 8080. Always stop the active service first. Clear any `STRATA_COMMIT`, `STRATA_IMAGE`, or `STRATA_PROFILE` overrides when using the pinned defaults.

IQ3_S → UD-IQ4_XS:

```bash
docker compose -f docker/strata/compose.yaml stop strata
docker compose -f docker/strata/compose.iq4xs.yaml up -d --build strata
docker compose -f docker/strata/compose.iq4xs.yaml logs -f strata
```

The first UD-IQ4_XS start downloads approximately 94 GB of model weights (93.7 GB, three GGUF shards), plus any missing setup/vision/MTP assets. `/health` does not respond during download, preparation, or model loading; follow logs rather than treating this as a failed server. VM205's 224 GiB RAM can hold the full ~59.5 GB expert arena; the explicit 60 GiB resident budget is intended to eliminate SSD expert reads during inference, not initial loading or other disk activity. GPU inference and zero file-tier expert reads still require VM205 verification.

Setup may warn that 60 GiB exceeds its 55 GiB recommendation: the upstream recommendation converts the 59.5 GB arena to GiB and rounds down. It keeps the explicit 60 GiB choice; do not replace it with the rounded-down recommendation. The engine can clamp the budget to free RAM at startup, so verify expert residency on VM205 under its actual memory load.

UD-IQ4_XS → IQ3_S:

```bash
docker compose -f docker/strata/compose.iq4xs.yaml stop strata
docker compose -f docker/strata/compose.yaml up -d --build strata
```

Both mount `/opt/models` as `/data`. Upstream names their configs separately (`strata-iq3_s.json` and `strata-unsloth-ud-iq4_xs.json`), and the entrypoint selects only the chosen model's config. Switching to an already-installed model therefore reuses its own setup, without a reinstall or deletion of the other model.

0.1.45 → 0.2.2 (no `--build`; the official image is pulled):

```bash
docker compose -f docker/strata/compose.iq4xs.yaml stop strata
docker compose -f docker/strata/compose.022.yaml up -d strata
docker compose -f docker/strata/compose.022.yaml logs -f strata
```

0.2.2 → 0.1.45:

```bash
docker compose -f docker/strata/compose.022.yaml stop strata
docker compose -f docker/strata/compose.iq4xs.yaml up -d --build strata
```

0.2.2 migrates the old `/data/models`, `/data/packs`, and `/data/mtp` layout to `/data/Strata-data` on its first start, a rename inside the mount. The Orca recipe's own config is a separate file (`/data/config/orca-q4_k_m.json`) and is not generated by either Compose file; whether a 0.1.45 install is reused after the migration is not verified.

## Storage and GPU exclusivity

- `STRATA_DATA_DIR` defaults to `/opt/models` on VM205, outside the checkout; it contains downloaded models, prepared packs, MTP layers, and per-model setup configurations. The engine remains in its separate image.
- Strata needs substantial host RAM for experts. IQ3_S keeps `LOW_RAM=auto`; UD-IQ4_XS explicitly sets the 60 GiB resident budget on GPU 0. The alternative IQ2_XS profile targets lower-memory hosts.
- Only one LLM/GPU workload can own this RTX 4090 at a time. Stop the currently active NInfer/llama.cpp/ComfyUI workload before starting Strata; this repository change does not stop or reconfigure VM205 services.
- Published speeds from the upstream README are from different GPUs. The ~100–140 tokens/s RTX 3090 number is an author estimate, not a measurement. VM205 performance and first-run behavior remain unverified until the GPU run is performed; record results in [`notes/strata-qwen38-flash-next-4090.md`](../../notes/strata-qwen38-flash-next-4090.md).
