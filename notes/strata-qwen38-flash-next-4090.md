# Strata on VM205 (RTX 4090) — run note

Status: **setup complete, GPU run pending** (2026-10-02). The recipe is
statically prepared (Dockerfile, compose, profiles, smoke script); the image
build, the ~70 GB model download, and the first API smoke have not been run
on VM205. Until then, treat everything below the line as proposed, not
measured.

## Plan

- Machine: VM205 (Proxmox, RTX 4090 24 GB sm_89, 224 GiB RAM, CPU pinned
  to cores 0-31)
- Engine: Strata image built from `Niko1221/Strata` @
  `1678de333d0e0711bc414ad992b640e1a37dd814` (build compiles the engine for
  `CUDA_ARCHITECTURES=89`)
- Profiles: `configs/strata-qwen38-flash-next-4090.env` (IQ3_S, 131072
  context, vision off) and `...-iq2xs.env` (IQ2_XS, same context)
- Port: `127.0.0.1:8090` (NInfer stays on 8080; the two cannot share the
  GPU, so stop the other engine first)
- A/B baseline: the llama.cpp `llama-qwen.service` Flash-Next sub profile
  (UD-Q4_K_XL, `--fit on --fit-target 256 -c 131072`, 25-30 t/s,
  see the vault page `qwen38-flash-next-local-inference`)

## Measured results

| Date | Profile | Model load | Prefill (t/s) | Decode (t/s) | VRAM / RAM | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| —   | —     | —         | —             | —            | —          | not yet run |

## Reference (other hardware, not VM205)

- RTX 5070 12 GB + 64 GB RAM (Strata README, author-measured): Q2_0 93 t/s,
  IQ2_XS 79, IQ3_XXS 62, IQ3_S 53 (short chat); 128K-context decode
  46-74 t/s; 32K-prompt reads 1.6-2.2k t/s
- Authors' estimate (not a measurement): RTX 3090 24 GB ~100-140 t/s
- VM205 224 GiB RAM runs every Strata size with experts in RAM
  (`LOW_RAM=auto` stays off)

## Procedure for the first run

```bash
# stop competing engines on VM205 (exclusivity, same rule as ComfyUI)
sudo systemctl stop llama-27b llama-qwen
docker stop ninfer-1 2>/dev/null || true

docker compose -f docker/strata/compose.yaml up --build
# first start: ~70 GB download + engine start; `docker compose ps` flips to
# healthy when the model is loaded
STRATA_BASE_URL=http://127.0.0.1:8090 bash scripts/smoke-strata.sh
```

Then record the load time, a prefill at ~32K and a decode at a realistic
prompt, plus `docker stats` and `nvidia-smi` numbers in the table above, and
repeat the identical measurement on the llama.cpp sub profile for the A/B.
