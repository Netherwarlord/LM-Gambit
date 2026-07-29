"""Assemble a portable LM-Gambit archive.

    python packaging/build.py                  # for the current platform
    python packaging/build.py --platform linux # or windows / macos
    python packaging/build.py --skip-web       # reuse an existing web/dist

Produces ``dist/LM-Gambit-<version>-<platform>.{zip,tar.gz}`` containing the
application source, the prebuilt web interface, and a launcher that creates a
virtual environment on first run.

**Why not a frozen binary.** ``llama-cpp-python`` compiles its backend in at
install time, so a bundled interpreter would freeze one choice — whatever the
build machine had, which for a CI runner means CPU-only — for every user
forever. Installing on the target machine lets pip pick the wheel that matches
that machine's hardware. The cost is a Python requirement; the alternative is
shipping something that cannot use anybody's GPU.

Only files git tracks are copied, so the archive cannot pick up local models,
results, settings or virtual environments.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"

#: Tracked paths that have no business in a distribution.
EXCLUDE_PREFIXES = (
    ".github/",
    "tests_py/",
    "packaging/",
    "web/src/",
    "web/public/",
    "web/package.json",
    "web/package-lock.json",
    "web/tsconfig",
    "web/vite.config.ts",
    ".gitignore",
    ".python-version",
    "requirements-ci.txt",
)

PLATFORMS = {
    "windows": {"launcher": "LM-Gambit.bat", "archive": "zip"},
    "linux": {"launcher": "LM-Gambit.sh", "archive": "tar.gz"},
    "macos": {"launcher": "LM-Gambit.sh", "archive": "tar.gz"},
}


def current_platform() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    return "linux"


def read_version() -> str:
    text = (ROOT / "server" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    if not match:
        raise SystemExit("Could not read __version__ from server/__init__.py")
    return match.group(1)


def tracked_files() -> list[str]:
    """Files git tracks, so nothing local leaks into the archive."""
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def included(path: str) -> bool:
    return not any(path.startswith(prefix) for prefix in EXCLUDE_PREFIXES)


def build_web() -> None:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise SystemExit("npm not found. Install Node 20+, or pass --skip-web.")
    print("Building the web interface...")
    for args in (["ci"], ["run", "build"]):
        subprocess.run([npm, *args], cwd=ROOT / "web", check=True, shell=False)


def stage(target: str, staging: Path) -> None:
    """Copy the application into a clean staging directory."""
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    copied = 0
    for relative in tracked_files():
        if not included(relative):
            continue
        source = ROOT / relative
        if not source.is_file():
            continue
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied += 1

    # web/dist is gitignored but is the whole point of shipping a build.
    dist_source = ROOT / "web" / "dist"
    if not (dist_source / "index.html").is_file():
        raise SystemExit(
            "web/dist is missing or incomplete. Run without --skip-web, or "
            "build it with: cd web && npm ci && npm run build"
        )
    shutil.copytree(dist_source, staging / "web" / "dist")

    launcher = PLATFORMS[target]["launcher"]
    _copy_launcher(PACKAGING / launcher, staging / launcher)
    shutil.copy2(PACKAGING / "GPU-ACCELERATION.md", staging / "GPU-ACCELERATION.md")

    print(f"Staged {copied} tracked files plus the web build.")


def _copy_launcher(source: Path, destination: Path) -> None:
    """Copy a launcher with the line endings its interpreter requires.

    ``.gitattributes`` pins these too, but the archive must be correct no
    matter how the tree was checked out: a CRLF ``.sh`` fails on Linux with
    "bad interpreter: ...^M", which is a baffling error for someone who just
    downloaded a release. Normalising here means a stale clone or an unusual
    ``core.autocrlf`` cannot ship a broken launcher.
    """
    text = source.read_bytes().replace(b"\r\n", b"\n")
    if destination.suffix == ".bat":
        text = text.replace(b"\n", b"\r\n")
    destination.write_bytes(text)
    if destination.suffix == ".sh":
        os.chmod(destination, 0o755)


def archive(target: str, staging: Path, version: str) -> Path:
    DIST.mkdir(exist_ok=True)
    stem = f"LM-Gambit-{version}-{target}"

    if PLATFORMS[target]["archive"] == "zip":
        out = DIST / f"{stem}.zip"
        out.unlink(missing_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    zf.write(path, Path(stem) / path.relative_to(staging))
        return out

    out = DIST / f"{stem}.tar.gz"
    out.unlink(missing_ok=True)
    with tarfile.open(out, "w:gz") as tf:
        # arcname roots everything under a single directory so extracting does
        # not scatter files into the user's current folder.
        tf.add(staging, arcname=stem, filter=_normalize)
    return out


def _normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Force sane POSIX metadata regardless of the build machine.

    Windows has no execute bit, so ``os.chmod(0o755)`` on the staged launcher
    is a no-op there and the shell script arrives non-executable — a Linux user
    extracts it and gets "permission denied". Setting the mode on the archive
    member instead makes a tarball built on Windows identical to one built on
    Linux. Ownership is zeroed for the same reason: whoever built it is not who
    should own the extracted files.
    """
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    if info.isdir():
        info.mode = 0o755
    elif info.name.endswith(".sh"):
        info.mode = 0o755
    else:
        info.mode = 0o644
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform",
        choices=[*sorted(PLATFORMS), "all"],
        default=current_platform(),
        help="Target platform, or 'all' for a complete release set",
    )
    parser.add_argument("--skip-web", action="store_true", help="Reuse an existing web/dist")
    args = parser.parse_args()

    targets = sorted(PLATFORMS) if args.platform == "all" else [args.platform]

    version = read_version()
    print(f"LM-Gambit {version} -> {', '.join(targets)}")

    # Once, not once per target: the bundle is identical on every platform.
    if not args.skip_web:
        build_web()

    built = []
    for target in targets:
        staging = DIST / f"_staging-{target}"
        stage(target, staging)
        built.append(archive(target, staging, version))
        shutil.rmtree(staging, ignore_errors=True)

    print()
    for out in built:
        size_mb = out.stat().st_size / (1024 * 1024)
        print(f"  {out.relative_to(ROOT)}  ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
