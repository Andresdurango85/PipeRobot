# 0031. History schema 2 for nightly records; one trusted builder, certify.yml, signs every series

- Status: Accepted
- Date: 2026-11-03

## Context

A nightly job (`nightly.yml`) evaluates a reference policy and the candidate (`main` HEAD) on the
same 500 rotating seeds in one job, and judges them two ways: paired (exact McNemar, with
`piperobot.stats.paired`) and unpaired (the candidate's fresh-seed count against the committed
baseline, through `gate.decide`, the overfitting signal). Those results belong in the history
([0026](0026-success-rate-history-data-branch-and-pages.md)) and need certificates
([0030](0030-signed-certificates-of-evaluation.md)), like the points `history.yml` adds on `main`.

Three constraints shape it:

- **The history is append-only.** `save_history` refuses anything but an exact prefix, and the
  first four records are schema 1. They cannot be migrated.
- **Certificates are permanent.** The v1 predicate page promises never to change, so a new record
  format needs a new predicate type.
- **The predicate is what the signing job writes** (0030). If `nightly.yml` signed on its own, or
  computed the record in the job that runs torch, the certificate would prove less.

In a reusable workflow, Fulcio puts the reusable workflow in the certificate's `buildSignerURI`
(GitHub's `job_workflow_ref`) and the top-level caller in `buildConfigURI` (`workflow_ref`).
_(Fulcio `docs/oid-info.md`, checked 2026-11-03; to be confirmed on a real certificate)_

## Decision

- **Schema 2** = every schema-1 field with the same meaning, plus:
  - `series`: `"main"` or `"nightly"`;
  - `paired`: null for `main`; for `nightly`, `{reference_commit, both, reference_only,
    candidate_only, neither, p_value, alpha, difference_interval, verdict}`, checked for
    consistency (the cells sum to `trials`, `both + candidate_only == successes`);
  - `cpu_flags_sha256`: null or the sha256 of the normalized `/proc/cpuinfo` flags line, on both
    series, to test whether CPU flags explain PushT's platform flips.
  - `runner_image`: null or the runner image as `$ImageOS $ImageVersion` (e.g.
    `ubuntu24 20261025.353.1`), on both series, so an image change shows next to a CPU change.

  For a nightly record, the schema-1 fields describe the unpaired arm: the candidate's
  fresh-seed counts against the committed baseline. So the page plots it as a series of its own
  without special cases.
- **No migration**: schema-1 records stay as written and load as `series: "main"`. New records
  are schema 2 once `certify.yml` signs them; until then `history record` keeps emitting schema 1
  (`--schema` defaults to 1).
- **A new predicate type**, `gate-verdict-v2` ([page](../attestations/gate-verdict-v2.md)), for
  schema-2 records. v1 certificates stay valid and keep their verification rules.
- **One trusted builder.** A reusable workflow, `.github/workflows/certify.yml`
  (`on: workflow_call`), is the only signer of v2 certificates. Both `history.yml` and
  `nightly.yml` call it, by relative path only (`uses: ./.github/workflows/certify.yml`), so it
  always runs at the caller's own ref; combined with `--source-ref refs/heads/main`, a branch
  cannot mint a `main` certificate. It writes the record from the raw evidence with our
  standard-library code (the paired block is computed there, from `candidate.json` and
  `reference.json`), signs, appends to the `history` branch and deploys the page: one write path,
  one signer.
- **The series is bound to the caller.** `certify.yml` takes the series as an input, so the
  verifier enforces: series `main` ⇔ `buildConfigURI` is `history.yml@refs/heads/main`; series
  `nightly` ⇔ `nightly.yml@refs/heads/main`; and `buildSignerURI` is
  `certify.yml@refs/heads/main`. Claiming the wrong series is a `MISMATCH`.
- **Nightly evidence**: subjects are `candidate.json` and `reference.json`; the verifier needs
  both files and recomputes the paired cells from them. The reference commit is a claim of the
  signed record: it cannot be recomputed from the files.
- **The nightly alert stays independent of signing**: `nightly.yml`'s own verdict job computes
  the same statistics from the same files and fails on a paired BLOCK, so a Sigstore or API outage
  cannot silence a regression alert.

## Alternatives considered

- Migrating schema-1 records to schema 2: forbidden by the append-only guard, and it would change
  what issued certificates point at.
- Letting `nightly.yml` sign with its own job: two signers, two copies of the signing logic, and
  the certificate would not say that one trusted builder produced it.
- Computing the paired block in `nightly.yml`'s evaluation job: the predicate would come from the
  job that runs third-party code.
- Keeping schema 1 and a separate nightly file: a second history to keep append-only, render and
  sign.

## Consequences

- The verifier knows two rules: v1 (signer `history.yml`, schema 1) and v2 (signer
  `certify.yml`, schema 2, series bound to the caller). It routes by the bundle's predicate type,
  or tries v2 then v1 against the API.
- `history.yml`'s attest, append and deploy jobs move into `certify.yml` (next PR); 0026's and
  0030's descriptions of those jobs then describe `certify.yml`.
- Nightly points add about 25 KB each (two results files and a bundle) to the `history` branch:
  ~9 MB a year at one a day.
- `history record --schema 1` is a transitional default; it becomes 2 with `certify.yml`.
