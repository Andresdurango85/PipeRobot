# 0009. Unusable data never gives a green result

- Status: Accepted
- Date: 2026-10-26

## Context

Running `eval/dataset_stats.py` on public SO-101 datasets found a dataset whose `info.json`
reported 0 episodes (data uploaded, metadata never finalized), and the script exited 0: a false
green. Other datasets could not be loaded at all (old v2.1 format, missing version tag) and
crashed with a traceback.

## Decision

Every tool in the gate distinguishes three outcomes with exit codes:

- 0: data loaded and passed the sanity checks.
- 1: data loaded but failed a sanity check (e.g. no episodes, inconsistent counts).
- 2: data could not be loaded; print one clear error line, no traceback.

## Alternatives considered

- Only warnings on stdout: CI only looks at exit codes, so the green would stand.
- Let exceptions propagate: the job fails, but the cause is buried in a traceback and cannot be
  told apart from a bug in our code.

## Consequences

- Empty or malformed inputs are caught before they reach the statistics.
- New tools (evaluation runner, baseline builder) must follow the same convention.
