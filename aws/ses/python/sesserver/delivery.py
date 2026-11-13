"""The delivery worker: takes queued recipients and sends them on, in the delivery mode in effect
(``settings.effective()``: the console's *Delivery settings*, else ``SES_DELIVERY``), read again on every attempt.

``relay``    one SMTP session with ``SES_RELAY_HOST`` (STARTTLS or TLS, AUTH when a user is set) for all recipients
``direct``   per recipient domain: its MX hosts in preference order (no MX: the domain itself), port
             ``SES_DIRECT_PORT``; STARTTLS when offered (required when the configuration set's TlsPolicy is REQUIRE)
``capture``  nothing leaves the server; every recipient counts as delivered and the message stays in the console

Recipients at ``simulator.amazonses.com`` never leave either; they answer as the SES mailbox simulator does
(``success``, ``bounce``, ``ooto``, ``complaint``, ``suppressionlist``).

A 5xx answer bounces the recipient (and puts it on the suppression list when the account or configuration set
suppresses bounces). A 4xx answer or a connection failure delays it: tried again after 1, 5, 15, 30 and then every
60 minutes until ``SES_RETRY_HOURS`` (or the configuration set's MaxDeliverySeconds) have passed, then it bounces.
"""

from __future__ import annotations

import smtplib
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set, Tuple

from . import dns, events, settings
from .config import DELIVERY_THREADS, DIRECT_PORT, SIMULATOR, log
from .sender import PENDING, overall
from .store import db
from .util import domain_of, now

DELAYS = (60, 300, 900, 1800, 3600)
# recipient -> (result, SMTP response, remote IP); result is "ok", "temp" or "perm"
Results = Dict[str, Tuple[str, str, str]]


class Worker:
    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.inflight: Set[str] = set()
        self.pool = ThreadPoolExecutor(DELIVERY_THREADS, thread_name_prefix="ses-delivery")
        self.stopped = threading.Event()
        self.kicked = False  # set by wake(): a wake-up between two waits is not lost

    def wake(self) -> None:
        with self.cond:
            self.kicked = True
            self.cond.notify_all()

    def start(self) -> None:
        threading.Thread(target=self.loop, name="ses-worker", daemon=True).start()

    def stop(self) -> None:
        self.stopped.set()
        self.wake()

    def loop(self) -> None:
        last_purge = 0.0
        while not self.stopped.is_set():
            wait = 30.0
            with self.cond:
                self.kicked = False
            try:
                due, wait = self._due()
                for message_id in due:
                    self.inflight.add(message_id)
                    self.pool.submit(self._run, message_id)
                if time.time() - last_purge > 3600:
                    last_purge = time.time()
                    gone = db().purge()
                    if gone:
                        log(f"removed {gone} messages older than the retention period")
            except Exception as exc:  # noqa: BLE001 - keep the worker alive
                log("delivery worker error:", repr(exc))
            with self.cond:
                if not self.kicked:
                    self.cond.wait(timeout=max(0.05, min(wait, 30.0)))
                self.kicked = False

    def _due(self) -> Tuple[List[str], float]:
        store = db()
        ts = now()
        due, wait = [], 30.0
        with store.lock:
            for message_id, rec in store.messages.items():
                if rec.get("Status") not in PENDING or message_id in self.inflight:
                    continue
                times = [r.get("NextAttempt") or 0 for r in rec["Recipients"].values()
                         if r["Status"] in ("QUEUED", "DELAYED")]
                if not times:
                    continue
                first = min(times)
                if first <= ts:
                    due.append(message_id)
                else:
                    wait = min(wait, first - ts)
        return due, wait

    def _run(self, message_id: str) -> None:
        try:
            deliver(message_id)
        except Exception as exc:  # noqa: BLE001 - a broken message must not stop the others
            log("delivery of", message_id, "failed:", repr(exc))
        finally:
            self.inflight.discard(message_id)
            self.wake()


