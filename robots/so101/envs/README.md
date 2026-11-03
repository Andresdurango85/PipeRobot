# SO-101 replay configuration

- `joint_units.json` and `joint_units.py`: named, reversible raw/radian mapping. The degree
  ranges belong to the course robot USD, not to LeRobot. No clipping is applied.
- `demo_datasets.json`: pinned demo revisions and optional measured control rate with provenance.
- `vials_to_rack.json`: course scene regions, randomization, sources and TCP offset in metres.
- `demo_replay.py`: standard-library event detection, geometry, tracking and fixed verdict rules.

The course recorded 60 Hz control despite 30 fps metadata: physics dt 1/120 s and decimation 2.
See [the verified Isaac notes](../../../docs/knowledge/isaac.md). The initial dataset entry keeps
its measured override null pending replay; compare substeps 2 and 4 before choosing a rate.

Extract with `tools/demo_extract.py`, replay with `tools/isaac_demo_replay.py` in Isaac Lab 3.0,
and regenerate the portable report with `tools/demo_replay_report.py`. Paths are relative to
`robots/so101/`. No object interaction is judged in this check.
