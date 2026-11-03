# 0027. SO-101 scene: actuator gains and mount height of the Isaac Lab 3.0 asset

- Status: Proposed
- Date: 2026-11-02

## Context

Draft. The decision and its evidence are written after the measurements below; this section is
committed first so that the predictions and decision rules predate the run.

### Pre-registered: mount-height comparison (recorded before running)

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

## Decision

To be written after the measurements.

## Alternatives considered

To be written.

## Consequences

To be written.
