"""Shell scripts and workload manifests for on-prem scaling clusters (Docker Swarm, Kubernetes via k3s, Nomad).

Everything here is a pure function of its arguments, so it is unit-tested without servers. The scripts run on
the servers over SSH (``core/onprem_cluster.py`` copies and starts them); manifests are JSON (valid YAML for
``docker stack deploy``, accepted by ``kubectl apply -f`` and the Nomad jobs API).

Each deployment runs the function host image as two workloads:

* ``main`` - one replica pinned to the master server with the data volume: schedules, built-in queues / topics /
  buckets, workflow executions, logs and the admin API live there.
* ``web`` - ``replicas`` copies behind the orchestrator's load balancer: HTTP routes and ``invoke()``. They hand
  everything stateful to ``main`` (``PSKIT_MAIN_URL``), so adding replicas or servers never duplicates a schedule.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..providers.onprem_remote import _docker_install_block, _docker_ready_block, _docker_shell_header, _shq

NOMAD_VERSION = "1.11.3"  # releases.hashicorp.com; override per cluster with `nomad_version`
K3S_INSTALL = "https://get.k3s.io"
NAMESPACE = "pskit"  # Kubernetes namespace of every pskit workload
DATA_ROOT = "/var/lib/pskit"  # Kubernetes / Nomad: <DATA_ROOT>/<stack> on the master holds the main replica's data
MARK = "PSKIT_SECTION="  # separates the outputs of one status script

_COMMON = (
    "need() { command -v \"$1\" >/dev/null 2>&1; }\n"
    "pkg_install() {\n"
    "  if need apt-get; then export DEBIAN_FRONTEND=noninteractive; as_root apt-get update -y >/dev/null;"
    " as_root apt-get install -y \"$@\";\n"
    "  elif need dnf; then as_root dnf install -y \"$@\";\n"
    "  elif need yum; then as_root yum install -y \"$@\";\n"
    "  elif need apk; then as_root apk add --no-cache \"$@\";\n"
    "  else echo \"pskit: install $* on this server and retry\" >&2; exit 1; fi\n"
    "}\n"
    "need curl || pkg_install curl\n"
)


def _header(*, secret: bool = False) -> str:
    """POSIX sh with ``as_root``, ``dk`` (docker, or sudo docker), ``need`` and ``pkg_install``.

    ``secret``: the script holds a join token, so it deletes itself when it ends.
    """
    trap = 'trap \'rm -f "$0"\' EXIT\n' if secret else ""
    return _docker_shell_header() + trap + _COMMON


def stack_name(service: str, stage: str) -> str:
    """``pskit-<service>-<stage>``: a valid Swarm stack, Kubernetes name (DNS-1123) and Nomad job id."""
    slug = re.sub(r"[^a-z0-9-]+", "-", f"pskit-{service}-{stage}".lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)[:50].rstrip("-")


# ---------------------------------------------------------------------------------------------- master / join
def master_script(orchestrator: str, advertise: str, nomad_version: str = NOMAD_VERSION) -> str:
    """Install the orchestrator on the master server (idempotent) and print ``PSKIT_NODE=<node name>``."""
    addr = _shq(advertise)
    if orchestrator == "swarm":
        return (
            _header() + _docker_install_block() + _docker_ready_block()
            + "state=$(dk info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null || echo inactive)\n"
            + _swarm_locked_check()
            + 'if [ "$state" = "pending" ] || [ "$state" = "error" ]; then\n'
            + '  echo "pskit: leaving a half-joined swarm ($state) first"\n'
            + "  dk swarm leave --force || true\n"
            + "  state=inactive\n"
            + "fi\n"
            + f'if [ "$state" != "active" ]; then dk swarm init --advertise-addr {addr}; fi\n'
            + "if [ \"$(dk info --format '{{.Swarm.ControlAvailable}}')\" != \"true\" ]; then\n"
            + '  echo "pskit: this server is a worker of another swarm; make its manager the master" >&2\n'
            + "  exit 1\n"
            + "fi\n"
            + "echo \"PSKIT_NODE=$(dk info --format '{{.Name}}')\"\n"
        )
    if orchestrator == "kubernetes":
        return (
            _header()
            + "if ! need k3s; then\n"
            + f"  curl -sfL {K3S_INSTALL} | as_root env INSTALL_K3S_EXEC=\"server --write-kubeconfig-mode 644"
            + f' --tls-san {advertise}" sh -\n'
            + "fi\n"
            + _wait("as_root k3s kubectl get nodes >/dev/null 2>&1", 90, "Kubernetes (k3s) did not start")
            + f"as_root k3s kubectl create namespace {NAMESPACE} >/dev/null 2>&1 || true\n"
            + "echo \"PSKIT_NODE=$(hostname | tr 'A-Z' 'a-z')\"\n"
        )
    if orchestrator == "nomad":
        config = _nomad_config(advertise, server=True, servers=[advertise])
        return _nomad_agent_script(config, nomad_version)
    raise ValueError(f"unknown orchestrator {orchestrator!r}")


def join_token_script(orchestrator: str) -> str:
    """Runs on the master: prints ``PSKIT_TOKEN=<worker join token>`` (Nomad needs none). Swarm also prints
    ``PSKIT_MEMBERS=<node ids>``, so the joining server can tell whether it is already a member."""
    if orchestrator == "swarm":
        return _header() + ("echo \"PSKIT_TOKEN=$(dk swarm join-token -q worker)\"\n"
                            "echo \"PSKIT_MEMBERS=$(dk node ls -q | tr '\\n' ' ')\"\n")
    if orchestrator == "kubernetes":
        return _header() + "echo \"PSKIT_TOKEN=$(as_root cat /var/lib/rancher/k3s/server/node-token)\"\n"
    return _header() + "echo PSKIT_TOKEN=\n"


def join_script(orchestrator: str, master: str, token: str, advertise: str,
                nomad_version: str = NOMAD_VERSION, members: Sequence[str] = ()) -> str:
    """Install the orchestrator agent on a server and join the master's cluster; prints ``PSKIT_NODE=``.

    Safe to repeat and to run on a server that was in a cluster before (removed while it was off, a join that
    stopped half way, a master that was set up again): stale membership is left first. ``members``: the node ids
    of the master's swarm (``join_token_script``). Only a server that manages another swarm with other nodes or
    services is refused, since leaving it would break that swarm."""
    if orchestrator == "swarm":
        return (
            _header(secret=True) + _docker_install_block() + _docker_ready_block()
            + "info=$(dk info --format '{{.Swarm.LocalNodeState}} {{.Swarm.ControlAvailable}} {{.Swarm.NodeID}}'"
            + " 2>/dev/null || echo inactive)\n"
            + "set -- $info\n"
            + 'state=${1:-inactive}; manager=${2:-false}; node_id=${3:-}\n'
            + f"members={_shq(' '.join(members))}\n"
            + 'case " $members " in *" $node_id "*) member=1 ;; *) member=0 ;; esac\n'
            + '[ -n "$node_id" ] || member=0\n'
            + _swarm_locked_check()
            + 'if [ "$state" = "active" ] && [ "$member" = "1" ]; then\n'
            + '  echo "already in this swarm"\n'
            + "else\n"
            + '  if [ "$state" = "active" ] && [ "$manager" = "true" ]; then\n'
            # $((...)) drops the padding BSD wc puts before the count.
            + '    others=$(($(dk node ls -q | grep -vx "$node_id" | wc -l)))\n'
            + "    services=$(($(dk service ls -q | wc -l)))\n"
            + '    if [ "$others" -gt 0 ] || [ "$services" -gt 0 ]; then\n'
            + '      echo "pskit: this server manages another swarm ($others other node(s), $services service(s)).'
            + ' Remove that cluster first, or run: docker swarm leave --force" >&2\n'
            + "      exit 1\n"
            + "    fi\n"
            + "  fi\n"
            + '  if [ "$state" != "inactive" ]; then\n'
            + '    echo "pskit: leaving the old swarm ($state) first"\n'
            + "    dk swarm leave --force || true\n"
            + "  fi\n"
            + f"  dk swarm join --advertise-addr {_shq(advertise)} --token {_shq(token)} {_shq(master + ':2377')}\n"
            + "fi\n"
            + "echo \"PSKIT_NODE=$(dk info --format '{{.Name}}')\"\n"
            + "echo \"PSKIT_NODE_ID=$(dk info --format '{{.Swarm.NodeID}}')\"\n"
        )
    if orchestrator == "kubernetes":
        env = "/etc/systemd/system/k3s-agent.service.env"
        url = "https://" + master + ":6443"
        return (
            _header(secret=True)
            + "if [ -x /usr/local/bin/k3s-uninstall.sh ]; then\n"
            + '  echo "pskit: this server runs a Kubernetes (k3s) server of its own. Remove that cluster first,'
            + ' or run: /usr/local/bin/k3s-uninstall.sh" >&2\n'
            + "  exit 1\n"
            + "fi\n"
            + f"if as_root grep -qF {_shq(url)} {env} 2>/dev/null && as_root grep -qF {_shq(token)} {env}"
            + " && as_root systemctl is-active --quiet k3s-agent; then\n"
            + '  echo "already in this cluster"\n'
            + "else\n"
            + "  if [ -x /usr/local/bin/k3s-agent-uninstall.sh ]; then\n"
            + '    echo "pskit: removing the old k3s agent first"\n'
            + "    as_root /usr/local/bin/k3s-agent-uninstall.sh || true\n"
            + "  fi\n"
            + f"  curl -sfL {K3S_INSTALL} | as_root env K3S_URL={_shq(url)}"
            + f" K3S_TOKEN={_shq(token)} INSTALL_K3S_EXEC={_shq('agent --node-external-ip ' + advertise)} sh -\n"
            + "fi\n"
            + "echo \"PSKIT_NODE=$(hostname | tr 'A-Z' 'a-z')\"\n"
        )
    if orchestrator == "nomad":
        return _nomad_agent_script(_nomad_config(advertise, server=False, servers=[master]), nomad_version)
    raise ValueError(f"unknown orchestrator {orchestrator!r}")


def leave_script(orchestrator: str) -> str:
    """Runs on the server that leaves: stop its agent (the master removes the node afterwards)."""
    if orchestrator == "swarm":
        return _header() + "dk swarm leave --force || true\n"
    if orchestrator == "kubernetes":
        return _header() + "if [ -x /usr/local/bin/k3s-agent-uninstall.sh ]; then as_root /usr/local/bin/k3s-agent-uninstall.sh; fi\n"
    return _header() + "as_root systemctl disable --now nomad || true\n"


def uninstall_script(orchestrator: str, *, master: bool, stacks: Sequence[str] = (), data_root: str = "",
                     delete_data: bool = False) -> str:
    """Runs on each server when a cluster is removed with ``--uninstall``: take off what pskit installed.

    Swarm: leave the swarm. Kubernetes: the k3s (agent) uninstall script, which also drops its images. Nomad: stop
    the agent and delete its binary, unit, config and data. The deployments' images (``stacks``: their repos) and
    the ``pskit-cluster`` scripts folder go too. Docker itself stays: one-server deployments and resources use it.
    ``delete_data`` (master only): also delete the main replicas' data (``<data_root>/<stack>``, Swarm volumes)."""
    body = ""
    if orchestrator == "swarm":
        body += "if need docker; then dk swarm leave --force >/dev/null 2>&1 || true; fi\n"
    elif orchestrator == "kubernetes":
        tool = "/usr/local/bin/k3s-uninstall.sh" if master else "/usr/local/bin/k3s-agent-uninstall.sh"
        body += f"if [ -x {tool} ]; then as_root {tool} || true; fi\n"
    elif orchestrator == "nomad":
        body += (
            "as_root systemctl disable --now nomad >/dev/null 2>&1 || true\n"
            # Nomad mounts secrets / alloc folders under its data dir: unmount them before deleting it.
            "for m in $(awk '$2 ~ \"^/opt/nomad/\" {print $2}' /proc/mounts | sort -r); do as_root umount \"$m\" || true; done\n"
            "as_root rm -rf /etc/nomad.d /opt/nomad /etc/systemd/system/nomad.service /usr/local/bin/nomad\n"
            "as_root systemctl daemon-reload >/dev/null 2>&1 || true\n"
        )
    else:
        raise ValueError(f"unknown orchestrator {orchestrator!r}")
    if orchestrator != "kubernetes" and stacks:
        repos = "|".join(sorted(stacks))  # stack_name(): only a-z, 0-9 and -
        body += (
            "if need docker; then\n"
            f"  for ref in $(dk images --format '{{{{.Repository}}}}:{{{{.Tag}}}}' | grep -E '^({repos}):'); do"
            " dk rmi -f \"$ref\" >/dev/null 2>&1 || true; done\n"
            "fi\n"
        )
    if master and delete_data:
        for stack in sorted(stacks):
            body += f"as_root rm -rf {_shq((data_root or DATA_ROOT).rstrip('/') + '/' + stack)}\n"
            if orchestrator == "swarm":
                body += f"if need docker; then dk volume rm {_shq(stack + '_data')} >/dev/null 2>&1 || true; fi\n"
    return _header() + body + "rm -rf pskit-cluster\n"


