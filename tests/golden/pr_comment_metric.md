<!-- piperobot-gate -->
## ✅ PipeRobot gate: PASS

No significant difference: difference interval [-0.573, 0.573] includes zero.

| | Episodes | Success rate | 95% CI |
| --- | ---: | ---: | ---: |
| Candidate | 1/2 | 50.0% | 9.5% to 90.5% |
| Baseline | 1/2 | 50.0% | 9.5% to 90.5% |
| **Difference** | | **+0.0 pp** | -57.3 pp to +57.3 pp |

### distance (cm)

| Run | Median | p90 | IQR |
| --- | ---: | ---: | ---: |
| Candidate | 2 | 2.8 | 1 |

Success when distance is below 2 cm.

> **Warning:** the threshold lies within one IQR of the candidate median, so the success rate is sensitive to small shifts in distance.

### Failed episodes (1)

_No per-episode details were provided._

<details><summary>How to read this verdict</summary>

Each episode is a pass/fail attempt at the task with its own seed and scene variation. The 95% interval of the difference (candidate - baseline) accounts for the luck of both runs.

- **BLOCK**: the whole interval is below zero, so the policy is worse. The PR is blocked.
- **WARN**: the rate dropped more than 10 pp, but the interval still includes zero. The PR passes; more episodes are needed to tell.
- **PASS**: no regression detected.

</details>
