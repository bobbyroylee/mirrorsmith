#!/usr/bin/env python3
"""Launch the mirrorsmith local web UI.

    python scripts/serve.py            # http://127.0.0.1:8770, opens browser
    python scripts/serve.py --port 9000 --no-open

Binds to localhost only — it reads your local POESESSID; never expose it.
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mirrorsmith.webapp import Handler  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = ap.parse_args()

    url = f"http://127.0.0.1:{args.port}/"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"mirrorsmith UI  →  {url}   (Ctrl+C to stop)")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
