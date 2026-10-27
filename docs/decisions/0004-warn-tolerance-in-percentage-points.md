# 0004. WARN tolerance of 10 pp; drops reported in pp

- Status: Accepted
- Date: 2026-10-26

## Context

The WARN verdict flags drops that are not significant but worth a look. With 50 episodes each
episode is worth 2 pp, so small drops are mostly noise. Simulation with an unchanged 80% policy:
a 5 pp tolerance raised WARN on ~25% of PRs, 10 pp on ~7%, 15 pp on ~1%. Separately, "dropped
14.0%" was ambiguous for 90% to 76% (relative or absolute?).

## Decision

- Default `--tolerance` is 0.10 (10 percentage points).
- Every drop and difference is reported in percentage points ("pp"), in the gate reason and in
  the PR comment.

## Alternatives considered

- 5 pp: one in four unchanged PRs would warn; people stop reading warnings (alert fatigue).
- 15 pp: almost never warns, so it adds little over BLOCK.
- Relative drops (%): ambiguous next to rates that are already percentages.

## Consequences

- ~7% of unchanged PRs still show WARN with 50 episodes; revisit when the episode count or the
  baseline size changes.
- The tolerance is a single constant (`DEFAULT_TOLERANCE`) and a CLI flag.