def drain_script(orchestrator: str, node: str, node_id: str = "") -> str:
    """Runs on the master: move every replica off ``node`` before it leaves."""
    n = _shq(node)
    if orchestrator == "swarm":
        return (
            _header() + f"dk node update --availability drain {n}\n"
            + _wait(f"[ -z \"$(dk node ps {n} --filter desired-state=running -q)\" ]", 120, "replicas did not move",
                    fail=False)
        )
    if orchestrator == "kubernetes":
        return _header() + (f"as_root k3s kubectl drain {n} --ignore-daemonsets --delete-emptydir-data --force"
                            " --timeout=180s || true\n")
    body = json.dumps({"DrainSpec": {"Deadline": 120 * 10**9, "IgnoreSystemJobs": False}})
    return _header() + (f"curl -fsS -X POST -H 'Content-Type: application/json' --data {_shq(body)}"
                        f" http://127.0.0.1:4646/v1/node/{_shq(node_id)}/drain >/dev/null || true\n")


def forget_script(orchestrator: str, node: str, node_id: str = "") -> str:
    """Runs on the master after the server left: remove the node from the cluster's list."""
    n = _shq(node)
    if orchestrator == "swarm":
        return _header() + _wait(
            f"[ \"$(dk node inspect {n} --format '{{{{.Status.State}}}}' 2>/dev/null || echo down)\" = down ]", 60,
            "node still up", fail=False) + f"dk node rm --force {n} || true\n"
    if orchestrator == "kubernetes":
        return _header() + f"as_root k3s kubectl delete node {n} --ignore-not-found\n"
    return _header() + f"curl -fsS -X PUT http://127.0.0.1:4646/v1/node/{_shq(node_id)}/purge >/dev/null || true\n"


