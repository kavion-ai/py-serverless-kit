"""The SMTP endpoint, like ``email-smtp.<region>.amazonaws.com``: applications that only speak SMTP send through it.

Log in with ``AUTH PLAIN`` or ``AUTH LOGIN``: the access key ID as user name and its SES SMTP password (``python
server.py --smtp-password``, or the console's *SMTP settings*) or the secret access key as password. With
``SES_TLS_CERT`` / ``SES_TLS_KEY`` the server offers STARTTLS (``SES_SMTP_REQUIRE_TLS=on`` refuses AUTH before it).
Each message goes through the same checks as SendRawEmail: the From header must be a verified identity.
"""

from __future__ import annotations

import base64
import binascii
import re
import socket
import socketserver
import ssl
from typing import Any, List, Optional

from .config import AUTH, HELO_NAME, MAX_MESSAGE, REGION, SMTP_REQUIRE_TLS, TLS_CERT, TLS_KEY, VERSION, log
from .errors import ApiError
from .sigv4 import check_smtp_login

_ADDR = re.compile(r"^\s*(?:FROM|TO)\s*:\s*<([^<>]*)>(.*)$", re.I)
_MAX_LINE = 4096


def tls_context() -> Optional[ssl.SSLContext]:
    if not (TLS_CERT and TLS_KEY):
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(TLS_CERT, TLS_KEY)
    return ctx


