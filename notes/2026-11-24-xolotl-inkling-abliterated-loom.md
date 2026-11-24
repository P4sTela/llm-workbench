# Xolotl / orcarouter Inkling 2 Mini abliterated on loom (RTX 4090) — 2026-11-24

Engine: Xolotl `xolotl-inkling` (Indras-Mirror/Xolotl 3435d55, MIT), built from source for sm_89 by
`docker/xolotl/Dockerfile` (~4 min of compile on loom). Server: Xolotl's own `serve.server --engine strata`
(OpenAI + Anthropic API, key required). Config: `configs/xolotl-inkling2mini-abliterated-4090.json`.

Model: orcarouter `Inkling-2-Mini-abliterated-Mix-16G.gguf` (llama.cpp GGUF, text only), loaded as is.
Drafter: unsloth `dspark/dspark-Inkling-2-Mini-BF16.gguf` (pre-mainline format). Tokenizer pack exported
from thinkingmachines/Inkling-2-Mini with `tools/inkling/export_tokenizer.py` (200,058 tokens).

Context 524288 with `--kv-type k8v4` and the drafter loaded: 14.28 GiB weights + 6.75 GiB state,
23.1 GB of VRAM in use.

| | llama.cpp b12648 (64K, no drafter) | llama.cpp (128K -ub 256, ngram-mod) | **Xolotl (512K, k8v4, DSpark)** |
|---|---|---|---|
| decode, English prose | 73.8 | 75.7 | **116.9** |
| decode, Python code | 73.8 | 85.9 | **212.4** |
| decode, Japanese prose | 73.6 | 74.8 | **100.4** |
| decode, rewrite a file | 71.6 | 104.8 | **224.8** |
| prefill, 20.6K prompt | 1,397 | 1,353 | **4,254** |
| needle at 132K tokens | — (192K arm: found, 442 t/s, 300 s) | — | **found, 3,075 t/s, 45 s** |
| tool call | pass | pass | pass |

Decode figures are medians of two 512-token runs at temperature 0.7 (server timings, checked
against wall clock). Temperature 0 gives the same speeds. The engine log shows speculative steps
on these sampled requests ("spec N steps, x accepted drafts/step"), although the server's timings
report draft_n = 0.

llama.cpp cannot use the DSpark drafter here: Unsloth's file fails `markov_w1` (201024 vs 200058),
and the "mainline" file fails `joint_proj` (5120 vs 2816) on b12648. 384K+ does not fit in llama.cpp
(compute buffer 4.8 GB at -ub 64).

## 512K at the edge

A 480,040-token needle prompt prefilled in 320 s (~1,500 t/s), then the engine aborted on the first
decode step: `CUDA error: out of memory` in `cudaGraphInstantiate`. The author's 512K run used a
13.93 GB file; this one is 14.28 GiB of weights, so the margin is smaller.

With `GGML_CUDA_DISABLE_GRAPHS=1` (docker/xolotl/xolotl.env) the same prompt passes: prefill 1,496 t/s,
the needle found (PERSIMMON-42), decode 65 t/s at 480K, 325 s wall. The cost is short-context decode:
code 212 -> 159 t/s, prose 117 -> 104 t/s.

## 384K with CUDA graphs on (the serving default)

`configs/xolotl-inkling2mini-abliterated-4090-384k.json`, empty `xolotl.env`: 21.7 GB of VRAM at load.
Decode (temperature 0.7, two runs): prose 113-119, code 207-218, Japanese 99-102, file rewrite 213-224 t/s,
i.e. the full speed. A 369,640-token needle prompt: prefill 2,977 t/s, needle found, decode 62 t/s at
370K, 126 s wall, engine still up afterwards.

Pick: 384K + graphs for speed (agent work, benchmarks); the 512K config + GGML_CUDA_DISABLE_GRAPHS=1
only when a prompt needs more than 384K.