def forget_stale_script(orchestrator: str, node: str, keep_id: str) -> str:
    """Runs on the master after ``node`` (re)joined: remove older, down entries of the same host name, left when
    the server was removed while unreachable or its swarm state was reset. Only Swarm keeps such entries."""
    if orchestrator != "swarm" or not keep_id:
        return _header()
    return _header() + (
        "for id in $(dk node ls -q); do\n"
        f"  [ \"$id\" = {_shq(keep_id)} ] && continue\n"
        "  set -- $(dk node inspect \"$id\" --format '{{.Description.Hostname}} {{.Status.State}}' 2>/dev/null)\n"
        f"  if [ \"${{1:-}}\" = {_shq(node)} ] && [ \"${{2:-}}\" = down ]; then dk node rm --force \"$id\" || true; fi\n"
        "done\n"
    )


def status_script(orchestrator: str, stack_prefix: str = "pskit-") -> str:
    """Runs on the master: node list and workloads, as sections ``PSKIT_SECTION=<name>`` followed by JSON lines."""
    if orchestrator == "swarm":
        return (
            _header()
            + f"echo {MARK}nodes\n"
            + "dk node ls --format '{{json .}}'\n"
            + f"echo {MARK}services\n"
            + "dk service ls --filter label=com.docker.stack.namespace --format '{{json .}}'\n"
            + f"echo {MARK}pending\n"
            + "for s in $(dk service ls -q); do dk service ps \"$s\" --filter desired-state=running"
            + " --format '{{json .}}' 2>/dev/null | grep -i '\"CurrentState\":\"Pending' || true; done\n"
        )
    if orchestrator == "kubernetes":
        k = "as_root k3s kubectl"
        return (
            _header()
            + f"echo {MARK}nodes\n{k} get nodes -o json\n"
            + f"echo {MARK}services\n{k} get deployments -n {NAMESPACE} -o json\n"
            + f"echo {MARK}pending\n{k} get pods -n {NAMESPACE} --field-selector=status.phase=Pending -o json\n"
        )
    api = "http://127.0.0.1:4646/v1"
    return (
        _header()
        + f"echo {MARK}nodes\ncurl -fsS {api}/nodes\necho\n"
        + f"echo {MARK}services\ncurl -fsS '{api}/jobs?prefix={stack_prefix}'\necho\n"
    )


