# Predicate type: gate verdict, v1

`https://github.com/Andresdurango85/PipeRobot/blob/main/docs/attestations/gate-verdict-v1.md`

This URI is the `predicateType` of PipeRobot's certificates of evaluation
([ADR 0030](../decisions/0030-signed-certificates-of-evaluation.md)). It never changes: a new
record format gets a `gate-verdict-v2` page.

## Statement

- **Subject**: one file, the evaluation's `results.json` (the results contract,
  `piperobot/results.py`), by sha256.
- **Predicate**: one history record, schema 1, exactly as stored in `history.json` on the
  `history` branch ([ADR 0026](../decisions/0026-success-rate-history-data-branch-and-pages.md)):

| Field | Meaning |
| --- | --- |
| `schema` | `1` |
| `commit`, `commit_date` | The evaluated commit on `main` and its committer date (UTC) |
| `evaluated_at` | When the evaluation ran (UTC) |
| `run_url`, `run_id`, `run_attempt` | The workflow run that evaluated and signed |
| `policy`, `evaluator` | From `results.json` |
| `successes`, `trials` | The candidate's counts |
| `confidence`, `interval` | Confidence level and the candidate's Wilson interval |
| `baseline` | The stored baseline's `successes` and `trials` |
| `difference_interval` | Newcombe interval of candidate − baseline |
| `tolerance` | The WARN tolerance, as a fraction |
| `verdict` | `pass`, `warn` or `block` |
| `seeds` | Episode seeds, compressed ranges (`1000-1049`) |
| `platform` | The evaluating runner's CPU, e.g. `AMD EPYC 7763 64-Core Processor, 4 CPUs` |

## Verify

With the files from the `history` branch (`results/<run>.<attempt>.json`,
`bundles/<run>.<attempt>.jsonl`), no GitHub login needed:

```
python -m piperobot.reports.certificate verify results.json --bundle bundle.jsonl
```

or with `gh` alone:

```
gh attestation verify results.json --bundle bundle.jsonl \
  --repo Andresdurango85/PipeRobot \
  --signer-workflow Andresdurango85/PipeRobot/.github/workflows/history.yml \
  --source-ref refs/heads/main --deny-self-hosted-runners \
  --predicate-type https://github.com/Andresdurango85/PipeRobot/blob/main/docs/attestations/gate-verdict-v1.md
```

The `gh` check proves the signer, commit and subject; the PipeRobot command also checks that the
signed record agrees with `results.json`. What a certificate does and does not prove: see
ADR 0030.
