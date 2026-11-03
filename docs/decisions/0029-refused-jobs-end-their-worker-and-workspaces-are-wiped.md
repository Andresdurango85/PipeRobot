# 0029. Refused runner jobs end their worker; every job's workspace is wiped

- Status: Accepted
- Date: 2026-11-03

## Context

[0027](0027-self-hosted-runner-push-only-and-pinned-actions.md) added a job-started hook to the
self-hosted GPU runner that refuses any job that is not one of our self-hosted workflows on a
push, dispatch or schedule. Measured on 2026-11-03 (runner 2.338.2), the hook's non-zero exit
skips a job's normal steps but **not its `if: always()` steps**: a refused `gpu-smoke` (run
41573497209) ran `actions/upload-artifact` on the runner and uploaded a file a previous job had
left in the workspace, because the checkout that would have cleaned it never ran. A fork-added
workflow could put its payload in such a step. GitHub's docs say the job "will not run".

The runner offers no setting to skip `always()` steps after a failed hook. The hook runs as a
direct child of the job's `Runner.Worker.exe` (`RunnerService.exe → Runner.Listener.exe →
Runner.Worker.exe → powershell.exe`), and every job gets a fresh worker.

## Decision

1. **On refusal, the job-started hook ends its parent `Runner.Worker.exe`**, after printing the
   reason, and exits 1. It checks the parent by name and never walks further up, so the Listener
   and the service are never touched. If the parent is anything else (tests, a shell), it only
   exits 1.
2. **A job-completed hook wipes the job's workspace after every job**
   (`.github/runner/job-completed.ps1`, `ACTIONS_RUNNER_HOOK_JOB_COMPLETED`). It deletes the
   contents of `GITHUB_WORKSPACE`, which holds our `out/` and `work/`, only if that folder is a
   direct child of `RUNNER_WORKSPACE` under `_work` and not one of the runner's own folders
   (`_tool`, `_temp`, …). The delete never follows junctions or symbolic links: it removes the
   link itself, because Windows PowerShell 5.1's `Remove-Item -Recurse` can delete a junction's
   target, such as the Isaac environment in `_tool`. Any failure fails the job (0009).
   The runner's tool cache (Isaac env, uv cache) is kept.
3. Both live copies sit in `C:\ProgramData\piperobot-runner\`, read-only for the runner's user,
   and are named in the runner's `.env`; they are redeployed by hand, elevated, from the
   reviewed files.

## Alternatives considered

- Accept that `always()` steps run and rely on the fork approval setting alone: one approval
  click away from code on the home PC.
- Kill the whole runner service on refusal: stops the job too, but leaves the runner offline
  until someone restarts it.
- A container per job: the runner is native Windows for Isaac's rendering
  ([0020](0020-self-hosted-gpu-runner.md)); no Windows container path for it.
- `Remove-Item -Recurse -Force` for the wipe: shorter, but follows junctions on PowerShell 5.1.

## Consequences

- Measured on draft PR #35 (runs 41580283257 push, 41580287237 pull_request): a refused job
  with an `always()` step writing a marker and an `always()` upload ran no step at all, wrote no
  marker and uploaded no artifact; each run ended in about 20 s, in one attempt. The Listener
  logged "worker encounter an unhandled exception or app crash" and the job result Failed, then
  kept listening; the runner stayed online and ran the next allowed job.
- **A refused job has no log on GitHub** (the worker dies before uploading it; the log API
  returns 404). The reason is not visible there: the run just fails in "Set up runner". The
  Listener's own log in `C:\actions-runner\_diag` records the crash.
- Every allowed job ends with "Wiped job workspace: … (N entries)" under "Complete runner",
  about 13 s for `gpu-smoke`. A cold workspace costs nothing measurable: `gpu-smoke` took 2 min
  30 s cold against 2 min 25 s–2 min 43 s before (run 41580744632; install 17 s, evaluation
  94 s), because the uv cache is in the tool cache and the Hugging Face cache in the runner
  user's profile. GPU contention from another session's study may have added noise.
- A refused job's actions are still downloaded to the runner before the hook runs (not
  executed).
- The fork approval setting stays on as a second layer.
