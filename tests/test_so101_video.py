"""Offline contracts for optional episode recording."""

import builtins
import json
import subprocess
import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Never

import pytest
from test_so101_scripted import Array, runtime_class

from piperobot.adapters.isaaclab import evaluate
from piperobot.adapters.isaaclab.specs import load_module

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def specs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setattr(evaluate, "evaluated_repo", lambda path: None)
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"name": "task", "module": "task.py", "layout": "test"}))
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"name": "policy", "module": "policy.py", "factory": "make"}))
    return task, policy


@pytest.mark.parametrize("record", [False, True])
def test_record_command_retry_metadata(
    specs: tuple[Path, Path], tmp_path: Path, record: bool
) -> None:
    task, policy = specs
    output = tmp_path / "results.json"
    frames = tmp_path / "frames" / "7"
    calls = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        out = Path(command[command.index("--out") + 1])
        expected = [
            str((tmp_path / "python").resolve()),
            "-m",
            "piperobot.adapters.isaaclab.episode",
            "--task",
            str(task.resolve()),
            "--policy",
            str(policy.resolve()),
            "--seed",
            "7",
            "--out",
            str(out),
            "--device",
            "cuda:0",
            "--viz",
            "none",
        ]
        if record:
            expected += ["--record", str(frames.resolve())]
            assert not frames.exists()
            frames.mkdir(parents=True)
            (frames / "partial.jpg").write_text("partial")
        assert command == expected
        calls.append(command)
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, 1, "", "crash")
        out.write_text(
            json.dumps(
                {
                    "seed": 7,
                    "scene": "randomized",
                    "success": False,
                    "failure": "not_placed",
                    "platform": {},
                }
            )
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    argv = [
        "--task",
        str(task),
        "--policy",
        str(policy),
        "--seeds",
        "7",
        "--isaac-python",
        str(tmp_path / "python"),
        "--workdir",
        str(tmp_path / "work"),
        "--output",
        str(output),
    ]
    if record:
        argv += ["--record-dir", str(frames.parent)]
    assert evaluate.main(argv, runner=runner) == 0
    metadata = json.loads(output.with_name("run_metadata.json").read_text())
    assert metadata["retries"] == 1
    assert metadata.get("record_dir") == (str(frames.parent.resolve()) if record else None)


def test_worker_help_record() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "piperobot.adapters.isaaclab.episode",
            "--record",
            "frames",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--record" in result.stdout


@pytest.mark.parametrize(("horizon", "success_at"), [(600, None), (37, None), (37, 4)])
@pytest.mark.parametrize("record", [False, True])
def test_capture_order_and_indices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    horizon: int,
    success_at: int | None,
    record: bool,
) -> None:
    env = runtime_class()()
    trace = []
    env.full_reset = False
    env.seed = 1
    env.names = ["wrist_flex"]
    env.table = {}
    env.substeps = 2
    env.action_space = "joint"
    env.uses_object_state = False
    env.robot = SimpleNamespace(
        joint_names=env.names,
        data=SimpleNamespace(joint_pos=Array(0.0), joint_pos_limits=Array([-1.66, 1.66])),
    )
    env.rack = SimpleNamespace(
        data=SimpleNamespace(root_pos_w=Array([0, 0, 0]), root_quat_w=Array([0, 0, 0, 1]))
    )
    env.reset_layout = lambda **kw: None
    env.set_joints = lambda values: None
    env.tracker = SimpleNamespace(reset=lambda: None, failure_reason=lambda: "not_placed")
    env.sensor = SimpleNamespace(reset=lambda: None)
    env.apply_policy_action = lambda action: None
    env.physics_step = lambda: trace.append("physics")
    env.sim = SimpleNamespace(render=lambda: trace.append("render"))
    env.record = {"every_n_steps": 2, "jpeg_quality": 90}

    class RGB(Array):
        def numpy(self) -> str:
            return "rgb"

    env.camera = SimpleNamespace(
        update=lambda *a, **kw: trace.append("camera"),
        data=SimpleNamespace(output={"rgb": RGB(None)}),
    )
    writes = []
    fake_cv2 = SimpleNamespace(
        COLOR_RGB2BGR=1,
        IMWRITE_JPEG_QUALITY=2,
        cvtColor=lambda rgb, mode: "bgr",
        imwrite=lambda path, bgr, params: writes.append((Path(path).name, bgr, params)) or True,
    )
    original = builtins.__import__

    def importing(name: str, *args: object, **kwargs: object) -> object:
        if name == "cv2":
            assert record
            return fake_cv2
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)

    def sample(index: int) -> SimpleNamespace:
        trace.append(index)
        env.dump_steps.append({"step_index": index})
        return SimpleNamespace(success=index == success_at, success_step=success_at)

    env.sample = sample
    result = env.run_policy_episode(
        lambda: None, lambda *a: [0], horizon, False, record_dir=tmp_path if record else None
    )
    steps_run = horizon if success_at is None else success_at + 1
    expected = []
    for index in range(steps_run):
        expected += ["physics", "physics", index]
        if record and index % 2 == 1:
            expected += ["render", "camera"]
    assert trace == expected
    assert result.get("frames") == (steps_run // 2 if record else None)
    expected_writes = (
        [(f"frame_{n:04d}.jpg", "bgr", [2, 90]) for n in range(steps_run // 2)] if record else []
    )
    assert writes == expected_writes


def test_scene_camera_is_optional(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Cfg(SimpleNamespace):
        def __init__(self, **kw: object) -> None:
            super().__init__(**kw)

    Cfg.InitialStateCfg = Cfg
    stage = SimpleNamespace(
        GetLoadRules=lambda: SimpleNamespace(AddRule=lambda *a: None),
        SetLoadRules=lambda rules: None,
    )
    sim = SimpleNamespace(
        UsdFileCfg=Cfg,
        MassPropertiesCfg=Cfg,
        PinholeCameraCfg=Cfg,
        SimulationContext=SimpleNamespace(instance=lambda: SimpleNamespace(stage=stage)),
    )
    robot = Cfg(spawn=Cfg(), init_state=Cfg())
    modules = {
        "isaaclab.sim": sim,
        "isaaclab.actuators": Cfg(ImplicitActuatorCfg=Cfg),
        "isaaclab.assets": Cfg(AssetBaseCfg=Cfg, RigidObjectCfg=Cfg),
        "isaaclab.scene": Cfg(InteractiveSceneCfg=Cfg),
        "isaaclab.utils": Cfg(clone=lambda obj: robot),
        "isaaclab_assets.robots.so101": Cfg(SO101_CFG=robot),
        "isaaclab_physx.sim.schemas": Cfg(PhysxArticulationCfg=Cfg, PhysxRigidBodyCfg=Cfg),
        "pxr": Cfg(Sdf=Cfg(Path=lambda path: path), Usd=Cfg(StageLoadRules=Cfg(NoneRule=0))),
    }
    original = builtins.__import__
    camera_imports = []

    def importing(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "isaaclab.sim" and not fromlist:
            return Cfg(sim=sim)
        if name == "isaaclab.sensors":
            if "CameraCfg" in fromlist:
                camera_imports.append(name)
            return Cfg(ContactSensorCfg=Cfg, CameraCfg=Cfg)
        if name in modules:
            return modules[name]
        return original(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", importing)
    module = load_module("video_scene_test", ROOT / "robots/so101/envs/vials_to_rack_scene.py")
    cfg = module.build_scene_cfg(tmp_path, camera=None)
    assert not hasattr(cfg, "video_camera")
    assert camera_imports == []
    camera = json.loads((ROOT / "robots/so101/envs/video_camera.json").read_text())
    cfg = module.build_scene_cfg(tmp_path, camera=camera)
    assert camera_imports
    assert cfg.video_camera.prim_path == "{ENV_REGEX_NS}/VideoCamera"
    assert cfg.video_camera.update_period == 0
    assert cfg.video_camera.data_types == ["rgb"]
    assert cfg.video_camera.width == 640


def test_recording_rejects_demo_before_runtime_import(tmp_path: Path) -> None:
    task = load_module("video_task_test", ROOT / "robots/so101/envs/vials_to_rack_task.py")
    with pytest.raises(ValueError, match="recording supports the randomized layout only"):
        task.run_episode(0, object(), "reconstructed_demo", {}, object(), record_dir=tmp_path)


@pytest.mark.parametrize("record", [False, True])
def test_worker_record_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record: bool
) -> None:
    from contextlib import contextmanager

    from piperobot.adapters.isaaclab import episode

    frames = tmp_path / "frames"
    output = tmp_path / "worker.json"
    seen = []

    def launcher_args(parser: ArgumentParser) -> None:
        parser.add_argument("--device", default="cpu")
        parser.add_argument("--viz", default="none")

    @contextmanager
    def launch(cfg: object, args: Namespace) -> Iterator[None]:
        assert getattr(args, "enable_cameras", False) is record
        yield

    def run(**kwargs: object) -> dict[str, object]:
        assert kwargs.get("record_dir") == (frames if record else None)
        assert ("record_dir" in kwargs) is record
        if record:
            assert frames.is_dir()
        seen.append(kwargs)
        return {"success": False, "scene": "randomized", **({"frames": 0} if record else {})}

    modules = {
        "isaaclab.app": SimpleNamespace(add_launcher_args=launcher_args, launch_simulation=launch),
        "isaaclab.sim": SimpleNamespace(SimulationCfg=SimpleNamespace),
        "isaaclab_physx.physics": SimpleNamespace(PhysxCfg=SimpleNamespace),
        "torch": SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: False), version=SimpleNamespace(cuda=None)
        ),
    }
    monkeypatch.setattr(episode, "import_module", modules.__getitem__)
    monkeypatch.setattr(episode, "version", lambda name: None)
    monkeypatch.setattr(
        episode,
        "load_module",
        lambda name, path: (
            SimpleNamespace(run_episode=run)
            if name == "evaluation_task"
            else SimpleNamespace(make=lambda: SimpleNamespace(reset=lambda seed: None))
        ),
    )

    def fast_exit(code: int) -> Never:
        raise SystemExit(code)

    monkeypatch.setattr(episode, "_exit", fast_exit)
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"name": "task", "module": "task.py", "layout": "randomized"}))
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"name": "policy", "module": "policy.py", "factory": "make"}))
    argv = ["--task", str(task), "--policy", str(policy), "--seed", "7", "--out", str(output)]
    if record:
        argv += ["--record", str(frames)]
    with pytest.raises(SystemExit) as exc:
        episode.main(argv)
    assert exc.value.code == 0
    assert len(seen) == 1
    result = json.loads(output.read_text())
    assert ("frames" in result) is record
