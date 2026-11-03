# Testing the gate's own code

How we check that the gate itself is correct: type checking, property-based tests and mutation
testing of `piperobot/stats`.

## Type checking (mypy)

- **`uv run mypy`** checks the `piperobot` package in strict mode, configured in
  `pyproject.toml` (`[tool.mypy]`), and runs as the pre-push hook `ci-mypy` and the `type-check`
  job in `ci.yml` ([ADR 0025](../decisions/0025-mypy-strict-type-checking.md)).
  ~~`tests/` and `robots/` are not checked.~~ _(verified 2026-11-02, mypy 2.4.1)_
- **Since 2026-11-03 mypy also checks `tests/`** (`files = ["piperobot", "tests"]`), except
  `tests/test_so101_*.py`, `tests/so101_loader.py` and `tests/test_dataset_stats.py`: they
  exercise `robots/so101` code and join together with `robots/` after the SO-101 scene PR lands.
  Tests that pass deliberately wrong types to `SuccessCount` carry `# type: ignore[arg-type]`
  (strict's `warn_unused_ignores` flags them if they stop being needed), and the optional
  `numpy`/`PIL` imports of `test_lerobot_compat.py` get a scoped `ignore_missing_imports`.
  _(verified 2026-11-03, mypy 2.4.1)_
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

## Property-based tests (Hypothesis)

- **`tests/test_stats_properties.py`** states the gate's laws for any counts: Wilson bounds in
  [0, 1] around p̂, monotone in successes, narrower with more trials at the same p̂, nested in
  confidence, symmetric; Newcombe contains the difference, antisymmetric; the verdict rule in
  exact arithmetic; an exact-tolerance drop never WARNs; improvements PASS; one more candidate
  success never worsens the verdict; invalid inputs raise. _(verified 2026-11-02, Hypothesis
  6.170.14)_
- **Deterministic by default**: `tests/conftest.py` loads a profile with `derandomize=True` and
  no example database, so local runs, hooks and CI see the same examples (~4 s).
  `HYPOTHESIS_PROFILE=explore` runs 5000 random examples per test (~60 s) for an occasional hunt.
  _(verified 2026-11-02, Hypothesis 6.170.14)_
- **`database=None` is not enough to keep `.hypothesis/` away**: Hypothesis also caches other
  data there, so `conftest.py` points `HYPOTHESIS_STORAGE_DIRECTORY` at a temp dir. In Codex's
  sandbox a `.hypothesis/` folder belongs to the sandbox user; delete it from inside the
  sandbox ([ci.md](ci.md)). _(verified 2026-11-02, Hypothesis 6.170.14, Codex CLI 0.166)_
- **A property can pass for the wrong reason: break the code and watch it fail.** The first
  boundary property drew up to 10,000 trials, where an exact-tolerance drop is almost always
  significant (BLOCK), so it never reached the WARN branch and passed with the float bug back
  in. Capped at 200 trials (PR-sized), it fails on the bug. _(verified 2026-11-02)_

## Mutation testing (mutmut)

- **mutmut 3 needs `fork()`**: on Windows it only runs inside WSL. We run it in
  `.github/workflows/mutation.yml` on `ubuntu-latest`: weekly, by hand (`workflow_dispatch`),
  and on PRs that touch `piperobot/stats/**` or its tests. It reports the score and each
  survivor's diff (job summary and log) and is not a required check. _(verified 2026-11-02,
  mutmut 3.8.1 docs and source)_
- **Run it locally** on Linux or WSL: `uv sync --group mutation`, then `uv run mutmut run`,
  `uv run mutmut results` (survivors), `uv run mutmut show <name>` (diff), `uv run mutmut browse`
  (interactive). Config is `[tool.mutmut]` in `pyproject.toml`. _(verified 2026-11-02,
  mutmut 3.8.1)_
- **Mutate one subpackage with `source_paths` plus `only_mutate`**: mutmut copies only
  `source_paths` into `mutants/` and removes the checkout from `sys.path`, so
  `source_paths = ["piperobot/stats"]` would hide `piperobot.results`, which the tests import.
  We use `source_paths = ["piperobot"]` with `only_mutate = ["piperobot/stats/*"]`, and
  `also_copy = ["robots"]` for the committed baselines. `do_not_mutate_patterns` and
  `# pragma: no mutate` skip whole statements, so on an `add_argument(...)` line they would also
  hide the `type=` mutants. _(verified 2026-11-02, mutmut 3.8.1 source)_