def deliver(message_id: str) -> None:
    store = db()
    ts = now()
    with store.lock:
        rec = store.messages.get(message_id)
        if rec is None:
            return
        due = [r for r, st in rec["Recipients"].items()
               if st["Status"] in ("QUEUED", "DELAYED") and (st.get("NextAttempt") or 0) <= ts]
        mail_from, tls_policy = rec.get("MailFrom") or rec["From"], rec.get("TlsPolicy") or "OPTIONAL"
    if not due:
        return
    raw = store.raw(message_id)
    conf = settings.effective()  # the mode now: switching it applies to queued and delayed mail too
    mode = conf["Mode"]
    results: Results = {}
    simulated = [r for r in due if domain_of(r) == SIMULATOR]
    real = [r for r in due if domain_of(r) != SIMULATOR]
    complaints = []
    for r in simulated:
        box = r.split("@")[0].lower()
        if box == "bounce":
            results[r] = ("perm", "550 5.1.1 user unknown (mailbox simulator)", "")
        elif box == "suppressionlist":
            results[r] = ("suppressed", "550 5.1.1 recipient is on the suppression list (mailbox simulator)", "")
        else:
            results[r] = ("ok", "250 2.6.0 Message received (mailbox simulator)", "")
            if box == "complaint":
                complaints.append(r)
    if real:
        if mode == "capture":
            for r in real:
                results[r] = ("ok", "250 2.0.0 Captured: kept on the server, not sent (delivery mode: capture)", "")
        elif mode == "relay":
            results.update(_relay(real, mail_from, raw, tls_policy, conf))
        else:
            for domain in sorted({domain_of(r) for r in real}):
                results.update(_direct(domain, [r for r in real if domain_of(r) == domain], mail_from, raw,
                                       tls_policy, conf["HeloName"]))
    _record(message_id, results, complaints)


def _record(message_id: str, results: Results, complaints: List[str]) -> None:
    store = db()
    ts = now()
    with store.lock:
        rec = store.messages.get(message_id)
        if rec is None:
            return
        cs = store.configuration_sets.get(rec.get("ConfigurationSetName") or "") or {}
        reasons = cs.get("SuppressedReasons")
        if reasons is None:
            reasons = store.account.get("SuppressedReasons") or []
        groups: Dict[Tuple[str, str], List[str]] = {}
        for rcpt, (result, response, ip) in results.items():
            st = rec["Recipients"][rcpt]
            st["Attempts"] = st.get("Attempts", 0) + (0 if result == "suppressed" else 1)
            st["LastAttempt"] = ts
            st["Response"] = response
            if ip:
                st["RemoteMtaIp"] = ip
            if result == "ok":
                st["Status"] = "DELIVERED"
                st.pop("NextAttempt", None)
                groups.setdefault(("Delivery", response + "\0" + ip), []).append(rcpt)
            elif result in ("perm", "suppressed"):
                st["Status"] = "BOUNCED"
                st.pop("NextAttempt", None)
                groups.setdefault(("Bounce" if result == "perm" else "Suppressed", response), []).append(rcpt)
                if result == "perm" and "BOUNCE" in reasons and domain_of(rcpt) != SIMULATOR:
                    store.suppressed[rcpt.lower()] = {"EmailAddress": rcpt, "Reason": "BOUNCE",
                                                      "LastUpdateTime": ts, "MessageId": message_id,
                                                      "FeedbackId": message_id}
            else:
                attempts = st["Attempts"]
                retry_at = ts + DELAYS[min(attempts - 1, len(DELAYS) - 1)]
                if retry_at > rec.get("Deadline", retry_at):
                    st["Status"] = "BOUNCED"
                    st.pop("NextAttempt", None)
                    groups.setdefault(("Expired", response), []).append(rcpt)
                else:
                    st["Status"] = "DELAYED"
                    st["NextAttempt"] = retry_at
                    groups.setdefault(("DeliveryDelay", response), []).append(rcpt)
        for (kind, key), rcpts in sorted(groups.items()):
            response = key.split("\0")[0]
            status = _enhanced(response)
            if kind == "Delivery":
                events.add(rec, "Delivery", rcpts, SmtpResponse=response, RemoteMtaIp=key.split("\0")[1])
            elif kind == "Bounce":
                events.add(rec, "Bounce", rcpts, BounceType="Permanent", BounceSubType="General",
                           Status=status or "5.0.0", DiagnosticCode=f"smtp; {response}")
            elif kind == "Suppressed":
                events.add(rec, "Bounce", rcpts, BounceType="Permanent", BounceSubType="OnAccountSuppressionList",
                           Status="5.1.1", DiagnosticCode=response)
            elif kind == "Expired":
                events.add(rec, "Bounce", rcpts, BounceType="Undetermined", BounceSubType="Undetermined",
                           Status=status or "4.4.7", DiagnosticCode=f"Delivery expired: {response}")
            else:
                events.add(rec, "DeliveryDelay", rcpts, DelayType="TransientCommunicationFailure",
                           Status=status or "4.0.0", DiagnosticCode=response, ExpirationTime=rec.get("Deadline"))
        for rcpt in complaints:
            events.add(rec, "Complaint", [rcpt], FeedbackType="abuse")
        rec["Status"] = overall(rec)
        store.save_message(rec)
        if any(r[0] == "perm" for r in results.values()):
            store.save()


