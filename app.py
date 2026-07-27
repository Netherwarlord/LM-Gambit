#!/usr/bin/env python3
"""LM-Gambit desktop entrypoint.

Starts the FastAPI backend, serves the compiled React interface from the same
origin and opens a browser at it:

    python app.py

For frontend development run the Vite dev server alongside it instead:

    python app.py --no-browser        # terminal 1
    cd web && npm run dev             # terminal 2  -> http://localhost:5173
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DEFAULT_PORT = 8765
WEB_DIST = ROOT_DIR / "web" / "dist"


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def find_port(host: str, preferred: int) -> int:
    for candidate in range(preferred, preferred + 20):
        if port_is_free(host, candidate):
            return candidate
    raise SystemExit(
        f"No free port found between {preferred} and {preferred + 19}. "
        "Pass --port to choose one explicitly."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="app.py",
        description="Run the LM-Gambit web interface.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: 127.0.0.1)")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to serve on (default: {DEFAULT_PORT}; the next free one is used if taken)",
    )
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on Python changes (dev)")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print(
            "FastAPI/uvicorn are not installed.\n"
            "  python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    port = args.port if port_is_free(args.host, args.port) else find_port(args.host, args.port)
    url = f"http://{'localhost' if args.host in {'127.0.0.1', '0.0.0.0'} else args.host}:{port}"

    if not (WEB_DIST / "index.html").is_file():
        print(
            "The web interface has not been built yet.\n"
            "  cd web && npm install && npm run build\n"
            f"Starting the API anyway — docs at {url}/api/docs\n",
            file=sys.stderr,
        )
    elif not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    print(f"\n  LM-Gambit  ->  {url}\n  Press Ctrl+C to stop.\n")

    uvicorn.run(
        "server.main:app" if args.reload else _build_app(),
        host=args.host,
        port=port,
        reload=args.reload,
        log_level="info",
        access_log=False,
    )
    return 0


def _build_app():
    from server.main import create_app

    return create_app()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
