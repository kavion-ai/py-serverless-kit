"""Starting the server (``main``) and the container health check (``check``)."""

from __future__ import annotations

import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any

from .config import AUTH, BIND, CREDENTIALS, DATA_DIR, PORT, UI_ON, VERSION
from .http import Handler
from .lifecycle import lifecycle_loop
from .store import Store, get_store, set_store
from .util import log


class Server(ThreadingHTTPServer):
    """One thread per connection; a client that goes away is not an error."""

    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return  # the client went away
        super().handle_error(request, client_address)


def check() -> int:
    """0 when the server answers on /-/health (``server.py --check``, a container health check)."""
    host = "127.0.0.1" if BIND in ("0.0.0.0", "") else BIND  # noqa: S104
    try:
        with urllib.request.urlopen(f"http://{host}:{PORT}/-/health", timeout=3) as resp:  # noqa: S310 - local health
            return 0 if resp.status == 200 else 1
    except OSError:
        return 1


def main() -> int:
    if "--check" in sys.argv[1:]:
        return check()
    if AUTH not in ("sigv4", "off"):
        print("S3_AUTH must be sigv4 or off", file=sys.stderr)
        return 2
    if AUTH != "off" and not CREDENTIALS:
        print(
            "set S3_SECRET_ACCESS_KEY (and S3_ACCESS_KEY_ID), or S3_CREDENTIALS=id:secret, or S3_AUTH=off",
            file=sys.stderr,
        )
        return 2
    set_store(Store(DATA_DIR))
    server = Server((BIND, PORT), Handler)
    threading.Thread(target=lifecycle_loop, name="lifecycle", daemon=True).start()
    log(
        f"S3 compatible server {VERSION} (Python) on {BIND}:{PORT}, data {DATA_DIR}, "
        f"{len(get_store().buckets)} buckets, auth {AUTH}" + (", console /ui/" if UI_ON else "")
    )
    if AUTH == "off":
        log("warning: S3_AUTH=off, anyone who reaches the port can read and change every object")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
