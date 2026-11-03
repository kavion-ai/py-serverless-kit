"""The ``secretsmanager`` / ``secretsmanager-node`` on-prem services: pskit's AWS Secrets Manager compatible server.

The server's code lives in ``aws/secretsmanager`` at the repository root: ``python/server.py`` (standard library
only), ``nodejs/server.js`` (no npm packages), the web console ``ui/index.html`` and a Dockerfile for each. The wheel
ships that folder as ``py_serverless_kit/aws`` (hatch ``force-include``); a source checkout reads it in place.

pskit runs it on the stock ``python:3.12-alpine`` / ``node:22-alpine`` image, so nothing has to be built or pushed:
``docker create`` makes the container, ``docker cp`` puts the server and the console page in ``/app`` (over SSH they
are copied to the server with scp first) and ``docker start`` runs it. They are too large for an environment variable
(Windows command lines stop at 32 KB, an SSH command at 128 KB). Clients sign with SigV4 using the service's user as
the access key ID and its password as the secret access key, which also sign in to the console at ``/ui/``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

PORT = 4584
# service id -> (server file in aws/secretsmanager, interpreter)
SERVICES: Dict[str, Dict[str, str]] = {
    "secretsmanager": {"file": "python/server.py", "run": "python", "image": "python:3.12-alpine", "lang": "Python"},
    "secretsmanager-node": {"file": "nodejs/server.js", "run": "node", "image": "node:22-alpine", "lang": "Node.js"},
}
UI_FILE = "ui/index.html"


def source_dir() -> Path:
    """``aws/secretsmanager``: installed in the wheel, or the repository's copy in a source checkout."""
    here = Path(__file__).resolve().parent.parent
    for candidate in (here / "aws" / "secretsmanager", here.parents[1] / "aws" / "secretsmanager"):
        if (candidate / UI_FILE).is_file():
            return candidate
    raise FileNotFoundError("aws/secretsmanager is missing from this installation of py-serverless-kit")


def script_name(service: str) -> str:
    return Path(SERVICES[service]["file"]).name


def app_files(service: str) -> Dict[str, bytes]:
    """The files of ``/app`` in the container: the server and the console page."""
    base = source_dir()
    return {script_name(service): (base / SERVICES[service]["file"]).read_bytes(),
            "index.html": (base / UI_FILE).read_bytes()}


def health(service: str) -> str:
    return f"{SERVICES[service]['run']} /app/{script_name(service)} --check"


def env(req: Dict[str, Any], password: str) -> Dict[str, str]:
    """The container's environment. ``SM_MASTER_KEY`` (generated once, kept in the env file) encrypts the values at
    rest; without it the data could not be read back after the service is re-created."""
    out = {
        "SM_PORT": str(PORT),
        "SM_BIND": "0.0.0.0",  # noqa: S104 - inside the container; the published port decides who reaches it
        "SM_DATA_DIR": "/data",
        "SM_REGION": "us-east-1",
        "SM_ACCESS_KEY_ID": str(req.get("user") or "pskit"),
        "SM_SECRET_ACCESS_KEY": password,
        "PYTHONUNBUFFERED": "1",
    }
    master = (req.get("generated") or {}).get("master_key")
    if master:
        out["SM_MASTER_KEY"] = str(master)
    return out


def create_args(req: Dict[str, Any], password: str) -> List[str]:
    """``docker create`` arguments of the server container (started after the files are copied in)."""
    argv = ["create", "--name", req["container"], "--restart", "unless-stopped",
            "--label", f"pskit.service={req['service']}", "--label", f"pskit.key={req['key']}",
            "-p", f"{req['bind']}:{req['port']}:{PORT}"]
    for name, value in env(req, password).items():
        argv += ["-e", f"{name}={value}"]
    if req.get("volume"):
        argv += ["-v", f"{req['volume']}:/data"]
    argv += [req["image"], SERVICES[req["service"]]["run"], f"/app/{script_name(req['service'])}"]
    return argv