- **Score on `piperobot/stats`**: first run 286 / 340 killed (84.1%). The 54 survivors were
  23 real gaps (no test used a non-default `--confidence` or `--tolerance`, so dropping their
  `type=float`, or passing the tolerance as the confidence, went unnoticed; `decide()` could
  ignore `confidence` for its intervals; the WARN reason text and `format_result()` layout were
  unchecked; the CLI's input groups could stop being required), 27 changes to `--help` text, and
  4 equivalent mutants. Tests now kill the first two groups: **336 / 340 killed (98.8%)**; the
  4 survivors are the equivalent mutants below (run 41567441367). _(verified 2026-11-02,
  mutmut 3.8.1)_
- **Accepted equivalent mutants** (4):
  - `text.partition("/")` → `rpartition` in `SuccessCount.parse`: they differ only with two or
    more `/`, and then both leave a `/` in a part that `int()` rejects.
  - `encoding="utf-8"` → `"UTF-8"` in `load_baseline`: the same codec.
  - `encoding="utf-8"` → `None` in `load_baseline`: the locale encoding, UTF-8 on the Linux
    runner. On Windows it is not equivalent, but mutmut only runs on Linux.
  - `diff_interval.upper < 0` → `<= 0` in `decide()`: they differ only when the Newcombe upper
    bound is exactly 0.0. A search of every pair with n ≤ 200 at 95% confidence, checking the
    two candidate counts at each BLOCK crossing, found no exact 0.0 and nothing within 1e-12.
- **Accepted equivalent mutants in `format_percent`** (3, since 2026-11-03): format `"f"` →
  `"F"` (differs only for inf and NaN, rejected before formatting), and `rstrip("0")` /
  `rstrip(".")` → `rstrip("XX0XX")` / `rstrip("XX.XX")` (`rstrip` takes a set of characters, and
  no `X` occurs in a number). With these, the score on 2026-11-03 is 354 / 361 killed, the 7
  survivors all equivalent. _(verified 2026-11-03, mutmut 3.8.1)_

## Bugs found in `piperobot/stats` (fixed 2026-11-02)

- **A drop of exactly the tolerance could WARN**, through float rounding: `0.7 - 0.8` is
  `-0.10000000000000009`, so 35/50 vs 40/50 warned while 40/50 vs 45/50 passed. With equal trials
  n ∈ {10, 20, 50, 100} and the default 10 pp, 33 such pairs warned. ADR 0004 already says only a
  drop that *exceeds* the tolerance warns, so this is a bug fix: `decide()` now compares exact
  counts (`Fraction`) with the tolerance as typed (`Fraction(str(tolerance))`, so 0.1 is 1/10).
  Over 633,625 (candidate, baseline, tolerance) combinations, the only verdicts that changed are
  461 WARN → PASS, all exact-tolerance drops. Against the committed baselines at the default
  tolerance, only 43/100 vs PushT's 265/500 changes; no 50-episode PR verdict changes.
  _(verified 2026-11-02)_
- **NaN tolerance silently disabled WARN** (`x > nan` is always false); a non-finite tolerance
  now raises `ValueError`. _(verified 2026-11-02)_
- **`SuccessCount` accepted floats and bools** (`SuccessCount(2.5, 5)`, `SuccessCount(True, 5)`:
  `bool` is a subclass of `int`); both now raise `TypeError`. _(verified 2026-11-02)_
- **`load_baseline` truncated**: `int(40.7)` is 40. Baselines must now hold JSON integers;
  `40.7`, `40.0`, `"40"` and `true` raise `BaselineError`. `40.0` is rejected on purpose: our own
  writers emit integers, so a float means a hand edit or a foreign writer (ADR 0009). The
  committed baselines still load. _(verified 2026-11-02)_
- **Percentages were rounded to whole numbers when printed**: a 0.125 tolerance showed as
  "12 pp" and a 0.975 confidence as "98%", in the gate reason and the PR comment. They now print
  the decimal as typed (`format_percent`: "12.5 pp", "97.5%"); the defaults still print "10 pp"
  and "95%", so the golden file is unchanged. Observed drops keep one decimal on purpose.
  _(verified 2026-11-03)_

## Rendered output (history page)

- **Look at rendered HTML, not only at its source**: the golden file of
  `piperobot/reports/history.py` passed while the last date label was clipped by the SVG's edge
  and the run URLs pushed the table off the page. Screenshot it headless:
  `msedge --headless=new --window-size=900,1700 --screenshot=<png> file:///<path>/history.html`
  (Edge ships with Windows; Chrome takes the same flags). _(verified 2026-11-03, Edge on
  Windows 11)_
- **Verdict colors on the history page** have at least 4.5:1 contrast on white (WCAG AA for
  text) and distinct luminance, and each point also has a text tooltip and a table row, so the
  verdict does not rely on color alone: pass `#164e35` (9.7:1), block `#b91c1c` (6.5:1),
  warn `#98700a` (4.5:1). _(verified 2026-11-03)_
- **Golden files need the shapes that break**: the first golden page had six records, so it
  missed that a single record drew no baseline (an SVG polyline with one vertex is invisible) and
  that a long platform string pushed the table off a narrow screen. Both showed on the first live
  page; `history_single.html` and `history_long_platform.html` now cover them. _(verified
  2026-11-03)_

## Certificates of evaluation (attestations)

- **`gh attestation verify --format json` returns a list**; each item's
  `verificationResult.statement` holds `subject[].digest.sha256`, `predicateType` and
  `predicate`, and `verificationResult.signature.certificate` holds the OIDC-backed fields:
  `sourceRepositoryDigest` (commit), `sourceRepositoryRef`, `buildSignerURI`,
  `runnerEnvironment` (`github-hosted`) and `runInvocationURI`
  (`.../actions/runs/<id>/attempts/<n>`). `tests/test_certificate.py` mocks this shape.
  _(verified 2026-11-03, gh 2.88.1, on a cli/cli release attestation)_
- **No GitHub login is needed with `--bundle`**: against the API, `gh attestation verify` asks
  for `gh auth login`; with `--bundle <file>` it verifies with an empty gh config, and
  `gh attestation trusted-root` works without login too. _(verified 2026-11-03, gh 2.88.1)_
- **Only the certificate is OIDC-backed; the predicate is what the signing job wrote**
  (`gh attestation verify --help`). Hence the separate `attest` job with no third-party code
  ([ADR 0030](../decisions/0030-signed-certificates-of-evaluation.md)). _(verified 2026-11-03)_
- **Sizes**: a Sigstore bundle is ~14 KB, a 50-episode `results.json` ~3–5 KB.
  _(measured 2026-11-03)_
