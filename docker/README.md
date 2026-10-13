# Docker recipes

Container definitions for each supported runtime live in subdirectories. Model weights should be mounted from the host rather than baked into images.

- `strata/`: retained Qwen3.8-Flash-Next recipes.
- `maya/`: pinned Project Maya / GLM-5.3-Flash Maya-M-Derisked on RTX 4090;
  default 256K/FP16 DFlash2 profile requires noncommercial use; optional 1M/INT8.
  [Build, calibration, measurements, switching and persistent state](../README.md#maya--glm-53-flash-maya-m-derisked--rtx-4090).
  Do not run alongside Strata on the same GPU.
