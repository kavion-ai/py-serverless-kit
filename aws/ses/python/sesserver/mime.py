"""Messages: build one from simple content (subject, text, HTML, headers, attachments), and read a raw one (its
envelope, its headers, and for the console its text, HTML and attachments)."""

from __future__ import annotations

import base64
import binascii
import email
import email.policy
import email.utils
from email.message import EmailMessage, Message
from typing import Any, Dict, List, Optional, Tuple

from .dkim import crlf, header_fields, split
from .errors import bad_request

# Headers SES does not let a caller set in Simple.Headers (it sets them itself).
_RESERVED = {"from", "to", "cc", "bcc", "subject", "reply-to", "return-path", "date", "message-id", "mime-version",
             "content-type", "content-transfer-encoding", "dkim-signature", "received", "sender"}


def _content(part: Any) -> Tuple[str, str]:
    """(data, charset) of an SES ``Content`` (``{"Data", "Charset"}``)."""
    if not isinstance(part, dict):
        return "", "UTF-8"
    return str(part.get("Data") or ""), str(part.get("Charset") or "UTF-8")


def build(*, source: str, to: List[str], cc: List[str], reply_to: List[str], subject: str, text: Optional[str],
          html: Optional[str], charset: str = "UTF-8", headers: Optional[List[Dict[str, Any]]] = None,
          attachments: Optional[List[Dict[str, Any]]] = None, message_id: str = "", date: float = 0.0) -> bytes:
    # cte_type 7bit: non-ASCII bodies go out quoted-printable or base64, so no server needs 8BITMIME.
    msg = EmailMessage(policy=email.policy.SMTP.clone(cte_type="7bit"))
    msg["From"] = source
    if to:
        msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if reply_to:
        msg["Reply-To"] = ", ".join(reply_to)
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(date or None, usegmt=True)
    if message_id:
        msg["Message-ID"] = message_id
    for header in headers or []:
        name, value = str(header.get("Name") or ""), str(header.get("Value") or "")
        if not name or name.lower() in _RESERVED or any(c in name + value for c in "\r\n"):
            raise bad_request(f"The header {name!r} can't be set (it is reserved, empty or has a line break).")
        msg[name] = value
    cs = (charset or "UTF-8").lower()
    if text is not None and html is not None:
        msg.set_content(text, charset=cs)
        msg.add_alternative(html, subtype="html", charset=cs)
    elif html is not None:
        msg.set_content(html, subtype="html", charset=cs)
    else:
        msg.set_content(text or "", charset=cs)
    for att in attachments or []:
        try:
            data = base64.b64decode(str(att.get("RawContent") or ""), validate=False)
        except (binascii.Error, ValueError):
            raise bad_request("Attachment RawContent must be base64.") from None
        ctype = str(att.get("ContentType") or "application/octet-stream")
        maintype, _sl, subtype = ctype.partition("/")
        disposition = "inline" if str(att.get("ContentDisposition") or "").upper() == "INLINE" else "attachment"
        name = str(att.get("FileName") or "attachment")
        if msg.get_content_maintype() != "multipart" or msg.get_content_subtype() != "mixed":
            msg.make_mixed()
        msg.add_attachment(data, maintype=maintype or "application", subtype=subtype or "octet-stream",
                           filename=name, disposition=disposition,
                           cid=f"<{att['ContentId'].strip('<>')}>" if att.get("ContentId") else None)
        if att.get("ContentDescription"):
            msg.get_payload()[-1]["Content-Description"] = str(att["ContentDescription"])
    return crlf(msg.as_bytes())


def simple(source: str, to: List[str], cc: List[str], reply_to: List[str], message: Dict[str, Any],
           message_id: str, date: float) -> bytes:
    """An SES ``Message`` (``Subject``, ``Body.Text`` / ``Body.Html``, ``Headers``, ``Attachments``)."""
    subject, _cs = _content(message.get("Subject"))
    body = message.get("Body") or {}
    text, cs_text = _content(body.get("Text")) if body.get("Text") else (None, "")
    html, cs_html = _content(body.get("Html")) if body.get("Html") else (None, "")
    if text is None and html is None:
        raise bad_request("Message.Body needs Text or Html.")
    return build(source=source, to=to, cc=cc, reply_to=reply_to, subject=subject, text=text, html=html,
                 charset=cs_text or cs_html or "UTF-8", headers=message.get("Headers"),
                 attachments=message.get("Attachments"), message_id=message_id, date=date)


