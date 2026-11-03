"""Run each selected episode in a fresh Isaac process and merge results."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from isaac_repeatability import parser_options, runner_worker_running, select_episodes, timestamp

ProcessRunner = Callable[..., subprocess.CompletedProcess]


def drive(args: argparse.Namespace, runner: ProcessRunner = subprocess.run) -> dict:
    data = json.loads(args.episodes_json.read_text(encoding="utf-8"))
    indices = select_episodes(args.episodes, [ep["index"] for ep in data["episodes"]])
    indices.sort(reverse=args.order == "reverse")
    started = time.perf_counter()
    start_timestamp = timestamp()
    worker_start = runner_worker_running()
    episodes, children = [], []
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    with TemporaryDirectory(prefix="repeatability-") as directory:
        for index in indices:
            output = Path(directory) / f"episode-{index}.json"
            tool = Path(__file__).with_name("isaac_repeatability.py")
            command = [
                str(args.isaac_python),
                str(tool),
                "--episodes-json",
                str(args.episodes_json.resolve()),
                "--out",
                str(output),
                "--config-label",
                args.config_label,
                "--episodes",
                str(index),
                "--order",
                args.order,
                "--determinism",
                args.determinism,
                "--actuators",
                args.actuators,
                "--device",
                args.device,
                "--viz",
                args.viz,
            ]
            if args.full_reset:
                command.append("--full-reset")
            if args.assets_dir is not None:
                command.extend(["--assets-dir", str(args.assets_dir.resolve())])
            process_started = time.perf_counter()
            try:
                process = runner(command, cwd=args.workdir, env=env, check=False)
                code = process.returncode
            except OSError as exc:
                children.append({"wall_seconds": time.perf_counter() - process_started})
                episodes.append({"index": index, "exit_code": -1, "error": str(exc)})
                continue
            try:
                child = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
            except (OSError, ValueError) as exc:
                child = {"error": f"Unreadable episode result: {exc}"}
            child_metadata = child.get("metadata", {})
            child_metadata.setdefault("wall_seconds", time.perf_counter() - process_started)
            children.append(child_metadata)
            child_eps = child.get("episodes", [])
            if code or len(child_eps) != 1 or child_eps[0].get("index") != index:
                episodes.append(
                    {
                        "index": index,
                        "exit_code": code,
                        "error": child.get("error", "Missing or invalid episode result"),
                    }
                )
            else:
                episodes.extend(child_eps)
    metadata = dict(children[0]) if children else {}
    metadata.update(
        config_label=args.config_label,
        process_per_episode=True,
        options={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        start_timestamp=start_timestamp,
        end_timestamp=timestamp(),
        runner_worker_start=worker_start,
        runner_worker_end=runner_worker_running(),
        wall_seconds=sum(child.get("wall_seconds", 0) for child in children),
        end_to_end_wall_seconds=time.perf_counter() - started,
        child_metadata=children,
    )
    return {"metadata": metadata, "episodes": episodes}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser_options(parser)
    parser.add_argument("--isaac-python", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--device", choices=("cuda:0", "cpu"), default="cuda:0")
    parser.add_argument("--viz", choices=("none",), default="none")
    args = parser.parse_args(argv)
    report = drive(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return int(any("exit_code" in ep for ep in report["episodes"]))


if __name__ == "__main__":
    raise SystemExit(main())