def metrics_command() -> str:
    """One line for any Linux server: CPU over one second, memory, disk of /, load and CPU count."""
    return (
        "a=$(head -1 /proc/stat); sleep 1; b=$(head -1 /proc/stat); echo \"cpu_a=$a\"; echo \"cpu_b=$b\"; "
        "echo \"cpus=$(nproc 2>/dev/null)\"; "
        "awk '/^MemTotal/ {t=$2} /^MemAvailable/ {a=$2} END {print \"mem_total_kb=\" t; print \"mem_avail_kb=\" a}'"
        " /proc/meminfo; "
        "df -P / | awk 'NR==2 {print \"disk_total_kb=\" $2; print \"disk_used_kb=\" $3}'; "
        "echo \"load=$(cut -d' ' -f1-3 /proc/loadavg)\"; echo \"hostname=$(hostname)\""
    )


def image_load_script(orchestrator: str, parts_dir: str, sha256: str, stale_glob: str = "") -> str:
    """Join the gzip parts in ``parts_dir`` (``part-00000`` ...), check them against ``sha256``, load the image into
    the node's container runtime and delete the parts. A damaged copy is deleted and the script fails, so the
    next attempt sends it again. ``stale_glob``: part folders of older images of the same deployment, removed."""
    d = _shq(parts_dir)
    check = (
        "need gunzip || pkg_install gzip\n"
        f"got=$(cat {d}/part-* | sha256sum | cut -d' ' -f1)\n"
        f'if [ "$got" != {_shq(sha256)} ]; then\n'
        '  echo "pskit: the copied image is damaged (checksum differs); it is copied again" >&2\n'
        f"  rm -rf {d}\n"
        "  exit 1\n"
        "fi\n"
    )
    if orchestrator == "kubernetes":
        load = (f"cat {d}/part-* | gunzip > {d}/image.tar\n"
                f"as_root k3s ctr images import {d}/image.tar\n")
    else:
        load = _docker_ready_block() + f"cat {d}/part-* | gunzip | dk load\n"
    clean = f"rm -rf {d}\n"
    if stale_glob:
        # `if`, not `[ -d ] && rm`: with no older copy the test fails last and the script would exit 1 after loading
        clean += f"for x in {stale_glob}; do if [ -d \"$x\" ]; then rm -rf \"$x\"; fi; done\n"
    return _header() + check + load + clean + "exit 0\n"


def has_image_command(orchestrator: str, image: str) -> str:
    """Exit 0 when the node already has ``image`` (so the copy is skipped)."""
    if orchestrator == "kubernetes":
        ref = image if "/" in image else f"docker.io/library/{image}"
        return f"sudo -n k3s ctr images ls -q 2>/dev/null | grep -qx {_shq(ref)} || k3s ctr images ls -q 2>/dev/null | grep -qx {_shq(ref)}"
    return f"docker image inspect {_shq(image)} >/dev/null 2>&1 || sudo -n docker image inspect {_shq(image)} >/dev/null 2>&1"


def prune_script(orchestrator: str, repo: str, keep: str) -> str:
    """Remove older tags of this deployment's image (best effort; an image still in use stays)."""
    if orchestrator == "kubernetes":
        return _header() + (
            f"for ref in $(as_root k3s ctr images ls -q | grep '^docker.io/library/{repo}:' | grep -v ':{keep}$'); do"
            " as_root k3s ctr images rm \"$ref\" >/dev/null 2>&1 || true; done\n"
        )
    return _header() + (
        f"for ref in $(dk images --format '{{{{.Repository}}}}:{{{{.Tag}}}}' | grep '^{repo}:' | grep -v ':{keep}$'); do"
        " dk rmi \"$ref\" >/dev/null 2>&1 || true; done\n"
    )


# ---------------------------------------------------------------------------------------------- workloads
def _health_cmd(python: str, port: int) -> List[str]:
    code = f"import urllib.request; urllib.request.urlopen('http://127.0.0.1:{port}/__pskit/health', timeout=3).read()"
    return ["CMD", python, "-c", code]


