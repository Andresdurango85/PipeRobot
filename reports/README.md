# reports

Builds the automatic PR comment from the gate result: verdict, success rates with confidence
intervals, and the failed episodes (seed, scene, failure, link to the video), then posts it.

```
uv run python -m reports.pr_comment --results out/results.json \
    --baseline-file stats/baseline.json --run-url "$RUN_URL" --commit "$HEAD_SHA" --output comment.md
uv run python -m reports.sticky_comment --pr 12 --body-file comment.md   # needs GITHUB_TOKEN
```

- The first line is the hidden marker `<!-- piperobot-gate -->`. `sticky_comment.py` finds the
  bot's comment with that marker and edits it on each push instead of posting a new one; it never
  edits a human's comment.
- At most 10 failed episodes are listed, sorted by seed; the rest are linked from the run.
- Rendering exits 0 whatever the verdict (2 on invalid inputs); the merge-blocking exit code comes
  from `python -m stats.gate`.
- Example output: [tests/golden/pr_comment_block.md](../tests/golden/pr_comment_block.md). It is
  a golden file: if the format changes, regenerate it with `UPDATE_GOLDEN=1 uv run pytest` and
  review the diff.
