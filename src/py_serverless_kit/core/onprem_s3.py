"""The ``s3`` / ``s3-node`` on-prem services: pskit's Amazon S3 compatible server.

The server's code lives in ``aws/s3`` at the repository root: ``python/server.py`` (standard library only),
``nodejs/server.js`` (no npm packages), the web console ``ui/index.html`` and a Dockerfile for each. The wheel ships
that folder as ``py_serverless_kit/aws`` (hatch ``force-include``); a source checkout reads it in place.

Like the Secrets Manager server (``core/onprem_secretsmanager.py``), it runs on the stock ``python:3.12-alpine`` /
``node:22-alpine`` image: ``docker create``, ``docker cp`` of the server and the console page into ``/app`` and
``docker start``, so nothing is built or pushed. Clients sign with SigV4 using the service's user as the access key ID
and its password as the secret access key, which also sign in to the console at ``/ui/``. The resource is a
``storage`` bucket on pskit's ``s3`` driver, so functions get storage triggers and ``put_object`` / ``get_object``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from . import onprem_secretsmanager

PORT = 9000
# service id -> (server file in aws/s3, interpreter)
SERVICES: Dict[str, Dict[str, str]] = {
    "s3": {"file": "python/server.py", "run": "python", "image": "python:3.12-alpine", "lang": "Python"},
    "s3-node": {"file": "nodejs/server.js", "run": "node", "image": "node:22-alpine", "lang": "Node.js"},
}
UI_FILE = "ui/index.html"


def source_dir() -> Path:
    """``aws/s3``: installed in the wheel, or the repository's copy in a source checkout."""
    here = Path(__file__).resolve().parent.parent
    for candidate in (here / "aws" / "s3", here.parents[1] / "aws" / "s3"):
        if (candidate / UI_FILE).is_file():
            return candidate
    raise FileNotFoundError("aws/s3 is missing from this installation of py-serverless-kit")


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
    """The container's environment."""
    return {
        "S3_PORT": str(PORT),
        "S3_BIND": "0.0.0.0",  # noqa: S104 - inside the container; the published port decides who reaches it
        "S3_DATA_DIR": "/data",
        "S3_REGION": "us-east-1",
        "S3_ACCESS_KEY_ID": str(req.get("user") or "pskit"),
        "S3_SECRET_ACCESS_KEY": password,
        "PYTHONUNBUFFERED": "1",
    }


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
    onprem_secretsmanager.start_with_app(req, target, sh, create_args(req, password), app_files(req["service"]))


def resource(req: Dict[str, Any], password: str, prefix: str, bucket: str) -> Dict[str, Any]:
    """(env values, s3 driver options, connection) of the ``storage`` resource."""
    url = f"http://{req['address']}:{req['port']}"
    user = str(req.get("user") or "pskit")
    values = {f"{prefix}_ACCESS_KEY": user, f"{prefix}_SECRET_KEY": password, f"{prefix}_URL": url}
    options = {"driver": "s3", "endpoint": url, "bucket": bucket, "region": "us-east-1",
               "access_key_env": f"{prefix}_ACCESS_KEY", "secret_key_env": f"{prefix}_SECRET_KEY",
               "path_style": True, "create_bucket": True}
    return {"env": values, "options": options, "connection": {"console_url": f"{url}/ui/", "url_env": f"{prefix}_URL"}}


