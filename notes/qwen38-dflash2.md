# Qwen3.8-27B + DFlash2

Status: **verified on VM205 with an NVIDIA RTX 4090**. This note records the
canonical 245760-token DFlash2 runtime. The matching 245760-token MTP3 profile is
reserved for an A/B comparison; GPU validation is pending.

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

The measured VM205 artifact is `20437336576` bytes with SHA-256
`0634abb07024221de141456cf04a42ab74b18bc38e1b781c6eb2e062a467eec3`.
It contains `1,190` objects (`1,184` tensors + `6` resources), including `66`
DFlash2 companion objects. The generated absolute-path report
`models/qwen3_8_27b-v2-dflash2.ninfer.graft.json` is ignored and is not a commit
target; portable artifact metadata is recorded here instead.

The graft helper imports the vendored conversion closure under `tools/` and
therefore needs CPU PyTorch and `safetensors` in the Python environment. Recreating
the artifact needs the 18 GB source artifact and 3.85 GB drafter weights.

## Canonical runtime

The runtime source is pinned to the P4sTela fork:

- Repo: `https://github.com/P4sTela/ninfer-4090.git`
- Branch: `validated/rtx4090-port-a889ce4`
- Tag: `vm205-dflash2-a889ce4`
- Commit: `a889ce4377d0f88093bb491d851d29eb1555e4f8`
- Image: `ninfer-4090:dflash2`
- Model: `qwen3_8_27b-v2-dflash2.ninfer`

The Dockerfile fetches the full 40-character commit with `git fetch --depth 1` and
checks the resulting `rev-parse` value. Compose defaults to
`configs/ninfer-v2-qwen38-4090-245760-e8-dflash2.env` and keeps the published port
loopback-only by default.

The verified profile reserves:

| Setting | Value |
| --- | --- |
| `MAX_CONTEXT` / `KV_CAPACITY` | `245760` |
| `PREFILL_CHUNK` | `512` |
| `KV_DTYPE` | `rk4v4-e8` |
| `SPEC` / `DRAFT_TOKENS` | `dflash2` / `7` |
| `LM_HEAD_DRAFT` / `PRESERVE_THINKING` | `false` / `true` |
| `DEFAULT_MAX_TOKENS` | `16384` |
| `HOST_KV_MIB` / `HOST_STATE_SLOTS` | `32768` / `16` |
| `MAX_CONCURRENCY` / `MAX_PENDING_REQUESTS` | `1` / `16` |
| `PENDING_TIMEOUT_MS` | `600000` |

Reproduce the serving setup with:

```bash
docker compose -f docker/ninfer/compose.yaml up --build
```

## MTP3 comparison and capacity boundary

`configs/ninfer-v2-qwen38-4090-245760-e8-mtp3.env` keeps the same 245760-token
context, KV capacity, prefill chunk, E8 KV type, and host/runtime reservations.
It switches to `qwen3_8_27b.ninfer`, `SPEC=mtp`, three draft tokens, and
`LM_HEAD_DRAFT=true`. GPU validation remains pending for this A/B profile.

The existing `262k` profile files are retained for historical reference. `262144`
is an unsupported/failed-capacity experiment for the RTX 4090 canonical runtime;
it is not the default and should not be used to describe the verified run.
Architecture documentation and model `max_position_embeddings` metadata are not
being changed by this runtime canonicalization.
