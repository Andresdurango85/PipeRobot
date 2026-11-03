"""Independent seeded layouts in meters and radians, without simulation imports."""

from __future__ import annotations

import random
from collections.abc import Mapping
from typing import NamedTuple, cast


class Layout(NamedTuple):
    tubes: tuple[tuple[float, float, float], ...]
    rack_position: tuple[float, float, float]
    rack_yaw: float


def sample_layout(seed: int, data: Mapping[str, object]) -> Layout:
    rng = random.Random(seed)  # noqa: S311 - reproducible scene sampling, not security
    tubes = cast(dict[str, list[list[float]] | list[float]], data["tubes"])
    rack = cast(dict[str, list[float]], data["rack"])
    origins = cast(list[list[float]], tubes["origins_m"])
    tx = cast(list[float], tubes["x_range_m"])
    ty = cast(list[float], tubes["y_range_m"])
    positions = tuple(
        (origin[0] + rng.uniform(*tx), origin[1] + rng.uniform(*ty), origin[2])
        for origin in origins
    )
    origin = rack["origin_m"]
    position = (
        origin[0] + rng.uniform(*rack["x_range_m"]),
        origin[1] + rng.uniform(*rack["y_range_m"]),
        origin[2],
    )
    return Layout(positions, position, rng.uniform(*rack["yaw_range_rad"]))
