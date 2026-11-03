# 0033. SO-101 Isaac evaluator: one fresh process per seed

- Status: Accepted
- Date: 2026-11-03

## Context

PR 3 of the tube-to-rack port builds the evaluator that will feed the gate from Isaac Lab 3.0
([ADR 0021](0021-isaac-lab-3-on-windows-without-arena.md),
[ADR 0028](0028-so101-scene-gains-and-mount.md)). ADR 0028 left an open problem: two runs over
the 75 reconstructed demos differed in 2 outcomes. The gate's statistics (Wilson/Newcombe,
[ADR 0003](0003-statistical-gate-wilson-newcombe.md), and the paired comparison of
[ADR 0032](0032-nightly-paired-run-on-rotating-seeds.md)) assume independent trials per seed, so
before writing the evaluator we measured repeatability. Facts and numbers:
[isaac.md](../knowledge/isaac.md).

### Pre-registered: same-seed repeatability study (committed in `fb5100b` before running)

The reconstructed-demo replay (course gains, 75 episodes), N = 3 runs per configuration: (a) the
current setup (GPU physics, one process); (b) PhysX enhanced determinism; (d) a full
`sim.reset(soft=False)` + `scene.reset()` before every episode; (e) CPU physics; (c) one fresh
process per episode, on a fixed 15-episode subset. Hypothesis H1, tested by one run of (a) in
reverse order: *the outcome of an episode depends on which episodes ran before it in the same
process.* Rule: a configuration is repeatable with zero outcome flips over N ≥ 3 runs; choose the
cheapest repeatable one by mean episode wall time.

Results (`robots/so101/envs/repeatability.py`, `tools/repeatability_report.py`):

| Config | Episodes | Outcome flips | Identical fingerprints | Wall time |
| --- | --- | --- | --- | --- |
| a | 75 | 0 | 75/75 | 6.2 s/episode |
| b | 75 | 0 | 75/75 | 6.0 s/episode |
| d | 75 | 0 | 75/75 | 6.2 s/episode |
| e | 75 | 0 | 75/75 | 1.1 s/episode |
| c | 15 | 0 | 15/15 | 5.6 s in process; 21.7 s with Kit's startup |

- **H1: supported.** In reverse order 12/75 outcomes and 50/75 trajectory fingerprints change;
  even episode 0 changes with its position. Every configuration is repeatable for a fixed order,
  so outcomes are a function of (seed, order), not of the seed alone.
