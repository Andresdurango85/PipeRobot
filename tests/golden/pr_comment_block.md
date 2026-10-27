<!-- piperobot-gate -->
## ❌ PipeRobot gate: BLOCK

Regression: success rate dropped 40.0 pp and the 95% interval of the difference [-0.545, -0.225] is entirely below zero.

| | Episodes | Success rate | 95% CI |
| --- | ---: | ---: | ---: |
| Candidate (`d70f397`) | 25/50 | 50.0% | 36.6% to 63.4% |
| Baseline | 45/50 | 90.0% | 78.6% to 95.7% |
| **Difference** | | **-40.0 pp** | -54.5 pp to -22.5 pp |

### Failed episodes (25)

| Seed | Scene | Failure | Video |
| ---: | --- | --- | --- |
| 0 | rack_0 | tube dropped | [▶ video](https://example.org/episode_0.mp4) |
| 1 | rack_1 | tube dropped | [▶ video](https://example.org/episode_1.mp4) |
| 2 | rack_2 | tube dropped | [▶ video](https://example.org/episode_2.mp4) |
| 3 | rack_0 | tube dropped | [▶ video](https://example.org/episode_3.mp4) |
| 4 | rack_1 | tube dropped | [▶ video](https://example.org/episode_4.mp4) |
| 5 | rack_2 | tube dropped | [▶ video](https://example.org/episode_5.mp4) |
| 6 | rack_0 | tube dropped | [▶ video](https://example.org/episode_6.mp4) |
| 7 | rack_1 | tube dropped | [▶ video](https://example.org/episode_7.mp4) |
| 8 | rack_2 | tube dropped | [▶ video](https://example.org/episode_8.mp4) |
| 9 | rack_0 | tube dropped | [▶ video](https://example.org/episode_9.mp4) |

_…and 15 more in the [workflow run](https://github.com/Andresdurango85/PipeRobot/actions/runs/1)._

<details><summary>How to read this verdict</summary>

Each episode is a pass/fail attempt at the task with its own seed and scene variation. The 95% interval of the difference (candidate - baseline) accounts for the luck of both runs.

- **BLOCK**: the whole interval is below zero, so the policy is worse. The PR is blocked.
- **WARN**: the rate dropped more than 10 pp, but the interval still includes zero. The PR passes; more episodes are needed to tell.
- **PASS**: no regression detected.

</details>

<sub>[Workflow run](https://github.com/Andresdurango85/PipeRobot/actions/runs/1) · commit `d70f397`</sub>
