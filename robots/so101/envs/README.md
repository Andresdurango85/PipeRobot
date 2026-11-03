# SO-101 replay configuration

- `joint_units.json` and `joint_units.py`: named, reversible raw/radian mapping. The degree
  ranges belong to the course robot USD, not to LeRobot. No clipping is applied.
- `demo_datasets.json`: pinned demo revisions and the measured control rate with provenance.
- `vials_to_rack.json`: course scene regions, randomization, sources and TCP offset in metres.
- `course_actuators.json`: the course robot's gains, for the matched-gains diagnostic only.
- `demo_replay.py`: standard-library event detection, geometry, tracking and fixed verdict rules.

The course dataset says 30 fps but holds 60 Hz control (physics dt 1/120 s, decimation 2),
measured by replaying it with the course's gains
([ADR 0024](../../../docs/decisions/0024-so101-demo-replay-go-no-go-and-control-rate.md),
[Isaac notes](../../../docs/knowledge/isaac.md)).

Extract with `tools/demo_extract.py`, replay with `tools/isaac_demo_replay.py` in Isaac Lab 3.0
(`--actuators usd` is the registered go/no-go, `--actuators usd course` adds the diagnostic), and
regenerate the portable report with `tools/demo_replay_report.py`. Paths are relative to
`robots/so101/`. No object interaction is judged in this check.

- `course_assets.json`: pinned course asset sizes, LFS hashes, provenance and unresolved references.
- `vials_to_rack_success.py`: stdlib placement and confirmation tracker using XYZW poses.
- `../tools/fetch_course_assets.py`: verified HTTPS fetch/check into an external cache.
