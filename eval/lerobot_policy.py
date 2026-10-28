"""Fetch a LeRobot policy from the Hub at a pinned revision and make it loadable by LeRobot 0.6.

Policies published before LeRobot 0.4 need two fixes (ADR 0016):

- config fields that 0.6 no longer knows (e.g. VQ-BeT's ``mlp_hidden_dim``) are dropped;
- their built-in normalization is converted to the 0.6 processor format with LeRobot's own
  `migrate_policy_normalization`, working around a bug in 0.6.1 where list values for
  tuple-typed fields (e.g. ``crop_shape``) crash the config serializer.

A spec can also override config values (``config_overrides``), e.g. an inference setting such
as VQ-BeT's ``bet_softmax_temperature``: a policy change that needs no retraining (ADR 0017).

The prepared policy is cached per revision and config changes, so repeated runs reuse it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import sys
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import mock

from eval.results import ResultsError

POLICY_FILES = ("config.json", "model.safetensors")


@dataclass(frozen=True)
class PolicySpec:
    name: str
    repo_id: str
    revision: str
    env: str
    drop_config_fields: tuple[str, ...] = field(default_factory=tuple)
    migrate_legacy_normalization: bool = False
    config_overrides: dict[str, Any] = field(default_factory=dict)

    @property
    def cache_name(self) -> str:
        """Directory name of the prepared policy: changes whenever the prepared files would."""
        changes = json.dumps(
            [self.drop_config_fields, self.config_overrides], sort_keys=True
        ).encode()
        return f"{self.name}-{self.revision[:12]}-{hashlib.sha256(changes).hexdigest()[:8]}"

    @classmethod
    def load(cls, path: Path) -> PolicySpec:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                name=str(data["name"]),
                repo_id=str(data["repo_id"]),
                revision=str(data["revision"]),
                env=str(data["env"]),
                drop_config_fields=tuple(data.get("drop_config_fields", ())),
                migrate_legacy_normalization=bool(data.get("migrate_legacy_normalization")),
                config_overrides=dict(data.get("config_overrides", {})),
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ResultsError(f"invalid policy spec {path}: {exc}") from exc


def _coerce_tuple_fields(config: Any) -> Any:  # noqa: ANN401 - any LeRobot policy config
    hints = typing.get_type_hints(type(config))
    for config_field in dataclasses.fields(config):
        value = getattr(config, config_field.name)
        if isinstance(value, list) and "tuple" in str(hints.get(config_field.name, "")):
            setattr(config, config_field.name, tuple(value))
    return config


def _migrate(source: Path, target: Path) -> None:
    import lerobot.policies  # noqa: F401 - registers policy config types
    import lerobot.processor.migrate_policy_normalization as migration

    make_config = migration.make_policy_config

    def make_config_with_tuples(policy_type: str, **kwargs: Any) -> Any:  # noqa: ANN401
        return _coerce_tuple_fields(make_config(policy_type, **kwargs))

    argv = ["migrate", "--pretrained-path", str(source), "--output-dir", str(target)]
    with (
        mock.patch.object(migration, "make_policy_config", make_config_with_tuples),
        mock.patch.object(sys, "argv", argv),
    ):
        migration.main()


def _download(spec: PolicySpec) -> Path:
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(spec.repo_id, revision=spec.revision, allow_patterns=list(POLICY_FILES))
    )


def prepare_policy(
    spec: PolicySpec, cache_dir: Path, download: Callable[[PolicySpec], Path] = _download
) -> Path:
    """Return a local directory with the policy ready for `lerobot-eval`."""
    prepared = cache_dir / spec.cache_name
    if (prepared / "model.safetensors").exists():
        return prepared

    downloaded = download(spec)
    staging = cache_dir / f"{prepared.name}-staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    config = json.loads((downloaded / "config.json").read_text(encoding="utf-8"))
    for name in spec.drop_config_fields:
        config.pop(name, None)
    unknown = sorted(set(spec.config_overrides) - config.keys())
    if unknown:
        raise ResultsError(f"config_overrides for fields the policy does not have: {unknown}")
    config.update(spec.config_overrides)
    (staging / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    shutil.copy2(downloaded / "model.safetensors", staging / "model.safetensors")

    if spec.migrate_legacy_normalization:
        _migrate(staging, prepared)
        shutil.rmtree(staging)
    else:
        staging.rename(prepared)
    return prepared
