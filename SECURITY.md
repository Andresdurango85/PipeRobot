# Security policy

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through GitHub:
[Security → Report a vulnerability](https://github.com/Andresdurango85/PipeRobot/security/advisories/new).

Include what you found, how to reproduce it, and its impact. You should get a first answer within
a week. This is a personal project in an early phase, so there is no bounty.

## Supported versions

Only the `main` branch is supported.

## Automated checks

Every pull request runs CodeQL (Python and GitHub Actions workflows), dependency review, and
ruff's security rules; Dependabot watches the dependencies. See
[ADR 0011](docs/decisions/0011-free-security-gates.md).
