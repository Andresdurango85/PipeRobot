"""Create or update the gate's single "sticky" comment on a pull request (ADR 0008).

The comment is found by the hidden marker on its first line and by its author (the Actions bot),
so a human comment that quotes the marker is never overwritten.

Usage (in a workflow, with GITHUB_TOKEN and GITHUB_REPOSITORY set):
    uv run python -m reports.sticky_comment --pr 12 --body-file out/comment.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from reports.pr_comment import COMMENT_MARKER

API_URL = "https://api.github.com"
BOT_LOGIN = "github-actions[bot]"
PAGE_SIZE = 100


class Transport(Protocol):
    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any: ...  # noqa: ANN401 - parsed JSON


class GitHubTransport:
    """Minimal GitHub REST client over urllib (no extra dependencies)."""

    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:  # noqa: ANN401 - parsed JSON
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(  # noqa: S310 - fixed https://api.github.com base URL
            API_URL + path, data=data, headers=self._headers, method=method
        )
        with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310 - same URL
            return json.loads(response.read() or b"null")


def find_sticky_comment(transport: Transport, repo: str, pr: int, author: str) -> int | None:
    page = 1
    while True:
        comments = transport.request(
            "GET", f"/repos/{repo}/issues/{pr}/comments?per_page={PAGE_SIZE}&page={page}"
        )
        for comment in comments:
            if comment["user"]["login"] == author and comment["body"].startswith(COMMENT_MARKER):
                return int(comment["id"])
        if len(comments) < PAGE_SIZE:
            return None
        page += 1


def upsert_sticky_comment(
    transport: Transport, repo: str, pr: int, body: str, author: str = BOT_LOGIN
) -> str:
    """Update the existing sticky comment, or create it. Returns "updated" or "created"."""
    if not body.startswith(COMMENT_MARKER):
        raise ValueError("comment body must start with the gate marker")
    comment_id = find_sticky_comment(transport, repo, pr, author)
    if comment_id is None:
        transport.request("POST", f"/repos/{repo}/issues/{pr}/comments", {"body": body})
        return "created"
    transport.request("PATCH", f"/repos/{repo}/issues/comments/{comment_id}", {"body": body})
    return "updated"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pr", type=int, required=True, help="Pull request number")
    parser.add_argument("--body-file", type=Path, required=True, help="Rendered comment")
    args = parser.parse_args(argv)

    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("ERROR: GITHUB_TOKEN and GITHUB_REPOSITORY must be set", file=sys.stderr)
        return 2
    body = args.body_file.read_text(encoding="utf-8")
    action = upsert_sticky_comment(GitHubTransport(token), repo, args.pr, body)
    print(f"Sticky comment {action} on {repo}#{args.pr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
