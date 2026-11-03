# 0024. Object-free demo replay as the SO-101 asset go/no-go; control rate measured per dataset

- Status: Accepted
- Date: 2026-11-02

## Context

The tube-to-rack task is being ported from NVIDIA's Sim-to-Real SO-101 course (Isaac Lab 2.3) to
Isaac Lab 3.0 ([ADR 0021](0021-isaac-lab-3-on-windows-without-arena.md)). The plan uses Isaac
Lab 3.0's own SO-101 asset (`so101_new_calib`), not the course's robot USD, so before porting the
scene we must know whether that asset reproduces the course's teleop demonstrations. The course
trains on `sreetz-nv/so101_teleop_vials_rack_left` (75 simulated episodes, LeRobot v3.0).

Three facts shape the check ([isaac.md](../knowledge/isaac.md)):

- The dataset holds joint states, joint actions and two videos, but **no object poses**. The
  course randomizes the rack and the tubes on every reset and the number of resets before each
  recorded episode is not recoverable, so replaying an episode into any scene is not replaying
  it into its own scene. A low "tube reached the rack" rate would not tell an asset problem from
  a scene mismatch.
- **The dataset says 30 fps but holds 60 Hz data.** The course's recorder writes one frame per
  `env.step`, and its environment steps at physics dt 1/120 s with decimation 2: 1/60 s of
  simulated time per frame. Its evaluation also gives one action per `env.step`. 18250 frames
  over 75 episodes is about 243 frames per episode: 4.05 s at 60 Hz, inside the course's 7.5 s
  evaluation timeout, against 8.1 s at 30 Hz, longer than that timeout.
- **The joint-unit table belongs to the course's robot USD, not to LeRobot.** LeRobot stores arm
  joints in -100..100 and the gripper in 0..100; the course maps them linearly to per-joint
  degree ranges that its own USD defines.

## Decision

- **The asset go/no-go is object-free.** `robots/so101/tools/isaac_demo_replay.py` replays every
  episode's actions on the Isaac Lab 3.0 asset with no objects and
  `robots/so101/tools/demo_replay_report.py` judges two things: joint tracking against the
  recorded states, and where the tool-centre point is when the recorded gripper starts and stops
  holding a tube, against the course's tube and rack regions expanded by its randomization
  ranges. The verdict is GO, BASE_OFFSET (a uniform translation, recorded with its value) or
  NO_GO. The thresholds are constants in `robots/so101/envs/demo_replay.py`, fixed before the
  first run; changing them needs a new ADR. A NO_GO stops the port until the asset choice is
  revisited. Success detection with real objects is validated separately, by scripting a tube
  into the rack.
- **Control rate is a per-dataset fact with provenance.** `robots/so101/envs/demo_datasets.json`
  stores `control_hz` and how it was established; code derives the physics substeps per frame
  from it and falls back to the metadata fps only when no measured value exists. For the course
  dataset it is 60 Hz.
- **SO-101 joint units are converted in exactly one place**, `robots/so101/envs/joint_units.py`,
  with the table as data in `joint_units.json` and joints looked up by name.

## Alternatives considered

- Replay into a nominal (non-randomized) scene and count tubes in the rack: confounds asset
  errors with the unknown per-episode scene.
- Take the rate from the dataset's `fps`: picks 30 Hz for data recorded at 60 Hz.
- Port the course's robot USD instead of using the 3.0 asset: kept as the fallback for a NO_GO;
  it brings its own joint names, gains and attribution questions.

## Consequences

- The port proceeds only on a measured GO or BASE_OFFSET, and the bar cannot move after a result.
- The 30-fps label also matters for training: a policy trained on this dataset (ACT, LeRobot)
  reads its chunk timing from the metadata fps, so its actions are meant for 60 Hz control. How
  that maps to the real arm's control loop is an open question for the training work.
- The replay does not test contacts, grasp dynamics or cameras; the scene port and the success
  term are tested in their own PRs.
