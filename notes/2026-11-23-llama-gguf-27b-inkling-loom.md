# llama.cpp GGUF arms on loom (RTX 4090, Gen4 x16) — 2026-11-23

Host: loom (ex-VM205), Debian 13, driver 620.70.06, llama.cpp 1.0.0-dev
build 12627 (server-cuda), one model at a time, `--jinja`, q8_0 KV.

Method: `scripts/bench-llama.py` — a 2.4K-token prompt for prefill, three
256-token generations for decode (thinking off), and one OpenAI tool call.
Numbers are the server's own `timings`.

| Model | Quant | ctx | prefill t/s | decode t/s | tool call | VRAM |
|---|---|---|---|---|---|---|
| Qwen3.8-27B (base) | UD-Q4_K_XL | 131072 | 3123 | 47.7 | pass | — |
| DaisyRose-27B | Q4_K_XL | 131072 | 2899 | 47.6 | pass | — |
| Inkling 2 Mini | IQ4_NL | 32768 | 1938 | **71.7** | pass | 20.9 GB |

Reference (old VM, Ubuntu 26.04, driver 595.84, **PCIe Gen1**): NInfer Qwen3.8-27B
44.2 t/s without MTP / 81.8 with MTP; Strata Qiwen3.8-Flash-Next 67.4 t/s.

## Notes

- The 27B pair is speed-identical, as expected for the same architecture and
  size: the DaisyRose gain is in task behaviour, not throughput. Comparing them
  needs an agent harness, not this bench.
- MTP is not active: the base GGUF carries `blk.64.nextn.*` and llama.cpp build
  12627 reports them as unused tensors, so decode is the MTP-off number. NInfer
  reached 81.8 t/s with MTP on; that is the route to recover it.
- Inkling 2 Mini runs 1.5x faster than the 27B dense at Qwen3.8-27B-class
  quality (AA v5 20.1), but it is verbose: generations hit the 256-token cap, so
  wall-clock per answer is worse than the t/s suggests.
- Inkling's GGUF layout matters. The Unsloth pack fails with
  `check_tensor_dims: tensor 'blk.24.attn_q.weight' not found` because it stores
  the loop as 48 layers (unmerged PR layout). The ggml-org conversion loads.
- Do not offload Inkling's looped experts to CPU on CUDA: upstream issue #32710
  returns NaN and a repeating token.
