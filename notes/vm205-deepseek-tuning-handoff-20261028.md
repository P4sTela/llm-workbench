# Handoff: tune DeepSeek-V4.1-Flash on VM205

Written 2026-10-28. State left behind: DeepSeek is serving, measured, and untuned. The next
session's job is to raise its decode speed without losing quality. Everything below is measured
fact unless marked [inference] or [verify].

**Executed 2026-10-28: no arm won.** Results and the preset mechanics in
[`vm205-deepseek-tuning-20261028.md`](vm205-deepseek-tuning-20261028.md); production was left at
`--dspark auto` with 6 of 6 experts per word.

## Where things stand

| | |
|---|---|
| Host | `ssh -o BatchMode=yes -l comfy comfy-vm.netbird.selfhosted` (private key `Lab` in 1Password; if the 1Password app is locked, ssh reports `Permission denied` even though the key is offered — unlock it, no shell restart needed). Remote shell is bash; pipe scripts with `bash -s`. |
| Serving | container `strata-ds`, image `ghcr.io/niko1221/strata:0.2.7-cuda13`, model `deepseek-v4.1-flash`, context 262144, `/health` 200 |
| Preset | `dsv41` (`/opt/models/state/strata/launch/dsv41.json`), engine log `/opt/models/state/strata/launch/dsv41.engine.log` |
| GLM arm | container `maya` (image `maya-glm53:4090-v1.1.31`) exists but is stopped; the GPU belongs to one engine at a time |
| Disk | 659 GB used / 100 GB free of 796 GB |
| API key | `STRATA_API_KEY` in `/opt/llm-workbench/.env` on the VM; never print it |

## Baseline to beat (measured 2026-10-28)

| metric | value |
|---|---|
| decode, thinking off, 3 runs | 30.6 / 47.6 / 53.4 tok/s → **median 47.6** |
| decode, default thinking, 64 tokens | 41.9 tok/s |
| prompt 4K / 16K | **854** / 1607 tok/s |
| 12 sanity fixtures (`bench/prompts/standard-v1`) | 12/12 |
| lm-eval gsm8k (limit 100) | 0.93 flexible (strict 0.00 = `####` format) |
| lm-eval ifeval (limit 100) | 0.81 prompt-strict / 0.877 instruction-strict |

Full context for these numbers: `notes/vm205-3model-bench-20261028.md` and the vault page
`queries/vm205-3model-bench-20261028`.

Placement at that baseline (from the engine log): 13,893 CPU-lane experts (134.8 GB) copied into
RAM, full-residency, no demand store, 23,570 MiB VRAM, `--experts` effectively 6, `--dspark auto`.

## What to try, in order

1. **`--dspark on --dspark-conf 0.65`.** `auto` decides for itself and on a CPU-bound box it can
   sit at "off"; the published RTX 4090 48 GB report went from 16-22 tok/s (`auto`) to 40.2 tok/s
   (`on`, conf 0.65). Cost: one restart. [inference] expect +10-25% here; measure, do not assume.
2. **`--experts 5` ("Faster").** 5 of 6 experts per word. Upstream measured 19/19 vs 18/19 tasks
   on four R9700, so the quality risk is real but small. Verify with the 12 fixtures + gsm8k.
3. **`strata launch --tune quick`.** Compares the standard settings, the drafter forced on, a
   shorter draft block (3), and one CPU thread per physical core; keeps a change only above 5%.
   Takes 5-10 minutes because every arm reloads the model.

Do not stack all three blind: measure after each, because the drafter and the expert count
interact (fewer experts on the CPU lane can make drafting matter less).

## How to apply the flags (confirm before running) [verify]

The image's `entrypoint.sh` maps only a fixed set of env vars (`MODEL`, `FAMILY`, `CONTEXT`,
`TUNE`, `PARALLEL`, `VISION`, `KV`, `GPU`, `PORT`, `API_KEY`, `PRESET`, `STRATA_SET`). `STRATA_SET`
is documented as "advanced engine settings, space separated KEY=VALUE (like `strata launch --set`)",
so the likely route is:

