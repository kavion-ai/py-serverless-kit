"""Category A (docs Q&A and how-to), batch 14: workflows and executions on the on-prem host, the dashboard, and
studio pages asked from an on-prem project. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


WF = "docs/workflows.md"
WE = "docs/workflow-executions.md"
DB = "docs/dashboard.md"
ST = "docs/studio.md"

CONVERSATIONS = [
    A(261, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WF}#embedded-orchestrator"],
      user="On our on-prem host, workflow `order` starts with a task on function `validate-order`. When someone calls validate-order's own HTTP route, a workflow execution appears too. Is that a bug?",
      steps=[S("search_docs", query="workflow starts when first task function runs on premises",
               docs=[D(WF, "embedded-orchestrator", start="- On premises, a workflow whose first state is a `task`", end="Other clouds don't do this: start the workflow itself there.")])],
      final="""No, that's on purpose. On premises, a workflow whose first state is a `task` also starts when that function runs on its own: its HTTP route, `invoke()`, `pskit trigger`, a schedule, a queue and so on [docs/workflows.md#embedded-orchestrator].

- The call's input becomes the workflow input, and the function's result is the first state's result, so the function doesn't run twice.
- The function's own response doesn't change. The HTTP response carries the run's id in `x-pskit-execution-id`.
- A failed call (an exception, or HTTP status 400 or more) starts nothing.

