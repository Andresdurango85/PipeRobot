# 0025. Type-check the piperobot package with mypy --strict

- Status: Accepted
- Date: 2026-11-02

## Context

The gate's verdict is only as trustworthy as the code that computes it. Ruff's `ANN` rules
already require annotations, but nothing checked that the annotations are right: a function
declared to return `SuccessCount` could return a `dict`, and only a test that happens to cover
that path would notice. Other repos install the `piperobot` package
([0019](0019-core-adapters-robots-layout.md)), so its types are part of its contract.

The LeRobot adapter imports `lerobot` and `huggingface_hub` lazily, inside functions. Both come
only with the `lerobot` extra (torch, several GB), which the lint-and-test environment does not
install ([0002](0002-python-tooling-and-pinning.md), [0013](0013-pre-commit-hooks-mirror-ci.md)).

Measured on `main` (68906ef) with mypy 2.4.1: `--strict` on `piperobot/` reports 5 errors, all
`import-not-found` for those lazy imports, and none in our own code.

## Decision

- **mypy, strict**, pinned in the uv `dev` group, configured in `pyproject.toml`
  (`[tool.mypy]`: `packages = ["piperobot"]`, `strict = true`). `uv run mypy` checks the package.
- **Optional dependencies**: one `[[tool.mypy.overrides]]` sets `ignore_missing_imports` for
  `lerobot.*` and `huggingface_hub.*` only, so their API is typed as `Any` while the adapter's own
  code stays strictly checked. The `hub` tests exercise the real API.
- **Scope**: the installable package only. `tests/` and `robots/` are not checked yet.
- **Hooks mirror CI**: a pre-push hook `ci-mypy` runs `uv run --isolated --locked mypy`. Without
  the extra, like CI, an installed `lerobot` or `huggingface_hub` cannot hide or add errors
  locally. CI runs it as its own `type-check` job in `ci.yml`.
- Any `# type: ignore` needs an error code and a comment saying why. Strict mode's
  `warn_unused_ignores` flags the ones that stop being needed.

## Alternatives considered

- pyright (strict): a faster checker with better inference, but its PyPI package (1.1.414) is a
  wrapper that downloads Node at runtime with `nodeenv` when Node is missing, then installs the
  pyright npm package with `npm`. The checker itself would sit outside `uv.lock`, invisible to
  Dependabot and dependency review, and could not run in Codex's offline sandbox
  ([0023](0023-codex-writes-code-claude-reviews.md)).
- basedpyright: bundles Node through a wheel, but it is a fork with its own defaults, and it
  would be a second Node-based toolchain in a Python repo for no gain on code that already passes
  mypy strict.
- Installing the `lerobot` extra in the type-check job so mypy sees real types: several GB per
  run for one adapter. LeRobot does not ship `py.typed` in 0.6.1, so mypy would treat it as
  untyped anyway.
- Stub packages for LeRobot: we would maintain them by hand for an API we call in two places.
- Excluding the adapters from the check: their own code would go unchecked to hide two imports.
- Also checking `tests/` and `robots/` now: `tests/` has 8 errors in 2 files (optional `numpy`
  and `PIL` imports, an SO-101 test fixture) and `robots/` has 30 in 7 files, in code that other
  sessions are changing. Left for a later PR.

## Consequences

- A wrong return type or a missing `None` check in `piperobot/` fails the push and CI.
- Calls into LeRobot and the Hub are unchecked (`Any`); a LeRobot upgrade still needs
  `pytest -m hub`.
- Pushing costs ~3 s more with a warm cache, ~5 s cold (mypy's cache lives in `.mypy_cache/`).
- When the package gains a new optional dependency imported lazily, add it to the override.
