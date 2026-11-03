# 0034. SO-101 scripted privileged-state policy: GO for the gate (43/50)

- Status: Accepted
- Date: 2026-11-03

## Context

The SO-101 gate needs a policy whose success rate leaves room to see a regression. The replay of
the course's demos succeeds 6/75 ([ADR 0033](0033-so101-isaac-evaluator-one-process-per-seed.md)):
the dataset has no object poses and the reconstruction guesses the grasp point. With 6 reference
successes, the paired gate can only block a total collapse, and the replay has only 75 seeds.
The plan agreed for the gate
was a scripted pick-and-place policy on the seeded randomized layout, accepted only after a
pre-registered go/no-go. Facts and numbers: [isaac.md](../knowledge/isaac.md).

**It is a privileged-state policy.** Every step it reads the simulator's tube, rack, slot and TCP
poses, and it closes the loop on the observed position of the held tube, which the real arm
cannot see. It measures the pipeline and regressions in simulation. It is not a deployable
policy; ACT, trained on the course's data, is the one meant to reach the real arm.

### Feasibility, from the 75 demos (before any code)

Gripper pose and joints at each demo's grasp and release frames, set in Isaac:

- The jaw closes across the lying tube (closing axis ≈ world -y, tube along +x).
- The tube turns vertical by pitching the gripper about that same horizontal axis: wrist_flex
  changes by about -1.7 rad between grasp and release, and wrist_roll barely changes (-0.11).
- The gripper's pitch is the sum shoulder_lift + elbow_flex + wrist_flex (parallel axes), and the
  demos hold the sum steady: 1.025 rad at grasp (sd 0.074, against 0.139 for wrist_flex alone),
  -0.172 at release (sd 0.158 against 0.375).
- The course publishes no success rate for this task, so there was no outside ceiling for the
  threshold.

### Tuning (development seeds 200000-200099 only)

The task gained a policy loop for the randomized layout (stop at a confirmed success or after a
600-step horizon; no force windows; a count of steps with wrist_flex within 0.05 rad of a limit),
an optional `UsesObjectState` observation, and a `tcp` action space,
`[x, y, z, gripper pitch, wrist_roll, gripper]`.

