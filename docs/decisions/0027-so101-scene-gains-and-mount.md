# 0027. SO-101 scene: course gains, course mount, and our own success judgement

- Status: Accepted
- Date: 2026-11-02

## Context

PR 2 of the tube-to-rack port builds the course's scene on Isaac Lab 3.0's SO-101 asset
([ADR 0024](0024-so101-demo-replay-go-no-go-and-control-rate.md)) and ports its success term.
Three questions had to be settled with measurements, each registered in a commit before its
first run: where the asset mounts, which actuator gains the scene runs, and whether the course's
success term judges placements the way our gate should. Facts and numbers:
[isaac.md](../knowledge/isaac.md).

### Pre-registered: mount-height comparison (committed in `bba8e4b` before running)

Setup: the course robot USD (`SO-ARM101-USD.usd`, sha256 `11f5f0bb…991006`, fetched to the cache
outside the repo) at the course's pose (-0.05, 0, 0), yaw 90°, with the course's joint names; the
Isaac Lab 3.0 asset (`so101_new_calib`, `physx` variant) at the same pose. Joints of both set from
the converted recorded states (the course's unit table) at the 75 grasp frames (start of the
first hold). Differences are 3.0 minus course, in the task frame:

- (a) the `gripper` body origin;
- (b) the physically equivalent points: the lowest point of the fixed-jaw collision geometry and
  of the moving-jaw collision geometry;
- (c) our TCP (URDF `gripper_frame_link` offset) against the course's end-effector frame, its
  `gripper` body origin with no offset (`so101_env_cfg.py`, `ee_frame` target `Robot/gripper`),
  for information;
- the lowest z of each robot's base collision geometry at spawn (where the foot sits).

Predictions:

- Δxy of the jaw-geometry points (median over 75 frames): |Δxy| < 0.010 m.
- Δz of the jaw-geometry points (median): the 3.0 asset sits lower, Δz in [-0.035, -0.008] m.
- Foot: 3.0 base collision min z ≈ -0.030 m at mount z = 0; course base collision min z within
  0.005 m of 0 or of the light-box floor (~0.026 m).
- If (a) and (b) disagree by more than 0.005 m, the body→TCP offset is the suspect.

Rules:

- PR 1's clusters conclusion changes if the median |Δxy| of the jaw-geometry points exceeds
  0.010 m, or if Δxy varies with the pose (p95 - p5 spread above 0.010 m in x or y). Then the
  result goes to the orchestrator before PR 2 builds on PR 1's GO.
- If the jaw-geometry Δz and the foot Δz agree within 0.005 m, the 3.0 asset's mount z is -Δz.
  If they disagree, both are reported and no mount is picked.

### Results (`robots/so101/tools/isaac_mount_compare.py`)

| 3.0 minus course | Grasp (median) | Release (median) |
| --- | --- | --- |
| (a) `gripper` and jaw body origins | 0.0 mm | 0.0 mm |
| (b) moving jaw's lowest point | (-1.1, 0.0, -0.9) mm | (-2.7, -2.1, -1.1) mm |
| (b) fixed jaw's lowest point | (-0.9, 2.2, -1.0) mm | (-2.4, 9.4, 4.2) mm |
| Foot (lowest base point), mount z = 0 | 3.0: +0.030 m | course: +0.030 m |

- The course's robot USD **is** `so101_new_calib` (default prim `/so101_new_calib`) with renamed
  joints, the course's gains and the course's joint limits: body origins agree within 0.1 mm at
  all 150 poses.
- Predictions: Δxy < 10 mm held. **Δz failed**: it is -1 mm, not -8 to -35 mm. **Both foot
  predictions failed**: both feet sit 3 cm *above* the root. The fixed jaw's release-frame
  spread (7–29 mm in y) comes from the two USDs' different collision meshes for that body
  (143k vs 57k points), not from kinematics; the moving jaw stays within ±7 mm.
- The clusters rule did not trip: PR 1's GO stands. The mount rule gives jaw Δz -0.001 and foot
  Δz 0.000, which agree: mount z = 0.
- PR 1's grasp TCP p5 of 0.027 m (below the mat) was gravity sag with the asset's SysID gains,
  not the mount: kinematically, from the recorded states, the fixed jaw's lowest point at grasp
  is at 0.034 m, on the mat.

### Registered sensing checks (`robots/so101/tools/isaac_success_check.py`)

