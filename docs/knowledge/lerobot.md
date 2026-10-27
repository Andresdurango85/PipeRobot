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
- **The Hugging Face Robotics Course imports still work in 0.6.1**:
  `from lerobot.datasets.lerobot_dataset import LeRobotDataset` and
  `from lerobot.datasets.streaming_dataset import StreamingLeRobotDataset`; both take
  `delta_timestamps`. _(verified 2026-10-26, LeRobot 0.6.1, import + signature check)_
- **Padding at episode edges is flagged as `<key>_is_pad`** (a `BoolTensor`) in each sample, for
  both the regular and the streaming dataset. _(verified 2026-10-26, LeRobot 0.6.1, source of
  `datasets/dataset_reader.py` and `datasets/streaming_dataset.py`)_
- **Unauthenticated Hub access works but warns** ("set a HF_TOKEN to enable higher rate limits").
  Fine for metadata; CI that downloads a lot will need a token as a secret.
  _(verified 2026-10-26, huggingface_hub via LeRobot 0.6.1)_

## Policies (ACT)

- **ACT defaults run a full chunk open-loop**: `ACTConfig()` has `chunk_size=100`,
  `n_action_steps=100`, `temporal_ensemble_coeff=None`, `n_obs_steps=1`, `use_vae=True`,
  `kl_weight=10.0`, `vision_backbone="resnet18"` and MEAN_STD normalization for visual, state and
  action. At 30 fps that is ~3.3 s between observations. Temporal ensembling requires
  `n_action_steps=1`. _(verified 2026-10-26, LeRobot 0.6.1, `ACTConfig()` + `configuration_act.py`)_
- **`ACTPolicy` keeps an action queue between `select_action` calls; `reset()` clears it** and must
  be called at every environment reset, or the next episode starts with the previous one's actions.
  _(verified 2026-10-26, LeRobot 0.6.1, `policies/act/modeling_act.py`)_
- **Normalization stats are saved with the policy's pre/post-processors** (`save_pretrained`) and
  restored by `DataProcessorPipeline.from_pretrained`, unless overridden with
  `overrides={"normalizer_processor": {"stats": ...}}`.
  _(verified 2026-10-26, LeRobot 0.6.1, `processor/normalize_processor.py` docstring)_

## Robot Learning Tutorial snippets vs 0.6.1

The tutorial's code (`fracapuano/robot-learning-tutorial`, `snippets/`) predates 0.6.1:

- **`dataset_to_policy_features` moved** from `lerobot.datasets.utils` to
  `lerobot.utils.feature_utils`. _(verified 2026-10-26, LeRobot 0.6.1, import check)_
- **`lerobot.robots.so100_follower` no longer exists**; SO-100 and SO-101 share
  `lerobot.robots.so_follower`, which exports `SO100Follower(Config)`, `SO101Follower(Config)` and
  `SOFollower(Config)`. _(verified 2026-10-26, LeRobot 0.6.1, import check)_
- **Still valid**: `lerobot.policies.factory.make_pre_post_processors`,
  `lerobot.policies.utils.build_inference_frame` / `make_robot_action`,
  `lerobot.configs.types.FeatureType`, `lerobot.async_inference` (`policy_server`, `robot_client`).
  _(verified 2026-10-26, LeRobot 0.6.1, import check)_

## Evaluation (`lerobot-eval`)

- **`lerobot-eval --policy.path=<dir|repo> --env.type=pusht` runs on CPU** with
  `--policy.device=cpu --policy.use_amp=false --eval.use_async_envs=false`; the PushT simulator
  comes with the `pusht` extra (gym-pusht + pymunk, 2D). VQ-BeT: ~6 s per episode on the laptop
  CPU, batch of 10 envs. _(verified 2026-10-27, LeRobot 0.6.1, `eval/lerobot_eval.py`)_
- **`eval_info.json` (0.6.1) is per task**: `per_task[0].metrics` holds lists `successes`,
  `max_rewards`, `sum_rewards`, `video_paths`; no seeds. Seeds are `--seed + episode index`
  (default 1000). Videos: only the first 10 episodes (hardcoded). _(verified 2026-10-27, source)_
- **Same seeds give identical outcomes in PushT** across separate runs.
  _(verified 2026-10-27, two runs of 500 episodes, seeds 1000–1499, episode by episode)_
- **PushT's reward is `coverage / 0.95`, capped at 1; success means coverage above 95 %.** So
  `max_rewards` in `eval_info.json` is not the coverage: a failed episode with max reward 0.99 is
  a near miss at ~94 % coverage. _(verified 2026-10-27, gym-pusht 0.1.8 source, `pusht.py`)_
- **Policies published before LeRobot 0.4 fail to load** with
  "requires migration to processor format": run
  `python -m lerobot.processor.migrate_policy_normalization --pretrained-path <dir> --output-dir <dir>`.
  In 0.6.1 that script crashes on tuple-typed config fields given as JSON lists (`crop_shape`);
  `eval/lerobot_policy.py` wraps it with a fix. Old configs may also carry fields 0.6 rejects
  (`lerobot/vqbet_pusht`: `mlp_hidden_dim`, unused in 0.6.1 code, safe to drop).
  _(verified 2026-10-27, LeRobot 0.6.1, [ADR 0016](../decisions/0016-real-evaluator-lerobot-pusht.md))_
- **`lerobot/vqbet_pusht` reaches 263/500 (52.6 %) with LeRobot 0.6.1** on seeds 1000–1499 and
  270/500 on seeds 2000–2499 (model card: 285/500 with an older version; not significantly
  different). Disjoint 50-episode windows of the same policy range from 18/50 to 33/50, and
  10-episode windows from 2/10 to 9/10. ~43 min per 500 episodes on the laptop CPU.
  _(verified 2026-10-27, [ADR 0016](../decisions/0016-real-evaluator-lerobot-pusht.md))_

## SO-100 / SO-101 naming

- **Action and state are 6 joint target positions**: `shoulder_pan.pos`, `shoulder_lift.pos`,
  `elbow_flex.pos`, `wrist_flex.pos`, `wrist_roll.pos`, `gripper.pos`. Same names on SO-100 and
  SO-101. _(verified 2026-10-26, LeRobot 0.6.1, 2 public datasets)_
- **`robot_type` in `info.json` is not reliable**: the same arm appears as `so100_follower`,
  `so_follower` and `so101_follower`. Check action dimension and names instead.
  _(verified 2026-10-26, LeRobot 0.6.1, see [datasets.md](datasets.md))_
