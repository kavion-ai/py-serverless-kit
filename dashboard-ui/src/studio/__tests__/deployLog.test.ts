import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { afterStatus, DeployLogParser, doneStatus, hostStatus, parseDeployLog, stageStatus } from "../deployLog";

const BUILD = [
  "Packaging my-service for On-premises (dev)",
  "  collected 12 source file(s) from /work/my-service",
  "  2 requirement(s) from function sub-projects",
  "  artifact artifact.zip: 14 files, 22.1 KiB, sha256 0123456789ab",
  "  terraform: 3 resource(s) -> .pskit/onprem-dev/main.tf.json",
];

const PLAN = [
  "Running terraform init",
  "",
  "Initializing the backend...",
  "Initializing provider plugins...",
  "Terraform has been successfully initialized!",
  "Running terraform apply",
  "terraform_data.host: Refreshing state... [id=abc]",
  "",
  "Terraform used the selected providers to generate the following execution plan.",
  "Plan: 2 to add, 1 to change, 0 to destroy.",
];

const FAILED = [
  ...BUILD,
  ...PLAN,
  "terraform_data.host: Modifying... [id=abc]",
  "terraform_data.host_test_02: Creating...",
  "terraform_data.host_test_03: Creating...",
  "terraform_data.host_test_02 (local-exec): Executing: [\"/bin/sh\" \"-c\" \"ssh ...\"]",
  "terraform_data.host (local-exec): host started",
  "terraform_data.host_test_03: Still creating... [10s elapsed]",
  "terraform_data.host_test_02 (local-exec): on-prem host did not become healthy; see /home/azureuser/my-service-dev-test-02/host.log",
  "terraform_data.host_test_02 (local-exec):   | Traceback (most recent call last):",
  "terraform_data.host_test_02 (local-exec):   | PermissionError: [Errno 13] Permission denied: '/home/azureuser-test-02'",
  "terraform_data.host: Modifications complete after 4s [id=abc]",
  "terraform_data.host_test_03: Creation complete after 12s [id=def]",
  "",
  "Error: local-exec provisioner error",
  "",
  "  with terraform_data.host_test_02,",
  "  on main.tf.json line 59, in resource.terraform_data.host_test_02.provisioner[0].local-exec:",
  "  59:       }",
  "",
  "Error running command 'apply': exit status 1. Output: command failed (1): ssh -o BatchMode=yes azureuser@20.102.66.232 sh '/home/azureuser/my-service-dev-test-02/remote_apply.sh'",
  "",
  "\u001b[31mError: `apply -input=false` failed with exit code 1\u001b[0m",
];

const FIREWALL = [
  "Firewall - my-service (dev) (open these; docs/onprem-network.md):",
  "  VM_01_2cpu (10.0.0.4)",
  "    [REQUIRED] inbound  TCP 3000     from users  - the functions' HTTP endpoint",
  "    [optional] inbound  TCP 22       from this machine (10.0.0.1)  - SSH deploys",
  "    ufw on VM_01_2cpu:",
  "      sudo ufw allow 3000/tcp",
  "      sudo ufw allow from 10.0.0.1 to any port 22 proto tcp",
  "  VM_03_2cpu",
  "    [NEEDED  ] outbound TCP 3000     to VM_01_2cpu (10.0.0.4)  - calls between groups",
];

const SUCCESS = [
  ...BUILD,
  ...PLAN,
  "terraform_data.host: Creating...",
  "terraform_data.host_test_02: Creating...",
  "terraform_data.host: Still creating... [10s elapsed]",
  "terraform_data.host_test_02: Creation complete after 9s [id=x]",
  "terraform_data.host: Creation complete after 12s [id=y]",
  "",
  "Apply complete! Resources: 2 added, 0 changed, 0 destroyed.",
  "",
  "Outputs:",
  "",
  'pskit = {"endpoint" = "http://10.0.0.4:3000"}',
  "Load balancer edge:",
  "  http://10.0.0.9:8000/my-service/ -> my-service-dev: round robin",
  "  WARNING: http://10.0.0.9:8000/my-service/__pskit/health did not answer yet (my-service-dev).",
  "Firewall - load balancer edge -> my-service (open these; docs/onprem-network.md):",
  "  edge-host",
  "    [REQUIRED] outbound TCP 3000     to VM_01_2cpu  - the load balancer calls the functions",
  ...FIREWALL,
  "",
  "\u001b[32m",
  "Deployed my-service (dev) to On-premises VM_01_2cpu\u001b[0m",
  "endpoint: http://10.0.0.4:3000",
  "deployed on: VM_01_2cpu",
  "functions:",
  "  hello                    http          GET /hello",
  "      GET    http://10.0.0.4:3000/hello",
  "  get-item                 http          GET /items/{id}",
  "      GET    http://10.0.0.5:8080/items/{id}",
  "",
  "Dashboard: file:///work/my-service/.pskit/dashboard.html",
];

