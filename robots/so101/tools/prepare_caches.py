"""Fill and verify evaluator caches from the repository environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

TOOLS = Path(__file__).resolve().parent
ROBOT = TOOLS.parent


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(
    argv: Sequence[str] | None = None,
    *,
    fetch: Callable[[str], bytes] | None = None,
    extract: Callable[[Mapping[str, object], int | None], object] | None = None,
) -> int:
    # Load sibling tools by path, including when this module itself is loaded by path.
    from piperobot.adapters.isaaclab.specs import load_module
    from piperobot.cache import cache_root

    assets = load_module("_prepare_assets", TOOLS / "fetch_course_assets.py")
    demos = load_module("_prepare_demos", TOOLS / "demo_extract.py")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--only", choices=("assets", "episodes"))
    args = parser.parse_args(argv)
    try:
        root = assets.validate_cache_dir(args.cache_root or cache_root())
    except ValueError as exc:
        parser.error(str(exc))
    print(f"cache root: {root}")
    failed = False
    if args.only != "episodes":
        try:
            manifest = json.loads((ROBOT / "envs/course_assets.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"course_assets.json: {exc}", file=sys.stderr)
            return 1
        directory = root / "course-assets" / manifest["source"]["commit"]
        for entry in manifest["assets"]:
            name = entry["name"]
            single = {**manifest, "assets": [entry]}
            try:
                result = assets.fetch_assets(
                    single, directory, include_reference=True, fetch=fetch or assets.download
                )
                status = "ok" if result[name] == "cached" else "fetched"
                print(f"{status} {name}")
            except Exception as exc:
                detail = str(exc).removeprefix(f"{name}: ")
                detail = detail.replace("expected sha256 ", "expected ").replace(
                    ", actual ", " got ", 1
                )
                print(f"MISMATCH {name} {detail}", file=sys.stderr)
                failed = True
    if args.only != "assets":
        try:
            entries = json.loads((ROBOT / "envs/demo_datasets.json").read_text(encoding="utf-8"))
            policy = json.loads((ROBOT / "policies/demo_replay.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"episodes.json configuration: {exc}", file=sys.stderr)
            return 1
        for entry in entries["datasets"]:
            target = (
                root
                / "datasets"
                / entry["repo_id"].replace("/", "--")
                / entry["revision"]
                / "episodes.json"
            )
            part = target.with_suffix(".json.part")
            try:
                pins = [
                    pin["sha256"]
                    for pin in policy["files"]
                    if Path(pin["path"].replace("${PIPEROBOT_CACHE}", str(root))).resolve()
                    == target.resolve()
                ]
                if len(pins) != 1:
                    raise ValueError("Expected exactly one policy hash pin")
                expected = pins[0]
                if target.is_file() and digest(target) == expected:
                    print("ok episodes.json")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                data = (extract or demos.extract)(entry, None)
                with part.open("wb") as stream:
                    stream.write(demos.serialize(data))
                    stream.flush()
                    os.fsync(stream.fileno())
                actual = digest(part)
                if actual != expected:
                    raise ValueError(f"expected {expected} got {actual}")
                os.replace(part, target)
                print("fetched episodes.json")
            except Exception as exc:
                print(f"MISMATCH episodes.json ({target}) {exc}", file=sys.stderr)
                failed = True
            finally:
                part.unlink(missing_ok=True)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
