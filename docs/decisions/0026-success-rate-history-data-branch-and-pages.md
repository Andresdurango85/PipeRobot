# 0026. Success-rate history: an append-only data branch, rendered to Pages

- Status: Accepted
- Date: 2026-11-03

## Context

The gate compares each PR with a stored baseline ([0003](0003-statistical-gate-wilson-newcombe.md)),
but nothing shows how the policy's success rate moves over time, which is what a team watching a
policy wants to see, and a feature of PipeRobot as a product. Nothing evaluates on `main` today:
`pr-gate` runs on `pull_request` only and evaluates the PR head, not the merge commit.

PushT outcomes depend on the CPU: the same seeds flip a few near-miss episodes between CPU models
([0016](0016-real-evaluator-lerobot-pusht.md), [0017](0017-pr-gate-pusht-on-github-runners.md)),
and GitHub-hosted runners alternate between models. A trend chart must show the platform of each
point, or a CPU change reads as a policy change.

The history is evidence. It must survive for years and must never be rewritten, least of all by
the change being evaluated.

## Decision

- **Store**: `history.json` on a data branch `history`, appended by a workflow, one record per
  evaluation. Git is the store and the audit trail; Pages only displays it.
- **Record** (schema 1, `piperobot/reports/history.py`): commit, commit date, evaluation time, run
  URL, id and attempt, policy and evaluator (from the results contract), successes and trials,
  confidence, Wilson interval, baseline counts, difference interval, tolerance, verdict, seed
  ranges, and the platform string. Everything but the commit, run and platform fields comes from
  `load_results` and `decide()`, so a record cannot disagree with the gate. The platform string
  comes from `piperobot.platform_info`, the same helper the gate workflow uses, so they never
  drift. A series is `(policy, evaluator)`, so a future SO-101/Isaac evaluator gets its own line.
- **Never rewritten**, in four layers:
  1. a ruleset on `history` blocks force pushes and deletion;
  2. `save_history` refuses to write unless the previous history is an exact prefix of the new one;
  3. the append and deploy jobs run only when `github.ref` is `refs/heads/main`
     (`workflow_dispatch` can run any branch's copy of the workflow), and the push names
     `refs/heads/history` explicitly, never a default refspec;
  4. review of workflow changes: GitHub grants same-repo PRs whatever token permissions their
     workflow requests, so "PRs only read" is a review rule, not a platform guarantee. Fork PRs
     are read-only regardless.
  The append job's `contents: write` token cannot push to `main`: `main`'s ruleset requires a
  pull request, and its only bypass actor is the repository admin role, which `GITHUB_TOKEN`
  does not have (checked 2026-11-03).
- **No lost points under bursts**: no concurrency group on the append job (a group keeps one
  pending run and cancels the older one). Instead, fetch–append–push with a retry on
  non-fast-forward. Append is idempotent on `(run_id, run_attempt)`, so a retry never duplicates a
  point; re-running a run adds a new point on purpose (a re-evaluation is data).
- **When**: on push to `main` that touches what can change the outcome (`piperobot/**`,
  `robots/pusht/**` including its baselines, `uv.lock`, the workflow itself), plus
  `workflow_dispatch` to force a point. So it is one point per evaluation, not one per merge.
- **Page**: a static HTML page with inline SVG, no JavaScript: per series, the rate with its
  Wilson interval, colored by verdict, a marker shape per platform with a legend, the baseline as
  a step line (it changes when the baseline is refreshed), and a table. Deployed with
  `actions/deploy-pages` (`pages: write`, `id-token: write`, the `github-pages` environment),
  with concurrency `cancel-in-progress: false`, as GitHub's Pages template does.

## Alternatives considered

- Pages rebuilt from past workflow artifacts: artifacts expire after at most 90 days; the history
  would vanish.
- Pages as the store (read the published file, append, redeploy): any deploy can overwrite it and
  it has no versioning.
- A `gh-pages` branch served directly: works, but mixes data with the rendered site; a separate
  data branch lets the page be re-rendered from the data at any time.
- An external database or service: needs a secret and an account, for a few kilobytes a month.
- Evaluating on every push to `main`: identical points and 5 CPU-minutes for docs-only merges.

## Consequences

- One more CPU evaluation (~5 min, GitHub-hosted, free for a public repo) per merge that touches
  the policy, the gate or a baseline.
- Andrés must apply three settings once: Pages from GitHub Actions, the orphan `history` branch
  seeded with `[]`, and its ruleset. The history starts with the first evaluation after that.
- The history is public, like the repo. The private crab repo would keep its own.
- The evaluation steps repeat `pr-gate`'s; sharing them as a reusable workflow is a follow-up.
