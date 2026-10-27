# 0016. First real evaluator: a pinned LeRobot policy in the PushT simulator, on CPU

- Status: Accepted
- Date: 2026-10-27

## Context

The pipeline ran end to end with a mock evaluator ([0014](0014-mock-evaluator-and-pr-gate-workflow.md)),
but no real policy or simulator had touched the results contract, and the SO-101 simulation needs
the home PC's GPU. LeRobot 0.6.1 ships CPU-friendly simulators (PushT, a 2D push-the-T task) and
`lerobot-eval`. A real evaluator now validates the contract, gives real timings and videos, and
proves the generic core works for a second robot without changes ([0015](0015-generic-core-vs-robot-specific.md)).

## Decision

- Policy: the official `lerobot/vqbet_pusht` (VQ-BeT, 158 MB, one network pass per action, so fast
  on CPU), pinned to a full commit SHA in `policies/pusht-vqbet.json`. Diffusion policies need ~100
  passes per action and are too slow on CPU; community ACT checkpoints use a config format 0.6
  cannot read.
- Simulator and tooling: the `sim-pusht` uv extra (`lerobot[dataset,evaluation,pusht]==0.6.1`).
- `eval/lerobot_policy.py` prepares the policy for LeRobot 0.6.1: drops config fields 0.6 no
  longer knows (`mlp_hidden_dim`), then converts the pre-0.4 built-in normalization with LeRobot's
  own `migrate_policy_normalization`, patched for a 0.6.1 bug (JSON lists for tuple-typed fields
  such as `crop_shape` crash the config serializer). Prepared policies are cached per revision.
- `eval/lerobot_eval.py` runs `lerobot-eval` in a subprocess (CPU, synchronous envs, explicit
  seed) and converts `eval_info.json` to the results contract: episode `i` gets seed
  `start_seed + i`; failures report the episode's max reward; failed episodes among the first 10
  (the only ones `lerobot-eval` records) get a video link.
- Baseline `stats/baselines/vqbet-pusht.json`: 263/500 (seeds 1000–1499) measured with this
  exact pipeline, not the model card's 285/500 (older LeRobot); the gate gives PASS between the
  two. A 500-episode baseline narrows its interval to ±4.4 pp, so a 50-episode PR run is compared
  against a nearly fixed reference.
- PR runs use fixed seeds (1000–1049 by default). The simulator is deterministic by seed, so an
  unchanged policy reproduces the same count on every PR and can never be blocked by sampling
  luck. Rotating seeds belong in a nightly run, where variation is the point.

## Alternatives considered

- Wait for Isaac Lab-Arena on the home PC: keeps the gate a demo for weeks.
- A community checkpoint already in the 0.6 processor format: unknown provenance and quality; the
  official policy plus a reproducible local conversion is more trustworthy for a quality gate.
- Calling LeRobot's eval functions in-process: tighter coupling to internals; the CLI in a
  subprocess is the documented interface.

## Consequences

- Measured on the laptop CPU: 50 episodes in 5 min 16 s (~6 s per episode), within the 30-minute
  budget. Same seeds gave identical outcomes across two runs: no flakiness from this simulator.
- 500-episode runs (laptop CPU, ~43 min each, ~5.1 s per episode): seeds 1000–1499 gave 263/500
  twice, identical episode by episode; seeds 2000–2499 gave 270/500. The gate gives PASS in both
  directions between them and against the model card.
- Sampling noise, from 1,000 episodes of the same policy: 10-episode windows range from 2/10 to
  9/10; disjoint 50-episode windows from 18/50 to 33/50. Against the 500-episode baseline the gate
  BLOCKs at 19/50 or fewer, so one window in 20 (seeds 1350–1399, 18/50) would have blocked an
  unchanged policy. That is the false-alarm rate expected from 95 % intervals, and the reason for
  fixed PR seeds and for ≥ 50 episodes.
- With a 263/500 baseline and 50 PR episodes, the gate BLOCKs a drop from 53 % to 38 % or lower
  and WARNs at 40–42 %. Smaller regressions need more episodes, or a paired comparison on the
  same seeds (future work).
- In PushT the reward is `coverage / 0.95`, capped at 1, and success needs coverage above 95 %.
  A failure with max reward 0.99 is a near miss at ~94 % coverage, not a solved task. Of 467
  failures, 37 never put any of the T on the target (reward 0) and 188 reached 0.90 or more.
- The migration patch depends on LeRobot 0.6.1 internals; `tests/test_lerobot_eval.py` covers the
  coercion, and a LeRobot upgrade must re-run a real evaluation.
- Using this evaluator in `pr-gate` on GitHub runners needs CPU-only torch wheels on Linux (PyPI's
  default Linux wheels bundle CUDA, several GB) and caching of the policy download.