def prepare_raw(raw: bytes, message_id: str, date: float) -> bytes:
    """A caller's raw message with CRLF line endings, without Bcc, and with Date / Message-ID added when missing."""
    raw = crlf(raw)
    head, body = split(raw)
    fields = header_fields(head)
    if not fields:
        raise bad_request("The raw message has no headers.")
    kept = [f for n, f in fields if n not in ("bcc", "return-path")]
    names = {n for n, _f in fields}
    extra = []
    if "date" not in names:
        extra.append(b"Date: " + email.utils.formatdate(date or None, usegmt=True).encode("ascii"))
    if "message-id" not in names and message_id:
        extra.append(b"Message-ID: " + message_id.encode("ascii"))
    if "mime-version" not in names:
        extra.append(b"MIME-Version: 1.0")
    return b"\r\n".join(kept + extra) + b"\r\n\r\n" + body


def headers_of(raw: bytes) -> Message:
    """The parsed header block (no body)."""
    head, _body = split(crlf(raw))
    return email.message_from_bytes(head + b"\r\n", policy=email.policy.default)


def raw_recipients(raw: bytes) -> Tuple[str, List[str], List[str], List[str]]:
    """(From, To, Cc, Bcc) of a raw message's headers."""
    msg = email.message_from_bytes(split(crlf(raw))[0] + b"\r\n", policy=email.policy.compat32)

    def addrs(name: str) -> List[str]:
        return [a for _n, a in email.utils.getaddresses(msg.get_all(name) or []) if a]

    return str(msg.get("From") or ""), addrs("To"), addrs("Cc"), addrs("Bcc")


def summary(raw: bytes) -> Dict[str, Any]:
    """The headers SES puts in ``mail.commonHeaders`` and ``mail.headers`` (first 50)."""
    msg = headers_of(raw)
    common: Dict[str, Any] = {}
    for key, name in (("from", "From"), ("replyTo", "Reply-To"), ("to", "To"), ("cc", "Cc"), ("bcc", "Bcc")):
        values = [str(v) for v in msg.get_all(name) or []]
        if values:
            common[key] = [a.strip() for v in values for a in _split_list(v)]
    for key, name in (("date", "Date"), ("messageId", "Message-ID"), ("subject", "Subject"),
                      ("returnPath", "Return-Path")):
        if msg.get(name) is not None:
            common[key] = str(msg.get(name))
    headers = [{"name": k, "value": str(v)} for k, v in list(msg.items())[:50]]
    return {"commonHeaders": common, "headers": headers, "headersTruncated": len(msg.items()) > 50}


def _split_list(value: str) -> List[str]:
    return [email.utils.formataddr(pair) if pair[0] else pair[1] for pair in email.utils.getaddresses([value]) if pair[1]]


def read(raw: bytes, max_text: int = 2 * 1024 * 1024) -> Dict[str, Any]:
    """For the console: headers, the text and HTML bodies and the attachments (name, type, size, content id)."""
    msg = email.message_from_bytes(crlf(raw), policy=email.policy.default)
    text = html = ""
    attachments = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        disposition = part.get_content_disposition()
        ctype = part.get_content_type()
        if disposition is None and ctype == "text/plain" and not text:
            text = _decode(part)[:max_text]
        elif disposition is None and ctype == "text/html" and not html:
            html = _decode(part)[:max_text]
        else:
            payload = part.get_payload(decode=True) or b""
            attachments.append({"FileName": part.get_filename() or "", "ContentType": ctype,
                                "Disposition": (disposition or "attachment").upper(), "Size": len(payload),
                                "ContentId": str(part.get("Content-ID") or "").strip("<>")})
    return {"Headers": [{"Name": k, "Value": str(v)} for k, v in msg.items()], "Text": text, "Html": html,
            "Attachments": attachments}


def _decode(part: Message) -> str:
    try:
        return str(part.get_content())
    except (LookupError, ValueError):
        payload = part.get_payload(decode=True) or b""
        return payload.decode("utf-8", "replace")
