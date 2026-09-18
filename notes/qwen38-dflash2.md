# Qwen3.8-27B + DFlash2

Status: **experimental; engine integration and GPU run are not yet verified here**.

## Inputs

- Target artifact: the existing NInfer V2 `qwen3_8_27b-v2.ninfer`.
- Drafter: `z-lab/Qwen3.8-27B-DFlash2`, revision
  `ac04198556d7e8867853cbc356807b969f311b05`.
- The manifest pins `config.json` (1,239 bytes) and `model.safetensors`
  (3,848,817,896 bytes) by SHA-256.
- The drafter is not a standalone language model. It is appended to the target
  artifact by `tools/artifact/graft_dflash2_w8.py`.

## Reproduce the artifact

The source target artifact must already be present in `MODEL_DIR`.
The downloader uses a separate `dflash2-source/` directory so the drafter's
`config.json` and `model.safetensors` cannot collide with other model files.

```bash
export MODEL_DIR=/path/to/ninfer-models
bash scripts/download-qwen38-dflash2.sh
bash scripts/graft-qwen38-dflash2.sh
```

The graft writes `qwen3_8_27b-v2-dflash2.ninfer` and a `.graft.json` report.
The source artifact is opened read-only. `DFlash2_DEVICE=cpu` is the default;
set it only when the conversion environment has a supported accelerator.
The graft preserves the source artifact identity (`qwen3.8-27b/groupwise-int`
or `nvfp4full`) rather than rewriting it.

The graft helper imports the vendored conversion closure under `tools/` and
therefore needs CPU PyTorch and `safetensors` in the Python environment. This
checkout only performs static Python checks; the full graft needs the 18 GB
source artifact and 3.85 GB drafter weights.

## Serve

Build the NInfer image, then select the DFlash2 env file in
`docker/ninfer/compose.yaml` (or copy its values into a local env file):

```bash
NINFER_PROFILE=../../configs/ninfer-v2-qwen38-4090-262k-e8-dflash2.env \
  docker compose -f docker/ninfer/compose.yaml up --build
```

The current compose file still points at the baseline MTP env file by default;
this is intentional until the DFlash2 engine fork passes its independent build
and GPU smoke checks. Do not report throughput or acceptance length from this
recipe until a real RTX 4090 run has produced logs.

## Build on VM205 (RTX 4090)

The DFlash2 engine source lives in the P4sTela fork (not upstream sergiuszm):

- Repo: `https://github.com/P4sTela/ninfer-4090.git`
- Branch: `feat/dflash2-qwen38-27b`
- Build commit: `be9e76683a2bb6ba870690bf4cc4d95fe91a97f3` on `feat/dflash2-qwen38-27b` (salvage of the
  pi `dflash2-27b-finish` port + `sampling_device.cuh` synced to the upstream
  tile-topk sampler; static-audited, CUDA-verified pending).
- Superseded commit `612d7aef` failed its first VM205 build
NINFER_COMMIT must be a full 40-char SHA: the Dockerfile fetches it with `git fetch --depth 1`, which cannot resolve short SHA prefixes (or non-advertised commits) on GitHub. Branch names also fail the trailing rev-parse test, so always pass the full SHA of the branch tip.: the port pulled
  upstream `speculative_round.cuh`/`sampling.cuh` but left `sampling_device.cuh`
  at the sergiuszm-base version, so the 8 tile-topk primitives were undefined.
  A follow-up build exposed two more gaps, both fixed in the build commit now
  pinned below: the dflash2 small-T swiglu launcher lacked its header
  declaration, and the r64_c96_k128 route exceeded the sm89 48 KiB SMEM cap
  (it was tuned for sm120a); cols 65-96 now use r64_c80_k128.

Build the DFlash2-capable image:

```bash
NINFER_REPO=https://github.com/P4sTela/ninfer-4090.git \
NINFER_COMMIT=be9e76683a2bb6ba870690bf4cc4d95fe91a97f3 \
NINFER_IMAGE=ninfer-4090:dflash2 \
NINFER_PROFILE=../../configs/ninfer-v2-qwen38-4090-262k-e8-dflash2.env \
  docker compose -f docker/ninfer/compose.yaml up --build
```

MTP baseline (unchanged defaults):

```bash
docker compose -f docker/ninfer/compose.yaml up --build
```

### A/B acceptance plan (post build)

1. `--spec mtp --draft-tokens 3` (LM_HEAD_DRAFT=true): baseline 148.6 t/s decode,
   accept ~81% (262K E8, first tested run).
2. `--spec dflash2 --draft-tokens 7`: measure decode t/s, prefill t/s,
   acceptance length/rate with a 27K-token prompt (code + prose mix).
3. VRAM: watch the headroom. Graft adds ~1.1-2.2 GiB; if 262K context OOMs,
   fall back to MAX_CONTEXT=200000 or KV_DTYPE=rk2v4-e8 before judging the
   drafter.
4. Open question: GDN state slot save/restore is not DFlash-aware (docs);
   verify host-state-slot behaviour before enabling host caching on the
   dflash2 profile.

## Upstream reference

The model card describes DFlash2's published H200 measurements and the SGLang/
vLLM integration. Those numbers are upstream measurements, not RTX 4090 results
for this workbench.