def _enhanced(response: str) -> str:
    parts = response.split()
    if len(parts) > 1 and parts[1].count(".") == 2 and parts[1].replace(".", "").isdigit():
        return parts[1]
    return ""


# ----------------------------------------------------------------------------- SMTP


class _HostFailed(Exception):
    """The host could not take the message (connection, TLS, greeting): try the next MX or retry later."""


def _context(verify: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _text(code: int, msg: Any) -> str:
    text = msg.decode("utf-8", "replace") if isinstance(msg, bytes) else str(msg)
    return f"{code} {' '.join(text.split())}".strip()


def _session(host: str, port: int, rcpts: List[str], mail_from: str, raw: bytes, *, tls: str, require_tls: bool,
             verify: bool, helo: str, user: str = "", password: str = "") -> Results:
    """One SMTP session. ``tls``: ``tls`` (implicit), ``starttls`` (when offered, required if ``require_tls``)
    or ``none``."""
    results: Results = {}
    try:
        if tls == "tls":
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, local_hostname=helo, timeout=60,
                                                  context=_context(verify))
        else:
            smtp = smtplib.SMTP(host, port, local_hostname=helo, timeout=60)
    except (OSError, smtplib.SMTPException) as exc:
        raise _HostFailed(f"421 4.4.1 Connection to {host}:{port} failed: {exc}") from None
    try:
        ip = ""
        try:
            ip = str(smtp.sock.getpeername()[0]) if smtp.sock else ""
        except OSError:
            pass
        smtp.ehlo()
        if tls in ("starttls", "opportunistic"):
            if smtp.has_extn("starttls"):
                try:
                    smtp.starttls(context=_context(verify))
                    smtp.ehlo()
                except (ssl.SSLError, smtplib.SMTPException):
                    if require_tls or tls == "starttls":
                        raise
                    smtp.close()  # opportunistic TLS failed: deliver in plain text, as MTAs do
                    return _session(host, port, rcpts, mail_from, raw, tls="none", require_tls=False, verify=False,
                                    helo=helo)
            elif require_tls:
                raise _HostFailed(f"421 4.7.10 {host} does not offer STARTTLS, which is required")
        if user:
            try:
                smtp.login(user, password)
            except smtplib.SMTPAuthenticationError as exc:
                raise _HostFailed(_text(exc.smtp_code, exc.smtp_error) + " (check the relay user and password)") \
                    from None
        code, msg = smtp.mail(mail_from)
        if code >= 400:
            kind = "perm" if code >= 500 else "temp"
            return {r: (kind, _text(code, msg), ip) for r in rcpts}
        accepted = []
        for r in rcpts:
            code, msg = smtp.rcpt(r)
            if code in (250, 251, 252):
                accepted.append(r)
            else:
                results[r] = ("perm" if code >= 500 else "temp", _text(code, msg), ip)
        if accepted:
            try:
                code, msg = smtp.data(raw)
            except smtplib.SMTPDataError as exc:
                code, msg = exc.smtp_code, exc.smtp_error
            kind = "ok" if code == 250 else ("perm" if code >= 500 else "temp")
            for r in accepted:
                results[r] = (kind, _text(code, msg), ip)
        try:
            smtp.quit()
        except (OSError, smtplib.SMTPException):
            pass
        return results
    except (OSError, smtplib.SMTPException, ssl.SSLError) as exc:
        if isinstance(exc, smtplib.SMTPResponseException) and exc.smtp_code >= 500:
            return {**{r: ("perm", _text(exc.smtp_code, exc.smtp_error), "") for r in rcpts}, **results}
        raise _HostFailed(f"421 4.4.2 {host}: {exc}") from None
    finally:
        try:
            smtp.close()
        except OSError:
            pass


def _relay(rcpts: List[str], mail_from: str, raw: bytes, tls_policy: str, conf: Dict[str, Any]) -> Results:
    tls, user = str(conf["RelayTls"]), str(conf["RelayUser"])
    try:
        return _session(str(conf["RelayHost"]), int(conf["RelayPort"]), rcpts, mail_from, raw, tls=tls,
                        require_tls=tls_policy == "REQUIRE" or (tls == "starttls" and bool(user)),
                        verify=bool(conf["RelayTlsVerify"]), helo=str(conf["HeloName"]), user=user,
                        password=str(conf["RelayPassword"]))
    except _HostFailed as exc:
        return {r: ("temp", str(exc), "") for r in rcpts}


