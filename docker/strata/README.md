# Strata (Qwen3.8-Flash-Next)

This is the workbench's canonical Strata runtime for Qwen3.8-Flash-Next on one RTX 4090 (sm_89), not a side-by-side A/B service. It builds the official Strata engine (MIT, [`Niko1221/Strata`](https://github.com/Niko1221/Strata)) at pinned commit `1678de333d0e0711bc414ad992b640e1a37dd814`. The Dockerfile follows the pinned upstream build, replacing `COPY . .` with a pinned shallow fetch and removing GeForce-incompatible forward-compatibility libraries. The engine is compiled during image build; the first container start downloads the model (about 70 GB) and starts the OpenAI- and Anthropic-compatible API on container port 8080.

## Main setup

On a Linux host with an RTX 4090, an NVIDIA driver >= 580, Docker, and the NVIDIA Container Toolkit, copy `.env.example` to `.env`. The defaults bind only to loopback on port 8080. On VM205, set `STRATA_BIND_ADDRESS=100.0.0.159` and `STRATA_PORT=8080` in `.env` to publish only on its NetBird address. Set a non-empty `STRATA_API_KEY` before the first setup when binding beyond loopback; the key is saved with Strata's setup configuration. Keep `.env` private and untracked.

Ensure no other inference service or GPU workload is using the RTX 4090, then start the canonical service:

```bash
docker compose -f docker/strata/compose.yaml up --build -d
```

The first start includes model download and setup. Follow startup with:

```bash
docker compose -f docker/strata/compose.yaml logs -f strata
```

The default profile is `configs/strata-qwen38-flash-next-4090.env`: `MODEL=IQ3_S`, 262144-token native context, vision enabled, and GPU 0. This is the single main profile. `configs/strata-qwen38-flash-next-4090-iq2xs.env` is an optional lower-memory alternative for the same service. Switch it with `STRATA_PROFILE=../../configs/strata-qwen38-flash-next-4090-iq2xs.env`; changing an already-installed model's settings requires `REINSTALL=1`.

The API identifies the model as `qwen3.8-flash-next`. Run the smoke test locally; when authentication is enabled, export `STRATA_API_KEY` into the shell before running it:

```bash
STRATA_BASE_URL=http://127.0.0.1:8080 bash scripts/smoke-strata.sh
```

The smoke test exercises health, model/status endpoints, a text completion, and OpenAI-compatible tool calling. From another NetBird peer, use `http://100.0.0.159:8080` and configure the API key in the client's secret/config mechanism.

## Storage and GPU exclusivity

- `STRATA_DATA_DIR` defaults to `models/strata-data` (outside tracked source and ignored by Git); it contains the downloaded model, prepared pack, MTP layer, and setup configuration. The engine remains in the image.
- Strata needs substantial host RAM for experts. VM205 has 224 GiB; `LOW_RAM=auto` lets setup choose whether the experts remain in RAM. The alternative IQ2_XS profile targets lower-memory hosts.
- Only one LLM/GPU workload can own this RTX 4090 at a time. Stop the currently active NInfer/llama.cpp/ComfyUI workload before starting Strata; this repository change does not stop or reconfigure VM205 services.
- Published speeds from the upstream README are from different GPUs. The ~100–140 tokens/s RTX 3090 number is an author estimate, not a measurement. VM205 performance and first-run behavior remain unverified until the GPU run is performed; record results in [`notes/strata-qwen38-flash-next-4090.md`](../../notes/strata-qwen38-flash-next-4090.md).
