"""The ``smtp`` on-prem service: a Node.js SMTP server that turns received mail into ``smtp`` events.

The container (``node:22-alpine``) installs nodemailer's ``smtp-server`` and ``mailparser`` once (cached in its
volume) and runs ``onprem_smtp.js``: it accepts mail for the given domains only (never a relay), parses it and
POSTs it to the pskit host (``POST /__pskit/smtp/<key>``), which runs every function with an ``smtp`` trigger on
the resource. When a function fails the sender gets a temporary error (451) and retries later.

On an SSH server the container uses the host network, so it reaches a pskit host bound to 127.0.0.1 and listens on
the port itself; on this machine (Docker Desktop) it publishes the port and reaches the host as
``host.docker.internal``.
"""

from __future__ import annotations

import base64
import ipaddress
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT = Path(__file__).with_name("onprem_smtp.js")
PACKAGES = "smtp-server@3 mailparser@3"
# Writes the script from the environment, installs the two packages once (kept in the volume), runs it.
START = (
    "set -e; mkdir -p /data/app; cd /data/app; "
    'printf %s "$PSKIT_SMTP_JS" | base64 -d > server.js; '
    "if [ ! -d node_modules/smtp-server ] || [ ! -d node_modules/mailparser ]; then "
    f"npm install --no-audit --no-fund --loglevel=error {PACKAGES}; fi; "
    "exec node server.js"
)
HEALTH = "cd /data/app && node server.js --check"
_DOMAIN = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(\.(?!-)[A-Za-z0-9-]{1,63})+$")
_URL = re.compile(r"^https?://[A-Za-z0-9_.:\[\]-]+(:\d+)?(/[^\s]*)?$")


def script_b64() -> str:
    return base64.b64encode(SCRIPT.read_bytes()).decode("ascii")