def launch(req: Dict[str, Any], password: str, target: Dict[str, Any], sh: Any) -> None:
    """Create the container, copy ``/app`` into it and start it. ``sh`` is the services runner."""
    start_with_app(req, target, sh, create_args(req, password), app_files(req["service"]))


def start_with_app(req: Dict[str, Any], target: Dict[str, Any], sh: Any, create: List[str],
                   files: Dict[str, bytes]) -> None:
    """``docker create``, copy ``files`` into the container's ``/app`` (scp first over SSH) and ``docker start``."""
    from ..providers.onprem_remote import scp_argv
    from .onprem_services import _ssh_argv, docker_argv, ssh_options

    container = req["container"]
    sh(docker_argv(target, create))
    with tempfile.TemporaryDirectory() as tmp:
        app = Path(tmp) / "app"
        app.mkdir()
        for name, data in files.items():
            (app / name).write_bytes(data)
        if target.get("method") == "ssh":
            remote = f"/tmp/pskit-{container}-app"  # noqa: S108 - removed right after
            sh(_ssh_argv(target, f"rm -rf {remote} && mkdir -p {remote}"), show=False)
            ssh = ssh_options(target)
            for name in sorted(os.listdir(app)):
                sh(scp_argv(ssh, str(app / name), f"{remote}/{name}"))
            sh(docker_argv(target, ["cp", f"{remote}/.", f"{container}:/app"]))
            sh(_ssh_argv(target, f"rm -rf {remote}"), check=False, show=False)
        else:
            sh(docker_argv(target, ["cp", f"{app}{os.sep}.", f"{container}:/app"]))
    sh(docker_argv(target, ["start", container]))


def connection(req: Dict[str, Any], password: str, prefix: str) -> Dict[str, Any]:
    """(env values, resource connection) for ``get_secret()`` and the AWS SDKs."""
    url = f"http://{req['address']}:{req['port']}"
    user = str(req.get("user") or "pskit")
    values = {f"{prefix}_DRIVER": "aws", f"{prefix}_URL": url, f"{prefix}_REGION": "us-east-1",
              f"{prefix}_ACCESS_KEY": user, f"{prefix}_SECRET_KEY": password}
    conn = {"driver": "aws", "url": url, "region": "us-east-1", "access_key_env": f"{prefix}_ACCESS_KEY",
            "secret_key_env": f"{prefix}_SECRET_KEY", "console_url": f"{url}/ui/"}
    return {"env": values, "connection": conn}