def swarm_stack(stack: str, image: str, *, port: int, replicas: int, master_node: str, cpu: float, memory_mb: int,
                python: str = "python", data_root: Optional[str] = None, avoid_master: bool = False) -> Dict[str, Any]:
    """A compose file (JSON) for ``docker stack deploy``: ``main`` on the master, ``web`` behind the routing mesh.

    The main replica's data is the stack's ``data`` volume, or ``<data_root>/<stack>`` on the master (the master's
    data directory). ``avoid_master``: web replicas run only on the other servers."""
    health = {"test": _health_cmd(python, port), "interval": "10s", "timeout": "5s", "retries": 3, "start_period": "30s"}
    reserve = {"cpus": f"{cpu:g}", "memory": f"{memory_mb}M"}
    return {
        "version": "3.8",
        "services": {
            "main": {
                "image": image,
                "environment": {"PSKIT_HOST_ROLE": "main", "PSKIT_REPLICA": "main", "PSKIT_NODE": "{{.Node.Hostname}}"},
                "volumes": [f"{data_root}/{stack}:/var/pskit/data" if data_root else "data:/var/pskit/data"],
                "networks": ["pskit"],
                "healthcheck": health,
                "deploy": {
                    "replicas": 1,
                    "placement": {"constraints": [f"node.hostname == {master_node}"]},
                    "update_config": {"order": "stop-first"},
                    "restart_policy": {"condition": "any"},
                    "resources": {"reservations": reserve},
                },
            },
            "web": {
                "image": image,
                "environment": {
                    "PSKIT_HOST_ROLE": "web",
                    "PSKIT_MAIN_URL": f"http://main:{port}",
                    "PSKIT_REPLICA": "{{.Node.Hostname}}-{{.Task.Slot}}",
                    "PSKIT_NODE": "{{.Node.Hostname}}",
                },
                "ports": [{"target": port, "published": port, "protocol": "tcp", "mode": "ingress"}],
                "networks": ["pskit"],
                "healthcheck": health,
                "deploy": {
                    "replicas": replicas,
                    **({"placement": {"constraints": [f"node.hostname != {master_node}"]}} if avoid_master else {}),
                    "update_config": {"parallelism": 1, "order": "start-first", "failure_action": "rollback"},
                    "restart_policy": {"condition": "any"},
                    "resources": {"reservations": reserve},
                },
            },
        },
        **({} if data_root else {"volumes": {"data": {}}}),
        "networks": {"pskit": {"driver": "overlay", "attachable": True}},
    }


def kubernetes_manifest(stack: str, image: str, *, port: int, replicas: int, master_node: str, cpu: float,
                        memory_mb: int, data_root: Optional[str] = None, avoid_master: bool = False) -> Dict[str, Any]:
    """Deployments ``<stack>-main`` / ``<stack>-web`` and Services (``<stack>`` is a LoadBalancer: k3s ServiceLB
    answers on ``port`` of every node). ``avoid_master``: web pods run only on the other nodes."""
    probe = {"httpGet": {"path": "/__pskit/health", "port": port}, "periodSeconds": 10, "timeoutSeconds": 5}
    requests = {"cpu": f"{int(round(cpu * 1000))}m", "memory": f"{memory_mb}Mi"}

    def deployment(role: str, count: int, env: List[Dict[str, Any]], extra: Dict[str, Any]) -> Dict[str, Any]:
        labels = {"app": stack, "role": role}
        container: Dict[str, Any] = {
            "name": "host",
            "image": image,
            "imagePullPolicy": "Never",  # copied to every node by pskit, no registry
            "ports": [{"containerPort": port}],
            "env": env,
            "readinessProbe": probe,
            "livenessProbe": {**probe, "initialDelaySeconds": 30, "failureThreshold": 6},
            "resources": {"requests": requests},
        }
        pod: Dict[str, Any] = {"containers": [container]}
        if role == "main":
            container["volumeMounts"] = [{"name": "data", "mountPath": "/var/pskit/data"}]
            pod["volumes"] = [{"name": "data", "hostPath": {"path": f"{data_root or DATA_ROOT}/{stack}",
                                                             "type": "DirectoryOrCreate"}}]
            pod["nodeSelector"] = {"kubernetes.io/hostname": master_node}
        else:
            # One web replica per server before any gets a second (the scheduler's default lets 3 share a server),
            # so every server the load balancer sends to runs one.
            pod["topologySpreadConstraints"] = [{"maxSkew": 1, "topologyKey": "kubernetes.io/hostname",
                                                 "whenUnsatisfiable": "ScheduleAnyway",
                                                 "labelSelector": {"matchLabels": labels}}]
            if avoid_master:
                off_master = {"key": "kubernetes.io/hostname", "operator": "NotIn", "values": [master_node]}
                pod["affinity"] = {"nodeAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": {
                    "nodeSelectorTerms": [{"matchExpressions": [off_master]}]}}}
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": f"{stack}-{role}", "namespace": NAMESPACE, "labels": labels},
            "spec": {
                "replicas": count,
                "selector": {"matchLabels": labels},
                "template": {"metadata": {"labels": labels}, "spec": pod},
                **extra,
            },
        }

    def service(name: str, role: str, kind: str) -> Dict[str, Any]:
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": name, "namespace": NAMESPACE, "labels": {"app": stack}},
            "spec": {"type": kind, "selector": {"app": stack, "role": role},
                     "ports": [{"name": "http", "port": port, "targetPort": port}]},
        }

    replica = {"name": "PSKIT_REPLICA", "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}}}
    node = {"name": "PSKIT_NODE", "valueFrom": {"fieldRef": {"fieldPath": "spec.nodeName"}}}
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}},
            deployment("main", 1, [{"name": "PSKIT_HOST_ROLE", "value": "main"}, replica, node],
                       {"strategy": {"type": "Recreate"}}),
            service(f"{stack}-main", "main", "ClusterIP"),
            deployment(
                "web", replicas,
                [{"name": "PSKIT_HOST_ROLE", "value": "web"},
                 {"name": "PSKIT_MAIN_URL", "value": f"http://{stack}-main:{port}"}, replica, node],
                {"strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1}}},
            ),
            service(stack, "web", "LoadBalancer"),
        ],
    }


