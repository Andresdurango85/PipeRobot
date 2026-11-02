# SO-101 bring-up with LeRobot 0.6.1 (Windows)

The runbook from bare servos to a policy evaluated on the real arm, in the order to run it.
Hardware, power supplies and cameras: see [AGENTS.md](../../AGENTS.md#hardware-and-stack).
**Never swap the leader's 5 V and the follower's 12 V supplies.**

How each fact was checked:

- `LeRobot 0.6.1, <file or --help>`: read from the installed package (source or `--help`).
- `docs/lerobot/so101` or `docs/lerobot/il_robots`: the official pages
  ([SO-101](https://huggingface.co/docs/lerobot/so101),
  [real-world robots](https://huggingface.co/docs/lerobot/il_robots)). They follow LeRobot
  `main`, not 0.6.1, so every flag taken from them was checked against the 0.6.1 `--help`.
- **Unverified until hardware**: written from source or docs, not run yet against motors.

Commands are for PowerShell: backtick line continuation, `COM` ports, and JSON-like camera
specs in single quotes so PowerShell leaves the braces alone. `COM3`/`COM4` are placeholders.

## 0. Prerequisites

- **Install the hardware dependencies with the `so101` dependency group**
  ([ADR 0022](../decisions/0022-so101-hardware-deps-and-manual-outcomes.md)):

  ```powershell
  uv sync --group so101
  ```

  It adds LeRobot's extras, by name:
  - `feetech`: `feetech-servo-sdk`, `pyserial`, `deepdiff`. Needed by `find-port`,
    `setup-motors`, `calibrate`, `teleoperate`, `record`, `replay` and `rollout`.
  - `hardware`: adds `pynput`, which the keyboard controls of `record` need on Windows.
  - `viz`: `rerun-sdk`, for `--display_data=true` and `lerobot-dataset-viz`.
  - `training`: `accelerate` (and `wandb`), required by `lerobot-train` even locally.

  `uv sync` is exact: add `--extra lerobot` or `--group sim-pusht` too if the machine also needs
  them, or they are uninstalled. Without `feetech`, `lerobot-find-port` fails with "'pyserial' is
  required but not installed". _(verified 2026-11-01, LeRobot 0.6.1, package metadata,
  `lerobot_find_port.py`, `lerobot_train.py`, `lerobot_dataset_viz.py`)_
- **Training needs the venv with the CUDA torch build**; the repo's `.venv` has CPU torch on
  Windows ([lerobot.md](lerobot.md#install)). That venv has LeRobot 0.6.1 and
  `torch 2.11.0+cu128` with CUDA available. _(verified 2026-11-01, home PC)_ To add the
  hardware deps, sync it with `--group so101` (point `UV_PROJECT_ENVIRONMENT` at it), then swap
  the cu128 torch and torchvision back in over the lock's CPU build, as
  `.github/workflows/gpu-smoke.yml` does. Unverified on that venv: the group was checked in a
  plain `.venv` (all four extras import, `lerobot-find-port` reaches its prompt).
- **Set `$env:PYTHONUTF8 = "1"` before running LeRobot commands.** Without it,
  `lerobot-record --help` and `lerobot-rollout --help` crash with `UnicodeEncodeError: 'charmap'
  codec can't encode character '≥'` (the Windows console uses cp1252).
  _(verified 2026-11-01, LeRobot 0.6.1, `--help` on the home PC)_
- **Use the same `id` for each arm in every command** (`piperobot_follower`,
  `piperobot_leader` below): it names the calibration file. Calibrations live in
  `$HF_HOME\lerobot\calibration\robots\so_follower\<id>.json` and
  `...\teleoperators\so_leader\<id>.json` (`HF_HOME` defaults to `~\.cache\huggingface`;
  override with `HF_LEROBOT_CALIBRATION`). _(verified 2026-11-01, LeRobot 0.6.1,
  `robots/robot.py`, `teleoperators/teleoperator.py`, `utils/constants.py`)_

## 1. Before the electronics arrive

- **Clean the printed parts**: remove all support material (a small screwdriver under the
  supports works). _(verified 2026-11-01, docs/lerobot/so101 (main))_
- **Sort and label the leader's 6 servos by gear ratio** (the ratio is on the motor's label) into
  three bins, and write the target joint and ID on each with tape. Mixing them up is the
  easy mistake: `setup-motors` writes an ID to whatever motor is plugged in, whatever its ratio.

  | Ratio | Count | Joint (ID) |
  | --- | --- | --- |
  | 1/345 | 1 | `shoulder_lift` (2) |
  | 1/191 | 2 | `shoulder_pan` (1), `elbow_flex` (3) |
  | 1/147 | 3 | `wrist_flex` (4), `wrist_roll` (5), `gripper` (6) |

  The follower's 6 servos are all 1/345, so any of them fits any joint; label them by joint
  anyway (IDs 1–6 as above). _(verified 2026-11-01, docs/lerobot/so101 (main) table; IDs from LeRobot
  0.6.1 `so_follower.py`, `so_leader.py`)_
- **Do not assemble yet.** IDs are set one motor at a time on a bare bus (step 4); the docs
  advise putting one 3-pin cable in each motor as it is placed. _(verified 2026-11-01,
  docs/lerobot/so101 (main))_
- **Enable Windows Developer Mode on the training PC** (Settings > System > For developers >
  Developer Mode): without it `lerobot-train` crashes at its first checkpoint (step 11). Andrés
  turns it on himself ([ADR 0022](../decisions/0022-so101-hardware-deps-and-manual-outcomes.md)).
- **Test the cameras now**, if you have them: plug the C920 and the wrist camera and run
  `lerobot-find-cameras opencv` (step 6). This works with the current `.venv`.

## 2. Leader gear ratios per joint

| Joint | Motor ID | Ratio |
| --- | --- | --- |
| `shoulder_pan` (base) | 1 | 1/191 |
| `shoulder_lift` | 2 | 1/345 |
| `elbow_flex` | 3 | 1/191 |
| `wrist_flex` | 4 | 1/147 |
| `wrist_roll` | 5 | 1/147 |
| `gripper` | 6 | 1/147 |

The mix lets the leader hold its own weight while staying light to move by hand. This matches
the 1× 1/345, 2× 1/191, 3× 1/147 set in AGENTS.md. _(verified 2026-11-01, docs/lerobot/so101 (main);
joint-to-ID mapping from LeRobot 0.6.1 `so_leader.py`)_

## 3. Find each arm's COM port

```powershell
$env:PYTHONUTF8 = "1"
lerobot-find-port
```

Connect one controller board by USB (and its supply), run the command, unplug the USB cable when
asked and press Enter: the port that disappeared is that arm's. On Windows it lists COM ports
through pyserial. Repeat for the other arm. _(verified 2026-11-01, LeRobot 0.6.1,
`lerobot_find_port.py`; COM names unverified until hardware)_

## 4. Set motor IDs and baudrate, one motor at a time

```powershell
lerobot-setup-motors --robot.type=so101_follower --robot.port=COM3
lerobot-setup-motors --teleop.type=so101_leader --teleop.port=COM4
```

- The script asks for the motors in reverse order, one prompt each: "Connect the controller board
  to the 'gripper' motor only and press enter.", then `wrist_roll`, `wrist_flex`, `elbow_flex`,
  `shoulder_lift`, `shoulder_pan`. After each it prints "'gripper' motor id set to 6", and so on.
  _(verified 2026-11-01, LeRobot 0.6.1, `so_follower.py`/`so_leader.py` `setup_motors`)_
- Only that motor may be on the bus, not daisy-chained to another. The script scans every
  baudrate to find it, writes its ID and sets its baudrate to 1,000,000 in EEPROM, so this is done
  once (and again for motors reused from another robot). _(verified 2026-11-01, LeRobot 0.6.1,
  `motors/motors_bus.py` `setup_motor`, `motors/feetech/feetech.py` `DEFAULT_BAUDRATE`)_
- For the leader, plug the motor whose ratio matches the prompted joint (step 2).
- If it fails, check the supply, the USB cable and the 3-pin cable. On a Waveshare board, both
  jumpers go on channel `B` (USB). Check the cabling before every Enter: the supply cable can come
  loose while you handle the board. _(verified 2026-11-01, docs/lerobot/so101 (main))_
- Afterwards, chain the motors and connect the board to `shoulder_pan` (ID 1). Then assemble.

Unverified until hardware.

## 5. Calibrate follower and leader

```powershell
lerobot-calibrate --robot.type=so101_follower --robot.port=COM3 --robot.id=piperobot_follower
lerobot-calibrate --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=piperobot_leader
```

- If a calibration file exists for that `id`: Enter reuses it, `c` + Enter recalibrates.
- "Move ... to the middle of its range of motion and press ENTER....": put every joint at the
  middle of its range. Torque is off.
- "Move all joints except 'wrist_roll' sequentially through their entire ranges of motion.":
  a live MIN/POS/MAX table updates while you sweep each joint end to end; Enter stops it.
  `wrist_roll` is taken as a full turn (0–4095) and not swept.
- The file is saved and its path printed ("Calibration saved to ...").
- On connect, the follower's gripper is limited to 50 % torque and current to avoid burning it out.

_(verified 2026-11-01, LeRobot 0.6.1, `so_follower.py`/`so_leader.py` `calibrate` and
`configure`; procedure also in docs/lerobot/so101 (main))_. On Windows, Enter during the sweep is read
with `msvcrt.kbhit()`, which needs a real console window: unverified until hardware whether the
VS Code terminal works; if Enter does nothing, run it from Windows Terminal.

## 6. Find the cameras

```powershell
lerobot-find-cameras opencv
```

It lists the OpenCV cameras with their index and default profile and saves a few frames to
`outputs\captured_images`. On the home PC with one webcam it found index 0, backend DSHOW,
default profile 640×480 YUY2 with `Fps: 0.0`, so always set `fps` explicitly in the camera spec.
_(verified 2026-11-01, LeRobot 0.6.1, home PC)_. Which index is the C920 and which is the wrist
camera is unverified until hardware: unplug one and run it again to tell them apart. Windows
indexes can change when USB devices change, so re-check after replugging.

## 7. Teleoperate, without and with cameras

```powershell
lerobot-teleoperate `
  --robot.type=so101_follower --robot.port=COM3 --robot.id=piperobot_follower `
  --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=piperobot_leader
```

With cameras and the Rerun viewer (needs `viz`):

```powershell
lerobot-teleoperate `
  --robot.type=so101_follower --robot.port=COM3 --robot.id=piperobot_follower `
  --robot.cameras='{ front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}' `
  --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=piperobot_leader `
  --display_data=true
```

- It calibrates any arm that has no calibration for its `id` before starting.
  _(verified 2026-11-01, docs/lerobot/il_robots (main))_
- Defaults: `--fps=60`, `--display_mode=rerun`. Camera fields: `index_or_path`, `width`,
  `height`, `fps`, plus `fourcc`, `rotation`, `backend`. `--robot.max_relative_target` caps each
  step's motion for safety (default none). _(verified 2026-11-01, LeRobot 0.6.1, `--help`,
  `config_so_follower.py`, `configuration_opencv.py`)_
- Unverified until hardware: whether both cameras sustain 30 fps at that resolution, and the
  teleop latency on Windows.

## 8. Record episodes (local dataset, not uploaded)

```powershell
lerobot-record `
  --robot.type=so101_follower --robot.port=COM3 --robot.id=piperobot_follower `
  --robot.cameras='{ front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}' `
  --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=piperobot_leader `
  --dataset.repo_id=local/so101_tube_rack `
  --dataset.single_task="Pick the centrifuge tube and place it in the yellow rack" `
  --dataset.num_episodes=10 --dataset.episode_time_s=30 --dataset.reset_time_s=15 `
  --dataset.push_to_hub=false
```

- **`--dataset.push_to_hub` defaults to `True`**: without `=false` the dataset is uploaded at the
  end. _(verified 2026-11-01, LeRobot 0.6.1, `lerobot-record --help`)_
- Other defaults: `fps=30`, `episode_time_s=60`, `reset_time_s=60`, `num_episodes=50`,
  `video=True`. The dataset goes to `$HF_HOME\lerobot\<repo_id>` unless `--dataset.root` is set;
  keep it out of the git repo. `repo_id` uses the `<user>/<name>` form even for local datasets.
  _(verified 2026-11-01, LeRobot 0.6.1, `lerobot-record --help`)_
- Keys: Right arrow or `n` ends the episode or reset early; Left arrow or `r` re-records it;
  Escape or `q` stops and saves (case-insensitive). On Windows these come from a `pynput` global
  listener (from `hardware`); the terminal fallback exists only on POSIX.
  _(verified 2026-11-01, LeRobot 0.6.1, `utils/keyboard_input.py` `init_keyboard_listener`)_.
  Unverified until hardware: whether keys pressed in another window also count, as a global
  listener suggests. If so, typing an `n`, `r` or `q` anywhere ends or discards the episode, so
  don't type in other windows while recording.
- To add episodes, re-run with `--resume=true`; `num_episodes` then counts the additional
  episodes. To start over, delete the dataset folder. _(verified 2026-11-01,
  docs/lerobot/il_robots (main); `--resume` in 0.6.1 `--help`)_
- **`lerobot-record` no longer runs policies** and rejects dataset names starting with `eval_`
  (reserved for `lerobot-rollout`, step 12). _(verified 2026-11-01, LeRobot 0.6.1,
  `lerobot_record.py`)_
- The docs suggest at least 50 episodes, about 10 per object position, with fixed cameras and a
  consistent grasp. _(verified 2026-11-01, docs/lerobot/il_robots (main))_

## 9. Visualize a recorded episode with Rerun

```powershell
lerobot-dataset-viz --repo-id local/so101_tube_rack --episode-index 0
```

Spawns a local Rerun viewer; `--root` points at a dataset outside the default cache, and
`--save 1 --output-dir <dir>` writes an `.rrd` file instead. Needs `viz`.
_(verified 2026-11-01, LeRobot 0.6.1, `lerobot-dataset-viz --help`)_

## 10. Replay an episode on the follower

```powershell
lerobot-replay --robot.type=so101_follower --robot.port=COM3 --robot.id=piperobot_follower `
  --dataset.repo_id=local/so101_tube_rack --dataset.episode=0
```

A quick repeatability check before training. _(verified 2026-11-01, LeRobot 0.6.1,
`lerobot-replay --help`)_. Unverified until hardware.

## 11. Train ACT locally on the GPU

Run from the venv with the CUDA torch build (with `training` added):

```powershell
lerobot-train `
  --dataset.repo_id=local/so101_tube_rack `
  --policy.type=act --policy.device=cuda `
  --policy.push_to_hub=false --wandb.enable=false `
  --output_dir=outputs/train/act_so101_tube_rack --job_name=act_so101_tube_rack
```

- **On Windows, training crashes at its first checkpoint unless symlinks are allowed.** After
  saving each checkpoint, `lerobot-train` points `checkpoints\last` at it with
  `Path.symlink_to`, uncaught. Without Developer Mode (Settings > System > For developers) or an
  elevated shell, that raises `[WinError 1314] A required privilege is not held by the client`,
  hours into a run (first save at step 20,000 by default). The checkpoint files are written just
  before, so they survive. Enable Developer Mode first (step 1), and check it with a short run
  using a small `--save_freq`. If `last` is missing, use the numbered step directory instead in the
  resume and `--policy.path` commands. _(verified 2026-11-01, LeRobot 0.6.1,
  `lerobot_train.py:703`, `common/train_utils.py`; the WinError reproduced with `Path.symlink_to`
  on the home PC from the agent's shell; confirm from a plain PowerShell window)_
- `--policy.device` and the ACT options (`--policy.chunk_size`, `--policy.n_action_steps`, ...)
  appear in `--help` only with `--policy.type=act`. _(verified 2026-11-01, LeRobot 0.6.1,
  `lerobot-train --policy.type=act --help`)_
- **`--policy.push_to_hub` defaults to `True`**; without `=false` or a `--policy.repo_id`, it
  fails with "'repo_id' argument missing. Please specify it to push the model to the hub."
  _(verified 2026-11-01, LeRobot 0.6.1, `configs/policies.py`, `configs/train.py`)_
- A local dataset is found under `$HF_HOME\lerobot\<repo_id>`, or pass `--dataset.root`.
  _(verified 2026-11-01, LeRobot 0.6.1, `lerobot-train --help`)_
- Defaults: `steps=100_000`, `batch_size=8`, `save_freq=20_000`, `num_workers=4`, `seed=1000`.
  ACT adapts to the dataset's motors and cameras. Checkpoints land in
  `<output_dir>\checkpoints\<step>\pretrained_model`, with `last` pointing at the newest.
  Resume with `--config_path=<output_dir>/checkpoints/last/pretrained_model/train_config.json
  --resume=true`. _(verified 2026-11-01, LeRobot 0.6.1, `configs/train.py`; layout and resume
  from docs/lerobot/il_robots (main))_
- ACT's defaults (chunk of 100 actions, open-loop) and the `reset()` rule are in
  [lerobot.md](lerobot.md#policies-act). Training time on the RTX 5060 Ti is unverified
  ("several hours" per the docs).

## 12. Evaluate the policy on the real arm

```powershell
lerobot-rollout --strategy.type=episodic `
  --policy.path=outputs/train/act_so101_tube_rack/checkpoints/last/pretrained_model `
  --robot.type=so101_follower --robot.port=COM3 --robot.id=piperobot_follower `
  --robot.cameras='{ front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}' `
  --dataset.repo_id=local/eval_so101_tube_rack `
  --dataset.single_task="Pick the centrifuge tube and place it in the yellow rack" `
  --dataset.num_episodes=20 --dataset.push_to_hub=false
```

- `lerobot-rollout` replaces `lerobot-record --policy.path` for deployment. Strategies: `base`
  (no recording), `sentry`, `highlight`, `episodic`, `dagger`. `episodic` mirrors
  `lerobot-record`: `num_episodes` episodes of up to `episode_time_s`, with `reset_time_s` between
  them, and the same arrow/Escape keys. With no leader connected, it holds the arm at its
  start-up pose during resets. _(verified 2026-11-01, LeRobot 0.6.1, `lerobot-rollout --help`,
  `rollout/configs.py`)_
- `--dataset.push_to_hub` defaults to `True` here too. _(verified 2026-11-01, LeRobot 0.6.1,
  `lerobot-rollout --help`)_
- **Nothing in 0.6.1 scores a real-arm episode**: success for the 20-attempt test (Phase 0) is
  judged by hand, per episode, and logged next to the simulation figure. The recorded eval
  dataset is the evidence. Write the success rule down before the first attempt (for example:
  the tube stands in the rack when the episode ends) and keep it fixed between runs you compare.
- The camera names and resolutions must match the training dataset. Unverified until hardware.

### Score the attempts and run the gate

Write one row per attempt in a CSV while the rollout runs. From Excel, save as **CSV UTF-8**:
plain "CSV" uses the Windows code page, and a note with accents then fails to read (a `;`
delimiter, a BOM and CRLF are accepted). `attempt` and `success` are required; `failure`, `scene` and
`video_url` are optional:

```csv
attempt,success,failure,scene
1,yes,,rack_left
2,no,tube dropped at the rack,rack_left
3,yes,,rack_right
```

`success` takes `yes/no`, `true/false` or `1/0`. A failure note on a success, an unknown
column, or attempts that are not exactly 1..N (a gap, a duplicate) fail with exit 2 rather than
silently dropping an attempt. Then turn it into the results contract and compare:

```powershell
uv run python -m piperobot.adapters.manual.evaluate `
  --attempts real_arm_attempts.csv --policy act_so101_tube_rack --output out/real_arm.json
uv run python -m piperobot.stats.gate --results out/real_arm.json --baseline 15/20
uv run python -m piperobot.reports.pr_comment --results out/real_arm.json --baseline 15/20 `
  --output out/real_arm_comment.md
```

`15/20` is only an example of a figure to compare against. Without `$env:PYTHONUTF8 = "1"`,
printing the comment to the console fails with `UnicodeEncodeError` (cp1252 cannot encode its
emoji); `--output` writes it to a file either way. _(verified 2026-11-01, home PC)_

Each episode's seed is its attempt number: a label, not a way to reproduce it
([ADR 0022](../decisions/0022-so101-hardware-deps-and-manual-outcomes.md)). There is no real-arm
baseline yet: compare against counts, and once a first run is accepted, store it as
`robots/so101/baselines/<policy>.json`. Keep the CSV and the eval dataset out of the git repo.

## 13. Windows gotchas

- `$env:PYTHONUTF8 = "1"`, or `--help` (and maybe other output) crashes on cp1252 (section 0).
- Ports are `COMn`; find them with `lerobot-find-port`, not by guessing (step 3).
- Camera indexes are positions in the DirectShow list and may move when USB devices change
  (step 6). LeRobot sets `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0` on Windows before importing
  OpenCV. _(verified 2026-11-01, LeRobot 0.6.1, `cameras/opencv/camera_opencv.py`)_
- Enter during calibration needs a real console (step 5); recording keys need `pynput` (step 8).
- Training needs symlink rights (Developer Mode) or it crashes at the first checkpoint (step 11).
- Without FFmpeg's shared libraries on the system, `torchcodec` cannot load and LeRobot logs a long
  "Could not load libtorchcodec" warning, then falls back to `pyav` to decode dataset videos. It
  is a warning, not an error; whether `pyav` slows training is unverified. _(verified
  2026-11-01, LeRobot 0.6.1, `utils/import_utils.py` `get_safe_default_video_backend`, home PC)_
- PowerShell: quote `--robot.cameras` in single quotes; quote values with spaces (`--dataset.single_task="..."`).