class Session(socketserver.StreamRequestHandler):
    timeout = 300
    tls: Optional[ssl.SSLContext] = None

    def setup(self) -> None:
        super().setup()
        self.user = "" if AUTH != "off" else "anonymous"
        self.secure = False
        self.mail_from: Optional[str] = None
        self.rcpts: List[str] = []

    def say(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode("utf-8"))
        self.wfile.flush()

    def readline(self) -> Optional[bytes]:
        line = self.rfile.readline(_MAX_LINE + 2)
        if not line:
            return None
        return line.rstrip(b"\r\n")

    def handle(self) -> None:
        try:
            self.say(f"220 {HELO_NAME} ESMTP pskit SES {VERSION}")
            while True:
                raw = self.readline()
                if raw is None:
                    return
                text = raw.decode("utf-8", "replace")
                verb, _sp, arg = text.partition(" ")
                verb = verb.upper()
                fn = getattr(self, f"cmd_{verb.lower()}", None) if verb.isalpha() else None
                if fn is None:
                    self.say("502 5.5.2 Command not recognized")
                    continue
                if fn(arg.strip()) is False:
                    return
        except (OSError, ssl.SSLError):
            return

    # ------------------------------------------------------------------ commands

    def cmd_ehlo(self, arg: str) -> None:
        self._reset()
        lines = [HELO_NAME, "8BITMIME", "PIPELINING", f"SIZE {MAX_MESSAGE}"]
        if self.tls and not self.secure:
            lines.append("STARTTLS")
        if AUTH != "off" and (self.secure or not SMTP_REQUIRE_TLS):
            lines.append("AUTH PLAIN LOGIN")
        for i, line in enumerate(lines):
            self.say(f"250{'-' if i < len(lines) - 1 else ' '}{line}")

    def cmd_helo(self, arg: str) -> None:
        self._reset()
        self.say(f"250 {HELO_NAME}")

    def cmd_starttls(self, arg: str) -> None:
        if not self.tls or self.secure:
            self.say("502 5.5.1 STARTTLS not available")
            return
        self.say("220 2.0.0 Ready to start TLS")
        conn = self.tls.wrap_socket(self.connection, server_side=True)
        self.connection = self.request = conn
        self.rfile = conn.makefile("rb")
        self.wfile = conn.makefile("wb")
        self.secure = True
        self._reset()
        self.user = "" if AUTH != "off" else "anonymous"

    def cmd_auth(self, arg: str) -> None:
        if AUTH == "off":
            self.say("235 2.7.0 Authentication successful")
            return
        if self.user:
            self.say("503 5.5.1 Already authenticated")
            return
        if SMTP_REQUIRE_TLS and not self.secure:
            self.say("530 5.7.0 Must issue a STARTTLS command first")
            return
        mech, _sp, initial = arg.partition(" ")
        try:
            if mech.upper() == "PLAIN":
                if not initial:
                    self.say("334 ")
                    initial = (self.readline() or b"").decode("ascii", "replace")
                parts = base64.b64decode(initial).decode("utf-8").split("\0")
                if len(parts) != 3:
                    raise ValueError
                user, password = parts[1], parts[2]
            elif mech.upper() == "LOGIN":
                if initial:
                    user = base64.b64decode(initial).decode("utf-8")
                else:
                    self.say("334 VXNlcm5hbWU6")
                    user = base64.b64decode(self.readline() or b"").decode("utf-8")
                self.say("334 UGFzc3dvcmQ6")
                password = base64.b64decode(self.readline() or b"").decode("utf-8")
            else:
                self.say("504 5.5.4 Unrecognized authentication type")
                return
        except (ValueError, binascii.Error, UnicodeDecodeError):
            self.say("501 5.5.2 Cannot decode the login")
            return
        if check_smtp_login(user, password):
            self.user = user
            self.say("235 2.7.0 Authentication successful")
        else:
            log("SMTP login refused for", repr(user), "from", self.client_address[0])
            self.say("535 5.7.8 Authentication credentials invalid")

    def cmd_mail(self, arg: str) -> None:
        if not self.user:
            self.say("530 5.7.1 Authentication required")
            return
        m = _ADDR.match(arg)
        if not m or not arg.upper().lstrip().startswith("FROM"):
            self.say("501 5.5.4 Syntax: MAIL FROM:<address>")
            return
        size = re.search(r"SIZE=(\d+)", m.group(2), re.I)
        if size and int(size.group(1)) > MAX_MESSAGE:
            self.say("552 5.3.4 Message size exceeds the limit")
            return
        self.mail_from, self.rcpts = m.group(1), []
        self.say("250 2.1.0 Ok")

    def cmd_rcpt(self, arg: str) -> None:
        if self.mail_from is None:
            self.say("503 5.5.1 MAIL first")
            return
        m = _ADDR.match(arg)
        if not m or not m.group(1) or not arg.upper().lstrip().startswith("TO"):
            self.say("501 5.5.4 Syntax: RCPT TO:<address>")
            return
        if len(self.rcpts) >= 50:
            self.say("452 4.5.3 Too many recipients")
            return
        self.rcpts.append(m.group(1))
        self.say("250 2.1.5 Ok")

    def cmd_data(self, arg: str) -> None:
        if self.mail_from is None or not self.rcpts:
            self.say("503 5.5.1 RCPT first")
            return
        self.say("354 End data with <CR><LF>.<CR><LF>")
        chunks: List[bytes] = []
        size, too_big = 0, False
        while True:
            line = self.rfile.readline(1024 * 1024)
            if not line:
                return
            if line in (b".\r\n", b".\n"):
                break
            if line.startswith(b"."):
                line = line[1:]
            size += len(line)
            if size > MAX_MESSAGE:
                too_big = True
            elif not too_big:
                chunks.append(line)
        if too_big:
            self._reset()
            self.say("552 5.3.4 Message size exceeds the limit")
            return
        self.say(self._send(b"".join(chunks)))
        self._reset()

    def _send(self, raw: bytes) -> str:
        from .operations import send_message
        from .util import addresses

        ctx = {"caller": self.user, "source_ip": self.client_address[0], "region": REGION}
        try:
            message_id = send_message(operation="SendSmtpEmail", ctx=ctx, source="", to=[], cc=[], bcc=[],
                                      reply_to=[], content={"Raw": {"Data": base64.b64encode(raw).decode()}},
                                      return_path=self.mail_from or "", envelope=addresses(self.rcpts))
        except ApiError as exc:
            if exc.code in ("TooManyRequestsException", "LimitExceededException"):
                return f"454 4.7.0 Throttling failure: {exc.message}"
            return f"554 5.7.1 Transaction failed: {exc.message}"
        except Exception as exc:  # noqa: BLE001 - answer the client, keep the session
            log("SMTP send failed:", repr(exc))
            return "451 4.3.0 Temporary server error, try again later"
        return f"250 Ok {message_id}"

    def cmd_rset(self, arg: str) -> None:
        self._reset()
        self.say("250 2.0.0 Ok")

    def cmd_noop(self, arg: str) -> None:
        self.say("250 2.0.0 Ok")

    def cmd_vrfy(self, arg: str) -> None:
        self.say("252 2.0.0 Cannot VRFY user")

    def cmd_quit(self, arg: str) -> bool:
        self.say("221 2.0.0 Bye")
        return False

    def _reset(self) -> None:
        self.mail_from, self.rcpts = None, []


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: Any) -> None:
        family = socket.AF_INET6 if ":" in address[0] else socket.AF_INET
        self.address_family = family
        super().__init__(address, Session)


def serve(bind: str, port: int) -> Server:
    import threading

    Session.tls = tls_context()
    server = Server((bind, port))
    threading.Thread(target=server.serve_forever, name="ses-smtp", daemon=True).start()
    return server