def nomad_job(stack: str, image: str, *, port: int, replicas: int, master_node: str, master_addr: str, cpu: float,
              memory_mb: int, data_root: Optional[str] = None) -> Dict[str, Any]:
    """A Nomad job (jobs API JSON). ``main`` holds ``port`` on the master; ``web`` holds it on each other server
    (one per server). Nomad does not load-balance: each of those servers answers on ``port`` itself. A load
    balancer in front of them is optional, and only for a single URL."""
    seconds = 10**9

    def group(role: str, count: int, env: Dict[str, str], constraints: List[Dict[str, str]]) -> Dict[str, Any]:
        # Group mode "host" is not enough. The Docker driver stays on its own bridge unless network_mode
        # is host, and then the published port is not on the server's loopback. /__pskit/health is checked
        # there. Host networking lets the process bind 0.0.0.0:<port> on the server itself. `ports` would
        # ask Docker to publish a port, which conflicts with host networking.
        config: Dict[str, Any] = {"image": image, "network_mode": "host", "force_pull": False}
        if role == "main":
            config["volumes"] = [f"{data_root or DATA_ROOT}/{stack}:/var/pskit/data"]
        return {
            "Name": role,
            "Count": count,
            "Constraints": constraints,
            "Networks": [{"Mode": "host", "ReservedPorts": [{"Label": "http", "Value": port, "To": port}]}],
            "RestartPolicy": {"Attempts": 10, "Interval": 30 * 60 * seconds, "Delay": 15 * seconds, "Mode": "delay"},
            "Update": {"MaxParallel": 1, "HealthCheck": "task_states", "MinHealthyTime": 10 * seconds,
                       "HealthyDeadline": 5 * 60 * seconds, "AutoRevert": True},
            "Tasks": [{
                "Name": "host",
                "Driver": "docker",
                "Config": config,
                "Env": env,
                "Resources": {"CPU": max(100, int(round(cpu * 1000))), "MemoryMB": memory_mb},
            }],
        }

    on_master = {"LTarget": "${node.unique.name}", "RTarget": master_node, "Operand": "="}
    return {
        "Job": {
            "ID": stack,
            "Name": stack,
            "Type": "service",
            "Datacenters": ["dc1"],
            "TaskGroups": [
                group("main", 1, {"PSKIT_HOST_ROLE": "main", "PSKIT_REPLICA": "main", "PSKIT_NODE": "${node.unique.name}"},
                      [on_master]),
                group(
                    "web", replicas,
                    {"PSKIT_HOST_ROLE": "web", "PSKIT_MAIN_URL": f"http://{master_addr}:{port}",
                     "PSKIT_REPLICA": "${node.unique.name}-${NOMAD_ALLOC_INDEX}", "PSKIT_NODE": "${node.unique.name}"},
                    [{**on_master, "Operand": "!="}, {"Operand": "distinct_hosts", "RTarget": "true"}],
                ),
            ],
        }
    }


def apply_script(orchestrator: str, stack: str, manifest: Dict[str, Any], port: int, timeout: int = 300,
                 data_path: str = "") -> str:
    """Runs on the master: apply the manifest and wait until the main replica answers ``/__pskit/health``.
    ``data_path``: the main replica's data folder on the master, created first (a bind mount needs it)."""
    doc = json.dumps(manifest, indent=1)
    path = f"pskit-cluster/{stack}.json"
    write = f"mkdir -p pskit-cluster\ncat > {path} <<'PSKIT_MANIFEST'\n{doc}\nPSKIT_MANIFEST\n"
    if data_path:
        write += f"as_root mkdir -p {_shq(data_path)}\n"
    if orchestrator == "swarm":
        run = (f"dk stack deploy --prune --resolve-image never -c {path} {_shq(stack)}\n"
               + _wait(f"dk service ls --filter label=com.docker.stack.namespace={stack} --format '{{{{.Replicas}}}}'"
                       " | awk -F'[/ ]' '$1 != $2 {bad=1} END {exit bad}'", timeout,
                       "replicas did not start", fail=False))
    elif orchestrator == "kubernetes":
        k = "as_root k3s kubectl"
        run = (f"{k} apply -f {path}\n"
               f"{k} rollout status deployment/{stack}-main -n {NAMESPACE} --timeout={timeout}s\n"
               f"{k} rollout status deployment/{stack}-web -n {NAMESPACE} --timeout={timeout}s || true\n")
    else:
        # Stop the previous job first. Main and web each bind this port on the host, so a new allocation
        # cannot start beside the old one. A missing job is fine (the DELETE fails and is ignored).
        run = (
            "export NOMAD_ADDR=http://127.0.0.1:4646\n"
            f"curl -fsS -X DELETE 'http://127.0.0.1:4646/v1/job/{stack}' >/dev/null 2>&1 || true\n"
            "pskit_stop=0\n"
            'while [ "$pskit_stop" -lt 30 ]; do\n'
            "  pskit_live=$(nomad job allocs -t "
            "'{{range .}}{{if eq .ClientStatus \"running\"}}x{{end}}{{end}}' "
            f"{_shq(stack)} 2>/dev/null || true)\n"
            '  [ -z "$pskit_live" ] && break\n'
            "  pskit_stop=$((pskit_stop + 1))\n"
            "  sleep 2\ndone\n"
            "curl -fsS -X POST -H 'Content-Type: application/json' --data @" + path
            + " http://127.0.0.1:4646/v1/jobs\necho\n"
        )
    health = f"curl -fsS -m 3 http://127.0.0.1:{port}/__pskit/health >/dev/null 2>&1"
    progress, on_fail = _apply_progress(orchestrator, stack)
    waited = _wait(health, timeout, f"no answer on http://127.0.0.1:{port}/__pskit/health",
                   progress=progress, on_fail=on_fail)
    return _header() + write + run + waited


