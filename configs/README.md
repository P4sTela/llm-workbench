# Configurations

Reusable runtime profiles go here. Keep machine-specific values out of committed files when possible; use `.env` for local paths, bind addresses, and ports.

Profiles should describe tested combinations of model, engine, hardware, context length, KV type, and speculative decoding settings.

## Qwen3.8-27B / RTX 4090

- `ninfer-v2-qwen38-4090-245760-e8-dflash2.env` is the verified VM205 canonical
  DFlash2 profile: 245760-token context and KV capacity, 512-token prefill chunks,
  E8 KV, and seven draft tokens.
- `ninfer-v2-qwen38-4090-245760-e8-mtp3.env` is the matching MTP3 comparison
  profile. It uses the base artifact and `LM_HEAD_DRAFT=true`; GPU validation is
  pending.
- The existing `262k` profiles are retained as historical unsupported/
  failed-capacity RTX 4090 experiments and are not the default runtime.
