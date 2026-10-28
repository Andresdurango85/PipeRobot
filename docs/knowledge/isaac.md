# Isaac Sim, Isaac Lab and Isaac Lab-Arena

Nothing is installed yet; these are facts read from NVIDIA's current docs, to plan the install
and the GPU runner ([ADR 0020](../decisions/0020-self-hosted-gpu-runner.md)).

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
- **Isaac Lab-Arena (`main` docs) runs on Isaac Sim 6.0.1 and Isaac Lab 3.0.0** and names no OS;
  its hardware needs are Isaac Sim's. Two installs: `./docker/run_docker.sh` (Docker, includes
  cuRobo reachability checks) or native `uv sync --extra dev` (no cuRobo). Both need
  `OMNI_KIT_ACCEPT_EULA=YES` and `ACCEPT_EULA=Y`. Whether the native install works on Windows is
  unverified. _(verified 2026-10-28, IsaacLab-Arena docs, quickstart/installation)_

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