def usage_markdown(entry: Dict[str, Any], prefix: str, bucket: str) -> str:
    """How to use: pskit functions, boto3, the AWS SDK for JavaScript, the AWS CLI and the console."""
    url = f"http://{entry.get('address')}:{entry.get('port')}"
    user = str(entry.get("user") or "pskit")
    lang = SERVICES.get(str(entry.get("service")), SERVICES["s3"])["lang"]
    env_file = str(entry.get("env_file") or ".env.onprem")
    return (
        "## Use it like Amazon S3\n\n"
        f"pskit's own S3 compatible server ({lang}, code in `aws/s3`) answers the S3 API at the endpoint below. Every "
        f"request is checked with AWS Signature Version 4 (or 2): sign with access key ID `{user}` and the password as "
        f"the secret access key (`{prefix}_ACCESS_KEY` / `{prefix}_SECRET_KEY` in `{env_file}`). Path-style "
        "addressing (`<endpoint>/<bucket>/<key>`) works everywhere; any region name is accepted.\n\n"
        "| | |\n|---|---|\n"
        f"| Endpoint | `{url}` |\n| Bucket | `{bucket}` (created on first use) |\n"
        f"| Web console | {url}/ui/ (access key ID `{user}`, password = secret key) |\n"
        "| Buckets | create / delete / list, versioning, tags, policies (anonymous access follows them), ACLs, CORS, "
        "lifecycle rules (applied), static website hosting, object lock, public access block, ownership controls, "
        "default encryption; logging, notification, replication and other configurations are stored |\n"
        "| Objects | put / get / head / delete / copy, ranges, conditional requests, metadata, tags, storage classes, "
        "checksums (CRC32, CRC32C, CRC64NVME, SHA1, SHA256), versions and delete markers, multi-object delete, "
        "multipart uploads, presigned URLs and browser POST uploads, GetObjectAttributes |\n"
        "| Not supported | S3 Select, torrents, S3 Express directory buckets; SSE is reported but the data is not "
        "encrypted at rest |\n\n"
        "### In pskit functions\n\n"
        "The resource uses pskit's `s3` driver, so storage triggers and the storage helpers work unchanged "
        "(see **Resources → How to use** for the handler snippets).\n\n"
        "### boto3 (any Python program)\n\n"
        "```python\nimport os\n\nimport boto3\nfrom botocore.config import Config\n\n"
        "s3 = boto3.client(\n    \"s3\",\n"
        f'    endpoint_url=os.environ["{prefix}_URL"],            # {url}\n'
        '    region_name="us-east-1",\n'
        f'    aws_access_key_id=os.environ["{prefix}_ACCESS_KEY"],\n'
        f'    aws_secret_access_key=os.environ["{prefix}_SECRET_KEY"],\n'
        '    config=Config(s3={"addressing_style": "path"}),\n)\n'
        f's3.put_object(Bucket="{bucket}", Key="reports/today.txt", Body=b"hello", ContentType="text/plain")\n'
        f'print(s3.get_object(Bucket="{bucket}", Key="reports/today.txt")["Body"].read())\n'
        f's3.upload_file("big.iso", "{bucket}", "isos/big.iso")          # multipart for large files\n'
        f'url = s3.generate_presigned_url("get_object", Params={{"Bucket": "{bucket}", "Key": "reports/today.txt"}}, '
        'ExpiresIn=3600)\n```\n\n'
        "### AWS SDK for JavaScript v3\n\n"
        "```js\nconst { S3Client, PutObjectCommand, GetObjectCommand } = require(\"@aws-sdk/client-s3\");\n\n"
        "const s3 = new S3Client({\n"
        f"  endpoint: process.env.{prefix}_URL,\n  region: \"us-east-1\",\n  forcePathStyle: true,\n"
        f"  credentials: {{ accessKeyId: process.env.{prefix}_ACCESS_KEY, secretAccessKey: process.env.{prefix}_SECRET_KEY }},\n"
        "});\n"
        f'await s3.send(new PutObjectCommand({{ Bucket: "{bucket}", Key: "hello.txt", Body: "hi" }}));\n'
        f'const out = await s3.send(new GetObjectCommand({{ Bucket: "{bucket}", Key: "hello.txt" }}));\n'
        "console.log(await out.Body.transformToString());\n```\n\n"
        "### AWS CLI\n\n"
        f"```bash\nexport AWS_ACCESS_KEY_ID={user} AWS_SECRET_ACCESS_KEY='<{prefix}_SECRET_KEY>' AWS_DEFAULT_REGION=us-east-1\n"
        f"aws --endpoint-url {url} s3 ls s3://{bucket}\n"
        f"aws --endpoint-url {url} s3 cp ./site s3://{bucket}/site --recursive\n"
        f"aws --endpoint-url {url} s3api put-bucket-versioning --bucket {bucket} "
        "--versioning-configuration Status=Enabled\n"
        f"aws --endpoint-url {url} s3 presign s3://{bucket}/site/index.html --expires-in 3600\n```\n\n"
        "Code written for AWS runs unchanged: on AWS, leave out the endpoint and the keys. Objects are plain files in "
        "the service's volume (not encrypted at rest): back them up with *Backup* and protect the server's disk.\n"
    )
