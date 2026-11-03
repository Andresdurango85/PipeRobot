from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from piperobot.reports import certificate as module
from piperobot.reports.certificate import (
    CertificateError,
    CertificateInputError,
    CertificateMismatch,
    CertificateNotFound,
    verify,
)
from piperobot.reports.history import GATE_VERDICT_PREDICATE_TYPE, record_from_gate
from piperobot.results import EpisodeResult, EvalResults, save_results
from piperobot.stats.gate import SuccessCount, decide

REPO = "Andresdurango85/PipeRobot"
SIGNER = f"https://github.com/{REPO}/.github/workflows/history.yml@refs/heads/main"


def evidence(
    path: Path,
    successes: int = 30,
    trials: int = 50,
    *,
    policy: str = "policy",
    evaluator: str = "sim",
    seed_start: int = 0,
) -> list[dict[str, Any]]:
    results = EvalResults(
        policy,
        evaluator,
        tuple(EpisodeResult(seed_start + i, i < successes) for i in range(trials)),
    )
    save_results(results, path)
    record = record_from_gate(
        results,
        decide(SuccessCount(successes, trials), SuccessCount(successes, trials)),
        commit="a" * 40,
        commit_date="2026-11-03T10:00:00Z",
        evaluated_at="2026-11-03T10:01:00Z",
        run_url=f"https://github.com/{REPO}/actions/runs/1",
        run_id=1,
        run_attempt=2,
        platform="CPU",
    )
    return [
        {
            "verificationResult": {
                "statement": {
                    "subject": [
                        {
                            "name": path.name,
                            "digest": {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
                        }
                    ],
                    "predicateType": GATE_VERDICT_PREDICATE_TYPE,
                    "predicate": record.to_dict(),
                },
                "signature": {
                    "certificate": {
                        "sourceRepositoryDigest": record.commit,
                        "sourceRepositoryRef": "refs/heads/main",
                        "buildSignerURI": SIGNER,
                        "runnerEnvironment": "github-hosted",
                        "runInvocationURI": f"https://github.com/{REPO}/actions/runs/1/attempts/2",
                    }
                },
            }
        }
    ]


def fake(
    payload: object, *, code: int = 0, stderr: str = ""
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], code, json.dumps(payload), stderr)

    return run


