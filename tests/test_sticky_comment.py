from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from reports.pr_comment import COMMENT_MARKER
from reports.sticky_comment import BOT_LOGIN, PAGE_SIZE, main, upsert_sticky_comment

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
