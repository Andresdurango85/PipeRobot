# Isaac Sim, Isaac Lab and Isaac Lab-Arena

Facts from NVIDIA's docs and from the install on the home PC (native Windows 11, RTX 5060 Ti 16 GB,
driver 610.88), for the install and the GPU runner ([ADR 0020](../decisions/0020-self-hosted-gpu-runner.md)).

## Platforms

- **Isaac Sim supports Ubuntu 22.04/24.04 and Windows 11 on x86_64**; Windows 10 is not
  supported and Ubuntu 22.04 is deprecated. Recommended drivers: 595.58.03 (Linux), 595.97
  (Windows). GPUs without RT cores (A100, H100) are not supported.
  _(verified 2026-10-28, Isaac Sim docs "Requirements", last updated 2026-10-14)_
- **Isaac Sim's GPU tiers start at an RTX 4080 16 GB** (minimum), RTX 5080 16 GB (good),
  RTX PRO 6000 Blackwell 48 GB (ideal). An RTX 5060 Ti 16 GB is not listed: same VRAM as the
  minimum, less compute. _(verified 2026-10-28, same page)_
- **The Isaac Sim container is Linux only** (`nvcr.io/nvidia/isaac-sim:6.2.0`, NVIDIA Container
  Toolkit, "recommended for deployment on remote headless servers"). Headless use is
  `./runheadless.sh` with WebRTC streaming; GUI mode needs a real local display. The compose web
  viewer does not support Windows hosts, "including WSL".
  _(verified 2026-10-28, Isaac Sim docs "Container Installation")_
- **WSL2 is not a supported Isaac Sim platform.** The official requirements do not list it;
  NVIDIA staff on the developer forums say Vulkan / RTX rendering is not available there (CUDA
  works). _(verified 2026-10-28, NVIDIA developer forums, not official docs)_
- **Isaac Lab 3.0 (Release 3.0) runs on Ubuntu 22.04+ x86_64, Linux aarch64 or Windows 11
  x86_64**, Python 3.12, Isaac Sim 6.2 (5.1 and older unsupported). Its default torch is 2.11.0
  for CUDA 13.0 (`cu130` index), which needs driver ≥ 580.65.06 (Linux) or ≥ 580.88 (Windows).
  _(verified 2026-10-28, docs.nvidia.com/isaaclab installation page)_
- **Isaac Lab-Arena supports Linux only**: its README requires "Linux (Ubuntu 22.04+)" and does
  not mention Windows. `main` targets Isaac Lab 3.0.0 + Isaac Sim 6.2.0; `release/0.3.1`, the
  recommended stable branch, targets Isaac Lab 3.0.0 EA + Isaac Sim 6.1.0; Python ≥ 3.12. The
  README names Franka and Unitree G1 embodiments, not the SO-101, and evaluates policies served
  behind a server (GR00T, π0.5, custom). Its hardware needs are Isaac Sim's. Two installs:
  `./docker/run_docker.sh` (Docker, includes cuRobo reachability checks) or native
  `uv sync --extra dev` (no cuRobo); both need `OMNI_KIT_ACCEPT_EULA=YES` and `ACCEPT_EULA=Y`.
  _(verified 2026-11-01, IsaacLab-Arena README on GitHub; install methods from its quickstart
  page, 2026-10-28, which names no OS)_

## Installing on Windows

- **Isaac Sim 6.2 installs from pip**: `isaacsim[all,extscache]==6.2.0.0` from
  `https://pypi.nvidia.com`, Python 3.12, after `torch==2.11.0` from the `cu128` or `cu130`
  index, in a dedicated environment (it pins Newton, Warp, MuJoCo and others). Windows may need
  long-path support. The first `isaacsim` import asks to accept the EULA, unless
  `OMNI_KIT_ACCEPT_EULA` is `YES`, `Y` or `1`. Headless in scripts: `SimulationApp({"headless":
  True})`. The docs give no download or install size.
  _(verified 2026-11-01, Isaac Sim docs "Python Environment Installation")_
- **Isaac Lab 3.0 on Windows 11**: clone `release/3.0.0` after enabling long paths, then
  `uv run --extra isaacsim isaaclab ...` from the checkout (recommended; picks the `cu130` torch
  build), or install Isaac Sim 6.2.0.0 and torch 2.11.0 / torchvision 0.26.0 (`cu130`) into a
  venv and run `isaaclab.bat -i`. Physics backends: Newton (`physics=newton_mjwarp`, default, no
  Isaac Sim), OV PhysX (`--extra ovphysx`, no Isaac Sim), Isaac Sim PhysX
  (`physics=isaacsim_physx`, needs Isaac Sim); the `kit` visualizer needs Isaac Sim. Headless:
  `--viz none`. The first Kit launch can take over ten minutes. No disk figure is given.
  _(verified 2026-11-01, Isaac Lab installation page, Release 3.0)_
- **LeIsaac (LightwheelAI, SO-101 tasks in Isaac Lab) supports up to Isaac Sim 5.1 / Isaac Lab
  2.3.0** (Python 3.11, torch 2.7.0 `cu128`); its install steps use `apt`, and its docs name no
  OS. _(verified 2026-11-01, LeIsaac docs "Installation")_
- **NVIDIA's `so101-typing-task` is the SO-101 on an Isaac Lab 3.0.0-based runtime** (patched,
  source revision 6f991d4becf7), "Linux x86-64 only" via Docker; "Windows and ARM have not been
  validated". _(verified 2026-11-01, Isaac Lab docs, SO-101 keyboard typing page)_

## Installed on the home PC

