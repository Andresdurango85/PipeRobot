import math

import pytest
from so101_loader import load

S = load("vials_success", "robots/so101/envs/vials_to_rack_success.py")
IDENTITY = (0.0, 0.0, 0.0, 1.0)
SLOT = (0.05, 0.05, 0.05)
OUT = (0.3, 0.3, 0.2)


def sample(
    tracker: object,
    index: int,
    force: float = 0.0,
    position: tuple[float, float, float] = SLOT,
    quat: tuple[float, float, float, float] = IDENTITY,
) -> object:
    return tracker.step(index, [S.VialState(force, position, quat)], (0.0, 0.0, 0.0), IDENTITY)


def warmed() -> object:
    tracker = S.SuccessTracker()
    for i in range(30):
        sample(tracker, i)
    return tracker


def test_clean_sequence_and_latched_success() -> None:
    tracker = warmed()
    assert sample(tracker, 30, 6.0).vials[0].grasped_now
    for i in range(31, 55):
        result = sample(tracker, i)
        assert result.vials[0].placed
        assert not result.success
        assert result.confirmation_count == i - 30
    result = sample(tracker, 55)
    assert result.success
    assert result.success_step == 55
    assert tracker.failure_reason() is None
    assert sample(tracker, 56, position=OUT).success
    assert tracker.success_step == 55


def test_preplaced_and_threshold_are_not_grasps() -> None:
    tracker = S.SuccessTracker()
    for i in range(100):
        result = sample(tracker, i, 5.0)
        assert not result.vials[0].grasped_now
        assert not result.vials[0].placed
        assert not result.success
    assert tracker.failure_reason() == "no_grasp"


def test_sideways_and_held_vials() -> None:
    tracker = warmed()
    sample(tracker, 30, 6.0)
    result = sample(tracker, 31, quat=(0.0, math.sqrt(0.5), 0.0, math.sqrt(0.5)))
    assert not result.vials[0].vertical
    assert not result.vials[0].placed
    assert tracker.failure_reason() == "not_placed"
    assert not sample(tracker, 32, 6.0).vials[0].placed
    assert sample(tracker, 33).vials[0].placed
    assert tracker.failure_reason() == "placement_not_held"


def test_warmup_placement_does_not_count() -> None:
    tracker = S.SuccessTracker()
    sample(tracker, 0, 6.0)
    for i in range(1, 30):
        assert not sample(tracker, i).vials[0].placed
    assert not sample(tracker, 30).vials[0].placed
    assert tracker.failure_reason() == "no_grasp"


@pytest.mark.parametrize("regrasp", [False, True])
def test_confirmation_resets_and_recovers(regrasp: bool) -> None:
    tracker = warmed()
    sample(tracker, 30, 6.0)
    for i in range(31, 40):
        sample(tracker, i)
    interrupted = sample(tracker, 40, 6.0 if regrasp else 0.0, OUT)
    assert interrupted.confirmation_count == 0
    assert interrupted.vials[0].placed
    for i in range(41, 65):
        assert not sample(tracker, i).success
    result = sample(tracker, 65)
    assert result.success
    assert result.success_step == 65
    assert result.confirmation_count == 25


def test_second_vial_and_instance_isolation() -> None:
    tracker = S.SuccessTracker(S.SuccessParams(warmup_steps=0))
    other = S.SuccessTracker(S.SuccessParams(warmup_steps=0))
    for i in range(26):
        result = tracker.step(
            i,
            [S.VialState(0.0, OUT, IDENTITY), S.VialState(6.0 if i == 0 else 0.0, SLOT, IDENTITY)],
            (0.0, 0.0, 0.0),
            IDENTITY,
        )
    assert result.success
    assert not result.vials[0].placed
    assert result.vials[1].placed
    assert not sample(other, 0).vials[0].placed


def test_rotated_rack_and_translation() -> None:
    q = (0.0, 0.0, math.sin(0.25), math.cos(0.25))
    local = (0.01, 0.11, 0.05)
    rotated = S.rotate_xyzw(q, local)
    origin = (1.0, 2.0, 3.0)
    world = tuple(a + b for a, b in zip(origin, rotated, strict=True))
    tracker = S.SuccessTracker()
    vial = S.VialState(0.0, world, IDENTITY)
    result = tracker.step(0, [vial], origin, q)
    assert result.vials[0].in_box
    assert result.vials[0].rack_local_position == pytest.approx(local)
    result = tracker.step(1, [vial], origin, IDENTITY)
    assert not result.vials[0].in_box


