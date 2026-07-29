#!/usr/bin/env bash
# LM-Gambit launcher (macOS / Linux).
#
# First run creates a virtual environment beside this script and installs the
# dependencies into it; later runs skip straight to starting the app.
#
# The environment is built on YOUR machine rather than shipped prebuilt, and
# that is the whole point: llama-cpp-python is a compiled package whose GPU
# support is baked in at install time. A prebuilt bundle would freeze one
# choice — almost certainly CPU-only — for everybody. Installing here means pip
# picks the build that matches this machine.
#
# For NVIDIA, AMD or Apple GPU acceleration, see GPU-ACCELERATION.md.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VENV="$HERE/.venv"
PYTHON_MIN="3.10"

find_python() {
    for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

if [ ! -x "$VENV/bin/python" ]; then
    echo "First run — setting up. This takes a few minutes and happens once."
    echo

    if ! PYTHON="$(find_python)"; then
        cat >&2 <<EOF
No suitable Python found.

LM-Gambit needs Python $PYTHON_MIN or newer on your PATH.

  macOS   brew install python@3.12
          or download from https://www.python.org/downloads/
  Linux   sudo apt install python3 python3-venv     (Debian/Ubuntu)
          sudo dnf install python3                  (Fedora)

Then run this script again.
EOF
        exit 1
    fi

    echo "Using $("$PYTHON" --version) at $(command -v "$PYTHON")"

    # python3-venv is a separate package on Debian/Ubuntu and its absence is a
    # confusing failure, so say what to install rather than let it fall over.
    if ! "$PYTHON" -m venv "$VENV" 2>/dev/null; then
        cat >&2 <<EOF

Could not create a virtual environment.

On Debian or Ubuntu this usually means the venv module is missing:

  sudo apt install python3-venv

EOF
        exit 1
    fi

    # llama-cpp-python ships only an sdist to PyPI, so a plain install compiles
    # it from source. On Linux that means a full toolchain and a long wait, and
    # the upstream index below carries prebuilt manylinux wheels instead.
    #
    # Deliberately NOT used on macOS. The PyPI wheel there already carries
    # Metal support, and adding a CPU-only index risks pip picking it on a tie,
    # quietly costing every Apple Silicon user their GPU for no visible reason.
    if [ "$(uname -s)" = "Linux" ]; then
        PIP_INDEX="--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu"
    else
        PIP_INDEX=""
    fi

    echo "Installing dependencies..."
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    # shellcheck disable=SC2086  # intentional word splitting; the URL has no spaces
    if ! "$VENV/bin/python" -m pip install $PIP_INDEX -r "$HERE/requirements.txt"; then
        cat >&2 <<EOF

Dependency installation failed.

If the error above mentions llama-cpp-python, cmake or a missing compiler,
then pip found no prebuilt wheel and fell back to building from source. That
needs a C toolchain:

  macOS   xcode-select --install
  Linux   sudo apt install build-essential cmake

The setup is resumable — run this script again once that is in place.
EOF
        rm -rf "$VENV"
        exit 1
    fi

    echo
    echo "Setup complete."
    echo
fi

exec "$VENV/bin/python" "$HERE/app.py" "$@"
