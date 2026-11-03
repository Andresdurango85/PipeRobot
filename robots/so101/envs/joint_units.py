# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# Ported from isaac-sim/Sim-to-Real-SO-101-Workshop @
# ce807d99724cb65671abec01f908a2fcb4a6eab7,
# source/sim_to_real_so101/utils/lerobot_interface.py (SO101_USD_MAPPING and the radian
# conversions). Modified for PipeRobot: table moved to JSON, joints looked up by name.
"""The sole SO-101 unit conversion implementation; no clipping."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path

type JointTable = dict[str, dict[str, list[float]]]


def load_table(path: Path | None = None) -> JointTable:
    source = path or Path(__file__).with_suffix(".json")
    return json.loads(source.read_text(encoding="utf-8"))["joints"]


def _normalize(values: Mapping[str, float], table: JointTable) -> dict[str, float]:
    result = {key.removesuffix(".pos"): float(value) for key, value in values.items()}
    if set(result) != set(table) or len(result) != len(values):
        raise ValueError("Unknown, missing or duplicate joints")
    if not all(math.isfinite(v) for v in result.values()):
        raise ValueError("Joint values must be finite")
    return result


def to_radians(values: Mapping[str, float], table: JointTable) -> dict[str, float]:
    values = _normalize(values, table)
    return {
        n: math.radians(
            t["degrees"][0]
            + (values[n] - t["raw"][0])
            * (t["degrees"][1] - t["degrees"][0])
            / (t["raw"][1] - t["raw"][0])
        )
        for n, t in table.items()
    }


def to_lerobot(radians: Mapping[str, float], table: JointTable) -> dict[str, float]:
    values = _normalize(radians, table)
    return {
        n: t["raw"][0]
        + (math.degrees(values[n]) - t["degrees"][0])
        * (t["raw"][1] - t["raw"][0])
        / (t["degrees"][1] - t["degrees"][0])
        for n, t in table.items()
    }
