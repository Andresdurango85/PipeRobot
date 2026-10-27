# CI (GitHub Actions)

## Current workflows

- **`ci.yml`**: ruff + pytest on `ubuntu-latest`, no GPU, no LeRobot; ~7 s per run.
  _(verified 2026-10-26, run 40439823769)_
- `pr-gate.yml` (GPU, self-hosted runner on the home PC) and `nightly.yml` (larger baseline) do
  not exist yet; see [`../STATUS.md`](../STATUS.md).

## Gotchas

- **`astral-sh/setup-uv@v6` runs on Node 20, which GitHub has deprecated**; it is forced onto
  Node 24 with an annotation. Latest release is v10.3.2 (2026-10-22); bump in its own PR and check
  whether inputs such as `enable-cache` changed. _(verified 2026-10-26, run annotations, GitHub releases)_
- **`ubuntu-latest` moves to Ubuntu 26 from 2026-10-19.** No impact today because uv pins Python
  3.12 itself. _(verified 2026-10-26, run annotations)_
- **The golden-file test needs LF endings everywhere**, enforced by `.gitattributes`
  ([ADR 0007](../decisions/0007-lf-line-endings.md)). _(verified 2026-10-26)_
- **Editing the sticky PR comment needs `pull-requests: write`** in the workflow permissions
  ([ADR 0008](../decisions/0008-sticky-pr-comment-and-golden-file.md)). Not yet exercised.
