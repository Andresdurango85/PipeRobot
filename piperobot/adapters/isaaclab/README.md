# Isaac Lab adapter

- `specs.py`: stdlib task/policy specs, pinned input validation and policy protocols.
- `episode.py`: one-seed worker; Isaac imports only after argument/help parsing.
- `evaluate.py`: isolated subprocess driver and gate results, metadata and full episode details.

Prepare policy inputs using the command in its spec before starting; no worker downloads data.
Run from the repository Python environment, with an existing Isaac Python executable:

```powershell
python -m piperobot.adapters.isaaclab.evaluate --task <task.json> --policy <policy.json> --episodes 50 --seed 0 --isaac-python <isaac-python.exe> --workdir <directory-outside-repo> --output <results.json> --device cuda:0
```

Use `--seeds 0-74` or `--seeds 0,3,7` instead of `--episodes`/`--seed` for explicit run order.
Every seed gets a fresh process and the task's wall timeout. A policy failure is a trial;
infrastructure errors get one retry with a fresh worker and output path (two attempts per seed).
At most three seeds may need retries; a fourth or two failed attempts stops with exit 2,
writes diagnostics, and publishes no results. Policy failures are never retried.
The output directory also receives `run_metadata.json` and `episodes_detail.json`.
Run evaluations in separate output directories to retain earlier reports.
Both command-line modules support `--help` without Isaac installed.
