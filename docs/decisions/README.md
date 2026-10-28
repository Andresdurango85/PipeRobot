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
| [0010](0010-main-branch-ruleset.md) | Main is protected by a ruleset; only the owner can bypass | Superseded by [0018](0018-no-required-review-for-the-owner.md) |
| [0011](0011-free-security-gates.md) | Free security gates: CodeQL, Dependabot, dependency review, ruff S rules | Accepted |
| [0012](0012-dependency-vulnerability-triage.md) | Override Pillow above LeRobot's cap; accept five unreachable advisories | Accepted |
| [0013](0013-pre-commit-hooks-mirror-ci.md) | Git hooks with prek; pre-push mirrors CI in a clean environment | Accepted |
| [0014](0014-mock-evaluator-and-pr-gate-workflow.md) | Mock evaluator and the pr-gate workflow, before the simulation exists | Accepted |
| [0015](0015-generic-core-vs-robot-specific.md) | Keep the generic gate core separate from SO-101-specific code | Accepted |
| [0016](0016-real-evaluator-lerobot-pusht.md) | First real evaluator: a pinned LeRobot policy in the PushT simulator, on CPU | Accepted |
| [0017](0017-pr-gate-pusht-on-github-runners.md) | pr-gate evaluates the PushT policy on GitHub-hosted runners, with CPU-only torch | Accepted |
| [0018](0018-no-required-review-for-the-owner.md) | Main needs a pull request and green checks, but no approving review | Accepted |

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
