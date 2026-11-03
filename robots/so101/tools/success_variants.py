"""Replay exact tracker samples to attribute outcomes to force and depth rules (stdlib)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "variants_success", Path(__file__).resolve().parents[1] / "envs/vials_to_rack_success.py"
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Cannot load success tracker")
S = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(S)


def replay_dump(dump: dict) -> dict[str, object]:
    """Replay all samples independently for each variant, preserving dumped parameters."""
    params = S.SuccessParams(**dump["success_params"])
    variants = {}
    depth_samples = []
    for threshold in (2.0, 5.0):
        for depth in (True, False):
            tracker = S.SuccessTracker(
                replace(
                    params,
                    force_threshold_n=threshold,
                    rack_rim_z=params.rack_rim_z if depth else math.inf,
                )
            )
            for sample in dump["steps"]:
                states = [S.VialState(**vial) for vial in sample["vials"]]
                result = tracker.step(
                    sample["step_index"],
                    states,
                    sample["rack_position"],
                    sample["rack_quaternion_xyzw"],
                )
                if threshold == 5.0 and depth:
                    vial = result.vials[0]
                    x, y, z = vial.rack_local_position
                    if (
                        vial.vertical
                        and not vial.grasped_now
                        and params.rack_local_x_min <= x <= params.rack_local_x_max
                        and params.rack_local_y_min <= y <= params.rack_local_y_max
                        and z < 0.1
                    ):
                        axis = S.rotate_xyzw(states[0].quaternion_xyzw, (0.0, 0.0, 1.0))
                        depth_samples.append(
                            {
                                "step_index": sample["step_index"],
                                "bottom_local_z": vial.bottom_local_z,
                                "margin_above_bound_m": vial.bottom_local_z - (0.073 - 0.02),
                                "tilt_deg": math.degrees(math.acos(max(-1.0, min(1.0, axis[2])))),
                            }
                        )
            variants[f"force_{threshold:g}n_depth_{'on' if depth else 'off'}"] = {
                "success": tracker.success_step is not None,
                "success_step": tracker.success_step,
                "failure_reason": tracker.failure_reason(),
            }
    ordered = sorted(depth_samples, key=lambda sample: sample["bottom_local_z"])
    median = None
    if ordered:
        middle = len(ordered) // 2
        central = (
            ordered[middle : middle + 1] if len(ordered) % 2 else ordered[middle - 1 : middle + 1]
        )
        median = {
            key: statistics.mean(sample[key] for sample in central)
            for key in ("bottom_local_z", "margin_above_bound_m", "tilt_deg")
        }
    return {
        "episode_index": dump["episode_index"],
        "variants": variants,
        "depth": {
            "count": len(ordered),
            "minimum": ordered[0] if ordered else None,
            "median": median,
        },
    }


def write_outputs(out: Path, episodes: list[dict[str, object]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "success_variants.json").write_text(
        json.dumps({"episodes": episodes}, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    names = [f"force_{force}n_depth_{depth}" for force in (2, 5) for depth in ("on", "off")]
    lines = [
        "| Episode | "
        + " | ".join(names)
        + " | Min bottom / margin (m) / tilt (deg) | Median bottom / margin (m) / tilt (deg) |",
        "| " + " | ".join(["---"] * 7) + " |",
    ]
    for episode in episodes:
        cells = [str(episode["episode_index"])]
        for name in names:
            variant = episode["variants"][name]
            cells.append(
                str(variant["success_step"] if variant["success"] else variant["failure_reason"])
            )
        for name in ("minimum", "median"):
            sample = episode["depth"][name]
            cells.append(
                "n/a"
                if sample is None
                else " / ".join(
                    f"{sample[key]:.6f}"
                    for key in ("bottom_local_z", "margin_above_bound_m", "tilt_deg")
                )
            )
        lines.append("| " + " | ".join(cells) + " |")
    (out / "success_variants.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dumps", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    write_outputs(
        args.out, [replay_dump(json.loads(path.read_text(encoding="utf-8"))) for path in args.dumps]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