- **(b) and (d) are bit-identical to (a)**: enhanced determinism and the full reset (it ran: 75
  "Fabric Kinematics already initialized" warnings in d's log) change nothing, and the full
  reset does not remove the order dependence. The carried state's mechanism is unknown.
- **(e) moves the baseline**: CPU physics changes 23/75 outcomes against (a) and matches 0/75
  fingerprints; the success counts are equal (8 = 8) only by coincidence, with different
  episodes succeeding. (c) changes 2/15 outcomes against (a).
- **The registered rule picked (e)**, the cheapest repeatable configuration. The table's figure
  for (c) also hides its cost: Kit's startup makes it ~22 s per episode, not 5.6.
- A CI job held the self-hosted runner at several run boundaries (`Runner.Worker.exe`;
  feat/paired-mcnemar's `gpu-smoke` and `pr-gate`, CodeQL). Fingerprints did not change; wall
  times vary ±7%.
- ADR 0028's 2/75 difference is consistent with H1: its two runs (`v2` at `bb3f0dd`, `v3` after
  `dd09dae`) ran the registered checks before the diagnostic in the same process, and S7b's setup
  changed between them, so the episodes had different predecessors.

### Pre-registered: evaluator acceptance test (committed in `75a497d` before running)

`robots/so101/envs/evaluator_acceptance.json`: two runs of seeds 0–74 with the evaluator (one
process per seed). Pass iff both runs complete; zero outcome flips and identical fingerprints
between them; the 15 study-subset seeds match the study's (c) run in outcome and fingerprint;
at most 36 s per seed.

- **First attempt (code `d3823c9`): failed.** Run A1 stopped at seed 11: the worker hung for
  120 s in Kit's shutdown (`SimulationApp.close` → `app.shutdown()`, the deadlock Isaac Sim
  documents as NVBug 5948099 and guards with a 120 s watchdog), then exited 1. The driver did what
  it was designed to do: evaluator error, exit 2, no results. No self-hosted job was running when
  the hang began. One hang in 87 worker processes. The rest, reported but not a pass: A2 completed
  all 75 seeds; the 15 subset seeds matched the study bit for bit (A1's 0 and 7 too); A1's 11
  completed seeds matched A2 (0 flips, 11/11 fingerprints); 20.9 s per seed; 6/75 successes.
- **Second attempt (code `ef5da20`, same criteria): passed.** Runs R1 and R2 completed with 0
  infrastructure retries; 0 outcome flips and 75/75 identical fingerprints between them; the 15
  subset seeds match the study in outcome and fingerprint; 20.2 s per seed end to end (slowest
  worker 35 s). R1 also matches the first attempt's A2 bit for bit, so skipping Kit's shutdown
  changed no result and no startup time (median worker 20.4 s vs 20.6 s); no Kit process was left
  behind. No CI job held the runner. Predictions: ~22 s per seed (measured 20.2); few successes
  (6/75: seeds 20, 22, 31, 49, 58, 61; failures 52 `no_grasp`, 17 `not_placed`).

## Decision

- **The evaluator runs every seed in a fresh Isaac process**, configuration (c), against the
  registered rule's pick (e). The rule was written before we knew about the order dependence and
  tested repeatability, not independence: in one process a policy change at episode k can change
  episode k+1's outcome, which contaminates both the unpaired and the paired comparison. One
  process per test is test isolation. (e) runs in one process and inherits H1.
- **Cost**: ~21 s per seed with Kit's startup; 50 seeds ≈ 18 min, inside the 30-minute budget.
- **The baseline is measured in the configuration the gate runs**: physics device and process
  model both change outcomes (23/75 for CPU vs GPU, 20/75 for in-process vs one process per
  seed).
- **Layout**: `piperobot/adapters/isaaclab/` holds the generic parts: task and policy specs
  (pinned input files checked by sha256), the per-seed worker (Isaac imported inside `main`, the
  task's simulation settings set before launch) and the driver, which writes the results
  contract plus `run_metadata.json` and `episodes_detail.json`. The SO-101 task and the first
  policy (open-loop replay of the course's demos, seed = demo index, on the reconstructed layout)
  live in `robots/so101/`. A seeded randomized layout with the course's ranges is implemented and
  unit-tested; it is refused for open-loop replay, which ignores the layout.
- **Infrastructure errors are not trials.** A worker crash, timeout or missing or invalid result
  is an evaluator error; it is retried once (a fresh process for the same seed), never a policy
  failure. A seed that fails twice, or more than three retried seeds in one run, makes the run an
  evaluator error: exit 2, no `results.json`. Retries are counted in the metadata and the summary
  line. The worker writes its result atomically, fsyncs and re-reads it, then exits with
  `os._exit(0)`, skipping Kit's shutdown.

## Alternatives considered

- (e) CPU physics, one process: cheapest and repeatable, but order-dependent (inferred: it runs
  in one process; not run in reverse).
- (d) full reset in one process: does not remove the order dependence.
- Untested, possible follow-ups: one process per seed on CPU physics; (e) in reverse order;
  2–3 workers in parallel (a worker peaks at ~2.9 GB of GPU memory over a ~9.9 GB desktop load
  on the 16 GB card; measure before trying).

## Consequences

- An evaluation costs Kit's startup per seed; parallel workers are the way to buy it back.
- The replay baseline is low (6/75 in one process per seed) because the dataset has no object
  poses and the reconstruction guesses the grasp point; it checks the pipeline, not a policy.
- Infrastructure flakiness is a visible metric (retries per run), not hidden in success rates.
