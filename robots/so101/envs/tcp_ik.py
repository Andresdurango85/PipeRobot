"""Pure TCP action geometry; no simulator or tensor dependency."""

import math
from collections.abc import Sequence


def skew(vector: Sequence[float]) -> list[list[float]]:
    x, y, z = vector
    return [[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]]


def shift_jacobian(
    jacobian: Sequence[Sequence[float]], offset: Sequence[float]
) -> list[list[float]]:
    cross = skew(offset)
    return [
        [
            jacobian[i][j] - sum(cross[i][k] * jacobian[k + 3][j] for k in range(3))
            for j in range(len(jacobian[0]))
        ]
        for i in range(3)
    ]


def clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def split_action(action: Sequence[float]) -> tuple[list[float], float, float, float]:
    if len(action) != 6 or not all(math.isfinite(v) for v in action):
        raise ValueError("TCP action must contain six finite values")
    if not 0 <= action[5] <= 100:
        raise ValueError("TCP gripper must be in 0..100")
    return list(action[:3]), action[3], action[4], action[5]
