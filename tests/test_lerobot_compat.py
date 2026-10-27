"""Compatibility checks for dependency overrides on top of LeRobot (ADR 0012).

LeRobot 0.6.1 caps Pillow below 13; we override that cap for security. These tests exercise the
LeRobot code paths that touch Pillow. They are skipped where the `lerobot` extra is not installed
(the lint/test CI job); run them after any change to the overrides or the LeRobot pin.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

image_writer = pytest.importorskip("lerobot.datasets.image_writer")
PIL_Image = pytest.importorskip("PIL.Image")


def test_pillow_override_is_installed() -> None:
    import PIL

    assert int(PIL.__version__.split(".")[0]) >= 13


@pytest.mark.parametrize(
    "array",
    [
        np.random.default_rng(0).integers(0, 256, (48, 64, 3), dtype=np.uint8),  # HWC uint8
        np.random.default_rng(0).random((3, 48, 64), dtype=np.float32),  # CHW float in [0, 1]
    ],
    ids=["hwc-uint8", "chw-float"],
)
def test_lerobot_converts_arrays_to_pil(array: np.ndarray) -> None:
    image = image_writer.image_array_to_pil_image(array)

    assert image.size == (64, 48)
    assert image.mode == "RGB"


# The only formats LeRobot 0.6.1 writes, both lossless. Several Pillow 13 fixes are in TIFF code.
@pytest.mark.parametrize("suffix", [".png", ".tiff"])
def test_lerobot_writes_images_that_reload_identically(tmp_path: Path, suffix: str) -> None:
    array = np.random.default_rng(0).integers(0, 256, (48, 64, 3), dtype=np.uint8)
    path = tmp_path / f"frame{suffix}"

    image_writer.write_image(array, path)

    with PIL_Image.open(path) as reloaded:
        assert np.array_equal(np.asarray(reloaded), array)


def test_torchvision_transforms_accept_pillow_images() -> None:
    transforms = pytest.importorskip("torchvision.transforms.v2")
    image = PIL_Image.new("RGB", (64, 48), color=(255, 200, 0))

    tensor = transforms.Compose([transforms.PILToTensor()])(image)

    assert tuple(tensor.shape) == (3, 48, 64)
