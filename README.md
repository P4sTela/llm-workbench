# LLM Workbench

A personal workbench for experimenting with open-weight LLMs across different machines.

This is a public collection of Docker configurations, machine-specific settings, and notes from real runs. It is intentionally practical and experimental rather than a general-purpose framework or a production platform.

## Current focus

- Qwen3.8-27B on an NVIDIA RTX 4090
- NInfer and llama.cpp
- Long-context, KV-cache, speculative decoding, reasoning, and tool-use experiments
- Reproducible configurations that can move to another Linux GPU host

## Repository layout

- `docker/` — container definitions and compose files
- `configs/` — reusable runtime profiles
- `models/` — model metadata and download instructions; weights are not committed
- `notes/` — short notes and results from actual runs
- `scripts/` — small helpers for fetching, checking, and smoke-testing

## Principles

- Pin model revisions and record checksums when a run matters.
- Keep model weights outside Git and mount them into containers.
- Keep host-specific values such as bind addresses in local `.env` files.
- Mark results as tested, experimental, or failed instead of presenting guesses as benchmarks.
- Do not commit API keys, personal prompts, session logs, or private tool definitions.

## Status

The repository is being built incrementally. The first recipe is planned around the tested NInfer V2 / Qwen3.8-27B / RTX 4090 configuration; new recipes will be added after they have been exercised on real hardware.

## License

No repository license has been selected yet. Until a license is added, the contents should not be assumed to be available for reuse. Model and dependency licenses remain the responsibility of their respective upstream projects.
