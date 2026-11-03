# 0037. The SO-101 gate verdict is a required check, produced on every push

- Status: Accepted
- Date: 2026-11-03

## Context

The SO-101 gate ([0035](0035-so101-gate-on-the-self-hosted-runner.md),
[0036](0036-so101-gate-scripted-policy-on-100-fixed-seeds.md)) blocked its registered regressions
(#60, #65), but "blocked" meant a red `so101-gate` check and a ❌ comment, not a merge refusal:
0035 kept it out of the required checks. Andrés decided on 2026-11-03 to make it required. Three
things stood in the way:

- The workflow ran only on pushes touching the gate's paths, and never on `dependabot/**`
  branches. A required check that a PR never produces stays pending forever.
- Its jobs are named `evaluate` and `report`. Required checks are matched by job name, and those
  names are generic.
- The runner is a PC that can be off.

## Decision

This supersedes 0035's "Not a required check" bullet. The rest of 0035 and 0036 stands.

- **Every push runs the workflow**: `on.push` has `branches: ["**"]` and no `paths` or
  `branches-ignore` filter. A hosted `changes` job (`contents: read`, about 10 s) decides whether
  the push is gate-relevant. The path list lives only in `.github/scripts/so101_gate.py`
  (`PATHS`); a test checks that it covers every module the gate imports.
- **What `changes` diffs**: on a branch, the whole branch against its merge-base with
  `origin/main`, never `github.event.before`, because the PR head is what gets merged: a docs-only
  push on top of a policy commit still evaluates. On `main`, `before..sha`. A manual dispatch, an
  all-zero `before`, or any git failure counts as relevant.
- **`evaluate` runs only when relevant and the actor is not Dependabot** (`needs: changes`, plus
  the existing repository and actor guards). `report` keeps `needs: evaluate` with no `if:`.
- **One uniquely named job, `so101-gate-verdict`, is the required check**: hosted,
  `needs: [changes, evaluate, report]`, `if: always()`, `contents: read` (it checks out the
  script; no write token). It passes when nothing gate-relevant changed, or when `evaluate` and
  `report` both succeeded (a PASS, a WARN, or the "no baseline on main yet" note). It fails when
  `changes` did not succeed, when Dependabot changed gate-relevant files, or when `evaluate` or
  `report` failed, was skipped or was cancelled; a BLOCK fails through `report`. A baseline-mode
  dispatch passes: it measures a baseline and is not a PR check.
- **Dependabot**: the runner never runs code that Dependabot pushed. When Dependabot changes a
  gate-relevant file (`uv.lock`, `pyproject.toml`), the verdict fails with that reason. Andrés
  reviews the update and pushes a commit to the branch, which runs the gate as his push, or
  bypasses.
- **Bypass**: the `main` ruleset already has the repository admin role as a bypass actor with
  mode "always". e5 adds `so101-gate-verdict` (integration 15368, GitHub Actions) to its required
  checks, with Andrés's OK of 2026-11-03, after two checks: this PR's own run is green and
  mirrors `report`'s PASS, and a docs-only PR after the merge passes in seconds without the
  runner.
- **Concurrency: branches cancel, main queues.** On a branch, a newer push cancels the older
  run; its verdict fails, but it belongs to an older SHA that no PR head points to. On `main`,
  runs queue instead (`cancel-in-progress` is false there): every push now runs the workflow, so
  a docs-only merge would otherwise cancel the in-progress run of an earlier gate-relevant merge,
  and its own `before..sha` diff would pass without that merge ever being evaluated on `main`.

## Alternatives considered

- **Require `report` directly**: the name is generic and, with a `paths` filter, most PRs would
  never produce it.
- **Keep the `paths` filter and add a no-op twin workflow with the inverse filter** (GitHub's
  documented workaround): two workflows must keep their lists in sync, and a push touching both
  sets would run both.
- **Diff `github.event.before..sha` on branches too**: a docs-only push after a policy commit
  would pass without evaluating the commit that gets merged.
- **Run the gate for Dependabot**: it would put code that Dependabot pushed on the home PC, which
  [0027](0027-self-hosted-runner-push-only-and-pinned-actions.md) rules out.

## Consequences

- An accidental merge from the UI can no longer skip a red or missing gate. Andrés is the only
  admin and every merge goes through his account, so the required check guards against mistakes
  rather than replacing our discipline: merges stay pinned to a green run.
- When the runner is off, a relevant PR waits with a pending verdict until it is back, or Andrés
  bypasses. Irrelevant PRs never wait: their verdict passes in seconds on hosted runners.
- Every push now costs two short hosted jobs, even when nothing relevant changed.
- Fork PRs never get the check, because the workflow is push-only (0035). A collaborator's
  commits are pushed to a branch here, as before.
- Renaming `so101-gate-verdict` means updating the ruleset in the same change.
- The check is self-attested: the verdict comes from the branch's own `so101-gate.yml` and
  `so101_gate.py`, so a PR that edits either (for example, dropping a path from `PATHS`) can
  change what the check means. Such a PR needs Andrés's explicit review of that diff.
- The sticky comment reflects the last gate-relevant run: if a later head stops being relevant
  (say, the policy change is reverted), the verdict passes while an old ❌ comment stays on the PR.