def destroy_script(orchestrator: str, stack: str) -> str:
    if orchestrator == "swarm":
        return _header() + f"dk stack rm {_shq(stack)} || true\n"
    if orchestrator == "kubernetes":
        return _header() + f"as_root k3s kubectl delete deployment,service -n {NAMESPACE} -l app={stack} --ignore-not-found\n"
    return _header() + f"curl -fsS -X DELETE 'http://127.0.0.1:4646/v1/job/{stack}?purge=true' >/dev/null || true\n"


def scale_script(orchestrator: str, stack: str, replicas: int, nomad_job_now: Optional[Dict[str, Any]] = None) -> str:
    """Set the web replicas. Nomad: re-register the running job with the new count (its scale API refuses while a
    deployment is still placing replicas, which is exactly when a full cluster needs more)."""
    if orchestrator == "swarm":
        return _header() + f"dk service scale --detach {_shq(stack + '_web')}={int(replicas)}\n"
    if orchestrator == "kubernetes":
        return _header() + f"as_root k3s kubectl scale deployment/{stack}-web -n {NAMESPACE} --replicas={int(replicas)}\n"
    job = dict(nomad_job_now or {})
    job["TaskGroups"] = [{**g, "Count": int(replicas)} if g.get("Name") == "web" else g
                         for g in job.get("TaskGroups") or []]
    path = f"pskit-cluster/{stack}-scale.json"
    return _header() + (
        f"mkdir -p pskit-cluster\ncat > {path} <<'PSKIT_MANIFEST'\n{json.dumps({'Job': job})}\nPSKIT_MANIFEST\n"
        f"curl -fsS -X POST -H 'Content-Type: application/json' --data @{path} http://127.0.0.1:4646/v1/jobs\necho\n"
    )


# ---------------------------------------------------------------------------------------------- helpers
def _swarm_locked_check() -> str:
    """A locked swarm manager needs its unlock key; pskit never leaves it (that would drop the swarm's data)."""
    return (
        'if [ "$state" = "locked" ]; then\n'
        '  echo "pskit: this server\'s swarm is locked. Run docker swarm unlock, or docker swarm leave --force,'
        ' and retry" >&2\n'
        "  exit 1\n"
        "fi\n"
    )


def _wait(check: str, seconds: int, message: str, *, fail: bool = True, progress: str = "",
          on_fail: str = "") -> str:
    """Retry ``check`` every 2 s for ``seconds``; then fail with ``message`` (or only warn).

    ``progress`` runs on the first miss and every 10 s after that, so a long wait shows what the orchestrator
    is doing instead of sitting silent. ``on_fail`` runs once when the wait gives up."""
    tick = ""
    if progress:
        tick = (
            '  if [ $((pskit_i % 5)) -eq 1 ]; then\n'
            f'    echo "pskit: waiting ({message})"\n'
            + _indent(progress, 4)
            + "  fi\n"
        )
    end = f'  echo "pskit: {message}" >&2\n'
    if on_fail:
        end += _indent(on_fail, 2)
    if fail:
        end += "  exit 1\n"
    return (
        "pskit_ok=0\npskit_i=0\n"
        f'while [ "$pskit_i" -lt {max(1, seconds // 2)} ]; do\n'
        f"  if {check}; then pskit_ok=1; break; fi\n"
        "  pskit_i=$((pskit_i + 1))\n"
        + tick
        + "  sleep 2\ndone\n"
        f'if [ "$pskit_ok" != "1" ]; then\n{end}fi\n'
    )


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "".join(pad + line + "\n" for line in text.strip("\n").split("\n"))


def _apply_progress(orchestrator: str, stack: str) -> Tuple[str, str]:
    """Shell run while a deploy waits for ``/__pskit/health``, and (for Nomad) the dump printed if it never answers."""
    if orchestrator == "swarm":
        filt = _shq("label=com.docker.stack.namespace=" + stack)
        return f"dk service ls --filter {filt} || true\n", ""
    if orchestrator == "kubernetes":
        return (f"as_root k3s kubectl get pods -n {NAMESPACE} -l app={stack} -o wide || true\n", "")
    return _nomad_watch(stack), (
        'echo "pskit: this check is the main replica on the master (127.0.0.1), not a load balancer" >&2\n'
        'echo "pskit: Nomad does not load-balance. Each server answers on its own port." >&2\n'
        f"nomad job status {_shq(stack)} >&2 || true\n"
        + _nomad_watch(stack)
    )


