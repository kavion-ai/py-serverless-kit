"""Category A (docs Q&A and how-to), batch 36: aws / gcp / azure. Studio pages: Resources in the cloud, YAML
mode, Browse account on Azure, save conflicts, extends files, Remove keeping resources, Full VS Code (studio in
Docker, runtimes), the session token and bind address, editor limits, session variables, log streams, cloud CLI
commands on the Test page, new projects, plan. Workflow executions: TIMED_OUT, -w ids, history events, embedded
starts on Azure. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


ST = "docs/studio.md"
WE = "docs/workflow-executions.md"

CONVERSATIONS = [
    A(691, provider="aws", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{ST}#project-environment-trigger-resources-and-remove"],
      user="studio only pls: after remove with keep resources i have old buckets left in aws dev. delete them from studio how",
      steps=[S("search_docs", query="studio delete kept resources in the cloud",
               docs=[D(ST, "project-environment-trigger-resources-and-remove", start="- **Resources → In the cloud**", end="the next deploy then deletes it in the cloud.")])],
      final="""**In studio**
1. Pick aws / dev in the top bar.
2. Open **Resources → In the cloud**. It lists the buckets, queues and topics pskit created for that stage, deployed or kept.
3. Tick the kept buckets (or click **Delete all kept**).
4. Confirm by typing what studio asks for. They are deleted with their data [docs/studio.md#project-environment-trigger-resources-and-remove]."""),

    A(692, provider="gcp", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=[f"{ST}#what-you-can-do"],
      user="studio: paste a whole functions block as raw yaml instead of using the forms",
      steps=[S("search_docs", query="studio yaml page raw editing",
               docs=[D(ST, "what-you-can-do", start="| **YAML** |", end="| **YAML** |")])],
      final="""**In studio**
1. Open **YAML** and switch on *YAML mode* (*Edit raw YAML*).
2. Paste your block and click *Apply to draft*. Parse errors show below the editor.
3. Check *Diff vs disk*, then click **Save** [docs/studio.md#what-you-can-do]."""),

    A(693, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{ST}#browse-account"],
      user="in the trigger form I click Browse account for my azure queue and it shows a message, no list. what does it need?",
      steps=[S("search_docs", query="browse account azure needs",
               docs=[D(ST, "browse-account")])],
      final="""On Azure, Browse account lists storage queues and blob containers. It runs with the credentials of the machine running studio and needs [docs/studio.md#browse-account]:

1. The SDKs: `azure-storage-queue` and `azure-storage-blob`.
2. `AZURE_STORAGE_CONNECTION_STRING` set for the storage account.

**In the terminal** (where you start studio)
```bash
pip install azure-storage-queue azure-storage-blob
export AZURE_STORAGE_CONNECTION_STRING='<connection string>'
pskit studio --open
```
You can always type the queue name instead."""),

    A(694, provider="aws", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{ST}#saving-what-changes-in-pskityml"],
      user="I had studio open, then did a git pull that changed pskit.yml. Now when I click Save studio asks me something. What are the choices, and do I lose anything?",
      steps=[S("search_docs", query="studio save pskit.yml changed on disk",
               docs=[D(ST, "saving-what-changes-in-pskityml")])],
      final="""Studio noticed that `pskit.yml` changed on disk since you loaded it. Save offers to **reload**, **overwrite** or **cancel** [docs/studio.md#saving-what-changes-in-pskityml]:

- Reload: load the pulled file; your unsaved draft edits are dropped.
- Overwrite: write your draft over the pulled version.
- Cancel: keep both as they are, so you can compare first in **YAML** → *Diff vs disk*.

Before every save, the previous file is copied to `.pskit/studio/backups/pskit.<timestamp>.yml`, so an overwrite can be undone."""),

    A(695, provider="gcp", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=[f"{ST}#saving-what-changes-in-pskityml"],
      user="i have pskit.gcp.yml with extends: pskit.yml. if i open studio, which file it change?",
      steps=[S("search_docs", query="studio extends file edited",
               docs=[D(ST, "saving-what-changes-in-pskityml", start="- A file that uses `extends:`", end="- A file that uses `extends:`")])],
      final="""Only the main file. A file that uses `extends:` is shown with a notice, and studio edits just that file, not the one it extends [docs/studio.md#saving-what-changes-in-pskityml].

So open studio on the file you want to change, and put GCP-only settings in `pskit.gcp.yml` and shared ones in `pskit.yml`."""),

    A(696, provider="azure", stage="staging", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{ST}#project-environment-trigger-resources-and-remove"],
      user="in studio i want remove azure staging functions but keep the queues and the blobs with data. only studio steps",
      steps=[S("search_docs", query="studio remove keep buckets queues",
               docs=[D(ST, "project-environment-trigger-resources-and-remove", start="- **Deploy → Remove** has a switch", end="the data resources stay in the cloud.")])],
      final="""**In studio**
1. Pick azure / staging in the top bar and open **Deploy**.
2. Click **Remove**.
3. Turn **off** *Remove also deletes buckets, queues and topics*. Functions and triggers are destroyed; the data resources stay [docs/studio.md#project-environment-trigger-resources-and-remove].
4. Type the confirmation studio asks for."""),

    A(697, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=[f"{ST}#full-vs-code-code-server-in-docker"],
      user="We run pskit studio itself inside a Docker container. Full VS Code fails to open the project. What extra setup does that need?",
      steps=[S("search_docs", query="studio inside container full vs code docker socket",
               docs=[D(ST, "full-vs-code-code-server-in-docker", start="**Studio itself inside a container**", words=200)])],
      final="""The code-server container is started by the host's Docker daemon, so studio must reach that daemon and know where the project lives on the host [docs/studio.md#full-vs-code-code-server-in-docker]:

1. Mount the Docker socket: `-v /var/run/docker.sock:/var/run/docker.sock`.
2. Mount the project and set `PSKIT_STUDIO_HOST_ROOT` to its path on the host.
3. Install the Docker CLI in the studio container.

```bash
docker run --rm -p 127.0.0.1:8770:8770 \\
  -v /var/run/docker.sock:/var/run/docker.sock \\
  -v "$PWD":/work -w /work \\
  -e PSKIT_STUDIO_HOST_ROOT="$PWD" \\
  python:3.12-slim sh -c "pip install py-serverless-kit && apt-get update && apt-get install -y docker.io && pskit studio --host 0.0.0.0"
```"""),

    A(698, provider="azure", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{ST}#full-vs-code-code-server-in-docker"],
      user="full vs code in studio has wrong node. my azure service is nodejs22. how change it?",
      steps=[S("search_docs", query="full vs code runtimes node version",
               docs=[D(ST, "full-vs-code-code-server-in-docker", start="**Runtimes**", end="The default is the project's own runtime.")])],
      final="""**In studio**
1. Open **Code** → **Full VS Code**.
2. Next to the image, pick **Node.js** 22.
3. While VS Code runs, click **Restart with these runtimes**. The container is replaced; your files stay [docs/studio.md#full-vs-code-code-server-in-docker].

The first start with a new combination builds an image, so it takes longer once. The default is the project's own runtime, so check that `provider.runtime` is `nodejs22`."""),

    A(699, provider="aws", stage="dev", mode="ask", page="none", persona="beginner",
      sources=[f"{ST}#security"],
      user="can i send the studio link with #token=... to my colleague so he can look at my project?",
      steps=[S("search_docs", query="studio session token url share",
               docs=[D(ST, "security", end="Requests with a foreign `Host` header")])],
      final="""Don't. Anyone with that URL has full access: studio can write files and run deploys with **your** cloud credentials [docs/studio.md#security]. By default it is only reachable from your machine anyway.

Share the project instead (git), and let your colleague run `pskit studio --open` on their machine. A new token is generated each time studio starts, so restart it if you already sent the link."""),

    A(700, provider="gcp", stage="dev", mode="ask", page="none", persona="detailed_spec",
      sources=["docs/studio.md#studio-build-a-project-without-writing-yaml", f"{ST}#security"],
      user="Our dev environment is a cloud VM. Can I start pskit studio there and open it from my laptop's browser?",
      steps=[S("search_docs", query="studio host bind address remote",
               docs=[D(ST, "studio-build-a-project-without-writing-yaml", start="| `--host` |", end="| `--port` |")])],
      final="""It binds to `127.0.0.1` by default. `--host` changes the bind address, but anything other than loopback prints a warning, because studio can edit files and deploy [docs/studio.md#studio-build-a-project-without-writing-yaml].

```bash
pskit studio --host 0.0.0.0 --port 8770
```
If you do this, only open the port to your own IP, and keep the token URL private: every API call needs it [docs/studio.md#security]."""),

    A(701, provider="aws", stage="dev", mode="ask", page="Code", persona="pasted_error",
      sources=[f"{ST}#security"],
      user="studio code editor won't open data/sample-events.json (3 MB). other files open fine",
      steps=[S("search_docs", query="studio editor file size limit",
               docs=[D(ST, "security", start="- The file editor only reaches files inside the project.", end="refuses binary files or files over 1 MiB.")])],
      final="""The built-in editor refuses files over 1 MiB (and binary files) [docs/studio.md#security].

Options:
1. Open it in your own editor on this machine, or in **Code** → **Full VS Code** (code-server on your project).
2. Or split it into smaller sample files you can edit in studio."""),

    A(702, provider="azure", stage="dev", mode="ask", page="Setup", persona="terse_expert",
      sources=[f"{ST}#setup-logs-and-provider-differences"],
      user="studio only: set ARM_SUBSCRIPTION_ID for this session",
      steps=[S("search_docs", query="studio set provider variables session",
               docs=[D(ST, "setup-logs-and-provider-differences", end="- test the SSH connection of an on-prem deploy.")])],
      final="""**In studio**
1. Open **Setup & credentials** with Azure in the top bar.
2. Under *Environment variables*, enter `ARM_SUBSCRIPTION_ID` and its value.
3. Click **Set for this session**. It holds only while studio runs, and the value is never sent back to the browser [docs/studio.md#setup-logs-and-provider-differences].
4. Click *Check again*."""),

    A(703, provider="aws", stage="dev", mode="ask", page="Logs", persona="informal_non_native",
      sources=[f"{ST}#setup-logs-and-provider-differences"],
      user="only in studio: delete old log streams of my worker function on aws",
      steps=[S("search_docs", query="studio logs delete streams",
               docs=[D(ST, "setup-logs-and-provider-differences", start="- **Logs** shows the logs", end="- **Logs** shows the logs")])],
      final="""**In studio**
1. Open **Logs** with aws / dev in the top bar.
2. Open *Stored logs* to list the log streams.
3. Tick the streams of `worker` you want gone (or choose all), click *Delete* and confirm.

Deleting streams works on AWS and on premises [docs/studio.md#setup-logs-and-provider-differences]."""),

    A(704, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="pasted_error",
      sources=[f"{WE}#the-execution-record", f"{WE}#cancel-timeouts-and-restarts-embedded-engine"],
      user="pskit workflow status shows TIMED_OUT for our export run, error States.Timeout. Where does that limit come from?",
      steps=[S("search_docs", query="workflow status TIMED_OUT States.Timeout",
               docs=[D(WE, "the-execution-record", start="| `status` | Meaning |", end="| `ABORTED` |")]),
             S("search_docs", query="workflow timeout key seconds",
               docs=[D(WE, "cancel-timeouts-and-restarts-embedded-engine", start="- **Timeout:**", end="On AWS it is the state machine's `TimeoutSeconds`.")])],
      final="""`TIMED_OUT` means the run went past `workflows.<name>.timeout` [docs/workflow-executions.md#the-execution-record].

**In code**
```yaml
workflows:
  export:
    timeout: 3600
```
The value is in seconds [docs/workflow-executions.md#cancel-timeouts-and-restarts-embedded-engine].

**In studio**
1. Open **Workflows** and select `export`.
2. Raise *Timeout (s)* and click **Save**.

Also check the task functions' own `timeout`, so a single task doesn't fail first."""),

    A(705, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=[f"{WE}#following-a-run"],
      user="gcp: workflow status <id> can't find the run. id from executions list",
      steps=[S("search_docs", query="workflow status gcp id workflow flag",
               docs=[D(WE, "following-a-run", start="Pages use `--offset` on premises", end="when the id alone doesn't identify the workflow.")])],
      final="""Pass the workflow name with `-w` when the id alone doesn't identify the workflow [docs/workflow-executions.md#following-a-run]:

```bash
pskit workflow status <id> -w order-pipeline --watch
pskit workflow cancel <id> -w order-pipeline
```"""),

    A(706, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=[f"{WE}#the-execution-record"],
      user="in workflow status --history i see enter, exit, retry, caught. what they mean?",
      steps=[S("search_docs", query="workflow history events enter exit retry caught",
               docs=[D(WE, "the-execution-record", start="History events:", end="List calls return the summary fields only")])],
      final="""[docs/workflow-executions.md#the-execution-record]

- `enter` / `exit`: a state started / finished (`exit` has `duration_ms`).
- `retry`: a `retry` rule ran the state again; it shows the `attempt` and the `error`.
- `caught`: a `catch` rule sent an error to another state.
- `fail`: a `fail` state ran.

Long runs keep the newest 1000 entries; `history_truncated` tells how many were dropped."""),

    A(707, provider="azure", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WE}#embedded-orchestrator-on-a-cloud", f"{WE}#workflow-executions"],
      user="Our Azure workflow uses the default engine. When I run pskit workflow start, what comes back, and can I follow it later?",
      steps=[S("search_docs", query="embedded orchestrator cloud start result history",
               docs=[D(WE, "embedded-orchestrator-on-a-cloud")])],
      final="""On Azure the default engine is the embedded orchestrator, so the run happens inside one call of the orchestrator function [docs/workflow-executions.md#embedded-orchestrator-on-a-cloud]:

- `pskit workflow start` posts to the orchestrator's HTTP URL and prints the result: `execution_id`, `status`, `output`, `duration_ms`.
- A failure answers 500 with `FAILED` (or `TIMED_OUT`), `error` and `cause`.
- No history is kept, so there's nothing to follow later; `pskit workflow executions` explains why.

```bash
pskit workflow start order-pipeline -i '{"amount": 50}'
```"""),

    A(708, provider="aws", stage="dev", mode="ask", page="Test", persona="aws_migrator",
      sources=[f"{ST}#test-functions"],
      user="Besides pskit, I want the plain aws CLI command to send a test message to the queue that triggers my worker. Does studio show that?",
      steps=[S("search_docs", query="studio how to test this cloud cli command",
               docs=[D(ST, "test-functions", start="**How to test this**", end="for which events pskit can send on each provider.")])],
      final="""Yes. The **How to test this** panel on the Test page shows each trigger three ways: studio steps, terminal commands (local `pskit invoke`, deployed `pskit trigger`, and the cloud's own CLI such as `aws sqs send-message`) with Copy buttons, and the console steps [docs/studio.md#test-functions].

**In studio**
1. Open **Test** and pick `worker` and its queue trigger.
2. Open *How to test this* → *Terminal* and copy the `aws sqs send-message` command."""),

    A(709, provider="gcp", stage="dev", mode="ask", page="none", persona="beginner",
      sources=["docs/studio.md#what-you-can-do", "docs/studio.md#studio-build-a-project-without-writing-yaml"],
      user="how i make a brand new project for google cloud in studio? i have empty folder",
      steps=[S("search_docs", query="studio new project empty folder",
               docs=[D(ST, "what-you-can-do", start="| **New project** |", end="| **New project** |")])],
      final="""**In studio**
1. Start studio in the empty folder:
```bash
cd my-service
pskit studio --open
```
2. The *New project* page appears because there is no `pskit.yml`. Enter the service name, pick Google Cloud and a starter template [docs/studio.md#what-you-can-do].
3. In **Overview & provider**, fill in *Project* (your GCP project ID) and click **Save**."""),

    A(710, provider="azure", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{ST}#what-you-can-do"],
      user="Before deploying to Azure prod from studio, I want to see exactly what Terraform will change. Where do I do that?",
      steps=[S("search_docs", query="studio deploy page plan",
               docs=[D(ST, "what-you-can-do", start="| **Deploy** |", end="| **Deploy** |")])],
      final="""**In studio**
1. Pick azure / prod in the top bar and open **Deploy**.
2. Click **Plan**. The live log shows the Terraform plan; nothing is changed [docs/studio.md#what-you-can-do].
3. If it looks right, click **Deploy**. A stage named `prod*` needs a typed confirmation."""),
]
