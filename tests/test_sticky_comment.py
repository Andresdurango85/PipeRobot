from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from piperobot.reports.pr_comment import COMMENT_MARKER
from piperobot.reports.sticky_comment import (
    BOT_LOGIN,
    PAGE_SIZE,
    GitHubTransport,
    is_transient,
    main,
    upsert_sticky_comment,
)

REPO = "owner/repo"
BODY = f"{COMMENT_MARKER}\n## ✅ PipeRobot gate: PASS\n"


class FakeGitHub:
    """In-memory stand-in for the three GitHub endpoints the module uses."""

    def __init__(self, comments: list[dict[str, Any]] | None = None) -> None:
        self.comments = comments or []
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:  # noqa: ANN401 - parsed JSON
        self.calls.append((method, path.split("?")[0]))
        if method == "GET":
            page = int(path.split("page=")[-1])
            return self.comments[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        assert payload is not None
        if method == "POST":
            self.comments.append({"id": 999, "user": {"login": BOT_LOGIN}, **payload})
        elif method == "PATCH":
            comment_id = int(path.rsplit("/", 1)[-1])
            next(c for c in self.comments if c["id"] == comment_id).update(payload)
        return {}


def _comment(comment_id: int, body: str, login: str = "someone") -> dict[str, Any]:
    return {"id": comment_id, "user": {"login": login}, "body": body}


def test_creates_comment_when_none_exists() -> None:
    github = FakeGitHub([_comment(1, "LGTM")])

    assert upsert_sticky_comment(github, REPO, 7, BODY) == "created"
    assert github.comments[-1]["body"] == BODY


def test_updates_its_own_comment_instead_of_adding_one() -> None:
    github = FakeGitHub([_comment(1, f"{COMMENT_MARKER}\nold", BOT_LOGIN)])

    assert upsert_sticky_comment(github, REPO, 7, BODY) == "updated"
    assert len(github.comments) == 1
    assert github.comments[0]["body"] == BODY
    assert ("PATCH", f"/repos/{REPO}/issues/comments/1") in github.calls


def test_never_edits_a_human_comment_that_quotes_the_marker() -> None:
    github = FakeGitHub([_comment(1, f"{COMMENT_MARKER} copied by a human", "andres")])

    assert upsert_sticky_comment(github, REPO, 7, BODY) == "created"
    assert github.comments[0]["body"].endswith("copied by a human")


def test_finds_comment_on_a_later_page() -> None:
    filler = [_comment(i, "chatter") for i in range(PAGE_SIZE)]
    github = FakeGitHub([*filler, _comment(500, f"{COMMENT_MARKER}\nold", BOT_LOGIN)])

    assert upsert_sticky_comment(github, REPO, 7, BODY) == "updated"
    assert github.comments[-1]["body"] == BODY


def test_rejects_body_without_marker() -> None:
    with pytest.raises(ValueError, match="marker"):
        upsert_sticky_comment(FakeGitHub(), REPO, 7, "no marker")


def test_main_requires_token_and_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    body = tmp_path / "comment.md"
    body.write_text(BODY, encoding="utf-8")

    assert main(["--pr", "7", "--body-file", str(body)]) == 2


def test_named_gates_have_independent_comments() -> None:
    github = FakeGitHub()
    markers = [COMMENT_MARKER, "<!-- piperobot-gate:so101 -->"]
    for marker in markers:
        assert upsert_sticky_comment(github, REPO, 7, marker + "\nold", marker=marker) == "created"
        # Fake transport assigns a fixed ID; give each comment a unique one like GitHub does.
        github.comments[-1]["id"] = len(github.comments)
    for marker in markers:
        assert upsert_sticky_comment(github, REPO, 7, marker + "\nnew", marker=marker) == "updated"
    assert [c["body"] for c in github.comments] == [m + "\nnew" for m in markers]


@pytest.mark.parametrize(
    "marker",
    [
        "",
        "<!-- piperobot-gate: -->",
        "<!-- other -->",
        "<!-- piperobot-gate:x -->\n",
        "<!-- piperobot-gate:<b> -->",
    ],
)
def test_invalid_markers(marker: str) -> None:
    with pytest.raises(ValueError, match="marker"):
        upsert_sticky_comment(FakeGitHub(), REPO, 7, marker, marker=marker)


class JSONResponse:
    def __init__(self, value: object) -> None:
        self.data = json.dumps(value).encode()

    def __enter__(self) -> JSONResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self) -> bytes:
        return self.data


class FakeOpener:
    """Exercise real request serialization, including an acknowledged-late POST."""

    def __init__(
        self, failures: list[tuple[str, int | Exception]], *, create_before_timeout: bool = False
    ) -> None:
        self.failures = list(failures)
        self.create_before_timeout = create_before_timeout
        self.comments: list[dict[str, Any]] = []
        self.calls: list[tuple[str, str]] = []
        self.sleeps: list[float] = []

    def __call__(self, req: urllib.request.Request, *, timeout: float) -> JSONResponse:
        assert timeout == 30
        method = req.get_method()
        url = urlsplit(req.full_url)
        self.calls.append((method, url.path))
        payload = json.loads(req.data) if isinstance(req.data, bytes) else None
        failure = None
        if self.failures and self.failures[0][0] == method:
            _, failure = self.failures.pop(0)
        if failure is not None and not (
            method == "POST" and self.create_before_timeout and isinstance(failure, TimeoutError)
        ):
            if isinstance(failure, int):
                raise urllib.error.HTTPError(req.full_url, failure, "msg", Message(), None)
            raise failure
        if method == "GET":
            assert payload is None
            page = int(parse_qs(url.query)["page"][0])
            return JSONResponse(self.comments[(page - 1) * PAGE_SIZE : page * PAGE_SIZE])
        assert payload is not None
        if method == "POST":
            comment_id = max((c["id"] for c in self.comments), default=0) + 1
            self.comments.append(_comment(comment_id, payload["body"], BOT_LOGIN))
        elif method == "PATCH":
            comment_id = int(url.path.rsplit("/", 1)[-1])
            next(c for c in self.comments if c["id"] == comment_id).update(payload)
        else:
            raise AssertionError(method)
        if isinstance(failure, Exception):
            raise failure
        return JSONResponse({})