def write_bundle(path: Path, statements: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(
            json.dumps(
                {
                    "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                    "verificationMaterial": {},
                    "dsseEnvelope": {
                        "payload": base64.b64encode(json.dumps(statement).encode()).decode(),
                        "payloadType": "application/vnd.in-toto+json",
                        "signatures": [],
                    },
                }
            )
            for statement in statements
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("bundle", [None, Path("bundle.json")])
def test_success_and_command(tmp_path: Path, bundle: Path | None) -> None:
    path = tmp_path / "results.json"
    payload = evidence(path)
    if bundle is not None:
        bundle = tmp_path / bundle
        write_bundle(bundle, [payload[0]["verificationResult"]["statement"]])

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        expected = [
            "custom-gh",
            "attestation",
            "verify",
            str(path),
            "--repo",
            REPO,
            "--signer-workflow",
            f"{REPO}/.github/workflows/history.yml",
            "--source-ref",
            "refs/heads/main",
            "--deny-self-hosted-runners",
            "--predicate-type",
            GATE_VERDICT_PREDICATE_TYPE,
            "--format",
            "json",
        ]
        if bundle is not None:
            expected += ["--bundle", str(bundle)]
        assert command == expected
        assert kwargs == {"capture_output": True, "text": True, "check": False}
        return fake(payload)(command)

    result = verify(path, bundle=bundle, gh="custom-gh", run=run)
    assert str(result) == (
        f"VERIFIED: policy/sim 30/50 (60.0%) PASS at aaaaaaa, run 1.2, signed by {SIGNER}"
    )
    assert result.subject_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("field", "value", "message", "mismatch"),
    [
        ("schema", 2, "not a gate-verdict record", False),
        ("subject", "bad", "subject sha256", False),
        ("commit", "b" * 40, "record commit", False),
        ("run_id", 9, "run_id/run_attempt", False),
        ("run_attempt", 9, "run_id/run_attempt", False),
        ("successes", 29, "29/50 successes, results.json has 30/50", True),
        ("trials", 51, "30/51 successes, results.json has 30/50", True),
        ("policy", "other", "policy 'other'.*'policy'", True),
        ("evaluator", "other", "evaluator 'other'.*'sim'", True),
        ("seeds", "1-50", "seeds '1-50'.*'0-49'", True),
    ],
)
def test_checks(tmp_path: Path, field: str, value: object, message: str, mismatch: bool) -> None:
    path = tmp_path / "results.json"
    payload = evidence(path)
    statement = payload[0]["verificationResult"]["statement"]
    if field == "subject":
        statement["subject"][0]["digest"]["sha256"] = value
    else:
        statement["predicate"][field] = value
    with pytest.raises(CertificateMismatch if mismatch else CertificateError, match=message) as exc:
        verify(path, run=fake(payload))
    if mismatch:
        assert "signer bug" in str(exc.value)


@pytest.mark.parametrize("payload", [{}, [], [None], [{"verificationResult": {}}]])
def test_unexpected_json(tmp_path: Path, payload: object) -> None:
    path = tmp_path / "results.json"
    evidence(path)
    with pytest.raises(CertificateInputError):
        verify(path, run=fake(payload))


def test_invalid_json_and_missing_inputs(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    evidence(path)

    def bad(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, "{", "")

    with pytest.raises(CertificateInputError, match="invalid gh JSON"):
        verify(path, run=bad)

    def missing(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("missing")

    with pytest.raises(CertificateInputError, match="cannot find"):
        verify(path, run=missing)
    with pytest.raises(CertificateInputError):
        verify(tmp_path / "absent", run=bad)


def test_first_parseable_predicate(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    payload = evidence(path)
    invalid = json.loads(json.dumps(payload[0]))
    invalid["verificationResult"]["statement"]["predicate"] = {}
    assert verify(path, run=fake([invalid, *payload])).record.successes == 30


@pytest.mark.parametrize(
    ("kind", "status", "prefix"),
    [
        ("gh", 1, "NOT VERIFIED: signature rejected"),
        ("not_found", 1, "NOT CERTIFIED:"),
        ("issuer", 1, "NOT VERIFIED:"),
        ("missing", 2, "ERROR:"),
        ("json", 2, "ERROR:"),
        ("mismatch", 1, "MISMATCH:"),
        ("success", 0, "VERIFIED:"),
    ],
)
def test_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    kind: str,
    status: int,
    prefix: str,
) -> None:
    path = tmp_path / "results.json"
    payload = evidence(path)
    if kind == "mismatch":
        payload[0]["verificationResult"]["statement"]["predicate"]["successes"] = 29

    def injected(path: Path, *, bundle: Path | None = None, repo: str = REPO) -> module.Certificate:
        if kind == "missing":

            def missing(*args: object, **options: object) -> subprocess.CompletedProcess[str]:
                raise FileNotFoundError("missing")

            return verify(path, run=missing, bundle=bundle, repo=repo)
        return verify(
            path,
            run=fake(
                {} if kind == "json" else payload,
                code=1 if kind in {"gh", "not_found", "issuer"} else 0,
                stderr={
                    "not_found": "\nError: no attestations found\n",
                    "issuer": '\nError: verifying with issuer "sigstore.dev"\n',
                }.get(kind, "signature rejected"),
            ),
            bundle=bundle,
            repo=repo,
        )

    monkeypatch.setattr(module, "verify", injected)
    assert module.main(["verify", str(path)]) == status
    captured = capsys.readouterr()
    assert (captured.out if status == 0 else captured.err).startswith(prefix)


@given(
    st.integers(1, 100),
    st.integers(0, 10000),
    st.integers(1, 10000),
    st.text(),
    st.text(),
    st.integers(0, 100000),
)
def test_agreement_and_any_changed_successes(
    trials: int,
    numerator: int,
    change: int,
    policy: str,
    evaluator: str,
    seed_start: int,
) -> None:
    successes = numerator % (trials + 1)
    changed = (successes + 1 + (change - 1) % trials) % (trials + 1)
    with TemporaryDirectory() as directory:
        path = Path(directory) / "results.json"
        payload = evidence(
            path, successes, trials, policy=policy, evaluator=evaluator, seed_start=seed_start
        )
        assert verify(path, run=fake(payload)).record.successes == successes
        payload[0]["verificationResult"]["statement"]["predicate"]["successes"] = changed
        with pytest.raises(CertificateMismatch, match=r"MISMATCH:.*signer bug"):
            verify(path, run=fake(payload))


def test_altered_file_bundle(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    payload = evidence(path, successes=29)
    bundle = tmp_path / "bundle.jsonl"
    write_bundle(bundle, [payload[0]["verificationResult"]["statement"]])
    evidence(path, successes=35)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    def unexpected(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        pytest.fail("gh must not run for a bundle without this file's sha256")

    with pytest.raises(CertificateNotFound, match=digest):
        verify(path, bundle=bundle, run=unexpected)


def test_bundle_collects_all_subjects_and_lines(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    payload = evidence(path)
    statement = payload[0]["verificationResult"]["statement"]
    other = {"name": "other.json", "digest": {"sha256": "b" * 64}}
    bundle = tmp_path / "bundle.jsonl"
    write_bundle(bundle, [{"subject": [other]}, {"subject": [other, *statement["subject"]]}])
    assert verify(path, bundle=bundle, run=fake(payload)).record.successes == 30


@pytest.mark.parametrize(
    "contents",
    [
        "not JSON",
        json.dumps({"dsseEnvelope": {"payload": "!!!"}}),
        json.dumps({}),
        "",
        json.dumps({"dsseEnvelope": {"payload": "e30="}}),
    ],
)
def test_malformed_bundle_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    contents: str,
) -> None:
    path = tmp_path / "results.json"
    evidence(path)
    bundle = tmp_path / "bundle.jsonl"
    bundle.write_text(contents, encoding="utf-8")

    def unexpected(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        pytest.fail("gh must not run for malformed input")

    def injected(path: Path, *, bundle: Path | None = None, repo: str = REPO) -> module.Certificate:
        return verify(path, bundle=bundle, repo=repo, run=unexpected)

    monkeypatch.setattr(module, "verify", injected)
    assert module.main(["verify", str(path), "--bundle", str(bundle)]) == 2
    assert capsys.readouterr().err.startswith("ERROR: invalid bundle:")


@pytest.mark.parametrize(
    ("stderr", "error"),
    [
        ("\nError: no attestations found\n", CertificateNotFound),
        (
            "Error: HTTP 404: Not Found "
            "(https://api.github.com/repos/Andresdurango85/PipeRobot/attestations/"
            "sha256:{digest}?per_page=30&predicate_type="
            "https://github.com/Andresdurango85/PipeRobot/blob/main/"
            "docs/attestations/gate-verdict-v1.md)",
            CertificateNotFound,
        ),
        (
            "Error: HTTP 404: Not Found "
            f"(https://api.github.com/repos/{REPO}/attestations/sha256:{'b' * 64})",
            CertificateError,
        ),
        (
            "Error: HTTP 404: Not Found "
            f"(https://api.github.com/repos/{REPO}/contents/sha256:{{digest}})",
            CertificateError,
        ),
        ('\nError: verifying with issuer "sigstore.dev"\n', CertificateError),
    ],
)
def test_api_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stderr: str,
    error: type[CertificateError],
) -> None:
    path = tmp_path / "results.json"
    evidence(path)
    stderr = stderr.format(digest=hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(error) as exc:
        verify(path, run=fake({}, code=1, stderr=stderr))
    assert type(exc.value) is error
    if error is CertificateError:
        assert str(exc.value) == stderr.strip()

    def injected(path: Path, *, bundle: Path | None = None, repo: str = REPO) -> module.Certificate:
        return verify(path, bundle=bundle, repo=repo, run=fake({}, code=1, stderr=stderr))

    monkeypatch.setattr(module, "verify", injected)
    assert module.main(["verify", str(path)]) == 1
    prefix = "NOT CERTIFIED:" if error is CertificateNotFound else "NOT VERIFIED:"
    assert capsys.readouterr().err.startswith(prefix)


@pytest.mark.parametrize("pretty", [False, True])
def test_single_json_bundle(tmp_path: Path, pretty: bool) -> None:
    path = tmp_path / "results.json"
    payload = evidence(path)
    bundle = tmp_path / "bundle.jsonl"
    write_bundle(bundle, [payload[0]["verificationResult"]["statement"]])
    document = json.loads(bundle.read_text(encoding="utf-8"))
    bundle.write_text(json.dumps(document, indent=2 if pretty else None), encoding="utf-8")
    assert verify(path, bundle=bundle, run=fake(payload)).record.successes == 30