```bash
docker stop strata-ds && docker rm strata-ds
docker run -d --name strata-ds --gpus all -v /opt/models:/data \
  -e FAMILY=deepseek41 -e MODEL=IST-DAS-2.25bpw -e CONTEXT=256k -e TUNE=skip -e PARALLEL=1 \
  -e PRESET=dsv41 \
  -e STRATA_SET="dspark=on dspark-conf=0.65 experts=5" \
  -e API_KEY="$STRATA_API_KEY" -e STRATA_ALLOWED_HOSTS=comfy-vm.netbird.selfhosted \
  -p 100.0.0.159:8080:8080 ghcr.io/niko1221/strata:0.2.7-cuda13
```

Read `/opt/strata/entrypoint.sh` in the image first (`docker run --rm --entrypoint cat <image>
/opt/strata/entrypoint.sh`) to confirm how `STRATA_SET` is passed through, and check the engine log
for the actual argv: it echoes `engine started: … --serve … --dspark … --experts …`. If `STRATA_SET`
does not carry launch-level settings, the fallback is to run `strata launch` with explicit flags
from inside the container and keep the process in the foreground.

**Do not reuse the old `docker` preset.** It was written by the 0.2.2 Qwen setup and still carries
`--resident-budget-gib` / `--vram-reserve-mib`, which `strata-dsv41` rejects with `unknown option`
(exit 1 after a successful load). Start with `PRESET=dsv41` or a fresh name.

## Verification loop (same tooling as the baseline)

```bash
# on the Mac, after unlocking 1Password
export BENCH_API_KEY=$(ssh -o BatchMode=yes -l comfy comfy-vm.netbird.selfhosted \
  "awk -F= '/^STRATA_API_KEY=/{print \$2}' /opt/llm-workbench/.env" | tr -d '\r\n ')
cd ~/bench && python3 bench_openai.py --base-url http://100.0.0.159:8080/v1 \
  --model deepseek-v4.1-flash --key-env BENCH_API_KEY --label deepseek-tune-<arm>
```

Accept a tuning change only if: decode improves beyond run-to-run spread (the baseline alone
ranged 30.6-53.4 tok/s), fixtures stay 12/12, and gsm8k flexible does not fall below ~0.90.

For the accuracy arm (about 50 minutes at these speeds):

```bash
lm_eval run --model openai-chat-completions \
  --model_args model=deepseek-v4.1-flash,base_url=http://100.0.0.159:8080/v1/chat/completions,tokenizer_backend=None \
  --tasks ifeval,gsm8k --limit 100 --apply_chat_template --output_path ~/bench/deepseek-tune-lmeval.json
```

## When a setting wins

- Save it in the preset, then mirror it into the repo (`docker/strata/compose.022.yaml` style:
  a dedicated compose for the DeepSeek arm) so a rebuild reproduces it.
- Record the result with the version string (`strata 0.2.7`, engine 0.1.52) next to the number —
  batched decoding is still in flight upstream (#4198 design, #4199 M1), so these numbers have a
  short shelf life.
- Append to `notes/vm205-3model-bench-20261028.md` (or a new note) and to the vault page.

## Open items that are not part of the tuning

- Qwen's 12 fixtures were never taken (its container had to stay stopped); the lm-eval arm also
  logged empty `content` responses, so 0.57 likely understates it.
- GLM could move to `Maya-S24` (94.7 GB, 24 GB-card attention, decode +14%) instead of
  Maya-M-Derisked (109 GiB); needs a download and a GPU swap.
- Repo state: Maya pin bumped to v1.1.31 (`c4be544`) in `Dockerfile` / `compose.yaml` / `README.md` /
  `configs/README.md` (commit `874f41e`); the two notes land after it. Nothing else is pending.
- Disk: `strata:backup-0.1.39` (12.9 GB) and one of the two Qwen packs
  (`orcarouter-Q4_K_M` 112 GB or `unsloth-UD-Q4_K_XL` 104 GB) are deletion candidates.
