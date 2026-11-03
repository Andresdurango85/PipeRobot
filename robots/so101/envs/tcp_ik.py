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


def integrate(
    previous: Sequence[float],
    solved: Sequence[float],
    measured: Sequence[float],
    gain: float,
    max_lead: float,
) -> list[float]:
    """Move the joint target a fraction of the IK step, never further than max_lead from the arm.

    Integrating on the previous target compensates the sag of low-gain joints under gravity; the
    gain and the lead limit keep that integration from winding up while the arm lags.
    """
    if not 0 < gain <= 1 or max_lead <= 0:
        raise ValueError("gain must be in (0, 1] and max_lead positive")
    return [
        clamp(p + gain * (s - p), m - max_lead, m + max_lead)
        for p, s, m in zip(previous, solved, measured, strict=True)
    ]
