"""pskit's Amazon SES compatible server (aws/ses) and its on-prem service.

The servers run for real here (Python always; C++ when ``aws/ses/cpp/build/ses-server`` is built or can be built
with ``make``) and are driven through boto3 (``ses`` and ``sesv2``), SMTP and the web console. Delivery goes to a
fake SMTP server in the test (relay mode, and direct mode through a fake DNS server answering MX / TXT).
"""

from __future__ import annotations

import base64
import http.cookiejar
import json
import os
import shutil
import smtplib
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

boto3 = pytest.importorskip("boto3")
from botocore.exceptions import ClientError  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "aws" / "ses"
CPP_BIN = SOURCE / "cpp" / "build" / "ses-server"


def _cpp_binary() -> Optional[str]:
    """The C++ server, built with ``make`` when a compiler and OpenSSL are there (Linux / macOS)."""
    if os.environ.get("PSKIT_SES_CPP"):
        return os.environ["PSKIT_SES_CPP"]
    if sys.platform == "win32":  # the server is Linux / macOS only
        return None
    if CPP_BIN.is_file():
        return str(CPP_BIN)
    if sys.platform == "win32" or not shutil.which("make") or not (SOURCE / "cpp" / "Makefile").is_file():
        return None
    done = subprocess.run(["make", "-C", str(SOURCE / "cpp")], capture_output=True, text=True, check=False)
    return str(CPP_BIN) if done.returncode == 0 and CPP_BIN.is_file() else None


CPP = _cpp_binary()
IMPLS = [
    pytest.param([sys.executable, str(SOURCE / "python" / "server.py")], id="python"),
    pytest.param([CPP or "ses-server"], id="cpp",
                 marks=pytest.mark.skipif(not CPP, reason="the C++ server is not built (make -C aws/ses/cpp)")),
]
ACCESS, SECRET = "AKIDPSKIT", "correct-horse-battery"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ----------------------------------------------------------------------------- fakes: SMTP sink and DNS


class SmtpSink:
    """A minimal SMTP server that records what it gets. A recipient whose local part starts with ``perm`` gets 550,
    ``temp`` gets 451; everything else is accepted."""

    def __init__(self) -> None:
        self.messages: List[Dict[str, object]] = []
        self.logins: List[Tuple[str, str]] = []
        sink = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                w = self.wfile
                w.write(b"220 sink ESMTP\r\n")
                mail_from, rcpts = "", []
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    cmd = line.decode().strip()
                    up = cmd.upper()
                    if up.startswith("EHLO"):
                        w.write(b"250-sink\r\n250-AUTH PLAIN LOGIN\r\n250 8BITMIME\r\n")
                    elif up.startswith("HELO"):
                        w.write(b"250 sink\r\n")
                    elif up.startswith("AUTH PLAIN"):
                        parts = base64.b64decode(cmd.split()[2]).decode().split("\0")
                        sink.logins.append((parts[1], parts[2]))
                        w.write(b"235 ok\r\n")
                    elif up.startswith("MAIL FROM"):
                        mail_from, rcpts = cmd.split(":", 1)[1].strip().strip("<>").split(">")[0], []
                        w.write(b"250 ok\r\n")
                    elif up.startswith("RCPT TO"):
                        addr = cmd.split(":", 1)[1].strip().strip("<>")
                        if addr.startswith("perm"):
                            w.write(b"550 5.1.1 no such user\r\n")
                        elif addr.startswith("temp"):
                            w.write(b"451 4.2.0 try later\r\n")
                        else:
                            rcpts.append(addr)
                            w.write(b"250 ok\r\n")
                    elif up == "DATA":
                        w.write(b"354 go\r\n")
                        data = b""
                        while True:
                            chunk = self.rfile.readline()
                            if chunk in (b".\r\n", b""):
                                break
                            data += chunk[1:] if chunk.startswith(b"..") else chunk
                        sink.messages.append({"from": mail_from, "to": list(rcpts), "data": data})
                        w.write(b"250 2.0.0 queued as SINK1\r\n")
                    elif up == "QUIT":
                        w.write(b"221 bye\r\n")
                        return
                    else:
                        w.write(b"250 ok\r\n")

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _dns_name(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode() for p in name.rstrip(".").split(".")) + b"\0"


class FakeDns:
    """Answers MX and TXT questions over UDP from ``records``: ``{(name, "MX"|"TXT"): [values]}``; MX values are
    ``(preference, host)``. An unknown name is NXDOMAIN."""

    def __init__(self, records: Dict[Tuple[str, str], list]) -> None:
        self.records = records
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
            except OSError:
                return
            ident = data[:2]
            off, labels = 12, []
            while data[off]:
                labels.append(data[off + 1:off + 1 + data[off]].decode())
                off += 1 + data[off]
            question = data[12:off + 5]
            qtype = struct.unpack(">H", data[off + 1:off + 3])[0]
            name = ".".join(labels).lower()
            kind = {15: "MX", 16: "TXT"}.get(qtype, "")
            known = any(n == name for n, _k in self.records)
            answers = []
            for value in self.records.get((name, kind), []):
                if kind == "MX":
                    rdata = struct.pack(">H", value[0]) + _dns_name(value[1])
                else:
                    raw = value.encode()
                    rdata = b"".join(bytes([len(raw[i:i + 255])]) + raw[i:i + 255] for i in range(0, len(raw), 255))
                answers.append(b"\xc0\x0c" + struct.pack(">HHIH", qtype, 1, 60, len(rdata)) + rdata)
            flags = 0x8180 if known else 0x8183
            reply = ident + struct.pack(">HHHHH", flags, 1, len(answers), 0, 0) + question + b"".join(answers)
            self.sock.sendto(reply, addr)

    def close(self) -> None:
        self.running = False
        self.sock.close()


# ----------------------------------------------------------------------------- the server under test


