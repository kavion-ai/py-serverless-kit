"""``main()``: serve, or ``--check`` (a container health check) or ``--rewrap`` (re-encrypt the file and exit)."""

from __future__ import annotations

import sys
from http.server import ThreadingHTTPServer

from .ciphers import DecryptError
from .config import AUTH, BIND, CREDENTIALS, ENV, PORT, STORE_FILE, UI_ON, VERSION, log
from .handler import Handler
from .keyring import Keyring
from .store import Store, set_store


def check() -> int:
    """0 when the server answers on ``/health``."""
    import urllib.request

    host = "127.0.0.1" if BIND in ("0.0.0.0", "") else BIND  # noqa: S104
    try:
        with urllib.request.urlopen(f"http://{host}:{PORT}/health", timeout=3) as resp:  # noqa: S310 - local health
            return 0 if resp.status == 200 else 1
    except OSError:
        return 1


def main() -> int:
    args = sys.argv[1:]
    if "--check" in args:
        return check()
    if AUTH not in ("sigv4", "off"):
        print("SM_AUTH must be sigv4 or off", file=sys.stderr)
        return 2
    if AUTH != "off" and not CREDENTIALS and "--rewrap" not in args:
        print("set SM_SECRET_ACCESS_KEY (and SM_ACCESS_KEY_ID), or SM_CREDENTIALS=id:secret, or SM_AUTH=off",
              file=sys.stderr)
        return 2
    try:
        store = Store(STORE_FILE, Keyring(ENV))
    except (ValueError, DecryptError) as exc:
        print(f"secretsmanager: {exc}", file=sys.stderr)
        return 2
    set_store(store)
    if store.stale():  # encrypt a plain file, decrypt with SM_ENCRYPTION=off, or rewrap to the current master key
        store.save()
    keyring = store.keyring
    if "--rewrap" in args:
        log(f"rewrapped {STORE_FILE} to master key {keyring.current!r}" if keyring.alg
            else f"wrote {STORE_FILE} unencrypted")
        return 0
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    server.daemon_threads = True
    log(f"Secrets Manager compatible server {VERSION} (Python) on {BIND}:{PORT}, data {STORE_FILE}, "
        f"{len(store.secrets)} secrets, auth {AUTH}" + (", console /ui/" if UI_ON else "")
        + (f", encryption {keyring.alg} (master key {keyring.current!r})" if keyring.alg else ", not encrypted"))
    if AUTH == "off":
        log("warning: SM_AUTH=off, anyone who reaches the port can read every secret")
    if not keyring.alg:
        log("warning: secrets are stored unencrypted; set SM_MASTER_KEY (openssl rand -base64 32) to encrypt them")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
