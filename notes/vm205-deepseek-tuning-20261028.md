# VM205: DeepSeek-V4.1-Flash decode tuning, measured 2026-10-28

Ran the three arms from `notes/vm205-deepseek-tuning-handoff-20261028.md` on the same host,
prompts and grading as the baseline. Result: **nothing beat the baseline**; production was left
where it started.

## Setup

| | |
|---|---|
| Host | Proxmox guest VM205, Ubuntu 26.04, driver 595.84, RTX 4090 24 GB, 215 GB RAM, 32 vCPU |
| Runtime | `ghcr.io/niko1221/strata:0.2.7-cuda13`, DeepSeek engine 0.1.52 |
| Model | `deepseek-v4.1-flash`, IST-DAS 2.25bpw, context 262144, parallel 1, `--vision on` |
| Placement | 14720 experts (142.8 GB) copied into RAM in 63 s, no demand store, 1024 of 15744 experts (13.82 GB) in VRAM, 592 MiB free |
| Harness | `bench_openai.py` (bench host, not in this repo): decode median of 3 with thinking off, 4K/16K prefill, 12 `standard-v1` fixtures |

## Results

Every arm was a full container recreate; decode is the median of three runs.

| arm | engine flags | decode (tok/s) | default thinking | fixtures |
|---|---|---|---|---|
| baseline | `--dspark auto --dspark-conf 0.65` | **47.6** (30.6 / 47.6 / 53.4) | 41.9 | 12/12 |
| A | `--dspark on --dspark-conf 0.65` | 34.9 (17.7 / 34.9 / 36.1) | 30.0 | 12/12 |
| B | `--dspark auto --experts 5` | 47.2 (36.0 / 47.2 / 58.6) | 48.4 | 12/12 |
| C (`--tune quick`) | `--experts 5 --dspark on --dspark-conf 0.65 --dspark-block 3` | 31.8 (24.8 / 31.8 / 42.8), warm reruns 39–43 | 36.7 | 12/12 |
| re-measured baseline after revert | `--dspark auto --dspark-conf 0.65` | 44.2 | 45.5 | 12/12 |

Prefill stayed at 845–913 tok/s (4K) and 1528–1667 tok/s (16K) in every arm: no arm moved it.

## Verdict

- **Drafting costs more than it saves on this box.** Forcing `--dspark on` drops decode by a
  quarter, with or without `--dspark-block 3`. The engine says why at startup: the routed experts
  are ~149 GB against a 24 GB card, so a verify round reads 3.3x a token's bytes and gains nothing
  (`auto` therefore refuses to load DSpark here).
- **`--experts 5` is speed-neutral** (47.2 vs 47.6, inside the 30–53 spread) and buys a real, if
  small, quality risk, so it is not worth taking alone.
- **`strata launch --tune quick` decided wrong on this box.** It reported 24.8 → 44.3 tok/s
  (+79%) and kept drafting plus a draft block of 3. Its "standard" sample (22.8–24.8 across two
  tuner runs) is less than half the decode rate this same box serves at (44–48), so the relative
  gain is measured against a depressed baseline. The harness's three-run median is the number to
  trust.
- Restore is safe: the re-measured baseline reproduces the original within spread (44.2 vs 47.6).

## Mechanics worth keeping

- `STRATA_SET="dspark=on dspark-conf=0.65"` in the container environment becomes repeated
  `--set dspark=on --set dspark-conf=0.65` on `strata launch`, i.e. `extra` in the preset. Valid
  keys are the engine's own flags: `--dspark on|off|none|auto`, `--dspark-block N`,
  `--dspark-conf F`, `--experts N|auto`. `--plan --output json` shows the resolved `extra` before
  anything starts.
- **A tuned preset cannot be reverted by restoring its JSON.** The launcher re-applies the
  `tuned` block (`--experts 5`, `--dspark on`, `--dspark-block 3`) on every start, and
  `<preset>.choices.json` holds `extra` plus `tune: quick` as well. `strata launch --delete-preset
  dsv41` and recreating the preset is what actually clears it; a new preset name does the same.
- The engine caches conversations in `state/strata/launch/ds4-slots` and reuses them, which makes
  repeated prefill measurements meaningless: a second run of the same 16K prompt reports
  `25051 reused + 1 read` and a handful of tok/s. Use a fresh label or a fresh prompt for prefill.
- Every recreate takes 60–90 s to load (63 s of that is the expert copy into RAM) plus a drain on
  stop, so a `docker stop` needs `-t 90` to avoid killing the engine mid-shutdown.

## Left state

`strata-ds` serves `--dspark auto --dspark-conf 0.65`, no `--experts` override (6 of 6 experts per
word), context 262144, `/health` 200 on `100.0.0.159:8080`. The preset `dsv41` was deleted and
recreated clean, so no tuning result is stored.
