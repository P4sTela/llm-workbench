# Terminal-Bench 2.0, 20-task subset: Inkling 2 Mini (Strata) vs Qwen3.8-27B (llama.cpp MTP) — 2026-11-24

Harness: Harbor + terminus-2, temperature 0.7, 2 trials at a time, agent timeout x2
(the server answers one request at a time), one attempt per task, tasks run on cachy
in Docker, model served from loom's RTX 4090. Subset: seed 20261123, 4 easy / 12 medium /
4 hard, model-training tasks excluded. Not comparable with leaderboard numbers.

| | Inkling 2 Mini SQ-20 (Strata 0.2.19, DSpark) | Qwen3.8-27B UD-Q4_K_XL (llama.cpp, MTP) |
|---|---|---|
| Solved | **11 / 20** | **11 / 20** |
| Solved by this model only | financial-document-processor, mailman, torch-pipeline-parallelism | break-filter-js-from-html, build-pov-ray, protein-assembly |
| Agent timeouts | 5 | 6 |
| Median output tokens per task | 16.4K | 34.0K |
| On the 8 tasks both solved: median output tokens / wall time | 15.1K / 387 s | 10.4K / 229 s |

Solved by both: cobol-modernization, custom-memory-heap-crash, fix-git,
large-scale-text-editing, openssl-selfsigned-cert, overfull-hbox, prove-plus-comm,
vulnerable-secret. The union solves 14 of 20.

Notes:
- Six Inkling trials first failed with "Failed to start tmux session" (harness, before
  the model ran) and were rerun; one rerun was cut by a host shutdown and run again.
- cobol-modernization under Qwen hit the agent timeout but the verifier still passed it.
- 20 tasks is small: a 3-vs-3 split of unique solves is noise-level.