Isaac Lab `release/3.0.0` checkout at commit `44044b0963` (the branch gets automated commits,
so the commit pins the lock), `uv sync --locked --extra isaacsim` into a venv outside this repo ([ADR 0021](../decisions/0021-isaac-lab-3-on-windows-without-arena.md)).

- **The install takes ~10 min and ~17 GB of disk**: 256 packages, download 8 min 17 s, install
  1 min 24 s; `isaacsim 6.2.0.0`, `torch 2.11.0+cu130` (CUDA 13.0). The env measures 16.4 GB and
  the uv cache grew from 5.2 to 21.6 GB, but free disk dropped only 17.1 GB: uv hardlinks the
  env's files to its cache. After the smoke tests the env is 16.9 GB; total disk used by install
  plus tests: 18.7 GB. _(verified 2026-11-01, uv 0.10.8)_
- **Kit keeps its caches inside the env**, in `site-packages/isaacsim/kit/cache` (0.47 GB after
  the smoke tests: `DerivedDataCache` 326 MB, `nv_shadercache` 141 MB), with logs in
  `isaacsim/kit/logs`. `%LOCALAPPDATA%\ov` holds only empty cache folders; telemetry and
  structured logs go to `~/.nvidia-omniverse/logs`. Deleting the env removes the caches.
  _(verified 2026-11-01)_
- **The EULA prompt is in `isaacsim/kit/kit_app.py`** (`check_eula()`, run on `import isaacsim`):
  it asks "Do you accept the EULA? (Yes/No)" and writes `isaacsim/kit/EULA_ACCEPTED` inside the
  env. With `OMNI_KIT_ACCEPT_EULA` set to `YES`, `Y` or `1` it returns early and writes nothing.
  Andrés accepted it himself on 2026-11-01. _(verified 2026-11-01, isaacsim 6.2.0.0)_
- **Isaac Lab's tutorials loop forever when headless** (`while sim.is_running()`), and Python
  buffers stdout when redirected to a file: bound the loop and set `PYTHONUNBUFFERED=1`.
  `--viz none` runs without a window. _(verified 2026-11-01, Isaac Lab 3.0.0)_
- **Headless launch and RTX camera rendering work on native Windows** (Vulkan, driver 610.88):
  an empty stage starts and stops in 5 s (500 steps in 0.30 s). The camera tutorial (2 cameras,
  640×480, RTX renderer) renders correct RGB images; its first run took 229 s (shader
  compilation), the second 17 s. It used ~4.1 GB of VRAM above the desktop's ~7.9 GB.
  _(verified 2026-11-01, Isaac Lab `scripts/tutorials/00_sim/create_empty.py` and
  `scripts/tutorials/04_sensors/run_usd_camera.py` at `44044b0963`, with their
  `while sim.is_running()` loops bounded to 500 and 30 steps)_
- **Isaac renders inside the runner's Windows service** (user `gh-runner`, session 0, no
  desktop): Kit picks Vulkan and the RTX 5060 Ti, logs no `[Error]`, and the RTX camera frame
  (640×480, cube and sphere) is pixel-identical to the same script run interactively on the
  owner's desktop, and between the cold and warm runs. Install as `gh-runner` into the runner's
  tool cache: 3 min 41 s (`uv sync --locked --extra isaacsim`), env 16.4 GB, C: free 122.0 →
  104.4 GB. Empty stage: 10.9 s. Camera: 206 s cold (launch 184 s, shader compilation), 12.7 s
  warm; +3.4–3.6 GB of VRAM. _(verified 2026-11-01, `isaac-render.yml` run 41369455668,
  `robots/so101/tools/isaac_render_check.py`)_
- **Kit fails at start when the Windows commit charge is exhausted, even with VRAM free**:
  `VkResult: ERROR_OUT_OF_DEVICE_MEMORY`, `Texture creation failed`, then `LLVM ERROR: out of
  memory`, with Git Bash forks failing on Win32 error 1455 (paging file too small). The GPU had
  ~10 GB free; free commit was 8.9 of 180 GB, because explorer.exe held 71 GB of commit (a shell
  leak) while 16.7 GB of physical RAM was still free. Before a GPU run, check
  `(Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory` as well as `nvidia-smi`.
  _(verified 2026-11-04, Isaac Sim 6.2, a camera-on framing run)_
- **Recording camera in Isaac Lab 3.0**:
  - Use `isaaclab.sensors.CameraCfg`. `TiledCamera` is a deprecated alias of `Camera`
    (`sensors/camera/tiled_camera.py`).
  - The launcher enables cameras only when the launch config contains a Kit camera
    (`app/sim_launcher.py:644-649`). Our worker builds the scene after launch, so it sets
    `enable_cameras = True` itself. That switches Kit to `isaaclab.python.headless.rendering.kit`.
  - Frames come from `sim.render()` then `camera.update(0.0, force_recompute=True)`.
    `Camera.set_world_poses_from_view(eyes, targets)` places it.
  - A camera-on re-run reproduces the camera-off episode bit for bit (same `trajectory_sha256`
    on 30/30 seeds), and costs about +20 s per 600-step episode and twice the commit (12.8-14.9
    against 6.6 GiB).
  - The light box's back wall is at world x ≈ 0.40. A camera near its `camera_mount` (top left)
    sees the rack and tubes.

  _(verified 2026-11-04, Isaac Lab `44044b0963`,
  [camera_record_check_result.json](../../robots/so101/envs/camera_record_check_result.json))_
