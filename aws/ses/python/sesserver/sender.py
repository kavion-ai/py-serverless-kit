"""Accepting a message: every check SES makes before it answers with a MessageId, then the queue.

Checks, in order: account and configuration set sending enabled, the From address is a verified identity (unless
``SES_VERIFY=off``), recipients (1 to 50; verified ones only in the sandbox), size, the daily quota and the
sending rate. Then the message is built, DKIM-signed for the From domain when its DKIM is verified, recipients on the
suppression list are dropped (a ``Bounce`` event with subtype ``OnAccountSuppressionList``), and the rest is queued
for the delivery worker.
"""

from __future__ import annotations

import collections
import re
import threading
import time
from typing import Any, Callable, Deque, Dict, List, Optional

from . import dkim, events, identities, mime
from .config import DELIVERY, MAX_24H, MAX_MESSAGE, MAX_RATE, MAX_RECIPIENTS, RETRY_HOURS, SANDBOX, SIMULATOR, VERIFY
from .errors import ApiError, bad_request, not_found, rejected
from .store import db
from .util import address, domain_of, message_id, now

_TAG = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_sent: Deque[float] = collections.deque()
_rate_lock = threading.Lock()
_wake: Optional[Callable[[], None]] = None

PENDING = ("QUEUED", "DELAYED", "SENDING")


def on_queued(callback: Callable[[], None]) -> None:
    global _wake
    _wake = callback


def sent_last_24h() -> int:
    since = time.time() - 86400
    return sum(len(r.get("Destinations") or []) for r in db().recent(since))


def _check_rate(count: int) -> None:
    if sent_last_24h() + count > MAX_24H:
        raise ApiError("LimitExceededException", "Daily message quota exceeded.", 400, "Throttling")
    with _rate_lock:
        cutoff = time.time() - 1.0
        while _sent and _sent[0] < cutoff:
            _sent.popleft()
        if len(_sent) + count > max(MAX_RATE, count):
            raise ApiError("TooManyRequestsException", "Maximum sending rate exceeded.", 429, "Throttling")
        _sent.extend([time.time()] * count)


def _tags(tags: Any) -> List[Dict[str, str]]:
    out = []
    for tag in tags or []:
        name, value = str(tag.get("Name") or ""), str(tag.get("Value") or "")
        if not _TAG.match(name) or not _TAG.match(value):
            raise bad_request("Message tag names and values may contain only ASCII letters, digits, '_' and '-'.")
        out.append({"Name": name, "Value": value})
    return out


def configuration_set(name: str) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    cs = db().configuration_sets.get(name)
    if cs is None:
        raise not_found(f"Configuration set <{name}> does not exist.", "ConfigurationSetDoesNotExist")
    return cs


def check_sender(source: str) -> str:
    """The bare From address; refused unless it may send (account enabled, verified identity)."""
    if not db().account.get("SendingEnabled", True):
        raise ApiError("SendingPausedException", "Sending is paused for this account.", 400,
                       "AccountSendingPausedException")
    addr = address(source)
    if not addr:
        raise bad_request(f"Illegal address: {source!r}.") if source else bad_request("Missing final '@domain'")
    if VERIFY != "off" and identities.sending_identity(addr) is None:
        raise rejected("Email address is not verified. The following identities failed the check in region "
                       f"{_region()}: {addr}")
    return addr


def _region() -> str:
    from .config import REGION

    return REGION.upper()


