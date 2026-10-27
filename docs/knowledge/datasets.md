# Public SO-101 datasets

Full exploration notes (in Spanish): [`../learning/public-so101-datasets.md`](../learning/public-so101-datasets.md).
Run any dataset through `uv run python -m eval.dataset_stats --repo-id <id>` first
([ADR 0009](../decisions/0009-fail-loudly-on-unusable-data.md) explains the exit codes).

## Catalogue

| Dataset | Real / sim | Episodes | Mean length | Cameras | Status |
| --- | --- | ---: | ---: | --- | --- |
| `lerobot/svla_so101_pickplace` | Real | 50 | 8.0 s | side, up | Loads (exit 0) |
| `maximilianofir/so101-left-rack-balanced-1000-dr-speed05-1-20261005` | Sim | 1000 | 10.9 s | external, wrist | Loads (exit 0) |
| `SO-101-robot-learning/so101_pick_place` | Real | 0 in metadata | — | side, top | Empty (exit 1) |
| `youliangtan/so101-table-cleanup` | Real | — | — | — | v2.1 format (exit 2) |
| `aswinkumar99/so101-eval-gallery` | — | — | — | — | No version tag (exit 2) |

_(all verified 2026-10-26, LeRobot 0.6.1, `eval/dataset_stats.py`)_

## Facts

- **All loadable SO-101 datasets seen so far record at 30 FPS with a 6-D action.**
  _(verified 2026-10-26, LeRobot 0.6.1, 2 datasets)_
- **Episodes last 8 to 11 s on average, 15.5 s at most**, so 50 evaluation episodes are roughly
  7 to 13 min of simulated time. A per-episode timeout of ~2× the longest demonstration is a
  reasonable starting point. _(verified 2026-10-26, LeRobot 0.6.1, 2 datasets)_
- **Camera keys differ between datasets** (`side`/`up`, `side`/`top`, `external`/`wrist`). A
  trained policy expects specific keys, so the environment config must map cameras explicitly.
  _(verified 2026-10-26, LeRobot 0.6.1, 3 datasets)_
- **The `maximilianofir/...left-rack...` dataset is a close match to our task**: simulated SO-101
  placing vials in a rack, external + wrist cameras, domain randomization of object placement,
  mat rotation, camera tilt and focal length, lighting, and joint speed (0.5–1.0×). Candidate
  training data for a first ACT policy. _(verified 2026-10-26, dataset card)_
- **A dataset can have data and videos uploaded while `info.json` says 0 episodes** (recording
  not finalized). _(verified 2026-10-26, SO-101-robot-learning/so101_pick_place)_
