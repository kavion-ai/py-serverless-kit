"""The ``ses`` / ``ses-cpp`` on-prem services: pskit's Amazon SES compatible server.

The server's code lives in ``aws/ses`` at the repository root: ``python/server.py`` + ``python/sesserver/``
(standard library only), ``cpp/`` (C++17 + OpenSSL: ``start.sh``, ``Makefile``, ``src/``), the web console ``ui/``
and a Dockerfile for each (see ``aws/ses/ARCHITECTURE.md``). The wheel ships that folder as
``py_serverless_kit/aws``.

Like the Secrets Manager and S3 servers, nothing is built or pushed: the Python server runs on the stock
``python:3.12-alpine`` image; the C++ server on ``alpine:3.20``, where ``start.sh`` installs the compiler once,
compiles the server into the volume (again only when the sources change) and runs it. ``docker create``, ``docker
cp`` of ``/app`` (scp first over SSH) and ``docker start``.

Clients sign with SigV4 using the service's user as the access key ID and its password as the secret access key
(boto3 ``ses`` / ``sesv2``, the AWS SDKs and CLI). The SMTP endpoint (port 2587) takes the same user with the SES SMTP
password derived from the secret key. Mail goes out through a relay (``ses_delivery: relay``), straight to the
recipients' MX hosts (``direct``) or stays in the console (``capture``, the default: nothing leaves until you choose).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from pathlib import Path
from typing import Any, Dict, List

from . import onprem_secretsmanager

PORT = 4579
SMTP_PORT = 2587
REGION = "us-east-1"
# service id -> how it runs
SERVICES: Dict[str, Dict[str, Any]] = {
    "ses": {"dir": "python", "image": "python:3.12-alpine", "lang": "Python",
            "command": ["python", "/app/server.py"], "check": "python /app/server.py --check"},
    "ses-cpp": {"dir": "cpp", "image": "alpine:3.20", "lang": "C++",
                "command": ["sh", "/app/start.sh"], "check": "sh /app/start.sh --check"},
}
UI_FILE = "ui/index.html"
DELIVERY = ("capture", "direct", "relay")
VERIFY = ("auto", "dns", "manual", "off")
_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
_HELO = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(\.(?!-)[A-Za-z0-9-]{1,63})+$")
# What the C++ build needs from the source tree (the build output and caches stay out).
_CPP_PARTS = ("start.sh", "Makefile", "src")


def source_dir() -> Path:
    """``aws/ses``: installed in the wheel, or the repository's copy in a source checkout."""
    here = Path(__file__).resolve().parent.parent
    for candidate in (here / "aws" / "ses", here.parents[1] / "aws" / "ses"):
        if (candidate / UI_FILE).is_file():
            return candidate
    raise FileNotFoundError("aws/ses is missing from this installation of py-serverless-kit")


def app_files(service: str) -> Dict[str, bytes]:
    """The files of ``/app`` in the container: the server (Python modules, or the C++ sources and start.sh) and the
    console under ``ui/``."""
    base = source_dir()
    tree = onprem_secretsmanager._tree  # noqa: SLF001 - the same copy rules (no caches, hidden files, Dockerfile)
    server = base / SERVICES[service]["dir"]
    if service == "ses":
        files = tree(server)
    else:
        files = {}
        for part in _CPP_PARTS:
            path = server / part
            if path.is_dir():
                files.update(tree(path, f"{part}/"))
            elif path.is_file():
                files[part] = path.read_bytes()
    return {**files, **tree(base / "ui", "ui/")}


def health(service: str) -> str:
    return str(SERVICES[service]["check"])


