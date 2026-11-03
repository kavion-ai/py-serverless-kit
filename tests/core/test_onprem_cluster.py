"""Scaling clusters (Swarm / Kubernetes / Nomad): scripts, manifests, the SSH flows, status, alerts and deploy."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from py_serverless_kit.core import onprem_cluster as clu
from py_serverless_kit.core import onprem_cluster_scripts as scripts
from py_serverless_kit.core import onprem_lb as lb
from py_serverless_kit.core import onprem_servers as srv

STAT_A = "cpu  100 0 100 800 0 0 0 0 0 0"
STAT_B = "cpu  190 0 190 820 0 0 0 0 0 0"  # 180 busy of 200 -> 90 %


class FakeSSH:
    """Records every command; answers scripts by their file name and metrics by server."""

    def __init__(self, nodes: Optional[dict] = None) -> None:
        self.calls: List[List[str]] = []
        self.scripts: List[Tuple[str, str]] = []  # (host, script text)
        self.nodes = nodes or {}
        self.status_out = ""
        self.has_image = False

    def __call__(self, argv: List[str], stdout: Optional[Path]) -> Tuple[int, str]:
        self.calls.append(argv)
        if argv[:3] == ["docker", "save", "-o"]:
            Path(argv[3]).write_bytes(b"image layers " * 1000)
            return 0, ""
        if argv[0] in ("scp", "sshpass") and any(a.endswith(".sh") for a in argv):
            local = next(a for a in argv if a.endswith(".sh") and Path(a).is_file())
            self.scripts.append((argv[-1].split("@")[-1].split(":")[0], Path(local).read_text("utf-8")))
            return 0, ""
        command = argv[-1]
        host = next((a.split("@")[-1] for a in argv if "@" in a), "")
        if command.startswith("sh pskit-cluster/master.sh") or command.startswith("sh pskit-cluster/join.sh"):
            return 0, f"installed\nPSKIT_NODE=node-{host}\n"
        if command.startswith("sh pskit-cluster/token.sh"):
            return 0, "PSKIT_TOKEN=SWMTKN-1-secret\n"
        if command.startswith("sh pskit-cluster/status.sh"):
            return 0, self.status_out
        if "/proc/stat" in command:
            if host not in self.nodes:
                return 255, "ssh: connect to host: Connection timed out"
            cpu_b, mem_avail = self.nodes[host]
            return 0, (f"cpu_a={STAT_A}\ncpu_b={cpu_b}\ncpus=4\nmem_total_kb=4000000\nmem_avail_kb={mem_avail}\n"
                       "disk_total_kb=1000000\ndisk_used_kb=500000\nload=0.5 0.4 0.3\nhostname=x\n")
        if "image inspect" in command or "images ls" in command:
            return (0 if self.has_image else 1), ""
        if command.startswith("curl -fsS http://127.0.0.1:4646/v1/nodes"):
            return 0, json.dumps([{"Name": "node-10.0.0.6", "ID": "abc-123"}])
        return 0, ""

    def script(self, name_part: str) -> str:
        return next(text for _host, text in reversed(self.scripts) if name_part in text)


@pytest.fixture
def servers(tmp_path: Path) -> Path:
    for name, host in (("edge1", "10.0.0.5"), ("edge2", "10.0.0.6"), ("edge3", "10.0.0.7")):
        srv.save_server(tmp_path, name, {"host": host, "user": "root", "auth": "agent"})
    return tmp_path


def _sh_ok(text: str) -> None:
    """The script parses as POSIX sh (when a shell is available here)."""
    shell = shutil.which("sh") or shutil.which("bash")
    if shell is None:
        return
    proc = subprocess.run([shell, "-n"], input=text.encode("utf-8"), capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode()


# ------------------------------------------------------------------------------------------- scripts
@pytest.mark.parametrize("orch", ["swarm", "kubernetes", "nomad"])
def test_every_script_is_valid_sh(orch):
    manifests = {
        "swarm": scripts.swarm_stack("pskit-shop-dev", "pskit-shop-dev:abc", port=8080, replicas=2, master_node="m",
                                     cpu=0.25, memory_mb=256),
        "kubernetes": scripts.kubernetes_manifest("pskit-shop-dev", "pskit-shop-dev:abc", port=8080, replicas=2,
                                                  master_node="m", cpu=0.25, memory_mb=256),
        "nomad": scripts.nomad_job("pskit-shop-dev", "pskit-shop-dev:abc", port=8080, replicas=2, master_node="m",
                                   master_addr="10.0.0.5", cpu=0.25, memory_mb=256),
    }
    for text in (
        scripts.master_script(orch, "10.0.0.5"),
        scripts.join_token_script(orch),
        scripts.join_script(orch, "10.0.0.5", "tok'en", "10.0.0.6"),
        scripts.leave_script(orch),
        scripts.drain_script(orch, "node-b", "id-1"),
        scripts.forget_script(orch, "node-b", "id-1"),
        scripts.forget_stale_script(orch, "node-b", "id-1"),
        scripts.join_script(orch, "10.0.0.5", "tok", "10.0.0.6", members=["abc", "def"]),
        scripts.status_script(orch),
        scripts.image_load_script(orch, "pskit-cluster/img.parts", "ab" * 32, "pskit-cluster/img-*.parts"),
        scripts.prune_script(orch, "pskit-shop-dev", "abc"),
        scripts.apply_script(orch, "pskit-shop-dev", manifests[orch], 8080),
        scripts.destroy_script(orch, "pskit-shop-dev"),
        scripts.scale_script(orch, "pskit-shop-dev", 4),
    ):
        assert text.startswith("#!/bin/sh\nset -eu\n")
        _sh_ok(text)


def test_scripts_install_and_join_each_orchestrator():
    swarm = scripts.master_script("swarm", "10.0.0.5")
    assert "dk swarm init --advertise-addr '10.0.0.5'" in swarm and "{{.Swarm.LocalNodeState}}" in swarm
    join = scripts.join_script("swarm", "10.0.0.5", "SWMTKN-1-x", "10.0.0.6")
    assert "dk swarm join --advertise-addr '10.0.0.6' --token 'SWMTKN-1-x' '10.0.0.5:2377'" in join
    assert "trap 'rm -f \"$0\"' EXIT" in join  # the join token does not stay on the server
    k3s = scripts.join_script("kubernetes", "10.0.0.5", "K10abc", "10.0.0.6")
    assert "K3S_URL='https://10.0.0.5:6443' K3S_TOKEN='K10abc'" in k3s and "get.k3s.io" in k3s
    assert "--tls-san 10.0.0.5" in scripts.master_script("kubernetes", "10.0.0.5")
    nomad = scripts.master_script("nomad", "10.0.0.5", "1.11.3")
    assert "releases.hashicorp.com/nomad/1.11.3/nomad_1.11.3_linux_$a.zip" in nomad
    assert "bootstrap_expect = 1" in nomad and 'servers = ["10.0.0.5:4647"]' in nomad
    worker = scripts.join_script("nomad", "10.0.0.5", "", "10.0.0.6")
    assert "server {" not in worker and 'http = "10.0.0.6"' in worker
    assert scripts.stack_name("Shop_API", "Dev") == "pskit-shop-api-dev"


def _run_swarm_join(tmp_path: Path, state: str, manager: str, node_id: str, members: List[str],
                    others: int = 0, services: int = 0) -> Tuple[int, str, List[str]]:
    """Run the swarm join script against a fake ``docker`` that reports the given swarm state."""
    sh = shutil.which("sh")
    if sh is None:
        pytest.skip("no POSIX sh here")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    fake = (
        "#!/bin/sh\n"
        f'echo "$*" >> "{log.as_posix()}"\n'
        'case "$1 $2" in\n'
        f"  'info --format') case \"$3\" in *LocalNodeState*) echo '{state} {manager} {node_id}' ;;"
        f" *NodeID*) echo new-id ;; *) echo node-x ;; esac ;;\n"
        f"  'node ls') i=0; echo '{node_id}'; while [ $i -lt {others} ]; do echo other$i; i=$((i+1)); done ;;\n"
        f"  'service ls') i=0; while [ $i -lt {services} ]; do echo svc$i; i=$((i+1)); done ;;\n"
        "esac\nexit 0\n"
    )
    for name, text in (("docker", fake), ("curl", "#!/bin/sh\nexit 0\n")):
        path = bin_dir / name
        path.write_bytes(text.encode("utf-8"))
        path.chmod(0o755)
    script = tmp_path / "join.sh"
    script.write_bytes(scripts.join_script("swarm", "10.0.0.5", "SWMTKN", "10.0.0.6", members=members)
                       .encode("utf-8"))
    env = {"PATH": f"{bin_dir.as_posix()}:/usr/bin:/bin", "HOME": tmp_path.as_posix()}
    proc = subprocess.run([sh, script.as_posix()], capture_output=True, env=env, timeout=60)
    calls = log.read_text("utf-8").splitlines() if log.exists() else []
    return proc.returncode, proc.stdout.decode() + proc.stderr.decode(), calls


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh")
@pytest.mark.parametrize("state,manager,node_id,members,leaves,joins,ok", [
    ("inactive", "false", "", ["m1"], False, True, True),         # fresh server
    ("pending", "false", "old", ["m1"], True, True, True),        # a join that stopped half way
    ("error", "false", "old", ["m1"], True, True, True),          # removed from the swarm while it was off
    ("active", "false", "old", ["m1"], True, True, True),         # worker of a swarm set up again / another swarm
    ("active", "false", "w1", ["m1", "w1"], False, False, True),  # already a member: nothing to do
    ("active", "true", "solo", ["m1"], True, True, True),         # empty single-node swarm of its own
    ("locked", "false", "x", ["m1"], False, False, False),        # needs its unlock key
])
def test_swarm_join_recovers_from_stale_membership(tmp_path, state, manager, node_id, members, leaves, joins, ok):
    code, out, calls = _run_swarm_join(tmp_path, state, manager, node_id, members)
    assert (code == 0) == ok, out
    assert any(c.startswith("swarm leave") for c in calls) == leaves, calls
    assert any(c.startswith("swarm join") for c in calls) == joins, calls
    if ok:
        assert "PSKIT_NODE_ID=new-id" in out


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh")
def test_swarm_join_refuses_to_break_another_swarm(tmp_path):
    code, out, calls = _run_swarm_join(tmp_path, "active", "true", "boss", ["m1"], others=2, services=1)
    assert code == 1 and "manages another swarm (2 other node(s), 1 service(s))" in out
    assert not any(c.startswith(("swarm leave", "swarm join")) for c in calls)


def test_rejoin_scripts_clean_up_old_state():
    master = scripts.master_script("swarm", "10.0.0.5")
    assert "dk swarm leave --force" in master and '"$state" = "pending"' in master
    k3s = scripts.join_script("kubernetes", "10.0.0.5", "K10abc", "10.0.0.6")
    assert "k3s-agent-uninstall.sh" in k3s and "grep -qF 'K10abc'" in k3s and "k3s-uninstall.sh ]" in k3s
    stale = scripts.forget_stale_script("swarm", "node-b", "id-1")
    assert "dk node rm --force" in stale and "'id-1'" in stale
    assert "node rm" not in scripts.forget_stale_script("kubernetes", "node-b", "id-1")
    assert "PSKIT_MEMBERS=" in scripts.join_token_script("swarm")


def test_join_server_passes_members_and_forgets_stale_nodes(servers):
    class SSH(FakeSSH):
        def __call__(self, argv, stdout):
            command = argv[-1]
            if command.startswith("sh pskit-cluster/token.sh"):
                self.calls.append(argv)
                return 0, "PSKIT_TOKEN=SWMTKN-1-secret\nPSKIT_MEMBERS=m-id w-old \n"
            if command.startswith("sh pskit-cluster/join.sh"):
                self.calls.append(argv)
                return 0, "PSKIT_NODE=node-b\nPSKIT_NODE_ID=w-new\n"
            return super().__call__(argv, stdout)

    ssh = SSH()
    clu.create_cluster(servers, "fun", "swarm", "edge1", lambda _m: None, run=ssh)
    clu.join_server(servers, "fun", "edge2", lambda _m: None, run=ssh)
    assert "members='m-id w-old'" in ssh.script("dk swarm join")
    stale = ssh.script("dk node rm --force \"$id\"")
    assert "'w-new'" in stale and "'node-b'" in stale


def test_workloads_split_main_and_web():
    stack = scripts.swarm_stack("pskit-shop-dev", "pskit-shop-dev:abc", port=8080, replicas=3, master_node="m1",
                                cpu=0.5, memory_mb=512, python="python3")
    main, web = stack["services"]["main"], stack["services"]["web"]
    assert main["deploy"]["replicas"] == 1 and main["deploy"]["placement"]["constraints"] == ["node.hostname == m1"]
    assert main["volumes"] == ["data:/var/pskit/data"] and "ports" not in main
    assert web["deploy"]["replicas"] == 3 and web["ports"][0]["published"] == 8080
    assert web["environment"]["PSKIT_MAIN_URL"] == "http://main:8080" and web["environment"]["PSKIT_HOST_ROLE"] == "web"
    assert web["deploy"]["resources"]["reservations"] == {"cpus": "0.5", "memory": "512M"}
    assert web["healthcheck"]["test"][1] == "python3"

    k8s = scripts.kubernetes_manifest("pskit-shop-dev", "pskit-shop-dev:abc", port=8080, replicas=3, master_node="m1",
                                      cpu=0.25, memory_mb=256)
    kinds = [(i["kind"], i["metadata"]["name"]) for i in k8s["items"]]
    assert kinds == [("Namespace", "pskit"), ("Deployment", "pskit-shop-dev-main"), ("Service", "pskit-shop-dev-main"),
                     ("Deployment", "pskit-shop-dev-web"), ("Service", "pskit-shop-dev")]
    main_pod = k8s["items"][1]["spec"]["template"]["spec"]
    assert main_pod["nodeSelector"] == {"kubernetes.io/hostname": "m1"}
    assert main_pod["containers"][0]["imagePullPolicy"] == "Never"
    web_env = {e["name"]: e.get("value") for e in k8s["items"][3]["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert web_env["PSKIT_MAIN_URL"] == "http://pskit-shop-dev-main:8080"
    assert k8s["items"][4]["spec"]["type"] == "LoadBalancer"
    assert k8s["items"][3]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"] == {
        "cpu": "250m", "memory": "256Mi"}

    job = scripts.nomad_job("pskit-shop-dev", "img:1", port=8080, replicas=2, master_node="m1", master_addr="10.0.0.5",
                            cpu=0.5, memory_mb=256)["Job"]
    main_g, web_g = job["TaskGroups"]
    assert main_g["Count"] == 1 and main_g["Constraints"][0]["Operand"] == "="
    assert web_g["Count"] == 2 and {c["Operand"] for c in web_g["Constraints"]} == {"!=", "distinct_hosts"}
    assert web_g["Tasks"][0]["Env"]["PSKIT_MAIN_URL"] == "http://10.0.0.5:8080"
    assert web_g["Tasks"][0]["Resources"] == {"CPU": 500, "MemoryMB": 256}
    assert web_g["Tasks"][0]["Config"]["network_mode"] == "host"
    assert "ports" not in web_g["Tasks"][0]["Config"]
    assert main_g["Tasks"][0]["Config"]["network_mode"] == "host"
    apply = scripts.apply_script("nomad", "pskit-shop-dev", {"Job": job}, 8080)
    assert "<<'PSKIT_MANIFEST'" in apply and "--data @pskit-cluster/pskit-shop-dev.json" in apply
    assert "network_mode" in apply and "nomad job allocs" in apply and "nomad alloc logs" in apply
    assert "DELETE 'http://127.0.0.1:4646/v1/job/pskit-shop-dev'" in apply
    assert "not a load balancer" in apply
    _sh_ok(apply)


# ------------------------------------------------------------------------------------------- parsing
def test_parse_orchestrator_outputs():
    swarm = "\n".join([
        f"{scripts.MARK}nodes",
        json.dumps({"Hostname": "m1", "Status": "Ready", "Availability": "Active", "ManagerStatus": "Leader"}),
        json.dumps({"Hostname": "w1", "Status": "Down", "Availability": "Drain", "ManagerStatus": ""}),
        f"{scripts.MARK}services",
        json.dumps({"Name": "pskit-shop-dev_web", "Replicas": "2/3 (max 1 per node)"}),
        f"{scripts.MARK}pending",
        json.dumps({"Name": "pskit-shop-dev_web.3", "CurrentState": "Pending 2 minutes ago",
                    "Error": "no suitable node (insufficient resources on 2 nodes)"}),
    ])
    view = clu.parse_orchestrator("swarm", swarm)
    assert view["nodes"]["m1"]["ready"] and view["nodes"]["m1"]["manager"]
    assert view["nodes"]["w1"]["availability"] == "Drain" and not view["nodes"]["w1"]["ready"]
    assert view["workloads"] == [{"name": "pskit-shop-dev_web", "running": 2, "desired": 3}]
    assert view["pending"] == ["pskit-shop-dev_web.3: no suitable node (insufficient resources on 2 nodes)"]

    nodes = {"items": [{"metadata": {"name": "m1", "labels": {"node-role.kubernetes.io/control-plane": "true"}},
                        "spec": {}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}}]}
    deps = {"items": [{"metadata": {"name": "pskit-shop-dev-web"}, "spec": {"replicas": 3},
                       "status": {"readyReplicas": 1}}]}
    pods = {"items": [{"metadata": {"name": "web-x"}, "status": {"conditions": [
        {"message": "0/1 nodes are available: 1 Insufficient cpu."}]}}]}
    k8s = clu.parse_orchestrator("kubernetes", "\n".join([f"{scripts.MARK}nodes", json.dumps(nodes),
                                                          f"{scripts.MARK}services", json.dumps(deps),
                                                          f"{scripts.MARK}pending", json.dumps(pods)]))
    assert k8s["nodes"]["m1"] == {"ready": True, "state": "Ready", "availability": "Active", "manager": True}
    assert k8s["workloads"][0]["running"] == 1 and "Insufficient cpu" in k8s["pending"][0]

    jobs = [{"ID": "pskit-shop-dev", "JobSummary": {"Summary": {"main": {"Running": 1}, "web": {"Running": 1,
                                                                                               "Queued": 2}}}}]
    nomad = clu.parse_orchestrator("nomad", "\n".join([
        f"{scripts.MARK}nodes", json.dumps([{"Name": "m1", "Status": "ready", "ID": "x", "SchedulingEligibility":
                                             "eligible"}]),
        f"{scripts.MARK}services", json.dumps(jobs)]))
    assert nomad["nodes"]["m1"]["ready"] and nomad["workloads"][1] == {"name": "pskit-shop-dev/web", "running": 1,
                                                                      "desired": 3}
    assert nomad["pending"] == ["pskit-shop-dev/web: 2 allocation(s) cannot be placed"]


def test_node_metrics():
    fake = FakeSSH({"10.0.0.5": (STAT_B, 1000000)})
    m = clu.node_metrics({"method": "ssh", "host": "10.0.0.5", "user": "root", "port": 22}, run=fake)
    assert m["reachable"] and m["cpu"] == 90.0 and m["memory"] == 75.0 and m["disk"] == 50.0 and m["cpus"] == 4
    down = clu.node_metrics({"method": "ssh", "host": "10.9.9.9", "user": "root", "port": 22}, run=fake)
    assert down == {"reachable": False, "error": "ssh: connect to host: Connection timed out"}


# ------------------------------------------------------------------------------------------- flows
def test_create_join_status_leave(servers):
    fake = FakeSSH({"10.0.0.5": (STAT_B, 1000000), "10.0.0.6": ("cpu  110 0 110 980 0 0 0 0 0 0", 3000000)})
    lines: List[str] = []
    created = clu.create_cluster(servers, "prod", "swarm", "edge1", lines.append, run=fake)
    assert created["nodes"] == [{"server": "edge1", "role": "master", "node": "node-10.0.0.5", "address": "10.0.0.5",
                                 "joined_at": created["nodes"][0]["joined_at"]}]
    assert "dk swarm init --advertise-addr '10.0.0.5'" in fake.script("swarm init")
    with pytest.raises(clu.ClusterError, match="already in cluster"):
        clu.create_cluster(servers, "other", "nomad", "edge1", lines.append, run=fake)

    joined = clu.join_server(servers, "prod", "edge2", lines.append, run=fake)
    assert [n["server"] for n in joined["nodes"]] == ["edge1", "edge2"]
    assert "--token 'SWMTKN-1-secret' '10.0.0.5:2377'" in fake.script("swarm join")
    assert not any("SWMTKN" in line for line in lines)  # the token is never printed

    fake.status_out = "\n".join([
        f"{scripts.MARK}nodes",
        json.dumps({"Hostname": "node-10.0.0.5", "Status": "Ready", "Availability": "Active", "ManagerStatus": "x"}),
        json.dumps({"Hostname": "node-10.0.0.6", "Status": "Ready", "Availability": "Active", "ManagerStatus": ""}),
        f"{scripts.MARK}services", f"{scripts.MARK}pending",
    ])
    current = clu.status(servers, "prod", run=fake)
    by = {n["server"]: n for n in current["nodes"]}
    assert by["edge1"]["full"] and by["edge1"]["over"] == ["cpu"]  # 90 % >= 85 %
    assert not by["edge2"]["full"] and by["edge2"]["cpu"] == 10.0
    assert current["full"] is False and current["reasons"] == []

    clu.leave_server(servers, "prod", "edge2", lines.append, run=fake)
    assert "dk node update --availability drain 'node-10.0.0.6'" in fake.script("availability drain")
    assert "dk swarm leave --force" in fake.script("swarm leave")
    assert [n["server"] for n in clu.public("prod", clu.get_cluster(servers, "prod"))["nodes"]] == ["edge1"]
    with pytest.raises(clu.ClusterError, match="master cannot leave"):
        clu.leave_server(servers, "prod", "edge1", lines.append, run=fake)


def test_nomad_leave_uses_the_node_id(servers):
    fake = FakeSSH()
    clu.create_cluster(servers, "lab", "nomad", "edge1", lambda _l: None, run=fake)
    clu.join_server(servers, "lab", "edge2", lambda _l: None, run=fake)
    clu.leave_server(servers, "lab", "edge2", lambda _l: None, run=fake)
    assert "/v1/node/'abc-123'/drain" in fake.script("/drain")
    assert "/v1/node/'abc-123'/purge" in fake.script("/purge")


@pytest.mark.parametrize("orchestrator, master_cmd, worker_cmd", [
    ("swarm", "dk swarm leave --force", "dk swarm leave --force"),
    ("kubernetes", "/usr/local/bin/k3s-uninstall.sh", "/usr/local/bin/k3s-agent-uninstall.sh"),
    ("nomad", "/usr/local/bin/nomad", "/usr/local/bin/nomad"),
])
def test_remove_uninstall_takes_the_orchestrator_off_master_and_workers(servers, orchestrator, master_cmd, worker_cmd):
    fake = FakeSSH()
    clu.create_cluster(servers, "prod", orchestrator, "edge1", lambda _l: None, run=fake)
    clu.join_server(servers, "prod", "edge2", lambda _l: None, run=fake)
    clu._update(servers, "prod", lambda c: c.setdefault("deployments", {}).__setitem__(
        "pskit-shop-dev", {"service": "shop", "stage": "dev", "image": "pskit-shop-dev:abc", "port": 8080}))
    fake.scripts.clear()
    lines: List[str] = []
    clu.remove_cluster(servers, "prod", lines.append, uninstall=True, run=fake)

    assert "prod" not in clu.load_clusters(servers)
    uninstalls = [(host, text) for host, text in fake.scripts if "rm -rf pskit-cluster" in text]
    assert [host for host, _t in uninstalls] == ["10.0.0.6", "10.0.0.5"]  # joined servers first, the master last
    (_w, worker), (_m, master) = uninstalls
    assert worker_cmd in worker and master_cmd in master
    destroy = next(text for _h, text in fake.scripts if "pskit-shop-dev" in text and text not in (worker, master))
    assert destroy == scripts.destroy_script(orchestrator, "pskit-shop-dev")
    assert "/var/lib/pskit/pskit-shop-dev" not in master  # data stays unless asked
    assert any("--delete-data" in line for line in lines)
    for _h, text in uninstalls:
        _sh_ok(text)


def test_remove_uninstall_can_delete_data_and_survives_an_offline_server(servers):
    fake = FakeSSH()
    clu.create_cluster(servers, "prod", "swarm", "edge1", lambda _l: None, run=fake)
    clu.join_server(servers, "prod", "edge2", lambda _l: None, run=fake)
    clu._update(servers, "prod", lambda c: c.setdefault("deployments", {}).__setitem__("pskit-shop-dev", {}))

    def offline(argv: List[str], stdout: Optional[Path]) -> Tuple[int, str]:
        if any("10.0.0.6" in a for a in argv):
            return 255, "ssh: connect to host 10.0.0.6: Connection timed out"
        return fake(argv, stdout)

    fake.scripts.clear()
    lines: List[str] = []
    clu.remove_cluster(servers, "prod", lines.append, uninstall=True, delete_data=True, run=offline)
    assert "prod" not in clu.load_clusters(servers)
    assert any("edge2 did not answer" in line for line in lines)
    master = fake.script("rm -rf pskit-cluster")
    assert "as_root rm -rf '/var/lib/pskit/pskit-shop-dev'" in master
    assert "dk volume rm 'pskit-shop-dev_data'" in master
    assert "grep -E '^(pskit-shop-dev):'" in master


def test_plain_remove_only_forgets(servers):
    fake = FakeSSH()
    clu.create_cluster(servers, "prod", "kubernetes", "edge1", lambda _l: None, run=fake)
    fake.scripts.clear()
    lines: List[str] = []
    clu.remove_cluster(servers, "prod", lines.append, run=fake)
    assert fake.scripts == [] and "prod" not in clu.load_clusters(servers)
    assert any("--uninstall" in line for line in lines)


def test_full_cluster_alerts_once_per_cooldown(servers):
    fake = FakeSSH({"10.0.0.5": (STAT_B, 100000)})  # 90 % cpu, 97.5 % memory
    clu.create_cluster(servers, "prod", "kubernetes", "edge1", lambda _l: None, run=fake)
    fake.status_out = ""
    sent: List[dict] = []

    def send(root, name, current, test=False):
        sent.append(clu.alert_event(name, current, test=test))
        return {"sent": ["function notify"], "errors": []}

    clu.save_settings(servers, "prod", {"alert": {"function": "notify", "cooldown_minutes": 30}})
    first = clu.check(servers, "prod", run=fake, send=send)
    assert first["full"] and first["alert"]["sent"] == ["function notify"]
    event = sent[0]
    assert event["type"] == "pskit.cluster.capacity" and event["cluster"] == "prod"
    assert "pskit cluster join prod SERVER" in event["message"] and event["nodes"][0]["over"] == ["cpu", "memory"]

    clu._update(servers, "prod", lambda c: c.__setitem__("last_alert_ts", __import__("time").time()))
    second = clu.check(servers, "prod", run=fake, send=send)
    assert second["alert"]["skipped"] == "cooldown" and len(sent) == 1


def test_send_alert_records_errors(servers, monkeypatch):
    clu.create_cluster(servers, "prod", "swarm", "edge1", lambda _l: None, run=FakeSSH())
    entry = clu.send_alert(servers, "prod", {"orchestrator": "swarm"}, test=True)
    assert entry["errors"] == ["no alert function or webhook is set (cluster settings)"]

    posted: List[dict] = []
    monkeypatch.setattr(clu, "_post_webhook", lambda url, event: posted.append({"url": url, **event}))
    clu.save_settings(servers, "prod", {"alert": {"webhook": "https://hooks.example.com/x", "function": "notify"}})
    entry = clu.send_alert(servers, "prod", {"orchestrator": "swarm"}, test=True)
    assert entry["sent"] == ["webhook"] and "no deployed on-prem stage" in entry["errors"][0]
    assert posted[0]["test"] is True and posted[0]["url"] == "https://hooks.example.com/x"
    assert [a["test"] for a in clu.get_cluster(servers, "prod")["alerts"]] == [True, True]
    with pytest.raises(clu.ClusterError, match="http"):
        clu.save_settings(servers, "prod", {"alert": {"webhook": "ftp://x"}})
    with pytest.raises(clu.ClusterError, match="10..100"):
        clu.save_settings(servers, "prod", {"capacity": {"cpu": 5}})


# ------------------------------------------------------------------------------------------- deploy
def test_deploy_target_is_one_server_or_a_cluster(servers):
    from py_serverless_kit.core import onprem_control as ctl

    clu.create_cluster(servers, "prod", "swarm", "edge1", lambda _l: None, run=FakeSSH())
    # --cluster on a project without options.cluster; replicas from pskit.yml are kept when another name is given
    options: dict = {"deploy": {"method": "local"}}
    assert srv.resolve_deploy(options, servers, "dev", cluster="prod") == "edge1"
    assert options["cluster"]["name"] == "prod" and options["deploy"]["method"] == "docker"
    options = {"cluster": {"name": "old", "replicas": 4}}
    srv.resolve_deploy(options, servers, "dev", cluster="prod")
    assert options["cluster"]["replicas"] == 4 and options["cluster"]["name"] == "prod"
    # --server wins over options.cluster: one machine
    options = {"cluster": "prod", "deploy": {"python": "bundle"}}
    assert srv.resolve_deploy(options, servers, "dev", "edge3") == "edge3"
    assert "cluster" not in options and options["deploy"]["host"] == "10.0.0.7"
    with pytest.raises(srv.ServerError, match="pick one"):
        srv.resolve_deploy({}, servers, "dev", "edge2", "prod")

    # the stage remembers the cluster of its last deploy
    work = servers / ".pskit" / "onprem-dev"
    (work / "onprem_app").mkdir(parents=True)
    (work / "onprem_app" / "pskit_host.json").write_text(json.dumps(
        {"port": 8080, "deploy": {"method": "cluster", "ssh": {"host": "10.0.0.5", "user": "root"}}}), "utf-8")
    data = ctl.remember_deploy(work, "edge1", "prod")
    assert srv.deployed_cluster(servers, "dev") == "prod" and srv.deployed_server(servers, "dev") == "edge1"
    assert ctl.deployed_on(data["spec"], "edge1", "prod")["label"] == "cluster prod (master edge1 (10.0.0.5))"
    options = {"deploy": {"method": "local"}}
    assert srv.resolve_deploy(options, servers, "dev") == "edge1" and options["cluster"]["name"] == "prod"
    options = {}
    assert srv.resolve_deploy(options, servers, "dev", srv.LOCAL) is None and "cluster" not in options
    clu.remove_cluster(servers, "prod", lambda _l: None)
    with pytest.raises(srv.ServerError, match="no longer exists"):
        srv.resolve_deploy({}, servers, "dev")


def test_studio_passes_the_cluster_to_deploy():
    from py_serverless_kit.studio.jobs import StudioError, build_argv

    assert build_argv("deploy", "onprem", "dev", {"cluster": "prod"}) == ["deploy", "--provider", "onprem",
                                                                          "--stage", "dev", "--cluster", "prod"]
    with pytest.raises(StudioError):
        build_argv("deploy", "onprem", "dev", {"cluster": "prod", "server": "edge1"})
    with pytest.raises(StudioError):
        build_argv("deploy", "onprem", "dev", {"cluster": "Bad Name"})


def test_resources_are_placed_on_the_freest_cluster_server(servers):
    from py_serverless_kit.core import onprem_services as svc

    # edge1 90 % cpu (over), edge2 25 % memory, edge3 50 % memory
    fake = FakeSSH({"10.0.0.5": (STAT_B, 3000000), "10.0.0.6": (STAT_A.replace("800", "900"), 3000000),
                    "10.0.0.7": (STAT_A.replace("800", "900"), 2000000)})
    clu.create_cluster(servers, "prod", "swarm", "edge1", lambda _l: None, run=fake)
    clu.join_server(servers, "prod", "edge2", lambda _l: None, run=fake, advertise="192.168.1.6")
    clu.join_server(servers, "prod", "edge3", lambda _l: None, run=fake)
    assert clu.place(servers, "prod", run=fake)["server"] == "edge2"
    assert clu.place(servers, "prod", "edge3")["server"] == "edge3"
    assert clu.place(servers, "prod", measure=False)["server"] == "edge1"  # the studio's quick check: no SSH
    with pytest.raises(clu.ClusterError, match="not in cluster"):
        clu.place(servers, "prod", "elsewhere")

    req = svc.check_request({"key": "cache", "service": "redis", "target": {"cluster": "prod"}}, servers, None,
                            run=fake)
    assert req["target"]["server"] == "edge2" and req["target"]["cluster"] == "prod"
    assert req["address"] == "192.168.1.6"  # the cluster address, reached by replicas on every server
    assert svc.describe_target(req["target"]) == "edge2 (root@10.0.0.6:22) in cluster prod"
    raw = {"provider": {"name": "onprem", "options": {"cluster": {"name": "prod", "replicas": 3}}}}
    assert svc.default_target(raw) == {"cluster": "prod"}
    assert svc.functions_target(raw, servers)["server"] == "edge1"

    state = svc.load_state(servers)
    state["services"]["cache"] = {"key": "cache", "service": "redis", "kind": "service", "target": req["target"],
                                  "address": req["address"], "port": 6379}
    svc.save_state(servers, state)
    fake.status_out = ""
    current = clu.status(servers, "prod", run=fake)
    assert current["resources"] == [{"key": "cache", "service": "redis", "kind": "service", "server": "edge2",
                                     "address": "192.168.1.6", "port": 6379}]
    assert {n["server"]: n["resources"] for n in current["nodes"]}["edge2"] == ["cache"]

    lines: List[str] = []
    clu.leave_server(servers, "prod", "edge2", lines.append, run=fake)
    assert "cluster" not in svc.load_state(servers)["services"]["cache"]["target"]  # keeps running on edge2
    assert any("cache (redis) on edge2" in line for line in lines)

    fake.nodes = {"10.0.0.5": (STAT_B, 3000000)}  # edge1 over the cpu limit, edge3 unreachable
    with pytest.raises(clu.ClusterError, match="over a capacity limit"):
        clu.place(servers, "prod", run=fake)


def test_options_cluster_targets_the_master(servers):
    clu.create_cluster(servers, "prod", "swarm", "edge1", lambda _l: None, run=FakeSSH())
    options = {"cluster": {"name": "prod", "replicas": 3}, "deploy": {"server": "edge2", "python": "bundle"}}
    assert srv.resolve_deploy(options, servers, "dev") == "edge1"
    assert options["cluster"] == {"name": "prod", "orchestrator": "swarm", "replicas": 3, "cpu": 0.25, "memory": 256}
    assert options["deploy"] == {"method": "docker", "host": "10.0.0.5", "user": "root", "port": 22, "server": "edge1",
                                 "python": "bundle", "auth": "agent"}
    for bad, message in (({"name": "nope"}, "no cluster 'nope'"), ({"name": "prod", "replicas": 0}, "replicas"),
                         ({"name": "prod", "size": 1}, "unknown options.cluster keys")):
        with pytest.raises(srv.ServerError, match=message):
            srv.resolve_deploy({"cluster": bad}, servers, "dev")


def test_render_writes_the_cluster_spec(make_project, tmp_path):
    for name, host in (("edge1", "10.0.0.5"), ("edge2", "10.0.0.6")):
        srv.save_server(tmp_path, name, {"host": host, "user": "root", "auth": "agent"})
    fake = FakeSSH()
    clu.create_cluster(tmp_path, "prod", "kubernetes", "edge1", lambda _l: None, run=fake)
    from py_serverless_kit.core.deployer import Deployer

    config = """
    service: shop
    provider:
      name: onprem
      runtime: python3.12
      options: {cluster: {name: prod, replicas: 4}, admin_token: tok}
    functions:
      hello: {handler: app.handlers.hello, events: [{http: {path: /hello, method: get}}]}
    """
    project = make_project(config)
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    app = project.work_dir / "onprem_app"
    spec = json.loads((app / "pskit_host.json").read_text("utf-8"))
    assert spec["deploy"]["method"] == "cluster" and spec["cluster"]["replicas"] == 4
    assert spec["host"] == "0.0.0.0" and spec["data_dir"] == "/var/pskit/data"
    assert spec["deploy"]["ssh"]["host"] == "10.0.0.5"  # logs / tests reach the host through the master
    assert (app / "Dockerfile").is_file()
    info = json.loads((app / clu.CLUSTER_SPEC).read_text("utf-8"))
    assert info["master"] == "edge1" and info["nodes"]["edge1"]["target"]["host"] == "10.0.0.5"
    digest_before = (app / "pskit_host.json").read_bytes()

    clu.join_server(tmp_path, "prod", "edge2", lambda _l: None, run=fake)
    project2 = make_project(config)
    Deployer(project2, echo=lambda _m: None).package(skip_deps=True)
    assert (app / "pskit_host.json").read_bytes() == digest_before  # joining a server does not redeploy
    assert set(json.loads((app / clu.CLUSTER_SPEC).read_text("utf-8"))["nodes"]) == {"edge1", "edge2"}


def test_deploy_builds_ships_applies_and_records(servers, tmp_path):
    fake = FakeSSH()
    clu.create_cluster(servers, "prod", "swarm", "edge1", lambda _l: None, run=fake)
    clu.join_server(servers, "prod", "edge2", lambda _l: None, run=fake)
    app = servers / ".pskit" / "onprem-dev" / "onprem_app"
    app.mkdir(parents=True)
    settings = {"name": "prod", "orchestrator": "swarm", "replicas": 3, "cpu": 0.25, "memory": 256}
    (app / clu.CLUSTER_SPEC).write_text(json.dumps(clu.cluster_file(servers, settings)), "utf-8")
    spec = {"service": "shop", "stage": "dev", "port": 8080, "endpoint": "http://10.0.0.5:8080"}

    def run(argv, stdout):
        if argv[:3] == ["docker", "image", "inspect"]:
            return 0, "sha256:0123456789abcdef\n"
        return fake(argv, stdout)

    lines: List[str] = []
    record = clu.deploy(app, spec, lines.append, run=run)
    assert record["image"] == "pskit-shop-dev:0123456789ab" and record["replicas"] == 3
    assert ["docker", "save", "-o"] == next(c for c in fake.calls if c[:2] == ["docker", "save"])[:3]
    loads = [s for s in fake.scripts if "gunzip | dk load" in s[1]]
    assert len(loads) == 2  # the master and the joined server
    applied = fake.script("dk stack deploy")
    assert "dk stack deploy --prune --resolve-image never -c pskit-cluster/pskit-shop-dev.json 'pskit-shop-dev'" in applied
    assert '"replicas": 3' in applied and "curl -fsS -m 3 http://127.0.0.1:8080/__pskit/health" in applied
    dep = clu.get_cluster(servers, "prod")["deployments"]["pskit-shop-dev"]
    assert dep["endpoint"] == "http://10.0.0.5:8080" and dep["image"] == record["image"]

    clu.scale(servers, "prod", "pskit-shop-dev", 6, lines.append, run=fake)
    assert "dk service scale --detach 'pskit-shop-dev_web'=6" in fake.script("service scale")
    clu.destroy(app, spec, lines.append, run=fake)
    assert "dk stack rm 'pskit-shop-dev'" in fake.script("stack rm")
    assert clu.get_cluster(servers, "prod").get("deployments") == {}


class FlakySCP(FakeSSH):
    """scp of image parts breaks ``breaks[host]`` times per host; the server "keeps" every part that arrived."""

    def __init__(self, breaks: dict, have: Optional[dict] = None) -> None:
        super().__init__()
        self.breaks = dict(breaks)
        self.have = have or {}  # host -> {part name: sha256}
        self.sent: List[Tuple[str, str]] = []
        self.local: dict = {}

    def __call__(self, argv, stdout):
        if argv[0] == "scp" and ".parts/part-" in argv[-1]:
            host = argv[-1].split("@")[-1].split(":")[0]
            part = argv[-1].rsplit("/", 1)[-1]
            if self.breaks.get(host, 0) > 0:
                self.breaks[host] -= 1
                return 255, "scp: Couldn't send packet: Broken pipe"
            import hashlib
            self.have.setdefault(host, {})[part] = hashlib.sha256(Path(argv[-2]).read_bytes()).hexdigest()
            self.sent.append((host, part))
            return 0, ""
        if "sha256sum part-*" in argv[-1]:
            host = next(a.split("@")[-1] for a in argv if "@" in a)
            return 0, "".join(f"{sha}  {name}\n" for name, sha in sorted(self.have.get(host, {}).items()))
        return super().__call__(argv, stdout)


def _targets(root: Path, *names: str) -> dict:
    return {n: clu._target(root, n) for n in names}


def test_image_copy_resumes_after_broken_pipe(servers, tmp_path, monkeypatch):
    monkeypatch.setattr(clu, "RETRY_DELAY", 0)
    monkeypatch.setattr(clu, "CHUNK_BYTES", 1024)
    tar = tmp_path / "image.tar"
    tar.write_bytes(bytes(range(256)) * 64)  # ~16 KB, compresses to several 1 KB parts
    fake = FlakySCP({"10.0.0.5": 2})
    lines: List[str] = []
    assert clu.ship_image("swarm", "pskit-shop-dev:abc", _targets(servers, "edge1", "edge2"), lines.append, fake,
                          tar=tar, required=("edge1",)) == []
    sent = [p for h, p in fake.sent if h == "10.0.0.5"]
    assert len(sent) == len(set(sent))  # a part that arrived is never sent again
    assert any("copy interrupted" in m and "attempt 2 of" in m for m in lines)
    assert any("edge1: loaded pskit-shop-dev:abc" in m for m in lines)
    load = fake.script("gunzip | dk load")
    assert "sha256sum" in load and "pskit-cluster/pskit-shop-dev-abc.parts" in load

    # A later deploy finds the parts already on the server and sends nothing again.
    again = FlakySCP({}, have={h: dict(p) for h, p in fake.have.items()})
    clu.ship_image("swarm", "pskit-shop-dev:abc", _targets(servers, "edge1"), lines.append, again, tar=tar)
    assert again.sent == []


def test_image_copy_failure_on_a_worker_only_warns(servers, tmp_path, monkeypatch):
    monkeypatch.setattr(clu, "RETRY_DELAY", 0)
    tar = tmp_path / "image.tar"
    tar.write_bytes(b"x" * 5000)
    fake = FlakySCP({"10.0.0.6": 100})
    lines: List[str] = []
    failed = clu.ship_image("swarm", "img:1", _targets(servers, "edge1", "edge2"), lines.append, fake, tar=tar,
                            required=("edge1",))
    assert failed == ["edge2"]
    assert any("WARNING: edge2:" in m and "run the deploy again" in m for m in lines)

    with pytest.raises(clu.ServiceError, match="could not copy the image to edge1.*parts already copied are kept"):
        clu.ship_image("swarm", "img:1", _targets(servers, "edge1", "edge2"), lines.append,
                       FlakySCP({"10.0.0.5": 100}), tar=tar, required=("edge1",))


def test_image_loaded_but_load_step_failed_is_not_copied_again(servers, tmp_path, monkeypatch):
    monkeypatch.setattr(clu, "RETRY_DELAY", 0)
    tar = tmp_path / "image.tar"
    tar.write_bytes(b"x" * 5000)

    class LoadedThenFails(FlakySCP):
        def __call__(self, argv, stdout):
            if argv[-1].startswith("sh pskit-cluster/") and "load" in argv[-1]:
                self.has_image = True
                return 1, "Loaded image: img:1"
            return super().__call__(argv, stdout)

    fake = LoadedThenFails({})
    lines: List[str] = []
    assert clu.ship_image("swarm", "img:1", _targets(servers, "edge1"), lines.append, fake, tar=tar) == []
    assert any("edge1: loaded img:1" in m for m in lines) and not any("copy interrupted" in m for m in lines)


def test_pack_image_is_reproducible(tmp_path, monkeypatch):
    monkeypatch.setattr(clu, "CHUNK_BYTES", 4096)
    tar = tmp_path / "image.tar"
    tar.write_bytes(bytes(range(256)) * 400)
    first = clu._pack_image(tar, tmp_path / "a")
    second = clu._pack_image(tar, tmp_path / "b")
    assert [p[2] for p in first[0]] == [p[2] for p in second[0]] and first[1] == second[1]
    import gzip
    joined = b"".join(p[1].read_bytes() for p in first[0])
    assert gzip.decompress(joined) == tar.read_bytes() and len(joined) == first[2]


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh")
def test_image_load_script_checks_and_loads(tmp_path):
    import gzip
    import hashlib
    payload = gzip.compress(b"layers" * 100, mtime=0)
    parts = tmp_path / "img.parts"
    parts.mkdir()
    (parts / "part-00000").write_bytes(payload[:50])
    (parts / "part-00001").write_bytes(payload[50:])
    stale = tmp_path / "img-old.parts"
    stale.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    loaded = tmp_path / "loaded"
    (bin_dir / "docker").write_bytes(f'#!/bin/sh\n[ "$1" = load ] && cat > "{loaded.as_posix()}"\nexit 0\n'.encode())
    (bin_dir / "docker").chmod(0o755)
    (bin_dir / "curl").write_bytes(b"#!/bin/sh\nexit 0\n")
    (bin_dir / "curl").chmod(0o755)
    env ={"PATH": f"{bin_dir.as_posix()}:/usr/bin:/bin", "HOME": tmp_path.as_posix()}

    def run(sha: str) -> int:
        script = tmp_path / "load.sh"
        script.write_bytes(scripts.image_load_script("swarm", parts.as_posix(), sha,
                                                     f"{tmp_path.as_posix()}/img-*.parts").encode())
        return subprocess.run([shutil.which("sh"), script.as_posix()], env=env, capture_output=True).returncode

    assert run("0" * 64) == 1 and not parts.exists()  # damaged copy: deleted, so it is sent again
    parts.mkdir()
    (parts / "part-00000").write_bytes(payload[:50])
    (parts / "part-00001").write_bytes(payload[50:])
    assert run(hashlib.sha256(payload).hexdigest()) == 0
    assert loaded.read_bytes() == b"layers" * 100 and not parts.exists() and not stale.exists()
    parts.mkdir()  # no older copy left to remove: the load still succeeds
    (parts / "part-00000").write_bytes(payload[:50])
    (parts / "part-00001").write_bytes(payload[50:])
    assert run(hashlib.sha256(payload).hexdigest()) == 0


def test_nomad_scale_re_registers_the_job(servers):
    fake = FakeSSH()
    clu.create_cluster(servers, "lab", "nomad", "edge1", lambda _l: None, run=fake)
    job = scripts.nomad_job("pskit-shop-dev", "img:1", port=8080, replicas=2, master_node="m", master_addr="10.0.0.5",
                            cpu=0.25, memory_mb=256)["Job"]
    clu._update(servers, "lab", lambda c: c.__setitem__("deployments", {"pskit-shop-dev": {"replicas": 2}}))

    def run(argv, stdout):
        if argv[-1] == "curl -fsS http://127.0.0.1:4646/v1/job/pskit-shop-dev":
            return 0, json.dumps(job)
        return fake(argv, stdout)

    clu.scale(servers, "lab", "pskit-shop-dev", 6, lambda _l: None, run=run)
    text = fake.script("-scale.json")
    sent = json.loads(text.split("<<'PSKIT_MANIFEST'\n", 1)[1].split("\nPSKIT_MANIFEST", 1)[0])
    assert [(g["Name"], g["Count"]) for g in sent["Job"]["TaskGroups"]] == [("main", 1), ("web", 6)]
    assert "--data @pskit-cluster/pskit-shop-dev-scale.json http://127.0.0.1:4646/v1/jobs" in text
    _sh_ok(text)
    assert clu.get_cluster(servers, "lab")["deployments"]["pskit-shop-dev"]["replicas"] == 6


# ------------------------------------------------------------------------------------------- live requests
class FakeControl:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def request(self, method, path, body=None, query=None, timeout=None):
        self.calls.append((method, path, query))
        return {"items": [dict(i) for i in self.items], "next": 42}


def test_requests_feed_maps_nodes_to_servers(servers):
    fake = FakeSSH()
    clu.create_cluster(servers, "prod", "swarm", "edge1", lambda _l: None, run=fake)
    clu.join_server(servers, "prod", "edge2", lambda _l: None, run=fake)
    with pytest.raises(clu.ClusterError, match="nothing is deployed"):
        clu.requests_feed(servers, "prod")
    clu._update(servers, "prod", lambda c: c.setdefault("deployments", {}).__setitem__(
        "pskit-shop-dev", {"stage": "dev", "endpoint": "http://10.0.0.5:8080", "port": 8080}))
    control = FakeControl([
        {"seq": 1, "method": "GET", "path": "/hello", "replica": "node-10.0.0.6-1", "node": "node-10.0.0.6"},
        {"seq": 2, "event_type": "schedule", "replica": "main", "node": ""},
        {"seq": 3, "method": "GET", "path": "/hello", "replica": "x-1", "node": "node-10.0.0.6"},
    ])
    page = clu.requests_feed(servers, "prod", since=7, control=control)
    assert [i["server"] for i in page["items"]] == ["edge2", "edge1", "edge2"]
    assert page["servers"] == {"edge2": 2, "edge1": 1} and page["next"] == 42 and page["stack"] == "pskit-shop-dev"
    assert control.calls == [("GET", "/__pskit/requests", {"since": 7, "limit": 200})]
    balance = page["balance"]
    assert balance["mode"] == "mesh" and balance["spreads"] is True and balance["port"] == 8080
    by_server = {row["server"]: row for row in balance["servers"]}
    assert set(by_server) == {"edge1", "edge2"}  # every server, including one with no HTTP requests
    assert by_server["edge2"]["requests"] == 2 and by_server["edge2"]["share"] == 100.0
    assert by_server["edge1"]["requests"] == 0 and by_server["edge1"]["serves"] == "web"
    assert by_server["edge2"]["url"] == "http://10.0.0.6:8080"
    with pytest.raises(clu.ClusterError, match="not deployed"):
        clu.requests_feed(servers, "prod", "other", control=control)


def test_nomad_balance_lists_every_server_and_its_url(servers):
    fake = FakeSSH()
    clu.create_cluster(servers, "prod", "nomad", "edge1", lambda _l: None, run=fake)
    clu.join_server(servers, "prod", "edge2", lambda _l: None, run=fake)
    clu.join_server(servers, "prod", "edge3", lambda _l: None, run=fake)
    clu._update(servers, "prod", lambda c: c.setdefault("deployments", {}).__setitem__(
        "pskit-shop-dev", {"stage": "dev", "endpoint": "http://10.0.0.5:8080", "port": 8080}))
    control = FakeControl([
        {"seq": 1, "method": "GET", "path": "/hello", "replica": "node-10.0.0.6-1", "node": "node-10.0.0.6"},
        {"seq": 2, "event_type": "schedule", "replica": "main", "node": ""},
    ])
    page = clu.requests_feed(servers, "prod", control=control)
    balance = page["balance"]
    assert balance["mode"] == "per-server" and balance["spreads"] is False
    by_server = {row["server"]: row for row in balance["servers"]}
    assert [row["server"] for row in balance["servers"]] == ["edge1", "edge2", "edge3"]
    assert by_server["edge1"]["serves"] == "main" and by_server["edge1"]["url"] == "http://10.0.0.5:8080"
    assert by_server["edge2"]["serves"] == "web" and by_server["edge2"]["requests"] == 1
    assert by_server["edge3"]["requests"] == 0 and by_server["edge3"]["url"] == "http://10.0.0.7:8080"
    assert by_server["edge1"]["requests"] == 0  # the schedule is not an HTTP request


def test_nomad_logs_feed_merges_every_server(servers):
    fake = FakeSSH()
    clu.create_cluster(servers, "prod", "nomad", "edge1", lambda _l: None, run=fake)
    clu.join_server(servers, "prod", "edge2", lambda _l: None, run=fake)
    clu.join_server(servers, "prod", "edge3", lambda _l: None, run=fake)
    pages = {
        "edge1": {"entries": [
            {"seq": 1, "ts": "2026-10-24T12:00:00.000+00:00", "message": "main up", "level": "INFO",
             "fields": {"replica": "main"}},
            {"seq": 2, "ts": "2026-10-24T12:00:01.000+00:00", "message": "shipped hello", "level": "INFO",
             "fields": {"replica": "node-b-1"}},
            {"seq": 3, "ts": "2026-10-24T12:00:03.000+00:00", "message": "kept from a quiet server", "level": "INFO",
             "fields": {"replica": "node-c-1"}},
        ]},
        "edge2": {"entries": [
            {"seq": 5, "ts": "2026-10-24T12:00:01.000+00:00", "message": "shipped hello", "level": "INFO",
             "fields": {"replica": "node-b-1"}},
            {"seq": 6, "ts": "2026-10-24T12:00:02.000+00:00", "message": "web only", "level": "INFO", "fields": {}},
        ]},
        "edge3": {"error": "no answer"},
    }
    page = clu.logs_feed(servers, "prod", ["edge1", "edge2", "edge3"], master="edge1", port=8080,
                         read=lambda server: pages[server])
    assert [entry["message"] for entry in page["entries"]] == ["main up", "shipped hello", "web only",
                                                               "kept from a quiet server"]
    hello = next(entry for entry in page["entries"] if entry["message"] == "shipped hello")
    assert hello["fields"]["server"] == "edge2"  # the web replica's own line, not the copy on main
    assert page["partial"] == ["edge3: no answer"]
    assert clu.logs_feed(servers, "prod", ["edge1", "edge2", "edge3"], master="edge1", port=8080, since=page["next"],
                         read=lambda server: pages[server])["entries"] == []
    with pytest.raises(clu.ClusterError, match="no replica on cluster prod"):
        clu.logs_feed(servers, "prod", ["edge2"], master="edge1", port=8080, read=lambda _s: {"error": "down"})


def test_nomad_log_backend_reads_every_server(servers, monkeypatch):
    from py_serverless_kit.core.cloud_logs import OnPremLogs
    from py_serverless_kit.core.onprem_control import HostControl

    fake = FakeSSH()
    clu.create_cluster(servers, "prod", "nomad", "edge1", lambda _l: None, run=fake)
    work = servers / ".pskit" / "onprem-dev"
    work.mkdir(parents=True)
    deployed = work / "onprem_deployed.json"
    deployed.write_text(json.dumps({
        "server": "edge1", "cluster": "prod",
        "spec": {"port": 8080, "admin_token": "tok", "deploy": {"method": "cluster", "ssh": {"host": "10.0.0.5", "user": "root"}}},
    }), "utf-8")
    seen: dict = {}

    def fake_feed(_root, name, members, **kw):
        seen["name"] = name
        seen["servers"] = list(members)
        seen["port"] = kw["port"]
        seen["token"] = kw["token"]
        return {"entries": [{"seq": 4, "message": "from web", "level": "INFO"}], "next": 4}

    monkeypatch.setattr(clu, "logs_feed", fake_feed)
    record = {"provider": "onprem", "stage": "dev"}
    control = HostControl("http://10.0.0.5:8080", token="tok", ssh={"host": "10.0.0.5", "user": "root"}, server="edge1")
    page = OnPremLogs(record, control, servers).query(since=3, limit=10)
    assert page["supported"] is True and page["entries"][0]["message"] == "from web"
    assert seen == {"name": "prod", "servers": ["edge1"], "port": 8080, "token": "tok"}

    clu.join_server(servers, "prod", "edge2", lambda _l: None, run=fake)
    control.server = "edge2"  # the server picker asked for one worker
    OnPremLogs(record, control, servers).query()
    assert seen["servers"] == ["edge2"]

    clu.create_cluster(servers, "mesh", "swarm", "edge3", lambda _l: None, run=fake)
    deployed.write_text(json.dumps({"server": "edge3", "cluster": "mesh", "spec": {"port": 9090, "admin_token": "tok",
                           "deploy": {"method": "cluster"}}}), "utf-8")

    class One:
        ssh = {"host": "10.0.0.7"}
        server = "edge3"

        def logs(self, **_kw):
            return {"entries": [{"seq": 1, "message": "mesh"}], "next": 1}

    assert OnPremLogs(record, One(), servers).query()["entries"][0]["message"] == "mesh"


def test_manifests_tell_replicas_their_node():
    swarm = scripts.swarm_stack("s", "i", port=8080, replicas=2, master_node="m", cpu=0.25, memory_mb=256)
    assert swarm["services"]["web"]["environment"]["PSKIT_NODE"] == "{{.Node.Hostname}}"
    k8s = scripts.kubernetes_manifest("s", "i", port=8080, replicas=2, master_node="m", cpu=0.25, memory_mb=256)
    envs = [c["env"] for d in k8s["items"] if d["kind"] == "Deployment" for c in d["spec"]["template"]["spec"]["containers"]]
    assert all({"name": "PSKIT_NODE", "valueFrom": {"fieldRef": {"fieldPath": "spec.nodeName"}}} in e for e in envs)
    nomad = scripts.nomad_job("s", "i", port=8080, replicas=2, master_node="m", master_addr="10.0.0.5", cpu=0.25,
                              memory_mb=256)
    assert all(g["Tasks"][0]["Env"]["PSKIT_NODE"] == "${node.unique.name}" for g in nomad["Job"]["TaskGroups"])


# ------------------------------------------------------------------------------------------- server settings
def test_server_home_bind_and_data_dir(tmp_path):
    from py_serverless_kit.core import onprem_services as svc

    srv.save_server(tmp_path, "box", {"host": "10.0.0.9", "user": "root", "auth": "agent", "home": "/srv/pskit/",
                                       "bind": "10.0.0.9", "data_dir": "/data/pskit"})
    item = srv.get_server(tmp_path, "box")
    assert (item["home"], item["bind"], item["data_dir"]) == ("/srv/pskit", "10.0.0.9", "/data/pskit")
    for bad, message in (({"home": "relative/x"}, "absolute"), ({"data_dir": "/a/../etc"}, "absolute"),
                         ({"bind": "eth0"}, "IPv4")):
        with pytest.raises(srv.ServerError, match=message):
            srv.save_server(tmp_path, "bad", {"host": "10.0.0.9", "auth": "agent", **bad})

    # functions: the server's defaults unless pskit.yml says otherwise
    options: dict = {"host": "127.0.0.1", "deploy": {"server": "box"}}
    srv.apply_to_deploy(options, tmp_path)
    assert options["host"] == "10.0.0.9" and options["data_dir"] == "/data/pskit"
    assert options["deploy"]["home"] == "/srv/pskit"
    from py_serverless_kit.providers.onprem_spec import parse_deploy

    spec = parse_deploy({"deploy": {**options["deploy"], "python": "system"}}, service="shop", stage="dev",
                        runtime="python3.12", architecture="x86_64")
    assert spec.remote_path == "/srv/pskit/shop-dev"
    options = {"host": "0.0.0.0", "data_dir": "/mine", "deploy": {"server": "box", "path": "/opt/app"}}
    srv.apply_to_deploy(options, tmp_path)
    assert options["host"] == "0.0.0.0" and options["data_dir"] == "/mine" and "home" not in options["deploy"]

    # services: published on the bind address, data in <data_dir>/<container>
    req = svc.check_request({"key": "cache", "service": "redis", "target": {"server": "box"}}, tmp_path, None)
    assert req["bind"] == "10.0.0.9" and req["volume"] == "/data/pskit/pskit-cache"
    argv = svc.run_args(req, "secret")
    assert "/data/pskit/pskit-cache:/data" in argv and "10.0.0.9:6379:6379" in argv
    calls = []
    sh = svc._Runner(lambda _l: None, lambda argv, _out: (calls.append(argv[-1]), (0, ""))[1])
    svc._make_volume(req["target"], sh, req["volume"])
    svc._drop_volume(req["target"], sh, req["volume"])
    assert "mkdir -p '/data/pskit/pskit-cache'" in calls[0] and "rm -rf '/data/pskit/pskit-cache'" in calls[1]


def test_cluster_uses_home_bind_and_data_dir(tmp_path):
    srv.save_server(tmp_path, "m1", {"host": "10.0.0.5", "user": "root", "auth": "agent", "home": "/srv/pskit",
                                      "bind": "192.168.1.5", "data_dir": "/data/pskit"})
    fake = FakeSSH()
    item = clu.create_cluster(tmp_path, "prod", "swarm", "m1", lambda _l: None, run=fake)
    assert item["advertise"] == "192.168.1.5"  # a specific bind address is the cluster address
    commands = [c[-1] for c in fake.calls if c[0] not in ("scp", "sshpass")]
    assert any(c.startswith("mkdir -p /srv/pskit/pskit-cluster") for c in commands)
    assert "cd /srv/pskit && sh pskit-cluster/master.sh" in commands
    assert any(c[-1].endswith(":/srv/pskit/pskit-cluster/master.sh") for c in fake.calls if c[0] == "scp")

    stack = scripts.swarm_stack("s", "i", port=8080, replicas=2, master_node="m", cpu=0.25, memory_mb=256,
                                data_root="/data/pskit")
    assert stack["services"]["main"]["volumes"] == ["/data/pskit/s:/var/pskit/data"] and "volumes" not in stack
    nomad = scripts.nomad_job("s", "i", port=8080, replicas=1, master_node="m", master_addr="a", cpu=0.25,
                              memory_mb=256, data_root="/data/pskit")
    assert nomad["Job"]["TaskGroups"][0]["Tasks"][0]["Config"]["volumes"] == ["/data/pskit/s:/var/pskit/data"]
    apply = scripts.apply_script("swarm", "s", stack, 8080, data_path="/data/pskit/s")
    assert "as_root mkdir -p '/data/pskit/s'" in apply
    _sh_ok(apply)


# ------------------------------------------------------------------------------------------- load balancer
def _lb_run(fake: FakeSSH, ok: str = "80"):
    """FakeSSH plus a load balancer that starts, and a built image with a fixed id."""

    def run(argv, stdout):
        if argv[-1] == "sh pskit-cluster/balancer.sh":
            fake.calls.append(argv)
            return 0, f"pulled\nPSKIT_LB_OK={ok}\nPSKIT_LB_DONE=1\n"
        if argv[:3] == ["docker", "image", "inspect"]:
            return 0, "sha256:0123456789abcdef\n"
        return fake(argv, stdout)

    return run


def _lb_scripts(fake: FakeSSH) -> List[str]:
    return [text for host, text in fake.scripts if host == "10.0.0.9" and "nginx -t" in text]


def _deploy(servers: Path, run, lines: List[str], **settings) -> dict:
    app = servers / ".pskit" / "onprem-dev" / "onprem_app"
    app.mkdir(parents=True, exist_ok=True)
    body = {"name": "prod", "orchestrator": "nomad", "replicas": 2, "cpu": 0.25, "memory": 256, **settings}
    (app / clu.CLUSTER_SPEC).write_text(json.dumps(clu.cluster_file(servers, body)), "utf-8")
    spec = {"service": "shop", "stage": "dev", "port": 8080, "endpoint": "http://10.0.0.5:8080"}
    return clu.deploy(app, spec, lines.append, run=run)


def test_balancer_conf_and_scripts():
    backends = [lb.backend("10.0.0.6", 8080, server="edge2"), lb.backend("10.0.0.7", 8080, server="edge3"),
                lb.backend("10.0.0.5", 8080, backup=True, server="edge1")]
    conf = lb.port_route_conf("port-80", 80, "least_connections", backends, comment="pskit-shop-dev")
    assert "upstream pskit_port_80 {" in conf and "listen 80;" in conf and "# pskit-shop-dev" in conf
    assert "server 10.0.0.6:8080 max_fails=3 fail_timeout=10s;" in conf
    assert "server 10.0.0.5:8080 backup;" in conf and "least_conn;" in conf and "zone pskit_port_80 64k;" in conf
    assert "proxy_pass http://pskit_port_80;" in conf
    assert "server [fd00::6]:8080" in lb.upstream_conf("k", "round_robin", [lb.backend("fd00::6", 8080)])
    with pytest.raises(ValueError):
        lb.backend("10.0.0.6; evil", 8080)
    files = {**lb.base_files("", 80, "least_connections"), "conf.d/r-port-80.conf": conf}
    apply = lb.apply_script("", files, replace_routes=True, checks={"80": "http://127.0.0.1:80/__pskit/health"})
    assert "nginx -t" in apply and "nginx -s reload" in apply and "--network host" in apply
    assert '-v "$lb/conf.d:/etc/nginx/conf.d:ro" -v "$lb/pskit-lua:/etc/nginx/pskit-lua:ro"' in apply
    assert lb.LB_IMAGE in apply and 'rm -f "$next"/conf.d/*.conf' in apply
    assert "PSKIT_LB_OK=80" in apply and apply.endswith("echo PSKIT_LB_DONE=1\n")
    with pytest.raises(ValueError):
        lb.apply_script("", {"../etc/passwd": "x"})
    for text in (apply, lb.apply_script("", {}), lb.remove_script(""), lb.logs_script("", 50)):
        assert text.startswith("#!/bin/sh\nset -eu\n")
        _sh_ok(text)


def test_balancer_follows_deploy_join_leave_and_remove(servers):
    srv.save_server(servers, "lb1", {"host": "10.0.0.9", "user": "root", "auth": "agent"})
    fake = FakeSSH()
    run = _lb_run(fake)
    lines: List[str] = []
    clu.create_cluster(servers, "prod", "nomad", "edge1", lines.append, run=run)
    clu.join_server(servers, "prod", "edge2", lines.append, run=run)
    item = clu.set_balancer(servers, "prod", "lb1", lines.append, run=run)
    assert item["balancer"]["server"] == "lb1" and item["balancer"]["port"] == 80
    assert "upstream pskit_" not in _lb_scripts(fake)[-1]  # nothing deployed yet

    record = _deploy(servers, run, lines)
    assert record["url"] == "http://10.0.0.9" and record["endpoint"] == "http://10.0.0.5:8080"
    conf = _lb_scripts(fake)[-1]
    assert "server 10.0.0.6:8080 max_fails=3" in conf and "server 10.0.0.5:8080 backup;" in conf
    assert any("Public URL (load balancer on lb1): http://10.0.0.9" in line for line in lines)
    assert not any("Nomad does not load-balance" in line for line in lines)
    assert clu.list_clusters(servers)[0]["balancer"]["urls"] == {"pskit-shop-dev": "http://10.0.0.9"}

    clu.join_server(servers, "prod", "edge3", lines.append, run=run)
    assert "server 10.0.0.7:8080 max_fails=3" in _lb_scripts(fake)[-1]

    clu.leave_server(servers, "prod", "edge3", lines.append, run=run)
    texts = [text for _host, text in fake.scripts]
    last_lb = max(i for i, t in enumerate(texts) if "nginx -t" in t)
    drain = max(i for i, t in enumerate(texts) if "/drain" in t)
    assert last_lb < drain  # off the load balancer before its replicas move
    assert "10.0.0.7" not in texts[last_lb]

    app = servers / ".pskit" / "onprem-dev" / "onprem_app"
    clu.destroy(app, {"service": "shop", "stage": "dev"}, lines.append, run=run)
    texts = [text for _host, text in fake.scripts]
    last_lb = max(i for i, t in enumerate(texts) if "nginx -t" in t)
    assert "pskit-shop-dev.conf" not in texts[last_lb]
    assert last_lb < max(i for i, t in enumerate(texts) if "v1/job/pskit-shop-dev?purge=true" in t)

    clu.remove_balancer(servers, "prod", lines.append, run=run)
    assert any(host == "10.0.0.9" and "dk rm -f pskit-lb" in text for host, text in fake.scripts)
    assert clu.get_cluster(servers, "prod").get("balancer") is None
    with pytest.raises(clu.ClusterError, match="no load balancer"):
        clu.remove_balancer(servers, "prod", lines.append, run=run)


def test_swarm_balancer_spreads_over_every_server(servers):
    srv.save_server(servers, "lb1", {"host": "10.0.0.9", "user": "root", "auth": "agent"})
    fake = FakeSSH()
    run = _lb_run(fake)
    clu.create_cluster(servers, "mesh", "swarm", "edge1", lambda _l: None, run=run)
    clu.join_server(servers, "mesh", "edge2", lambda _l: None, run=run)
    clu._update(servers, "mesh", lambda c: c.setdefault("deployments", {}).__setitem__(
        "pskit-shop-dev", {"stage": "dev", "endpoint": "http://10.0.0.5:8080", "port": 8080}))
    clu.set_balancer(servers, "mesh", "lb1", lambda _l: None, port=8000, run=run)
    conf = _lb_scripts(fake)[-1]
    assert "listen 8000;" in conf and "backup;" not in conf
    assert "server 10.0.0.5:8080 max_fails=3" in conf and "server 10.0.0.6:8080 max_fails=3" in conf
    page = clu.requests_feed(servers, "mesh", control=FakeControl([]))
    assert page["balance"]["mode"] == "balancer" and page["balance"]["balancer_url"] == "http://10.0.0.9:8000"
    assert {row["balancer"] for row in page["balance"]["servers"]} == {"primary"}


def test_master_serves_switch(servers):
    srv.save_server(servers, "lb1", {"host": "10.0.0.9", "user": "root", "auth": "agent"})
    fake = FakeSSH()
    run = _lb_run(fake)
    lines: List[str] = []
    item = clu.create_cluster(servers, "prod", "nomad", "edge1", lines.append, serve_on_master=True, run=run)
    assert item["master_serves"] is True and clu.get_cluster(servers, "prod")["master_serves"] is True
    assert any("serves requests too" in line for line in lines)
    clu.join_server(servers, "prod", "edge2", lines.append, run=run)
    clu.set_balancer(servers, "prod", "lb1", lines.append, run=run)
    _deploy(servers, run, lines)
    conf = _lb_scripts(fake)[-1]
    assert "server 10.0.0.5:8080 max_fails=3" in conf and "server 10.0.0.6:8080 max_fails=3" in conf
    assert "backup;" not in conf

    item = clu.set_master_serves(servers, "prod", False, lines.append, run=run)
    assert item["master_serves"] is False
    assert "server 10.0.0.5:8080 backup;" in _lb_scripts(fake)[-1]
    balance = clu.requests_feed(servers, "prod", control=FakeControl([]))["balance"]
    assert {r["server"]: r["balancer"] for r in balance["servers"]} == {"edge1": "backup", "edge2": "primary"}


def test_master_serves_defaults_and_web_placement(servers):
    run = FakeSSH()
    assert clu.create_cluster(servers, "n", "nomad", "edge1", lambda _l: None, run=run)["master_serves"] is False
    assert clu.create_cluster(servers, "s", "swarm", "edge2", lambda _l: None, run=run)["master_serves"] is True
    k = clu.create_cluster(servers, "k", "kubernetes", "edge3", lambda _l: None, serve_on_master=False, run=run)
    assert k["master_serves"] is False
    # Saved before the setting existed: the old behaviour (Nomad: backup only; Swarm / k3s: serves).
    assert clu.master_serves({"orchestrator": "nomad"}) is False and clu.master_serves({"orchestrator": "swarm"})
    one = {"orchestrator": "swarm", "master": "m", "master_serves": False, "nodes": {"m": {"address": "10.0.0.5"}}}
    assert clu._backends(one) == (["m"], [])  # nobody else to send requests to
    two = {**one, "nodes": {**one["nodes"], "w": {"address": "10.0.0.6"}}}
    assert clu._backends(two) == (["w"], ["m"])

    web = scripts.swarm_stack("s", "i", port=8080, replicas=2, master_node="m", cpu=0.25, memory_mb=256,
                              avoid_master=True)["services"]["web"]
    assert web["deploy"]["placement"] == {"constraints": ["node.hostname != m"]}
    assert "placement" not in scripts.swarm_stack("s", "i", port=8080, replicas=2, master_node="m", cpu=0.25,
                                                  memory_mb=256)["services"]["web"]["deploy"]
    k8s = scripts.kubernetes_manifest("s", "i", port=8080, replicas=2, master_node="m", cpu=0.25, memory_mb=256,
                                      avoid_master=True)
    terms = k8s["items"][3]["spec"]["template"]["spec"]["affinity"]["nodeAffinity"][
        "requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
    assert terms == [{"matchExpressions": [{"key": "kubernetes.io/hostname", "operator": "NotIn", "values": ["m"]}]}]
    assert "affinity" not in k8s["items"][1]["spec"]["template"]["spec"]



def test_kubernetes_requests_spread_over_every_server_behind_the_load_balancer():
    from py_serverless_kit.core import onprem_balancers as balancers

    # Web pods: one per server first (the scheduler's default would let two share a server); main is pinned.
    k8s = scripts.kubernetes_manifest("s", "i", port=8080, replicas=2, master_node="m", cpu=0.25, memory_mb=256)
    spread = k8s["items"][3]["spec"]["template"]["spec"]["topologySpreadConstraints"]
    assert spread == [{"maxSkew": 1, "topologyKey": "kubernetes.io/hostname", "whenUnsatisfiable": "ScheduleAnyway",
                       "labelSelector": {"matchLabels": {"app": "s", "role": "web"}}}]
    assert "topologySpreadConstraints" not in k8s["items"][1]["spec"]["template"]["spec"]

    # Kubernetes nodes pick a pod per connection: no reused upstream connections, or every request sticks to one.
    nodes = {"m": {"address": "10.0.0.5"}, "w": {"address": "10.0.0.6"}}
    kube = {"orchestrator": "kubernetes", "master": "m", "nodes": nodes, "master_serves": True}
    swarm = {**kube, "orchestrator": "swarm"}
    found = balancers.cluster_backends(kube, 8080)
    assert [b["server"] for b in found] == ["m", "w"] and all(b["per_request"] for b in found)
    assert not any(b.get("per_request") for b in balancers.cluster_backends(swarm, 8080))
    route = balancers.make_route("pskit-shop-dev", found, path="shop")
    assert all(b["per_request"] for b in route["backends"])
    for algorithm in ("round_robin", "least_connections", "least_time", "ip_hash"):
        conf = lb.upstream_conf("shop", algorithm, route["backends"])
        assert "keepalive" not in conf.replace("no keepalive", "") and "10.0.0.6" in conf, algorithm
    plain = [lb.backend("10.0.0.7", 8080, server="s1")]
    assert "keepalive 32;" in lb.upstream_conf("shop", "round_robin", plain) and "per_request" not in plain[0]

def test_balancer_refuses_members_and_shared_ports(servers):
    srv.save_server(servers, "lb1", {"host": "10.0.0.9", "user": "root", "auth": "agent"})
    fake = FakeSSH()
    run = _lb_run(fake)
    clu.create_cluster(servers, "prod", "nomad", "edge1", lambda _l: None, run=run)
    with pytest.raises(clu.ClusterError, match="outside the cluster"):
        clu.set_balancer(servers, "prod", "edge1", lambda _l: None, run=run)
    clu.set_balancer(servers, "prod", "lb1", lambda _l: None, run=run)
    with pytest.raises(clu.ClusterError, match="load balancer of cluster 'prod'"):
        clu.join_server(servers, "prod", "lb1", lambda _l: None, run=run)
    with pytest.raises(clu.ClusterError, match="load balancer of cluster 'prod'"):
        clu.create_cluster(servers, "other", "swarm", "lb1", lambda _l: None, run=run)

    clu._update(servers, "prod", lambda c: c.setdefault("deployments", {}).__setitem__(
        "pskit-api-dev", {"stage": "dev", "port": 9000}))
    with pytest.raises(clu.ClusterError, match="balancer_port: 8081"):
        _deploy(servers, run, [])
    record = _deploy(servers, run, [], balancer_port=8081)
    assert record["url"] == "http://10.0.0.9:8081"
    assert clu.get_cluster(servers, "prod")["deployments"]["pskit-shop-dev"]["balancer_port"] == 8081
    conf = _lb_scripts(fake)[-1]
    assert "listen 80;" in conf and "listen 8081;" in conf

    options = {"cluster": {"name": "prod", "balancer_port": 8081}}
    assert clu.deploy_spec(servers, options)["balancer_port"] == 8081
    with pytest.raises(clu.ClusterError, match="balancer_port"):
        clu.deploy_spec(servers, {"cluster": {"name": "prod", "balancer_port": 0}})


def test_unreachable_balancer_only_warns_and_status_shows_it(servers):
    srv.save_server(servers, "lb1", {"host": "10.0.0.9", "user": "root", "auth": "agent"})
    fake = FakeSSH({"10.0.0.5": (STAT_B, 2000000)})
    clu.create_cluster(servers, "prod", "nomad", "edge1", lambda _l: None, run=_lb_run(fake))
    clu.set_balancer(servers, "prod", "lb1", lambda _l: None, run=_lb_run(fake))

    def broken(argv, stdout):
        if argv[-1] == "sh pskit-cluster/balancer.sh":
            return 1, "pskit: nginx refused the new load balancer config; the running one is unchanged\n"
        return fake(argv, stdout)

    lines: List[str] = []
    assert clu.sync_balancer(servers, "prod", lines.append, run=broken) is False
    assert any("WARNING: could not update the load balancer" in line and "balancer sync prod" in line
               for line in lines)
    with pytest.raises(clu.ClusterError, match="nginx refused"):
        clu.sync_balancer(servers, "prod", lines.append, run=broken, strict=True)

    current = clu.status(servers, "prod", run=fake)
    assert current["balancer"]["server"] == "lb1" and current["balancer"]["reachable"] is False
    assert current["balancer"]["running"] is False