To turn it off:
```yaml
workflows:
  order:
    start_at: Validate
    options: {start_on_entry: false}
    states:
      Validate: {type: task, function: validate-order, end: true}
```
Other clouds don't do this; there you start the workflow itself."""),

    A(262, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises", f"{WF}#embedded-orchestrator"],
      user="On AWS our Step Functions workflow waits 2 hours between two tasks. Does a wait that long work with the embedded engine on-prem, or does it hit the function timeout?",
      steps=[S("search_docs", query="embedded engine on premises wait function timeout",
               docs=[D("docs/providers.md", "onprem-on-premises", start="| workflows | embedded engine inside the host", end="| workflows | embedded engine inside the host")]),
             S("search_docs", query="embedded orchestrator whole run one invocation",
               docs=[D(WF, "embedded-orchestrator", start="- The **whole run must fit in one function invocation**", end="`pskit validate` warns about this.")])],
      final="""It works on-prem. There the embedded engine runs inside the host, so a workflow isn't cut off by a function timeout [docs/providers.md#onprem-on-premises].

The "whole run must fit in one function invocation" limit applies to the embedded orchestrator on **clouds** (900 s on AWS, 600 s on Azure, ...) [docs/workflows.md#embedded-orchestrator].

**In code**
```yaml
workflows:
  order:
    timeout: 10800
    start_at: Charge
    states:
      Charge: {type: task, function: charge, next: Pause}
      Pause: {type: wait, seconds: 7200, next: Ship}
      Ship: {type: task, function: ship, end: true}
```
Note: if the host restarts during the wait, the run is marked `ABORTED` and isn't resumed."""),

    A(263, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="pasted_error",
      sources=[f"{WE}#cancel-timeouts-and-restarts-embedded-engine"],
      user="019a15d27b5a2e414a2a2164c474  order-pipeline  ABORTED  cause: host restarted\n\nwe only redeployed. can it continue?",
      steps=[S("search_docs", query="execution aborted host restarted resumed",
               docs=[D(WE, "cancel-timeouts-and-restarts-embedded-engine", start="- **Restart:**", end="They are not resumed.")])],
      final="""No. A redeploy restarts the host. Runs the previous process left `RUNNING` are marked `ABORTED` (`cause: host restarted`), a host note is logged, and they are not resumed [docs/workflow-executions.md#cancel-timeouts-and-restarts-embedded-engine].

Start it again with the same input:
```bash
pskit workflow status 019a15d27b5a2e414a2a2164c474 --history
pskit workflow start order-pipeline -i @input.json
```
To avoid this, deploy when no long runs are active (`pskit workflow executions order-pipeline --status RUNNING`), and make the task functions safe to run twice."""),

    A(264, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WE}#cancel-timeouts-and-restarts-embedded-engine"],
      user="We started 30 workflow runs at once on the on-prem host. Many show RUNNING but with no current state. Are they stuck?",
      steps=[S("search_docs", query="workflow concurrency workers running no current state",
               docs=[D(WE, "cancel-timeouts-and-restarts-embedded-engine", start="- **Retention and concurrency:**")])],
      final="""No, they're waiting. The host runs up to 8 executions at a time (`provider.options.workflow_workers`). Further starts queue and show `RUNNING` with no `current_state` until a worker picks them up [docs/workflow-executions.md#cancel-timeouts-and-restarts-embedded-engine].

To run more at once:
```yaml
provider:
  name: onprem
  options:
    workflow_workers: 16
```
Then deploy again. Raise it only if the server and the systems your tasks call can take the load."""),

    A(265, provider="onprem", stage="staging", mode="auto", page="Workflows", persona="terse_expert",
      sources=[f"{WE}#cancel-timeouts-and-restarts-embedded-engine"],
      user="cancel a run whose task is mid-flight: does the task get killed?",
      steps=[S("search_docs", query="cancel execution running task",
               docs=[D(WE, "cancel-timeouts-and-restarts-embedded-engine", end="Cancelling a finished run returns it unchanged.")])],
      final="""No. Cancel stops the run before its **next** state, so a task that's already running finishes first. A `wait` state or a retry back-off wakes up at once. The response has `cancel_requested: true`, and the status becomes `CANCELLED` shortly after [docs/workflow-executions.md#cancel-timeouts-and-restarts-embedded-engine].

```bash
pskit workflow cancel <execution_id>
```"""),

    A(266, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=[f"{WE}#following-a-run"],
      user="terminal only: last 50 failed runs of order-pipeline, then the full history of one",
      steps=[S("search_docs", query="list failed executions history",
               docs=[D(WE, "following-a-run", start="pskit workflow executions", end="pskit workflow cancel <id>"),
                     D(WE, "following-a-run", start="Pages use `--offset` on premises", end="Pages use `--offset` on premises")])],
      final="""**In the terminal**
```bash
pskit workflow executions order-pipeline --status FAILED -n 50
pskit workflow status <id> --history
```
On premises the pages use `--offset` and give a total count [docs/workflow-executions.md#following-a-run]."""),

    A(267, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=[f"{WE}#cancel-timeouts-and-restarts-embedded-engine"],
      user="my workflow sometimes run forever. i want it stop after 10 minutes automatic",
      steps=[S("search_docs", query="workflow timeout timed out",
               docs=[D(WE, "cancel-timeouts-and-restarts-embedded-engine", start="- **Timeout:**", end="`TimeoutSeconds`.")])],
      final="""Set `timeout` (seconds) on the workflow. On premises the engine enforces it, and a run past it becomes `TIMED_OUT` [docs/workflow-executions.md#cancel-timeouts-and-restarts-embedded-engine].

**In code**
```yaml
workflows:
  order-pipeline:
    timeout: 600
```
Keep your `start_at` and `states` as they are.

**In studio**
Open **Workflows**, select the workflow, set *Timeout (s)* to 600 and click **Save**."""),

    A(268, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=[f"{WE}#cancel-timeouts-and-restarts-embedded-engine", "docs/providers.md#onprem-on-premises"],
      user="how many finished workflow executions does the on-prem host keep, and where?",
      steps=[S("search_docs", query="execution retention records data_dir",
               docs=[D(WE, "cancel-timeouts-and-restarts-embedded-engine", start="- **Restart:**")])],
      final="""The newest **500** (`provider.options.execution_retention`). Running ones are never pruned. Records live in `<data_dir>/executions/<id>.json` [docs/workflow-executions.md#cancel-timeouts-and-restarts-embedded-engine].

```yaml
provider:
  name: onprem
  options:
    execution_retention: 2000
```"""),

    A(269, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="beginner",
      sources=[f"{WE}#following-a-run", f"{DB}#live-mode"],
      user="is there a web page to see workflow runs instead of commands?",
      steps=[S("search_docs", query="dashboard executions tab",
               docs=[D(WE, "following-a-run", start="The dashboard's **Executions** tab"),
                     D(DB, "live-mode", end="serves the page at `/` plus this API.")])],
      final="""Yes, the dashboard's **Executions** tab: filters, pages, a start dialog and a live detail panel [docs/workflow-executions.md#following-a-run].

**In the terminal**
```bash
pskit dashboard --serve --open
```
It serves the page on `127.0.0.1:8765` [docs/dashboard.md#live-mode]. For on-prem deployments it talks to the host itself."""),

    A(270, provider="onprem", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=[f"{DB}#security"],
      user="Can I run `pskit dashboard --serve --host 0.0.0.0` on our ops box so the team opens it from their laptops? What's exposed?",
      steps=[S("search_docs", query="dashboard host 0.0.0.0 security",
               docs=[D(DB, "security")])],
      final="""You can, but pskit warns: anyone who can reach the port can read logs and start or cancel executions. There's no login. Put it behind your own authentication [docs/dashboard.md#security].

What stays protected:
- admin tokens and cloud credentials never reach the browser;
- a foreign `Host` header gets `421` (blocks DNS rebinding);
- `POST` needs `content-type: application/json` and a same-origin `Origin`.

```bash
pskit dashboard --serve --host 0.0.0.0 --port 8765
```
Safer: keep the default loopback bind and let each person reach it through an SSH tunnel."""),

    A(271, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=[f"{ST}#test-functions"],
      user="in the studio how do i send a real message to my deployed onprem worker and see what it logs?",
      steps=[S("search_docs", query="studio test page send deployed function logs",
               docs=[D(ST, "test-functions", end="Turn on *Show the function's logs* to watch it.")])],
      final="""**In studio**
1. Open **Test**.
2. *1. Choose the event*: pick `worker` and its queue trigger.
3. *2. Edit the event*: change the payload. It starts from a queue sample.
4. *3. Run it*: click **☁ Send to onprem / dev**. That sends a real queue message to the deployed host (`pskit trigger`).
5. Turn on *Show the function's logs* to watch it.

**▶ Run locally** instead runs the handler on this machine with a synthetic event, without the deployed host [docs/studio.md#test-functions]."""),

    A(272, provider="onprem", stage="dev", mode="auto", page="Test", persona="informal_non_native",
      sources=[f"{ST}#test-functions"],
      user="i always type same json for test. studio can remember it?",
      steps=[S("search_docs", query="studio save test event payload",
               docs=[D(ST, "test-functions", start="2. Edit the payload.", end="like test events in the Lambda console.")])],
      final="""Yes. On the **Test** page, click **Save event**. Named payloads are kept per function in `.pskit/studio/test-events.json`, like test events in the Lambda console [docs/studio.md#test-functions]."""),

    A(273, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=[f"{ST}#full-vs-code-code-server-in-docker"],
      user="the code editor in studio is small. can i get real vs code with python extension?",
      steps=[S("search_docs", query="studio full vs code code-server",
               docs=[D(ST, "full-vs-code-code-server-in-docker", end="The default is the project's own runtime.")])],
      final="""Yes: **Full VS Code**. It runs code-server in Docker on your project and embeds it in the studio [docs/studio.md#full-vs-code-code-server-in-docker].

**In studio**
1. Open **Code** and click **Full VS Code**.
2. Pick a Python (3.9 to 3.13) and/or Node.js version.
3. Click **Pull & start**. The first start builds an image with those runtimes and the Python extension.
4. Use **Open in new tab** for more room, and **Stop** when you're done. Your files stay in the project folder.

It needs Docker on your machine. It's published on `127.0.0.1` only."""),

    A(274, provider="onprem", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=[f"{ST}#security"],
      user="can the studio Code editor open .pskit/onprem-servers.json?",
      steps=[S("search_docs", query="studio file editor reach files pskit folder",
               docs=[D(ST, "security")])],
      final="""No. The file editor only reaches files inside the project and never touches `.pskit/`, `.git/`, `.venv/`, `node_modules/` or `__pycache__`. It also refuses binary files and files over 1 MiB [docs/studio.md#security].

Saved servers are managed in **Resources > On-prem services > Servers** instead, or with `pskit resources onprem servers list`."""),

    A(275, provider="onprem", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{ST}#saving-what-changes-in-pskityml"],
      user="Our pskit.yml has lots of comments explaining the on-prem options. If I edit and save in the studio, what happens to them, and can I get the old file back?",
      steps=[S("search_docs", query="studio save comments backup",
               docs=[D(ST, "saving-what-changes-in-pskityml")])],
      final="""Comments are **not** kept, and the key order follows the studio's layout. Before every save the previous file is copied to `.pskit/studio/backups/pskit.<timestamp>.yml`, and the last 20 are kept [docs/studio.md#saving-what-changes-in-pskityml].

Also good to know:
- `${env:...}`, `${self:...}` and `${opt:...}` are saved as written, never resolved.
- If the file changed on disk since you loaded it, **Save** offers to reload, overwrite or cancel.

If the comments matter, keep editing those parts by hand, or move the explanations into a README."""),

    A(276, provider="onprem", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=[f"{ST}#browse-account"],
      user="Browse account in the trigger picker on onprem — what does it list, needs creds?",
      steps=[S("search_docs", query="browse account on premises",
               docs=[D(ST, "browse-account")])],
      final="""On premises it lists the existing queue and bucket directories under the host's data directory, and needs nothing [docs/studio.md#browse-account]. You can always type the name instead."""),

    A(277, provider="onprem", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=[f"{ST}#what-you-can-do"],
      user="where in studio do i choose if my functions run on my laptop or over ssh or in docker?",
      steps=[S("search_docs", query="studio on premises deploy method host port",
               docs=[D(ST, "what-you-can-do", start="| **Overview & provider** |", end="| **Overview & provider** |")])],
      final="""**In studio**
1. Open **Overview & provider**.
2. With the on-premises provider selected, pick the deploy method: *local*, *ssh* or *docker*.
3. Fill in the host and port (and the admin token, services and host tuning if you need them).
4. Click **Save**.

[docs/studio.md#what-you-can-do]"""),

    A(278, provider="onprem", stage="prod", mode="ask", page="Logs", persona="informal_non_native",
      sources=[f"{ST}#setup-logs-and-provider-differences", f"{DB}#log-sources"],
      user="logs of old function is big mess. in studio i can delete only that function logs on onprem?",
      steps=[S("search_docs", query="studio logs delete streams on-prem",
               docs=[D(ST, "setup-logs-and-provider-differences", start="- **Logs** shows the logs", end="can show its live logs.")]),
             S("search_docs", query="dashboard log sources on premises delete",
               docs=[D(DB, "log-sources", start="| On premises |", end="| On premises |")])],
      final="""Yes. On premises you can delete one function's entries, the host notes, or everything (memory and `host.jsonl`) [docs/dashboard.md#log-sources].

**In studio**
1. Open **Logs**.
2. List the stored log streams, select the old function's, and delete them [docs/studio.md#setup-logs-and-provider-differences]."""),

    A(279, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{ST}#project-environment-trigger-resources-and-remove"],
      user="in the studio i want remove the functions but keep my queues and buckets. which button?",
      steps=[S("search_docs", query="studio remove keep resources switch",
               docs=[D(ST, "project-environment-trigger-resources-and-remove", start="- **Deploy → Remove** has a switch", end="the data resources stay in the cloud.")])],
      final="""**In studio**
1. Open **Deploy**.
2. Turn **off** *Remove also deletes buckets, queues and topics*.
3. Click **Remove** and type the confirmation.

With the switch off, remove runs `pskit remove --keep-resources`: functions and triggers are destroyed and the data resources stay [docs/studio.md#project-environment-trigger-resources-and-remove]."""),

    A(280, provider="onprem", stage="dev", mode="ask", page="Setup", persona="detailed_spec",
      sources=[f"{ST}#project-environment-trigger-resources-and-remove"],
      user="Before testing locally I want a fresh .venv with Python 3.11 and our requirements installed. Can the studio do that for me?",
      steps=[S("search_docs", query="studio project environment venv requirements",
               docs=[D(ST, "project-environment-trigger-resources-and-remove", end="page.")])],
      final="""Yes [docs/studio.md#project-environment-trigger-resources-and-remove].

**In studio**
1. Open **Setup & credentials** and go to **Project environment**.
2. Pick Python 3.11 from the list. Every interpreter found on this machine is listed, including the Windows `py` launcher's.
3. Create (or recreate) `.venv`. It installs `requirements.txt` into it, and the output streams in the page.

For a Node.js service it runs **npm install** instead (`npm ci` when there's a lockfile)."""),
]
