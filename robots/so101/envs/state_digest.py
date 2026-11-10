"""Canonical state hashing for the randomized evaluator.

Vector order: tubes 1, 2, 3 world root position (3) and XYZW quaternion (4),
then rack world root position (3) and XYZW quaternion (4), then six robot joint
positions in robot.joint_names order: 34 floats. Derived slots and TCP are excluded.
"""

import hashlib
from collections.abc import Iterable


def state_digest(values: Iterable[float]) -> str:
    """Hash comma-separated six-decimal ASCII values, normalizing rounded zero."""
    rounded = (round(value, 6) for value in values)
    canonical = ",".join(f"{value if value != 0 else 0.0:.6f}" for value in rounded)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()
