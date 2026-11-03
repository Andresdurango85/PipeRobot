"""Offline cache preparation and weak-grip prerequisites."""

import hashlib
import json
from pathlib import Path

import pytest
from so101_loader import load

from piperobot.adapters.isaaclab import specs
from piperobot.cache import cache_root

P = load("prepare_test", "robots/so101/tools/prepare_caches.py")
D = load("extract_test", "robots/so101/tools/demo_extract.py")
R = load("replay_test", "robots/so101/policies/demo_replay.py")
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("env", "system", "suffix"),
    [
        ({}, "nt", "AppData/Local/piperobot"),
        ({}, "posix", ".cache/piperobot"),
        ({"PIPEROBOT_CACHE": ""}, "posix", ".cache/piperobot"),
        ({"XDG_CACHE_HOME": "~/xdg"}, "posix", "xdg/piperobot"),
    ],
)
def test_roots(env: dict[str, str], system: str, suffix: str, tmp_path: Path) -> None:
    if "XDG_CACHE_HOME" in env:
        env["XDG_CACHE_HOME"] = str(tmp_path / "xdg")
    assert cache_root(env, system, tmp_path) == (tmp_path / suffix).resolve()
    assert (
        cache_root({"PIPEROBOT_CACHE": "~/custom"}, system, tmp_path)
        == (tmp_path / "custom").resolve()
    )
    assert cache_root({"LOCALAPPDATA": str(tmp_path)}, "nt") == tmp_path / "piperobot"


def test_expansion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PIPEROBOT_CACHE", raising=False)
    assert specs.expand_variables("${PIPEROBOT_CACHE}/x") == str(cache_root()) + "/x"
    monkeypatch.setenv("PIPEROBOT_CACHE", str(tmp_path))
    assert specs.resolve_path("${PIPEROBOT_CACHE}/x", ROOT) == tmp_path / "x"
    fetcher = load("fetch_default_test", "robots/so101/tools/fetch_course_assets.py")
    assert fetcher.default_cache_dir("abc") == tmp_path / "course-assets/abc"


def test_serialization_and_floor(tmp_path: Path) -> None:
    data = {
        "joint_names": ["arm", "gripper.pos"],
        "episodes": [{"index": 0, "action": [[1, 12], [2, 41]], "state": [[1, 18]]}],
    }
    payload = D.serialize(data)
    assert payload.endswith(b"\n")
    assert not payload.endswith(b"\n\n")
    assert b"\r" not in payload
    path = tmp_path / "episodes.json"
    path.write_bytes(payload)
    for floor in [None, 25.0]:
        policy = R.DemoReplayPolicy(path, floor)
        policy.reset(0)
        assert policy.act({"step": 0}) == [1, 12 if floor is None else 25]
        assert policy.act({"step": 1}) == [2, 41]
        assert policy.reference_episode(0) == data["episodes"][0]


@pytest.fixture
def configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, bytes]:
    robot = tmp_path / "robot"
    (robot / "envs").mkdir(parents=True)
    (robot / "policies").mkdir()
    payload = D.serialize({"episodes": []})
    sha = hashlib.sha256(payload).hexdigest()
    (robot / "envs/course_assets.json").write_text(
        json.dumps(
            {
                "source": {"commit": "abc", "url_template": "https://example.test/{name}"},
                "assets": [
                    {"name": "scene.usd", "size": len(payload), "sha256": sha, "use": "scene"}
                ],
            }
        )
    )
    (robot / "envs/demo_datasets.json").write_text(
        json.dumps({"datasets": [{"repo_id": "a/b", "revision": "rev"}]})
    )
    (robot / "policies/demo_replay.json").write_text(
        json.dumps(
            {
                "files": [
                    {"path": "${PIPEROBOT_CACHE}/datasets/a--b/rev/episodes.json", "sha256": sha}
                ]
            }
        )
    )
    monkeypatch.setattr(P, "ROBOT", robot)
    original = specs.load_module

    def loader(name: str, path: Path) -> object:
        module = original(name, path)
        if name == "_prepare_assets":
            checkout = tmp_path / "checkout"
            checkout.mkdir(exist_ok=True)
            (checkout / "pyproject.toml").touch()
            module.__file__ = str(checkout / "robots/so101/tools/fetch.py")
        return module

    monkeypatch.setattr(specs, "load_module", loader)
    return tmp_path / "cache", payload


@pytest.mark.parametrize("only", [None, "assets", "episodes"])
def test_prepare_idempotent(configuration: tuple[Path, bytes], only: str | None) -> None:
    root, payload = configuration
    args = ["--cache-root", str(root)] + (["--only", only] if only else [])
    assert P.main(args, fetch=lambda _: payload, extract=lambda *_: {"episodes": []}) == 0

    def forbidden(*args: object) -> bytes:
        pytest.fail("Network called with a full cache")

    assert P.main(args, fetch=forbidden, extract=forbidden) == 0
    assert (root / "course-assets/abc/scene.usd").exists() == (only != "episodes")
    assert (root / "datasets/a--b/rev/episodes.json").exists() == (only != "assets")


def test_prepare_mismatch(configuration: tuple[Path, bytes]) -> None:
    root, _ = configuration
    assert (
        P.main(
            ["--cache-root", str(root)], fetch=lambda _: b"bad", extract=lambda *_: {"bad": True}
        )
        == 1
    )
    assert not list(root.rglob("*.part"))
    assert not list(root.rglob("episodes.json"))
    assert not list(root.rglob("scene.usd"))


def test_refuse_repo() -> None:
    with pytest.raises(SystemExit, match="2"):
        P.main(["--cache-root", str(ROOT)])


def test_policy_specs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPEROBOT_CACHE", str(tmp_path))
    payload = b"fake cache\n"
    for name in ["demo_replay", "demo_replay_weak_grip"]:
        data = json.loads((ROOT / f"robots/so101/policies/{name}.json").read_text())
        target = Path(specs.expand_variables(data["files"][0]["path"]))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        # Both specs pin the same extracted file.
        assert data["files"][0]["sha256"] == (
            "273e182343a8d2a477a7cf9d562162a632e4197cc0a6bde41ae5f2c5823c2d52"
        )
        data["files"][0]["sha256"] = hashlib.sha256(payload).hexdigest()
        spec = tmp_path / f"{name}.json"
        spec.write_text(json.dumps(data))
        assert Path(specs.PolicySpec.load(spec).options["episodes_json"]) == target
    expectation_path = ROOT / "robots/so101/policies/weak_grip_expectation.json"
    expectation = json.loads(expectation_path.read_text())
    assert set(expectation) == {
        "registered",
        "spec",
        "seeds",
        "config",
        "reference",
        "expectation",
        "failure_of_expectation",
    }
