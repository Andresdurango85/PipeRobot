# Testing the gate's own code

How we check that the gate itself is correct: type checking, and (next) property-based and
mutation tests for `piperobot/stats`.

## Type checking (mypy)

- **`uv run mypy`** checks the `piperobot` package in strict mode, configured in
  `pyproject.toml` (`[tool.mypy]`), and runs as the pre-push hook `ci-mypy` and the `type-check`
  job in `ci.yml` ([ADR 0025](../decisions/0025-mypy-strict-type-checking.md)).
  `tests/` and `robots/` are not checked. _(verified 2026-11-02, mypy 2.4.1)_
- **On `main` at 68906ef, `--strict` found no errors in our own code**: only 5
  `import-not-found` errors, for the lazy `lerobot` and `huggingface_hub` imports in
  `piperobot/adapters/lerobot/policy.py`. A per-module `ignore_missing_imports` override
  clears them. _(verified 2026-11-02, mypy 2.4.1)_
- **LeRobot 0.6.1 ships no `py.typed`**, so mypy would treat it as untyped even if installed;
  `huggingface_hub` does ship one. _(verified 2026-11-02, LeRobot 0.6.1 site-packages)_
- **Run mypy without the extra to match CI**: `uv run --isolated --locked mypy` (what the hook
  runs). A plain `uv run mypy` in a venv that has the `lerobot` extra sees the real
  `huggingface_hub` types and can report errors that CI does not. _(verified 2026-11-02)_
- **Measuring `tests/` with `uvx mypy` is misleading**: uvx's throwaway env has no pytest, so
  every `@pytest.mark.parametrize` becomes an untyped decorator (40 false errors). Run it inside
  the project env (`uv run --with mypy ...`). _(verified 2026-11-02, uv 0.10.8)_
- **The PyPI `pyright` package is a wrapper**: without Node on `PATH` it downloads Node with
  `nodeenv` and then the pyright npm package with `npm`, at runtime, outside `uv.lock`.
  _(verified 2026-11-02, pyright 1.1.414 PyPI readme)_
