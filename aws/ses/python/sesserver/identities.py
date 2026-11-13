"""Identities (domains and addresses), their verification and DKIM, and which identity lets an address send.

Verification follows ``SES_VERIFY``:

``auto``    a new identity is verified at once (whoever has the keys decides what may be sent)
``dns``     a domain is verified when ``_amazonses.<domain>`` TXT holds its token or its DKIM record is published;
            an address when its domain (or a parent domain) is verified, or the console marks it verified
``manual``  the console marks identities verified
``off``     no identity is needed to send

A domain's DKIM key is pskit's own (2048-bit RSA, ``<selector>._domainkey.<domain>`` TXT), or one you bring
(``DkimSigningAttributes``). Mail is DKIM-signed once the record is found in DNS (``SES_DKIM_CHECK=off``: at once).
Pending records are looked up again every 10 minutes for 72 hours, as SES does.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from . import dns
from .config import ACCOUNT, DELIVERY, DKIM_CHECK, HELO_NAME, REGION, RELAY_HOST, VERIFY, log
from .errors import bad_request
from .rsa import Key
from .store import db
from .util import domain_of, is_domain, is_email, now, selector, token

PENDING_FOR = 72 * 3600
RECHECK = 600


def arn(kind: str, name: str, region: str = REGION) -> str:
    return f"arn:aws:ses:{region}:{ACCOUNT}:{kind}/{name}"


def kind_of(name: str) -> str:
    if "@" in name:
        if not is_email(name):
            raise bad_request(f"Invalid email address <{name}>.")
        return "EMAIL_ADDRESS"
    if not is_domain(name):
        raise bad_request(f"Invalid domain name <{name}>.")
    return "DOMAIN"


def normalize(name: Any) -> str:
    text = str(name or "").strip()
    if "@" in text:
        local, _at, domain = text.rpartition("@")
        return f"{local}@{domain.lower()}"
    return text.lower().rstrip(".")


def new(name: str, dkim: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    kind = kind_of(name)
    ts = now()
    rec: Dict[str, Any] = {
        "IdentityName": name, "IdentityType": kind, "CreatedTimestamp": ts,
        "VerificationStatus": "SUCCESS" if VERIFY in ("auto", "off") else "PENDING",
        "VerificationInfo": {"LastCheckedTimestamp": ts, **({"LastSuccessTimestamp": ts}
                                                           if VERIFY in ("auto", "off") else {})},
        "FeedbackForwardingStatus": True, "Tags": [], "Policies": {},
    }
    if kind == "DOMAIN":
        rec["VerificationToken"] = token()
        set_dkim(rec, dkim)
    return rec


def set_dkim(rec: Dict[str, Any], attrs: Optional[Dict[str, Any]]) -> None:
    """Generate pskit's key (``AWS_SES``) or take the caller's (``EXTERNAL``: selector and private key)."""
    attrs = attrs or {}
    origin = str(attrs.get("DomainSigningAttributesOrigin") or ("EXTERNAL" if attrs.get("DomainSigningPrivateKey")
                                                                 else "AWS_SES"))
    length = str(attrs.get("NextSigningKeyLength") or "RSA_2048_BIT")
    if origin == "EXTERNAL":
        sel = str(attrs.get("DomainSigningSelector") or "")
        if not sel or not is_domain(sel + ".x") or "." in sel:
            raise bad_request("DomainSigningSelector must be a DNS label such as 'mail2026'.")
        try:
            key = Key.load(str(attrs.get("DomainSigningPrivateKey") or ""))
        except (ValueError, IndexError) as exc:
            raise bad_request(f"DomainSigningPrivateKey is not an RSA private key in base64: {exc}") from None
        if key.bits not in (1024, 2048):
            raise bad_request("The DKIM key must be a 1024 or 2048 bit RSA key.")
        length = f"RSA_{key.bits}_BIT"
    else:
        origin, sel = "AWS_SES", selector()
        key = Key.generate(1024 if length == "RSA_1024_BIT" else 2048)
    rec["Dkim"] = {
        "SigningEnabled": True, "Status": "PENDING" if DKIM_CHECK else "SUCCESS", "Selector": sel,
        "PrivateKey": key.private_b64(), "PublicKey": key.public_b64(), "Origin": origin,
        "CurrentSigningKeyLength": length, "NextSigningKeyLength": length, "LastKeyGenerationTimestamp": now(),
    }


# ----------------------------------------------------------------------------- who may send


def domains_up(domain: str) -> List[str]:
    """``a.b.example.com`` -> itself, ``b.example.com``, ``example.com`` (not the top-level domain)."""
    parts = domain.split(".")
    return [".".join(parts[i:]) for i in range(len(parts) - 1)]


def verified(name: str) -> bool:
    """Whether the identity ``name`` (or, for an address, its domain or a parent domain) is verified."""
    if VERIFY == "off":
        return True
    store = db()
    rec = store.identities.get(name)
    if rec and rec["VerificationStatus"] == "SUCCESS":
        return True
    domain = domain_of(name) if "@" in name else name
    return any((store.identities.get(d) or {}).get("VerificationStatus") == "SUCCESS"
               for d in domains_up(domain) if d != name)


def sending_identity(addr: str) -> Optional[str]:
    """The verified identity that lets ``addr`` send: the address, its domain, or a parent domain."""
    store = db()
    rec = store.identities.get(addr)
    if rec and rec["VerificationStatus"] == "SUCCESS":
        return addr
    for d in domains_up(domain_of(addr)):
        if (store.identities.get(d) or {}).get("VerificationStatus") == "SUCCESS":
            return d
    return None


def status_of(rec: Dict[str, Any]) -> str:
    """The verification status shown for an identity (an address inherits its verified domain's)."""
    if rec["VerificationStatus"] != "SUCCESS" and rec["IdentityType"] == "EMAIL_ADDRESS" and verified(
            rec["IdentityName"]):
        return "SUCCESS"
    return str(rec["VerificationStatus"])


def dkim_signer(addr: str) -> Optional[Tuple[str, str, Key]]:
    """(domain, selector, key) to sign mail from ``addr`` with: the closest domain identity whose DKIM is verified."""
    store = db()
    for d in domains_up(domain_of(addr)):
        rec = store.identities.get(d)
        dk = (rec or {}).get("Dkim")
        if dk and dk.get("SigningEnabled") and dk.get("Status") == "SUCCESS":
            return d, dk["Selector"], Key.load(dk["PrivateKey"])
    return None


# ----------------------------------------------------------------------------- DNS checks


def check(name: str) -> Dict[str, Any]:
    """Look the domain's records up now and update the identity (verification and DKIM status)."""
    store = db()
    with store.lock:
        rec = store.identities.get(name)
        if rec is None or rec["IdentityType"] != "DOMAIN":
            return rec or {}
        token_, dk = rec.get("VerificationToken"), dict(rec.get("Dkim") or {})
    ts = now()
    found_token = found_dkim = False
    error = ""
    try:
        found_token = any(t.strip() == token_ for t in dns.txt(f"_amazonses.{name}"))
    except dns.DnsError as exc:
        error = exc.kind
    if dk:
        try:
            records = dns.txt(f"{dk['Selector']}._domainkey.{name}")
            found_dkim = any(_dkim_key_of(t) == dk["PublicKey"] for t in records)
            if not found_dkim and not error:
                error = "INVALID_VALUE" if records else "TYPE_NOT_FOUND"
        except dns.DnsError as exc:
            error = error or exc.kind
    with store.lock:
        rec = store.identities.get(name)
        if rec is None:
            return {}
        info = rec.setdefault("VerificationInfo", {})
        info["LastCheckedTimestamp"] = ts
        expired = ts - rec["CreatedTimestamp"] > PENDING_FOR
        if found_token or found_dkim:
            info["LastSuccessTimestamp"] = ts
            info.pop("ErrorType", None)
            if VERIFY == "dns" and rec["VerificationStatus"] != "SUCCESS":
                rec["VerificationStatus"] = "SUCCESS"
                log("identity verified:", name)
        elif error:
            info["ErrorType"] = error
            if VERIFY == "dns" and rec["VerificationStatus"] == "PENDING" and expired:
                rec["VerificationStatus"] = "FAILED"
        if rec.get("Dkim"):
            if found_dkim:
                if rec["Dkim"]["Status"] != "SUCCESS":
                    log("DKIM record found, signing mail from", name)
                rec["Dkim"]["Status"] = "SUCCESS"
            elif rec["Dkim"]["Status"] != "SUCCESS":
                rec["Dkim"]["Status"] = "FAILED" if expired else (
                    "TEMPORARY_FAILURE" if error == "DNS_SERVER_ERROR" else "PENDING")
        store.save()
        return rec


def _dkim_key_of(record: str) -> str:
    tags = {}
    for part in record.split(";"):
        k, _eq, v = part.strip().partition("=")
        tags[k.strip()] = "".join(v.split())
    return tags.get("p", "")


def pending() -> List[str]:
    store = db()
    with store.lock:
        return [n for n, r in store.identities.items() if r["IdentityType"] == "DOMAIN" and (
            (r.get("Dkim") or {}).get("Status") in ("PENDING", "TEMPORARY_FAILURE")
            or (VERIFY == "dns" and r["VerificationStatus"] == "PENDING"))]


def check_later(name: str) -> None:
    if DKIM_CHECK:
        threading.Thread(target=_safe_check, args=(name,), daemon=True).start()


def _safe_check(name: str) -> None:
    try:
        check(name)
    except Exception as exc:  # noqa: BLE001 - a background check must not end the thread loudly
        log("DNS check of", name, "failed:", repr(exc))


def checker_loop(stop: threading.Event) -> None:
    while not stop.wait(RECHECK):
        if not DKIM_CHECK:
            continue
        for name in pending():
            _safe_check(name)


# ----------------------------------------------------------------------------- DNS records to publish


def dns_records(rec: Dict[str, Any]) -> List[Dict[str, str]]:
    """What to add at the domain's DNS provider for this identity."""
    if rec["IdentityType"] != "DOMAIN":
        return []
    name = rec["IdentityName"]
    out = []
    dk = rec.get("Dkim")
    if dk:
        out.append({"Type": "TXT", "Name": f"{dk['Selector']}._domainkey.{name}",
                    "Value": f"v=DKIM1; k=rsa; p={dk['PublicKey']}", "Purpose": "DKIM", "Status": dk["Status"]})
    out.append({"Type": "TXT", "Name": f"_amazonses.{name}", "Value": rec.get("VerificationToken") or "",
                "Purpose": "Verification", "Status": rec["VerificationStatus"]})
    if DELIVERY == "relay":
        spf = f"v=spf1 include:<your relay provider's SPF domain> ~all  (relay: {RELAY_HOST})"
    else:
        spf = f"v=spf1 a:{HELO_NAME} ~all"
    out.append({"Type": "TXT", "Name": name, "Value": spf, "Purpose": "SPF (recommended)", "Status": ""})
    out.append({"Type": "TXT", "Name": f"_dmarc.{name}", "Value": f"v=DMARC1; p=none; rua=mailto:postmaster@{name}",
                "Purpose": "DMARC (recommended)", "Status": ""})
    mail_from = (rec.get("MailFrom") or {}).get("MailFromDomain")
    if mail_from:
        out.append({"Type": "MX", "Name": mail_from, "Value": f"10 {HELO_NAME}", "Purpose": "Custom MAIL FROM",
                    "Status": (rec.get("MailFrom") or {}).get("MailFromDomainStatus", "")})
        out.append({"Type": "TXT", "Name": mail_from, "Value": spf, "Purpose": "Custom MAIL FROM (SPF)", "Status": ""})
    return out


def set_verified(name: str, value: bool) -> Dict[str, Any]:
    store = db()
    with store.lock:
        rec = store.identities[name]
        rec["VerificationStatus"] = "SUCCESS" if value else "PENDING"
        info = rec.setdefault("VerificationInfo", {})
        info["LastCheckedTimestamp"] = now()
        if value:
            info["LastSuccessTimestamp"] = now()
        store.save()
        return rec
