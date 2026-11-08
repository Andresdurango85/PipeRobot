<!-- piperobot-gate:test -->
## ✅ Policy gate: PASS

| Measurement | Value |
| --- | ---: |
| Reference | 1/2 (50.0%) |
| Candidate | 1/2 (50.0%) |
| Episodes lost / gained | 0 / 0 |
| Exact McNemar p | 1 |
| Difference (candidate - reference) | +0.0 pp |
| 95% paired CI | +0.0 to +0.0 pp |

### distance (cm)

| Run | Median | p90 | IQR |
| --- | ---: | ---: | ---: |
| Reference | 2 | 2.8 | 1 |
| Candidate | 2 | 2.8 | 1 |

Success when distance is below 2 cm.

> **Warning:** the threshold lies within one IQR of the reference median, so the success rate is sensitive to small shifts in distance.

> **Warning:** the threshold lies within one IQR of the candidate median, so the success rate is sensitive to small shifts in distance.

No regression detected: difference \+0\.0 pp \(0 episodes lost, 0 gained\)\. Exact McNemar p=1, alpha=0\.025\.

**Candidate failed seeds:** 1

<details><summary>How to read this verdict</summary>

The reference and candidate run on the same seeds on the same runner. Only discordant episodes count in the exact McNemar test: episodes lost by the candidate or gained over the reference. Shared successes and failures provide no evidence of a difference.

- **BLOCK**: exact one-sided p < 0.025.
- **WARN**: not significant, but the drop exceeds 10 pp; more episodes are needed.
- **PASS**: no regression detected.

The paired confidence interval reports the size of the difference; it does not decide.

</details>
