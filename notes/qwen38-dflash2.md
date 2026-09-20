# Qwen3.8-27B + DFlash2

Status: **experimental; the upstream engine integration and local VM205 GPU run are not yet verified here**.

The current VM205 grafted artifact is already present, but the image must be rebuilt
from the upstream source pin below before runtime testing.

## Inputs

- Target artifact: the existing NInfer V2 `qwen3_8_27b.ninfer`.
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

The upstream artifact manifest documents the complete artifact as
`20,437,336,576` bytes with `1,190` objects (`1,184` tensors + `6` resources),
including `66` DFlash2 companion objects, and SHA-256
`0634abb07024221de141456cf04a42ab74b18bc38e1b781c6eb2e062a467eec3`.
The VM205 graft output reports the same byte size, `1,190` objects, and `66`
grafted DFlash2 objects. Its VM file hash has not been independently read back
here, so this does not claim hash identity.

The graft helper imports the vendored conversion closure under `tools/` and
therefore needs CPU PyTorch and `safetensors` in the Python environment. This
checkout only performs static Python checks; the full graft needs the 18 GB
source artifact and 3.85 GB drafter weights.

## Serve

Build the NInfer image from the upstream source pin below, then select the
DFlash2 env file in `docker/ninfer/compose.yaml` (or copy its values into a
local env file):

```bash
NINFER_PROFILE=../../configs/ninfer-v2-qwen38-4090-262k-e8-dflash2.env \
  docker compose -f docker/ninfer/compose.yaml up --build
```

The current compose file still points at the baseline MTP env file by default;
this is intentional until the DFlash2 image built from the upstream tip passes
its independent build and GPU smoke checks. Do not report throughput or
acceptance length from this recipe until a real RTX 4090 run has produced logs.

## Build on VM205 (RTX 4090)

The runtime source pin is now the verified upstream `rtx4090-port` tip:

- Repo: `https://github.com/sergiuszm/ninfer-4090.git`
- Branch: `rtx4090-port`
- Build commit: `a889ce4377d0f88093bb491d851d29eb1555e4f8` on `rtx4090-port` (branch tip).
- Relative to the old common ancestor `1bd56c9a`, the current custom fork work is
  10 commits ahead due to custom changes, while upstream is 100 commits ahead. This is
  lineage context only; the GitHub ahead/behind banner alone is not evidence of
  a feature.
- Direct inspection of upstream tip `a889ce4377d0f88093bb491d851d29eb1555e4f8`
  shows Qwen3.8-27B DFlash2 support, including the `qwen3_8_27b` DFlash2
  converter/runtime files, 2048/4096 sliding-window support, and the `sm_89`
  DFlash2 W8 shared-memory fix.

`NINFER_COMMIT` must be a full 40-character SHA. The Dockerfile fetches it with
`git fetch --depth 1`, which cannot resolve short SHA prefixes (or non-advertised
commits) on GitHub. Branch names also fail the trailing `rev-parse` test, so
always pass the full SHA of the branch tip.

Build the DFlash2-capable image:

```bash
NINFER_REPO=https://github.com/sergiuszm/ninfer-4090.git \
NINFER_COMMIT=a889ce4377d0f88093bb491d851d29eb1555e4f8 \
NINFER_IMAGE=ninfer-4090:dflash2 \
NINFER_PROFILE=../../configs/ninfer-v2-qwen38-4090-262k-e8-dflash2.env \
  docker compose -f docker/ninfer/compose.yaml up --build
```

MTP baseline (unchanged defaults):

```bash
docker compose -f docker/ninfer/compose.yaml up --build
```

### A/B acceptance plan (post build)

The local VM205 GPU run remains unverified here. The baseline in step 1 is a
prior recorded comparison value, not a verified DFlash2 result.

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

The model card describes DFlash2's published RTX 5090 measurements and the
SGLang/vLLM integration. Those numbers are upstream measurements, not RTX 4090
evidence for this workbench; the local VM205 GPU run remains unverified.
