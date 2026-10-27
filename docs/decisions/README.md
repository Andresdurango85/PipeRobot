# Architecture Decision Records

One file per decision: why we chose something, what else we considered, and what it costs.
ADRs are **immutable** once accepted. To change a decision, write a new ADR and mark the old one
`Superseded by NNNN`. `tests/test_docs.py` checks the format and that this index is complete.

## Index

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-memory-system-in-repo.md) | Project memory lives in the repo | Accepted |
| [0002](0002-python-tooling-and-pinning.md) | uv, Python 3.12, LeRobot pinned as an optional extra | Accepted |
| [0003](0003-statistical-gate-wilson-newcombe.md) | Gate verdict from Wilson and Newcombe intervals | Accepted |
| [0004](0004-warn-tolerance-in-percentage-points.md) | WARN tolerance of 10 pp; drops reported in pp | Accepted |
| [0005](0005-two-machine-setup.md) | Home PC with RTX for heavy work, laptop for travel | Accepted |
| [0006](0006-apache-2-license.md) | Apache-2.0 license | Accepted |
| [0007](0007-lf-line-endings.md) | LF line endings on every machine | Accepted |
| [0008](0008-sticky-pr-comment-and-golden-file.md) | Sticky PR comment, tested with a golden file | Accepted |
| [0009](0009-fail-loudly-on-unusable-data.md) | Unusable data never gives a green result | Accepted |

## Template

Copy to `NNNN-short-kebab-title.md` with the next free number, then add it to the index.

```markdown
# NNNN. Title in a few words

- Status: Proposed | Accepted | Deprecated | Superseded by NNNN
- Date: YYYY-MM-DD

## Context

What problem or force makes this decision necessary. Facts, numbers, links.

## Decision

What we do, stated so that someone can check whether the code follows it.

## Alternatives considered

- Option: why not.

## Consequences

What gets easier, what gets harder, what we must watch.
```