def check(body: Dict[str, Any]) -> Dict[str, Any]:
    """Validated SES settings of a create request: delivery mode, relay, verification mode, HELO name."""
    from .onprem_services import ServiceError

    delivery = str(body.get("ses_delivery") or ("relay" if body.get("relay_host") else "capture")).lower()
    if delivery not in DELIVERY:
        raise ServiceError(f"ses_delivery must be one of {', '.join(DELIVERY)}")
    verify = str(body.get("ses_verify") or "auto").lower()
    if verify not in VERIFY:
        raise ServiceError(f"ses_verify must be one of {', '.join(VERIFY)}")
    out: Dict[str, Any] = {"delivery": delivery, "verify": verify}
    helo = str(body.get("helo_name") or "").strip().lower()
    if helo and not _HELO.match(helo):
        raise ServiceError("helo_name must be a host name such as mail.example.com")
    if helo:
        out["helo_name"] = helo
    relay = str(body.get("relay_host") or "").strip()
    if delivery == "relay":
        host, _sep, port_text = relay.partition(":")
        if not host or not _HOST.match(host) or host.startswith("-"):
            raise ServiceError("relay_host must be the SMTP relay's host[:port], e.g. smtp.office365.com:587")
        try:
            port = int(body.get("relay_port") or port_text or 587)
        except ValueError:
            raise ServiceError("relay_port must be a number") from None
        if not 1 <= port <= 65535:
            raise ServiceError("relay_port must be between 1 and 65535")
        tls = str(body.get("relay_tls") or ("tls" if port == 465 else "starttls")).lower()
        if tls not in ("starttls", "tls", "none"):
            raise ServiceError("relay_tls must be starttls, tls or none")
        out.update(relay_host=host, relay_port=port, relay_tls=tls, relay_user=str(body.get("relay_user") or ""))
    elif relay:
        raise ServiceError("relay_host goes with ses_delivery: relay")
    return out


def env(req: Dict[str, Any], password: str) -> Dict[str, str]:
    """The container's environment."""
    ses = req.get("ses") or {"delivery": "capture", "verify": "auto"}
    out = {
        "SES_PORT": str(PORT),
        "SES_SMTP_PORT": str(SMTP_PORT),
        "SES_BIND": "0.0.0.0",  # noqa: S104 - inside the container; the published ports decide who reaches it
        "SES_DATA_DIR": "/data",
        "SES_REGION": REGION,
        "SES_ACCESS_KEY_ID": str(req.get("user") or "pskit"),
        "SES_SECRET_ACCESS_KEY": password,
        "SES_DELIVERY": ses["delivery"],
        "SES_VERIFY": ses["verify"],
        "SES_SMTP_HOST": str(req.get("address") or ""),
        "PYTHONUNBUFFERED": "1",
    }
    if ses.get("helo_name"):
        out["SES_HELO_NAME"] = ses["helo_name"]
    if ses["delivery"] == "relay":
        out.update(SES_RELAY_HOST=ses["relay_host"], SES_RELAY_PORT=str(ses["relay_port"]),
                   SES_RELAY_TLS=ses["relay_tls"])
        if ses.get("relay_user"):
            out["SES_RELAY_USER"] = ses["relay_user"]
        if req.get("relay_password"):
            out["SES_RELAY_PASSWORD"] = str(req["relay_password"])
    return out


def create_args(req: Dict[str, Any], password: str) -> List[str]:
    """``docker create`` arguments of the server container (started after the files are copied in)."""
    from .onprem_services import host_port

    argv = ["create", "--name", req["container"], "--restart", "unless-stopped",
            "--label", f"pskit.service={req['service']}", "--label", f"pskit.key={req['key']}",
            "-p", f"{req['bind']}:{req['port']}:{PORT}",
            "-p", f"{req['bind']}:{host_port(req, SMTP_PORT)}:{SMTP_PORT}"]
    for name, value in env(req, password).items():
        argv += ["-e", f"{name}={value}"]
    if req.get("volume"):
        argv += ["-v", f"{req['volume']}:/data"]
    argv += [req["image"], *SERVICES[req["service"]]["command"]]
    return argv


def launch(req: Dict[str, Any], password: str, target: Dict[str, Any], sh: Any) -> None:
    onprem_secretsmanager.start_with_app(req, target, sh, create_args(req, password), app_files(req["service"]))


def smtp_password(secret: str, region: str = REGION) -> str:
    """The SES SMTP password of a secret access key (AWS's published algorithm, version 4)."""
    key = ("AWS4" + secret).encode("utf-8")
    for part in ("11111111", region, "ses", "aws4_request", "SendRawEmail"):
        key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(b"\x04" + key).decode("ascii")