- **Leaving `launch_simulation`'s block ends the process**: it closes Kit with the block's exit
  status (a `SystemExit(n)` raised inside is kept), so code after the `with` never runs. Write
  results and print summaries inside the block. _(verified 2026-11-01, Isaac Lab 3.0.0,
  `isaaclab/app/sim_launcher.py`)_
- **Isaac Lab 3.0 ships the SO-101**: `isaaclab_assets.robots.so101` (`SO101_CFG`, 5-DOF arm plus
  gripper, USD from the Isaac Nucleus) and tasks `IsaacContrib-Stack-Cube-SO101-v0`,
  `-IK-Abs-v0`, `-Joint-Teleop-v0` and `IsaacContrib-Keyboard-SO101`. `Stack-Cube-SO101-v0` uses
  PhysX on `cuda:0`, actions of shape (envs, 6) and an 89-value observation; 4 envs × 300 steps
  of random actions take ~11.3 s, the env is ready in ~6 s warm (51 s on the first run), and it
  uses ~1.35 GB of VRAM. _(verified 2026-11-01, Isaac Lab 3.0.0)_
- **Same seed, same SO-101 episode, bit for bit**: two runs of `Stack-Cube-SO101-v0` (seed 1000,
  4 envs, 300 steps of seeded random actions on CUDA) gave identical observations, with and
  without determinism settings (torch deterministic algorithms, PhysX
  `enable_enhanced_determinism`, launcher `--deterministic`); seed 1001 differs (max |Δ| 134.5).
  Proprioceptive observations only, no camera and no learned policy in the loop, so this does
  not yet make a CUDA gate reproducible. Re-run it with
  [`robots/so101/tools/isaac_seed_check.py`](../../robots/so101/tools/isaac_seed_check.py).
  _(verified 2026-11-01, home PC)_
- **`configure_seed()` turns `cudnn.benchmark` back on**: Isaac Lab envs call it on construction
  and on `reset(seed=...)`, and without `torch_deterministic=True` it sets
  `torch.backends.cudnn.benchmark = True`. Apply deterministic torch settings after both. The
  launcher's own `--deterministic` flag only requests reproducible rendering.
  _(verified 2026-11-01, `isaaclab/utils/seed.py`, `isaaclab_physx/app/kit_launcher.py`)_
- **`resolve_task_config()` re-parses `sys.argv` with Hydra**: a script with its own argparse
  must strip its arguments (`sys.argv = sys.argv[:1]`) before calling it.
  _(verified 2026-11-01, Isaac Lab 3.0.0)_
- **`uv pip install` applies the `[tool.uv]` overrides of the project in the current
  directory**: from the Isaac Lab checkout, `uv pip install "lerobot[pusht]==0.6.1"` keeps numpy
  (2.5.1), packaging (26.0) and pillow (12.3.0); a dry run from this repo's checkout, under this
  repo's overrides, proposed numpy 2.2.6, packaging 25.0 and pillow 13.0.0. Add packages to the
  Isaac env only from the Isaac Lab checkout. _(verified 2026-11-01, uv 0.10.8)_
- **LeRobot 0.6.1 imports and runs a randomly initialised ACT inside the Isaac Lab env**, in the
  same process as Isaac, installed as above. `uv pip check` then reports LeRobot's caps as broken (`numpy<2.3`,
  `packaging<26`, `datasets`' `fsspec<=2026.2.0`), as it already does for Isaac Sim's own pins.
  Even so, `ACTPolicy(cfg).select_action()` ran on CUDA next to Isaac, and the simulation output
  stayed bit-identical to the clean env. Not tested: anything that uses `datasets`/`fsspec`,
  video writing. Tested in a throwaway copy of the env, then deleted.
  _(verified 2026-11-01, LeRobot 0.6.1)_
- **A real LeRobot ACT checkpoint loads with its processors inside a running Isaac Lab process**:
  `samarth-shukla6/act-svla-so101-pickplace` (Apache-2.0, revision `c903979a9d`, state 6, two
  480×640 cameras `up` and `side`, chunk 100) via `ACTPolicy.from_pretrained` and
  `make_pre_post_processors(..., pretrained_path=..., pretrained_revision=...,
  preprocessor_overrides={"device_processor": {"device": "cuda"}})`, in 21.7 s including the
  download. Pre-processor: rename, add batch dim, device, normalizer (stats for state, action and
  both cameras); post-processor: unnormalizer, device (back to CPU). One `select_action` on CUDA
  gave a finite (1, 6) action in the dataset's units, identical on a second call after
  `policy.reset()`, and the seeded simulation stayed bit-identical to the clean env. The inputs
  were Isaac joint positions and random images, so this tests loading and plumbing, not behaviour;
  Isaac reports joints in radians, and the evaluator must convert them to the units the
  checkpoint was trained on. _(verified 2026-11-01, LeRobot 0.6.1, throwaway copy of the Isaac
  env, then deleted)_

## NVIDIA's SO-101 course

- **"Train an SO-101 Robot From Sim-to-Real With NVIDIA Isaac" pins Isaac Sim 5.1.0, Isaac Lab
  2.3.0, LeRobot 0.4.3 and GR00T N1.6**, and needs "a computer with Docker and an NVIDIA GPU (Ada
  or Blackwell architecture)". These are older than what Arena (Isaac Sim 6.0.1) and this repo
  (LeRobot 0.6.1) use. _(verified 2026-10-28, course page "Get the Code and Models")_
