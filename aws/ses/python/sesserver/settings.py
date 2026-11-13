"""The delivery settings in effect: what the console saved (``ses.json``, key ``delivery``) over the environment.

The environment (``SES_DELIVERY``, ``SES_RELAY_*``, ``SES_HELO_NAME``) gives the defaults the server starts with. The
console's *Delivery settings* page saves a mode (``capture``, ``relay`` or ``direct``) with the relay and HELO
settings; they take effect at once (the next delivery attempt, queued and delayed mail included) and survive restarts
until the console resets them. The relay password is stored (mode 600, like the DKIM keys) and never sent back.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from .config import (
    DELIVERY,
    HELO_NAME,
    RELAY_HOST,
    RELAY_PASSWORD,
    RELAY_PORT,
    RELAY_TLS,
    RELAY_TLS_VERIFY,
    RELAY_USER,
)
from .errors import bad_request
from .store import db

MODES = ("capture", "relay", "direct")
TLS = ("starttls", "tls", "none")
_HOST = re.compile(r"^(?!-)[A-Za-z0-9.-]{1,253}$|^\[?[0-9A-Fa-f:.]{2,45}\]?$")
_HELO = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(\.(?!-)[A-Za-z0-9-]{1,63})*$")


def environment() -> Dict[str, Any]:
    return {"Mode": DELIVERY, "RelayHost": RELAY_HOST, "RelayPort": RELAY_PORT, "RelayUser": RELAY_USER,
            "RelayPassword": RELAY_PASSWORD, "RelayTls": RELAY_TLS, "RelayTlsVerify": RELAY_TLS_VERIFY,
            "HeloName": HELO_NAME}


def effective() -> Dict[str, Any]:
    """The settings delivery uses now, with ``Source``: ``console`` or ``environment``."""
    saved = db().delivery
    if not saved:
        return {**environment(), "Source": "environment"}
    return {**environment(), **saved, "Source": "console"}


def public(values: Dict[str, Any]) -> Dict[str, Any]:
    """The settings for the console: everything but the relay password (only whether one is set)."""
    out = {k: v for k, v in values.items() if k != "RelayPassword"}
    out["RelayPasswordSet"] = bool(values.get("RelayPassword"))
    return out


def check(params: Dict[str, Any]) -> Dict[str, Any]:
    """Validated settings from the console. An omitted ``RelayPassword`` keeps the one in effect (when the relay host
    and user stay the same)."""
    mode = str(params.get("Mode") or "").lower()
    if mode not in MODES:
        raise bad_request("Mode must be capture, relay or direct.")
    current = effective()
    helo = str(params.get("HeloName") or current["HeloName"] or "").strip().lower().rstrip(".")
    if not _HELO.match(helo):
        raise bad_request("HeloName must be a host name such as mail.example.com.")
    out: Dict[str, Any] = {"Mode": mode, "HeloName": helo}
    if mode == "relay":
        host = str(params.get("RelayHost") or "").strip()
        if not host or not _HOST.match(host):
            raise bad_request("RelayHost must be the relay's host name or IP address, e.g. smtp.office365.com.")
        try:
            port = int(params.get("RelayPort") or 587)
        except (TypeError, ValueError):
            raise bad_request("RelayPort must be a number.") from None
        if not 1 <= port <= 65535:
            raise bad_request("RelayPort must be between 1 and 65535.")
        tls = str(params.get("RelayTls") or ("tls" if port == 465 else "starttls")).lower()
        if tls not in TLS:
            raise bad_request("RelayTls must be starttls, tls or none.")
        user = str(params.get("RelayUser") or "").strip()
        password = params.get("RelayPassword")
        if password is None:
            same = current.get("RelayHost") == host and current.get("RelayUser") == user
            password = current.get("RelayPassword") if same else ""
        password = str(password or "")
        if user and not password:
            raise bad_request("RelayPassword is required with RelayUser.")
        if user and tls == "none":
            raise bad_request("A relay login needs TLS (starttls or tls): the password would cross the network in "
                              "plain text.")
        verify = params.get("RelayTlsVerify")
        out.update(RelayHost=host, RelayPort=port, RelayTls=tls, RelayUser=user, RelayPassword=password,
                   RelayTlsVerify=True if verify is None else bool(verify))
    return out


def save(values: Dict[str, Any]) -> None:
    store = db()
    with store.lock:
        store.delivery = dict(values)
        store.save()


def reset() -> None:
    save({})
