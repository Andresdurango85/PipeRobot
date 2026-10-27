# LeRobot

Pinned version: 0.6.1 ([ADR 0002](../decisions/0002-python-tooling-and-pinning.md)).

## Install

- **LeRobot 0.6.1 requires Python 3.12 or newer.** _(verified 2026-10-26, LeRobot 0.6.1, PyPI metadata)_
- **On a machine without CUDA, `uv sync --extra lerobot` installs the CPU build of torch**
  (torch 2.11.0+cpu); the whole `.venv` is ~1.1 GB, not the several GB of a CUDA build.
  _(verified 2026-10-26, LeRobot 0.6.1, Windows 11 laptop)_
- **LeRobot 0.6.1 caps its dependencies tightly**: `torch<2.12`, `Pillow<13`, `setuptools<82`
  (torch 2.11 needs it), `datasets<5`; datasets 4.8.5 adds `fsspec<=2026.2.0`. Security fixes
  above those caps need a uv override ([ADR 0012](../decisions/0012-dependency-vulnerability-triage.md)).
  The same caps are on LeRobot's GitHub `main`. _(verified 2026-10-27, PyPI metadata + GitHub)_
- **Pillow 13.0.0 works with LeRobot 0.6.1** for image conversion and PNG/TIFF writing, the only
  formats `write_image` accepts (`.jpg` raises "Unsupported image file extension").
  _(verified 2026-10-27, LeRobot 0.6.1, `tests/test_lerobot_compat.py`)_

## Datasets API

- **`LeRobotDatasetMetadata` is imported from `lerobot.datasets`** and downloads only the `meta/`
  folder (info.json, episodes parquet, tasks, stats), never videos. Cheap to run anywhere.
  _(verified 2026-10-26, LeRobot 0.6.1, `eval/dataset_stats.py`)_
- **`meta.episodes` behaves like a Hugging Face `datasets.Dataset`**: column access with
  `episodes["length"]` gives the frame count of each episode.
  _(verified 2026-10-26, LeRobot 0.6.1, `eval/dataset_stats.py`)_
- **LeRobot 0.6 reads only dataset format v3.0.** A v2.1 dataset fails with "The dataset you
  requested (...) is in 2.1 format" and suggests
  `python -m lerobot.scripts.convert_dataset_v21_to_v30 --repo-id=<id>`.
  _(verified 2026-10-26, LeRobot 0.6.1, youliangtan/so101-table-cleanup)_
- **A Hub dataset must have a git tag with its codebase version** (e.g. `v3.0`); without it,
  loading raises `RuntimeError: Your dataset must be tagged with a codebase version`.
  _(verified 2026-10-26, LeRobot 0.6.1, aswinkumar99/so101-eval-gallery)_
- **Unauthenticated Hub access works but warns** ("set a HF_TOKEN to enable higher rate limits").
  Fine for metadata; CI that downloads a lot will need a token as a secret.
  _(verified 2026-10-26, huggingface_hub via LeRobot 0.6.1)_

## SO-100 / SO-101 naming

- **Action and state are 6 joint target positions**: `shoulder_pan.pos`, `shoulder_lift.pos`,
  `elbow_flex.pos`, `wrist_flex.pos`, `wrist_roll.pos`, `gripper.pos`. Same names on SO-100 and
  SO-101. _(verified 2026-10-26, LeRobot 0.6.1, 2 public datasets)_
- **`robot_type` in `info.json` is not reliable**: the same arm appears as `so100_follower`,
  `so_follower` and `so101_follower`. Check action dimension and names instead.
  _(verified 2026-10-26, LeRobot 0.6.1, see [datasets.md](datasets.md))_