def test_history_advances_once_and_reset() -> None:
    tracker = S.SuccessTracker(S.SuccessParams(warmup_steps=0))
    sample(tracker, 0, 6.0, OUT)
    for i in range(1, 20):
        assert sample(tracker, i, position=OUT).vials[0].recently_grasped
    assert not sample(tracker, 20, position=OUT).vials[0].recently_grasped
    with pytest.raises(ValueError, match="Expected step index 21"):
        sample(tracker, 20)
    tracker.reset()
    assert tracker.failure_reason() == "no_grasp"
    result = sample(tracker, 0)
    assert not result.vials[0].placed
    assert not result.vials[0].recently_grasped
    assert result.confirmation_count == 0
    assert result.success_step is None


def test_reset_clears_success() -> None:
    tracker = S.SuccessTracker(S.SuccessParams(warmup_steps=0, confirm_steps=1))
    sample(tracker, 0, 6.0)
    assert sample(tracker, 1).success
    tracker.reset()
    assert not sample(tracker, 0).success
    assert tracker.success_step is None


@pytest.mark.parametrize(
    ("position", "inside"),
    [((0.0, 0.12, 0.05), True), ((0.12, 0.0, -0.01), True), ((0.1, 0.1, 0.1), False)],
)
def test_box_boundaries(position: tuple[float, float, float], inside: bool) -> None:
    assert sample(S.SuccessTracker(), 0, position=position).vials[0].in_box is inside


@pytest.mark.parametrize(("force", "grasped"), [(4.9, False), (5.0, False), (5.1, True)])
def test_measured_grasp_threshold(force: float, grasped: bool) -> None:
    assert sample(S.SuccessTracker(), 0, force).vials[0].grasped_now is grasped


@pytest.mark.parametrize(
    ("height", "quat", "bottom", "inside"),
    [
        (0.073 + 0.017, IDENTITY, 0.073, False),
        (0.073 + 0.0995, (1.0, 0.0, 0.0, 0.0), 0.073, False),
        (0.0158, IDENTITY, 0.0158 - 0.017, True),
        (0.08, IDENTITY, 0.063, False),
    ],
)
def test_slot_depth(
    height: float,
    quat: tuple[float, float, float, float],
    bottom: float,
    inside: bool,
) -> None:
    tracker = S.SuccessTracker(S.SuccessParams(warmup_steps=0))
    sample(tracker, 0, 6.0, (0.06, 0.06, height), quat)
    vial = sample(tracker, 1, position=(0.06, 0.06, height), quat=quat).vials[0]
    assert vial.vertical
    assert vial.bottom_local_z == pytest.approx(bottom)
    assert vial.in_box is inside
    assert vial.placed is inside


def test_depth_uses_tube_axis_in_rack_frame() -> None:
    q = (0.0, math.sin(0.3), 0.0, math.cos(0.3))
    local = (0.06, 0.06, 0.069)
    position = S.rotate_xyzw(q, local)
    tracker = S.SuccessTracker()
    vial = S.VialState(0.0, position, q)
    result = tracker.step(0, [vial], (0.0, 0.0, 0.0), q).vials[0]
    assert result.bottom_local_z == pytest.approx(0.052)
    assert result.in_box


def test_depth_margin_is_configurable_and_strict() -> None:
    params = S.SuccessParams(tube_axis_span_m=(-0.02, 0.1), rack_rim_z=0.08, rim_margin_m=0.01)
    height = params.rack_rim_z - params.rim_margin_m - params.tube_axis_span_m[0]
    tracker = S.SuccessTracker(params)
    vial = sample(tracker, 0, position=(0.06, 0.06, height)).vials[0]
    assert vial.bottom_local_z == pytest.approx(0.07)
    assert not vial.in_box


