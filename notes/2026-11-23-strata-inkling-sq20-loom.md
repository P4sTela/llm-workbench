# Strata 0.2.19 / Inkling 2 Mini SQ-20 on loom (RTX 4090) — 2026-11-23

Host: loom, Debian 13, driver 620.70.06, image `ghcr.io/niko1221/strata:0.2.19-cuda13`
(strata-inkling 0.1.65). Recipe: `docker/strata/compose.inkling.yaml` +
`configs/strata-inkling2mini-sq20-4090.env` (SQ-20 lossless, 128K ctx, PARALLEL=1,
vision on GPU, int8 KV, no tuning). VRAM in use: 23.3 GB of 24.5 GB.

Method: non-streaming chat completions, 512-token cap, three runs per prompt,
server `timings`. DSpark drafting is on by default (built into the model).

| prompt | decode t/s (median) | draft acceptance |
|---|---|---|
| English prose (MoE explanation) | 119.6 | 0.28 |
| Python code (LRU cache + tests) | 152.4 | 0.41 |
| Japanese prose (~400 chars) | 100.7 | 0.21 |

Prefill: 20,591-token prompt at 3,204 t/s (TTFT 6.4 s). OpenAI tool call: pass.

Against llama.cpp on the same card (ggml-org IQ4_NL, no drafter): 71.5 t/s
decode on the English prompt, so Strata is 1.67x faster there while serving the
lossless pack instead of a 4-bit one.

Notes:
- The three runs per prompt gave identical outputs and timings: default
  sampling looks greedy. Set temperature explicitly when that matters.
- Draft acceptance follows the text: code is most predictable, Japanese least.
- The container needs `STRATA_API_KEY` (in the untracked `.env`).
