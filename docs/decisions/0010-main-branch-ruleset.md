# 0010. Main is protected by a ruleset; only the owner can bypass

- Status: Accepted
- Date: 2026-10-27

## Context

The repo is public. Other people must not be able to change `main` without Andrés's approval,
but Andrés (and the agents acting with his account) must keep a fast path: pushing directly to
`main` when he decides to. Agents are not treated as "other people": they act as Andrés.

## Decision

A repository ruleset named `main` targets the default branch:

- Changes go through a pull request with 1 approving review; code owner review is required
  (`.github/CODEOWNERS` assigns everything to `@Andresdurango85`); new pushes dismiss stale
  approvals; review threads must be resolved.
- Required status checks, reported by GitHub Actions: `lint-and-test` and `dependency-review`.
- Code scanning results are required: CodeQL alerts of security severity high or above, or of
  severity error, block the merge ([0011](0011-free-security-gates.md)).
- No force pushes and no deletion of `main`.
- Bypass: the repository **admin** role, always. In a personal repo that is only the owner.
- Merged branches are deleted automatically.

## Alternatives considered

- Classic branch protection: older mechanism; rulesets are layered, visible to everyone who can
  read the repo, and editable through one API object.
- No bypass: Andrés could not push directly, which he asked to keep.
- A separate bot account for agents: not needed while agents act as Andrés; revisit if agents run
  unattended with broader permissions or if outside contributors join.

## Consequences

- Outside contributors can only reach `main` through a PR Andrés approves after the checks pass.
- PRs opened with Andrés's account cannot be approved by Andrés (GitHub forbids self-approval);
  he merges them through the bypass ("Merge without waiting for requirements", or
  `gh pr merge --admin`).
- Anything holding Andrés's token can also bypass: protect the token, and agents still follow the
  AGENTS.md rule of working through PRs.
- Renaming a CI job breaks a required check; update the ruleset in the same PR.