Expectations S0–S6 were committed in `d1c53ea`, S7 and S7b with the slot-depth rule in `bb3f0dd`,
all before their first run. With the course's gains and with the asset's: S0 objects settle, S1
the lying tube's axis is +x (the WXYZ→XYZW trap), S2/S3 a tube dropped over a slot enters it at
rack yaw 0 and 0.5 rad (bottom at rack-local z -0.001) and counts as in the box but not placed
(never grasped), S4 a tube lying on the rack top is not vertical, S5 a tube beside the rack is out
of the box, S6 the jaw sensor reads 0 N with no tube, S7 a tube standing upright on the rack top is
out of the box. **S7b failed on its first run because of its setup**: the held pose was computed
from the rack's nominal origin (z 0.06) while the rack settles at 0.041, so the tube was held
1.9 cm too high and the course's `z < 0.1` test also rejected it, which is not what S7b exists to
show. The setup was corrected in `dd09dae` (held pose from the settled rack; expectation
unchanged) and S7b passed on the re-run: a tube held upright over a slot opening with its bottom
at rim + 2.7 mm passes the footprint, the course's height test and the vertical test, and only the
slot-depth rule rejects it.

### Diagnostic, not registered: reconstructed demos

For each of the 75 demos, a tube is placed under the grasp TCP (at its mid-length, a guess: the
dataset has no object poses), the rack is placed with a slot under the release TCP, and the
actions are replayed at 60 Hz with the tracker running. The many `no_grasp` failures come from
that guess, so the counts compare configurations; they are not a performance figure.

- Course gains: 11/75 end-to-end successes (first run, course success term); asset (SysID)
  gains: 2/75, then 1/75 with our success term, with 21–27 episodes that grasp the tube but fail
  to place it.
- Jaw contact force on the tube: at most 0.61 N while the open jaw approaches, up to 1.98 N when
  the closing jaw pushes the tube without holding it, 10–19 N (per-episode median) in genuine
  grasps.
- The slot-depth rule turned two course-term successes into `not_placed`. Replaying the dumped
  tracker inputs under 2/5 N × depth on/off (`success_variants.py`): in both the tube rested on
  the rack's rim, tilted 7–39°, with its bottom at 0.064–0.073 m (1–2 cm above the bound); a
  seated tube's bottom is at -0.001 m. The force threshold changed no outcome in those episodes.
- **The replay is not reproducible run to run once contacts are involved**: two runs with the
  same code differ in 2 of 75 outcomes, in success steps by 1–4 steps and in the force summaries
  of 19 episodes.

## Decision

- **Mount**: the Isaac Lab 3.0 asset mounts at the course pose, (-0.05, 0, 0), yaw 90°.
- **Gains**: the scene runs the course's actuator settings (`course_actuators.json`: stiffness,
  damping, 30 N·m effort limit, 32 solver iterations) when evaluating policies trained on the
  course's data, because that data was recorded with them. The asset's SysID gains are kept for
  sim-to-real checks against the real arm. The actuators are a scene parameter
  (`build_scene_cfg(..., actuators="course" | "usd")`), recorded with every result.
- **Success is our gate's judgement, ported from the course with two deliberate changes**
  (`vials_to_rack_success.py`):
  - grasp contact threshold **5 N** (the course uses 2 N, at the measured push level; 5 N sits in
    the gap up to genuine grasps, about 2.5× from each side);
  - a **slot-depth rule**: a tube is in the rack only if its lowest end is at least 2 cm below
    the rack's rim (rack-local z < 0.053), whichever way up it is. The course's tests (footprint,
    origin z < 0.1, |axis z| > 0.7) accept a tube standing on the rim or leaning on it at up to
    ~45°.
  The rest follows the course: 30-step warmup, a 20-step grasp history, release before
  placement, 25 confirmation steps, failure reasons `no_grasp`, `not_placed`,
  `placement_not_held`.
- **Assets** are fetched at runtime from the course repository at `ce807d9` into a cache outside
  the checkout, verified by sha256 (`fetch_course_assets.py`), never committed; the light box's
  remote camera payload (`rsd455.usd`, Isaac 5.1 Nucleus) and MDL materials stay unresolved until
  cameras are needed.

## Alternatives considered

- SysID gains everywhere: closer to the real servos, but the policy's data was made with the
  course's gains; with SysID the arm sags and placements fail (1–2/75 vs 11/75).
- Keep the course's 2 N: right at the measured push level.
- Keep the course's success tests without a depth rule: counts tubes standing on or leaning on
  the rim.
- Correct the mount from the PR 1 TCP dip: the dip was gain sag, not geometry.

## Consequences

- The evaluator (next PR) builds on this scene and success term, and reports the actuator
  choice with its results.
- Our success numbers are not directly comparable with the course's: they are stricter by
  design (depth rule, 5 N).
- The run-to-run variation with contacts must be understood before the gate trusts a single
  run: the evaluator PR measures same-seed repeatability in this scene and checks whether
  PhysX's enhanced determinism or a fresh process per episode removes it.
- The diagnostic's many `no_grasp` episodes come from not knowing where along the tube the
  operator grasped; they do not measure the scene.
