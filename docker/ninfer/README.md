# NInfer

The first reference run used a locally built `ninfer-4090:sm89` image based on the [`sergiuszm/ninfer-4090`](https://github.com/sergiuszm/ninfer-4090) `rtx4090-port` work.

The tested launch values are in [`configs/ninfer-v2-qwen38-4090-262k-e8-mtp3.env`](../../configs/ninfer-v2-qwen38-4090-262k-e8-mtp3.env). Model weights and artifacts are mounted from outside the repository; they are never baked into Git or the container image by default.

Docker build and run instructions will be added here when they have been reproduced from a clean checkout. Until then, the result note is a record of a tested configuration, not a claim that this repository already provides a one-command deployment.