def usage_markdown(entry: Dict[str, Any], prefix: str) -> str:
    """How to use: get_secret(), boto3, the AWS SDK for JavaScript, the AWS CLI and the console."""
    key = str(entry["key"])
    url = f"http://{entry.get('address')}:{entry.get('port')}"
    user = str(entry.get("user") or "pskit")
    lang = SERVICES.get(str(entry.get("service")), SERVICES["secretsmanager"])["lang"]
    env_file = str(entry.get("env_file") or ".env.onprem")
    py_store, js_store = ("", "") if key == "secrets" else (f', store="{key}"', f', {{ store: "{key}" }}')
    return (
        "## Use it like AWS Secrets Manager\n\n"
        f"pskit's own Secrets Manager compatible server ({lang}, code in `aws/secretsmanager`) answers the Secrets "
        "Manager API at the endpoint below. Every request is checked with AWS Signature Version 4: sign with access "
        f"key ID `{user}` and the password as the secret access key (`{prefix}_ACCESS_KEY` / `{prefix}_SECRET_KEY` "
        f"in `{env_file}`). Any region works; ARNs carry the region you sign with.\n\n"
        "| | |\n|---|---|\n"
        f"| Endpoint | `{url}` |\n| Web console | {url}/ui/ (access key ID `{user}`, password = secret key) |\n"
        "| Operations | CreateSecret, GetSecretValue, BatchGetSecretValue, PutSecretValue, UpdateSecret, DescribeSecret, "
        "ListSecrets (filters, paging), DeleteSecret (recovery window or force), RestoreSecret, ListSecretVersionIds, "
        "UpdateSecretVersionStage, TagResource, UntagResource, GetRandomPassword, resource policies |\n"
        "| Not supported | rotation (RotateSecret) and replica regions |\n\n"
        "### In pskit functions\n\n"
        "```python\nfrom py_serverless_kit import get_secret, put_secret\n\n\ndef handler(event, ctx):\n"
        f'    password = get_secret("prod/db", "password"{py_store})   # one field of a JSON secret\n'
        f'    put_secret("last-run", ctx.request_id{py_store})\n```\n\n'
        "```js\nconst { getSecret } = require(\"pskit\");\n\n"
        f'exports.handler = async () => ({{ password: await getSecret("prod/db", "password"{js_store}) }});\n```\n\n'
        "### boto3 (any Python program)\n\n"
        "```python\nimport json\nimport os\n\nimport boto3\n\n"
        "sm = boto3.client(\n    \"secretsmanager\",\n"
        f'    endpoint_url=os.environ["{prefix}_URL"],            # {url}\n'
        '    region_name="us-east-1",\n'
        f'    aws_access_key_id=os.environ["{prefix}_ACCESS_KEY"],\n'
        f'    aws_secret_access_key=os.environ["{prefix}_SECRET_KEY"],\n)\n'
        'sm.create_secret(Name="prod/db", SecretString=json.dumps({"user": "app", "password": "s3cret"}))\n'
        'print(json.loads(sm.get_secret_value(SecretId="prod/db")["SecretString"]))\n'
        'sm.put_secret_value(SecretId="prod/db", SecretString=json.dumps({"user": "app", "password": "n3w"}))\n'
        'print(sm.get_secret_value(SecretId="prod/db", VersionStage="AWSPREVIOUS")["SecretString"])\n```\n\n'
        "### AWS SDK for JavaScript v3\n\n"
        "```js\nconst { SecretsManagerClient, GetSecretValueCommand } = require(\"@aws-sdk/client-secrets-manager\");\n\n"
        "const sm = new SecretsManagerClient({\n"
        f"  endpoint: process.env.{prefix}_URL,\n  region: \"us-east-1\",\n"
        f"  credentials: {{ accessKeyId: process.env.{prefix}_ACCESS_KEY, secretAccessKey: process.env.{prefix}_SECRET_KEY }},\n"
        "});\n"
        "const out = await sm.send(new GetSecretValueCommand({ SecretId: \"prod/db\" }));\n"
        "console.log(JSON.parse(out.SecretString));\n```\n\n"
        "### AWS CLI\n\n"
        f"```bash\nexport AWS_ACCESS_KEY_ID={user} AWS_SECRET_ACCESS_KEY='<{prefix}_SECRET_KEY>' AWS_DEFAULT_REGION=us-east-1\n"
        f"aws --endpoint-url {url} secretsmanager create-secret --name api-key --secret-string abc123\n"
        f"aws --endpoint-url {url} secretsmanager get-secret-value --secret-id api-key\n"
        f"aws --endpoint-url {url} secretsmanager list-secrets\n```\n\n"
        "Code written for AWS runs unchanged: on AWS, leave out `endpoint_url` and the keys.\n\n"
        "### Encryption at rest\n\n"
        "The data is one JSON file in the service's volume (mode 600). Every secret version is encrypted with its "
        "own random data key (AES-256-GCM); the data key is stored wrapped by the master key "
        f"`{prefix}_MASTER_KEY` in `{env_file}`, as AWS does with KMS. The disk and the *Backup* archives hold only "
        "ciphertext; signed callers (the clients above, the console) get the values decrypted, so nothing changes "
        f"for them. **Keep `{prefix}_MASTER_KEY` safe and back it up apart from the data: without it the secrets "
        "can't be read.** Re-creating the service reuses it.\n\n"
        "Set `SM_ENCRYPTION` to `chacha20-poly1305` or `aes-256-cbc-hmac` for another algorithm. With "
        "`SM_MASTER_KEYS=id1:key1,id2:key2`, `KmsKeyId` picks a key per secret "
        "(`sm.create_secret(Name=\"prod/db\", KmsKeyId=\"alias/id1\", ...)`); set `SM_MASTER_KEY_ID` to another id "
        "and restart to rewrap every data key to it.\n"
    )
