import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from so101_loader import load

F = load("fetch_course_assets", "robots/so101/tools/fetch_course_assets.py")
DATA = b"verified asset"


@pytest.fixture(autouse=True)
def simulated_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The required --basetemp is inside the real checkout. Model an independent
    # checkout so tmp_path is external without weakening production validation.
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "pyproject.toml").write_text("")
    monkeypatch.setattr(F, "__file__", str(root / "robots" / "so101" / "tools" / "fetch.py"))


def manifest() -> dict[str, Any]:
    return {
        "source": {"commit": "abc", "url_template": "https://example.test/{commit}/{name}"},
        "assets": [
            {
                "name": name,
                "size": len(DATA),
                "sha256": hashlib.sha256(DATA).hexdigest(),
                "use": use,
            }
            for name, use in [("scene.usd", "scene"), ("robot.usd", "reference")]
        ],
    }


def test_fetch_cache_replace_and_reference(tmp_path: Path) -> None:
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return DATA

    assert F.fetch_assets(manifest(), tmp_path, fetch=fetch) == {"scene.usd": "downloaded"}
    assert (tmp_path / "scene.usd").read_bytes() == DATA
    assert not (tmp_path / "robot.usd").exists()
    assert F.fetch_assets(manifest(), tmp_path, fetch=fetch) == {"scene.usd": "cached"}
    assert len(calls) == 1
    (tmp_path / "scene.usd").write_bytes(b"tampered")
    F.fetch_assets(manifest(), tmp_path, include_reference=True, fetch=fetch)
    assert len(calls) == 3
    assert (tmp_path / "scene.usd").read_bytes() == DATA
    assert (tmp_path / "robot.usd").read_bytes() == DATA
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("payload", [b"X" * len(DATA), b"short"])
def test_bad_download_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], payload: bytes
) -> None:
    config = tmp_path / "manifest.json"
    config.write_text(json.dumps(manifest()))
    cache = tmp_path / "cache"
    args = ["--manifest", str(config), "--cache-dir", str(cache)]
    assert F.main(args, fetch=lambda _: payload) == 1
    error = capsys.readouterr().err
    assert "scene.usd" in error
    assert hashlib.sha256(DATA).hexdigest() in error
    assert hashlib.sha256(payload).hexdigest() in error
    assert not (cache / "scene.usd.part").exists()
    assert not (cache / "scene.usd").exists()


def test_wrong_size_even_with_matching_hash(tmp_path: Path) -> None:
    config = manifest()
    config["assets"][0]["size"] += 1
    with pytest.raises(ValueError, match="expected size"):
        F.fetch_assets(config, tmp_path, fetch=lambda _: DATA)
    assert not list(tmp_path.glob("*.part"))


def test_check_missing_good_and_tampered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "manifest.json"
    config.write_text(json.dumps(manifest()))
    cache = tmp_path / "cache"
    args = ["--manifest", str(config), "--cache-dir", str(cache), "--check", "--json"]

    def forbidden_fetch(url: str) -> bytes:
        pytest.fail(f"Unexpected download: {url}")

    assert F.main(args, fetch=forbidden_fetch) == 1
    assert not cache.exists()
    F.fetch_assets(manifest(), cache, fetch=lambda _: DATA)
    assert F.main(args, fetch=forbidden_fetch) == 0
    output = capsys.readouterr().out
    assert f"cache: {cache}" in output
    assert '"scene.usd": "cached"' in output
    (cache / "scene.usd").write_bytes(b"bad")
    assert F.main(args, fetch=forbidden_fetch) == 1


def test_repo_cache_refused() -> None:
    root = Path(F.__file__).resolve().parents[3]
    for cache in [root, root / "assets", root / "robots" / "cache"]:
        with pytest.raises(ValueError, match="never stored in the repo"):
            F.fetch_assets(manifest(), cache, fetch=lambda _: DATA)


@pytest.mark.parametrize("template", ["http://example.test/{name}", "file:///tmp/{name}"])
def test_only_https(tmp_path: Path, template: str) -> None:
    config = manifest()
    config["source"]["url_template"] = template
    with pytest.raises(ValueError, match="Only HTTPS"):
        F.fetch_assets(config, tmp_path, fetch=lambda _: DATA)


def test_pinned_manifest() -> None:
    config = json.loads(F.MANIFEST.read_text())
    assert config["source"]["commit"] == "ce807d99724cb65671abec01f908a2fcb4a6eab7"
    assert len(config["assets"]) == 5
    assert sum(a["use"] == "reference" for a in config["assets"]) == 1


def test_https_redirect_rejects_downgrade() -> None:
    with pytest.raises(ValueError, match="Only HTTPS"):
        F.HTTPSRedirectHandler().redirect_request(None, None, 302, "Found", {}, "http://bad.test")


def test_default_cache_path() -> None:
    cache = F.default_cache_dir("pinned")
    assert cache.parts[-3:] == ("piperobot", "course-assets", "pinned")
