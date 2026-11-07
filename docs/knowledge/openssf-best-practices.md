# OpenSSF Best Practices badge: passing-level answer sheet

Answers for the [OpenSSF Best Practices](https://www.bestpractices.dev/) "passing" form, one row
per criterion, ready to paste. The maintainer fills in the form with the maintainer's personal
GitHub account; nothing here is submitted automatically.

- **Source**: the live criteria list at <https://www.bestpractices.dev/en/criteria/0> (with
  details) and the badge's own
  [`criteria/criteria.yml`](https://github.com/coreinfrastructure/best-practices-badge/blob/main/criteria/criteria.yml)
  for which answers allow N/A or require a URL. Fetched 2026-11-06: **67 criteria** (43 MUST,
  10 SHOULD, 14 SUGGESTED), none obsolete or future.
- **Why it matters**: Scorecard's CII-Best-Practices check (0 today) gives 2 for a badge in
  progress, 5 for passing, 7 for silver, 10 for gold (Scorecard v5.6.0,
  `checks/evaluation/cii_best_practices.go`). It finds the badge by the repository URL.
- **Evidence URLs** point at `main`. "MUST" rows decide the badge: one Unmet MUST means no
  passing badge. SHOULD and SUGGESTED rows can stay Unmet.

`B` below stands for `https://github.com/Andresdurango85/PipeRobot/blob/main`.

## Open decisions for Andrés

These need a statement or a choice only the maintainer can make. Every other row is a fact
checked against the repository on 2026-11-06.

1. **Releases** (`version_unique`, `release_notes`; also `version_semver`, `version_tags`). The
   repository has no tags and no releases; `pyproject.toml` says `0.1.0`, never published.
   - **Option A, no release**: `version_unique` Met by commit IDs (the details allow them, and
     every certificate and history record names its commit), `release_notes` N/A. The form
     allows N/A only for results "not intended for reuse in multiple locations" that use
     continuous delivery. The `piperobot` package is meant to be reused by a second robot's
     repository ([ADR 0019](../decisions/0019-core-adapters-robots-layout.md)), so this N/A is a
     stretch and a reviewer may reject it.
   - **Option B, a first release** (proposed, not done): tag `v0.1.0` on `main` and publish a
     GitHub Release whose notes are a short hand-written summary (not `git log`). Then
     `version_unique`, `version_semver`, `version_tags` and `release_notes` are all Met.
     Later releases need notes too, so it is a small standing commitment.
2. **Secure-development knowledge** (`know_secure_design`, `know_common_errors`). Both are
   statements about the primary developer, so only Andrés can answer them. The rows below give
   a draft built from what the repository shows; confirm or rewrite it.
3. **Private vulnerability-report contact** (`vulnerability_report_private`). GitHub's private
   vulnerability reporting is enabled and `SECURITY.md` points to it; that is enough for Met.
   An e-mail address as a second channel is optional, and it would be public.
4. **Accepted dependency advisories** (`vulnerabilities_fixed_60_days`). Five advisories in
   the optional `lerobot` extra's dependencies are dismissed as unreachable
   ([ADR 0012](../decisions/0012-dependency-vulnerability-triage.md)), one of them high
   (fsspec). The criterion covers the project's own vulnerabilities, so the answer below is Met,
   but confirm you are comfortable stating it.

## Basics

| Criterion | Level | Answer | Justification (paste) | Evidence |
| --- | --- | --- | --- | --- |
| `description_good` | MUST | Met | PipeRobot is a CI quality gate for robot policies: on every pull request it runs the policy in simulation many times, compares its success rate with a stored baseline using confidence intervals, and blocks the PR if it regressed. | `B/README.md` |
| `interact` | MUST | Met | The README explains how to get and run it; CONTRIBUTING.md explains how to report bugs and request features (GitHub issues) and how to contribute (pull requests). | `B/CONTRIBUTING.md` |
| `contribution` | MUST | Met | Contributions are GitHub pull requests from a branch or fork; CONTRIBUTING.md describes the flow and the checks `main` requires. | `B/CONTRIBUTING.md#branches-and-pull-requests` |
| `contribution_requirements` | SHOULD | Met | CONTRIBUTING.md lists the requirements: typed Python checked by ruff and strict mypy, tests with every new behaviour, regression tests before fixes, green CI. | `B/CONTRIBUTING.md#code-standards` |
| `floss_license` | MUST | Met | Apache-2.0. | `B/LICENSE` |
| `floss_license_osi` | SUGGESTED | Met | Apache-2.0 is OSI-approved. | `B/LICENSE` |
| `license_location` | MUST | Met | The license is in `LICENSE` at the repository root. | `B/LICENSE` |
| `documentation_basics` | MUST | Met | The README's "Reproduce the gate in 30 minutes" covers installing, running and reading the gate, and CI runs those exact commands on Linux and Windows so they cannot drift. SECURITY.md and the runner ADRs cover secure use. | `B/README.md` |
| `documentation_interface` | MUST | Met | Each command-line tool documents its options with `--help`; module READMEs document the gate, report and evaluator CLIs with their exit codes; the results-file contract is in ADR 0014 and the module docstring (`python -m pydoc piperobot.results`); the certificate format is in `docs/attestations/`. | `B/piperobot/stats/README.md` |
| `sites_https` | MUST | Met | The repository and the GitHub Pages history site are served over HTTPS only. | `https://github.com/Andresdurango85/PipeRobot` |
| `discussion` | MUST | Met | GitHub issues and pull requests: searchable, URL-addressable, open to anyone with a free account, no proprietary client needed. | `https://github.com/Andresdurango85/PipeRobot/issues` |
| `english` | SHOULD | Met | All documentation, code and reviews are in English (`docs/learning/` holds the maintainer's personal course notes in Spanish). | `B/AGENTS.md` |
| `maintained` | MUST | Met | Under active development: several merged pull requests a week. | `https://github.com/Andresdurango85/PipeRobot/commits/main` |

`documentation_interface` is the weakest Met: the results contract has no reference page of its
own outside ADR 0014 and a docstring. A short `docs/reference/results.md` would make it solid.

## Change control

| Criterion | Level | Answer | Justification (paste) | Evidence |
| --- | --- | --- | --- | --- |
| `repo_public` | MUST | Met | Public GitHub repository. | `https://github.com/Andresdurango85/PipeRobot` |
| `repo_track` | MUST | Met | Git records every change with its author and date. | `https://github.com/Andresdurango85/PipeRobot/commits/main` |
| `repo_interim` | MUST | Met | Every change lands through a public pull request; all interim commits are in the repository. | `https://github.com/Andresdurango85/PipeRobot/pulls?q=is%3Apr` |
| `repo_distributed` | SUGGESTED | Met | Git. | |
| `version_unique` | MUST | Decision 1 | Option A: every evaluation, certificate and history record is identified by its git commit ID. Option B: release `v0.1.0`. | |
| `version_semver` | SUGGESTED | Unmet (Met with option B) | No releases yet; `pyproject.toml` uses SemVer (`0.1.0`). | `B/pyproject.toml` |
| `version_tags` | SUGGESTED | Unmet (Met with option B) | No release tags yet. | |
| `release_notes` | MUST | Decision 1 | Option A: N/A (weak, see above). Option B: the GitHub Release notes of `v0.1.0`. | |
| `release_notes_vulns` | MUST | N/A | No releases and no publicly known vulnerability in the project's own code. | |

## Reporting

| Criterion | Level | Answer | Justification (paste) | Evidence |
| --- | --- | --- | --- | --- |
| `report_process` | MUST | Met | Bugs are reported as GitHub issues, as CONTRIBUTING.md explains. | `B/CONTRIBUTING.md#report-a-bug-or-request-a-feature` |
| `report_tracker` | SHOULD | Met | GitHub issues. | `https://github.com/Andresdurango85/PipeRobot/issues` |
| `report_responses` | MUST | Met | No bug reports have been filed by others yet; the maintainer acknowledges new ones. | `https://github.com/Andresdurango85/PipeRobot/issues?q=is%3Aissue` |
| `enhancement_responses` | SHOULD | Met | No enhancement requests have been filed yet; the maintainer answers new ones. | `https://github.com/Andresdurango85/PipeRobot/issues?q=is%3Aissue` |
| `report_archive` | MUST | Met | GitHub issues and pull requests are public and searchable. | `https://github.com/Andresdurango85/PipeRobot/issues?q=is%3Aissue` |
| `vulnerability_report_process` | MUST | Met | SECURITY.md describes how to report a vulnerability. | `B/SECURITY.md` |
| `vulnerability_report_private` | MUST | Met (decision 3) | Reports go privately through GitHub's private vulnerability reporting (Security → Report a vulnerability), which is enabled. | `B/SECURITY.md` |
| `vulnerability_report_response` | MUST | N/A | No vulnerability reports received in the last 6 months. SECURITY.md promises a first answer within a week. | |

`report_responses` has no N/A option. With no issues ever filed by others it is met vacuously;
say so in the justification rather than implying a track record.

## Quality

| Criterion | Level | Answer | Justification (paste) | Evidence |
| --- | --- | --- | --- | --- |
| `build` | MUST | Met | `uv sync` builds and installs the `piperobot` package from source (PEP 517, `uv_build` backend) with its locked dependencies. | `B/pyproject.toml` |
| `build_common_tools` | SUGGESTED | Met | Standard `pyproject.toml` built by uv. | `B/pyproject.toml` |
| `build_floss_tools` | SHOULD | Met | uv and `uv_build` are FLOSS (MIT/Apache-2.0). | |
| `test` | MUST | Met | pytest suite in `tests/`, run with `uv run pytest`, documented in CONTRIBUTING.md and run by CI on every pull request. | `B/CONTRIBUTING.md#run-the-checks` |
| `test_invocation` | SHOULD | Met | The standard `pytest` command (`uv run pytest`). | `B/pyproject.toml` |
| `test_most` | SUGGESTED | Unmet | Not measured: there is no coverage tool. Property-based tests, golden files, mutation testing of `piperobot/stats` and fuzzing of the parsers cover the core, but no figure backs "most branches". To meet it: add branch coverage to CI and report it. | `B/docs/knowledge/testing.md` |
| `test_continuous_integration` | SUGGESTED | Met | GitHub Actions runs the tests, type check and static analysis on every pull request; `main` requires them. | `B/.github/workflows/ci.yml` |
| `test_policy` | MUST | Met | New behaviour comes with tests, and bug fixes start with a failing regression test (CONTRIBUTING.md, Tests). | `B/CONTRIBUTING.md#tests` |
| `tests_are_added` | MUST | Met | Recent major changes added tests with the code: the parser fuzzing (#85), the untrusted-input hardening with test-first regression tests (#84), the vulnerability-scanner config (#83). | `https://github.com/Andresdurango85/PipeRobot/pull/85` |
| `tests_documented_added` | SUGGESTED | Met | The test policy is in CONTRIBUTING.md and the pull request template's checklist. | `B/CONTRIBUTING.md#tests` |
| `warnings` | MUST | Met | ruff (pycodestyle, pyflakes, bugbear, flake8-bandit and others) and mypy in strict mode. | `B/pyproject.toml` |
| `warnings_fixed` | MUST | Met | CI fails on any ruff or mypy finding, so none are outstanding; each suppression is an inline `noqa` with its reason. | `B/.github/workflows/ci.yml` |
| `warnings_strict` | SUGGESTED | Met | mypy `strict = true` and ruff's type-annotation and security rules. `robots/` and a few SO-101 tests are not type-checked yet; that is tracked as a next step. | `B/pyproject.toml` |

## Security

| Criterion | Level | Answer | Justification (paste) | Evidence |
| --- | --- | --- | --- | --- |
| `know_secure_design` | MUST | Decision 2 | Draft: the primary developer applies least privilege (read-only or empty default permissions in every workflow, write scopes only on the jobs that need them, a push-only self-hosted runner), fail-safe defaults (a gate that blocks on invalid input), limited attack surface and allowlist input validation at the parse boundary, and open design (certificates anyone can verify). | `B/docs/decisions/0027-self-hosted-runner-push-only-and-pinned-actions.md` |
| `know_common_errors` | MUST | Decision 2 | Draft: the primary developer knows the common errors for this kind of software and counters each: untrusted input (typed parsing, fuzzing), injection in CI workflows (zizmor, environment variables instead of `${{ }}` in scripts), command injection (fixed argument lists, no shell), supply-chain attacks (SHA-pinned actions, hash-pinned lockfile, Dependabot, dependency review), leaked secrets (secret scanning with push protection). | `B/docs/decisions/0040-fuzz-untrusted-parsers-with-atheris.md` |
| `crypto_published` | MUST | Met | Only published algorithms: SHA-256 digests and Sigstore signatures (ECDSA), through GitHub artifact attestations. | `B/docs/decisions/0030-signed-certificates-of-evaluation.md` |
| `crypto_call` | SHOULD | Met | No cryptography is implemented here: hashing uses Python's `hashlib`, and signing and verification are delegated to GitHub's attestation actions and `gh attestation verify`. | `B/piperobot/reports/certificate.py` |
| `crypto_floss` | MUST | Met | `hashlib`, the `gh` CLI and Sigstore are FLOSS. | |
| `crypto_keylength` | MUST | N/A | The software configures no keys: signing uses short-lived Sigstore certificates issued outside this project. | |
| `crypto_working` | MUST | Met | SHA-256 and ECDSA only; no MD4, MD5, single DES, RC4 or Dual_EC_DRBG. | `B/piperobot/reports/certificate.py` |
| `crypto_weaknesses` | SHOULD | Met | No SHA-1 or other weak algorithm in any security mechanism. | |
| `crypto_pfs` | SHOULD | N/A | The software implements no key-agreement protocol; TLS is handled by the platform. | |
| `crypto_password_storage` | MUST | N/A | The software stores no passwords. | |
| `crypto_random` | MUST | N/A | The software generates no keys or nonces. The mock evaluator's seeded `random.Random` simulates outcomes and is not a security mechanism. | |
| `delivery_mitm` | MUST | Met | Delivered from GitHub over HTTPS or SSH; dependencies come from PyPI over HTTPS and are hash-checked against `uv.lock`. | `B/uv.lock` |
| `delivery_unsigned` | MUST | Met | No hash is retrieved over HTTP: dependency hashes are committed in `uv.lock` and GitHub Actions are pinned by commit SHA. | `B/uv.lock` |
| `vulnerabilities_fixed_60_days` | MUST | Met (decision 4) | No unpatched medium-or-higher vulnerability in the project's own code. Five advisories in dependencies of the optional `lerobot` extra are documented as unreachable here, with a review date. | `B/docs/decisions/0012-dependency-vulnerability-triage.md` |
| `vulnerabilities_critical_fixed` | SHOULD | Met | No critical vulnerability is open; the critical Pillow advisories were fixed by overriding LeRobot's version cap. | `B/docs/decisions/0012-dependency-vulnerability-triage.md` |
| `no_leaked_credentials` | MUST | Met | No credentials in the repository; CI secrets live in GitHub Actions, and secret scanning with push protection is enabled. | `B/SECURITY.md` |

## Analysis

| Criterion | Level | Answer | Justification (paste) | Evidence |
| --- | --- | --- | --- | --- |
| `static_analysis` | MUST | Met | CodeQL (Python and GitHub Actions), ruff with its flake8-bandit security rules, strict mypy and zizmor run on every pull request and every push to `main`, so every change is analysed before it merges. | `B/SECURITY.md` |
| `static_analysis_common_vulnerabilities` | SUGGESTED | Met | CodeQL's security queries, ruff's flake8-bandit rules and zizmor's workflow-injection audits look for common vulnerabilities. | `B/docs/decisions/0011-free-security-gates.md` |
| `static_analysis_fixed` | MUST | Met | No static-analysis vulnerability is open. The open code-scanning alerts are Scorecard posture checks (branch protection, code review, maintained, this badge), not code findings. | `https://github.com/Andresdurango85/PipeRobot/security/code-scanning` |
| `static_analysis_often` | SUGGESTED | Met | On every pull request and every push to `main`. | `B/.github/workflows/zizmor.yml` |
| `dynamic_analysis` | SUGGESTED | Met | Coverage-guided fuzzing with atheris of every parser of untrusted input, on parser pull requests and weekly, plus Hypothesis property tests and mutation testing. | `B/.github/workflows/fuzz.yml` |
| `dynamic_analysis_unsafe` | SUGGESTED | N/A | The project's code is Python only, a memory-safe language. | |
| `dynamic_analysis_enable_assertions` | SUGGESTED | Met | Tests and fuzz harnesses run with Python assertions enabled (never `-O`). | `B/.github/workflows/fuzz.yml` |
| `dynamic_analysis_fixed` | MUST | Met | Inputs that escaped a parser's documented error were fixed test-first (#84, #85) under a written policy; none is open. | `B/docs/decisions/0040-fuzz-untrusted-parsers-with-atheris.md` |

_(verified 2026-11-06: bestpractices.dev criteria/0 and `criteria.yml`; repository settings and
alerts through the GitHub API; Scorecard v5.6.0 source)_
