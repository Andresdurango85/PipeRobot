# 0040. Fuzz the untrusted-input parsers with atheris on hosted runners

- Status: Accepted
- Date: 2026-11-05

## Context

OpenSSF Scorecard's Fuzzing check gives us 0/10. In Scorecard v5.6.0 (`checks/raw/fuzzing.go`) the
check is binary and has two independent triggers:

- a `.clusterfuzzlite/Dockerfile` with at least one line that is not a comment;
- the literal regex `import atheris` in any `*.py` file, when Python is a prominent language.
  Ours is: Python 705k lines, HTML 23k.

Hypothesis tests are not detected for Python, and neither is `from atheris import ...`.

Beyond the score, several parsers read input produced outside the process that trusts them:

- `results.json` from CI artifacts;
- `history.json` and its records, from the `history` branch;
- Sigstore bundles;
- the Isaac task and policy specs;
- the SO-101 video selection and rerun files, written by PR-branch code on the self-hosted
  runner.

Their output feeds the signed history and the PR comments. A hand probe on 2026-11-05 found
inputs that escaped every one of them: `RecursionError` on deep JSON, `UnicodeDecodeError`,
`AttributeError`/`TypeError` on wrong shapes. They were fixed test-first in #84
([testing.md](../knowledge/testing.md)). Writing the harnesses found one more class: error
messages that rendered an untrusted nested value with `repr` raised `RecursionError`. The affected
inputs were an episode missing `"success"`, a non-bool `"success"`, a baseline count, a paired
verdict and a policy's `prepare`. They were fixed test-first in this ADR's PR. Coverage-guided
fuzzing should find the next ones before an artifact does.

Two facts constrain the tooling:

- OSS-Fuzz's `base-builder` image, which ClusterFuzzLite builds on, compiles Python 3.11.13 and
  pip-installs atheris into it. This project requires Python `>=3.12,<3.13`, and `uv.lock`
  resolves for 3.12.
- atheris 3.1.0 (June 2026) ships manylinux x86_64 wheels for CPython 3.12 to 3.14 and nothing
  for Windows.

## Decision

- **atheris harnesses run by a workflow on GitHub-hosted runners**; no ClusterFuzzLite, no
  Docker.
- **Harnesses** live in `fuzz/`.
  - `fuzz/targets.py` holds one plain function per target (no atheris import).
  - `fuzz/fuzz_<target>.py` wraps each with `atheris.Setup`.
  - Every harness has the literal top-level line `import atheris`, and a test enforces it, so
    that a refactor cannot silently drop the Scorecard trigger.
  - One harness drives an existing-style Hypothesis strategy through
    `@given(...).hypothesis.fuzz_one_input`, for structure-aware inputs.
- **Targets and their contract**: `load_results` (`ResultsError`), `load_history` and
  `HistoryRecord.from_dict` (`HistoryError`), the certificate bundle reader
  (`CertificateInputError`), isaaclab `specs.read_object` (`ResultsError`), and
  `video_manifest.build_manifest` (`VideoInputError`). Each target calls the entry point as
  production does and accepts only that error.
- **False-positive policy**:
  - A crash on a documented exception type is a harness bug: fix the harness, never the parser.
  - Any other exception is a real crash. Write a regression test from the reproducer, show that it
    fails, then fix the parser at the parse boundary only (the read, `json.loads`, explicit shape
    checks; never a broad `except ValueError`). Error messages name the field and the type of
    an untrusted value, never its `repr`.
- **Seed corpus**: committed in `fuzz/corpus/<target>/`.
  - Small (a test caps it at 64 KiB), derived from existing golden and test data.
  - Never CI artifacts or videos.
  - The corpus a run grows is discarded.
- **Workflow `fuzz.yml`**:
  - Triggers: `pull_request` on the parsers' paths, a weekly `schedule`, and `workflow_dispatch`.
  - Hosted `ubuntu-26.04`, one matrix job per harness.
  - Time: 60 s per harness on a PR, 10 min per harness on the schedule.
  - Permissions: top-level `permissions: {}`, the job gets `contents: read`.
  - A crash fails the job and uploads its reproducer as an artifact.
  - It never runs on the self-hosted runner; a test checks it. `pull_request` is safe here because
    the job is hosted and read-only ([0027](0027-self-hosted-runner-push-only-and-pinned-actions.md)
    restricts the self-hosted runner).
- **Dependency**: `atheris` in a `fuzz` dependency group with the marker
  `sys_platform == 'linux' and platform_machine == 'x86_64'`, hash-pinned in `uv.lock`
  ([0002](0002-python-tooling-and-pinning.md)). Only the fuzz job installs it; Windows machines and
  the self-hosted runner never do.
- `tests/test_fuzz_targets.py` runs every target over its corpus and a few hostile inputs without
  atheris, so the targets are also exercised on Windows and in `lint-and-test`.

## Alternatives considered

- **ClusterFuzzLite** (`.clusterfuzzlite/` plus its GitHub actions):
  - It brings corpus pruning, crash deduplication and SARIF.
  - But its Python images run 3.11. We would maintain a Dockerfile that builds Python 3.12 from
    source and rebuilds atheris against clang's fuzzer runtime, inside a base image that changes
    under us, and pin its pip installs by hash to keep Pinned-Dependencies at 10.
  - It is slow and fragile, for the same score. Rejected while the base images lack 3.12.
- **OSS-Fuzz**: the same images, and it needs project acceptance; out of scope for Phase 0.
- **Hypothesis alone**: we already use it for properties. It is not coverage-guided and Scorecard
  does not count it, so it stays complementary.
- **A persistent corpus** (a data branch like `history`): useful once the weekly run finds
  interesting inputs. Not needed to start; revisit if the seed corpus plateaus.

## Consequences

- Scorecard Fuzzing goes from 0 to 10, read through the API after the merge.
- A PR that touches the parsers waits about 5 more minutes on hosted runners. `fuzz.yml` is not a
  required check.
- Crash triage:
  - A weekly crash shows up as a failed scheduled run with its reproducer.
  - Someone must turn it into a regression test and a fix, under the policy above.
- The harnesses cannot run on Windows (no atheris wheel); the pytest smoke test covers the targets
  there.
- atheris is one more Linux-only dependency to keep current. Revisit ClusterFuzzLite if OSS-Fuzz's
  images move to Python 3.12 or later.
- Open question, for Andrés and not part of this decision: `EpisodeResult.from_dict` still accepts
  non-integer seeds (`3.7` becomes 3, `true` becomes 1, bytes are parsed). That is not a crash,
  so the fuzz policy does not cover it, but silently truncating a seed is a reproducibility risk.
  Should a non-integer seed be rejected?
