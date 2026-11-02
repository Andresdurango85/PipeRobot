"""Check headless Isaac rendering in the runner's Windows service session.

Runs in the Isaac Lab 3.0 environment of ADR 0021 (Isaac Lab ``release/3.0.0`` at commit
``44044b0963``), from a scratch directory, not a repo checkout (Isaac Lab writes logs relative to
the working directory). ``PY`` is that environment's python; the workflow
``.github/workflows/isaac-render.yml`` runs both modes inside the runner's service::

    cd <scratch-dir>
    PYTHONUNBUFFERED=1 $PY <repo>/robots/so101/tools/isaac_render_check.py \
        --mode empty --viz none --out-dir out
    PYTHONUNBUFFERED=1 $PY <repo>/robots/so101/tools/isaac_render_check.py \
        --mode camera --viz none --out-dir out

``OMNI_KIT_ACCEPT_EULA=YES`` records the owner's acceptance of the Omniverse EULA (ADR 0021) in
environments where Isaac Sim has not recorded it; never create ``EULA_ACCEPTED`` by hand.
Exit codes: 0 success, 1 no nonblack camera frame, 2 exception.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections.abc import Sequence
from pathlib import Path

PROCESS_START = time.perf_counter()


def run(args: argparse.Namespace, result: dict[str, object]) -> int:
    """Launch Kit, run the check, and record the result before Kit's shutdown ends the process."""
    from isaaclab.app import launch_simulation
    from isaaclab.sim import SimulationCfg

    args.enable_cameras = args.mode == "camera"
    sim_cfg = SimulationCfg(dt=0.01, device=args.device)
    with launch_simulation(sim_cfg, args):
        try:
            code = _check(args, result, sim_cfg)
        except Exception:
            traceback.print_exc()
            code = 2
        _finish(args, result, code)
        if code:
            # Leaving the block closes Kit, which ends the process with this exit status.
            raise SystemExit(code)
    return 0


def _check(args: argparse.Namespace, result: dict[str, object], sim_cfg: object) -> int:
    """Step the simulation and, in camera mode, capture one RTX frame. Kit must be running."""
    from isaaclab.sim import SimulationContext

    sim = SimulationContext(sim_cfg)
    result["launch_seconds"] = time.perf_counter() - PROCESS_START
    setup_start = time.perf_counter()
    camera = None
    if args.enable_cameras:
        import isaaclab.sim as sim_utils
        import torch
        from isaaclab.sensors.camera import CameraCfg
        from isaaclab.utils import instantiate
        from isaaclab_physx.renderers import IsaacRtxRendererCfg

        ground = sim_utils.GroundPlaneCfg()
        ground.func("/World/Ground", ground)
        light = sim_utils.DistantLightCfg(intensity=3000.0, color=(0.75, 0.75, 0.75))
        light.func("/World/Light", light)
        sim_utils.create_prim("/World/Origin_00", "Xform")
        sim_utils.create_prim("/World/Objects", "Xform")
        cube = sim_utils.CuboidCfg(
            size=(0.3, 0.3, 0.3),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.8, 0.2, 0.2)),
        )
        cube.func("/World/Objects/Cube", cube, translation=(0.0, 0.0, 0.15))
        sphere = sim_utils.SphereCfg(
            radius=0.15,
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.2, 0.4, 0.8)),
        )
        sphere.func("/World/Objects/Sphere", sphere, translation=(0.5, 0.3, 0.15))
        camera = instantiate(
            CameraCfg(
                prim_path="/World/Origin_00/CameraSensor",
                update_period=0,
                height=480,
                width=640,
                data_types=["rgb"],
                renderer_cfg=IsaacRtxRendererCfg(),
                spawn=sim_utils.PinholeCameraCfg(
                    focal_length=24.0,
                    focus_distance=400.0,
                    horizontal_aperture=20.955,
                    clipping_range=(0.1, 1.0e5),
                ),
            )
        )
    sim.reset()
    if camera is not None:
        camera.set_world_poses_from_view(
            torch.tensor([[2.0, 2.0, 1.5]], device=sim.device),
            torch.tensor([[0.0, 0.0, 0.0]], device=sim.device),
        )
    result["scene_setup_seconds"] = time.perf_counter() - setup_start
    stepping_start = time.perf_counter()
    for step in range(args.max_steps if camera is not None else args.steps):
        sim.step()
        result["steps"] = step + 1
        if camera is None:
            continue
        import numpy as np
        from PIL import Image

        camera.update(dt=sim.get_physics_dt())
        rgb = camera.data.output.get("rgb")
        if rgb is None:
            continue
        batch = rgb.torch
        if batch.numel() == 0:
            continue
        frame = batch[0].cpu().numpy()
        if frame.shape != (480, 640, 3):
            continue
        frame = np.asarray(frame, dtype=np.uint8)
        mean, std = float(frame.mean()), float(frame.std())
        nonblack = std > 2 and mean > 5
        result.update(shape=list(frame.shape), mean=mean, std=std, nonblack=nonblack)
        Image.fromarray(frame).save(args.out_dir / "rgb.png")
        if nonblack:
            # Measured from process start, including launch and scene setup.
            result["first_valid_frame_seconds"] = time.perf_counter() - PROCESS_START
            break
    result["stepping_seconds"] = time.perf_counter() - stepping_start
    return 0 if camera is None or result["nonblack"] else 1


def _finish(args: argparse.Namespace, result: dict[str, object], code: int) -> None:
    result["total_seconds"] = time.perf_counter() - PROCESS_START
    result["exit_code"] = code
    (args.out_dir / f"{args.mode}.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    for key, value in result.items():
        print(f"{key}: {value}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("empty", "camera"), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--max-steps", type=int, default=60)
    argv = list(sys.argv[1:] if argv is None else argv)
    # Help must work without Isaac installed; normal runs use its full launcher parser.
    if "--help" in argv or "-h" in argv:
        parser.add_argument("--viz", help="Isaac launcher visualizer; use none for headless")
        parser.add_argument("--device", help="Isaac launcher device")
        parser.parse_args(argv)
        return 0
    result: dict[str, object] = {
        "launch_seconds": None,
        "scene_setup_seconds": None,
        "stepping_seconds": None,
    }
    args, _ = parser.parse_known_args(argv)
    try:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        result["mode"] = args.mode
        if args.mode == "camera":
            result.update(
                first_valid_frame_seconds=None, shape=None, mean=None, std=None, nonblack=False
            )
        from isaaclab.app import add_launcher_args

        add_launcher_args(parser)
        args = parser.parse_args(argv)
        if args.steps < 1 or args.max_steps < 1:
            parser.error("step counts must be positive")
        return run(args, result)
    except Exception:  # before Kit started, e.g. a failed import or launch
        traceback.print_exc()
        _finish(args, result, 2)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
