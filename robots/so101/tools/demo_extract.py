"""Extract pinned LeRobot v3 parquet episodes without downloading video."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


def feature_names(info: Mapping[str, Any]) -> list[str]:
    def names(key: str) -> list[str]:
        value = info["features"][key]["names"]
        if isinstance(value, dict):
            value = [n for axis in value.values() for n in axis]
        if not isinstance(value, list) or len(value) != 6 or len(set(value)) != 6:
            raise ValueError("Expected six unique feature names")
        return value

    action, state = names("action"), names("observation.state")
    if action != state:
        raise ValueError("Action and state feature names differ")
    return action


def rows_to_episodes(
    rows: Iterable[Mapping[str, Any]], max_episodes: int | None = None
) -> list[dict[str, Any]]:
    if max_episodes is not None and max_episodes < 1:
        raise ValueError("max_episodes must be positive")
    ordered = sorted(rows, key=lambda r: (r["episode_index"], r["frame_index"]))
    episodes: list[dict[str, Any]] = []
    previous = None
    for row in ordered:
        identity = (int(row["episode_index"]), int(row["frame_index"]))
        if identity == previous:
            raise ValueError("Duplicate episode/frame index")
        previous = identity
        if not episodes or episodes[-1]["index"] != identity[0]:
            if max_episodes is not None and len(episodes) == max_episodes:
                break
            episodes.append({"index": identity[0], "action": [], "state": []})
        if identity[1] != len(episodes[-1]["action"]):
            raise ValueError("Non-contiguous frame indices")
        for source, target in (("action", "action"), ("observation.state", "state")):
            values = [float(v) for v in row[source]]
            if len(values) != 6 or not all(math.isfinite(v) for v in values):
                raise ValueError("Expected six finite joint values")
            episodes[-1][target].append(values)
    if not episodes:
        raise ValueError("No episodes")
    return episodes


def extract(entry: Mapping[str, Any], max_episodes: int | None) -> dict[str, Any]:
    from huggingface_hub import snapshot_download
    from pyarrow import parquet

    root = Path(
        snapshot_download(
            repo_id=entry["repo_id"],
            repo_type="dataset",
            revision=entry["revision"],
            allow_patterns=["meta/info.json", "data/*"],
        )
    )
    info = json.loads((root / "meta/info.json").read_text(encoding="utf-8"))
    names = feature_names(info)
    rows = (
        row
        for path in sorted((root / "data").rglob("*.parquet"))
        for row in parquet.read_table(path).to_pylist()
    )
    return {
        "repo_id": entry["repo_id"],
        "revision": entry["revision"],
        "metadata_fps": info["fps"],
        "control_hz": entry["control_hz"],
        "control_hz_provenance": entry["control_hz_provenance"],
        "joint_names": names,
        "episodes": rows_to_episodes(rows, max_episodes),
    }


def serialize(data: object) -> bytes:
    """Serialize identical UTF-8 bytes on every platform, including the final LF."""
    return (json.dumps(data, allow_nan=False) + "\n").encode("utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", type=Path, required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-episodes", type=int)
    args = parser.parse_args(argv)
    entries = json.loads(args.datasets.read_text(encoding="utf-8"))["datasets"]
    matches = [e for e in entries if e["repo_id"] == args.repo_id]
    if len(matches) != 1:
        parser.error("Expected exactly one pinned dataset entry")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(serialize(extract(matches[0], args.max_episodes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
