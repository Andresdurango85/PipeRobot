"""Evaluate each seed in a fresh Isaac process; crashes never count as trials."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from piperobot.adapters.isaaclab.specs import PolicySpec, TaskSpec, object_dict, read_object
from piperobot.results import EpisodeResult, EvalResults, ResultsError, save_results

REPO_ROOT = Path(__file__).resolve().parents[3]


class Runner(Protocol):
    def __call__(
        self, command: list[str], *, cwd: Path, env: dict[str, str], timeout: float
    ) -> subprocess.CompletedProcess[str]: ...


def run_process(
    command: list[str], *, cwd: Path, env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - explicit evaluator executable and argument list
        command, cwd=cwd, env=env, timeout=timeout, capture_output=True, text=True, check=False
    )


def git_commit() -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - resolved git executable and fixed arguments
            [git, "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def parse_seeds(value: str) -> list[int]:
    try:
        if "," not in value and "-" in value[1:]:
            first, last = value.split("-", 1)
            seeds = list(range(int(first), int(last) + 1))
        else:
            seeds = [int(part) for part in value.split(",")]
    except ValueError as exc:
        raise ResultsError("Seeds must be an inclusive range or comma-separated integers") from exc
    if not seeds or len(seeds) != len(set(seeds)):
        raise ResultsError("Seeds must be nonempty and unique")
    return seeds


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8"
    )


def validate_episode(data: dict[str, object], seed: int) -> EpisodeResult:
    if type(data.get("seed")) is not int or data["seed"] != seed:
        raise ResultsError("Worker returned a missing or mismatched seed")
    success = data.get("success")
    scene = data.get("scene")
    failure = data.get("failure")
    if not isinstance(success, bool) or not isinstance(scene, str) or not scene:
        raise ResultsError("Worker must return boolean success and a scene label")
    if not success and (not isinstance(failure, str) or not failure):
        raise ResultsError("Failed trial must include a failure reason")
    if not isinstance(data.get("platform"), dict):
        raise ResultsError("Worker must return platform metadata")
    return EpisodeResult(seed, success, scene, None if success else str(failure))


def evaluate(args: argparse.Namespace, *, runner: Runner = run_process) -> int:
    started = time.perf_counter()
    start_timestamp = timestamp()
    task = TaskSpec.load(args.task)
    policy = PolicySpec.load(args.policy)
    seeds = select_seeds(args)
    workdir = args.workdir.resolve()
    if workdir == REPO_ROOT or REPO_ROOT in workdir.parents:
        raise ResultsError("--workdir must be outside the repository")
    workdir.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # A previous successful run must not survive a failed replacement evaluation.
    output.unlink(missing_ok=True)
    metadata: dict[str, object] = {
        "task": asdict(task),
        "policy": asdict(policy),
        "layout": task.layout,
        "device": args.device,
        "git_commit": git_commit(),
        "start_timestamp": start_timestamp,
    }
    details: list[dict[str, object]] = []
    episodes = []
    first_platform: dict[str, object] | None = None
    differences: list[dict[str, object]] = []
    error: str | None = None
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(REPO_ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    with tempfile.TemporaryDirectory(prefix="piperobot-", dir=workdir) as temporary:
        for seed in seeds:
            worker_out = Path(temporary) / f"episode-{seed}.json"
            command = [
                str(args.isaac_python.resolve()),
                "-m",
                "piperobot.adapters.isaaclab.episode",
                "--task",
                str(args.task.resolve()),
                "--policy",
                str(args.policy.resolve()),
                "--seed",
                str(seed),
                "--out",
                str(worker_out),
                "--device",
                args.device,
                "--viz",
                "none",
            ]
            process_started = time.perf_counter()
            code: int | None = None
            stderr = ""
            detail: dict[str, object] = {"seed": seed}
            try:
                process = runner(command, cwd=workdir, env=env.copy(), timeout=task.timeout_s)
                code, stderr = process.returncode, process.stderr
                if code != 0:
                    raise ResultsError("Worker exited unsuccessfully")
                data = read_object(worker_out)
                detail.update(data)
                episode = validate_episode(data, seed)
                platform = object_dict(data["platform"], "platform")
                if first_platform is None:
                    first_platform = platform
                else:
                    changed = {
                        key: {"first": first_platform.get(key), "current": platform.get(key)}
                        for key in first_platform.keys() | platform.keys()
                        if key not in first_platform
                        or key not in platform
                        or first_platform.get(key) != platform.get(key)
                    }
                    if changed:
                        differences.append({"seed": seed, "fields": changed})
                episodes.append(episode)
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                if isinstance(exc, subprocess.TimeoutExpired):
                    raw = exc.stderr or ""
                    stderr = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
                error = f"Seed {seed}, exit code {code}: {exc}; stderr tail: {stderr[-4000:]}"
                detail["error"] = error
                print(error, file=sys.stderr)
            detail.update(
                exit_code=code, process_wall_seconds=time.perf_counter() - process_started
            )
            detail["stderr_tail"] = stderr[-4000:]
            details.append(detail)
            if error:
                break
    metadata.update(
        end_timestamp=timestamp(),
        wall_seconds=time.perf_counter() - started,
        platform=first_platform,
        platform_differences=differences,
    )
    if error:
        metadata["error"] = error
    write_json(output.with_name("run_metadata.json"), metadata)
    write_json(output.with_name("episodes_detail.json"), details)
    if error:
        return 2
    results = EvalResults(policy.name, "isaaclab", tuple(episodes))
    save_results(results, output)
    print(f"{policy.name}: {results.successes}/{results.trials} episodes succeeded")
    return 0


def select_seeds(args: argparse.Namespace) -> list[int]:
    if args.seeds is not None:
        if args.seed is not None:
            raise ResultsError("--seed is only valid with --episodes")
        return parse_seeds(args.seeds)
    if args.episodes is None or args.episodes <= 0:
        raise ResultsError("--episodes must be positive")
    start = args.seed if args.seed is not None else 0
    return list(range(start, start + args.episodes))


def main(argv: Sequence[str] | None = None, *, runner: Runner = run_process) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seeds")
    group.add_argument("--episodes", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--isaac-python", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args(argv)
    try:
        return evaluate(args, runner=runner)
    except (ResultsError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