describe("deploy log parser", () => {
  test("splits the build and plan steps", () => {
    const log = parseDeployLog([...BUILD, ...PLAN]);
    assert.equal(log.stage, 1);
    assert.deepEqual(log.build, BUILD);
    assert.equal(log.planSummary, "Plan: 2 to add, 1 to change, 0 to destroy.");
    assert.ok(log.plan.includes("terraform_data.host: Refreshing state... [id=abc]"), "refreshing belongs to the plan");
    assert.equal(log.hosts.length, 0, "refreshing does not start a host");
    assert.equal(stageStatus(log, 0, "running"), "done");
    assert.equal(stageStatus(log, 1, "running"), "running");
  });

  test("gives each host only its own lines and finds the failed one", () => {
    const log = parseDeployLog(FAILED);
    assert.deepEqual(
      log.hosts.map((h) => h.key),
      ["host", "host_test_02", "host_test_03"],
    );
    const [main, two, three] = log.hosts;
    assert.equal(main.status, "done");
    assert.equal(main.action, "modify");
    assert.equal(main.detail, "Modifications complete after 4s");
    assert.ok(main.lines.every((l) => l.startsWith("terraform_data.host:") || l.startsWith("terraform_data.host (")));
    assert.equal(three.status, "done");
    assert.equal(three.lines.length, 3);

    assert.equal(two.status, "failed");
    assert.deepEqual(two.error, ["on-prem host did not become healthy; see /home/azureuser/my-service-dev-test-02/host.log"]);
    assert.deepEqual(two.tail, ["Traceback (most recent call last):", "PermissionError: [Errno 13] Permission denied: '/home/azureuser-test-02'"]);
    assert.equal(two.errorBlock[0], "Error: local-exec provisioner error");
    assert.ok(two.errorBlock.some((l) => l.includes("remote_apply.sh")));
    assert.ok(two.lines.every((l) => l.startsWith("terraform_data.host_test_02")));

    // pskit's own error names no host (ANSI stripped).
    assert.deepEqual(log.errors, [["Error: `apply -input=false` failed with exit code 1"]]);
    assert.equal(hostStatus(two, log, "failed"), "failed");
    assert.equal(hostStatus(main, log, "failed"), "done");
    assert.equal(hostStatus(undefined, log, "failed"), "waiting");
    assert.equal(doneStatus(log, "failed"), "waiting");
  });

  test("a running host is failed when the job fails, and live while it runs", () => {
    const lines = [...BUILD, ...PLAN, "terraform_data.host_gpu: Creating...", "terraform_data.host_gpu: Still creating... [20s elapsed]"];
    const log = parseDeployLog(lines);
    assert.equal(log.hosts[0].detail, "20s elapsed");
    assert.equal(hostStatus(log.hosts[0], log, "running"), "running");
    assert.equal(hostStatus(log.hosts[0], log, "failed"), "failed");
    assert.equal(hostStatus(log.hosts[0], log, "cancelled"), "cancelled");
    assert.equal(hostStatus(undefined, log, "running"), "waiting");
  });

  test("reads the steps after the apply", () => {
    const log = parseDeployLog(SUCCESS);
    assert.equal(log.stage, 4);
    assert.equal(log.applySummary, "Apply complete! Resources: 2 added, 0 changed, 0 destroyed.");
    assert.ok(log.apply.includes("Outputs:"));
    assert.deepEqual(log.balancer, [
      "Load balancer edge:",
      "  http://10.0.0.9:8000/my-service/ -> my-service-dev: round robin",
      "  WARNING: http://10.0.0.9:8000/my-service/__pskit/health did not answer yet (my-service-dev).",
    ]);
    assert.equal(log.balancerWarnings, 1);
    assert.deepEqual(
      log.firewall.map((s) => s.server),
      ["edge-host", "VM_01_2cpu (10.0.0.4)", "VM_03_2cpu"],
    );
    const vm1 = log.firewall[1].sections[0];
    assert.equal(vm1.title, "my-service (dev)");
    assert.deepEqual(
      vm1.rules.map((r) => [r.level, r.direction, r.port, r.peer, r.why]),
      [
        ["required", "inbound", "TCP 3000", "from users", "the functions' HTTP endpoint"],
        ["optional", "inbound", "TCP 22", "from this machine (10.0.0.1)", "SSH deploys"],
      ],
    );
    assert.deepEqual(vm1.ufw, ["sudo ufw allow 3000/tcp", "sudo ufw allow from 10.0.0.1 to any port 22 proto tcp"]);
    assert.equal(log.firewall[2].sections[0].rules[0].level, "feature");
    assert.equal(log.firewall[0].sections[0].title, "load balancer edge -> my-service");
    assert.deepEqual(log.endpoints, ["http://10.0.0.4:3000", "http://10.0.0.4:3000/hello", "http://10.0.0.5:8080/items/{id}"]);
    assert.ok(log.done.includes("Dashboard: file:///work/my-service/.pskit/dashboard.html"));
    assert.equal(log.errors.length, 0);
    assert.equal(afterStatus(log, "balancer", "succeeded"), "done");
    assert.equal(afterStatus(log, "firewall", "running"), "done");
    assert.equal(doneStatus(log, "succeeded"), "done");
    assert.equal(doneStatus(log, "running"), "running");
  });

  test("merges firewall blocks of one server", () => {
    const log = parseDeployLog([...BUILD, ...PLAN, "Apply complete! Resources: 0 added, 0 changed, 0 destroyed.", ...FIREWALL, ...FIREWALL]);
    assert.equal(log.firewall.length, 2);
    assert.equal(log.firewall[0].sections.length, 2);
  });

  test("remove: hosts are destroyed", () => {
    const log = parseDeployLog([
      "Initializing the backend...",
      "terraform_data.host_test_02: Destroying... [id=x]",
      "terraform_data.host: Destroying... [id=y]",
      "terraform_data.host_test_02: Destruction complete after 1s",
      "terraform_data.host: Destruction complete after 2s",
      "",
      "Destroy complete! Resources: 2 destroyed.",
      "  load balancer edge: removed /my-service",
      "\u001b[32mRemoved.\u001b[0m",
    ]);
    assert.deepEqual(
      log.hosts.map((h) => [h.key, h.action, h.status]),
      [
        ["host_test_02", "destroy", "done"],
        ["host", "destroy", "done"],
      ],
    );
    assert.equal(log.applySummary, "Destroy complete! Resources: 2 destroyed.");
    assert.deepEqual(log.balancer, ["  load balancer edge: removed /my-service"]);
    assert.equal(log.stage, 4);
  });

  test("a configuration error fails the build step", () => {
    const log = parseDeployLog(["  error: functions.hello.handler: not found", "Error: 1 configuration error(s); fix them and retry"]);
    assert.equal(log.stage, 0);
    assert.equal(stageStatus(log, 0, "failed"), "failed");
    assert.equal(stageStatus(log, 1, "failed"), "waiting");
    assert.deepEqual(log.errors, [["Error: 1 configuration error(s); fix them and retry"]]);
  });

  test("parses incrementally by seq and skips lines it has seen", () => {
    const p = new DeployLogParser();
    const all = FAILED.map((text, i) => ({ seq: i + 1, text }));
    p.push(all.slice(0, 20));
    p.push(all.slice(10, 30)); // overlapping poll
    p.push(all.slice(30));
    const whole = parseDeployLog(FAILED);
    const parts = p.snapshot();
    assert.equal(parts.lineCount, FAILED.length);
    assert.deepEqual(parts.hosts, whole.hosts);
    assert.deepEqual(parts.errors, whole.errors);
  });

  test("stays linear on a large output", () => {
    const lines: string[] = [...BUILD, ...PLAN];
    for (let i = 0; i < 20000; i++) lines.push(`terraform_data.host_g${i % 8} (local-exec): line ${i}`);
    const started = Date.now();
    const log = parseDeployLog(lines);
    assert.equal(log.hosts.length, 8);
    assert.equal(log.hosts[0].lines.length, 2500);
    assert.ok(Date.now() - started < 2000, "parses 20k lines quickly");
  });
});