- **Its simulation evaluation runs in two Docker containers**: a GR00T policy server and the
  Isaac simulator client, `lerobot_eval --task Lerobot-So101-Teleop-Vials-To-Rack-Eval ...`
  (`--headless` instead of `--rerun` disables the UI). It assumes a Linux desktop (`xhost`, X11
  socket mounts, `--gpus all`, `--privileged`) and does not use Isaac Lab-Arena. This
  `lerobot_eval` is the course's own CLI, not LeRobot 0.6.1's `lerobot-eval`. It prints a live
  success rate; no fixed episode count. _(verified 2026-10-28, course page "Sim Evaluation")_
- **The course's code is `isaac-sim/Sim-to-Real-SO-101-Workshop`** (Apache-2.0): Isaac Lab
  tasks such as `Lerobot-So101-Teleop-Vials-To-Rack` in `source/sim_to_real_so101`, tested on
  "Ubuntu Linux >22.04", set up only through Docker (`docker/sim/Dockerfile`).
  _(verified 2026-11-01, repository README)_
- **The course repository's public history starts on 2026-04-16** (initial commit `d327be4`, 5
  commits by `ce807d9`), but its training dataset `sreetz-nv/so101_teleop_vials_rack_left` was
  created on 2026-01-26. The dataset was recorded with code older than anything published, so
  the published code shows how the course replays and evaluates that data, not how it was
  recorded. _(verified 2026-11-02, GitHub commits API and the Hub dataset API)_
- **Licences of what we port.** The repository is Apache-2.0. Its `THIRD_PARTY_NOTICES` does not
  list the USD assets (robot, tubes, rack, mat, light box), so the repository's Apache-2.0
  applies to them; the 24 HDRIs are CC0 (Poly Haven, `assets/hdri/LICENCE`). Files ported into
  this repo keep the course's SPDX header and name the source commit:
  `robots/so101/envs/joint_units.py` (from `utils/lerobot_interface.py`), and the scene facts in
  `robots/so101/envs/vials_to_rack.json` (from `assets/so101.py`,
  `tasks/vials_to_rack_env_cfg.py`, `tasks/task_env_cfg.py`), all at
  `ce807d99724cb65671abec01f908a2fcb4a6eab7`. Asset binaries are never committed.
  _(verified 2026-11-02)_

## SO-101 course demos on the Isaac Lab 3.0 asset

The object-free go/no-go of [ADR 0024](../decisions/0024-so101-demo-replay-go-no-go-and-control-rate.md).

- **The course's training dataset holds no object poses**: `observation.state`, `action`, two
  videos (`ego`, `external_D455`, 640×480) and indices; 75 episodes, 18250 frames, LeRobot v3.0,
  revision `69802873f4a26bffb716fca1f4fb1bb0e3d2a07a`. The course randomizes the rack and tubes
  on every reset, so a demo cannot be replayed into its own scene.
  _(verified 2026-11-02, `meta/info.json`)_
- **Its joint values are LeRobot units, not degrees**: arm joints in -100..100 (wrist_flex
  reaches -100.0 exactly), gripper 0..100 (0.5..58.7). The course converts them with a per-joint
  degree table that belongs to its own robot USD; that table is now
  `robots/so101/envs/joint_units.json`. _(verified 2026-11-02, `meta/stats.json`,
  `utils/lerobot_interface.py`)_
- **The metadata says 30 fps, the published course code runs it at 60 Hz.** The recorder
  (`scripts/lerobot_agent.py`, `utils/lerobot_recorder.py`) writes one frame per `env.step` with
  no subsampling, and `env.step` is physics dt 1/120 × decimation 2 = 1/60 s; the course's
  evaluation also gives one action per `env.step`, with a 450/60 s timeout. 243 frames per
  episode is 4.05 s at 60 Hz, 8.1 s at 30 Hz. The dataset predates the public code (above); the
  matched-gains replay below measured 60 Hz. _(verified 2026-11-02, course code at `ce807d9`)_
- **The tube in the jaw shows in the recorded data**: while holding, the gripper state stays
  5+ units above the commanded gripper (median gap 15.7). A run of 15+ frames with that gap
  finds a hold in all 75 episodes (72 with one, 3 with a regrasp); the first hold starts the
  grasp, the end of the last one is the release. An absolute "gripper closed" threshold does not
  work: operators close to anywhere between 1 and 13. _(verified 2026-11-02)_
- **The Isaac Lab 3.0 SO-101 asset** (`so101_new_calib_SysID`, variant `Physics=physx`) has
  bodies `base, shoulder, upper_arm, lower_arm, wrist, gripper, moving_jaw_so101_v1` and hard
  limits (degrees) pan ±110, lift ±100, elbow ±96.8, wrist_flex ±95, wrist_roll -157.2..162.8,
  gripper -10..100: the course table except elbow ([-100, 90]) and wrist_roll (±160). Its
  tool-centre point is the URDF's `gripper_frame_link`, (-0.0079, -0.0002, -0.0981) m from the
  `gripper` body (TheRobotStudio/SO-ARM100 `a758567`). _(verified 2026-11-02, Isaac Lab 3.0)_
- **Replaying the 75 demos on it, object-free** (`isaac_demo_replay.py`, robot at the course's
  base pose): all 75 grasps land in the course's tube region and all 75 releases over its rack
  region, at both rates; no target leaves the joint limits. Joint tracking against the recorded
  states (LeRobot units, pooled arm p95): 5.55 at 60 Hz (wrist_flex p95 10.0, max 19.1; fails
  the pre-set bar) and 1.71 at 30 Hz (passes). The pre-registered verdict is GO at 30 Hz, but a
  slower replay of the same targets always tracks better when the asset's gains differ from the
  recording robot's, so this comparison cannot tell the rate; it shows that the asset's SysID
  gains lag the course robot's at 60 Hz. Without rendering, 18250 frames take 155 s at 2
  substeps and 303 s at 4. _(verified 2026-11-02, RTX 5060 Ti, branch
  `feat/so101-replay-gonogo`)_
