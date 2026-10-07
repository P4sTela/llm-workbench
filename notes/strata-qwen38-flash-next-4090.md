# Strata on VM205 (RTX 4090) — run note

Status: **IQ3_S/262144 is the current VM205 deployment (user-confirmed 2026-10-07)**. The earlier 131072 deployment was API-smoke-tested on 2026-10-02. UD-IQ4_XS is a new pinned configuration; its GPU build, inference, expert residency, and RTX 4090 performance are not verified by the Mac-side checks.

## Main runtime configuration

- Machine: VM205 (Proxmox, RTX 4090 24 GB sm_89, 224 GiB RAM, CPU pinned to cores 0-31)
- Engine: Strata image built from `Niko1221/Strata` @ `1678de333d0e0711bc414ad992b640e1a37dd814` (`CUDA_ARCHITECTURES=89`)
- Main profile: `configs/strata-qwen38-flash-next-4090.env` (`IQ3_S`, 262144 native context, vision enabled, GPU 0)
- Host endpoint: `100.0.0.159:8080` over NetBird; now the Compose default, with no API key. Do not expose the keyless API outside NetBird.
- Persistent model/setup data: `STRATA_DATA_DIR` (default `/opt/models`, outside Git); no `.env` is needed on VM205.
- GPU exclusivity: Only one LLM/GPU workload can own this RTX 4090. Ensure NInfer/llama.cpp/ComfyUI is stopped before starting or reconfiguring Strata; this local profile edit does not change VM205 services.

The annotated tag `canonical-strata-iq3s-262k` freezes the pre-change IQ3_S/262144 recipe at Strata pin `1678de33`; `docker/strata/compose.yaml` keeps that pin. The new UD-IQ4_XS profile is paired only with `docker/strata/compose.iq4xs.yaml`, Strata v0.1.39 (`a1641e9f`), and image `strata-qwen38:4090-iq4xs`. It uses Unsloth, native 262144 context, vision, default int8 KV, GPU 0, and a 60 GiB resident budget covering the ~59.5 GB expert arena on VM205's 224 GiB RAM. Both configurations share NetBird port 8080 and `/opt/models` with separate per-model setup configs: [stop the active service before switching](../docker/strata/README.md#exclusive-iq3_s--ud-iq4_xs-switching). First UD-IQ4_XS startup downloads ~94 GB in three shards; `/health` is unavailable until setup and model loading finish.

## Measured results

| Date | Profile | Model load | Prefill (t/s) | Decode (t/s) | VRAM / RAM | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| —   | —     | —         | —             | —            | —          | not yet run |

## Reference (other hardware, not VM205)

- RTX 5070 12 GB + 64 GB RAM (Strata README, author-measured): Q2_0 93 t/s, IQ2_XS 79, IQ3_XXS 62, IQ3_S 53 (short chat); 128K-context decode 46-74 t/s; 32K-prompt reads 1.6-2.2k t/s
- Authors' estimate (not a measurement): RTX 3090 24 GB ~100-140 t/s
- VM205 has 224 GiB RAM. The earlier 131072 context was API-smoke-tested, and the user now confirms IQ3_S at 262144; actual RAM use and performance remain to be measured.

## First-run checklist

1. Confirm the RTX 4090 is not in use by NInfer, llama.cpp, ComfyUI, or another workload.
2. On VM205, use the built-in NetBird bind, port 8080, `/opt/models`, and empty API key; no `.env` is required.
3. Start `docker compose -f docker/strata/compose.yaml up --build -d`; allow for the first model download and setup.
4. Verify container health and run `scripts/smoke-strata.sh` against `http://100.0.0.159:8080` (set `STRATA_MODEL_ID=qwen3.8-flash-next-unsloth` for UD-IQ4_XS; export a key only if explicitly enabled).
5. Record load time, a prefill at about 32K, decode speed at a realistic prompt, `docker stats`, and `nvidia-smi` measurements above.

## References

- Upstream Strata source is pinned to the commit above. The API implements OpenAI-compatible tool calls in the pinned `serve/server.py` and `serve/frontend.py`; the actual model's tool-call reliability on VM205 remains to be tested.
- Previous NInfer and llama.cpp runs remain historical configurations; do not run them concurrently with Strata on the RTX 4090.
