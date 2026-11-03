# Predicate type: gate verdict, v2

`https://github.com/Andresdurango85/PipeRobot/blob/main/docs/attestations/gate-verdict-v2.md`

The `predicateType` of PipeRobot's certificates of evaluation for history records of schema 2
([ADR 0031](../decisions/0031-history-schema-2-and-certify-trusted-builder.md)). It never
changes. Schema-1 records keep [v1](gate-verdict-v1.md).

## Statement

- **Signer**: `.github/workflows/certify.yml@refs/heads/main`, a reusable workflow, called by
  `history.yml` (series `main`) or `nightly.yml` (series `nightly`). The caller is the
  certificate's `buildConfigURI`.
- **Subjects**: `results.json` for `main`; `candidate.json` and `reference.json` for `nightly`.
- **Predicate**: one history record, schema 2: every [v1 field](gate-verdict-v1.md) (for a
  nightly record they describe the candidate's fresh-seed run against the committed baseline),
  plus:

| Field | Meaning |
| --- | --- |
| `schema` | `2` |
| `series` | `main` or `nightly` |
| `paired` | `null` for `main`; for `nightly` the paired comparison on the same seeds: `reference_commit`, the four cells `both`, `reference_only`, `candidate_only`, `neither`, the exact McNemar `p_value`, `alpha`, the paired Newcombe `difference_interval` and its `verdict` |
| `cpu_flags_sha256` | sha256 of the evaluating runner's normalized `/proc/cpuinfo` flags line, or `null` |
| `runner_image` | the evaluating runner's image, `$ImageOS $ImageVersion` (e.g. `ubuntu24 20261025.353.1`), or `null` |

## Verify

```
python -m piperobot.reports.certificate verify results.json --bundle bundle.jsonl
python -m piperobot.reports.certificate verify candidate.json --reference reference.json --bundle bundle.jsonl
```

The verifier pins the signer `certify.yml` on `refs/heads/main`, a hosted runner and this
predicate type. It also checks that the series matches the calling workflow, that the record
agrees with the files (counts, seeds, and the paired cells for nightly), and the certificate's
commit and run. The `reference_commit` is a claim of the signed record; it cannot be recomputed
from the files.