- **The asset's USD gains are not the course's.** Read back after spawning (stiffness /
  damping, effort limit): pan 48.4 / 3.34, lift 47.8 / 2.56, elbow 14.7 / 0.34, wrist_flex
  43.6 / 4.14, wrist_roll 54.9 / 2.97, gripper 68.3 / 2.82, all 3.35 N·m. The course's
  (`assets/so101.py`): 55 / 0.7, 30 / 0.8, 25 / 0.7, 12 / 0.5, 7 / 0.5, 4 / 0.3, all 30 N·m, with
  32 solver position iterations (the asset uses 8). Overriding them is a per-joint
  `ImplicitActuatorCfg(stiffness, damping, joint_effort_limit)` and a
  `PhysxArticulationCfg` in `spawn.articulation_props`; the read-back values confirm it takes
  effect. _(verified 2026-11-02, Isaac Lab 3.0, `robot.data.joint_stiffness` etc.)_
- **With the course's gains, the 3.0 asset reproduces the recording at 60 Hz** (diagnostic,
  [ADR 0024](../decisions/0024-so101-demo-replay-go-no-go-and-control-rate.md)): pooled arm p95
  0.71 LeRobot units, best-fit action-to-state lag 1.30 frames against the dataset's own 1.34,
  recorded-vs-simulated shift 0.01 frames. At 30 Hz it runs ahead: p95 2.72, lag 0.47, shift
  +0.91. With the USD gains at 60 Hz the lag is 2.95 frames. Two articulations in one stage
  changed the USD-gain p95 slightly (5.50 / 1.67 against 5.55 / 1.71 alone).
  _(verified 2026-11-02, RTX 5060 Ti)_
- **The course's robot USD is Isaac Lab 3.0's `so101_new_calib` with renamed joints**
  (`Rotation, Pitch, Elbow, Wrist_Pitch, Wrist_Roll, Jaw`; default prim `/so101_new_calib`), its
  own gains and the course's joint limits. Spawned side by side at the course pose and set to the
  recorded states of the 75 grasp and 75 release frames, the `gripper` and jaw body origins agree
  within 0.1 mm, the moving jaw's lowest collision point within ±7 mm, and both feet (lowest base
  collision point) sit at z = +0.030 with the root at z = 0. So the 3.0 asset mounts at the
  course pose (-0.05, 0, 0), yaw 90°, with no height correction. The fixed jaw's lowest point
  differs by up to 3 cm at release because the two USDs carry different collision meshes for that
  body (143k vs 57k points) and the lowest vertex jumps between them; it is not a kinematic
  difference. `robots/so101/tools/isaac_mount_compare.py`.
  _(verified 2026-11-02, Isaac Lab 3.0, course USD sha256 `11f5f0bb…991006`)_
- **The asset's SysID gains sag under gravity.** Kinematically, from the recorded states, the fixed
  jaw's lowest point at grasp is at z = 0.034 m (median), on the mat (top ≈ 0.035); replaying the
  actions with the USD gains put the TCP 2 mm lower at the median and 14 mm lower at p5 (0.027),
  because the 3.35 N·m effort limit cannot hold the arm. _(verified 2026-11-02)_
- **An articulation without `fix_root_link=True` whose base intersects a ground plane explodes:**
  the course USD spawned that way read its foot at z = -0.068 after one step, and its body
  positions then went to ~1e8 m, silently (no error). Spawn it with
  `UsdFileCfg(fix_root_link=True)` and, for kinematic comparisons, no ground plane and gravity
  off. _(verified 2026-11-02, Isaac Lab 3.0)_

## SO-101 tube-to-rack scene in Isaac Lab 3.0

Scene, checks and decisions: [ADR 0028](../decisions/0028-so101-scene-gains-and-mount.md).

- **The course's scene needs four files and no local dependencies**: `lightbox-simple.usd`,
  `mat.usda`, `Vial_opaque.usda`, `Vial_rack_simple.usda` (~3.5 MB; the `tex/*.png` in the repo
  are unused). Remote references stay unresolved: the light box's camera mount payload
  `rsd455.usd` on an Isaac **5.1** Nucleus path, and MDL materials (render only). Stage load rules
  (`Usd.StageLoadRules.NoneRule` on `LightBox/camera_mount/rsd455`) installed before spawning keep
  Kit from fetching the payload. `fetch_course_assets.py` gets them by sha256 into
  `%LOCALAPPDATA%\piperobot\course-assets\<commit>`. _(verified 2026-11-02, course `ce807d9`)_
- **The course has no ground plane**: the light box's `Base` mesh is the floor, and it collides.
  The rack (spawned at z 0.06) settles at z = 0.041 on the mat; tubes spawned lying at z 0.05
  settle at 0.050. _(verified 2026-11-02, Isaac Lab 3.0)_
- **Geometry**: the rack's origin is a corner, footprint [0, 0.12]² in its frame, top surface at
  rack-local z = 0.073, four slot centres at (0.03/0.09, 0.03/0.09); a tube dropped over a slot
  goes in and rests with its bottom at rack-local z = -0.001. The tube's origin is 1.7 cm above
  one end (extent -0.017 to +0.0995 m along its axis), radius 1.7 cm. _(verified 2026-11-02)_
- **The course's success test accepts tubes that are not in a slot**: a tube lying on the rack
  top has origin z 0.089 < 0.1 (only the vertical test rejects it), and a tube standing upright on
  the rim or leaning on it at up to ~45° passes the footprint, height and vertical tests. Our
  tracker adds a slot-depth rule (lowest end below rim - 2 cm). _(verified 2026-11-02, checks
  S4, S7, S7b)_