def resource(req: Dict[str, Any], password: str, prefix: str) -> Dict[str, Any]:
    """(env values, resource connection) for boto3 / the AWS SDKs and SMTP clients."""
    from .onprem_services import host_port

    url = f"http://{req['address']}:{req['port']}"
    user = str(req.get("user") or "pskit")
    smtp_port = host_port(req, SMTP_PORT)
    values = {f"{prefix}_URL": url, f"{prefix}_REGION": REGION, f"{prefix}_ACCESS_KEY": user,
              f"{prefix}_SECRET_KEY": password, f"{prefix}_SMTP_HOST": str(req["address"]),
              f"{prefix}_SMTP_PORT": str(smtp_port), f"{prefix}_SMTP_USER": user,
              f"{prefix}_SMTP_PASSWORD": smtp_password(password)}
    if req.get("relay_password"):
        values[f"{prefix}_RELAY_PASSWORD"] = str(req["relay_password"])
    conn = {"driver": "ses", "url": url, "region": REGION, "access_key_env": f"{prefix}_ACCESS_KEY",
            "secret_key_env": f"{prefix}_SECRET_KEY", "smtp_host": str(req["address"]), "smtp_port": smtp_port,
            "smtp_user_env": f"{prefix}_SMTP_USER", "smtp_password_env": f"{prefix}_SMTP_PASSWORD",
            "console_url": f"{url}/ui/", "delivery": (req.get("ses") or {}).get("delivery", "capture")}
    return {"env": values, "connection": conn}


