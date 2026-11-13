"""Message events: kept in the message record (``Events``) and, when ``SES_EVENTS_URL`` is set, POSTed there as JSON
in the SES event publishing format (``eventType``, ``mail``, ``delivery`` / ``bounce`` / ``complaint`` / ...), as
an SES configuration set sends them to SNS or EventBridge.

Event types: ``Send``, ``Reject``, ``Delivery``, ``Bounce``, ``Complaint``, ``DeliveryDelay``.
"""

from __future__ import annotations

import json
import queue
import threading
import urllib.request
from typing import Any, Dict, List, Optional

from .config import ACCOUNT, EVENTS_TOKEN, EVENTS_URL, HELO_NAME, REGION, log
from .util import iso, now

_QUEUE: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=10000)
_started = False
_lock = threading.Lock()


def add(rec: Dict[str, Any], kind: str, recipients: List[str], **detail: Any) -> Dict[str, Any]:
    """Append an event to the message record (the caller saves it) and queue it for the webhook."""
    event = {"Type": kind, "Timestamp": now(), "Recipients": list(recipients), **detail}
    rec.setdefault("Events", []).append(event)
    if EVENTS_URL and _wanted(rec, kind):
        _start()
        try:
            _QUEUE.put_nowait(publish_format(rec, event))
        except queue.Full:
            log("events: queue full, dropped a", kind, "event of", rec["MessageId"])
    return event


def _wanted(rec: Dict[str, Any], kind: str) -> bool:
    """Every event, or only the types the configuration set's enabled event destinations match."""
    from .store import db

    name = rec.get("ConfigurationSetName")
    if not name:
        return True
    cs = db().configuration_sets.get(name) or {}
    dests = [d for d in (cs.get("EventDestinations") or {}).values() if d.get("Enabled", True)]
    if not dests:
        return True
    wanted = {t.upper() for d in dests for t in d.get("MatchingEventTypes") or []}
    return {"DeliveryDelay": "DELIVERY_DELAY"}.get(kind, kind.upper()) in wanted


def publish_format(rec: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    tags: Dict[str, List[str]] = {"ses:operation": [rec.get("Operation") or "SendEmail"],
                                  "ses:source-ip": [rec.get("SourceIp") or ""],
                                  "ses:from-domain": [rec.get("FromDomain") or ""],
                                  "ses:caller-identity": [rec.get("Caller") or ""]}
    if rec.get("ConfigurationSetName"):
        tags["ses:configuration-set"] = [rec["ConfigurationSetName"]]
    for tag in rec.get("Tags") or []:
        tags.setdefault(tag["Name"], []).append(tag["Value"])
    mail = {
        "timestamp": iso(rec["Timestamp"]), "source": rec.get("Source") or "", "sourceArn": rec.get("SourceArn") or "",
        "sendingAccountId": ACCOUNT, "messageId": rec["MessageId"], "destination": rec.get("Destinations") or [],
        "headersTruncated": rec.get("HeadersTruncated", False), "headers": rec.get("Headers") or [],
        "commonHeaders": rec.get("CommonHeaders") or {}, "tags": tags,
    }
    kind, ts, rcpts = event["Type"], iso(event["Timestamp"]), event["Recipients"]
    out: Dict[str, Any] = {"eventType": kind, "mail": mail}
    if kind == "Send":
        out["send"] = {}
    elif kind == "Reject":
        out["reject"] = {"reason": event.get("Reason") or "Bad content"}
    elif kind == "Delivery":
        out["delivery"] = {"timestamp": ts, "processingTimeMillis": int((event["Timestamp"] - rec["Timestamp"]) * 1000),
                           "recipients": rcpts, "smtpResponse": event.get("SmtpResponse") or "",
                           "reportingMTA": HELO_NAME, "remoteMtaIp": event.get("RemoteMtaIp") or ""}
    elif kind == "Bounce":
        out["bounce"] = {"bounceType": event.get("BounceType") or "Permanent",
                         "bounceSubType": event.get("BounceSubType") or "General",
                         "bouncedRecipients": [{"emailAddress": r, "action": "failed",
                                                "status": event.get("Status") or "5.0.0",
                                                "diagnosticCode": event.get("DiagnosticCode") or ""} for r in rcpts],
                         "timestamp": ts, "feedbackId": event.get("FeedbackId") or rec["MessageId"],
                         "reportingMTA": f"dsn; {HELO_NAME}"}
    elif kind == "Complaint":
        out["complaint"] = {"complainedRecipients": [{"emailAddress": r} for r in rcpts], "timestamp": ts,
                            "feedbackId": event.get("FeedbackId") or rec["MessageId"],
                            "complaintFeedbackType": event.get("FeedbackType") or "abuse"}
    elif kind == "DeliveryDelay":
        out["deliveryDelay"] = {"timestamp": ts, "delayType": event.get("DelayType") or "TransientCommunicationFailure",
                                "expirationTime": iso(event.get("ExpirationTime") or event["Timestamp"]),
                                "delayedRecipients": [{"emailAddress": r, "status": event.get("Status") or "4.0.0",
                                                       "diagnosticCode": event.get("DiagnosticCode") or ""}
                                                      for r in rcpts]}
    return out


def _start() -> None:
    global _started
    with _lock:
        if not _started:
            threading.Thread(target=_post_loop, name="ses-events", daemon=True).start()
            _started = True


def _post_loop() -> None:
    while True:
        payload = _QUEUE.get()
        _post(payload)


def _post(payload: Dict[str, Any], tries: int = 3) -> Optional[int]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": f"pskit-ses ({REGION})"}
    if EVENTS_TOKEN:
        headers["Authorization"] = f"Bearer {EVENTS_TOKEN}"
    for attempt in range(tries):
        req = urllib.request.Request(EVENTS_URL, data=body, headers=headers, method="POST")  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - the operator's URL
                return resp.status
        except OSError as exc:
            if attempt == tries - 1:
                log("events: POST to SES_EVENTS_URL failed:", exc)
            else:
                threading.Event().wait(2 ** attempt)
    return None