- **Jaw contact forces (`force_matrix_w`, moving jaw filtered on the tubes, PhysX 6.2 includes
  friction)**: open jaw approaching a tube at most 0.61 N; closing jaw pushing a tube it does not
  hold up to 1.98 N; genuine grasps 10–19 N per-episode median. The course's 2 N threshold is at
  the push level; we use 5 N. _(verified 2026-11-02, 75 reconstructed demos, course gains)_
- **Reconstructed demos end to end** (tube under each demo's grasp TCP, rack with a slot under
  its release TCP, replay at 60 Hz): 11/75 succeed with the course's gains, 1–2/75 with the
  asset's SysID gains (21–27 episodes grasp but cannot place: sag). Most failures are `no_grasp`
  because the dataset does not say where along the tube the operator grasped (we assume
  mid-length). _(verified 2026-11-02)_
- **Replays with contacts are repeatable for a fixed episode order, but an episode's outcome
  depends on the episodes run before it in the same process**: 3 runs of the 75 reconstructed
  demos in one process are bit-identical (trajectory fingerprints), on GPU and on CPU physics;
  the same list in reverse order changes 12/75 outcomes and 50/75 fingerprints. Neither
  `PhysxCfg.enable_enhanced_determinism` nor `sim.reset(soft=False)` + `scene.reset()` before
  each episode changes a single bit, so neither removes it; the carried state is unknown. One
  fresh process per episode is order-free and repeatable. ADR 0028's "2/75 run to run" came from
  different predecessors (S7b's setup changed between the runs). CPU physics changes 23/75
  outcomes against GPU; one process per episode changes 20/75 against one process for all.
  _(verified 2026-11-03, Isaac Lab 3.0 / PhysX 6.2, [ADR 0033](../decisions/0033-so101-isaac-evaluator-one-process-per-seed.md))_
- **Kit's shutdown can hang**: `SimulationApp.close()` → `app.shutdown()` deadlocked once in 87
  worker processes; Isaac Sim documents it (NVBug 5948099) and arms a 120 s faulthandler
  watchdog that then exits with 1. Our worker writes, fsyncs and re-reads its result, then calls
  `os._exit(0)`; that changed no fingerprint and no startup time.
  _(verified 2026-11-03, Isaac Sim 6.2, `simulation_app.py`)_
- **One Isaac process per episode costs ~20 s** (Kit startup plus a ~6 s episode) on the RTX 5060
  Ti; a worker peaks at ~2.9 GB of GPU memory. On Windows (WDDM) `nvidia-smi` gives no
  per-process memory: measure the total against the idle desktop load (~9.9 GB here).
  _(verified 2026-11-03)_
- **Two Isaac workers at once give the same results as one** (`evaluate --workers 2`):
  registered test, 125 seeds (replay 0-74, scripted dev 200000-200049), 0 outcome flips and
  every `trajectory_sha256` identical
  ([result](../../robots/so101/envs/workers_acceptance_result.json)). On the scripted policy one
  worker takes 27.5 s per seed, two take 16.4 s (1.68×; each process slows from 27.4 to 32.1 s).
  GPU memory above the idle desktop: 3379 MB peak with one worker, ~5.37 GB with two, so the
  gate budgets 4352 MB per worker (peak + 25%). Kit's per-second log names did not collide with
  launches 3 s apart. **More than two is not safe on 64 GB of RAM**: an accidental run with up
  to 4 processes kept the same outcomes and hashes but hit three host-memory failures (a
  timeout, a `MemoryError` in warp, PhysX "failed to allocate pinned host buffers"); with two,
  free RAM stayed above ~10 GB. _(verified 2026-11-03, Isaac Sim 6.2, Isaac Lab 3.0, RTX 5060 Ti)_
- **Evaluator inputs live under one cache root**: `PIPEROBOT_CACHE`, else
  `%LOCALAPPDATA%\piperobot` (XDG cache on Linux). `robots/so101/tools/prepare_caches.py` (repo
  env, `uv sync --group so101-data`) fills and verifies it by sha256: the course's assets under
  `course-assets/<commit>/` and the replay policy's `datasets/<repo>/<revision>/episodes.json`;
  a second run does no network I/O. `episodes.json` is written as LF bytes on every platform; the
  first pin (`ae786b9c…`) was a Windows CRLF file extracted before `control_hz` was recorded,
  with episodes identical to today's (`273e1823…`). A replay seed through the new root matches
  the acceptance run's fingerprint. _(verified 2026-11-03)_
- **SO-101 kinematics for scripted control**: shoulder_lift, elbow_flex and wrist_flex have
  parallel axes, so the gripper's pitch is their sum; the course demos hold it steady (1.025 rad
  at grasp, -0.172 at release). The open jaws are not centred on the course's TCP (gripper body
  + `tcp.offset_m`): a grasp aimed at the tube's axis lands the fixed jaw on the tube, 2 cm across
  and 8 mm below works. Position IK on the course's low gains must integrate on the previous
  joint target (gravity holds the measured joints short) with a gain and a lead limit (0.2,
  0.25 rad), or it stalls or winds up. Isaac Lab 3.0: `robot.data.body_link_jacobian_w` (fixed
  base: Jacobian index = body index - 1), `DifferentialIKController(command_type="position",
  ik_method="dls")`, `data.joint_pos_target` (deprecated, works).
  _(verified 2026-11-03, [ADR 0034](../decisions/0034-so101-scripted-privileged-state-policy.md))_
