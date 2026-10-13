#!/usr/bin/env python3
"""Run Maya's GLM tuning without serving or swallowing calibration failures.

Pinned maya.py's --calibrate --no-start returns zero even when tuning fails,
including engine exceptions and busy GPUs, and treats store-write errors as
warnings. Reuse its actual GLM calibration and hardware key, but propagate errors
and persist both the exact selected config and the calibration store explicitly.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/maya")
import maya  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--no-start", action="store_true", required=True)
    args = parser.parse_args()
    path = args.config.resolve(strict=True)
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("backend", "cuda") != "cuda":
        parser.error("this recipe's GLM calibration requires the CUDA backend")

    # Unlike upstream busy_gpus(), a failed query or absent selected GPU must not
    # be interpreted as an idle device. Keep upstream's >1 GiB busy threshold.
    query = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=30, check=True,
    )
    used = {}
    for line in query.stdout.splitlines():
        index, memory = line.split(",")
        used[int(index)] = int(float(memory))
    for gpu in cfg["gpu"]:
        if gpu not in used:
            parser.error(f"selected GPU {gpu} is absent from nvidia-smi")
        if used[gpu] > 1024:
            parser.error(f"GPU {gpu} has {used[gpu]} MiB in use; stop model servers before calibrating")

    # Read before measuring: do not silently discard a malformed old store.
    store_path = maya.CAL_STORE
    store = json.loads(store_path.read_text(encoding="utf-8")) if store_path.exists() else {}
    if not isinstance(store, dict):
        parser.error(f"{store_path} must contain a calibration object")
    key = maya.hardware_key(cfg)  # Draft modes use separate HOME calibration stores.
    result = maya.CAL.run(cfg, say=maya.say)
    rate = result["report"].get("tok_s")
    if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
        raise RuntimeError("calibration produced no positive measured decode rate; config/store unchanged")
    env = maya.CAL.apply(cfg.get("env") or {}, result["settings"])
    if env:
        cfg["env"] = env
    else:
        cfg.pop("env", None)
    store[key] = {
        "settings": result["settings"], "tok_s": rate, "date": time.strftime("%Y-%m-%d"),
    }
    store_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = store_path.parent / f"{path.stem}-calibration-report.json"
    report_path.write_text(json.dumps({"hardware_key": key, **result}, indent=1) + "\n", encoding="utf-8")
    # Atomic individual replacements; any I/O failure exits nonzero. No server or
    # dashboard-state rewrite occurs, and unrelated config/env settings survive.
    store_tmp = store_path.with_suffix(".json.tmp")
    store_tmp.write_text(json.dumps(store, indent=1) + "\n", encoding="utf-8")
    store_tmp.replace(store_path)
    cfg_tmp = path.with_suffix(".json.tmp")
    cfg_tmp.write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
    cfg_tmp.replace(path)
    print(f"Calibrated {path}: {rate} tok/s; store: {store_path}; report: {report_path}")


if __name__ == "__main__":
    main()