LIST_PATH = f"/repos/{REPO}/issues/7/comments"


@pytest.mark.parametrize("failures", [1, 2])
def test_retries_post_server_errors(failures: int) -> None:
    opener = FakeOpener([("POST", 500)] * failures)
    assert (
        upsert_sticky_comment(
            GitHubTransport("token", opener), REPO, 7, BODY, sleep=opener.sleeps.append
        )
        == "created"
    )
    assert len(opener.comments) == 1
    assert opener.comments[0]["body"] == BODY
    assert opener.sleeps == [2.0, 5.0][:failures]
    assert opener.calls == [("GET", LIST_PATH), ("POST", LIST_PATH)] * (failures + 1)
    assert opener.failures == []


@pytest.mark.parametrize("code", [422, 403])
def test_client_errors_do_not_retry(code: int) -> None:
    opener = FakeOpener([("POST", code)])
    with pytest.raises(urllib.error.HTTPError) as caught:
        upsert_sticky_comment(
            GitHubTransport("token", opener), REPO, 7, BODY, sleep=opener.sleeps.append
        )
    assert caught.value.code == code
    assert opener.sleeps == []
    assert opener.calls == [("GET", LIST_PATH), ("POST", LIST_PATH)]
    assert opener.comments == []


@pytest.mark.parametrize(("code", "attempts"), [(500, 3), (422, 1), (403, 1)])
def test_main_handles_http_failures(
    code: int,
    attempts: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    opener = FakeOpener([("POST", code)] * attempts)
    monkeypatch.setattr(urllib.request, "urlopen", opener)
    monkeypatch.setattr(time, "sleep", opener.sleeps.append)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    body = tmp_path / "comment.md"
    body.write_text(BODY, encoding="utf-8")
    assert main(["--pr", "7", "--body-file", str(body)]) == 2
    assert opener.comments == []
    assert opener.sleeps == ([2.0, 5.0] if code == 500 else [])
    assert opener.calls == [("GET", LIST_PATH), ("POST", LIST_PATH)] * attempts
    stderr = capsys.readouterr().err
    assert "ERROR: could not post the sticky comment:" in stderr
    assert stderr.count("retrying in") == attempts - 1


def test_timeout_after_creation_updates_without_duplicate() -> None:
    opener = FakeOpener([("POST", TimeoutError("read timeout"))], create_before_timeout=True)
    assert (
        upsert_sticky_comment(
            GitHubTransport("token", opener), REPO, 7, BODY, sleep=opener.sleeps.append
        )
        == "updated"
    )
    assert len(opener.comments) == 1
    assert opener.comments[0]["body"] == BODY
    assert opener.sleeps == [2.0]
    assert opener.calls == [
        ("GET", LIST_PATH),
        ("POST", LIST_PATH),
        ("GET", LIST_PATH),
        ("PATCH", f"/repos/{REPO}/issues/comments/1"),
    ]


@pytest.mark.parametrize("error", [502, urllib.error.URLError("connection refused")])
def test_retries_list_failures(error: int | Exception) -> None:
    opener = FakeOpener([("GET", error)])
    assert (
        upsert_sticky_comment(
            GitHubTransport("token", opener), REPO, 7, BODY, sleep=opener.sleeps.append
        )
        == "created"
    )
    assert opener.sleeps == [2.0]
    assert opener.calls == [("GET", LIST_PATH), ("GET", LIST_PATH), ("POST", LIST_PATH)]
    assert len(opener.comments) == 1


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        *[
            (urllib.error.HTTPError("url", code, "msg", Message(), None), True)
            for code in (500, 502, 503)
        ],
        *[
            (urllib.error.HTTPError("url", code, "msg", Message(), None), False)
            for code in (400, 403, 404, 422)
        ],
        (urllib.error.URLError("refused"), True),
        (urllib.error.URLError(TimeoutError()), True),
        (TimeoutError(), True),
        (ConnectionResetError(), True),
        (http.client.RemoteDisconnected("closed"), True),
        (http.client.IncompleteRead(b"partial"), True),
        (ValueError(), False),
    ],
)
def test_transient_classifier(error: BaseException, expected: bool) -> None:
    assert is_transient(error) is expected


def test_programming_error_does_not_retry() -> None:
    error = ValueError("bad JSON")
    opener = FakeOpener([("POST", error)])
    with pytest.raises(ValueError, match="bad JSON") as caught:
        upsert_sticky_comment(
            GitHubTransport("token", opener), REPO, 7, BODY, sleep=opener.sleeps.append
        )
    assert caught.value is error
    assert opener.sleeps == []
    assert opener.calls == [("GET", LIST_PATH), ("POST", LIST_PATH)]
