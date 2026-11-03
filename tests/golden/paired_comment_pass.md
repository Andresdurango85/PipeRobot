<!-- piperobot-gate:test -->
## ✅ Policy gate: PASS

| Measurement | Value |
| --- | ---: |
| Reference | 40/50 (80.0%) |
| Candidate | 40/50 (80.0%) |
| Episodes lost / gained | 0 / 0 |
| Exact McNemar p | 1 |
| Difference (candidate - reference) | +0.0 pp |
| 95% paired CI | -4.3 to +4.3 pp |

No regression detected: difference \+0\.0 pp \(0 episodes lost, 0 gained\)\. Exact McNemar p=1, alpha=0\.025\.

**Candidate failed seeds:** 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29 … and 10 more

<details><summary>How to read this verdict</summary>

The reference and candidate run on the same seeds on the same runner. Only discordant episodes count in the exact McNemar test: episodes lost by the candidate or gained over the reference. Shared successes and failures provide no evidence of a difference.

- **BLOCK**: exact one-sided p < 0.025.
- **WARN**: not significant, but the drop exceeds 10 pp; more episodes are needed.
- **PASS**: no regression detected.

The paired confidence interval reports the size of the difference; it does not decide.

</details>

commit abcdef123 · [Workflow run](https://example.com/run/1)
