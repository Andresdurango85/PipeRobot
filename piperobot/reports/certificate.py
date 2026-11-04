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
    GATE_VERDICT_V2_PREDICATE_TYPE,
    HistoryError,
    HistoryRecord,
    compress_seeds,
)
from piperobot.results import load_results
from piperobot.stats.paired import PairedCounts


class CertificateError(ValueError):
    """The certificate or its evidence did not verify."""


class CertificateMismatch(CertificateError):
    """Signed evaluation fields disagree with the evidence."""


class CertificateNotFound(CertificateError):
    """No certificate covers this exact file."""

    def __init__(self, digest: str, *, crlf: bool = False) -> None:
        message = (
            "NOT CERTIFIED: no certificate exists for this exact file "
            f"(sha256 {digest}). It was altered, or never certified on main."
        )
        if crlf:
            message += (
                " The file has CRLF line endings; certified files are LF. "
                "Was it checked out with core.autocrlf?"
            )
        super().__init__(message)


class CertificateInputError(ValueError):
    """The verifier could not load its inputs."""


def _bundle_types(bundle: Path) -> dict[str, str]:
    """Read untrusted subjects; gh must still verify the bundle cryptographically."""
    digests: dict[str, str] = {}
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
                kind = statement.get("predicateType")
                if kind in (GATE_VERDICT_PREDICATE_TYPE, GATE_VERDICT_V2_PREDICATE_TYPE):
                    digests[digest] = kind
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
        series = " " + r.series if r.schema == 2 else ""
        return (
            f"VERIFIED: {r.policy}/{r.evaluator}{series} {r.successes}/{r.trials} "
            f"({100 * r.successes / r.trials:.1f}%) {r.verdict.value.upper()} "
            f"at {self.commit[:7]}, "
            f"run {r.run_id}.{r.run_attempt}, signed by {self.signer}"
        )


def verification_command(
    results_path: Path,
    *,
    repo: str = "Andresdurango85/PipeRobot",
    gh: str = "gh",
    predicate_type: str = GATE_VERDICT_PREDICATE_TYPE,
) -> list[str]:
    """Build the pinned verification policy shared by the verifier and history page."""
    workflow = "certify" if predicate_type == GATE_VERDICT_V2_PREDICATE_TYPE else "history"
    return [
        gh,
        "attestation",
        "verify",
        str(results_path),
        "--repo",
        repo,
        "--signer-workflow",
        f"{repo}/.github/workflows/{workflow}.yml",
        "--source-ref",
        "refs/heads/main",
        "--deny-self-hosted-runners",
        "--predicate-type",
        predicate_type,
        "--format",
        "json",
    ]


def _verify(
    results_path: Path,
    *,
    reference_path: Path | None = None,
    predicate_type: str = GATE_VERDICT_PREDICATE_TYPE,
    repo: str = "Andresdurango85/PipeRobot",
    bundle: Path | None = None,
    gh: str = "gh",
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Certificate:
    try:
        contents = results_path.read_bytes()
        digest = hashlib.sha256(contents).hexdigest()
    except OSError as exc:
        raise CertificateInputError(str(exc)) from exc
    command = verification_command(results_path, repo=repo, gh=gh, predicate_type=predicate_type)
    if bundle is not None:
        if digest not in _bundle_types(bundle):
            raise CertificateNotFound(digest, crlf=b"\r\n" in contents)
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
            raise CertificateNotFound(digest, crlf=b"\r\n" in contents)
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
            if record.schema != (2 if predicate_type == GATE_VERDICT_V2_PREDICATE_TYPE else 1):
                continue
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
        actual_predicate_type = statement["predicateType"]
    except (KeyError, TypeError) as exc:
        raise CertificateInputError("unexpected gh statement or certificate structure") from exc
    if actual_predicate_type != predicate_type:
        raise CertificateError("not a gate-verdict record: wrong predicate type")
    if record.schema == 2:
        caller = certificate.get("buildConfigURI")
        workflow = "nightly" if record.series == "nightly" else "history"
        expected = f"https://github.com/{repo}/.github/workflows/{workflow}.yml@refs/heads/main"
        signer = f"https://github.com/{repo}/.github/workflows/certify.yml@refs/heads/main"
        if caller != expected or certificate["buildSignerURI"] != signer:
            raise CertificateMismatch(
                f"MISMATCH: series {record.series}, caller {caller!r}, "
                f"signer {certificate['buildSignerURI']!r}"
            )
        if record.series == "nightly" and reference_path is None:
            raise CertificateInputError("a nightly certificate needs --reference")
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
    if record.series == "nightly":
        if reference_path is None:
            raise CertificateInputError("a nightly certificate needs --reference")
        try:
            reference_digest = hashlib.sha256(reference_path.read_bytes()).hexdigest()
            reference = load_results(reference_path)
        except (OSError, ValueError) as exc:
            raise CertificateInputError(f"invalid reference: {exc}") from exc
        if not any(subject["digest"]["sha256"] == reference_digest for subject in subjects):
            raise CertificateMismatch("MISMATCH: reference sha256 is not a subject")
        try:
            counts = PairedCounts.from_results(reference, results)
        except ValueError as exc:
            raise CertificateMismatch(f"MISMATCH: paired results: {exc}") from exc
        if record.paired is None or any(
            getattr(record.paired, name) != value for name, value in vars(counts).items()
        ):
            raise CertificateMismatch("MISMATCH: paired cells disagree with results files")
    return Certificate(
        record,
        certificate["sourceRepositoryDigest"],
        certificate["buildSignerURI"],
        certificate["runInvocationURI"],
        digest,
    )


def verify(
    results_path: Path,
    *,
    reference_path: Path | None = None,
    repo: str = "Andresdurango85/PipeRobot",
    bundle: Path | None = None,
    gh: str = "gh",
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Certificate:
    """Verify signed evaluation evidence. Nightly reference_commit is a signed claim;
    the results files cannot establish the reference policy's source commit.
    Untrusted bundle statements only route verification; gh verifies their signatures.
    """
    if bundle is not None:
        try:
            contents = results_path.read_bytes()
            digest = hashlib.sha256(contents).hexdigest()
        except OSError as exc:
            raise CertificateInputError(str(exc)) from exc
        kind = _bundle_types(bundle).get(digest)
        if kind is None:
            raise CertificateNotFound(digest, crlf=b"\r\n" in contents)
        return _verify(
            results_path,
            reference_path=reference_path,
            repo=repo,
            bundle=bundle,
            gh=gh,
            run=run,
            predicate_type=kind,
        )
    try:
        return _verify(
            results_path,
            reference_path=reference_path,
            repo=repo,
            gh=gh,
            run=run,
            predicate_type=GATE_VERDICT_V2_PREDICATE_TYPE,
        )
    except CertificateNotFound:
        return _verify(results_path, repo=repo, gh=gh, run=run)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("verify")
    check.add_argument("results", type=Path)
    check.add_argument("--bundle", type=Path)
    check.add_argument("--reference", type=Path)
    check.add_argument("--repo", default="Andresdurango85/PipeRobot")
    args = parser.parse_args(argv)
    try:
        options: dict[str, Any] = {"bundle": args.bundle, "repo": args.repo}
        if args.reference is not None:
            options["reference_path"] = args.reference
        print(verify(args.results, **options))
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
