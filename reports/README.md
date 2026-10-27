# reports

Builds the automatic PR comment from the gate result: verdict, success rates with confidence
intervals, and the failed episodes (seed, scene, failure, link to the video).

```
uv run python -m reports.pr_comment --candidate 25/50 --baseline 45/50 \
    --failed-episodes failed.json --run-url "$RUN_URL" --commit "$GITHUB_SHA" --output comment.md
```

- The first line is the hidden marker `<!-- piperobot-gate -->`. The workflow uses it to find and
  edit its previous comment on each push (sticky comment) instead of posting a new one.
- At most 10 failed episodes are listed, sorted by seed; the rest are linked from the run.
- Rendering always exits 0; the merge-blocking exit code comes from `python -m stats.gate`.
- Example output: [tests/golden/pr_comment_block.md](../tests/golden/pr_comment_block.md). It is
  a golden file: if the format changes, regenerate it with `UPDATE_GOLDEN=1 uv run pytest` and
  review the diff.
