# 0011. Free security gates: CodeQL, Dependabot, dependency review, ruff S rules

- Status: Accepted
- Date: 2026-10-27

## Context

A quality gate for robot code should itself be held to a security standard. The repo is public,
so GitHub's security features are free for it. The dependency tree is large (LeRobot pulls torch
and ~90 packages) and the workflows will soon run on a self-hosted runner on a personal PC, where
a workflow injection would be costly.

## Decision

| Gate | What it catches | When |
| --- | --- | --- |
| CodeQL, default setup (Python + GitHub Actions) | Vulnerable code patterns and workflow injection | Every PR, pushes to `main`, weekly |
| Dependabot alerts + security updates | Known CVEs in dependencies; opens fix PRs | Continuous (repo settings) |
| Dependabot version updates (`.github/dependabot.yml`) | Outdated uv dependencies and Actions | Weekly, grouped PRs |
| Dependency review (`dependency-review.yml`) | PRs that add a dependency with a known high or critical vulnerability | Every PR |
| ruff `S` rules (flake8-bandit) | Insecure Python patterns (`eval`, `pickle`, shell subprocess, hardcoded secrets…) | Local and CI, part of `lint-and-test` |
| Secret scanning + push protection | Committed credentials | Every push (on by default for public repos) |
| Private vulnerability reporting + `SECURITY.md` | A private channel for external reports | — |

CodeQL alerts (high or above, or error) and the two status checks block merges through the
ruleset ([0010](0010-main-branch-ruleset.md)).

## Alternatives considered

- CodeQL advanced setup (a workflow file in the repo): versioned and customizable, but needs
  maintenance; default setup is maintained by GitHub and enough for now. Switch if we need custom
  queries or a specific schedule.
- Snyk, SonarCloud, Semgrep Cloud: free tiers exist, but they add accounts and tokens and overlap
  with what GitHub gives natively.
- pip-audit / OSV-Scanner in CI: overlaps with Dependabot alerts and dependency review; can add
  later to scan the full lockfile on every run.
- OpenSSF Scorecard: a useful posture score; not a gate. Possible follow-up.

## Consequences

- Dependabot will open weekly PRs; each one goes through the same gates.
- Findings that are false positives are silenced inline with a reason (e.g.
  `# noqa: S105 - a verdict name, not a password`), never by disabling a rule globally.
- Tests ignore `S101` (assert) and `S311` (seeded `random` for Monte Carlo checks).
