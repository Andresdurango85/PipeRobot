# 0030. Signed certificates of evaluation: Sigstore attestations of results and verdict on main

- Status: Accepted
- Date: 2026-11-03

## Context

The history ([0026](0026-success-rate-history-data-branch-and-pages.md)) records each evaluation
on `main`, but a record is only a JSON file: nothing proves that our CI produced it, on that
commit, with that policy. PipeRobot should be able to hand out a "certificate of evaluation" that
anyone can check, without trusting us or our page.

GitHub artifact attestations sign an in-toto statement (subjects by digest, plus a predicate)
with a short-lived Sigstore certificate bound to the workflow's OIDC identity. For public
repositories they are available on every current plan, use the Sigstore public-good instance and
are written to its public, immutable transparency log (Rekor); private repositories need GitHub
Enterprise Cloud, so the crab's private repo cannot use them. `actions/attest` v4 is current;
`attest-build-provenance` v4 is a thin wrapper of it. _(checked 2026-11-03)_

What is proven and what is not, from `gh attestation verify`: the certificate's fields are
OIDC-backed (repository, signer workflow and its ref, source commit, the signing job's runner
type). The predicate is whatever the signing job wrote: anyone in control of that job's execution
could falsify it.

`gh attestation verify` against the GitHub API needs a logged-in `gh`; with `--bundle` it needs
no login at all. _(checked 2026-11-03, gh 2.88.1, with an empty gh config)_

## Decision

- **What is signed, on `main` only, in `history.yml`**: one certificate per history point.
  Subject: `results.json` (sha256). Predicate: the history record itself (schema 1: commit,
  policy, evaluator, counts, Wilson interval, baseline, difference interval, tolerance, verdict,
  seeds, platform, run), with the predicate type
  `https://github.com/Andresdurango85/PipeRobot/blob/main/docs/attestations/gate-verdict-v1.md`,
  a constant in `piperobot.reports.history` that the workflow and the verifier both read. A
  standard SLSA provenance over `results.json` and `record.json` is signed too, for generic
  tooling.
- **Signing is isolated from the evaluation.** `evaluate` (LeRobot, torch) keeps `contents: read`
  and never gets `id-token`, so a compromised dependency cannot mint a signing token. A separate
  `attest` job on a GitHub-hosted runner runs only our standard-library module to write
  `record.json`, then `actions/attest`, with `contents: read`, `id-token: write`,
  `attestations: write`.
- **The history stores the certified record.** `append --record` appends exactly the signed
  `record.json`, and refuses one whose run id and attempt are not the current run's, so a stale or
  replayed artifact cannot add a point.
- **Evidence that outlives the run.** Workflow artifacts expire (7 days here), and a certificate
  whose subject is gone cannot be checked. The append job also commits
  `results/<run_id>.<attempt>.json` and the gate-verdict bundle `bundles/<run_id>.<attempt>.jsonl`
  to the `history` branch, under its append-only ruleset. AGENTS.md's rule that raw outputs never
  go into memory is about `docs/` and the project memory; this branch is neither: it is attested
  evidence, and these files are what keeps each certificate checkable without the API.
- **Verification**: `python -m piperobot.reports.certificate verify results.json [--bundle F]`
  runs `gh attestation verify` pinned to this repo, the `history.yml` signer workflow,
  `--source-ref refs/heads/main`, `--deny-self-hosted-runners` and the predicate type, then checks
  the predicate against `results.json` (counts, policy, seeds), the certificate's commit and run.
  A predicate that disagrees with its subject is a distinct, loud failure.
- **Pull requests are not certified in v1.** A same-repo PR can edit `pr-gate.yml` itself, so its
  certificate would only say "a workflow at `refs/pull/N/merge`"; fork PRs cannot get
  `id-token: write` at all.

## What a certificate proves, and what it does not

It proves: `history.yml` at commit C on `refs/heads/main`, running on a GitHub-hosted runner,
signed this record about the file with this sha256, and the signature is in the public log.

It does not prove: that the evaluating job was honest. Its integrity (the LeRobot and torch
versions from `uv.lock`, the runner it ran on) is trusted, not proven. `--deny-self-hosted-runners`
checks the signing job's runner, not the evaluating job's: a future Isaac evaluation on the home
PC would still get a certificate signed on a hosted runner, and its platform is only what the
record's `platform` field says.

## Alternatives considered

- SLSA provenance only: generic, but the verdict and intervals would not be in a signed claim.
- Signing in the `evaluate` job: one job fewer, but third-party code would run next to an
  `id-token: write` token.
- Certifying PRs now: weaker identity (see above) and no signature at all for forks.
- Keeping only the GitHub API copy: verification would need a GitHub login and depends on an
  undocumented retention.

## Consequences

- One more short job per history point; `append` now depends on `attest`, so a Sigstore or
  attestations-API outage blocks a point until the run is re-run (idempotent, nothing lost). No
  `continue-on-error`: an uncertified point must not appear silently.
- About 20 KB more per point on the `history` branch (a ~5 KB `results.json` and a ~14 KB
  bundle): ~7 MB for a year of daily points.
- The predicate type URI is permanent: changing the record format means a `gate-verdict-v2`.
