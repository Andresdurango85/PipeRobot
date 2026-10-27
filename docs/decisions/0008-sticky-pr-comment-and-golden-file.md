# 0008. Sticky PR comment, tested with a golden file

- Status: Accepted
- Date: 2026-10-26

## Context

The gate posts a comment on every PR push. A new comment per push buries the discussion. The
comment format is the product's main user interface, so format changes must be reviewed.

## Decision

- `reports/pr_comment.py` starts the comment with the hidden marker `<!-- piperobot-gate -->`;
  the workflow finds and edits its own previous comment instead of posting a new one.
- At most 10 failed episodes are listed (sorted by seed); the rest are linked from the run.
- Rendering always exits 0; only `python -m stats.gate` decides the merge-blocking exit code.
- `tests/golden/pr_comment_block.md` holds a full rendered comment. A format change shows up as a
  diff in the PR; regenerate with `UPDATE_GOLDEN=1 uv run pytest`.

## Alternatives considered

- One comment per push: noisy.
- Only assertion-based tests: they miss unintended layout changes.
- A template engine (Jinja): an extra dependency for little gain at this size.

## Consequences

- The workflow needs `pull-requests: write` permission to edit the comment.
- Golden files must be reviewed, not regenerated blindly.