@pytest.mark.parametrize("face", range(6))
@pytest.mark.parametrize("offset", [-1e-7, 0.0, 1e-7])
def test_box_faces(face: int, offset: float) -> None:
    # Isolate each face, including strict z with the rim moved out of the way.
    params = S.SuccessParams(rack_rim_z=1.0) if face == 4 else S.SuccessParams()
    position = [0.06, 0.06, 0.03]
    if face < 4:
        position[face // 2] = -offset if face % 2 == 0 else 0.12 + offset
    else:
        position[2] = (
            0.1 if face == 4 else params.rack_rim_z - params.rim_margin_m + 0.017
        ) + offset
    result = (
        S.SuccessTracker(params)
        .step(0, [S.VialState(0.0, tuple(position), IDENTITY)], (0, 0, 0), IDENTITY)
        .vials[0]
    )
    assert result.box_signed_distance == pytest.approx(offset, abs=1e-15)
    assert result.in_box == (offset < 0 if face >= 4 else offset <= 0)


def test_box_random_yaw_and_tilt() -> None:
    import random

    rng = random.Random(44)
    p = S.SuccessParams()
    for _ in range(1000):
        yaw, tilt = rng.uniform(-math.pi, math.pi), rng.uniform(-math.pi, math.pi)
        rack_q = (0, 0, math.sin(yaw / 2), math.cos(yaw / 2))
        tube_q = (0, math.sin(tilt / 2), 0, math.cos(tilt / 2))
        local = tuple(rng.uniform(-0.05, 0.17) for _ in range(3))
        world = S.rotate_xyzw(rack_q, local)
        v = S.SuccessTracker(p).step(0, [S.VialState(0, world, tube_q)], (0, 0, 0), rack_q).vials[0]
        x, y, z = v.rack_local_position
        expected = (
            0 <= x <= 0.12
            and 0 <= y <= 0.12
            and z < 0.1
            and v.bottom_local_z < p.rack_rim_z - p.rim_margin_m
        )
        assert v.in_box == expected
        assert v.in_box == (v.box_signed_distance <= 0)


def test_upright_on_rack_rim_binds() -> None:
    v = sample(S.SuccessTracker(), 0, position=(0.06, 0.06, 0.09)).vials[0]
    assert not v.in_box
    assert v.box_signed_distance == pytest.approx(0.02)


def test_state_digest_canonicalization() -> None:
    import hashlib

    digest = load("state_digest_tests", "robots/so101/envs/state_digest.py").state_digest
    assert digest([-0.0]) == digest([0.0]) == digest([1e-7]) == digest([-1e-7])
    assert digest([1.0, 2.0]) != digest([2.0, 1.0])
    assert digest([1.1234567, -0.0]) == hashlib.sha256(b"1.123457,0.000000").hexdigest()


@pytest.mark.parametrize("face", range(6))
def test_rotated_tilted_face_grid(face: int) -> None:
    import random

    rng = random.Random(44 + face)
    p = S.SuccessParams(rack_rim_z=1.0) if face == 4 else S.SuccessParams()
    for _ in range(30):
        yaw, tilt = rng.uniform(-math.pi, math.pi), rng.uniform(-math.pi, math.pi)
        if face == 5:
            # Keep the bottom face below the origin-z ceiling while isolating it.
            tilt = rng.uniform(-math.pi / 2, math.pi / 2)
        rack_q = (0, 0, math.sin(yaw / 2), math.cos(yaw / 2))
        tube_q = (0, math.sin(tilt / 2), 0, math.cos(tilt / 2))
        axis_z = S.rotate_xyzw(tube_q, (0, 0, 1))[2]
        for offset in (-1e-6, 1e-6):
            local = [0.06, 0.06, 0.0]
            if face < 4:
                local[face // 2] = -offset if face % 2 == 0 else 0.12 + offset
            elif face == 4:
                local[2] = p.rack_local_z_max + offset
            else:
                local[2] = (
                    p.rack_rim_z
                    - p.rim_margin_m
                    - min(end * axis_z for end in p.tube_axis_span_m)
                    + offset
                )
            world = S.rotate_xyzw(rack_q, tuple(local))
            vial = (
                S.SuccessTracker(p)
                .step(0, [S.VialState(0, world, tube_q)], (0, 0, 0), rack_q)
                .vials[0]
            )
            assert vial.box_signed_distance == pytest.approx(offset, abs=1e-14)
            assert vial.in_box == (offset < 0)
