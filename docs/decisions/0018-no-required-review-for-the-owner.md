# 0018. Main needs a pull request and green checks, but no approving review

- Status: Accepted
- Date: 2026-10-28

## Context

[0010](0010-main-branch-ruleset.md) required 1 approving code-owner review on every PR. All PRs
come from Andrés's account (his own work and agents acting as him), and GitHub forbids
self-approval, so every merge needed the admin bypass (`gh pr merge --admin`). Claude Code's
permission classifier refuses that bypass even with Andrés's standing authorization, so every
merge waited for him to click it by hand. The review rule protected nothing extra: only accounts
with write access can merge, and that is only Andrés.

## Decision

The `main` ruleset keeps everything from 0010 except the review requirement:

- A pull request is still required; required approving reviews: 0; code owner review and
  dismissing stale approvals: off. Review threads must still be resolved.
- Unchanged: required checks `lint-and-test`, `dependency-review` and `pr-gate`; CodeQL
  thresholds; no force pushes or deletion; admin bypass; branches deleted after merge.

## Alternatives considered

- Keep the review rule and merge by hand: every PR waits for a click, including agent PRs that
  Andrés already authorized.
- A bot account that approves agent PRs: an extra credential to protect, for a review nobody
  reads; revisit if outside contributors get write access.

## Consequences

- PRs merge with a plain `gh pr merge --merge` once the checks pass; no bypass needed.
- If someone else ever gets write access, restore a required review (e.g. code owner) first.
- Agents still work through PRs (AGENTS.md); the gate and the checks are now the only thing
  between a PR and `main`, which is the point of the project.
