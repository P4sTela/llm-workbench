# Configurations

Reusable runtime profiles go here. Keep machine-specific values out of committed files when possible; use `.env` for local paths, bind addresses, and ports.

Profiles should describe tested combinations of model, engine, hardware, context length, KV type, and speculative decoding settings.

## Qwen3.8-Flash-Next / RTX 4090

- `strata-qwen38-flash-next-4090.env`: retained IQ3_S/262144 recipe, vision enabled, int8 KV, GPU 0; use `docker/strata/compose.yaml` (Strata pin `1678de33`). The pre-change recipe is frozen at tag `canonical-strata-iq3s-262k`.
- `strata-qwen38-flash-next-4090-ud-iq4xs.env`: new Unsloth UD-IQ4_XS/262144, vision enabled, int8 KV, GPU 0, 60 GiB resident expert budget; use only `docker/strata/compose.iq4xs.yaml` (v0.1.45 pin `477ac13f`). GPU validation is pending.
- Both use VM205's NetBird-only `100.0.0.159:8080`, `/opt/models`, and no API key by default, without `.env`. Override these non-secret host values elsewhere. [Stop before switching](../docker/strata/README.md#exclusive-iq3_s--ud-iq4_xs-switching).

## GLM-5.3-Flash / RTX 4090

- `maya-glm53-flash-m-derisked-4090-dflash2.env`: default Project Maya v1.1.0 (`77697c37`), Maya-M-Derisked, 262144 context, FP16 latent KV, GPU 0, parallel 1, text only, DFlash2. The drafter requires noncommercial use under CC BY-NC-ND 4.0. PCIe share `0.00` is measured on VM205; recalibrate on other CPUs.
- `maya-glm53-flash-m-derisked-4090.env`: retained 32768-context ordinary-decode comparison. `DRAFT=mtp` does not load MTP on a single GPU. Changing the installed draft requires explicit `REINSTALL=1` preparation.
- `maya-glm53-flash-m-derisked-4090-1m-int8.env`: explicit non-default 1048576-context alternative with INT8 latent KV. Two uncached near-capacity fact-retrieval requests passed; initial reads took about 24–25 minutes. Cache compression changes numerical precision; broad quality preservation is unverified. Explicitly prepare when switching and return to the default profile afterwards.
- All use `docker/maya/compose.yaml`; select alternatives through `MAYA_PROFILE`. Pinned target/drafter manifests enforce revisions, sizes and SHA-256. Model data and settings live in `/opt/models/maya`; draft modes have separate calibration homes. NetBird-only `100.0.0.159:8080`, no API key by default; never run both engines on the RTX 4090. [Build, calibrate, switch and roll back](../README.md#maya--glm-53-flash-maya-m-derisked--rtx-4090).
- Verified on VM205: Japanese/code/8K checks; FP16 near-capacity retrieval at 64K, 128K, 256K and 512K; INT8 retrieval at 1M; OpenAI text/tool calls; Anthropic text/tool-result round trip; and automatic recovery from main-process termination. FP16 at 1M failed for insufficient expert-pool VRAM and automatically fell back to 512K. The final 256K/FP16 service retained its settings across restart and passed the short checks again. Full-VM reboot was not exercised. The Derisked edit remains experimental; refusal reduction and capability preservation are not guarantees.

## Qwen3.8-27B / RTX 4090

- `ninfer-v2-qwen38-4090-245760-e8-dflash2.env` is the verified VM205 canonical
  DFlash2 profile: 245760-token context and KV capacity, 512-token prefill chunks,
  E8 KV, and seven draft tokens.
- `ninfer-v2-qwen38-4090-245760-e8-mtp3.env` is the matching MTP3 comparison
  profile. It uses the base artifact and `LM_HEAD_DRAFT=true`; GPU validation is
  pending.
- The existing `262k` profiles are retained as historical unsupported/
  failed-capacity RTX 4090 experiments and are not the default runtime.