def _nomad_watch(stack: str) -> str:
    """One snapshot: every allocation, then events and recent logs for main and for anything not running.

    The main replica is the one ``/__pskit/health`` on the master is waiting for. A web replica on another
    server does not open that port."""
    quoted = _shq(stack)
    table = (
        "nomad job allocs -t "
        r"""'{{range .}}{{printf "  %-8s %-12s %s\n" .TaskGroup .ClientStatus .NodeName}}{{end}}' """
        + quoted
    )
    ids = (
        "nomad job allocs -t "
        "'{{range .}}{{if or (ne .ClientStatus \"running\") (eq .TaskGroup \"main\")}}"
        "{{println .ID}}{{end}}{{end}}' "
        + quoted
    )
    awk = "'f { print; c++; if (c == 8) exit } /Recent Events/ { f = 1; c = 0; print }'"
    return (
        f'echo "pskit: Nomad allocations for {stack}:"\n'
        f"{table} 2>&1 || true\n"
        f"for pskit_alloc in $({ids} 2>/dev/null || true); do\n"
        '  echo "pskit: allocation $pskit_alloc"\n'
        f'  nomad alloc status "$pskit_alloc" 2>/dev/null | awk {awk} || true\n'
        '  nomad alloc logs -stderr -tail -n 20 "$pskit_alloc" host 2>/dev/null || true\n'
        '  nomad alloc logs -stdout -tail -n 10 "$pskit_alloc" host 2>/dev/null || true\n'
        "done\n"
    )


def _nomad_config(advertise: str, *, server: bool, servers: List[str]) -> str:
    lines = [
        'datacenter = "dc1"',
        'data_dir = "/opt/nomad/data"',
        'bind_addr = "0.0.0.0"',
        f'advertise {{\n  http = "{advertise}"\n  rpc = "{advertise}"\n  serf = "{advertise}"\n}}',
    ]
    if server:
        lines.append("server {\n  enabled = true\n  bootstrap_expect = 1\n}")
    joined = ", ".join(f'"{s}:4647"' for s in servers)
    lines.append(f"client {{\n  enabled = true\n  servers = [{joined}]\n}}")
    lines.append('plugin "docker" {\n  config {\n    volumes {\n      enabled = true\n    }\n  }\n}')
    return "\n".join(lines) + "\n"


_NOMAD_UNIT = """[Unit]
Description=HashiCorp Nomad agent (pskit cluster)
Wants=network-online.target
After=network-online.target docker.service

[Service]
ExecStart=/usr/local/bin/nomad agent -config /etc/nomad.d
ExecReload=/bin/kill -HUP $MAINPID
KillMode=process
KillSignal=SIGINT
Restart=on-failure
RestartSec=2
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
"""


def _nomad_agent_script(config: str, version: str) -> str:
    url = f"https://releases.hashicorp.com/nomad/{version}/nomad_{version}_linux_$a.zip"
    return (
        _header() + _docker_install_block() + _docker_ready_block()
        + "if ! need nomad; then\n"
        + '  case "$(uname -m)" in x86_64|amd64) a=amd64 ;; aarch64|arm64) a=arm64 ;;'
        + ' *) echo "pskit: Nomad has no build for $(uname -m)" >&2; exit 1 ;; esac\n'
        + "  need unzip || pkg_install unzip\n"
        + f'  curl -fsSL -o /tmp/pskit-nomad.zip "{url}"\n'
        + "  as_root unzip -o /tmp/pskit-nomad.zip nomad -d /usr/local/bin\n"
        + "  rm -f /tmp/pskit-nomad.zip\n"
        + "fi\n"
        + "as_root mkdir -p /etc/nomad.d /opt/nomad/data\n"
        + f"cat > /tmp/pskit-nomad.hcl <<'PSKIT_HCL'\n{config}PSKIT_HCL\n"
        + f"cat > /tmp/pskit-nomad.service <<'PSKIT_UNIT'\n{_NOMAD_UNIT}PSKIT_UNIT\n"
        + "changed=0\n"
        + "cmp -s /tmp/pskit-nomad.hcl /etc/nomad.d/nomad.hcl || { as_root mv /tmp/pskit-nomad.hcl /etc/nomad.d/nomad.hcl;"
        + " changed=1; }\n"
        + "cmp -s /tmp/pskit-nomad.service /etc/systemd/system/nomad.service || { as_root mv /tmp/pskit-nomad.service"
        + " /etc/systemd/system/nomad.service; changed=1; }\n"
        + "rm -f /tmp/pskit-nomad.hcl /tmp/pskit-nomad.service\n"
        + "as_root systemctl daemon-reload\n"
        + "as_root systemctl enable nomad >/dev/null 2>&1 || true\n"
        + 'if [ "$changed" = "1" ] || ! as_root systemctl is-active --quiet nomad; then as_root systemctl restart nomad; fi\n'
        + _wait("curl -fsS -m 3 http://127.0.0.1:4646/v1/agent/self >/dev/null 2>&1", 90, "Nomad did not start")
        + 'echo "PSKIT_NODE=$(hostname)"\n'
    )
