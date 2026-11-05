"""Verify rerun fingerprints before frames can be encoded."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Hashable, Mapping, Sequence
from pathlib import Path
from typing import Any


class VideoInputError(ValueError):
    """Video evidence input is missing or malformed."""


def build_manifest(
    selection: Mapping[str, Any],
    judged: Sequence[Mapping[str, Any]],
    recorded: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(selection, Mapping) or not isinstance(selection.get("seeds"), list):
        raise VideoInputError("selection must be an object with a seeds list")
    for label, episodes in (
        ("selection seeds", selection["seeds"]),
        ("judged", judged),
        ("recorded", recorded),
    ):
        if not isinstance(episodes, Sequence) or isinstance(episodes, (str, bytes, bytearray)):
            raise VideoInputError(f"{label} must be a sequence of objects with seed")
        for episode in episodes:
            if not isinstance(episode, Mapping) or "seed" not in episode:
                raise VideoInputError(f"{label} must contain objects with seed")
            if not isinstance(episode["seed"], Hashable):
                raise VideoInputError(f"{label}: seed must be hashable")
    original = {episode["seed"]: episode for episode in judged}
    reruns = {episode["seed"]: episode for episode in recorded}
    entries = []
    for item in selection["seeds"]:
        seed = item["seed"]
        before, after = original.get(seed), reruns.get(seed)
        entry = {**item, "status": "missing"}
        if after is not None:
            matched = (
                before is not None
                and bool(before.get("trajectory_sha256"))
                and all(
                    before.get(key) == after.get(key)
                    for key in ("success", "failure", "trajectory_sha256")
                )
                and "error" not in after
            )
            entry["status"] = "matched" if matched else "diverged"
            if matched:
                entry["frames"] = after.get("frames", 0)
        entries.append(entry)
    return {"seeds": entries}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("selection", "judged", "recorded", "frames-dir", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args(argv)
    inputs = []
    for path in (args.selection, args.judged, args.recorded):
        try:
            contents = path.read_text(encoding="utf-8-sig")
        except (OSError, ValueError) as exc:
            print(f"ERROR: {path}: {' '.join(str(exc).splitlines())}", file=sys.stderr)
            return 2
        try:
            inputs.append(json.loads(contents))
        except (ValueError, RecursionError) as exc:
            print(f"ERROR: {path}: {' '.join(str(exc).splitlines())}", file=sys.stderr)
            return 2
    try:
        manifest = build_manifest(*inputs)
    except VideoInputError as exc:
        print(f"ERROR: {' '.join(str(exc).splitlines())}", file=sys.stderr)
        return 2
    for entry in manifest["seeds"]:
        # Only integer seed directories under the supplied frames root may be removed.
        seed = entry["seed"]
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        directory = args.frames_dir / str(seed)
        if entry["status"] != "matched" and directory.exists():
            if directory.resolve().parent != args.frames_dir.resolve():
                raise ValueError("frames directory escapes the frames root")
            if directory.is_symlink():
                raise ValueError("frames directory must not be a symlink")
            shutil.rmtree(directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
