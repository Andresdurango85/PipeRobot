# 0038. SO-101 failed-episode videos: a camera re-run after the verdict

- Status: Accepted
- Date: 2026-11-04

## Context

Phase 0 asks for a PR comment with the rate, the verdict and videos of failed episodes. PushT
meets it with run-artifact videos. The SO-101 gate
([0035](0035-so101-gate-on-the-self-hosted-runner.md),
[0036](0036-so101-gate-scripted-policy-on-100-fixed-seeds.md),
[0037](0037-so101-gate-verdict-is-a-required-check.md)) evaluates 100 seeds without a camera in
~26-29 min on two workers. That leaves ~1-3 min of the 30-minute budget, and the desktop leaves
~9.5 GB of VRAM free.

A registered check
([registration](../../robots/so101/envs/camera_record_check.json),
[result](../../robots/so101/envs/camera_record_check_result.json)) measured a camera-on re-run
against the camera-off episode on 30 development seed and policy pairs:

- Same success, failure, success_step and `trajectory_sha256` on 30/30. The rendering kit file
  and the extra `render()` calls do not reach the physics, so a recorded re-run shows the episode
  the gate judged.
- Cost of one camera-on worker against a camera-off one:
  - VRAM: 4.2-4.5 GB above idle, against 2.7-3.5 GB;
  - Windows commit: 12.8-14.9 GiB, against 6.6 GiB;
  - time: about +20 s per failed seed (53-61 s against 31-39 s);
  - output: 13.3 MB of JPEG frames per failed seed (300 frames, 640×480, 30 fps).
- Host commit, not VRAM, is what runs out. Kit fails at start when the commit charge is exhausted,
  even with VRAM free ([isaac.md](../knowledge/isaac.md)).

## Decision

- `evaluate` stays camera-free and unchanged. The scene has no camera prim unless recording is
  on. The verdict (`report`, and `so101-gate-verdict`, which needs only `changes`, `evaluate` and
  `report`) never waits for or depends on videos.
- Three jobs follow `evaluate`, in gate mode and never on `main` (no PR to comment on; main's
  runs queue):
  - `video-select` (hosted, read-only) picks the seeds from the artifact and the baseline:
    - the lost seeds (reference success, candidate failure) first, then the candidate's other
      failures, ascending, capped at 5;
    - **a PASS with no lost seed records nothing**: its failures are the baseline's own (the
      scripted policy's wrist_flex mode), the same on every PR, so recording them would cost the
      single runner ~5 min per PR for no new information. The comment says so.
    - Once at least one seed is lost (even on a PASS), the list is padded up to 5 with the
      candidate's other failures, which may include failures the baseline shares: "b > 0"
      decides whether to record, not what.
    - Video selection pairs on the candidate's seeds only, so a baseline covering more seeds
      does not break it. The gate's own verdict (`paired_comment`) still requires identical seed
      sets.
  - `video` (self-hosted) runs only when that list is non-empty:
    - it re-runs those seeds with one fixed external camera (`robots/so101/envs/video_camera.json`)
      through the evaluator's own retry discipline;
    - it keeps a video only if the re-run's outcome and `trajectory_sha256` equal the judged
      episode's;
    - `continue-on-error`, 15-minute timeout;
    - a preflight skips recording with a warning when free commit is below 19 GiB (the cold
      14.9 GiB peak +25%).
  - `video-report` (hosted, the only new job with `pull-requests: write`):
    - encodes H.264 MP4s with the image's ffmpeg (apt if it is ever missing), so nothing is
      installed on the PC or in the runner's env;
    - uploads them as `so101-videos-<run>-<attempt>` (7 days; frames 1 day);
    - upserts a second sticky comment, `<!-- piperobot-gate:so101-videos -->`, with the commit,
      the run link and the download link, or the reason nothing was recorded.
- The video jobs are not part of the required check. A video failure is a warning, never a red
  gate.
- Videos are simulation only and artifacts only, never committed or pushed to the Hub.
- The camera on/off check is re-run (new registration) after any Isaac Sim, Isaac Lab or Kit
  upgrade, and after any change to the scene or the episode loop. If it ever fails, recording
  switches to replaying the judged episode's recorded states into a render-only scene.
- The evaluate preflight checks free commit as well as VRAM before choosing two workers
  (`COMMIT_PER_WORKER_MB` 8448: 6.6 GiB +25%).

## Alternatives considered

- **Cameras inside the 100-seed evaluation**: +20 s per failed seed on every seed, and twice the
  commit per worker. It breaks the 30-minute budget and the two-worker memory fit.
- **A section inside the verdict comment**: `report` rewrites the whole comment, so a report
  rerun (as after #67's GitHub 500) would wipe the section, and the two jobs could race.
- **Recording every candidate failure on a PASS**: ~5 runner minutes per PR, for failures that
  are the same on every PR.
- **Encoding MP4 on the PC**: needs imageio-ffmpeg or PyAV in the Isaac env and the runner's env;
  JPEG via OpenCV needs nothing new.
- **Replay recorded states into a render-only scene**: exact by construction, but more code. Kept
  as the fallback for a failed on/off check.

## Consequences

- On a regressing PR the verdict comes first. A second comment follows ~5-7 min later (the runner
  re-runs up to 5 seeds), and the next PR's evaluation waits that long for the runner.
- When a later push skips `evaluate` (an irrelevant change), the videos comment keeps the older
  commit, as the verdict comment does (0037). The SHA in it shows which commit it belongs to.
- The first recording on a cold runner may pay ~184 s of shader compilation once.
- MP4 size and the extra runner minutes are measured on the first real run (a demo PR, as #65).