def usage_markdown(entry: Dict[str, Any], prefix: str) -> str:
    """How to use: boto3 (sesv2 and ses), the AWS SDK for JavaScript, nodemailer over SMTP, the AWS CLI, the
    console, delivery and DNS."""
    from .onprem_services import host_port

    url = f"http://{entry.get('address')}:{entry.get('port')}"
    user = str(entry.get("user") or "pskit")
    smtp_port = host_port(entry, SMTP_PORT)
    lang = SERVICES.get(str(entry.get("service")), SERVICES["ses"])["lang"]
    ses = entry.get("ses") or {"delivery": "capture", "verify": "auto"}
    env_file = str(entry.get("env_file") or ".env.onprem")
    delivery = {
        "capture": "**capture**: mail is accepted, signed and kept in the console, and *nothing is sent*. Good for "
                   "development; create the service again with `ses_delivery: direct` or `relay` to send for real.",
        "direct": "**direct**: the server delivers to each recipient domain's MX hosts on port 25. The server needs "
                  "outbound port 25 (most clouds block it: ask your provider, or use a relay), a public IP with "
                  "reverse DNS matching its HELO name, and SPF / DKIM records for your domains.",
        "relay": f"**relay** through `{ses.get('relay_host')}:{ses.get('relay_port')}` ({ses.get('relay_tls')}"
                 + (f", user `{ses['relay_user']}`" if ses.get("relay_user") else "") + "): your mail provider "
                 "(Microsoft 365, Google Workspace, Postfix, SendGrid, ...) sends it on.",
    }[ses["delivery"]]
    return (
        "## Use it like Amazon SES\n\n"
        f"pskit's own Amazon SES compatible server ({lang}, code in `aws/ses`) answers the SES v1 (`ses`) and v2 "
        f"(`sesv2`) APIs at the endpoint below. Every request is checked with AWS Signature Version 4: sign with "
        f"access key ID `{user}` and the password as the secret access key (`{prefix}_ACCESS_KEY` / "
        f"`{prefix}_SECRET_KEY` in `{env_file}`).\n\n"
        "| | |\n|---|---|\n"
        f"| API endpoint | `{url}` (region `{REGION}`) |\n"
        f"| SMTP endpoint | `{entry.get('address')}:{smtp_port}`, user `{user}`, password `{prefix}_SMTP_PASSWORD` "
        "(the SES SMTP password of the secret key; the secret key works too) |\n"
        f"| Web console | {url}/ui/ (access key ID `{user}`, password = secret key) |\n"
        f"| Delivery | {delivery} |\n"
        f"| Sender verification | `{ses['verify']}` (see below) |\n\n"
        "### 1. Verify a sender\n\n"
        "As on SES, the From address must be a verified identity: a domain (every address of it and its subdomains) "
        "or one address. Create it in the console (*Identities > Create identity*) or with the API; the console "
        "lists the DNS records to publish: DKIM (`<selector>._domainkey.<domain>` TXT, pskit signs your mail with "
        "it once it is found in DNS), SPF and DMARC.\n\n"
        "```python\nimport os\n\nimport boto3\n\n"
        "ses = boto3.client(\n    \"sesv2\",\n"
        f'    endpoint_url=os.environ["{prefix}_URL"],            # {url}\n'
        f'    region_name="{REGION}",\n'
        f'    aws_access_key_id=os.environ["{prefix}_ACCESS_KEY"],\n'
        f'    aws_secret_access_key=os.environ["{prefix}_SECRET_KEY"],\n)\n'
        'ses.create_email_identity(EmailIdentity="example.com")\n```\n\n'
        "### 2. Send\n\n"
        "```python\nses.send_email(\n    FromEmailAddress=\"App <no-reply@example.com>\",\n"
        '    Destination={"ToAddresses": ["user@example.org"]},\n'
        '    Content={"Simple": {"Subject": {"Data": "Hello"},\n'
        '                        "Body": {"Text": {"Data": "Hi!"}, "Html": {"Data": "<b>Hi!</b>"}}}},\n)\n\n'
        "# SES v1 works too: boto3.client(\"ses\", ...).send_email(Source=..., Destination=..., Message=...)\n```\n\n"
        "AWS SDK for JavaScript v3 (and nodemailer's SES transport, which uses it):\n\n"
        "```js\nconst { SESv2Client, SendEmailCommand } = require(\"@aws-sdk/client-sesv2\");\n\n"
        "const ses = new SESv2Client({\n"
        f"  endpoint: process.env.{prefix}_URL,\n  region: \"{REGION}\",\n"
        f"  credentials: {{ accessKeyId: process.env.{prefix}_ACCESS_KEY, secretAccessKey: process.env.{prefix}_SECRET_KEY }},\n"
        "});\n"
        "await ses.send(new SendEmailCommand({\n  FromEmailAddress: \"no-reply@example.com\",\n"
        "  Destination: { ToAddresses: [\"user@example.org\"] },\n"
        "  Content: { Simple: { Subject: { Data: \"Hello\" }, Body: { Text: { Data: \"Hi!\" } } } },\n}));\n```\n\n"
        "SMTP (any language, framework or appliance):\n\n"
        "```python\nimport os\nimport smtplib\nfrom email.message import EmailMessage\n\n"
        'msg = EmailMessage()\nmsg["From"], msg["To"], msg["Subject"] = "no-reply@example.com", "user@example.org", "Hi"\n'
        'msg.set_content("Sent through the SES SMTP endpoint.")\n'
        f'with smtplib.SMTP(os.environ["{prefix}_SMTP_HOST"], int(os.environ["{prefix}_SMTP_PORT"])) as smtp:\n'
        f'    smtp.login(os.environ["{prefix}_SMTP_USER"], os.environ["{prefix}_SMTP_PASSWORD"])\n'
        "    smtp.send_message(msg)\n```\n\n"
        "AWS CLI:\n\n"
        f"```bash\nexport AWS_ACCESS_KEY_ID={user} AWS_SECRET_ACCESS_KEY='<{prefix}_SECRET_KEY>' "
        f"AWS_DEFAULT_REGION={REGION}\n"
        f"aws --endpoint-url {url} sesv2 create-email-identity --email-identity example.com\n"
        f"aws --endpoint-url {url} ses send-email --from no-reply@example.com --to user@example.org "
        "--subject Hi --text 'Hello'\n"
        f"aws --endpoint-url {url} sesv2 get-account\n```\n\n"
        "Code written for SES runs unchanged: on AWS, leave out `endpoint_url` and the keys (or set "
        f"`AWS_ENDPOINT_URL_SESV2={url}` and keep the code identical everywhere).\n\n"
        "### What it does like SES\n\n"
        "Templates (Handlebars: `{{name}}`, `{{#if}}`, `{{#each}}`), bulk sending, configuration sets, the "
        "account-level suppression list (permanent bounces are added), sending quotas (`SES_MAX_24H`, "
        "`SES_MAX_RATE`), the mailbox simulator (`success@simulator.amazonses.com`, `bounce@...`, `complaint@...`), "
        "DKIM signing, custom MAIL FROM, retries for up to 12 hours with `DeliveryDelay` and `Bounce` events. Every "
        "message, its per-recipient result and events are in the console (*Messages*). Set `SES_EVENTS_URL` on the "
        "container to receive each event as JSON in the SES event publishing format.\n\n"
        "### Sender verification modes\n\n"
        "`auto` (default) verifies a new identity at once; `dns` verifies a domain when its DKIM or "
        "`_amazonses.<domain>` TXT record is found; `manual` waits for *Mark as verified* in the console; `off` "
        "allows any From address. Pick one with `--ses-verify` when creating the service.\n"
    )
