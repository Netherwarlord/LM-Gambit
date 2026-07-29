"""Publish release archives to a Gitea instance.

    python packaging/publish_gitea.py --tag v2.0.0 dist/*.zip dist/*.tar.gz

Creates the release if it does not exist, then uploads each file as an asset.
Re-running replaces assets of the same name rather than erroring, so a failed
half-finished publish can simply be run again.

Reads configuration from the environment, which Gitea Actions populates:

    GITEA_URL         instance root, e.g. https://git.example.lan
                      (falls back to GITHUB_SERVER_URL, which Gitea sets)
    GITEA_REPOSITORY  "owner/repo" (falls back to GITHUB_REPOSITORY)
    GITEA_TOKEN       an access token with write:repository

**Why not a marketplace action.** ``softprops/action-gh-release`` targets
GitHub's API and does not work against Gitea. The Gitea-flavoured forks exist
but pin you to a third party for the one step that matters most, on a forge
whose API is small enough to call directly. urllib covers it in ~150 lines with
nothing to install and nothing to trust.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

TIMEOUT = 120


class PublishError(RuntimeError):
    pass


def _request(
    method: str,
    url: str,
    token: str,
    *,
    body: bytes | None = None,
    content_type: str | None = None,
) -> dict | list | None:
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Authorization", f"token {token}")
    request.add_header("Accept", "application/json")
    if content_type:
        request.add_header("Content-Type", content_type)

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        # The response body carries Gitea's actual complaint; without it the
        # caller only sees "HTTP Error 422" and has to guess.
        detail = error.read().decode("utf-8", "replace").strip()
        raise PublishError(f"{method} {url} -> {error.code} {error.reason}\n{detail}") from None
    except urllib.error.URLError as error:
        raise PublishError(f"{method} {url} -> {error.reason}") from None

    return json.loads(payload) if payload else None


def find_or_create_release(api: str, token: str, tag: str, *, draft: bool, notes: str) -> dict:
    try:
        return _request("GET", f"{api}/releases/tags/{tag}", token)
    except PublishError as error:
        if "404" not in str(error):
            raise

    print(f"Creating release {tag}")
    body = json.dumps(
        {"tag_name": tag, "name": tag, "body": notes, "draft": draft, "prerelease": False}
    ).encode()
    return _request("POST", f"{api}/releases", token, body=body, content_type="application/json")


def upload_asset(api: str, token: str, release: dict, path: Path) -> None:
    # Uploading over an existing name appends rather than replaces, which would
    # leave two assets called LM-Gambit-2.0.0-linux.tar.gz after a re-run.
    for asset in release.get("assets") or []:
        if asset.get("name") == path.name:
            print(f"  replacing existing {path.name}")
            _request("DELETE", f"{api}/releases/{release['id']}/assets/{asset['id']}", token)

    boundary = f"----LMGambit{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="attachment"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )

    url = f"{api}/releases/{release['id']}/assets?name={urllib.parse.quote(path.name)}"
    _request(
        "POST",
        url,
        token,
        body=body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    print(f"  uploaded {path.name} ({path.stat().st_size / (1024 * 1024):.1f} MB)")


DEFAULT_NOTES = """\
Download the archive for your platform, extract it, and run the launcher
inside — `LM-Gambit.bat` on Windows, `./LM-Gambit.sh` on macOS and Linux.

The first run creates a virtual environment and installs dependencies; that
takes a few minutes and happens once. It needs **Python 3.10 or newer** on the
machine. See `GPU-ACCELERATION.md` in the archive for CUDA, Metal and ROCm.

Scores read as *"correct where checkable, well-formed elsewhere"* — 16 of the
26 built-in questions have answer keys, and the rest are graded on form.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="Archives to attach")
    parser.add_argument("--tag", required=True, help="Tag to release, e.g. v2.0.0")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish immediately instead of leaving a draft for review",
    )
    args = parser.parse_args()

    url = os.environ.get("GITEA_URL") or os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITEA_REPOSITORY") or os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITEA_TOKEN")

    missing = [
        name
        for name, value in (
            ("GITEA_URL", url),
            ("GITEA_REPOSITORY", repository),
            ("GITEA_TOKEN", token),
        )
        if not value
    ]
    if missing:
        print(f"Missing environment: {', '.join(missing)}", file=sys.stderr)
        return 1

    missing_files = [str(path) for path in args.files if not path.is_file()]
    if missing_files:
        print(f"No such file: {', '.join(missing_files)}", file=sys.stderr)
        return 1

    api = f"{url.rstrip('/')}/api/v1/repos/{repository}"

    try:
        release = find_or_create_release(
            api, token, args.tag, draft=not args.publish, notes=DEFAULT_NOTES
        )
        for path in args.files:
            upload_asset(api, token, release, path)
    except PublishError as error:
        print(f"\n{error}", file=sys.stderr)
        return 1

    state = "published" if args.publish else "draft"
    print(f"\n{args.tag} {state}: {url.rstrip('/')}/{repository}/releases/tag/{args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