def accept(*, operation: str, caller: str, source_ip: str, source: str, to: List[str], cc: List[str],
           bcc: List[str], envelope: Optional[List[str]], build: Callable[[str, float], bytes], return_path: str = "",
           configuration_set_name: str = "", tags: Any = None) -> str:
    store = db()
    cs = configuration_set(configuration_set_name)
    if cs is not None and not cs.get("SendingEnabled", True):
        raise ApiError("SendingPausedException", f"Sending is paused for configuration set <{cs['Name']}>.", 400,
                       "ConfigurationSetSendingPausedException")
    sender = check_sender(source)
    recipients: List[str] = []
    for addr in (envelope if envelope else to + cc + bcc):
        if addr.lower() not in {r.lower() for r in recipients}:
            recipients.append(addr)
    if not recipients:
        raise bad_request("Missing required header 'To'.") if envelope is None else rejected("No recipients.")
    if len(recipients) > MAX_RECIPIENTS:
        raise rejected(f"Recipient count exceeds {MAX_RECIPIENTS}.")
    if SANDBOX:
        unverified = [r for r in recipients if domain_of(r) != SIMULATOR and not identities.verified(r)]
        if unverified:
            raise rejected("Email address is not verified. The following identities failed the check in region "
                           f"{_region()}: {', '.join(unverified)}")
    message_tags = _tags(tags)
    _check_rate(len(recipients))
    ident = message_id()
    ts = now()
    raw = build(f"<{ident}@{domain_of(sender)}>", ts)
    if len(raw) > MAX_MESSAGE:
        raise rejected(f"Message length is more than {MAX_MESSAGE // (1024 * 1024)} MB.")
    signer = identities.dkim_signer(sender)
    if signer:
        raw = dkim.sign(raw, signer[0], signer[1], signer[2])
    with store.lock:
        sending_id = identities.sending_identity(sender) or sender
        mail_from = return_path and address(return_path)
        if not mail_from:
            mf = (store.identities.get(sending_id) or {}).get("MailFrom") or {}
            mail_from = (f"bounce@{mf['MailFromDomain']}" if mf.get("MailFromDomainStatus") == "SUCCESS"
                         else sender)
        reasons = (cs or {}).get("SuppressedReasons")
        if reasons is None:
            reasons = store.account.get("SuppressedReasons") or []
        heads = mime.summary(raw)
        deadline = ts + min(RETRY_HOURS * 3600, float((cs or {}).get("MaxDeliverySeconds") or 1e12))
        rec: Dict[str, Any] = {
            "MessageId": ident, "Timestamp": ts, "Operation": operation, "Caller": caller, "SourceIp": source_ip,
            "Source": source, "From": sender, "FromDomain": domain_of(sender),
            "SourceArn": identities.arn("identity", sending_id), "MailFrom": mail_from,
            "Destinations": recipients, "Subject": str(heads["commonHeaders"].get("subject") or ""),
            "ConfigurationSetName": configuration_set_name or "", "Tags": message_tags, "Size": len(raw),
            "DkimDomain": signer[0] if signer else "", "Headers": heads["headers"],
            "CommonHeaders": heads["commonHeaders"], "HeadersTruncated": heads["headersTruncated"],
            "Delivery": DELIVERY, "TlsPolicy": (cs or {}).get("TlsPolicy") or "OPTIONAL", "Deadline": deadline,
            "Recipients": {}, "Events": [],
        }
        suppressed = []
        for r in recipients:
            entry = store.suppressed.get(r.lower())
            if entry and entry.get("Reason") in reasons and domain_of(r) != SIMULATOR:
                rec["Recipients"][r] = {"Status": "SUPPRESSED", "Attempts": 0,
                                        "Response": "Recipient is on the account-level suppression list"}
                suppressed.append(r)
            else:
                rec["Recipients"][r] = {"Status": "QUEUED", "Attempts": 0, "NextAttempt": ts, "Response": ""}
        events.add(rec, "Send", recipients)
        if suppressed:
            events.add(rec, "Bounce", suppressed, BounceType="Permanent", BounceSubType="OnAccountSuppressionList",
                       Status="5.1.1", DiagnosticCode="Amazon SES did not send the message to this address because "
                       "it is on the suppression list for your account.")
        rec["Status"] = overall(rec)
        store.save_message(rec, raw)
    if _wake:
        _wake()
    return ident


def overall(rec: Dict[str, Any]) -> str:
    states = [r["Status"] for r in rec["Recipients"].values()]
    if any(s == "SENDING" for s in states):
        return "SENDING"
    if any(s == "QUEUED" for s in states):
        return "QUEUED"
    if any(s == "DELAYED" for s in states):
        return "DELAYED"
    if states and all(s == "DELIVERED" for s in states):
        return "DELIVERED"
    if states and all(s in ("BOUNCED", "SUPPRESSED") for s in states):
        return "BOUNCED"
    return "PARTIAL"


def raw_build(raw: bytes) -> Callable[[str, float], bytes]:
    return lambda mid, ts: mime.prepare_raw(raw, mid, ts)
