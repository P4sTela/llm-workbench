# Strata (Qwen3.8-Flash-Next)

This recipe builds the official Strata engine (MIT,
[`Niko1221/Strata`](https://github.com/Niko1221/Strata)) at pinned commit
`1678de333d0e0711bc414ad992b640e1a37dd814` as a single-stage CUDA image and
serves Qwen3.8-Flash-Next on one RTX 4090 (sm_89). The build is the official
Dockerfile from the pinned tree with the `COPY . .` replaced by a pinned
shallow fetch, plus the GeForce forward-compat removal used by the NInfer
recipe. The engine is compiled during `docker build`; the first container
start only downloads the ~70 GB model into the `strata-data` volume and then
starts the OpenAI- and Anthropic-compatible server on port 8080 (published as
`127.0.0.1:8090` by default, so it can run beside the NInfer server on 8080).

## Clean-checkout workflow

On a Linux host with an RTX 4090, an NVIDIA driver >= 580, Docker and the
NVIDIA Container Toolkit:

```bash
docker compose -f docker/strata/compose.yaml up --build
```

The default profile is `configs/strata-qwen38-flash-next-4090.env`
(`MODEL=IQ3_S`, 131072 context, vision off, single card). The first start
downloads the model, so allow time; `docker compose ps` reports `healthy`
once the model is loaded. In another terminal:

```bash
STRATA_BASE_URL=http://127.0.0.1:8090 bash scripts/smoke-strata.sh
```

The API identifies the model as `qwen3.8-flash-next`.

## Profiles

- `configs/strata-qwen38-flash-next-4090.env` — quality profile: `IQ3_S`
  (the largest size; "matches the full model on the published tests"). Needs
  ~55 GB of combined RAM+VRAM, so it fits on VM205 (224 GiB RAM) with the
  experts fully in RAM.
- `configs/strata-qwen38-flash-next-4090-iq2xs.env` — speed profile: `IQ2_XS`
  (the README-recommended size for 64 GB hosts).

Switch profiles with `STRATA_PROFILE=...`. Switching to a model that is not
yet on the volume runs the setup pass (model download) for it; switching
between models already on the volume does not. To change a setting for an
already-set-up model, add `REINSTALL=1`.

## Host requirements and caveats

- Strata loads 32-62 GB into RAM. VM205 has 224 GiB, so `LOW_RAM=auto`
  keeps the experts in RAM (fastest mode). On smaller hosts set `LOW_RAM=on`
  or pick a smaller `MODEL`.
- The server refuses to start into a GPU another program already uses
  (it checks free VRAM). On VM205 stop the NInfer container and any
  `llama-server` unit first, or run Strata on the 27B slot only after the
  other engine is down. This is the same exclusivity rule as ComfyUI.
- The model download and the setup config live in the named `strata-data`
  volume; the engine is part of the image. Pinning a new `STRATA_COMMIT`
  requires a rebuild.
- The published speeds (README, RTX 5070 12 GB and RX 9070 XT 16 GB) are
  other hardware; the "100-140 tokens/s on an RTX 3090" figure is the
  authors' estimate, not a measurement. VM205 results belong in
  [`notes/strata-qwen38-flash-next-4090.md`](../../notes/strata-qwen38-flash-next-4090.md).
