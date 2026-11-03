"""Open-loop course replay: seeds identify demos; actions use dataset joint order."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast


class DemoReplayPolicy:
    def __init__(self, episodes_json: str | Path) -> None:
        data = json.loads(Path(episodes_json).read_text(encoding="utf-8"))
        self.joint_names: list[str] = data["joint_names"]
        self.episodes: dict[int, dict[str, object]] = {
            episode["index"]: episode for episode in data["episodes"]
        }
        self.episode: Mapping[str, object] | None = None

    def reference_episode(self, seed: int) -> Mapping[str, object]:
        if type(seed) is not int or seed not in self.episodes or not 0 <= seed <= 74:
            raise ValueError(f"Demo index {seed} out of range (0..74, present in extracted file)")
        return self.episodes[seed]

    def reset(self, seed: int) -> None:
        self.episode = self.reference_episode(seed)

    def act(self, observation: Mapping[str, object]) -> Sequence[float]:
        if self.episode is None:
            raise ValueError("Call reset(seed) before act")
        step = observation.get("step")
        actions = cast(list[list[float]], self.episode["action"])
        if type(step) is not int or not 0 <= step < len(actions):
            raise ValueError("Observation step out of range")
        return actions[step].copy()