- **Teleporting an object relative to another one must use the other one's settled pose**, not
  its configured initial pose: the rack drops 1.9 cm from its spawn height, which made check S7b
  hold a tube 1.9 cm too high on its first run. _(verified 2026-11-02)_
- **Cost**: Kit launch plus the static checks take under 1 min, and the 75 reconstructed demos
  (no rendering) ~7.5 min, on the RTX 5060 Ti. _(verified 2026-11-02)_

## Reinforcement learning (crab RL track)

[ADR 0043](../decisions/0043-reinforcement-learning-track-for-the-crab.md). The crab's own
tasks, commands and results live in its private repo; general Isaac Lab RL facts go here.

- **Isaac Lab 3.0 has one RL entry point for every library**:
  `scripts/reinforcement_learning/train.py` (and `play.py`, `train_multigpu.py`) calls
  `isaaclab_rl.entrypoints.run_train_cli`. Per-library backends sit in
  `isaaclab_rl/entrypoints/backends/` (`train_rsl_rl.py`, `train_skrl.py`, `train_rl_games.py`,
  `train_sb3.py`, `train_torchrl.py`, `train_rlinf.py`). The per-library
  `scripts/reinforcement_learning/rsl_rl/` folders of older tutorials do not exist in 3.0.
  _(verified 2026-11-07 in the clone at `release/3.0.0` `44044b0963`)_
- **`rsl-rl-lib` 5.5.1 is already in the home PC's Isaac Lab 3.0 environment**: it came with
  the environment's install on 2026-11-01. The entry points require at least 5.0.1
  (`RSL_RL_MIN_VERSION` in `isaaclab_rl/rsl_rl/utils.py`). _(verified 2026-11-07)_
- **A verified `rsl_rl` training command on native Windows** (PPO, Isaac Lab's Franka reach
  reference task), run from a scratch directory with the Isaac Lab 3.0 venv's Python:

  ```
  PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 <isaaclab-venv>/Scripts/python.exe \
    <IsaacLab clone>/scripts/reinforcement_learning/train.py --rl_library rsl_rl \
    --task Isaac-Reach-Franka --num_envs 2048 --max_iterations 200 --seed 1 \
    --run_timestamp <name> --viz none presets=hold
  ```

  - Checkpoints land in `<cwd>/logs/rsl_rl/<experiment>/<run_timestamp>/model_<n>.pt`.
  - `--rl_library` picks the backend.
  - Task ids in 3.0 have no `-v0` suffix (`Isaac-Reach-Franka`, `Isaac-Lift-Franka`).
  - Presets are Hydra tokens on the command line (`presets=hold`), not flags.

  Versions: isaacsim 6.2.0.0, isaaclab 28.0.1, isaaclab_rl 1.5.1, isaaclab_tasks 25.2.0 (clone
  `release/3.0.0` at `44044b0963`), rsl-rl-lib 5.5.1, torch 2.11.0+cu130, warp-lang 1.17.0;
  tensorboard 2.21.0 is already in the venv. _(verified 2026-11-07, RTX 5060 Ti 16 GB, driver
  610.88, Windows 11)_
- **`PYTHONIOENCODING=utf-8` is required when training output goes to a file on Windows.** Isaac
  Lab prints non-ASCII characters, and Python's default cp1252 stdout dies with
  `UnicodeEncodeError` about 13 s in. _(verified 2026-11-07)_
- **`nvidia-smi --query-compute-apps` shows `used_memory` as `[N/A]` per process on Windows**
  (WDDM driver model). Measure the GPU's total used and free memory instead
  (`nvidia-smi --query-gpu=memory.used,memory.free`). _(verified 2026-11-07, driver 610.88)_
- **Startup and the first iteration are slow**: about 25–60 s from launch to the first
  iteration, and the first iteration includes about 30–66 s of kernel warm-up. Time-box jobs
  with that overhead included. _(verified 2026-11-07)_
- **`play.py --video` must not be combined with `--viz none`.** Without `--viz`, `play.py`
  creates a headless Kit visualizer by itself. _(verified 2026-11-07)_
- **`--video` (in `play.py` or `train.py`) needs the Isaac Lab clone's `video` extra**, or it
  dies at launch with `ModuleNotFoundError`. That extra is moviepy 1.0.3 and imageio-ffmpeg 0.6.0,
  the versions in the clone's `uv.lock`. Install them from the clone, so its `[tool.uv]`
  overrides apply:
  `uv pip install --python <isaaclab-venv>/Scripts/python.exe "moviepy==1.0.3" "imageio-ffmpeg==0.6.0"`.
  It also pulls in proglog 0.1.12. `uv pip check` on that venv lists 6 version mismatches that
  were there before and are unrelated:
  - numpy 2.5.1 against isaacsim-kernel's 2.3.1 and numba's `<2.5`;
  - fsspec, pywin32 and urllib3;
  - a missing onnxruntime-gpu.

  _(verified 2026-11-07)_
- **Evaluating an `rsl_rl` inference policy: call `env.reset()` inside `torch.inference_mode()`
  too**, not only the policy step. Otherwise the second episode's reset raises "Inplace update
  to inference tensor outside InferenceMode" (from the command metrics). _(verified 2026-11-07)_