class Server:
    def __init__(self, argv: List[str], data: Path, **env: str) -> None:
        self.port, self.smtp_port = _free_port(), _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.data = data
        full = {**os.environ, "SES_PORT": str(self.port), "SES_SMTP_PORT": str(self.smtp_port),
                "SES_BIND": "127.0.0.1", "SES_DATA_DIR": str(data), "SES_ACCESS_KEY_ID": ACCESS,
                "SES_SECRET_ACCESS_KEY": SECRET, "SES_DELIVERY": "capture", "SES_DKIM_CHECK": "off",
                "SES_HELO_NAME": "ses.test", "SES_UI_DIR": str(SOURCE / "ui"), **env}
        self.proc = subprocess.Popen(argv, env=full, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 20
        while True:
            try:
                with urllib.request.urlopen(self.url + "/health", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                if self.proc.poll() is not None or time.monotonic() > deadline:
                    out = self.proc.stdout.read().decode() if self.proc.stdout else ""
                    raise RuntimeError(f"server did not start: {out}") from None
                time.sleep(0.1)
        kw = dict(endpoint_url=self.url, region_name="us-east-1", aws_access_key_id=ACCESS,
                  aws_secret_access_key=SECRET)
        self.v1 = boto3.client("ses", **kw)
        self.v2 = boto3.client("sesv2", **kw)

    def stop(self) -> str:
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        out = self.proc.stdout.read().decode() if self.proc.stdout else ""
        if self.proc.stdout:
            self.proc.stdout.close()
        return out

    def message(self, message_id: str) -> dict:
        return json.loads((self.data / "messages" / f"{message_id}.json").read_text("utf-8"))

    def raw(self, message_id: str) -> bytes:
        return (self.data / "messages" / f"{message_id}.eml").read_bytes()

    def wait(self, message_id: str, done=("DELIVERED", "BOUNCED", "PARTIAL", "DELAYED"), timeout: float = 15) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            try:
                rec = self.message(message_id)
                if rec["Status"] in done:
                    return rec
            except (OSError, ValueError, KeyError):
                pass
            if time.monotonic() > deadline:
                raise AssertionError(f"message {message_id} did not reach {done}")
            time.sleep(0.1)


@pytest.fixture(params=IMPLS)
def impl(request):
    return request.param


@pytest.fixture
def server(impl, tmp_path):
    srv = Server(impl, tmp_path / "data")
    yield srv
    srv.stop()


def _send(v2, to, **extra):
    return v2.send_email(FromEmailAddress="App <app@example.com>", Destination={"ToAddresses": to},
                         Content={"Simple": {"Subject": {"Data": "Hello"},
                                             "Body": {"Text": {"Data": "plain"}, "Html": {"Data": "<b>html</b>"}}}},
                         **extra)["MessageId"]


# ----------------------------------------------------------------------------- the API


def test_v2_identities_dkim_and_capture_delivery(server):
    created = server.v2.create_email_identity(EmailIdentity="Example.COM")
    assert created["IdentityType"] == "DOMAIN" and created["VerifiedForSendingStatus"] is True
    dkim = created["DkimAttributes"]
    assert dkim["Status"] == "SUCCESS" and len(dkim["Tokens"]) == 1
    with pytest.raises(ClientError) as err:
        server.v2.create_email_identity(EmailIdentity="example.com")
    assert err.value.response["Error"]["Code"] == "AlreadyExistsException"
    got = server.v2.get_email_identity(EmailIdentity="example.com")
    assert got["VerificationStatus"] == "SUCCESS" and got["DkimAttributes"]["SigningEnabled"] is True
    message_id = _send(server.v2, ["someone@dest.org"], EmailTags=[{"Name": "campaign", "Value": "welcome"}])
    rec = server.wait(message_id)
    assert rec["Status"] == "DELIVERED" and rec["DkimDomain"] == "example.com"
    assert [e["Type"] for e in rec["Events"]] == ["Send", "Delivery"]
    assert rec["Tags"] == [{"Name": "campaign", "Value": "welcome"}]
    raw = server.raw(message_id)
    assert raw.startswith(b"DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=example.com;")
    sys.path.insert(0, str(SOURCE / "python"))
    try:
        from sesserver import dkim as dkim_mod
    finally:
        sys.path.pop(0)
    public = json.loads((server.data / "ses.json").read_text())["identities"]["example.com"]["Dkim"]["PublicKey"]
    assert dkim_mod.verify(raw, public)
    assert b"multipart/alternative" in raw and f"<{message_id}@example.com>".encode() in raw
    # A subdomain address sends under the verified parent domain.
    assert server.wait(_send_from(server.v2, "news@mail.example.com"))["Status"] == "DELIVERED"


def _send_from(v2, source):
    return v2.send_email(FromEmailAddress=source, Destination={"ToAddresses": ["x@dest.org"]},
                         Content={"Simple": {"Subject": {"Data": "s"}, "Body": {"Text": {"Data": "t"}}}})["MessageId"]


def test_unverified_senders_are_rejected(server):
    with pytest.raises(ClientError) as err:
        _send(server.v2, ["x@dest.org"])
    assert err.value.response["Error"]["Code"] == "MessageRejected"
    assert "app@example.com" in err.value.response["Error"]["Message"]
    with pytest.raises(ClientError) as err:
        server.v1.send_email(Source="app@example.com", Destination={"ToAddresses": ["x@dest.org"]},
                             Message={"Subject": {"Data": "s"}, "Body": {"Text": {"Data": "t"}}})
    assert err.value.response["Error"]["Code"] == "MessageRejected"


def test_v1_query_api(server):
    token = server.v1.verify_domain_identity(Domain="example.com")["VerificationToken"]
    assert len(base64.b64decode(token)) == 32
    assert server.v1.verify_domain_dkim(Domain="example.com")["DkimTokens"]
    server.v1.verify_email_identity(EmailAddress="ops@other.org")
    server.v1.verify_email_identity(EmailAddress="ops@other.org")  # idempotent, as on SES
    assert server.v1.list_identities()["Identities"] == ["example.com", "ops@other.org"]
    assert server.v1.list_identities(IdentityType="Domain")["Identities"] == ["example.com"]
    attrs = server.v1.get_identity_verification_attributes(Identities=["example.com", "ops@other.org", "x.net"])
    assert attrs["VerificationAttributes"] == {"example.com": {"VerificationStatus": "Success",
                                                               "VerificationToken": token},
                                               "ops@other.org": {"VerificationStatus": "Success"}}
    dk = server.v1.get_identity_dkim_attributes(Identities=["example.com"])["DkimAttributes"]["example.com"]
    assert dk["DkimEnabled"] is True and dk["DkimVerificationStatus"] == "Success"
    assert server.v1.list_verified_email_addresses()["VerifiedEmailAddresses"] == ["ops@other.org"]
    message_id = server.v1.send_email(
        Source='"Ops" <ops@other.org>', Destination={"ToAddresses": ["a@dest.org"], "CcAddresses": ["b@dest.org"],
                                                     "BccAddresses": ["c@dest.org"]},
        Message={"Subject": {"Data": "Grüße", "Charset": "UTF-8"}, "Body": {"Text": {"Data": "héllo"}}},
        ReplyToAddresses=["reply@other.org"])["MessageId"]
    rec = server.wait(message_id)
    assert sorted(rec["Recipients"]) == ["a@dest.org", "b@dest.org", "c@dest.org"]
    raw = server.raw(message_id)
    assert b"c@dest.org" not in raw.split(b"\r\n\r\n")[0] and b"Reply-To: reply@other.org" in raw
    assert rec["DkimDomain"] == ""  # other.org has no DKIM key
    raw_id = server.v1.send_raw_email(RawMessage={
        "Data": b"From: ops@other.org\nTo: r@dest.org\nBcc: hidden@dest.org\nSubject: raw\n\nbody\n"})["MessageId"]
    raw_rec = server.wait(raw_id)
    assert sorted(raw_rec["Recipients"]) == ["hidden@dest.org", "r@dest.org"]
    assert b"hidden@dest.org" not in server.raw(raw_id) and b"\r\nSubject: raw\r\n" in server.raw(raw_id)
    quota = server.v1.get_send_quota()
    assert quota["Max24HourSend"] == 50000 and quota["SentLast24Hours"] == 5
    points = server.v1.get_send_statistics()["SendDataPoints"]
    assert sum(p["DeliveryAttempts"] for p in points) == 5
    assert server.v1.get_account_sending_enabled()["Enabled"] is True
    server.v1.update_account_sending_enabled(Enabled=False)
    with pytest.raises(ClientError) as err:
        server.v1.send_raw_email(RawMessage={"Data": b"From: ops@other.org\nTo: r@dest.org\n\nx"})
    assert err.value.response["Error"]["Code"] == "AccountSendingPausedException"
    server.v1.update_account_sending_enabled(Enabled=True)
    server.v1.delete_identity(Identity="ops@other.org")
    server.v1.delete_identity(Identity="ops@other.org")  # no error, as on SES
    assert server.v1.list_identities()["Identities"] == ["example.com"]
    with pytest.raises(ClientError) as err:
        server.v1.get_template(TemplateName="missing")
    assert err.value.response["Error"]["Code"] == "TemplateDoesNotExist"


def test_templates_render_the_same_everywhere(server):
    server.v2.create_email_identity(EmailIdentity="example.com")
    server.v1.create_template(Template={
        "TemplateName": "welcome", "SubjectPart": "Hi {{name}}!",
        "TextPart": "{{#each items}}{{@index}}:{{this.title}}{{#if @last}}.{{else}}, {{/if}}{{/each}}"
                    "{{#unless vip}} (standard){{/unless}}{{! a comment }}",
        "HtmlPart": "<p>{{name}} {{{raw}}} {{missing.deep}}{{#with org}}{{city}}{{/with}}</p>"})
    data = {"name": "<Ann & Bob>", "raw": "<i>x</i>", "items": [{"title": "a"}, {"title": "b"}], "vip": False,
            "org": {"city": "Pune"}}
    rendered = server.v1.test_render_template(TemplateName="welcome", TemplateData=json.dumps(data))
    text = rendered["RenderedTemplate"]
    assert "Subject: Hi <Ann & Bob>!" in text
    import email
    import email.policy

    msg = email.message_from_string(text, policy=email.policy.default)
    assert msg.get_body(("plain",)).get_content().strip() == "0:a, 1:b. (standard)"
    assert msg.get_body(("html",)).get_content().strip() == "<p>&lt;Ann &amp; Bob&gt; <i>x</i> Pune</p>"
    # Non-ASCII bodies are 7-bit safe (quoted-printable / base64) and decode back to the same text.
    server.v2.create_email_template(TemplateName="intl", TemplateContent={"Subject": "Grüße {{n}}",
                                                                         "Text": "Héllo {{n}} — ✓"})
    intl = email.message_from_string(server.v1.test_render_template(
        TemplateName="intl", TemplateData='{"n": "Zoë"}')["RenderedTemplate"], policy=email.policy.default)
    assert intl["Subject"] == "Grüße Zoë" and intl.get_content().strip() == "Héllo Zoë — ✓"
    assert intl["Content-Transfer-Encoding"] in ("quoted-printable", "base64")
    server.v2.delete_email_template(TemplateName="intl")
    with pytest.raises(ClientError) as err:
        server.v2.create_email_template(TemplateName="bad", TemplateContent={"Subject": "{{#if x}}open"})
    assert err.value.response["Error"]["Code"] == "BadRequestException"
    with pytest.raises(ClientError) as err:
        server.v1.test_render_template(TemplateName="welcome", TemplateData="not json")
    assert err.value.response["Error"]["Code"] == "InvalidRenderingParameter"
    server.v2.update_email_template(TemplateName="welcome", TemplateContent={"Subject": "S {{n}}", "Text": "T {{n}}"})
    assert server.v2.get_email_template(TemplateName="welcome")["TemplateContent"]["Subject"] == "S {{n}}"
    message_id = server.v2.send_email(
        FromEmailAddress="app@example.com", Destination={"ToAddresses": ["x@dest.org"]},
        Content={"Template": {"TemplateName": "welcome", "TemplateData": '{"n": 7}'}})["MessageId"]
    assert server.wait(message_id)["Subject"] == "S 7"
    bulk = server.v2.send_bulk_email(
        FromEmailAddress="app@example.com",
        DefaultContent={"Template": {"TemplateName": "welcome", "TemplateData": '{"n": "default"}'}},
        BulkEmailEntries=[
            {"Destination": {"ToAddresses": ["one@dest.org"]},
             "ReplacementEmailContent": {"ReplacementTemplate": {"ReplacementTemplateData": '{"n": "one"}'}}},
            {"Destination": {"ToAddresses": ["two@dest.org"]}},
            {"Destination": {"ToAddresses": ["not an address"]}}])["BulkEmailEntryResults"]
    assert [r["Status"] for r in bulk] == ["SUCCESS", "SUCCESS", "INVALID_PARAMETER"]
    assert server.wait(bulk[0]["MessageId"])["Subject"] == "S one"
    assert server.wait(bulk[1]["MessageId"])["Subject"] == "S default"
    names = [t["TemplateName"] for t in server.v2.list_email_templates()["TemplatesMetadata"]]
    assert names == ["welcome"]
    server.v2.delete_email_template(TemplateName="welcome")
    assert server.v1.list_templates()["TemplatesMetadata"] == []


def test_simple_content_attachments_and_headers(server):
    server.v2.create_email_identity(EmailIdentity="example.com")
    message_id = server.v2.send_email(
        FromEmailAddress="app@example.com", Destination={"ToAddresses": ["x@dest.org"]},
        Content={"Simple": {"Subject": {"Data": "files"}, "Body": {"Text": {"Data": "see attached"}},
                            "Headers": [{"Name": "X-Order", "Value": "42"}],
                            "Attachments": [{"FileName": "report.csv", "ContentType": "text/csv",
                                             "RawContent": b"a,b\n1,2\n"}]}})["MessageId"]
    server.wait(message_id)
    import email
    import email.policy

    msg = email.message_from_bytes(server.raw(message_id), policy=email.policy.default)
    assert msg["X-Order"] == "42" and msg.get_content_type() == "multipart/mixed"
    att = next(msg.iter_attachments())
    assert att.get_filename() == "report.csv" and att.get_content() == "a,b\n1,2\n"
    with pytest.raises(ClientError):
        server.v2.send_email(FromEmailAddress="app@example.com", Destination={"ToAddresses": ["x@dest.org"]},
                             Content={"Simple": {"Subject": {"Data": "s"}, "Body": {"Text": {"Data": "t"}},
                                                 "Headers": [{"Name": "From", "Value": "evil@x.com"}]}})


def test_mailbox_simulator_and_suppression_list(server):
    server.v2.create_email_identity(EmailIdentity="example.com")
    sim = "simulator.amazonses.com"
    message_id = _send(server.v2, [f"success@{sim}", f"bounce@{sim}", f"complaint@{sim}", f"suppressionlist@{sim}"])
    rec = server.wait(message_id)
    assert rec["Status"] == "PARTIAL"
    states = {r: s["Status"] for r, s in rec["Recipients"].items()}
    assert states == {f"success@{sim}": "DELIVERED", f"bounce@{sim}": "BOUNCED", f"complaint@{sim}": "DELIVERED",
                      f"suppressionlist@{sim}": "BOUNCED"}
    kinds = sorted(e["Type"] for e in rec["Events"])
    assert kinds.count("Bounce") == 2 and "Complaint" in kinds
    # Simulator bounces never reach the suppression list.
    assert server.v2.list_suppressed_destinations()["SuppressedDestinationSummaries"] == []
    server.v2.put_suppressed_destination(EmailAddress="Gone@Dest.org", Reason="BOUNCE")
    got = server.v2.get_suppressed_destination(EmailAddress="gone@dest.org")["SuppressedDestination"]
    assert got["Reason"] == "BOUNCE"
    rec = server.wait(_send(server.v2, ["gone@dest.org", "ok@dest.org"]))
    assert rec["Recipients"]["gone@dest.org"]["Status"] == "SUPPRESSED"
    assert rec["Recipients"]["ok@dest.org"]["Status"] == "DELIVERED"
    bounce = next(e for e in rec["Events"] if e["Type"] == "Bounce")
    assert bounce["BounceSubType"] == "OnAccountSuppressionList"
    # A configuration set can turn suppression off for its mail.
    server.v2.create_configuration_set(ConfigurationSetName="no-supp", SuppressionOptions={"SuppressedReasons": []})
    rec = server.wait(_send(server.v2, ["gone@dest.org"], ConfigurationSetName="no-supp"))
    assert rec["Recipients"]["gone@dest.org"]["Status"] == "DELIVERED"
    listed = server.v2.list_suppressed_destinations(Reasons=["BOUNCE"])["SuppressedDestinationSummaries"]
    assert [s["EmailAddress"] for s in listed] == ["Gone@dest.org"]  # the domain is lower-cased
    server.v2.delete_suppressed_destination(EmailAddress="gone@dest.org")
    with pytest.raises(ClientError) as err:
        server.v2.get_suppressed_destination(EmailAddress="gone@dest.org")
    assert err.value.response["Error"]["Code"] == "NotFoundException"


def test_configuration_sets_tags_and_account(server):
    server.v2.create_email_identity(EmailIdentity="example.com")
    server.v2.create_configuration_set(ConfigurationSetName="marketing", DeliveryOptions={"TlsPolicy": "REQUIRE"},
                                       Tags=[{"Key": "team", "Value": "growth"}])
    cs = server.v2.get_configuration_set(ConfigurationSetName="marketing")
    assert cs["DeliveryOptions"]["TlsPolicy"] == "REQUIRE" and cs["SendingOptions"]["SendingEnabled"] is True
    assert server.v2.list_configuration_sets()["ConfigurationSets"] == ["marketing"]
    assert server.v1.describe_configuration_set(ConfigurationSetName="marketing")["DeliveryOptions"] == {
        "TlsPolicy": "Require"}
    server.v2.create_configuration_set_event_destination(
        ConfigurationSetName="marketing", EventDestinationName="hook",
        EventDestination={"Enabled": True, "MatchingEventTypes": ["BOUNCE", "DELIVERY"],
                          "SnsDestination": {"TopicArn": "arn:aws:sns:us-east-1:000000000000:mail"}})
    dests = server.v2.get_configuration_set_event_destinations(ConfigurationSetName="marketing")["EventDestinations"]
    assert dests[0]["Name"] == "hook" and dests[0]["MatchingEventTypes"] == ["BOUNCE", "DELIVERY"]
    server.v2.put_configuration_set_sending_options(ConfigurationSetName="marketing", SendingEnabled=False)
    with pytest.raises(ClientError) as err:
        _send(server.v2, ["x@dest.org"], ConfigurationSetName="marketing")
    assert err.value.response["Error"]["Code"] == "SendingPausedException"
    with pytest.raises(ClientError) as err:
        _send(server.v2, ["x@dest.org"], ConfigurationSetName="nope")
    assert err.value.response["Error"]["Code"] == "NotFoundException"
    arn = "arn:aws:ses:us-east-1:000000000000:configuration-set/marketing"
    server.v2.tag_resource(ResourceArn=arn, Tags=[{"Key": "env", "Value": "prod"}])
    tags = server.v2.list_tags_for_resource(ResourceArn=arn)["Tags"]
    assert tags == [{"Key": "env", "Value": "prod"}, {"Key": "team", "Value": "growth"}]
    server.v2.untag_resource(ResourceArn=arn, TagKeys=["team"])
    assert server.v2.list_tags_for_resource(ResourceArn=arn)["Tags"] == [{"Key": "env", "Value": "prod"}]
    server.v2.delete_configuration_set(ConfigurationSetName="marketing")
    account = server.v2.get_account()
    assert account["SendingEnabled"] is True and account["ProductionAccessEnabled"] is True
    assert account["SuppressionAttributes"]["SuppressedReasons"] == ["BOUNCE", "COMPLAINT"]
    server.v2.put_account_suppression_attributes(SuppressedReasons=["COMPLAINT"])
    assert server.v2.get_account()["SuppressionAttributes"]["SuppressedReasons"] == ["COMPLAINT"]


def test_signature_is_checked(server):
    bad = boto3.client("sesv2", endpoint_url=server.url, region_name="us-east-1", aws_access_key_id=ACCESS,
                       aws_secret_access_key="wrong")
    with pytest.raises(ClientError) as err:
        bad.get_account()
    assert err.value.response["ResponseMetadata"]["HTTPStatusCode"] == 403
    unknown = boto3.client("ses", endpoint_url=server.url, region_name="us-east-1", aws_access_key_id="NOPE",
                           aws_secret_access_key=SECRET)
    with pytest.raises(ClientError) as err:
        unknown.list_identities()
    assert err.value.response["Error"]["Code"] == "InvalidClientTokenId"
    req = urllib.request.Request(server.url + "/v2/email/account")
    with pytest.raises(urllib.error.HTTPError) as http:
        urllib.request.urlopen(req, timeout=5)
    assert http.value.code == 403
    # Identities with "@" in the path are signed with the path encoded twice, as the SDKs do.
    server.v2.create_email_identity(EmailIdentity="me@example.org")
    assert server.v2.get_email_identity(EmailIdentity="me@example.org")["IdentityType"] == "EMAIL_ADDRESS"
    server.v2.delete_email_identity(EmailIdentity="me@example.org")


def test_rate_and_daily_quota(impl, tmp_path):
    srv = Server(impl, tmp_path / "data", SES_MAX_24H="3", SES_MAX_RATE="100")
    try:
        srv.v2.create_email_identity(EmailIdentity="example.com")
        _send(srv.v2, ["a@dest.org", "b@dest.org"])
        with pytest.raises(ClientError) as err:
            _send(srv.v2, ["c@dest.org", "d@dest.org"])
        assert err.value.response["Error"]["Code"] == "LimitExceededException"
        assert srv.v2.get_account()["SendQuota"]["SentLast24Hours"] == 2
    finally:
        srv.stop()


def test_verify_manual_and_sandbox(impl, tmp_path):
    srv = Server(impl, tmp_path / "data", SES_VERIFY="manual", SES_SANDBOX="on")
    try:
        srv.v2.create_email_identity(EmailIdentity="example.com")
        assert srv.v2.get_email_identity(EmailIdentity="example.com")["VerificationStatus"] == "PENDING"
        with pytest.raises(ClientError):
            _send(srv.v2, ["x@dest.org"])
        _console_call(srv, "SetEmailIdentityVerified", {"EmailIdentity": "example.com", "Verified": True})
        with pytest.raises(ClientError) as err:  # the sandbox needs verified recipients too
            _send(srv.v2, ["x@dest.org"])
        assert "x@dest.org" in err.value.response["Error"]["Message"]
        assert srv.v2.get_account()["ProductionAccessEnabled"] is False
        srv.wait(_send(srv.v2, ["success@simulator.amazonses.com", "ops@example.com"]))
    finally:
        srv.stop()


# ----------------------------------------------------------------------------- delivery


def test_relay_delivery_bounces_and_retries(impl, tmp_path):
    sink = SmtpSink()
    srv = Server(impl, tmp_path / "data", SES_DELIVERY="relay", SES_RELAY_HOST="127.0.0.1",
                 SES_RELAY_PORT=str(sink.port), SES_RELAY_TLS="none", SES_RELAY_USER="relayuser",
                 SES_RELAY_PASSWORD="relaypw")
    try:
        srv.v2.create_email_identity(EmailIdentity="example.com")
        message_id = _send(srv.v2, ["good@dest.org", "perm@dest.org", "temp@dest.org"])
        rec = srv.wait(message_id, done=("PARTIAL", "DELAYED"))
        deadline = time.monotonic() + 10
        while rec["Recipients"]["temp@dest.org"]["Status"] != "DELAYED" and time.monotonic() < deadline:
            time.sleep(0.1)
            rec = srv.message(message_id)
        assert rec["Recipients"]["good@dest.org"]["Status"] == "DELIVERED"
        assert rec["Recipients"]["good@dest.org"]["Response"].startswith("250")
        assert rec["Recipients"]["perm@dest.org"]["Status"] == "BOUNCED"
        assert rec["Recipients"]["temp@dest.org"]["Status"] == "DELAYED"
        assert rec["Recipients"]["temp@dest.org"]["NextAttempt"] > time.time() + 30
        assert sink.logins == [("relayuser", "relaypw")]
        assert sink.messages[0]["to"] == ["good@dest.org"] and sink.messages[0]["from"] == "app@example.com"
        assert sink.messages[0]["data"].startswith(b"DKIM-Signature:")
        bounce = next(e for e in rec["Events"] if e["Type"] == "Bounce")
        assert bounce["Recipients"] == ["perm@dest.org"] and bounce["Status"] == "5.1.1"
        assert any(e["Type"] == "DeliveryDelay" for e in rec["Events"])
        # The permanent bounce put the address on the suppression list.
        listed = srv.v2.list_suppressed_destinations()["SuppressedDestinationSummaries"]
        assert [s["EmailAddress"] for s in listed] == ["perm@dest.org"]
        _console_call(srv, "RetryMessage", {"MessageId": message_id})
        deadline = time.monotonic() + 10
        while srv.message(message_id)["Recipients"]["temp@dest.org"]["Attempts"] < 2:
            assert time.monotonic() < deadline
            time.sleep(0.1)
    finally:
        srv.stop()
        sink.close()


def test_direct_delivery_through_mx_and_dns_verification(impl, tmp_path):
    sink = SmtpSink()
    records: Dict[Tuple[str, str], list] = {("dest.org", "MX"): [(10, "localhost")]}
    dns = FakeDns(records)
    srv = Server(impl, tmp_path / "data", SES_DELIVERY="direct", SES_DIRECT_PORT=str(sink.port),
                 SES_DNS_SERVER=f"127.0.0.1:{dns.port}", SES_VERIFY="dns", SES_DKIM_CHECK="on")
    try:
        srv.v2.create_email_identity(EmailIdentity="example.com")
        got = srv.v2.get_email_identity(EmailIdentity="example.com")
        assert got["VerificationStatus"] == "PENDING" and got["DkimAttributes"]["Status"] in ("PENDING", "FAILED",
                                                                                              "TEMPORARY_FAILURE")
        rows = _console_call(srv, "GetEmailIdentityDnsRecords", {"EmailIdentity": "example.com"})["Records"]
        dkim_row = next(r for r in rows if r["Purpose"] == "DKIM")
        verify_row = next(r for r in rows if r["Purpose"] == "Verification")
        records[(dkim_row["Name"], "TXT")] = [dkim_row["Value"]]
        records[(verify_row["Name"], "TXT")] = [verify_row["Value"]]
        records[("example.com", "TXT")] = ["v=spf1 -all"]
        checked = _console_call(srv, "CheckEmailIdentity", {"EmailIdentity": "example.com"})
        assert checked["VerificationStatus"] == "SUCCESS" and checked["DkimAttributes"]["Status"] == "SUCCESS"
        # An address of the verified domain may send without its own verification.
        message_id = srv.v2.send_email(
            FromEmailAddress="news@example.com", Destination={"ToAddresses": ["one@dest.org", "x@nowhere.test"]},
            Content={"Simple": {"Subject": {"Data": "direct"}, "Body": {"Text": {"Data": "via MX"}}}})["MessageId"]
        rec = srv.wait(message_id, done=("PARTIAL", "DELIVERED", "BOUNCED"))
        assert rec["Recipients"]["one@dest.org"]["Status"] == "DELIVERED"
        assert rec["Recipients"]["x@nowhere.test"]["Status"] == "BOUNCED"  # NXDOMAIN
        assert sink.messages[0]["to"] == ["one@dest.org"]
        assert sink.messages[0]["data"].startswith(b"DKIM-Signature:") and rec["DkimDomain"] == "example.com"
    finally:
        srv.stop()
        sink.close()
        dns.close()


# ----------------------------------------------------------------------------- SMTP endpoint


def _smtp_password(secret: str, region: str) -> str:
    import hashlib
    import hmac

    key = ("AWS4" + secret).encode()
    for part in ("11111111", region, "ses", "aws4_request", "SendRawEmail"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    return base64.b64encode(b"\x04" + key).decode()


def test_smtp_endpoint(server):
    server.v2.create_email_identity(EmailIdentity="example.com")
    with smtplib.SMTP("127.0.0.1", server.smtp_port, timeout=10) as smtp:
        smtp.ehlo()
        assert smtp.has_extn("auth")
        with pytest.raises(smtplib.SMTPSenderRefused):
            smtp.sendmail("app@example.com", ["x@dest.org"], b"Subject: s\r\n\r\nx")
        smtp.login(ACCESS, _smtp_password(SECRET, "eu-west-1"))
        refused = smtp.sendmail("bounces@example.com", ["x@dest.org", "y@dest.org"],
                                b"From: App <app@example.com>\r\nTo: x@dest.org\r\nSubject: via smtp\r\n\r\n"
                                b".dot line\r\nend\r\n")
        assert refused == {}
        with pytest.raises(smtplib.SMTPDataError) as err:
            smtp.sendmail("a@spoof.com", ["x@dest.org"], b"From: a@spoof.com\r\nSubject: s\r\n\r\nx")
        assert err.value.smtp_code == 554
    with smtplib.SMTP("127.0.0.1", server.smtp_port, timeout=10) as smtp:
        with pytest.raises(smtplib.SMTPAuthenticationError):
            smtp.login(ACCESS, "wrong")
        smtp.login(ACCESS, SECRET)  # the secret access key works too
    msgs = [json.loads(p.read_text()) for p in (server.data / "messages").glob("*.json")]
    rec = next(m for m in msgs if m["Subject"] == "via smtp")
    assert sorted(rec["Recipients"]) == ["x@dest.org", "y@dest.org"] and rec["MailFrom"] == "bounces@example.com"
    assert b"\r\n.dot line\r\n" in server.raw(rec["MessageId"])


# ----------------------------------------------------------------------------- console, persistence


def _console(server):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    body = json.dumps({"user": ACCESS, "password": SECRET}).encode()
    req = urllib.request.Request(server.url + "/ui/login", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=5) as resp:
        csrf = json.loads(resp.read())["csrf"]
    return opener, csrf


def _console_call(server, operation, payload):
    opener, csrf = _console(server)
    req = urllib.request.Request(server.url + f"/ui/api/{operation}", data=json.dumps(payload).encode(),
                                 method="POST", headers={"Content-Type": "application/json", "X-SES-CSRF": csrf})
    with opener.open(req, timeout=30) as resp:
        return json.loads(resp.read())


def test_web_console_login_csrf_and_operations(server):
    with urllib.request.urlopen(server.url + "/ui/", timeout=5) as resp:
        assert "script-src 'self'" in resp.headers["Content-Security-Policy"]
    req = urllib.request.Request(server.url + "/ui/api/GetAccount", data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=5)
    assert err.value.code == 401
    opener, csrf = _console(server)
    req = urllib.request.Request(server.url + "/ui/api/GetAccount", data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as err:
        opener.open(req, timeout=5)
    assert err.value.code == 403
    bad = urllib.request.Request(server.url + "/ui/login", method="POST",
                                 data=json.dumps({"user": ACCESS, "password": "nope"}).encode())
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(bad, timeout=5)
    assert err.value.code == 401
    _console_call(server, "CreateEmailIdentity", {"EmailIdentity": "example.com"})
    sent = _console_call(server, "SendEmail", {
        "FromEmailAddress": "app@example.com", "Destination": {"ToAddresses": ["x@dest.org"]},
        "Content": {"Simple": {"Subject": {"Data": "from console"}, "Body": {"Html": {"Data": "<h1>Hi</h1>"}}}}})
    server.wait(sent["MessageId"])
    listed = _console_call(server, "ListMessages", {"Query": "console"})
    assert [m["MessageId"] for m in listed["Messages"]] == [sent["MessageId"]] and listed["Total"] == 1
    got = _console_call(server, "GetMessage", {"MessageId": sent["MessageId"], "IncludeRaw": True})
    assert got["Content"]["Html"].strip() == "<h1>Hi</h1>" and got["Caller"] == f"console:{ACCESS}"
    assert "DKIM-Signature" in got["Raw"]
    stats = _console_call(server, "GetStatistics", {"Days": 7})
    assert len(stats["Days"]) == 7 and stats["Days"][-1]["Delivered"] == 1
    info = _console_call(server, "GetServerInfo", {})
    assert info["Delivery"] == "capture" and info["Smtp"]["Port"] == server.smtp_port
    creds = _console_call(server, "GetSmtpCredentials", {})
    assert creds["Username"] == ACCESS and creds["Password"] == _smtp_password(SECRET, "us-east-1")
    _console_call(server, "DeleteMessage", {"MessageId": sent["MessageId"]})
    assert _console_call(server, "ListMessages", {})["Total"] == 0


def _console_error(server, operation, payload):
    with pytest.raises(urllib.error.HTTPError) as err:
        _console_call(server, operation, payload)
    return err.value.code, json.loads(err.value.read() or b"{}")


def test_delivery_mode_is_chosen_in_the_console(impl, tmp_path):
    sink = SmtpSink()
    data = tmp_path / "data"
    srv = Server(impl, data)  # started in capture mode (SES_DELIVERY=capture)
    try:
        got = _console_call(srv, "GetDeliverySettings", {})
        assert got["Mode"] == "capture" and got["Source"] == "environment" and "RelayPassword" not in got
        srv.v2.create_email_identity(EmailIdentity="example.com")
        captured = srv.wait(_send(srv.v2, ["first@dest.org"]))
        assert captured["Recipients"]["first@dest.org"]["Response"].startswith("250 2.0.0 Captured")
        assert sink.messages == []
        # Bad settings are refused; a relay login needs TLS.
        assert _console_error(srv, "PutDeliverySettings", {"Mode": "pigeon"})[0] == 400
        assert _console_error(srv, "PutDeliverySettings", {"Mode": "relay"})[0] == 400
        code, body = _console_error(srv, "PutDeliverySettings", {
            "Mode": "relay", "RelayHost": "127.0.0.1", "RelayPort": sink.port, "RelayTls": "none",
            "RelayUser": "u", "RelayPassword": "p"})
        assert code == 400 and "TLS" in body["message"]
        # A relay that does not answer: the mail waits (DELAYED) ...
        dead = _free_port()
        _console_call(srv, "PutDeliverySettings", {"Mode": "relay", "RelayHost": "127.0.0.1", "RelayPort": dead,
                                                   "RelayTls": "none"})
        assert _console_call(srv, "TestDeliverySettings", {})["Ok"] is False
        waiting = _send(srv.v2, ["second@dest.org"])
        assert srv.wait(waiting, done=("DELAYED",))["Delivery"] == "relay"
        # ... and goes out as soon as the settings are fixed, without waiting for its retry time.
        relay = {"Mode": "relay", "RelayHost": "127.0.0.1", "RelayPort": sink.port, "RelayTls": "none"}
        tested = _console_call(srv, "TestDeliverySettings", relay)
        assert tested["Ok"] is True and tested["Steps"], tested
        saved = _console_call(srv, "PutDeliverySettings", relay)
        assert saved["Mode"] == "relay" and saved["Source"] == "console" and saved["RelayPort"] == sink.port
        assert srv.wait(waiting, done=("DELIVERED",))["Recipients"]["second@dest.org"]["Response"].startswith("250")
        assert srv.wait(_send(srv.v2, ["third@dest.org"]))["Status"] == "DELIVERED"
        assert sorted(m["to"][0] for m in sink.messages) == ["second@dest.org", "third@dest.org"]
        info = _console_call(srv, "GetServerInfo", {})
        assert info["Delivery"] == "relay" and info["DeliverySource"] == "console"
    finally:
        srv.stop()
    srv = Server(impl, data)  # the console's choice survives a restart and wins over SES_DELIVERY
    try:
        got = _console_call(srv, "GetDeliverySettings", {})
        assert got["Mode"] == "relay" and got["Source"] == "console" and got["Environment"]["Mode"] == "capture"
        assert "RelayPassword" not in got and "RelayPassword" not in got["Environment"]  # only RelayPasswordSet
        reset = _console_call(srv, "ResetDeliverySettings", {})
        assert reset["Mode"] == "capture" and reset["Source"] == "environment"
        assert _console_call(srv, "TestDeliverySettings", {})["Ok"] is True  # capture: nothing to test
    finally:
        srv.stop()
        sink.close()


def test_data_survives_a_restart_and_is_shared(tmp_path):
    impls = [p.values[0] for p in IMPLS if not p.marks]
    data = tmp_path / "data"
    first = Server(impls[0], data)
    try:
        first.v2.create_email_identity(EmailIdentity="example.com")
        first.v2.create_email_template(TemplateName="t", TemplateContent={"Subject": "s", "Text": "x"})
        message_id = _send(first.v2, ["x@dest.org"])
        first.wait(message_id)
    finally:
        first.stop()
    if os.name == "posix":
        assert (data / "ses.json").stat().st_mode & 0o777 == 0o600
    for argv in impls:  # each implementation reads what the first wrote
        srv = Server(argv, data)
        try:
            assert srv.v2.get_email_identity(EmailIdentity="example.com")["DkimAttributes"]["Status"] == "SUCCESS"
            assert srv.v2.get_email_template(TemplateName="t")["TemplateContent"]["Subject"] == "s"
            assert _console_call(srv, "GetMessage", {"MessageId": message_id})["Status"] == "DELIVERED"
            assert srv.wait(_send(srv.v2, ["y@dest.org"]))["DkimDomain"] == "example.com"
        finally:
            srv.stop()


def test_refuses_to_start_without_credentials(impl, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SES_")}
    env.update(SES_DATA_DIR=str(tmp_path), SES_PORT=str(_free_port()), SES_SMTP_PORT=str(_free_port()))
    done = subprocess.run(impl, env=env, capture_output=True, text=True, timeout=20, check=False)
    assert done.returncode == 2 and "SES_SECRET_ACCESS_KEY" in done.stderr


# ----------------------------------------------------------------------------- the pskit on-prem service

from py_serverless_kit.core import onprem_services as svc  # noqa: E402
from py_serverless_kit.core import onprem_ses  # noqa: E402

from .test_onprem_services import RAW, FakeDocker  # noqa: E402

SSH = {"method": "ssh", "host": "20.40.60.80", "user": "ubuntu", "identity_file": "key.pem"}


def _create(tmp_path, **body):
    fake = FakeDocker()
    req = {"key": "mail", "service": "ses", "password": "Sup3r-secret-pw", **body}
    entry = svc.create(tmp_path, req, RAW, lambda _l: None, run=fake, wait_seconds=1)
    return entry, fake.calls


def _env_of(argv):
    return dict(argv[i + 1].split("=", 1) for i, arg in enumerate(argv) if arg == "-e")


def test_catalog_lists_both_servers():
    items = {i["id"]: i for i in svc.catalog()}
    for sid, lang in (("ses", "Python"), ("ses-cpp", "C++")):
        item = items[sid]
        assert item["group"] == "Mail" and item["auth"] and item["port"] == 4579 and item["backup"]
        assert lang in item["label"] and item["gui"] == ["SES console"] and item["extra_ports"] == [2587]


def test_create_runs_the_python_server_with_capture_by_default(tmp_path):
    entry, calls = _create(tmp_path, user="AKIDLOCAL")
    create = next(c for c in calls if c[:2] == ["docker", "create"])
    env = _env_of(create)
    assert env["SES_ACCESS_KEY_ID"] == "AKIDLOCAL" and env["SES_SECRET_ACCESS_KEY"] == "Sup3r-secret-pw"
    assert env["SES_DELIVERY"] == "capture" and env["SES_VERIFY"] == "auto" and "SES_RELAY_HOST" not in env
    assert "127.0.0.1:4579:4579" in create and "127.0.0.1:2587:2587" in create
    assert create[-3:] == ["python:3.12-alpine", "python", "/app/server.py"]
    cp = next(c for c in calls if c[:2] == ["docker", "cp"])
    assert calls.index(create) < calls.index(cp) < calls.index(["docker", "start", entry["container"]])
    assert entry["resource"]["type"] == "custom" and entry["resource"]["connection"]["driver"] == "ses"
    assert entry["env"]["PSKIT_MAIL_URL"] == "http://127.0.0.1:4579"
    assert entry["env"]["PSKIT_MAIL_SMTP_PORT"] == "2587"
    assert entry["env"]["PSKIT_MAIL_SMTP_PASSWORD"] == _smtp_password("Sup3r-secret-pw", "us-east-1")
    assert entry["ses"] == {"delivery": "capture", "verify": "auto"}
    assert any("capture" in n for n in entry["notes"])
    assert svc.gui_links(entry)[0]["url"] == "http://127.0.0.1:4579/ui/"
    assert svc.public_entry(entry)["env"]["PSKIT_MAIL_SMTP_PASSWORD"] == "***"


def test_relay_settings_and_password(tmp_path):
    entry, calls = _create(tmp_path, ses_verify="dns", relay_host="smtp.office365.com:587", relay_user="app@corp.com",
                           relay_password="relay-pw-123", helo_name="mail.corp.com", port=14579)
    env = _env_of(next(c for c in calls if c[:2] == ["docker", "create"]))
    assert env["SES_DELIVERY"] == "relay" and env["SES_RELAY_HOST"] == "smtp.office365.com"
    assert env["SES_RELAY_PORT"] == "587" and env["SES_RELAY_TLS"] == "starttls"
    assert env["SES_RELAY_USER"] == "app@corp.com" and env["SES_RELAY_PASSWORD"] == "relay-pw-123"
    assert env["SES_VERIFY"] == "dns" and env["SES_HELO_NAME"] == "mail.corp.com"
    create = next(c for c in calls if c[:2] == ["docker", "create"])
    assert "127.0.0.1:14579:4579" in create and "127.0.0.1:12587:2587" in create  # the SMTP port moves along (+10000)
    assert "relay_password" not in json.dumps(entry["ses"]) and "relay-pw-123" not in json.dumps(entry["ses"])
    assert entry["env"]["PSKIT_MAIL_RELAY_PASSWORD"] == "relay-pw-123"


@pytest.mark.parametrize("body, message", [
    ({"ses_delivery": "relay"}, "relay_host"),
    ({"ses_delivery": "pigeon"}, "ses_delivery"),
    ({"ses_verify": "maybe"}, "ses_verify"),
    ({"relay_host": "-bad"}, "relay_host"),
    ({"ses_delivery": "direct", "relay_host": "smtp.x.com"}, "relay_host goes with"),
    ({"helo_name": "not a host"}, "helo_name"),
])
def test_bad_settings_are_refused(tmp_path, body, message):
    with pytest.raises(svc.ServiceError, match=message):
        _create(tmp_path, **body)


def test_cpp_service_compiles_in_a_stock_alpine_over_ssh(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "check_ssh_login", lambda _t: None)
    entry, calls = _create(tmp_path, service="ses-cpp", target=SSH, ses_delivery="direct")
    texts = [" ".join(c) for c in calls]
    create = next(t for t in texts if "docker 'create'" in t)
    assert "'alpine:3.20' 'sh' '/app/start.sh'" in create and "'0.0.0.0:2587:2587'" in create
    scps = sorted(t.rsplit("/", 1)[-1] for t in texts if t.startswith("scp") or " scp " in t)
    assert scps == ["Makefile", "src", "start.sh", "ui"]
    assert entry["env"]["PSKIT_MAIL_URL"] == "http://20.40.60.80:4579" and entry["ses"]["delivery"] == "direct"


def test_copied_files_are_the_repository_copy():
    python = onprem_ses.app_files("ses")
    assert python["server.py"] == (SOURCE / "python" / "server.py").read_bytes()
    assert "sesserver/operations.py" in python and not any("__pycache__" in n for n in python)
    assert python["ui/index.html"] == (SOURCE / "ui" / "index.html").read_bytes()
    assert any(n.startswith("ui/assets/js/") for n in python) and "Dockerfile" not in python
    cpp = onprem_ses.app_files("ses-cpp")
    assert cpp["start.sh"] == (SOURCE / "cpp" / "start.sh").read_bytes()
    assert any(n.startswith("src/") and n.endswith(".cpp") for n in cpp) and "Makefile" in cpp
    assert not any(n.startswith("build/") or n.startswith("data/") for n in cpp)


def test_usage_guide(tmp_path):
    _create(tmp_path, user="AKIDLOCAL")
    usage = svc.service_usage(tmp_path, "mail", probe=False)["markdown"]
    assert 'boto3.client(\n    "sesv2"' in usage and "SESv2Client" in usage and "smtplib.SMTP(" in usage
    assert "PSKIT_MAIL_SMTP_PASSWORD" in usage and "http://127.0.0.1:4579/ui/" in usage
    assert "nothing is sent" in usage