- **IK** (Isaac Lab's position-only DLS on shoulder_pan, shoulder_lift and elbow_flex):
  - Computing q + dq from the measured joints stalls about 2.7 cm short. The course's low gains
    let gravity hold the arm off its target, so the measured q never moves.
  - Integrating on the previous joint target removes the stall. That alone winds up and diverges,
    so it runs with gain 0.2 and a 0.25 rad limit on how far a target may lead the measured joint.
  - wrist_flex is derived from the commanded pitch.
- **Grasp point**: the open jaws are not centred on the course's TCP, so the fixed jaw landed on
  the tube. The grasp point sits 2 cm across the tube and 8 mm below its axis. Along the tube it
  is 4 cm out from the origin, capped so the TCP stays within x = 0.295 m and never less than
  1.5 cm from the tube's end: every in-process failure had the tube at x ≥ 0.255 m.
- **Placement**: the held tube, not the TCP, is steered over the slot, because the tube hangs off
  the TCP by however far off-centre it was grasped. The transfer height is 0.19 m, so the tube
  clears the rack.
- The reconstructed-demo path was kept byte for byte: 75/75 fingerprints and 6/75 equal to the
  acceptance run (ADR 0033) with the spike's code.
- Development result at the code commit `0bf1787`:
  - through the evaluator (one process per seed): 91/100, 0 infrastructure retries, 24.1 s per
    seed;
  - in one process: 88/100, with 7 seeds that differ between the two modes (ADR 0033's H1).

### Pre-registered: go/no-go (`82ad858`, pushed before the run)

`robots/so101/policies/scripted_go_no_go.json`:

- Code: `0bf1787`. The run commit `82ad858` adds only the registration and was pushed to GitHub
  before the run started.
- Seeds 210000-210049, run once through the evaluator, one Isaac process per seed.
- GO at ≥ 30/50. The registration also states the recorded environment, the rule for voided runs
  and the NO-GO path (no retuning against those seeds).

Result: **GO, 43/50 (86%)**.

- The 7 failures are all `not_placed`. Most of them, 4 of 7 (seeds 210003, 210012, 210017 and
  210036), have wrist_flex pinned at its limit for about 490 of 600 steps.
- 16/50 seeds touch the wrist_flex limit at least once, 11 of them successes. In the 43 successes
  that is about 114 steps in total, so the pass does not rest on the limit.
- 0 infrastructure retries and no voided run. 25.0 s per seed end to end: 50 seeds take about
  21 minutes.
- Environment as registered: RTX 5060 Ti, driver 610.88, torch 2.11.0+cu130, Isaac Lab
  release/3.0.0 at `44044b0963`, Isaac Sim 6.2. No platform difference between workers.
- A CI job held the runner when the run started. Per ADR 0033 that leaves fingerprints unchanged;
  the time per seed may be noisy.
- The per-seed artifacts are kept outside the repository, until this decision merges. sha256:

  | Artifact | sha256 |
  | --- | --- |
  | go/no-go `results.json` | `ed0d4a976bedcdd6e6863a55907897efc11b41d80e542c563a409c7b9ce3c4d6` |
  | go/no-go `run_metadata.json` | `c905571ebb82b51d7f247abfc5d4b7b0a30de7611e32e858b69ef04b5c422c92` |
  | go/no-go `episodes_detail.json` | `3414342dbb1e1dc9e5a6556a34f4841e908e17b9f9152aadb9d2e637c7f1834b` |
  | development `results.json` | `1f240f63547d666e42fdb413d67ffa8e996c7b10437aa20da8baed862e24b78c` |
  | development `run_metadata.json` | `7ea6f961701aa0d4a4f9acf49a97bbf91f0acc1e6582bf28294a46cc8649bc35` |
  | development `episodes_detail.json` | `dc5322b2a437633cdc65d767e5cba1415db28ca05ada12bbe57923570ba16ff8` |

## Decision

- `robots/so101/policies/scripted_pick_place.json`, on
  `robots/so101/envs/vials_to_rack_task_randomized.json`, passed its registered go/no-go and is
  **proposed to replace `demo_replay` as the SO-101 gate's policy**. The gate's own ADR (in the
  gate-workflow PR, not merged when this was written) applies the change; this ADR does not edit
  it.
- The decision method does not change. The gate stays paired: exact McNemar on fixed seeds
  ([ADR 0032](0032-nightly-paired-run-on-rotating-seeds.md)), against a per-episode baseline
  measured on the same runner. Isaac is bit-reproducible per seed on one machine (ADR 0033).
- What the scripted policy buys is power for that paired test: unlimited seeds, a 500-seed
  baseline (100000-100499), PR seeds drawn from it, and a reference rate near 86% instead of 8%.
- Unpaired comparison is not a gate method here. At most it is a nightly observation, as with
  PushT.
- The replay stays the evaluator's pipeline acceptance test (ADR 0033), and the fallback policy.

## Alternatives considered

- Keep the replay as the gate's policy: blocks only a total collapse (6 reference successes).
- A better replay reconstruction: still 75 seeds and an open-loop policy that ignores the layout.
- Wait for a trained ACT policy: the gate would have no policy with power until then. ACT
  replaces the scripted policy through the same pipeline when it exists.

## Consequences

- Known limitation: the dominant failure mode is wrist_flex pinned at its limit (4 of 7
  go/no-go failures). A future retune needs a new, untouched go/no-go seed range declared in
  advance (the registration's NO-GO path applies to any retune).
- Gate results measure the simulated pipeline and regressions of a privileged-state policy, not
  a deployable one; the PR comment and the docs must say so.
- A deliberately worse PR for the BLOCK demo can now be a scripted parameter change; its expected
  outcome must be registered like the weak-grip spec's.
- Any change to the success tracker, the scene or the randomization voids this go/no-go and
  needs a new one.
