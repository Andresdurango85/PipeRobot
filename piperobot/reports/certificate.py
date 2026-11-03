"""Verify evaluation certificates signed by the workflow on main.

A certificate proves the signer workflow, commit, subject digest and hosted signing
runner. The evaluating job's own integrity, its dependencies from uv.lock and its
runner are trusted, not proven.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from piperobot.reports.history import (
    GATE_VERDICT_PREDICATE_TYPE,
    HistoryError,
    HistoryRecord,
    compress_seeds,
)
from piperobot.results import load_results


class CertificateError(ValueError):
    """The certificate or its evidence did not verify."""


class CertificateMismatch(CertificateError):
    """Signed evaluation fields disagree with the evidence."""


class CertificateNotFound(CertificateError):
    """No certificate covers this exact file."""

    def __init__(self, digest: str) -> None:
        super().__init__(
            "NOT CERTIFIED: no certificate exists for this exact file "
            f"(sha256 {digest}). It was altered, or never certified by history.yml on main."
        )


class CertificateInputError(ValueError):
    """The verifier could not load its inputs."""


def _bundle_digests(bundle: Path) -> set[str]:
    """Read untrusted subjects; gh must still verify the bundle cryptographically."""
    digests: set[str] = set()
    try:
        contents = bundle.read_text(encoding="utf-8")
        try:
            document = json.loads(contents)
        except ValueError:
            document = None
        lines = [contents] if isinstance(document, dict) else contents.splitlines()
        if not lines:
            raise ValueError("empty bundle")
        for line in lines:
            entry = json.loads(line)
            statement = json.loads(
                base64.b64decode(entry["dsseEnvelope"]["payload"], validate=True)
            )
            subjects = statement["subject"]
            if not isinstance(subjects, list) or not subjects:
                raise ValueError("expected nonempty subject list")
            for subject in subjects:
                digest = subject["digest"]["sha256"]
                if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                    raise ValueError("invalid subject sha256")
                digests.add(digest)
    except (OSError, ValueError, TypeError, KeyError, binascii.Error) as exc:
        raise CertificateInputError(f"invalid bundle: {exc}") from exc
    return digests


@dataclass(frozen=True)
class Certificate:
    record: HistoryRecord
    commit: str
    signer: str
    run_url: str
    subject_sha256: str

    def __str__(self) -> str:
        r = self.record
        return (
            f"VERIFIED: {r.policy}/{r.evaluator} {r.successes}/{r.trials} "
            f"({100 * r.successes / r.trials:.1f}%) {r.verdict.value.upper()} "
            f"at {self.commit[:7]}, "
            f"run {r.run_id}.{r.run_attempt}, signed by {self.signer}"
        )


def verification_command(
    results_path: Path, *, repo: str = "Andresdurango85/PipeRobot", gh: str = "gh"
) -> list[str]:
    """Build the pinned verification policy shared by the verifier and history page."""
    return [
        gh,
        "attestation",
        "verify",
        str(results_path),
        "--repo",
        repo,
        "--signer-workflow",
        f"{repo}/.github/workflows/history.yml",
        "--source-ref",
        "refs/heads/main",
        "--deny-self-hosted-runners",
        "--predicate-type",
        GATE_VERDICT_PREDICATE_TYPE,
        "--format",
        "json",
    ]


def verify(
    results_path: Path,
    *,
    repo: str = "Andresdurango85/PipeRobot",
    bundle: Path | None = None,
    gh: str = "gh",
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Certificate:
    try:
        digest = hashlib.sha256(results_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CertificateInputError(str(exc)) from exc
    command = verification_command(results_path, repo=repo, gh=gh)
    if bundle is not None:
        if digest not in _bundle_digests(bundle):
            raise CertificateNotFound(digest)
        command.extend(("--bundle", str(bundle)))
    try:
        output = run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise CertificateInputError(f"cannot find {gh}: {exc}") from exc
    if output.returncode:
        if bundle is None and (
            "no attestations found" in output.stderr
            or ("HTTP 404" in output.stderr and f"/attestations/sha256:{digest}" in output.stderr)
        ):
            raise CertificateNotFound(digest)
        raise CertificateError(output.stderr.strip())
    try:
        items = json.loads(output.stdout)
    except ValueError as exc:
        raise CertificateInputError(f"invalid gh JSON: {exc}") from exc
    if not isinstance(items, list) or not items:
        raise CertificateInputError("expected a nonempty gh JSON list")
    selected: tuple[HistoryRecord, dict[str, Any], dict[str, Any]] | None = None
    for item in items:
        try:
            verification = item["verificationResult"]
            statement = verification["statement"]
            certificate = verification["signature"]["certificate"]
            if not isinstance(statement, dict) or not isinstance(certificate, dict):
                raise TypeError
            predicate = statement["predicate"]
        except (KeyError, TypeError) as exc:
            raise CertificateInputError("unexpected gh verification JSON structure") from exc
        try:
            record = HistoryRecord.from_dict(predicate)
        except HistoryError:
            continue
        selected = record, statement, certificate
        break
    if selected is None:
        raise CertificateError("not a gate-verdict record")
    record, statement, certificate = selected
    try:
        subjects = statement["subject"]
        if not isinstance(subjects, list) or any(
            not isinstance(subject, dict)
            or not isinstance(subject.get("digest"), dict)
            or not isinstance(subject["digest"].get("sha256"), str)
            for subject in subjects
        ):
            raise TypeError
        fields = (
            "sourceRepositoryDigest",
            "sourceRepositoryRef",
            "buildSignerURI",
            "runnerEnvironment",
            "runInvocationURI",
        )
        if any(not isinstance(certificate.get(field), str) for field in fields):
            raise TypeError
        predicate_type = statement["predicateType"]
    except (KeyError, TypeError) as exc:
        raise CertificateInputError("unexpected gh statement or certificate structure") from exc
    if predicate_type != GATE_VERDICT_PREDICATE_TYPE:
        raise CertificateError("not a gate-verdict record: wrong predicate type")
    if not any(subject["digest"]["sha256"] == digest for subject in subjects):
        raise CertificateError("subject sha256 does not match results file")
    if record.commit != certificate["sourceRepositoryDigest"]:
        raise CertificateError("record commit does not match certificate sourceRepositoryDigest")
    invocation = re.fullmatch(
        rf"https://github\.com/{re.escape(repo)}/actions/runs/([0-9]+)/attempts/([0-9]+)",
        certificate["runInvocationURI"],
    )
    if invocation is None or (record.run_id, record.run_attempt) != tuple(
        map(int, invocation.groups())
    ):
        raise CertificateError("record run_id/run_attempt does not match runInvocationURI")
    try:
        results = load_results(results_path)
    except (OSError, ValueError) as exc:  # ResultsError is a ValueError; others are bugs
        raise CertificateInputError(f"invalid results: {exc}") from exc
    if (record.successes, record.trials) != (results.successes, results.trials):
        raise CertificateMismatch(
            "MISMATCH: the signed record is inconsistent with its signed results file "
            f"(signer bug): the record says {record.successes}/{record.trials} successes, "
            f"results.json has {results.successes}/{results.trials}."
        )
    for field, expected in (
        ("policy", results.policy),
        ("evaluator", results.evaluator),
        ("seeds", compress_seeds(e.seed for e in results.episodes)),
    ):
        actual = getattr(record, field)
        if actual != expected:
            raise CertificateMismatch(
                "MISMATCH: the signed record is inconsistent with its signed results file "
                f"(signer bug): the record says {field} {actual!r}, results.json has "
                f"{expected!r}."
            )
    return Certificate(
        record,
        certificate["sourceRepositoryDigest"],
        certificate["buildSignerURI"],
        certificate["runInvocationURI"],
        digest,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("verify")
    check.add_argument("results", type=Path)
    check.add_argument("--bundle", type=Path)
    check.add_argument("--repo", default="Andresdurango85/PipeRobot")
    args = parser.parse_args(argv)
    try:
        print(verify(args.results, bundle=args.bundle, repo=args.repo))
    except CertificateInputError as exc:
        print(f"ERROR: {' '.join(str(exc).splitlines())}", file=sys.stderr)
        return 2
    except (CertificateNotFound, CertificateMismatch) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except CertificateError as exc:
        print(f"NOT VERIFIED: {' '.join(str(exc).splitlines())}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
