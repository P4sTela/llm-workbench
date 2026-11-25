# Qwen3.8-Flash-Next on Xolotl `strata` (loom, RTX 4090 + 220 GiB RAM) — 2026-11-25

Image `llm-workbench/xolotl:3435d55-qfn` (docker/xolotl/Dockerfile now also builds the `strata` target).
Configs: `configs/xolotl-qwen38fn-orca-q4km-4090.json`, `configs/xolotl-qwen38fn-xq45-4090.json`
(256K context, int8 KV with 32K resident, MTP `--spec 4`, exact routing: no STRATA_ROUTE_RESIDENT).

Setup steps on loom:
- MTP draft layer: `tools/mtp_fetch.py fetch` (5.2 GB of mtp.* tensors from Qwen/Qwen3.8-Flash-Next by range
  requests, no token needed) -> `verify` -> `mtp_pack.py --experts q2_0` -> `mtp_rt.py` -> copy `data/draft_vocab.bin`
  into `/opt/models/qwen3.8-flash-next-mtp/rt`. Shared by both models.
- orcarouter Q4_K_M (3 shards, 119.2 GB): `tools/iq_pack.py --gguf <shard 1> --out pack-q4km --compat-bf16` (~1 min).
- XQ 45 GB ships `pack-qfn45`, whose native_experts.txt names the shards `Swift1.5-QFN-XQ-45GB-0000N-of-00002.gguf`;
  the HF files are named differently, so symlinks with the old names are needed (else "ArenaExpertSource: cannot open").

Speed, `~/bench/tb2-loom/speed.py` (temperature 0.7, 1,024 tokens, median of 2; engine t/s / wall-clock t/s):

| | prose | code | ja | file rewrite | prefill 17K | VRAM expert cache |
|---|---|---|---|---|---|---|
| orca Q4_K_M, tail skip 7 (engine default) | 139.9 / 125.8 | 136.9 / 127.2 | 137.8 / 131.3 | 190.7 / 164.7 | 2,534 | 5,307 slots, 16.2 GiB |
| orca Q4_K_M, exact (`STRATA_ROUTE_TAIL_SKIP=0`) | 115.4 / 102.6 | 116.3 / 110.2 | 114.5 / 109.7 | 159.8 / 143.7 | 2,552 | same |
| XQ 45 GB, tail skip 7 | 161.3 / 151.4 | 176.9 / 168.8 | 142.3 / 137.9 | 233.3 / 210.3 | 4,418 | 10,250 slots, 14.9 GiB |
| XQ 45 GB, exact | 163.0 / 150.3 | 169.4 / 165.9 | 145.7 / 134.8 | 222.6 / 202.3 | 4,462 | same |

Tool call passes on all four. The XQ experts are smaller, so twice as many fit in VRAM and the exact
path costs nothing; on Q4_K_M the tail skip (a lossy "skip a missed rank>=7 expert") is worth ~20%.
Previous loom figure for Flash-Next: 67.4 t/s (Strata 0.2.2, orcarouter Q4_K_M, Oct).