def _onprem_options(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    provider = (raw or {}).get("provider") or {}
    options = provider.get("options") if provider.get("name") == "onprem" else None
    if options is None:
        options = ((((raw or {}).get("providers") or {}).get("onprem") or {}).get("provider") or {}).get("options")
    return options if isinstance(options, dict) else {}


def admin_token(raw: Optional[Dict[str, Any]], root: Path, env_file: str) -> str:
    """The host's ``admin_token`` (``${env:NAME}`` read from the env file or this environment)."""
    from ..runtime.onprem_host import parse_env_text
    from .onprem_services import ServiceError

    token = str(_onprem_options(raw).get("admin_token") or "")
    match = re.fullmatch(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}", token)
    if match:
        path = root / env_file
        values = parse_env_text(path.read_text("utf-8")) if path.is_file() else {}
        token = values.get(match.group(1)) or os.environ.get(match.group(1), "")
        if not token:
            raise ServiceError(f"provider.options.admin_token reads {match.group(1)}, which is not set in {env_file} "
                               "or this environment: the SMTP server needs the token to call the functions")
    elif "${" in token:
        raise ServiceError("provider.options.admin_token: use a plain value or ${env:NAME} so the SMTP server can "
                           "send it to the host")
    return token


def check(body: Dict[str, Any], raw: Optional[Dict[str, Any]], root: Path, target: Dict[str, Any]) -> Dict[str, Any]:
    """Validated smtp settings of a create request: domains, functions_url, hostname, max_size_mb, network."""
    from .onprem_services import ServiceError

    domains = body.get("domains") or []
    if isinstance(domains, str):
        domains = [d for d in re.split(r"[\s,]+", domains) if d]
    if not isinstance(domains, list) or not domains:
        raise ServiceError("domains: list the domains this server receives mail for, e.g. inbound.example.com")
    for domain in domains:
        if not _DOMAIN.match(str(domain)):
            raise ServiceError(f"domains: {domain!r} is not a domain name")
    domains = [str(d).lower().rstrip(".") for d in domains]
    try:
        max_mb = float(body.get("max_size_mb") or 25)
    except (TypeError, ValueError):
        raise ServiceError("max_size_mb must be a number") from None
    if not 0 < max_mb <= 100:
        raise ServiceError("max_size_mb must be between 0 and 100")
    hostname = str(body.get("hostname") or f"mail.{domains[0]}").strip().lower()
    if not _DOMAIN.match(hostname):
        raise ServiceError("hostname must be a host name such as mail.example.com")
    network = "host" if target["method"] == "ssh" else "bridge"
    url = str(body.get("functions_url") or "").strip().rstrip("/")
    if url and not _URL.match(url):
        raise ServiceError("functions_url must be the pskit host's URL, e.g. http://10.0.0.5:8080")
    # A URL pskit picked follows the functions: `pskit deploy` points the server at where they run now.
    auto = not url
    if auto:
        url = auto_url(raw, root, target)
    return {"domains": domains, "functions_url": url, "functions_url_auto": auto, "hostname": hostname,
            "max_size_mb": max_mb, "network": network}


def auto_url(raw: Optional[Dict[str, Any]], root: Path, target: Dict[str, Any]) -> str:
    """The URL an SMTP server on ``target`` reaches the functions' host at, from where they run now."""
    from .onprem_services import ServiceError, functions_target

    port = int(_onprem_options(raw).get("port") or 8080)
    try:
        functions = functions_target(raw, root)
    except ServiceError as exc:
        raise ServiceError(f"{exc} Or set functions_url to the pskit host's URL (e.g. http://10.0.0.5:8080) "
                           "so the SMTP server knows where to send mail events") from None
    if functions["method"] == "local" and target["method"] == "ssh":
        functions = _cluster_of(root, target) or functions  # not deployed yet: they go to this server's cluster
    if target["method"] == "local":
        if functions["method"] != "local":
            raise ServiceError("the functions run on an SSH server: create the SMTP server there, or set "
                               "functions_url to the pskit host's URL")
        return f"http://host.docker.internal:{port}"
    if functions["method"] == "ssh" and functions.get("host") == target.get("host"):
        return f"http://127.0.0.1:{port}"  # same server, host network: reaches a host bound to 127.0.0.1
    if functions.get("cluster") and _in_cluster(root, str(functions["cluster"]), target):
        # Swarm publishes the port on every node (routing mesh); k3s and Nomad: the master's cluster address.
        here = functions.get("orchestrator") == "swarm"
        return f"http://{'127.0.0.1' if here else functions['address']}:{port}"
    if functions["method"] == "ssh":
        return f"http://{functions['host']}:{port}"
    raise ServiceError("the functions are not deployed to a server yet (they run on this machine, which the "
                       "SMTP server cannot reach): deploy them first (pskit deploy --server NAME or "
                       "--cluster NAME), create the SMTP server on a server of a scaling cluster, or set "
                       "functions_url to a URL of the pskit host it can reach")


def _follows_functions(smtp: Dict[str, Any], port: int) -> bool:
    """Whether pskit picked the server's functions URL (so it moves with them). Servers created before this was
    recorded: a plain ``http://<host>:<host port>`` is what pskit picks; a path or another port was typed in."""
    if "functions_url_auto" in smtp:
        return bool(smtp["functions_url_auto"])
    return bool(re.fullmatch(rf"http://[A-Za-z0-9_.\[\]:-]+:{port}", str(smtp.get("functions_url") or "")))


def retarget(root: Path, raw: Dict[str, Any], keys: List[str], emit: Any, *, run: Any = None) -> List[str]:
    """After a deploy: point the SMTP servers ``keys`` (the ones the deployed functions have ``smtp`` triggers on) at
    where the functions run now. A server whose URL pskit picked and that now differs (the functions moved to another
    server or cluster, or the old one was removed) is started again with the new URL; its data and installed
    packages stay in the volume. Only warns. Returns the keys that were changed."""
    from .onprem_services import ServiceError, _Runner, docker_argv, env_file_of, load_state, save_state

    state = load_state(root)
    port = int(_onprem_options(raw).get("port") or 8080)
    changed: List[str] = []
    for key in sorted(set(keys)):
        entry = (state.get("services") or {}).get(key)
        if not isinstance(entry, dict) or entry.get("service") != "smtp" or not isinstance(entry.get("smtp"), dict):
            continue
        smtp = dict(entry["smtp"])
        old = str(smtp.get("functions_url") or "")
        if not _follows_functions(smtp, port):
            continue
        target = entry.get("target") or {"method": "local"}
        try:
            new = auto_url(raw, root, target)
        except ServiceError as exc:
            emit(f"  WARNING: SMTP server {key!r} still sends mail to {old}: {exc}")
            continue
        if new == old:
            continue
        emit(f"SMTP server {key!r}: the functions moved, sending mail to {new} (was {old})")
        smtp.update(functions_url=new, functions_url_auto=True)
        req = {**entry, "smtp": smtp}
        sh = _Runner(emit, run)
        try:
            token = admin_token(raw, root, str(entry.get("env_file") or env_file_of(raw)))
            sh(docker_argv(target, ["rm", "-f", str(entry["container"])]), check=False, show=False)
            sh(docker_argv(target, run_args(req, token)))
        except (ServiceError, KeyError) as exc:
            emit(f"  WARNING: SMTP server {key!r} was not restarted: {exc}. Re-create it with the same key.")
            continue
        state["services"][key] = {**entry, "smtp": smtp}
        save_state(root, state)
        changed.append(key)
    return changed


def _in_cluster(root: Path, name: str, target: Dict[str, Any]) -> bool:
    """Whether the SMTP server's machine (a saved server, or its host) is a node of cluster ``name``."""
    from .onprem_cluster import load_clusters
    from .onprem_servers import load_servers

    nodes = (load_clusters(root).get(name) or {}).get("nodes") or {}
    if target.get("server") in nodes:
        return True
    servers = load_servers(root)
    return bool(target.get("host")) and any((servers.get(n) or {}).get("host") == target["host"] for n in nodes)


def _cluster_of(root: Path, target: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The functions' target on the one scaling cluster the SMTP server's machine belongs to, else None."""
    from .onprem_cluster import load_clusters
    from .onprem_services import ServiceError, functions_target

    names = [n for n in sorted(load_clusters(root)) if _in_cluster(root, n, target)]
    if len(names) != 1:
        return None
    try:
        return functions_target({"provider": {"name": "onprem", "options": {"cluster": names[0]}}}, root)
    except ServiceError:
        return None


def env(req: Dict[str, Any], token: str) -> Dict[str, str]:
    """The container's environment."""
    smtp = req["smtp"]
    host_network = smtp["network"] == "host"
    out = {
        "PSKIT_SMTP_NAME": req["key"],
        "PSKIT_SMTP_PORT": str(req["port"] if host_network else 25),
        "PSKIT_SMTP_BIND": req["bind"] if host_network else "0.0.0.0",  # noqa: S104 - inside the container
        "PSKIT_SMTP_DOMAINS": ",".join(smtp["domains"]),
        "PSKIT_SMTP_HOSTNAME": smtp["hostname"],
        "PSKIT_SMTP_MAX_MB": f"{smtp['max_size_mb']:g}",
        "PSKIT_FUNCTIONS_URL": smtp["functions_url"],
        "PSKIT_SMTP_JS": script_b64(),
    }
    if token:
        out["PSKIT_ADMIN_TOKEN"] = token
    return out


def run_args(req: Dict[str, Any], token: str) -> List[str]:
    """``docker run`` arguments of the SMTP container."""
    argv = ["run", "-d", "--name", req["container"], "--restart", "unless-stopped",
            "--label", "pskit.service=smtp", "--label", f"pskit.key={req['key']}"]
    if req["smtp"]["network"] == "host":
        argv += ["--network", "host"]
    else:
        argv += ["-p", f"{req['bind']}:{req['port']}:25", "--add-host", "host.docker.internal:host-gateway"]
    for name, value in env(req, token).items():
        argv += ["-e", f"{name}={value}"]
    argv += ["-v", f"{req['volume']}:/data", req["image"], "sh", "-c", START]
    return argv


def resource(req: Dict[str, Any]) -> Dict[str, Any]:
    smtp = req["smtp"]
    return {
        "type": "smtp",
        "external": True,
        "connection": {"host": req["address"], "port": req["port"], "domains": ",".join(smtp["domains"]),
                       "hostname": smtp["hostname"]},
    }


def _is_ip(address: str) -> bool:
    try:
        ipaddress.ip_address(address)
    except ValueError:
        return False
    return True


def _is_private(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def dns_records(entry: Dict[str, Any]) -> List[Dict[str, str]]:
    """The records to add at the domain's DNS provider."""
    smtp = entry.get("smtp") or {}
    hostname = str(smtp.get("hostname") or "mail.example.com")
    address = str(entry.get("address") or "")
    ip = address if address and not _is_private(address) and _is_ip(address) else "<public IP of the server>"
    rows = [{"type": "A", "name": hostname, "value": ip, "why": "the mail server's address"}]
    for domain in smtp.get("domains") or []:
        rows.append({"type": "MX", "name": domain, "value": f"10 {hostname}", "why": f"mail for *@{domain} goes here"})
    return rows


def usage_markdown(entry: Dict[str, Any]) -> str:
    """How to use: what the service does, the DNS records, testing and the handler code."""
    key = str(entry["key"])
    smtp = entry.get("smtp") or {}
    domains = list(smtp.get("domains") or ["example.com"])
    hostname = str(smtp.get("hostname") or f"mail.{domains[0]}")
    address, port = str(entry.get("address") or ""), int(entry.get("port") or 25)
    attach = list(entry.get("attach") or [])
    md: List[str] = [
        f"# SMTP server `{key}`\n",
        f"Receives mail for **{', '.join(domains)}** (and their subdomains) on `{address}:{port}` and runs the "
        f"functions with an `smtp` trigger on `{key}`"
        + (f" (now: {', '.join(f'`{f}`' for f in attach)})" if attach else "")
        + f". Mail for other domains is refused, so it is never an open relay. Each mail is posted to "
        f"`{smtp.get('functions_url')}/__pskit/smtp/{key}`; when a function fails the sending server gets a "
        "temporary error and tries again later.\n",
        "## 1. Add these records at your domain provider\n",
        "Sign in where your domain's DNS is managed (Cloudflare, GoDaddy, Namecheap, Route 53, Azure DNS, Google "
        "Cloud DNS, ...) and add:\n",
        "| Type | Name (host) | Value | Why |\n|---|---|---|---|\n"
        + "".join(f"| {r['type']} | `{r['name']}` | `{r['value']}` | {r['why']} |\n" for r in dns_records(entry)),
        "- **Name**: most providers want only the part before your root domain (`mail` for "
        "`mail.example.com`, `inbound` for `inbound.example.com`, `@` for the root domain itself).\n"
        "- **MX priority** is the `10`; some providers have a separate field for it.\n"
        "- **Cloudflare**: set the A record to *DNS only* (grey cloud). Cloudflare's proxy does not carry mail.\n"
        "- **Already receive mail on the root domain** (Microsoft 365, Google Workspace)? Do **not** change its MX: "
        "use a subdomain such as `inbound.example.com` here, or every mailbox of the company stops receiving mail.\n"
        "- Optional, for a subdomain that only receives: `TXT <subdomain> \"v=spf1 -all\"` tells the world it "
        "never sends mail, so nobody can send spoofed mail from it.\n",
    ]
    if _is_private(address):
        md.append(f"`{address}` is a private address: the A record must hold the server's **public** IP.\n")
    md.append(
        "## 2. Open the port\n\n"
        + (f"Senders always connect to port **25**. This server listens on {port}: forward 25 to it "
           f"(`sudo iptables -t nat -A PREROUTING -p tcp --dport 25 -j REDIRECT --to-port {port}`) or recreate it "
           "on port 25.\n\n" if port != 25 else "")
        + "Allow inbound TCP 25 from anywhere in the server's firewall (Azure: network security group; AWS: "
        "security group; GCP: VPC firewall rule; Linux: `sudo ufw allow 25/tcp`). Cloud providers block "
        "*outbound* 25, which does not matter here: this server only receives.\n"
    )
    first = domains[0]
    md.append(
        "## 3. Check it\n\n"
        "DNS changes take a few minutes (sometimes hours) to show up:\n\n"
        f"```bash\nnslookup -type=mx {first}          # -> {hostname}\nnslookup {hostname}            # -> the server's IP\n"
        f"pskit resources onprem logs {key}   # every mail is logged with sender, recipients and result\n```\n\n"
        "Send a test mail from any mail account to `anything@" + first + "`, or with Python:\n\n"
        "```python\nimport smtplib\nfrom email.message import EmailMessage\n\nmsg = EmailMessage()\n"
        f'msg["From"], msg["To"], msg["Subject"] = "me@example.org", "test@{first}", "Hello"\n'
        'msg.set_content("It works.")\n'
        f'with smtplib.SMTP("{address}", {port}, timeout=30) as s:\n    s.send_message(msg)\n```\n'
    )
    md.append(
        "## 4. Read the mail in a function\n\n"
        f"The trigger in `pskit.yml`:\n\n```yaml\nfunctions:\n  on-mail:\n    handler: handler.on_mail\n"
        f"    events:\n      - smtp: {{resource: {key}}}\n```\n\n"
        "`event.data` holds the mail:\n\n"
        "```python\nimport base64\n\n\ndef on_mail(event, context):\n    mail = event.data\n"
        '    print(mail["from"], mail["to"], mail["cc"], mail["subject"])\n'
        '    body = mail["text"] or mail["html"]\n'
        '    for att in mail["attachments"]:\n'
        '        data = base64.b64decode(att["content"])  # bytes\n'
        '        print(att["filename"], att["content_type"], att["size"])\n'
        '    return {"ok": True}\n```\n\n'
        "```javascript\nexports.onMail = async (event) => {\n  const mail = event.data;\n"
        "  console.log(mail.from, mail.to, mail.subject, mail.text);\n"
        '  for (const att of mail.attachments) Buffer.from(att.content, "base64");\n'
        "  return { ok: true };\n};\n```\n\n"
        "| Field | |\n|---|---|\n"
        "| `from`, `from_name` | sender address and display name |\n"
        "| `to`, `cc`, `bcc`, `reply_to` | address lists (`bcc`: recipients not in To / Cc) |\n"
        "| `subject`, `date`, `message_id`, `in_reply_to`, `references` | |\n"
        "| `text`, `html` | the body |\n"
        "| `headers` | `{lower-case name: value}` (first of each) |\n"
        "| `attachments` | `[{filename, content_type, disposition, size, content_id, checksum, content}]`, "
        "`content` in base64 |\n"
        "| `envelope` | `{mail_from, rcpt_to}`: the SMTP envelope |\n"
        "| `remote_ip`, `helo`, `tls`, `size`, `received_at`, `server`, `id` | about the delivery |\n"
        "| `Records` | the Amazon SES receipt event (`Records[0].ses.mail` / `.receipt`) |\n"
        "| `content` | the raw message in base64 (`content_encoding: BASE64`) |\n\n"
        "**Code written for Amazon SES** works unchanged on the same data: "
        '`event.data["Records"][0]["ses"]["mail"]["commonHeaders"]["subject"]`, or the whole message with '
        '`email.message_from_bytes(base64.b64decode(event.data["content"]))` (what an SES -> SNS action with '
        "BASE64 encoding gives). pskit does not scan for spam or viruses nor check SPF / DKIM / DMARC: those "
        "verdicts are `GRAY`.\n"
    )
    md.append(
        "## Settings\n\n"
        f"- Change domains, port or the functions' URL: remove `{key}` and create it again with the same key.\n"
        "- Functions moved to another server or cluster (or the old one was removed)? `pskit deploy` points this "
        "server at where they run now (unless you typed the functions' URL when creating it).\n"
        "- Attach another function: add `- smtp: {resource: " + key + "}` to its `events` (or *Trigger functions* "
        "when creating) and deploy; the SMTP server needs no change.\n"
        "- The host's `admin_token` changed? Recreate the service so it sends the new one.\n"
    )
    return "\n".join(md)


def _addresses(value: Any) -> List[str]:
    if not value:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [s.strip() for s in str(value).split(",") if s.strip()]


def test_event(data: Any, server: str = "smtp") -> Dict[str, Any]:
    """A test mail (``{"from", "to", "cc", "subject", "text", "html", "attachments": [{"filename", "content_type",
    "content" or "content_base64"}]}``) as the event the SMTP service sends; a full event is returned unchanged."""
    import email.utils
    import hashlib
    import secrets
    from datetime import datetime, timezone
    from email.message import EmailMessage

    if isinstance(data, dict) and "Records" in data:
        return data
    data = data if isinstance(data, dict) else {"text": "" if data is None else str(data)}
    sender_header = str(data.get("from") or "sender@example.org")
    from_name, sender = email.utils.parseaddr(sender_header)
    to = [email.utils.parseaddr(a)[1] for a in _addresses(data.get("to") or "test@example.com")]
    cc = [email.utils.parseaddr(a)[1] for a in _addresses(data.get("cc"))]
    bcc = [email.utils.parseaddr(a)[1] for a in _addresses(data.get("bcc"))]
    now = datetime.now(timezone.utc)
    msg = EmailMessage()
    msg["From"] = sender_header
    msg["To"] = ", ".join(_addresses(data.get("to") or "test@example.com"))
    if cc:
        msg["Cc"] = ", ".join(_addresses(data.get("cc")))
    msg["Subject"] = str(data.get("subject") or "")
    msg["Date"] = email.utils.format_datetime(now)
    msg["Message-ID"] = email.utils.make_msgid(domain="pskit.test")
    msg.set_content(str(data.get("text") or ""))
    if data.get("html"):
        msg.add_alternative(str(data["html"]), subtype="html")
    attachments = []
    for att in data.get("attachments") or []:
        content = (base64.b64decode(att["content_base64"]) if att.get("content_base64")
                   else str(att.get("content") or "").encode("utf-8"))
        ctype = str(att.get("content_type") or "application/octet-stream")
        maintype, _, subtype = ctype.partition("/")
        name = str(att.get("filename") or "attachment")
        msg.add_attachment(content, maintype=maintype, subtype=subtype or "octet-stream", filename=name)
        attachments.append({"filename": name, "content_type": ctype, "disposition": "attachment",
                            "size": len(content), "content_id": "", "checksum": hashlib.md5(content).hexdigest(),  # noqa: S324
                            "content": base64.b64encode(content).decode("ascii")})
    raw = msg.as_bytes()
    recipients = to + cc + bcc
    headers = [{"name": k, "value": str(v)} for k, v in msg.items()]
    ident = secrets.token_hex(20)
    stamp = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    common: Dict[str, Any] = {"returnPath": sender, "from": [sender_header], "date": msg["Date"],
                              "to": _addresses(data.get("to") or "test@example.com"), "messageId": msg["Message-ID"],
                              "subject": msg["Subject"]}
    if cc:
        common["cc"] = _addresses(data.get("cc"))
    gray = {"status": "GRAY"}
    return {
        "id": ident, "server": server, "received_at": stamp, "from": sender, "from_name": from_name,
        "to": to, "cc": cc, "bcc": bcc, "reply_to": [], "subject": msg["Subject"], "date": stamp,
        "message_id": msg["Message-ID"], "in_reply_to": "", "references": [],
        "text": str(data.get("text") or ""), "html": str(data.get("html") or ""),
        "headers": {h["name"].lower(): h["value"] for h in reversed(headers)},
        "attachments": attachments, "envelope": {"mail_from": sender, "rcpt_to": recipients},
        "remote_ip": "127.0.0.1", "helo": "pskit-test", "tls": False, "size": len(raw),
        "Records": [{"eventSource": "aws:ses", "eventVersion": "1.0", "ses": {
            "mail": {"timestamp": stamp, "source": sender, "messageId": ident, "destination": recipients,
                     "headersTruncated": False, "headers": headers, "commonHeaders": common},
            "receipt": {"timestamp": stamp, "processingTimeMillis": 0, "recipients": recipients,
                        "spamVerdict": gray, "virusVerdict": gray, "spfVerdict": gray, "dkimVerdict": gray,
                        "dmarcVerdict": gray, "action": {"type": "Lambda", "invocationType": "RequestResponse"}},
        }}],
        "content": base64.b64encode(raw).decode("ascii"),
        "content_encoding": "BASE64",
    }
