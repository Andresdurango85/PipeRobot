# Contributing to PipeRobot

PipeRobot is a CI quality gate for robot policies ([README](README.md)). Bug reports, ideas,
documentation and code are welcome. It is a personal project in an early phase, so a review can
take a few days.

## Report a bug or request a feature

Open a [GitHub issue](https://github.com/Andresdurango85/PipeRobot/issues). For a bug, include
the command you ran, your OS, what you expected and what happened (the output or the failing CI
run). Feature ideas and questions go in issues too.

**Do not report a security vulnerability in a public issue.** Follow [SECURITY.md](SECURITY.md).

## Set up

You need git and [uv](https://docs.astral.sh/uv/getting-started/installation/); uv installs
Python 3.12 itself.

```
uv sync                  # ruff, mypy, pytest, prek, zizmor
uv run prek install      # once per clone: the git hooks, which mirror CI
```

The simulators are optional and heavy (`uv sync --extra lerobot`, several GB). You only need them
to change an evaluator; the README's 30-minute path shows how.

## Run the checks

```
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run prek run --all-files --hook-stage pre-push   # what CI's lint-and-test job runs
```

`uv run pytest` includes `tests/test_docs.py`, which checks the documentation's links and the
ADR format. Tests that need the network are marked and skipped by default (`-m hub`, `-m github`).
Do not bypass the hooks (`--no-verify`): if one fails, fix the cause.

## Code standards

- Typed Python 3.12. ruff (lint, including its security rules, and format; line length 100) and
  mypy in strict mode define the style; `pyproject.toml` holds their configuration.
- Dependencies are pinned in `uv.lock`
  ([ADR 0002](docs/decisions/0002-python-tooling-and-pinning.md)).
- The generic gate core stays free of robot- and framework-specific code: that lives in
  `piperobot/adapters/` and `robots/`
  ([ADR 0015](docs/decisions/0015-generic-core-vs-robot-specific.md),
  [ADR 0019](docs/decisions/0019-core-adapters-robots-layout.md)); a test enforces it.
- Code, comments, commits and documentation are in English.

## Tests

- New behaviour comes with tests in `tests/`.
- A bug fix starts with a regression test that fails on the current code; then the fix.
- Golden files (`tests/golden/`) change only on purpose: regenerate them with
  `UPDATE_GOLDEN=1 uv run pytest` and review the diff.
- CI must be green. `main` requires `lint-and-test`, `dependency-review`, `pr-gate` and
  `so101-gate-verdict`; CodeQL, zizmor and the type check run on every pull request too.
- More on how the gate's own code is tested: [docs/knowledge/testing.md](docs/knowledge/testing.md).

## Branches and pull requests

- Never push to `main`: it accepts changes only through pull requests, with no force-push.
- Work on a branch (or a fork), one topic per pull request, in small steps.
- Fill in the [pull request template](.github/pull_request_template.md). A non-trivial decision
  gets an ADR in [docs/decisions/](docs/decisions/README.md); a verified fact or gotcha gets a
  dated entry in [docs/knowledge/](docs/knowledge/README.md).

## License

PipeRobot is licensed under [Apache-2.0](LICENSE). Under section 5 of that license, a
contribution you submit for inclusion is licensed under the same terms, unless you state
otherwise.

## AI agents

Agents (and anyone who wants the full project rules) start with [AGENTS.md](AGENTS.md).
