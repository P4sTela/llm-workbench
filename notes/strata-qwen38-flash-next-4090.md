# Strata on VM205 (RTX 4090) — run note

Status: **canonical repository configuration prepared; VM deployment and GPU run pending** (2026-10-02). The Dockerfile, Compose service, main profile, and API smoke test are in place. The image build, model download, and first API smoke test have not been run on VM205. The service is not yet active as the machine's main inference runtime; all runtime claims below remain unmeasured on VM205.

## Main runtime configuration

- Machine: VM205 (Proxmox, RTX 4090 24 GB sm_89, 224 GiB RAM, CPU pinned to cores 0-31)
- Engine: Strata image built from `Niko1221/Strata` @ `1678de333d0e0711bc414ad992b640e1a37dd814` (`CUDA_ARCHITECTURES=89`)
- Main profile: `configs/strata-qwen38-flash-next-4090.env` (`IQ3_S`, 131072 context, vision enabled, GPU 0)
- Host endpoint: `100.0.0.159:8080` over NetBird; the generic Compose default stays on loopback. Configure `STRATA_API_KEY` before first setup when exposing over the VPN.
- Persistent model/setup data: `STRATA_DATA_DIR` (default `models/strata-data`, outside Git)
- GPU exclusivity: stop the currently active NInfer/llama.cpp/ComfyUI workload before starting Strata. No VM service has been stopped or started as part of preparing these files.

## Measured results

| Date | Profile | Model load | Prefill (t/s) | Decode (t/s) | VRAM / RAM | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| —   | —     | —         | —             | —            | —          | not yet run |

## Reference (other hardware, not VM205)

- RTX 5070 12 GB + 64 GB RAM (Strata README, author-measured): Q2_0 93 t/s, IQ2_XS 79, IQ3_XXS 62, IQ3_S 53 (short chat); 128K-context decode 46-74 t/s; 32K-prompt reads 1.6-2.2k t/s
- Authors' estimate (not a measurement): RTX 3090 24 GB ~100-140 t/s
- VM205 has 224 GiB RAM; actual model residency, context behavior, and speed remain to be measured.

## First-run checklist

1. Confirm the RTX 4090 is not in use by NInfer, llama.cpp, ComfyUI, or another workload.
2. On VM205, set `.env` to bind `STRATA_BIND_ADDRESS=100.0.0.159`, `STRATA_PORT=8080`, and a private `STRATA_API_KEY`.
3. Start `docker compose -f docker/strata/compose.yaml up --build -d`; allow for the first model download and setup.
4. Verify container health and run `scripts/smoke-strata.sh` against `http://100.0.0.159:8080` with the API key available in the shell.
5. Record load time, a prefill at about 32K, decode speed at a realistic prompt, `docker stats`, and `nvidia-smi` measurements above.

## References

- Upstream Strata source is pinned to the commit above. The API implements OpenAI-compatible tool calls in the pinned `serve/server.py` and `serve/frontend.py`; the actual model's tool-call reliability on VM205 remains to be tested.
- Previous NInfer and llama.cpp runs remain historical configurations; do not run them concurrently with Strata on the RTX 4090.
