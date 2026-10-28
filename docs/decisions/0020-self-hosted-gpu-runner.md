# 0020. A self-hosted GPU runner on the home PC, native Windows, trusted code only

- Status: Proposed
- Date: 2026-10-28

## Context

Phase 0 asks for a GitHub Actions workflow on a GPU runner, headless, in under 30 min per PR.
`pr-gate` meets it on CPU only ([0017](0017-pr-gate-pusht-on-github-runners.md)); the GPU runner
was deferred to its own security ADR. The home PC has the GPU
([0005](0005-two-machine-setup.md)): RTX 5060 Ti 16 GB (Blackwell), Windows 11, 64 GB RAM, with
WSL2 (Ubuntu) and Docker Desktop installed. Its system drive has ~35 GB free.

Where the runner's OS must be is decided by Isaac, its real user. Verified on 2026-10-28
([isaac.md](../knowledge/isaac.md)):

- Isaac Sim 6.x and Isaac Lab 3.0 support Windows 11 and Ubuntu natively. The Isaac Sim
  container is Linux only.
- WSL2 is not a supported Isaac Sim platform (no Vulkan / RTX rendering there, per NVIDIA staff
  on the forums). Our policies need camera images, so rendering is required: WSL2 is ruled out.
- Isaac Lab-Arena's docs name no OS: Docker (Linux) or a native `uv` install. NVIDIA's SO-101
  course runs its simulation evaluation in Docker on a Linux desktop (X11, `--gpus all`), with
  Isaac Sim 5.1, Isaac Lab 2.3 and LeRobot 0.4.3, not the versions Arena or this repo pin.
- The RTX 5060 Ti is below Isaac Sim's named minimum (RTX 4080 16 GB); VRAM matches.

The security forces:

- GitHub: self-hosted runners "should almost never be used for public repositories", because any
  user can open a pull request and compromise the environment. Ephemeral runners are only a
  partial mitigation.
- A `pull_request` workflow runs the workflow files of the PR head. A fork PR can add a job with
  `runs-on` set to our runner's labels; a job-level `if` in our own workflow does not stop it.
  Only the repo setting "approval for fork pull request workflows" does. It is currently
  `first_time_contributors`, which lets anyone with one merged PR run workflows unapproved.
  `pull_request_target` workflows ignore that setting.
- This PC also holds Andrés's employer accounts (git, `gh`, credential manager). A job that can
  read his user profile could reach them, which [AGENTS.md](../../AGENTS.md) forbids outright.
- On Windows, `--ephemeral` de-registers the runner after one job; re-registering needs a token
  with admin rights on the repo stored on the same machine.

## Decision

- **Platform: native Windows 11**, the only platform on this PC where both CUDA torch (verified)
  and Isaac Sim are supported. Revisit with a new ADR if Isaac Lab-Arena or the SO-101 tasks do
  not run natively on Windows, or if headless rendering fails in a Windows service; the
  alternative then is a dual-boot Ubuntu 24.04 with Docker.
- **Isolation**: the runner runs as a Windows service under a dedicated local standard user
  (`gh-runner`), not an administrator, with no access to Andrés's profile, credential manager or
  `gh` config. Its work and tool-cache directories live outside any user's profile. No secrets are
  given to it or stored for it.
- **Scope**: registered on this repository only, with the labels `self-hosted`, `Windows`, `X64`
  and the custom label `gpu`. Workflows target `[self-hosted, Windows, gpu]`, never bare
  `self-hosted`.
- **Trusted code only**:
  - The repo's fork approval setting becomes "Require approval for all external contributors".
    Andrés reads `.github/` changes in a fork PR before approving it.
  - GPU workflows use `pull_request` and `workflow_dispatch`, never `pull_request_target`; jobs
    run only if the PR comes from this repo and not from Dependabot
    (`github.event.pull_request.head.repo.full_name == github.repository &&
    github.actor != 'dependabot[bot]'`); `permissions: contents: read`; no secrets.
- **Persistent, not ephemeral, for now**: re-registration would put an admin token on the same
  machine, a larger risk than a persistent runner that only executes the owner's code. The
  checkout is cleaned on every job. Ephemeral or just-in-time runners come with a Linux container
  setup if the runner ever has to serve untrusted code.
- **Not a required check** while CUDA evaluation is not reproducible
  ([lerobot.md](../knowledge/lerobot.md)): a separate workflow, `gpu-smoke.yml`, checks
  `nvidia-smi` and that torch sees CUDA, runs a short PushT evaluation on CUDA, and records the
  time. `pr-gate` stays on `ubuntu-latest`.
- **CUDA torch without touching the lock**: the workflow syncs the locked environment and then
  installs `torch` and `torchvision` from the PyTorch `cu128` index over it, at the versions the
  lock pins, and runs with `--no-sync`. A CUDA source or extra in `pyproject.toml` waits for the
  Isaac evaluator.

## Alternatives considered

- WSL2: CUDA works, Isaac Sim rendering does not.
- A Linux runner container on Docker Desktop (WSL2 backend): fresh per job, so truly ephemeral,
  but the Isaac Sim container is not supported under WSL2.
- Dual-boot Ubuntu 24.04: NVIDIA's documented Docker path and ephemeral containers, but a second
  OS on a full disk, and Windows tools unavailable while it runs. The fallback if Windows fails.
- Running the runner as Andrés's user: simplest, but every job could read his employer
  credentials.
- Cloud GPU per run ([0005](0005-two-machine-setup.md)): paid per hour while the home GPU idles.

## Consequences

- The GPU workflow runs only when the PC is on; otherwise its job waits in the queue (up to 24 h)
  and shows as pending. It is not required, so merges do not wait for it.
- Fork PRs need a manual approval, for every external contributor.
- The runner auto-updates; one not updated within 30 days stops receiving jobs.
- A Windows service runs in session 0, without a desktop: CUDA works there, but Isaac's Vulkan
  rendering must be checked headless before the Isaac evaluator moves onto it.
- ~35 GB free on the system drive is not enough for Isaac Sim plus its caches: freeing space or
  a second drive is part of the Isaac install plan.
- A PushT smoke run proves the runner is wired; it does not prove that an Isaac evaluation fits
  in 30 minutes.
