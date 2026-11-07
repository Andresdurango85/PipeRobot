"""Annotated source releases fail closed before signing or publishing."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

BAD_SIGNATURES: list[Any] = [[], None, {}, "signature"]
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_preflight", ROOT / ".github/scripts/release_preflight.py"
)
assert SPEC is not None
assert SPEC.loader is not None
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def run_git(binary: str, root: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603 -- resolved git, explicit test arguments.
        [binary, "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "bad-name",
        "missing",
        "lightweight",
        "unreachable",
        "version",
        "missing-notes",
        "blank-notes",
    ],
)
def test_check_tag(
    tmp_path: Path, git_binary: str, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    def git(*args: str) -> str:
        return run_git(git_binary, tmp_path, *args)

    git("init", "-b", "main")
    git("config", "commit.gpgsign", "false")
    git("config", "tag.gpgsign", "false")
    git("config", "user.name", "Release Test")
    git("config", "user.email", "release@example.invalid")
    version = "0.2.0" if case == "version" else "0.1.0"
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nversion = "{version}"\n', encoding="utf-8"
    )
    notes = tmp_path / "docs/releases/v0.1.0.md"
    notes.parent.mkdir(parents=True)
    if case != "missing-notes":
        notes.write_text(" \n\t" if case == "blank-notes" else "Release notes", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "Initial release")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    if case == "unreachable":
        git("checkout", "-b", "other")
        (tmp_path / "other").write_text("other", encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "Unmerged change")
    if case == "lightweight":
        git("tag", "v0.1.0")
    elif case != "missing":
        git("tag", "-a", "v0.1.0", "-m", "Release")
    # Working tree content must never substitute for committed release metadata.
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "99.0.0"', encoding="utf-8")
    notes.write_text("Working tree notes", encoding="utf-8")
    args = [
        "check-tag",
        "--tag",
        "v01.0.0" if case == "bad-name" else "v0.1.0",
        "--repo-root",
        str(tmp_path),
    ]
    assert release.main(args) == (0 if case == "success" else 1)
    output = capsys.readouterr()
    assert output.out == ""
    if case == "success":
        assert output.err == ""
        assert release.main([*args, "--main-ref", "main"]) == 0
    else:
        assert output.err.startswith("ERROR: ")
        assert len(output.err.splitlines()) == 1


@pytest.mark.parametrize(
    "tag",
    ["v1.2", "v1.2.3-rc1", "1.2.3", "v1.02.3", "v1.2.03", "v-1.2.3", "v1.2.3\n", "--help"],
)
def test_invalid_tag_names(tag: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="tag must match"):
        release.check_tag(tag, "origin/main", tmp_path)


def bundle_value() -> dict[str, Any]:
    return {
        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "verificationMaterial": {"certificate": {}},
        "dsseEnvelope": {
            "payload": "e30=",
            "payloadType": "application/vnd.in-toto+json",
            "signatures": [{"sig": "test"}],
        },
    }


def test_envelope_round_trip(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    output = tmp_path / "file.intoto.jsonl"
    value = bundle_value()
    bundle.write_text(json.dumps(value) + "\n", encoding="utf-8")
    assert release.main(["envelope", "--bundle", str(bundle), "--output", str(output)]) == 0
    expected = json.dumps(value["dsseEnvelope"], separators=(",", ":")) + "\n"
    assert output.read_bytes() == expected.encode()
    assert release.main(["check-envelope", "--bundle", str(bundle), "--envelope", str(output)]) == 0


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\n",
        "{}\n{}",
        "{} {}",
        "{\n}",
        "{}\n\n",
        "invalid",
        "[]",
        "null",
        "{}",
        '{"dsseEnvelope": []}',
        '{"dsseEnvelope": {}}',
        *[
            json.dumps(
                {
                    "dsseEnvelope": {
                        k: v for k, v in bundle_value()["dsseEnvelope"].items() if k != missing
                    }
                }
            )
            for missing in ("payload", "payloadType", "signatures")
        ],
        *[
            json.dumps({"dsseEnvelope": {**bundle_value()["dsseEnvelope"], "signatures": value}})
            for value in BAD_SIGNATURES
        ],
        '{"dsseEnvelope":{},"dsseEnvelope":{}}',
        '{"dsseEnvelope":NaN}',
    ],
)
@pytest.mark.parametrize("command", ["envelope", "check-envelope"])
def test_bad_bundles(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, command: str
) -> None:
    bundle = tmp_path / "bundle"
    output = tmp_path / "output"
    bundle.write_text(text, encoding="utf-8")
    output.write_text(json.dumps(bundle_value()["dsseEnvelope"]), encoding="utf-8")
    before = output.read_bytes()
    flag = "--output" if command == "envelope" else "--envelope"
    assert release.main([command, "--bundle", str(bundle), flag, str(output)]) == 1
    assert output.read_bytes() == before
    assert len(capsys.readouterr().err.splitlines()) == 1


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{}",
        "[]",
        "invalid",
        "{}\n{}",
        "{} {}",
        "{\n}",
        json.dumps(bundle_value()["dsseEnvelope"]) + "\n\n",
        json.dumps({**bundle_value()["dsseEnvelope"], "payload": "changed"}),
    ],
)
def test_bad_envelope(tmp_path: Path, text: str) -> None:
    bundle, output = tmp_path / "bundle", tmp_path / "output"
    bundle.write_text(json.dumps(bundle_value()), encoding="utf-8")
    output.write_text(text, encoding="utf-8")
    assert release.main(["check-envelope", "--bundle", str(bundle), "--envelope", str(output)]) == 1


@pytest.mark.parametrize("args", [[], ["unknown"], ["envelope"], ["check-tag"]])
def test_argument_errors(args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert release.main(args) == 1
    assert capsys.readouterr().err.startswith("ERROR: ")


def test_current_release_notes_exist() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    notes = ROOT / f"docs/releases/v{version}.md"
    assert notes.is_file(), f"missing release notes: {notes}"
    assert notes.read_text(encoding="utf-8").strip()
