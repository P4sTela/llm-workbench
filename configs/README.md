# Configurations

Reusable runtime profiles go here. Keep machine-specific values out of committed files when possible; use `.env` for local paths, bind addresses, and ports.

Profiles should describe tested combinations of model, engine, hardware, context length, KV type, and speculative decoding settings.

## Qwen3.8-Flash-Next / RTX 4090

- `strata-qwen38-flash-next-4090.env`: current VM205 IQ3_S/262144, vision enabled, int8 KV, GPU 0; use `docker/strata/compose.yaml` (Strata pin `1678de33`). The pre-change recipe is frozen at tag `canonical-strata-iq3s-262k`.
- `strata-qwen38-flash-next-4090-ud-iq4xs.env`: new Unsloth UD-IQ4_XS/262144, vision enabled, int8 KV, GPU 0, 60 GiB resident expert budget; use only `docker/strata/compose.iq4xs.yaml` (v0.1.39 pin `a1641e9f`). GPU validation is pending.
- Both use VM205's NetBird-only `100.0.0.159:8080`, `/opt/models`, and no API key by default, without `.env`. Override these non-secret host values elsewhere. [Stop before switching](../docker/strata/README.md#exclusive-iq3_s--ud-iq4_xs-switching).

## Qwen3.8-27B / RTX 4090

- `ninfer-v2-qwen38-4090-245760-e8-dflash2.env` is the verified VM205 canonical
  DFlash2 profile: 245760-token context and KV capacity, 512-token prefill chunks,
  E8 KV, and seven draft tokens.
- `ninfer-v2-qwen38-4090-245760-e8-mtp3.env` is the matching MTP3 comparison
  profile. It uses the base artifact and `LM_HEAD_DRAFT=true`; GPU validation is
  pending.
- The existing `262k` profiles are retained as historical unsupported/
  failed-capacity RTX 4090 experiments and are not the default runtime.