def _direct(domain: str, rcpts: List[str], mail_from: str, raw: bytes, tls_policy: str, helo: str) -> Results:
    try:
        hosts = [h for _p, h in dns.mx(domain)]
    except dns.DnsError as exc:
        if exc.kind == "HOST_NOT_FOUND":
            return {r: ("perm", f"550 5.1.2 Host or domain name not found: {domain}", "") for r in rcpts}
        if exc.kind == "TYPE_NOT_FOUND":
            return {r: ("perm", f"556 5.1.10 {domain} does not accept mail (null MX)", "") for r in rcpts}
        return {r: ("temp", f"451 4.4.3 DNS lookup of {domain} failed: {exc}", "") for r in rcpts}
    last = f"451 4.4.1 No MX host of {domain} answered"
    for host in hosts[:5]:
        try:
            return _session(host, DIRECT_PORT, rcpts, mail_from, raw, tls="opportunistic",
                            require_tls=tls_policy == "REQUIRE", verify=False, helo=helo)
        except _HostFailed as exc:
            last = str(exc)
    return {r: ("temp", last, "") for r in rcpts}


_WORKER: Optional[Worker] = None


def worker() -> Worker:
    global _WORKER
    if _WORKER is None:
        _WORKER = Worker()
    return _WORKER


def test_connection(conf: Dict[str, Any], domain: str = "gmail.com") -> Dict[str, Any]:
    """Try the settings without sending anything: log in to the relay (TLS, AUTH), or reach an MX host of ``domain``
    on the direct port. ``{"Ok": bool, "Message": str, "Steps": [str]}``."""
    steps: List[str] = []
    mode = conf["Mode"]
    if mode == "capture":
        return {"Ok": True, "Message": "Capture mode sends nothing, so there is no connection to test.", "Steps": []}
    if mode == "relay":
        host, port, tls, user = str(conf["RelayHost"]), int(conf["RelayPort"]), str(conf["RelayTls"]), \
            str(conf["RelayUser"])
        targets = [host]
    else:
        host, port, tls, user = "", DIRECT_PORT, "opportunistic", ""
        try:
            targets = [h for _p, h in dns.mx(domain)][:3]
            steps.append(f"MX of {domain}: {', '.join(targets)}")
        except dns.DnsError as exc:
            return {"Ok": False, "Message": f"DNS lookup of the MX hosts of {domain} failed: {exc}", "Steps": steps}
    last = ""
    for target in targets:
        try:
            if tls == "tls":
                smtp: smtplib.SMTP = smtplib.SMTP_SSL(target, port, local_hostname=str(conf["HeloName"]),
                                                      timeout=15, context=_context(bool(conf["RelayTlsVerify"])))
            else:
                smtp = smtplib.SMTP(target, port, local_hostname=str(conf["HeloName"]), timeout=15)
        except (OSError, smtplib.SMTPException) as exc:
            last = f"Cannot connect to {target}:{port}: {exc}"
            if mode == "direct":
                last += " (is outbound port 25 blocked? Most clouds block it: use a relay, or ask them to open it)"
            steps.append(last)
            continue
        try:
            code, banner = smtp.ehlo()
            steps.append(f"Connected to {target}:{port}" + (" over TLS" if tls == "tls" else "") +
                         f": {_text(code, banner).splitlines()[0][:120]}")
            if tls in ("starttls", "opportunistic") and smtp.has_extn("starttls"):
                smtp.starttls(context=_context(mode == "relay" and bool(conf["RelayTlsVerify"])))
                smtp.ehlo()
                steps.append("STARTTLS: encrypted")
            elif tls == "starttls":
                return {"Ok": False, "Message": f"{target} does not offer STARTTLS. Pick TLS (port 465) or none.",
                        "Steps": steps}
            if user:
                smtp.login(user, str(conf["RelayPassword"]))
                steps.append(f"Logged in as {user}")
            smtp.quit()
            done = "Relay works: mail will be sent through it." if mode == "relay" else \
                f"Direct delivery works: {target} accepted the connection on port {port}."
            return {"Ok": True, "Message": done, "Steps": steps}
        except smtplib.SMTPAuthenticationError as exc:
            return {"Ok": False, "Message": f"Login refused: {_text(exc.smtp_code, exc.smtp_error)}", "Steps": steps}
        except (OSError, smtplib.SMTPException, ssl.SSLError) as exc:
            last = f"{target}: {exc}"
            steps.append(last)
        finally:
            try:
                smtp.close()
            except OSError:
                pass
    return {"Ok": False, "Message": last or "No server answered.", "Steps": steps}
