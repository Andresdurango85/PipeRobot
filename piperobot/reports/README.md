# reports

Builds the automatic PR comment from the gate result: verdict, success rates with confidence
intervals, and the failed episodes (seed, scene, failure, link to the video), then posts it.

```
uv run python -m piperobot.reports.pr_comment --results out/results.json \
    --baseline-file robots/mock/baseline.json --run-url "$RUN_URL" --commit "$HEAD_SHA" --output comment.md
uv run python -m piperobot.reports.sticky_comment --pr 12 --body-file comment.md   # needs GITHUB_TOKEN
```

- The first line is the hidden marker `<!-- piperobot-gate -->`. `sticky_comment.py` finds the
  bot's comment with that marker and edits it on each push instead of posting a new one; it never
  edits a human's comment.
- Posting retries GitHub 5xx and network errors (3 attempts, 2 s and 5 s apart); 4xx fails at
  once. Each retry lists the comments again first, so a POST that timed out after GitHub created
  the comment is edited, not duplicated. A failure after the last attempt exits 2.
- At most 10 failed episodes are listed, sorted by seed; the rest are linked from the run.
- Rendering exits 0 whatever the verdict (2 on invalid inputs); the merge-blocking exit code comes
  from `python -m piperobot.stats.gate`.
- Example output: [tests/golden/pr_comment_block.md](../../tests/golden/pr_comment_block.md). It is
  a golden file: if the format changes, regenerate it with `UPDATE_GOLDEN=1 uv run pytest` and
  review the diff.

## Evaluation history

`history.py` keeps schema 1 evaluation records and renders a standalone HTML page with
success-rate charts, confidence bars, platform markers and run links. It uses only the standard
library.

```
python -m piperobot.reports.history append --history history.json --results results.json \
    --baseline-file baseline.json --commit SHA --commit-date 2026-11-03T10:00:00Z \
    --run-url https://github.com/owner/repo/actions/runs/1 --run-id 1 --run-attempt 1 --new
python -m piperobot.reports.history render --history history.json --output history.html
```

`--new` allows a missing history only for bootstrap or local use. Records are append-only:
identical run/attempt duplicates are idempotent, conflicting duplicates fail, and saving requires
the previous history as an exact prefix. Writes replace the file atomically. Invalid inputs exit
2 with an `ERROR:` line. Platform labels default to `python -m piperobot.platform_info`.

The `history.yml` workflow evaluates main, appends each result to the `history` data branch
with fetch/append/push retries, and renders that branch to GitHub Pages. CI never uses `--new`;
the data branch must be created and seeded first (ADR 0026).
