"""Offline coverage of specs, isolated workers, replay and seeded scene sampling."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from piperobot.adapters.isaaclab import evaluate
from piperobot.adapters.isaaclab.specs import PolicySpec, TaskSpec, load_module
from piperobot.results import ResultsError, load_results

ROOT = Path(__file__).resolve().parents[1]
POLICY = load_module("test_demo_policy", ROOT / "robots/so101/policies/demo_replay.py")
TASK = load_module("test_tube_task", ROOT / "robots/so101/envs/vials_to_rack_task.py")
RANDOM = load_module(
    "test_random_layout", ROOT / "robots/so101/envs/vials_to_rack_randomization.py"
)


def write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def specs(tmp_path: Path) -> tuple[Path, Path]:
    task = write(
        tmp_path / "task.json",
        {
            "name": "test-task",
            "module": "task.py",
            "layout": "test",
            "options": {},
        },
    )
    policy = write(
        tmp_path / "policy.json",
        {
            "name": "test-policy",
            "module": "policy.py",
            "factory": "make",
            "options": {},
        },
    )
    return task, policy


def test_specs(specs: tuple[Path, Path]) -> None:
    task, policy = specs
    assert TaskSpec.load(task).module == task.parent / "task.py"
    assert TaskSpec.load(task).timeout_s == 300
    assert PolicySpec.load(policy).module == policy.parent / "policy.py"


def test_policy_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLICY_CACHE", str(tmp_path))
    path = tmp_path / "episodes.json"
    spec = tmp_path / "policy.json"
    data = {
        "name": "demo",
        "module": "policy.py",
        "factory": "make",
        "options": {"episodes_json": "${POLICY_CACHE}/episodes.json"},
        "files": [{"path": "${POLICY_CACHE}/episodes.json", "sha256": "bad"}],
        "prepare": "python demo_extract.py --out episodes.json",
    }
    write(spec, data)
    with pytest.raises(ResultsError, match=r"Missing.*demo_extract"):
        PolicySpec.load(spec)
    path.write_bytes(b"pinned")
    with pytest.raises(ResultsError, match=r"SHA256 mismatch.*demo_extract"):
        PolicySpec.load(spec)
    data["files"][0]["sha256"] = hashlib.sha256(b"pinned").hexdigest()
    write(spec, data)
    loaded = PolicySpec.load(spec)
    assert loaded.files[0]["path"] == str(path)
    assert loaded.options["episodes_json"] == str(tmp_path) + "/episodes.json"


@pytest.mark.parametrize("timeout", [0, -1, True, "300"])
def test_invalid_timeout(specs: tuple[Path, Path], timeout: object) -> None:
    task, _ = specs
    data = json.loads(task.read_text())
    data["timeout_s"] = timeout
    write(task, data)
    with pytest.raises(ResultsError, match="timeout_s"):
        TaskSpec.load(task)


@pytest.mark.parametrize(("value", "expected"), [("0-74", list(range(75))), ("0,3,7", [0, 3, 7])])
def test_seeds(value: str, expected: list[int]) -> None:
    assert evaluate.parse_seeds(value) == expected


@pytest.mark.parametrize("value", ["0,0", "3-0", "", "a,b"])
def test_bad_seeds(value: str) -> None:
    with pytest.raises(ResultsError, match="Seeds"):
        evaluate.parse_seeds(value)


@pytest.mark.parametrize(
    "mode",
    [
        "pass",
        "trial_failure",
        "crash",
        "timeout",
        "invalid",
        "missing",
        "bad_success",
        "wrong_seed",
    ],
)
def test_driver(
    specs: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
) -> None:
    monkeypatch.setattr(evaluate, "git_commit", lambda: "test-commit")
    monkeypatch.setattr(evaluate, "REPO_ROOT", tmp_path / "repo")
    task, policy = specs
    output = tmp_path / "result" / "results.json"
    output.parent.mkdir()
    output.write_text("stale result")
    calls = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        seed = int(command[command.index("--seed") + 1])
        path = Path(command[command.index("--out") + 1])
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, 300, stderr=b"timeout details")
        if mode == "crash":
            return subprocess.CompletedProcess(command, 7, "", "crash details")
        if mode == "invalid":
            path.write_text("{broken")
        elif mode != "missing":
            write(
                path,
                {
                    "seed": seed + 1 if mode == "wrong_seed" else seed,
                    "scene": "scene",
                    "success": "yes" if mode == "bad_success" else mode == "pass",
                    "failure": "no_grasp",
                    "trajectory_sha256": "fingerprint",
                    "platform": {"device": "cpu", "varying": seed},
                },
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    argv = [
        "--task",
        str(task),
        "--policy",
        str(policy),
        "--seeds",
        "0,3,7",
        "--isaac-python",
        "isaac-python",
        "--workdir",
        str(tmp_path / "work"),
        "--output",
        str(output),
        "--device",
        "cpu",
    ]
    code = evaluate.main(argv, runner=runner)
    details = json.loads(output.with_name("episodes_detail.json").read_text())
    metadata = json.loads(output.with_name("run_metadata.json").read_text())
    if mode in {"pass", "trial_failure"}:
        assert code == 0
        results = load_results(output)
        assert results.trials == 3
        assert results.successes == (3 if mode == "pass" else 0)
        assert [ep.seed for ep in results.episodes] == [0, 3, 7]
        assert all(ep.failure == "no_grasp" for ep in results.failed)
        assert "test-policy:" in capsys.readouterr().out
        assert len(metadata["platform_differences"]) == 2
        assert len(details) == 3
    else:
        assert code == 2
        assert not output.exists()
        assert len(calls) == len(details) == 1
        assert "error" in metadata
        assert "Seed 0, exit code" in capsys.readouterr().err
    for _, kwargs in calls:
        assert kwargs["cwd"] == (tmp_path / "work").resolve()
        assert kwargs["timeout"] == 300
        assert kwargs["env"]["PYTHONUNBUFFERED"] == "1"
        assert kwargs["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(tmp_path / "repo")
    assert metadata["git_commit"] == "test-commit"


def test_episode_count() -> None:
    import argparse

    assert evaluate.select_seeds(argparse.Namespace(seeds=None, episodes=3, seed=1000)) == [
        1000,
        1001,
        1002,
    ]
    with pytest.raises(ResultsError, match="positive"):
        evaluate.select_seeds(argparse.Namespace(seeds=None, episodes=0, seed=None))


@pytest.mark.parametrize("module", ["episode", "evaluate"])
def test_help(module: str) -> None:
    process = subprocess.run(  # noqa: S603 - current Python and fixed adapter help arguments
        [sys.executable, "-m", f"piperobot.adapters.isaaclab.{module}", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert "--task" in process.stdout


def test_randomization() -> None:
    data = json.loads((ROOT / "robots/so101/envs/vials_to_rack.json").read_text())
    assert RANDOM.sample_layout(42, data) == RANDOM.sample_layout(42, data)
    assert RANDOM.sample_layout(42, data) != RANDOM.sample_layout(43, data)
    for seed in range(100):
        layout = RANDOM.sample_layout(seed, data)
        for pose, origin in zip(layout.tubes, data["tubes"]["origins_m"], strict=True):
            for axis, key in enumerate(("x_range_m", "y_range_m")):
                low, high = data["tubes"][key]
                assert origin[axis] + low <= pose[axis] <= origin[axis] + high
            assert pose[2] == origin[2]
        for axis, key in enumerate(("x_range_m", "y_range_m")):
            low, high = data["rack"][key]
            origin = data["rack"]["origin_m"][axis]
            assert origin + low <= layout.rack_position[axis] <= origin + high
        assert -0.5 <= layout.rack_yaw <= 0.5
    assert any(abs(RANDOM.sample_layout(seed, data).rack_yaw) > 0.1 for seed in range(10))


def test_replay_and_task(tmp_path: Path) -> None:
    path = write(
        tmp_path / "episodes.json",
        {
            "joint_names": ["gripper.pos"],
            "episodes": [
                {"index": 7, "action": [[7.0], [8.0]], "state": [[0.0], [0.0]]},
                {"index": 0, "action": [[1.0]], "state": [[0.0]]},
            ],
        },
    )
    policy = POLICY.DemoReplayPolicy(path)
    policy.reset(7)
    assert policy.reference_episode(7)["index"] == 7
    assert policy.act({"step": 1}) == [8.0]
    for seed in (-1, 75, 2):
        with pytest.raises(ValueError, match="out of range"):
            policy.reset(seed)
    assert TASK.scene_label(7, "reconstructed_demo") == "demo_7"
    assert TASK.scene_label(7, "randomized") == "randomized"
    with pytest.raises(ValueError, match="Open-loop replay ignores randomized"):
        TASK.validate_layout(policy, "randomized")
    TASK.validate_layout(policy, "reconstructed_demo")
    with pytest.raises(ValueError, match="Unknown layout"):
        TASK.scene_label(0, "unknown")


@pytest.mark.parametrize("fails", [False, True])
def test_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fails: bool,
) -> None:
    import argparse
    from collections.abc import Iterator
    from contextlib import contextmanager
    from types import ModuleType, SimpleNamespace

    from piperobot.adapters.isaaclab import episode

    entered = []
    launched: list[object] = []

    @contextmanager
    def launch_simulation(sim_cfg: object, args: object) -> Iterator[None]:
        launched.append(sim_cfg)
        entered.append(True)
        try:
            yield
        except SystemExit as exc:
            # The process exit must be requested while the simulator is still active.
            entered.append(exc.code)
            raise

    def add_launcher_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--device", default="cpu")
        parser.add_argument("--viz", default="none")

    app = ModuleType("isaaclab.app")
    app.add_launcher_args = add_launcher_args
    app.launch_simulation = launch_simulation
    sim = ModuleType("isaaclab.sim")
    sim.SimulationCfg = SimpleNamespace
    physx = ModuleType("isaaclab_physx.physics")
    physx.PhysxCfg = SimpleNamespace
    torch = ModuleType("torch")
    torch.cuda = SimpleNamespace(is_available=lambda: False)
    torch.version = SimpleNamespace(cuda=None)
    for name, module in {
        "isaaclab": ModuleType("isaaclab"),
        "isaaclab.app": app,
        "isaaclab.sim": sim,
        "isaaclab_physx": ModuleType("isaaclab_physx"),
        "isaaclab_physx.physics": physx,
        "torch": torch,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(episode, "version", lambda distribution: "test-version")
    task_module = tmp_path / "task.py"
    task_module.write_text(
        "def simulation_settings(options):\n"
        "    return {'dt': 0.25}\n"
        "def run_episode(**kwargs):\n"
        + (
            "    raise RuntimeError('task exploded')\n"
            if fails
            else "    return {'success': True, 'scene': 'test-scene'}\n"
        ),
        encoding="utf-8",
    )
    (tmp_path / "policy.py").write_text(
        "class Policy:\n    def reset(self, seed):\n        self.seed = seed\n",
        encoding="utf-8",
    )
    task = write(
        tmp_path / "task.json",
        {
            "name": "task",
            "module": "task.py",
            "layout": "test",
            "options": {"gain": 1},
        },
    )
    policy = write(
        tmp_path / "policy.json",
        {
            "name": "policy",
            "module": "policy.py",
            "factory": "Policy",
        },
    )
    output = tmp_path / "worker.json"
    output.write_text("stale")
    with pytest.raises(SystemExit, match="1" if fails else "0"):
        episode.main(
            [
                "--task",
                str(task),
                "--policy",
                str(policy),
                "--seed",
                "7",
                "--out",
                str(output),
            ]
        )
    assert entered == [True, 1 if fails else 0]
    # The task's settings are in the config before launch.
    assert getattr(launched[0], "dt", None) == 0.25
    if fails:
        assert not output.exists()
    else:
        data = json.loads(output.read_text())
        assert data["seed"] == 7
        assert data["platform"]["device"] == "cpu"
        assert data["platform"]["options"] == {"gain": 1}
        assert data["wall_seconds"] >= 0


def test_duplicate_driver_seeds(
    specs: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, policy = specs
    monkeypatch.setattr(evaluate, "git_commit", lambda: None)
    assert (
        evaluate.main(
            [
                "--task",
                str(task),
                "--policy",
                str(policy),
                "--seeds",
                "0,0",
                "--isaac-python",
                "unused",
                "--workdir",
                str(tmp_path / "work"),
                "--output",
                str(tmp_path / "results.json"),
            ],
            runner=lambda *args, **kwargs: pytest.fail("must not start workers"),
        )
        == 2
    )
    assert not (tmp_path / "results.json").exists()


def test_nonfinite_worker_json(tmp_path: Path) -> None:
    from piperobot.adapters.isaaclab.specs import read_object

    path = tmp_path / "bad.json"
    path.write_text('{"success": true, "wall_seconds": NaN}')
    with pytest.raises(ResultsError, match="Non-finite"):
        read_object(path)


def test_action_hook_preserves_replay_trace() -> None:
    """Exercise the actual runtime method without importing simulator dependencies."""
    import ast
    import time
    from contextlib import nullcontext
    from dataclasses import asdict, dataclass
    from types import SimpleNamespace

    source = ROOT / "robots/so101/envs/vials_to_rack_episodes.py"
    tree = ast.parse(source.read_text())
    runtime_class = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    method = next(
        n
        for n in runtime_class.body
        if isinstance(n, ast.FunctionDef) and n.name == "run_reconstructed_episode"
    )
    method.returns = None
    for argument in method.args.args:
        argument.annotation = None
    namespace = {
        "torch": SimpleNamespace(inference_mode=nullcontext),
        "time": time,
        "json": json,
        "hashlib": hashlib,
        "math": __import__("math"),
        "asdict": asdict,
    }

    @dataclass
    class Placement:
        origin_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)
        yaw: float = 0.0

    namespace["LAYOUT"] = SimpleNamespace(
        rack_pose_for_release=lambda *args: Placement(),
        tube_pose_for_grasp=lambda *args: (0.0,) * 7,
        park_poses=lambda *args: [],
    )
    namespace["CORE"] = SimpleNamespace(
        yaw_to_quat_xyzw=lambda *args: (0.0, 0.0, 0.0, 1.0),
        find_holds=lambda *args: [(0, 2)],
        HOLD_GAP=1,
    )
    namespace["UNITS"] = SimpleNamespace(to_lerobot=lambda values, table: values)
    namespace["distribution"] = lambda values: list(values)
    # Execute only the registered runtime method, with explicit offline dependencies.
    exec(  # noqa: S102 - compile the local runtime method for offline order regression coverage
        compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace
    )
    run = namespace["run_reconstructed_episode"]
    episode = {"index": 7, "state": [[0.0], [0.0]], "action": [[1.0], [2.0]]}

    class Scalar:
        def __getitem__(self, key: object) -> Scalar:
            return self

        def item(self) -> float:
            return 0.0

    class Runtime:
        def __init__(self) -> None:
            self.trace = []
            self.full_reset = False
            self.names = ["gripper"]
            self.gripper = 0
            self.data = {}
            self.table = {}
            self.rack = object()
            self.tubes = [object()]
            self.substeps = 2
            self.robot = SimpleNamespace(
                joint_names=self.names,
                data=SimpleNamespace(joint_pos=SimpleNamespace(torch=Scalar())),
                set_joint_position_target_index=lambda **kw: self.trace.append(("target", kw)),
            )
            self.tracker = SimpleNamespace(reset=lambda: None, failure_reason=lambda: None)
            self.sensor = SimpleNamespace(reset=lambda: None)

        def grasp_release_tcps(self, ep: object) -> tuple:
            return (0, 1, (0.0,) * 3, (0.0,) * 3)

        def reset_layout(self) -> None:
            self.trace.append("reset")

        def teleport(self, obj: object, pose: object) -> None:
            self.trace.append(("teleport", pose))

        def converted(self, row: list[float]) -> dict[str, float]:
            return {"gripper": row[0]}

        def set_joints(self, values: object) -> None:
            self.trace.append(("joints", values))

        def tensor(self, values: object) -> object:
            return values

        def physics_step(self) -> None:
            self.trace.append("step")

        def forces(self) -> list[float]:
            return [1.0]

        def sample(self, index: int) -> object:
            self.trace.append(("sample", index))
            self.dump_steps.append({"step": index, "forces": self.forces()})
            return SimpleNamespace(success=True, success_step=1)

    default = Runtime()
    hooked = Runtime()
    observations = []

    def actions(index: int, observation: object) -> list[float]:
        observations.append(observation)
        return episode["action"][index]

    original = run(default, episode, False)
    with_policy = run(hooked, episode, False, action_source=actions)
    assert default.trace == hooked.trace
    assert original["trajectory_sha256"] == with_policy["trajectory_sha256"]
    assert observations == [
        {"step": 0, "joint_pos": {"gripper": 0.0}},
        {"step": 1, "joint_pos": {"gripper": 0.0}},
    ]
