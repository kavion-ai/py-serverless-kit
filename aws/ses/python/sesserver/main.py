"""``main()``: serve (HTTP API + console, SMTP endpoint, delivery worker), or ``--check`` (a container health check)
or ``--smtp-password`` (print the SES SMTP password of the secret key and exit)."""

from __future__ import annotations

import sys
import threading
from http.server import ThreadingHTTPServer

from . import identities, sender
from .config import (
    AUTH,
    BIND,
    CREDENTIALS,
    DATA_DIR,
    DELIVERY,
    ENV,
    PORT,
    REGION,
    RELAY_HOST,
    SMTP_BIND,
    SMTP_ON,
    SMTP_PORT,
    UI_ON,
    VERIFY,
    VERSION,
    log,
)
from .delivery import worker
from .handler import Handler
from .store import Store, set_store


def check() -> int:
    import urllib.request

    host = "127.0.0.1" if BIND in ("0.0.0.0", "", "::") else BIND  # noqa: S104
    try:
        with urllib.request.urlopen(f"http://{host}:{PORT}/health", timeout=3) as resp:  # noqa: S310 - local health
            return 0 if resp.status == 200 else 1
    except OSError:
        return 1


def main() -> int:
    args = sys.argv[1:]
    if "--check" in args:
        return check()
    if "--smtp-password" in args:
        from .sigv4 import smtp_password

        secret = ENV.get("SES_SECRET_ACCESS_KEY") or ""
        if not secret:
            print("set SES_SECRET_ACCESS_KEY", file=sys.stderr)
            return 2
        print(smtp_password(secret, REGION))
        return 0
    if AUTH not in ("sigv4", "off"):
        print("SES_AUTH must be sigv4 or off", file=sys.stderr)
        return 2
    if AUTH != "off" and not CREDENTIALS:
        print("set SES_SECRET_ACCESS_KEY (and SES_ACCESS_KEY_ID), or SES_CREDENTIALS=id:secret, or SES_AUTH=off",
              file=sys.stderr)
        return 2
    if DELIVERY not in ("relay", "direct", "capture"):
        print("SES_DELIVERY must be relay, direct or capture", file=sys.stderr)
        return 2
    if DELIVERY == "relay" and not RELAY_HOST:
        print("SES_DELIVERY=relay needs SES_RELAY_HOST", file=sys.stderr)
        return 2
    if VERIFY not in ("auto", "dns", "manual", "off"):
        print("SES_VERIFY must be auto, dns, manual or off", file=sys.stderr)
        return 2
    try:
        store = Store()
    except (OSError, ValueError) as exc:
        print(f"ses: cannot read {DATA_DIR}: {exc}", file=sys.stderr)
        return 2
    set_store(store)
    work = worker()
    sender.on_queued(work.wake)
    work.start()
    stop = threading.Event()
    threading.Thread(target=identities.checker_loop, args=(stop,), name="ses-dns", daemon=True).start()
    for name in identities.pending():
        identities.check_later(name)
    smtp_server = None
    if SMTP_ON:
        from .smtp import serve

        try:
            smtp_server = serve(SMTP_BIND, SMTP_PORT)
        except OSError as exc:
            print(f"ses: cannot listen for SMTP on {SMTP_BIND}:{SMTP_PORT}: {exc}", file=sys.stderr)
            return 2
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    server.daemon_threads = True
    log(f"SES compatible server {VERSION} (Python) on {BIND}:{PORT}"
        + (f", SMTP {SMTP_BIND}:{SMTP_PORT}" if smtp_server else "")
        + f", data {DATA_DIR}, delivery {DELIVERY}" + (f" via {RELAY_HOST}" if DELIVERY == "relay" else "")
        + f", verify {VERIFY}, {len(store.identities)} identities, {len(store.messages)} messages, auth {AUTH}"
        + (", console /ui/" if UI_ON else ""))
    if AUTH == "off":
        log("warning: SES_AUTH=off, anyone who reaches the port can send mail")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        work.stop()
    return 0
