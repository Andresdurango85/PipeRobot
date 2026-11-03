"""Fetch verified course assets outside the checkout; no simulator required."""

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from collections.abc import Callable, Sequence
from email.message import Message
from pathlib import Path
from typing import IO, Any
from urllib.parse import urlsplit

MANIFEST = Path(__file__).resolve().parents[1] / "envs" / "course_assets.json"


def require_https(url: str) -> None:
    if urlsplit(url).scheme != "https" or not urlsplit(url).hostname:
        raise ValueError(f"Only HTTPS asset URLs are allowed: {url}")


class HTTPSRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        require_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url: str) -> bytes:
    require_https(url)
    opener = urllib.request.build_opener(HTTPSRedirectHandler())
    with opener.open(url, timeout=120) as response:
        return response.read()


def default_cache_dir(commit: str) -> Path:
    base = (
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        if os.name == "nt"
        else Path.home() / ".cache"
    )
    return base / "piperobot" / "course-assets" / commit


def validate_cache_dir(cache_dir: Path) -> Path:
    resolved = cache_dir.expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            if resolved.is_relative_to(parent):
                raise ValueError(
                    "Assets are never stored in the repo; choose an external cache dir"
                )
            break
    return resolved


def fetch_assets(
    manifest: dict[str, Any],
    cache_dir: Path,
    *,
    include_reference: bool = False,
    check: bool = False,
    fetch: Callable[[str], bytes] = download,
) -> dict[str, str]:
    cache_dir = validate_cache_dir(cache_dir)
    source = manifest["source"]
    result = {}
    for asset in manifest["assets"]:
        if asset["use"] == "reference" and not include_reference:
            continue
        name = asset["name"]
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            raise ValueError(f"Invalid asset name: {name}")
        url = source["url_template"].format(**source, name=name)
        require_https(url)
        target = cache_dir / name
        expected = asset["sha256"]
        if target.is_file():
            data = target.read_bytes()
            if len(data) == asset["size"] and hashlib.sha256(data).hexdigest() == expected:
                result[name] = "cached"
                continue
        if check:
            result[name] = "missing_or_invalid"
            continue
        cache_dir.mkdir(parents=True, exist_ok=True)
        part = cache_dir / f"{name}.part"
        try:
            data = fetch(url)
            part.write_bytes(data)
            actual = hashlib.sha256(data).hexdigest()
            if len(data) != asset["size"] or actual != expected:
                raise ValueError(
                    f"{name}: expected sha256 {expected}, actual {actual}; "
                    f"expected size {asset['size']}, actual {len(data)}"
                )
            part.replace(target)
        finally:
            part.unlink(missing_ok=True)
        result[name] = "downloaded"
    return result


def main(argv: Sequence[str] | None = None, *, fetch: Callable[[str], bytes] = download) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--include-reference", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        cache = validate_cache_dir(
            args.cache_dir or default_cache_dir(manifest["source"]["commit"])
        )
        print(f"cache: {cache}")
        result = fetch_assets(
            manifest, cache, include_reference=args.include_reference, check=args.check, fetch=fetch
        )
        if args.json:
            print(json.dumps(result, sort_keys=True))
        return int("missing_or_invalid" in result.values())
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
