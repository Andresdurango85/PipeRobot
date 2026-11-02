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
