import math

import pytest
from so101_loader import load

U = load("joint_units", "robots/so101/envs/joint_units.py")
TABLE = U.load_table()


@pytest.mark.parametrize(
    ("name", "raw", "degrees"),
    [
        ("shoulder_pan", 100, 110),
        ("shoulder_pan", -100, -110),
        ("elbow_flex", 0, -5),
        ("gripper", 0, -10),
        ("gripper", 100, 100),
    ],
)
def test_endpoints(name: str, raw: float, degrees: float) -> None:
    values = dict.fromkeys(TABLE, 0.0)
    values[name] = raw
    assert math.degrees(U.to_radians(values, TABLE)[name]) == pytest.approx(degrees)


def test_round_trip_order_and_features() -> None:
    values = {n: i * 8.7 for i, n in enumerate(TABLE)}
    features = {n + ".pos": v for n, v in reversed(list(values.items()))}
    assert U.to_lerobot(U.to_radians(features, TABLE), TABLE) == pytest.approx(values)
    values["shoulder_pan"] = 200
    assert math.degrees(U.to_radians(values, TABLE)["shoulder_pan"]) == pytest.approx(220)


@pytest.mark.parametrize("values", [{}, {"unknown": 0}])
def test_bad_names(values: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="joints"):
        U.to_radians(values, TABLE)
    with pytest.raises(ValueError, match="joints"):
        U.to_lerobot(values, TABLE)


@pytest.mark.parametrize(
    "row",
    [
        [-44.0, -98.8, -34.8, -100.0, -71.7, 8.5],
        [35.0, 50.3, 100.0, 66.7, -34.9, 58.1],
        [-44.1, -99.2, -35.1, -99.8, -72.9, 0.5],
        [35.0, 49.9, 99.9, 67.1, -34.8, 58.7],
    ],
)
def test_dataset_extrema(row: list[float]) -> None:
    converted = U.to_radians(dict(zip(TABLE, row, strict=True)), TABLE)
    for name, value in converted.items():
        low, high = TABLE[name]["degrees"]
        assert low - 1e-10 <= math.degrees(value) <= high + 1e-10