- **RL cost on the RTX 5060 Ti 16 GB** (seed 1, desktop apps closed, ~12.5 GB VRAM free at
  rest):

  | Task | Envs | s / iteration | Wall | Min free VRAM | Min free commit |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | Reach-Franka, 200 iterations | 512 | 0.70 | 230 s | 12.3 GB | ~63–64 GB |
  | Reach-Franka, 200 iterations | 1024 | 0.73 | 171 s | 12.2 GB | ~63–64 GB |
  | Reach-Franka, 200 iterations | 2048 | 0.73 | 175 s | 12.0 GB | ~63–64 GB |
  | Lift-Franka, 40 iterations | 1024 | 1.14 | 118 s | 11.1 GB | ~62 GB |
  | Lift-Franka, 40 iterations | 2048 | 1.39 | 81 s | 10.3 GB | ~62 GB |

  Reach's time per iteration stays flat from 512 to 2048 envs: at that size it is bound by CPU
  and Python, not the GPU, so more envs give more samples for free. A job at these sizes adds
  about 0.5–2.2 GB of VRAM and ~2 GB of commit charge.

  At 4096 envs, the tasks' default:
  - Reach: 100 iterations in 1 min 40 s, startup included;
  - Lift: 1.7 s per iteration, using about 3.9 GB of VRAM, with 8.5 GB still free.

  Both leave the 5 GB below, so the weekend runs use 4096 envs.

  The SO-101 gate can start while a training job is running ([ADR
  0043](../decisions/0043-reinforcement-learning-track-for-the-crab.md): no preemption), so the
  job's own footprint must leave at least 5 GB of VRAM free for one gate worker. The gate's
  Isaac process alone took +3.4–3.6 GB in the render check above. The queue runner starts a
  job only with at least 7 GB of VRAM and 16 GB of commit free. _(verified 2026-11-07)_

### Evaluating the reference tasks (verified 2026-11-08)

Facts from the RL weekend's reference runs on Isaac Lab's public Franka tasks. They feed
[ADR 0044](../decisions/0044-gate-trained-policies-against-a-spec-with-checked-repeatability.md).
Source paths are relative to `source/` in the clone at `release/3.0.0` `44044b0963`.

- **Reach's `hold` preset pays its success reward inside a 5 cm / 0.2 rad band.** `hold` removes
  the success termination and adds `pose_command_success` as a reward, weight 10
  (`isaaclab_tasks/core/reach/config/franka/franka_reach_env_cfg.py:242-246`), with thresholds of
  0.05 m and 0.2 rad (`isaaclab_tasks/core/reach/reach_env_cfg.py:112-113`).
  - Inside that band, the only pull toward finer precision is position tracking (weight -0.2).
  - Override the band with the Hydra token
    `env.commands.ee_pose.position_success_threshold=<m>`, placed after `presets=hold`.
- **`hold`'s penalty profile depends on the physics backend**
  (`franka_reach_env_cfg.py:248-258`).
  - Newton keeps the task's `action_rate` curriculum, which ends at -0.005.
  - The PhysX aliases use `action_rate` -0.01 and a curriculum weight of -0.5, 100 times larger.
  - Results are comparable only on the same backend.
- **Lift trains under an ADR curriculum that scales gravity.** The `gravity_adr` term interpolates
  gravity from (0, 0, 0) to (0, 0, -9.81) m/s² with the difficulty level
  (`isaaclab_tasks/core/lift/adr_curriculum.py:126-137`). It also scales the out-of-bound floor
  and observation noise.
  - `play_mode()` sets `init_difficulty` to `max_difficulty`
    (`isaaclab_tasks/core/lift/lift_env_cfg.py:579-580`), so evaluating in play mode runs at full
    gravity.
  - 6000 iterations at 4096 envs reached a difficulty of only 0.86-0.89.
- **Lift's training `Metrics/success_rate` is not a task-success measure.**
  - It counts an episode once the object is *ever* within the threshold.
  - The goal resamples every 4-6 s (`lift_env_cfg.py:159`).
  - Starts come from a success-monitored reset bank aimed at 50% success (`lift_env_cfg.py:321`,
    `:415`).
  - Training read 0.89-0.91 on three seeds while a fixed-goal, end-of-episode evaluation at full
    gravity scored 3, 15 and 2 of 100.
  - In play mode the bank stays on, with 32 states per group (`lift_env_cfg.py:575-578`), so one
    process's episodes are coupled.
- **Repeatability on `newton_mjwarp` depends on contacts.** Newton's default is
  `deterministic_mode="not_guaranteed"`
  (`isaaclab_newton/isaaclab_newton/physics/newton_manager_cfg.py:190`).
  - Reach, with no contacts, re-evaluated in a fresh process bit-identically: 100 of 100 outcomes
    and final-state digests matched.
  - Lift, with contacts, did not. Three processes on the same checkpoint and seeds scored 3, 3
    and 6 of 100, and 0-1 of 100 final-state digests matched.
  - `deterministic_mode="run_to_run"` orders contacts deterministically, at a memory and speed
    cost. Untested here.
- **Video from a custom task: put the camera in `sim.visualizer_cfgs`.**
  `sim.default_visualizer_cfg` is only a hint, and "does not add a visualizer"
  (`isaaclab/isaaclab/sim/simulation_cfg.py:143-146`). A task that sets only that captured no
  frames. A `KitVisualizerCfg(headless=True, ...)` in `sim.visualizer_cfgs` works, and
  `--viz none` still disables it for training.
- **Costs on the RTX 5060 Ti 16 GB, 4096 envs:**

  | Job | Wall time |
  | --- | --- |
  | Reach-Franka (`hold`), 1500 iterations | 20-24 min |
  | Lift-Franka, 6000 iterations | about 3 h 05 min |
  | Evaluating 100 episodes, one env: Reach | 6.4-6.9 min |
  | Evaluating 100 episodes, one env: Lift | 9-10.4 min |
