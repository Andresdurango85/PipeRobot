# 0044. Gate trained policies against a written spec, with repeatability checked per task

- Status: Accepted
- Date: 2026-11-08

## Context

The first weekend of the RL track ([ADR 0043](0043-reinforcement-learning-track-for-the-crab.md),
2026-11-07/08) trained Isaac Lab's public Franka tasks as references, with three training seeds
each, and judged every checkpoint with the gate's paired test on 100 fixed evaluation seeds. Each
experiment was registered before it ran. Four results bear on the gate's generic core:

1. **Training metrics disagreed with the spec.** On `Isaac-Lift-Franka` (6000 iterations),
   training's own `Metrics/success_rate` read 0.89 to 0.91 on every seed. At the task's full
   spec, the final checkpoints succeeded on 3, 15 and 2 of 100 episodes. The training metric
   counts an episode once the object is *ever* near a goal that moves every 4 to 6 s, starts from
   a bank of states biased toward 50% success, and runs at the curriculum level training reached
   (gravity scaled to about 0.88 of real). The spec holds one goal to the last step at real
   gravity. On `Isaac-Reach-Franka`, the task's own 5 cm success stayed at 1.000 while a 2 cm
   specification moved between 2 and 55 of 100.
2. **One checkpoint is not the unit.** With one Reach recipe, the 2 cm finals of three training
   seeds were 32, 41 and 45 of 100 (up to 13 pp apart, a WARN), and the mid checkpoints were 55,
   5 and 2. Seed 1's "final worse than mid" (a BLOCK) did not repeat on seeds 2 and 3. On one of
   the crab's tasks, a reward change with a sound gradient argument lowered the recipe from
   147/300 to 108/300 across three seeds. One seed alone would have shown a PASS (-3 pp).
3. **Repeatability depends on the task, not only on the backend.** Both tasks ran on Isaac Lab
   3.0's default `newton_mjwarp` backend (`deterministic_mode: not_guaranteed`). Reach, which has
   no contacts, re-evaluated bit-identically: 100 of 100 outcomes and final-state digests matched.
   Lift, with gripper, object and table contacts, did not: three fresh processes on the same
   checkpoint and seeds scored 3, 3 and 6 of 100, and 0 to 1 of 100 final-state digests matched.
   The successful seeds barely overlapped. So the paired McNemar test, which assumes seed k gives
   the same episode for both policies, gains nothing there.
4. **A binary threshold near the typical error turns small shifts into large swings.** Reach
   episodes all ended within 3.9 cm of the target, with medians of 1.9 to 3.2 cm, so the 2 cm
   threshold sat inside the distribution. A shift of a few millimetres moved the rate by tens of
   points.

Until now, the gate's contract ([results.py](../../piperobot/results.py)) carries only a seed and
a pass/fail per episode. Its paired path ([ADR 0032](0032-nightly-paired-run-on-rotating-seeds.md))
assumes that seeds reproduce episodes. [ADR 0033](0033-so101-isaac-evaluator-one-process-per-seed.md)
checked that once, for the SO-101 evaluator on PhysX.

## Decision

1. **The gate judges against a written spec, never against training's metrics.** Each task's
   success definition is written down independently of its training reward and curriculum.
   Evaluation runs at the full spec: the task's final curriculum level, with real physics
   parameters. A training-time success metric is never a gate input. A trained checkpoint's
   provenance records the curriculum level it reached.
2. **Repeatability is an admission check per task and evaluator version.** Before a task's
   comparisons are paired, one checkpoint is evaluated twice, in fresh processes. The results
   carry optional per-episode `initial_state_sha256` and `final_state_sha256`.
   - If outcomes and final digests match on every seed, the task is **repeatable**, and the
     paired McNemar gate applies.
   - If they don't, the task is **not repeatable**. Its comparisons use the unpaired
     Wilson/Newcombe gate ([ADR 0003](0003-statistical-gate-wilson-newcombe.md)), which needs
     more episodes for the same power. The report says which path was used and why.
   - The check is re-run after an upgrade of the simulator, physics backend or evaluator.
3. **Seeds must vary the scene.** When initial-state digests are present, two different seeds
   sharing one initial state is an error, not a result.
4. **A continuous metric goes next to the rate.** An episode may carry one numeric `metric`
   (for example the end distance to the goal), and the results may name it, its unit and the
   success threshold. Reports then show its median, p90 and IQR per run. They warn when the
   threshold lies within one IQR of the median, because there the rate is sensitive to small
   shifts.
5. **For trained policies, the unit under test is the recipe.** When the gate compares trained
   policies, rather than a fixed checkpoint or a scripted policy as today, each side is at least
   three training seeds of one recipe, evaluated on the same seeds and compared as pooled
   counts. Comparing one checkpoint with another mostly measures training noise.

Points 2 to 4 are implemented now in the generic core. Point 1 is a rule for task specs and
reports. Point 5 is the design for when the gate first judges a training recipe; it is not built
yet.

## Alternatives considered

- **Keep the pass/fail-only contract and always pair.** On a non-repeatable task the paired test
  loses its premise and its power, and nothing in the report would say so.
- **Gate on training's own success metric.** That is cheap and already logged, but on Lift it
  read 0.90 against 0.03 at spec, so it would have passed a policy that does not do the task.
- **One process per seed everywhere** (ADR 0033's approach). It removes coupling between
  episodes, such as Lift's success-monitored reset bank, but not divergence inside an episode, and
  it costs a process start per seed.
- **Force deterministic physics** (`deterministic_mode="run_to_run"` on Newton). This is
  promising for contact-rich tasks, but it costs memory and speed, and we have not tested it. It
  is a candidate fix for a task that fails the admission check, not a rule.
- **Several training seeds per side right now.** That would triple the GPU cost of every gate run
  before any PR trains a policy. We record the design now and build it with the first trained
  candidate.

## Consequences

- Reports become more honest about what a verdict can mean: paired or unpaired, how close the
  threshold sits to the typical error, and which spec was used.
- The results contract grows three optional fields. Existing evaluators keep working unchanged,
  and the checks run only when an evaluator provides the fields.
- Non-repeatable tasks need more episodes for the same power. That shows up as a longer
  evaluation or a wider interval, not as false confidence.
- Watch: a task whose repeatability changes after an upgrade. Re-running the admission check is
  part of every simulator or backend upgrade.
