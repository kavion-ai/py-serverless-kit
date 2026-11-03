"""A console for one-click services, in the studio and the CLI: type a command, see its output.

Every line runs once (``docker exec`` in the service's container, or a small helper container on the service's
private network when the image has no client), on this machine or over SSH, with the service's own credentials.
Commands do not share state between lines (each ``psql -c`` is its own session); for an interactive session use
``pskit resources onprem console KEY`` in a terminal, or the studio's full terminal (:mod:`onprem_terminal`).

The *shell* mode runs the line with ``sh -c`` inside the service's container. Servers get the same with
:func:`run_server`: the line runs over SSH.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

RunFn = Callable[[List[str], Optional[Path]], Tuple[int, str]]
MAX_OUTPUT = 200_000

# Helper images for services whose image has no client (pinned, small).
REDIS_CLI = "redis:7-alpine"
NATS_BOX = "natsio/nats-box:0.14.5"
AWS_CLI = "amazon/aws-cli:2.22.35"
CURL = "curlimages/curl:8.11.1"
BUSYBOX = "busybox:1.37"

# label, how to read the line, examples. "cli": the line is split into arguments for the client;
# "text": the whole line is one argument (SQL, JavaScript, a URL path, a memcached command).
CONSOLES: Dict[str, Dict[str, Any]] = {
    "redis": {"label": "redis-cli", "input": "cli", "examples": ["PING", "INFO server", "KEYS *", "LLEN jobs",
                                                                   "XINFO STREAM jobs", "GET mykey"]},
    "valkey": {"label": "valkey-cli", "input": "cli", "examples": ["PING", "INFO server", "KEYS *", "LLEN jobs"]},
    "keydb": {"label": "keydb-cli", "input": "cli", "examples": ["PING", "INFO server", "KEYS *"]},
    "dragonfly": {"label": "redis-cli (helper)", "input": "cli", "examples": ["PING", "INFO server", "DBSIZE", "KEYS *"]},
    "postgres": {"label": "psql", "input": "text", "examples": ["\\dt", "SELECT version();", "SELECT now();",
                                                               "CREATE TABLE notes(id serial primary key, body text);"]},
    "mysql": {"label": "mysql", "input": "text", "examples": ["SHOW TABLES;", "SELECT VERSION();", "SHOW DATABASES;"]},
    "mariadb": {"label": "mariadb", "input": "text", "examples": ["SHOW TABLES;", "SELECT VERSION();", "SHOW DATABASES;"]},
    "mongodb": {"label": "mongosh", "input": "text", "examples": ["db.getCollectionNames()", "db.stats()",
                                                                 "db.notes.insertOne({body: 'hi'})", "db.notes.find().limit(5)"]},
    "kafka": {"label": "rpk", "input": "cli", "examples": ["cluster info", "topic list", "topic describe events",
                                                            "topic consume events -n 5", "group list"]},
    "apache-kafka": {"label": "kafka scripts", "input": "cli", "examples": [
        "kafka-topics.sh --list", "kafka-topics.sh --describe", "kafka-consumer-groups.sh --list",
        "kafka-console-consumer.sh --topic events --from-beginning --max-messages 5 --timeout-ms 5000"]},
    "rabbitmq": {"label": "rabbitmqctl", "input": "cli", "examples": ["list_queues name messages consumers",
                                                                       "list_exchanges", "list_users", "status"]},
    "lavinmq": {"label": "lavinmqctl", "input": "cli", "examples": ["list_queues", "list_users", "status"]},
    "nats": {"label": "nats (nats-box helper)", "input": "cli", "examples": ["server info", "stream ls", "stream info jobs",
                                                                            "consumer ls jobs", "pub jobs hello"]},
    "minio": {"label": "mc (alias local)", "input": "cli", "examples": ["ls local", "ls local/files", "admin info local",
                                                                         "du local"]},
    "rustfs": {"label": "aws s3 (helper)", "input": "cli", "examples": ["s3 ls", "s3 ls s3://files", "s3api list-buckets"]},
    "localstack": {"label": "awslocal", "input": "cli", "examples": ["sqs list-queues", "s3 ls", "secretsmanager list-secrets",
                                                                     "sqs get-queue-attributes --queue-url http://localhost:4566/000000000000/jobs --attribute-names All"]},
    "elasticmq": {"label": "aws sqs (helper)", "input": "cli", "examples": ["sqs list-queues",
                                                                            "sqs get-queue-attributes --queue-url http://elasticmq:9324/000000000000/jobs --attribute-names All"]},
    "secretsmanager": {"label": "aws secretsmanager (helper)", "input": "cli", "examples": [
        "secretsmanager list-secrets", "secretsmanager create-secret --name api-key --secret-string abc123",
        "secretsmanager get-secret-value --secret-id api-key", "secretsmanager get-random-password"]},
    "openbao": {"label": "bao (Vault CLI)", "input": "cli", "examples": ["kv list secret", "kv get secret/db-password",
                                                                       "kv put secret/api-key value=abc123", "status"]},
    "memcached": {"label": "memcached text protocol", "input": "text", "examples": ["stats", "stats items", "version"]},
    "mailpit": {"label": "Mailpit API (GET path)", "input": "text", "examples": ["/api/v1/info", "/api/v1/messages?limit=5"]},
    "fake-gcs": {"label": "Cloud Storage JSON API (GET path)", "input": "text", "examples": ["/storage/v1/b",
                                                                                              "/storage/v1/b/files/o"]},
}

CONSOLES["secretsmanager-node"] = CONSOLES["secretsmanager"]
CONSOLES["s3"] = CONSOLES["s3-node"] = {"label": "aws s3 (helper)", "input": "cli", "examples": [
    "s3 ls", "s3api list-buckets", "s3 ls s3://files --recursive", "s3api get-bucket-versioning --bucket files"]}


class ConsoleError(Exception):
    pass


def console_info(entry: Dict[str, Any]) -> Dict[str, Any]:
    service = str(entry.get("service"))
    spec = CONSOLES.get(service)
    return {
        "service": service,
        "available": spec is not None,
        "label": spec["label"] if spec else "",
        "input": spec["input"] if spec else "",
        "examples": list(spec["examples"]) if spec else [],
        "shell": True,
        "note": "" if spec else f"{service} has no command-line client here; use the shell mode, Data or How to use.",
    }


def _secret(entry: Dict[str, Any], suffix: str) -> str:
    env = entry.get("env") or {}
    return next((str(v) for k, v in env.items() if k.endswith(suffix) and not k.endswith("_GUI" + suffix)), "")


def _user(entry: Dict[str, Any]) -> str:
    from .onprem_services import DEFAULT_USER

    return str(entry.get("user") or DEFAULT_USER.get(str(entry.get("service")), "pskit"))


def _redis_auth(entry: Dict[str, Any]) -> List[str]:
    password, user = _secret(entry, "_PASSWORD"), _user(entry)
    if not password:
        return []
    if user in ("", "default") or entry.get("service") == "dragonfly":
        return ["-a", password, "--no-auth-warning"]
    return ["--user", user, "--pass", password, "--no-auth-warning"]


def _database(entry: Dict[str, Any]) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", str(entry.get("key")))


def _split(line: str) -> List[str]:
    try:
        return shlex.split(line)
    except ValueError as exc:
        raise ConsoleError(f"cannot read the command: {exc}") from None


def command_args(entry: Dict[str, Any], line: str) -> Tuple[str, List[str]]:
    """(``exec`` or a helper image, arguments) for one console line of the service."""
    service = str(entry.get("service"))
    container = str(entry.get("container"))
    user, password = _user(entry), _secret(entry, "_PASSWORD")
    from .onprem_services import SERVICES

    port = str((SERVICES.get(service) or {}).get("port") or "")
    if service in ("redis", "valkey", "keydb"):
        cli = {"redis": "redis-cli", "valkey": "valkey-cli", "keydb": "keydb-cli"}[service]
        return "exec", [cli, *_redis_auth(entry), *_split(line)]
    if service == "dragonfly":
        return REDIS_CLI, ["redis-cli", "-h", container, "-p", port, *_redis_auth(entry), *_split(line)]
    if service == "postgres":
        return "exec", ["psql", "-U", user, "-d", _database(entry), "-v", "ON_ERROR_STOP=1", "-c", line]
    if service in ("mysql", "mariadb"):
        cli = "mysql" if service == "mysql" else "mariadb"
        return "exec", ["env", f"MYSQL_PWD={password}", cli, "-u", user, "-t", _database(entry), "-e", line]
    if service == "mongodb":
        return "exec", ["mongosh", "--quiet", "-u", user, "-p", password, "--authenticationDatabase", "admin",
                        _database(entry), "--eval", line]
    if service == "kafka":
        return "exec", ["rpk", *_split(line), "-X", "brokers=127.0.0.1:9093"]
    if service == "apache-kafka":
        args = _split(line)
        if not args:
            raise ConsoleError("type a kafka-*.sh script and its arguments")
        tool = args[0] if "/" in args[0] else "/opt/kafka/bin/" + args[0]
        extra = [] if any(a.startswith("--bootstrap-server") for a in args) else ["--bootstrap-server", "localhost:9092"]
        return "exec", [tool, *args[1:], *extra]
    if service == "rabbitmq":
        return "exec", ["rabbitmqctl", *_split(line)]
    if service == "lavinmq":
        return "exec", ["lavinmqctl", *_split(line)]
    if service == "nats":
        url = f"nats://{container}:{port}"
        auth = ["--user", user, "--password", password] if password else []
        return NATS_BOX, ["nats", "-s", url, *auth, *_split(line)]
    if service == "minio":
        script = 'mc alias set local http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc "$@"'
        return "exec", ["sh", "-c", script, "mc", *_split(line)]
    if service in ("rustfs", "secretsmanager", "secretsmanager-node", "s3", "s3-node"):
        access, secret = _secret(entry, "_ACCESS_KEY"), _secret(entry, "_SECRET_KEY")
        return AWS_CLI, ["env", f"AWS_ACCESS_KEY_ID={access}", f"AWS_SECRET_ACCESS_KEY={secret}",
                         "AWS_DEFAULT_REGION=us-east-1", "aws", "--endpoint-url", f"http://{container}:{port}",
                         *_split(line)]
    if service == "localstack":
        return "exec", ["awslocal", *_split(line)]
    if service == "openbao":
        return "exec", ["env", "BAO_ADDR=http://127.0.0.1:8200", f"BAO_TOKEN={_secret(entry, '_TOKEN')}", "bao",
                        *_split(line)]
    if service == "elasticmq":
        args = [a.replace("http://elasticmq:9324", f"http://{container}:{port}") for a in _split(line)]
        return AWS_CLI, ["env", "AWS_ACCESS_KEY_ID=x", "AWS_SECRET_ACCESS_KEY=x", "AWS_DEFAULT_REGION=us-east-1",
                         "aws", "--endpoint-url", f"http://{container}:{port}", *args]
    if service == "memcached":
        return BUSYBOX, ["sh", "-c", f'printf "%s\\r\\nquit\\r\\n" "$1" | nc {container} {port}', "memcached", line]
    if service in ("mailpit", "fake-gcs"):
        path = line.strip()
        if not path.startswith("/"):
            raise ConsoleError("type a URL path, e.g. " + CONSOLES[service]["examples"][0])
        http_port = "8025" if service == "mailpit" else port
        return CURL, ["curl", "-sS", "--max-time", "20", f"http://{container}:{http_port}{path}"]
    raise ConsoleError(f"{service} has no console client; use the shell mode")


def _credentials(entry: Dict[str, Any]) -> List[str]:
    """Values to hide in commands and output: passwords, tokens, secret keys (8+ characters, longest first)."""
    names = ("PASSWORD", "TOKEN", "SECRET_KEY", "ACCOUNT_KEY", "CONNECTION_STRING")
    values = {str(v) for k, v in (entry.get("env") or {}).items() if any(n in k for n in names) and len(str(v)) >= 8}
    return sorted(values, key=len, reverse=True)


def _display(argv: List[str], secrets: List[str]) -> str:
    text = " ".join(shlex.quote(a) for a in argv)
    for secret in secrets:
        text = text.replace(secret, "***")
    return text


def _run(argv: List[str], timeout: float) -> Tuple[int, str]:
    try:
        proc = subprocess.run(  # noqa: S603 - explicit argv, no shell here
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=timeout
        )
    except FileNotFoundError:
        return 127, f"command not found: {argv[0]}"
    except subprocess.TimeoutExpired as exc:
        out = exc.output.decode("utf-8", "replace") if isinstance(exc.output, bytes) else ""
        return 124, out + f"\n(stopped after {int(timeout)} s; long-running commands belong in a full terminal)"
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def run_line(
    root: Path,
    key: str,
    line: str,
    *,
    shell: bool = False,
    run: Optional[RunFn] = None,
    timeout: float = 60,
) -> Dict[str, Any]:
    """Run one console line against service ``key``. Returns ``{output, exit_code, command}``."""
    from .onprem_services import _entry, docker_argv

    entry = _entry(root, key)
    if entry.get("kind") == "runtime":
        raise ConsoleError(f"{key} is installed software, not a container; use the server shell")
    line = str(line or "").strip()
    if not line:
        raise ConsoleError("type a command")
    if len(line) > 8000:
        raise ConsoleError("the command is longer than 8000 characters")
    target = entry["target"]
    container = str(entry["container"])
    secrets = _credentials(entry)
    if shell:
        how, args = "exec", ["sh", "-c", line]
    else:
        how, args = command_args(entry, line)
    runner = run or (lambda argv, _stdout: _run(argv, timeout))
    if how == "exec":
        docker = ["exec", container, *args]
    else:
        network = f"{container}-net"
        runner(docker_argv(target, ["network", "create", network]), None)
        runner(docker_argv(target, ["network", "connect", network, container]), None)
        docker = ["run", "--rm", "--network", network, "--entrypoint", args[0], how, *args[1:]]
    argv = docker_argv(target, docker)
    code, out = runner(argv, None)
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f"\n... (cut at {MAX_OUTPUT} characters)"
    for secret in secrets:
        out = out.replace(secret, "***")
    return {"output": out, "exit_code": code, "command": _display(["docker", *docker], secrets)}


def interactive_args(entry: Dict[str, Any], *, shell: bool = False) -> List[str]:
    """``exec -it <container> <client>`` arguments for docker: the service's client, or ``sh``."""
    service = str(entry.get("service"))
    user, password = _user(entry), _secret(entry, "_PASSWORD")
    args: List[str] = ["sh"]
    if not shell:
        if service in ("redis", "valkey", "keydb"):
            args = [{"redis": "redis-cli", "valkey": "valkey-cli", "keydb": "keydb-cli"}[service], *_redis_auth(entry)]
        elif service == "postgres":
            args = ["psql", "-U", user, "-d", _database(entry)]
        elif service in ("mysql", "mariadb"):
            args = ["env", f"MYSQL_PWD={password}", "mariadb" if service == "mariadb" else "mysql", "-u", user,
                    _database(entry)]
        elif service == "mongodb":
            args = ["mongosh", "-u", user, "-p", password, "--authenticationDatabase", "admin", _database(entry)]
    return ["exec", "-it", str(entry["container"]), *args]


def interactive_argv(root: Path, key: str, *, shell: bool = False) -> List[str]:
    """The command for a real terminal here: ``docker exec -it``, over ``ssh -t`` for a server."""
    from .onprem_services import _entry, docker_argv

    entry = _entry(root, key)
    argv = docker_argv(entry["target"], interactive_args(entry, shell=shell))
    if "ssh" in argv and argv[0] in ("ssh", "sshpass"):
        argv.insert(argv.index("ssh") + 1, "-t")
    return argv


def run_server(target: Dict[str, Any], line: str, *, run: Optional[RunFn] = None, timeout: float = 120) -> Dict[str, Any]:
    """Run one shell line on an SSH server (a fresh login shell each time)."""
    from .onprem_services import _ssh_argv

    if target.get("method") != "ssh":
        raise ConsoleError("the server shell is for SSH servers; use your own terminal on this machine")
    line = str(line or "").strip()
    if not line:
        raise ConsoleError("type a command")
    argv = _ssh_argv(target, line)
    code, out = (run or (lambda a, _s: _run(a, timeout)))(argv, None)
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f"\n... (cut at {MAX_OUTPUT} characters)"
    return {"output": out, "exit_code": code, "command": f"ssh {target.get('user')}@{target.get('host')} {line}"}
