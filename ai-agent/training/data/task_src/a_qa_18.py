"""Category A (docs Q&A and how-to), batch 18: the Deploy, Logs and Test pages of pskit studio for on-prem stages
(machine choice, cluster or one server, typed confirmation, plan, health check, info, log sources, stored logs,
test events, trigger on another server). Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


PR = "docs/providers.md"
OP = "onprem-on-premises"
LS = "logs-and-stats"
CL = "docs/cluster.md"
ONE = "one-server-or-the-cluster-per-deploy"
ST = "docs/studio.md"
SV = "docs/resource-guides/onprem/services.md"
CHOSEN = "deploy-the-functions-to-a-chosen-machine"
CLI = "docs/cli.md"
TS = "docs/troubleshooting.md"

REMEMBERS = D(PR, OP, start="**The stage remembers its machine.**", end="**The stage remembers its machine.**")
SAME_CHOICE = D(SV, CHOSEN, start="Logs, triggers and executions follow the same choice",
                end="so two machines never overwrite each other's deployment.")

CONVERSATIONS = [
    A(341, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{PR}#{OP}"],
      user="on the deploy page the Machine box says 'Same as the last deploy: app-1'. what does it mean? i don't remember choosing app-1",
      steps=[S("search_docs", query="stage remembers machine last deploy",
               docs=[REMEMBERS])],
      final="""Your last deploy of this stage went to app-1 (picked in **Deploy > Machine** or with `--server app-1`). pskit wrote that into `.pskit/onprem-staging/onprem_deployed.json`, so the stage remembers it [docs/providers.md#onprem-on-premises]:
- the next deploy without another choice goes to app-1 again;
- Test, Logs, `pskit trigger` and `pskit logs` talk to the host on app-1.

To go somewhere else for one deploy:

**In studio**
1. **Deploy > Machine**: pick another saved server, or *This machine*.
2. Press **Deploy**.

**In the terminal**
```bash
pskit deploy -s staging --server app-2
pskit deploy -s staging --server local
```"""),

    A(342, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{CL}#{ONE}"],
      user="In the studio only: how do I move our staging stage from one server onto cluster prod for a load test, and back to app-1 afterwards?",
      steps=[S("search_docs", query="deploy page run on scaling cluster one machine",
               docs=[D(CL, ONE, end="4. Where the stage was last deployed: a cluster or a saved server.")])],
      final="""**In studio**
1. Choose stage `staging` in the top bar and open **Deploy**.
2. Set *Run on* to **Scaling cluster**, pick `prod`, press **Deploy** and confirm. The stage now remembers the cluster.
3. After the test, set *Run on* to **One machine**, choose **app-1** in *Machine*, press **Deploy**.

The old place keeps running after a move. Remove the stage there when it should stop [docs/cluster.md#one-server-or-the-cluster-per-deploy]."""),

    A(343, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="informal_non_native",
      sources=[f"{ST}#what-you-can-do"],
      user="when i press deploy on prod stage the studio want i type something. what i type? on dev it not ask",
      steps=[S("search_docs", query="deploy prod typed confirmation studio",
               docs=[D(ST, "what-you-can-do", start="| **Deploy** |", end="| **Deploy** |")])],
      final="""That's on purpose. **Remove**, and a deploy to any stage whose name starts with `prod`, need a typed confirmation [docs/studio.md#what-you-can-do].

Type the target the dialog shows, `onprem/prod`, then press **Deploy**. Stages like `dev` or `staging` only ask a normal yes/no."""),

    A(344, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{CLI}#pskit-plan", f"{PR}#{OP}"],
      user="What does the Plan button do for an on-prem stage? Does it copy anything to the server or restart the host?",
      steps=[S("search_docs", query="plan on-premises terraform_data local-exec",
               docs=[D(CLI, "pskit-plan"),
                     D(PR, OP, start="**Resources:** `terraform_data.host`", end="**Resources:** `terraform_data.host`")])],
      final="""Plan only packages and asks Terraform what it *would* do: `pskit plan` runs package, `terraform init` and `terraform plan` [docs/cli.md#pskit-plan].

On-prem has one resource, `terraform_data.host`. Its create step runs `onprem_deploy.py apply` and its destroy step runs `onprem_deploy.py destroy` [docs/providers.md#onprem-on-premises]. Those run only on **Deploy** or **Remove**, so a plan doesn't copy files or restart anything.

**In the terminal**
```bash
pskit plan -s dev
pskit plan -s dev --destroy
```"""),

    A(345, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{PR}#{OP}", f"{TS}#provider-gotchas"],
      user="deploy to app-1 fails: http://127.0.0.1:8090/__pskit/health does not answer\n... systemctl status ... journalctl ...\nwhat is pskit waiting for?",
      steps=[S("search_docs", query="health does not answer deploy fails systemctl journalctl",
               docs=[D(PR, OP, start="SSH and `scp` write `pskit-run.sh`", end="when a unit was used.")])],
      final="""After copying the release, pskit restarts the host and waits until `/__pskit/health` answers on the server itself. Here the host didn't come up, so the deploy fails and adds `systemctl status` and `journalctl` to the error [docs/providers.md#onprem-on-premises].

The real cause is in those `journalctl` lines. Look for:
- a Python traceback at start, such as an import error in a handler or a missing dependency. Run the function on your machine with `pskit invoke -f <function>` to see it;
- the port: each service needs its own `options.port`. If another service already uses 8090, give this one another port.

Fix it, then deploy again."""),

    A(346, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="aws_migrator",
      sources=["docs/architecture.md#deploy-pipeline", f"{SV}#{CHOSEN}"],
      user="With Lambda we used aliases dev and prod on the same function. On-prem, what's the equivalent, and can dev and prod live on the same server?",
      steps=[S("search_docs", query="stages separate deployments state per stage onprem",
               docs=[D("docs/architecture.md", "deploy-pipeline", start="- **One directory per provider and stage.**", end="- **One directory per provider and stage.**"),
                     SAME_CHOICE])],
      final="""Stages. Each stage is its own deployment, with its own directory, Terraform state and host process [docs/architecture.md#deploy-pipeline].

They can share a server if each one has its own port.

**In code**
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {server: app-1, path: /opt/pskit/shop}
stages:
  prod:
    provider:
      options:
        port: 8081
        deploy: {server: app-1, path: /opt/pskit/shop-prod}
```

**In the terminal**
```bash
pskit deploy -s dev
pskit deploy -s prod
```
Each stage has its own URL, on its own port."""),

    A(347, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{CLI}#pskit-info"],
      user="what does the Info button show for my onprem deploy? i want the url of my functions",
      steps=[S("search_docs", query="pskit info deployed functions urls",
               docs=[D(CLI, "pskit-info"), REMEMBERS])],
      final="""**Info** runs `pskit info`. It shows the deployed functions, their triggers and URLs, and where the stage runs (`deployed on: <server>`). Before the first deploy it lists them as `not deployed` [docs/cli.md#pskit-info].

**In studio**
1. **Deploy > Info**.

**In the terminal**
```bash
pskit info -s dev
pskit info -s dev --refresh --json
```
`--refresh` reads the Terraform outputs again instead of the saved record."""),

    A(348, provider="onprem", stage="prod", mode="ask", page="Logs", persona="beginner",
      sources=[f"{SV}#{CHOSEN}", f"{PR}#{OP}"],
      user="the logs page has a Server dropdown. which server should i pick? and port 8080 is closed from my office",
      steps=[S("search_docs", query="logs server choice port closed ssh",
               docs=[SAME_CHOICE,
                     D(PR, OP, start="**Ports closed to this machine.**", end="**Ports closed to this machine.**")])],
      final="""Keep the default. Logs start on the server this stage was last deployed to. Pick another server only when the same stage also runs elsewhere [docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine].

A closed port is fine. When 8080 can't be reached from your machine, pskit reads the logs over the deploy's SSH login instead [docs/providers.md#onprem-on-premises].

**In studio**
1. **Logs**: leave *Server* as it is, or choose the machine.

**In the terminal**
```bash
pskit logs -s prod
pskit logs -s prod --server app-2
```"""),

    A(349, provider="onprem", stage="dev", mode="ask", page="Logs", persona="terse_expert",
      sources=[f"{PR}#{OP}"],
      user="clear only the host notes on the onprem host, keep function logs. http call?",
      steps=[S("search_docs", query="delete logs host notes function __host__",
               docs=[D(PR, OP, start="| `GET /__pskit/logs/streams` |", end="| `DELETE /__pskit/logs[?function=]` |")])],
      final="""`DELETE /__pskit/logs?function=__host__`. It also rewrites `host.jsonl` [docs/providers.md#onprem-on-premises].

**In the terminal**
```bash
curl -X DELETE -H "x-pskit-token: ${PSKIT_ADMIN_TOKEN}" "http://192.0.2.10:8080/__pskit/logs?function=__host__"
```
Leave out the header when no `admin_token` is set."""),

    A(350, provider="onprem", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/placement.md#how-the-groups-work-together"],
      user="We use placement: api on app-1, resize on gpu-box. The Logs page says 'Every group of this project'. Do I have to read logs on gpu-box separately?",
      steps=[S("search_docs", query="placement groups logs default group",
               docs=[D("docs/placement.md", "how-the-groups-work-together", start="| `pskit logs`, the studio's logs |", end="| `pskit logs`, the studio's logs |")])],
      final="""No. Every group sends its logs and invocation counts to the default group, so one list has them all [docs/placement.md#how-the-groups-work-together]. Each line's `group` field says where it ran.

**In the terminal**
```bash
pskit logs -s prod -f
pskit logs -s prod --function resize --level error
```
The groups send their logs to the default group's port, so that port must be open from gpu-box."""),

    A(351, provider="onprem", stage="dev", mode="ask", page="Logs", persona="informal_non_native",
      sources=[f"{PR}#{LS}"],
      user="i use print() in handler, not ctx.logger. on onprem i see it in logs or not?",
      steps=[S("search_docs", query="print stdout captured logs onprem",
               docs=[D(PR, LS, end="the listen address.")])],
      final="""Yes. The host records `print()` lines too, as source `stdout` at level `INFO`, and `stderr` lines as `WARNING` [docs/providers.md#logs-and-stats].

**In the terminal**
```bash
pskit logs --source stdout
pskit logs -f --function worker
```
`ctx.logger` is still better: its lines are structured and carry the function and request id."""),

    A(352, provider="onprem", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{TS}#http", f"{PR}#{LS}"],
      user="POST /orders on my onprem host returns\n{\"error\": \"Internal Server Error\", \"status\": 500, \"request_id\": \"7c1e0f3a\"}\nno detail. where is the real error?",
      steps=[S("search_docs", query="500 with only a request id logs",
               docs=[D(TS, "http", start="**500 with only a request id**", end="to include the exception text."),
                     D(PR, LS, start="Entries written during an invocation", end="Entries written during an invocation")])],
      final="""The response hides the exception on purpose. Find that `request_id` in the host's logs [docs/troubleshooting.md#http]. Entries written during an invocation carry its `function` and `request_id` [docs/providers.md#logs-and-stats].

**In the terminal**
```bash
pskit logs -s prod --level error -n 200
pskit logs -s prod --level error --json
```
The `--json` lines show the `request_id` field, so you can match `7c1e0f3a`. The studio's **Logs** page shows the same entries.

To see the full traceback, run the function on your machine with the same body, for example `pskit invoke -f <function> -t http --method POST --path /orders -d @body.json`."""),

    A(353, provider="onprem", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=[f"{SV}#{CHOSEN}"],
      user="on the test page step 3 there is a Server box. my staging runs on app-2. what happens if i choose app-1?",
      steps=[S("search_docs", query="test server choice trigger other machine",
               docs=[SAME_CHOICE])],
      final="""**Send to onprem / staging** then sends the event to the host on app-1, not to app-2. Triggers and logs follow the server you pick; without a choice they go to the host of the last deploy (app-2) [docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine].

So keep app-2 unless staging also runs on app-1. **Run locally** doesn't use the Server box: it runs on your machine.

**In the terminal**
```bash
pskit trigger -s staging --server app-2 -f api
```"""),

    A(354, provider="onprem", stage="dev", mode="ask", page="Test", persona="aws_migrator",
      sources=[f"{ST}#test-functions", "docs/cli.md#pskit-settings"],
      user="In the Lambda console we shared test events across the team. Where does studio keep saved test events, and can colleagues get them?",
      steps=[S("search_docs", query="saved test events file share",
               docs=[D(ST, "test-functions", start="2. Edit the payload.", end="`.pskit/studio/test-events.json`, like test events in the Lambda console."),
                     D(CLI, "pskit-settings", start="| `.pskit/studio/test-events.json` |", end="| `.pskit/studio/test-events.json` |")])],
      final="""**Save event** keeps named payloads per function in `.pskit/studio/test-events.json` [docs/studio.md#test-functions]. `.pskit/` is out of git, so a clone doesn't get them.

To hand them over, export the project's settings. The file includes the saved test events [docs/cli.md#pskit-settings].

**In the terminal**
```bash
pskit settings export -o team.pskit-settings
pskit settings import team.pskit-settings
```

**In studio**
1. **Setup & credentials > Move settings to another machine**: *Export settings*, then import the file on the other machine.

The file also has SSH keys and service passwords. Send it and its passphrase by different channels."""),

    A(355, provider="onprem", stage="staging", mode="ask", page="Test", persona="terse_expert",
      sources=[f"{CLI}#pskit-trigger", f"{SV}#{CHOSEN}"],
      user="cli only: 2 real queue msgs to worker on the staging host on app-2, not the last deployed one",
      steps=[S("search_docs", query="pskit trigger queue messages server",
               docs=[D(CLI, "pskit-trigger", start="pskit trigger -f worker -e 0 -d '[{\"id\": 1}, {\"id\": 2}]'", end="| `--json` | JSON output |"),
                     SAME_CHOICE])],
      final="""**In the terminal**
```bash
pskit trigger -s staging --server app-2 -f worker -e 0 -d '[{"id": 1}, {"id": 2}]'
pskit logs -s staging --server app-2 -f --function worker
```
[docs/cli.md#pskit-trigger]"""),

    A(356, provider="onprem", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=[f"{ST}#test-functions", f"{CLI}#pskit-trigger"],
      user="What does the 'How to test this' panel on the Test page give me for an on-prem storage trigger? I want commands I can paste into our runbook.",
      steps=[S("search_docs", query="how to test this panel commands storage trigger",
               docs=[D(ST, "test-functions", start="**How to test this**"),
                     D(CLI, "pskit-trigger", start="| Type | `-d` |")])],
      final="""For each trigger it shows three ways: the studio steps, the terminal commands with **Copy** buttons, and console steps where they exist. The commands are the local `pskit invoke` and the deployed `pskit trigger` [docs/studio.md#test-functions].

For a storage trigger:

**In the terminal**
```bash
pskit invoke -f on-upload -t storage -d '{"key": "in/a.csv"}'
pskit trigger -f on-upload -e 0 -d '{"key": "in/a.csv", "content": "id,total"}'
pskit trigger --list
```
`pskit trigger` uploads the object to the deployed host's bucket. `"action": "deleted"` deletes it instead [docs/cli.md#pskit-trigger]. `--list` prints every trigger's commands, even before a deploy."""),

    A(357, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{CL}#{ONE}"],
      user="studio asks: 'This stage is deployed on app-1 now. Deploying it on app-2 moves it there (remove it from the old place first if it should no longer run there).' will app-1 stop by itself?",
      steps=[S("search_docs", query="move stage old place keeps running remove",
               docs=[D(CL, ONE, start="So `pskit deploy --cluster prod` once moves a stage", end="back to one server. The old place keeps running until you `pskit remove` it there.")])],
      final="""No. The old place keeps running until you remove it there [docs/cluster.md#one-server-or-the-cluster-per-deploy].

**In the terminal**
Remove it from app-1 first, then deploy to app-2:
```bash
pskit remove -s staging --server app-1
pskit deploy -s staging --server app-2
```

**In studio**
1. **Deploy > Machine**: choose **app-1**, press **Remove** and type the confirmation.
2. Choose **app-2**, press **Deploy**.

Remove leaves `data_dir` on app-1, so queued messages and files stay there."""),

    A(358, provider="onprem", stage="dev", mode="ask", page="Logs", persona="informal_non_native",
      sources=[f"{PR}#{OP}"],
      user="logs page have 'Stored logs' part. what it show for onprem?",
      steps=[S("search_docs", query="log streams onprem entry count first last time",
               docs=[D(PR, OP, start="| `GET /__pskit/logs/streams` |", end="| `DELETE /__pskit/logs[?function=]` |")])],
      final="""A list of the stored log streams: per function, the number of entries and the first and last time. Host notes are their own stream [docs/providers.md#onprem-on-premises]. Tick some and delete them, or delete all.

**In studio**
1. **Logs > Stored logs**.

**In the terminal**
```bash
pskit logs --streams
pskit logs --delete-all --function worker -y
```"""),

    A(359, provider="onprem", stage="prod", mode="ask", page="Logs", persona="aws_migrator",
      sources=[f"{PR}#{LS}", "docs/configuration.md#provider"],
      user="our config has log_retention_days: 30 from AWS. What does that do on the on-prem host, and how long are logs kept there?",
      steps=[S("search_docs", query="log retention onprem host.jsonl rotate",
               docs=[D("docs/configuration.md", "provider", start="| `log_retention_days` |", end="| `log_retention_days` |"),
                     D(PR, LS, start="Entries written during an invocation", end="Messages longer than 16 KiB are truncated.")])],
      final="""Nothing. `log_retention_days` is the AWS CloudWatch log group retention [docs/configuration.md#provider].

The host keeps logs by size instead [docs/providers.md#logs-and-stats]:
- the newest 5000 entries in memory (`options.log_buffer`);
- every entry in `<data_dir>/logs/host.jsonl`, which rotates at 10 MiB and keeps three old files.

**In code**
```yaml
provider:
  name: onprem
  log_retention_days: 30
  options:
    log_buffer: 20000
```
You can leave `log_retention_days` in place for the AWS deploys. To keep logs longer, copy the rotated files or ship them to your own log system."""),

    A(360, provider="onprem", stage="prod", mode="ask", page="Logs", persona="beginner",
      sources=[f"{CL}#how-the-functions-run-in-a-cluster", f"{CL}#live-logs"],
      user="my functions run on cluster prod with 3 replicas. the logs page shows all lines mixed. how do i know which replica wrote a line?",
      steps=[S("search_docs", query="cluster logs replica tag which server",
               docs=[D(CL, "how-the-functions-run-in-a-cluster", start="* A web replica hands those to main.", end="`replica`, so `pskit logs`, the studio's **Logs** view and `/__pskit/stats` show the whole cluster."),
                     D(CL, "live-logs", start="Web replicas send their lines to the main replica.")])],
      final="""Each web replica sends its lines to the main replica every second, tagged with `replica` [docs/cluster.md#how-the-functions-run-in-a-cluster]. That field tells you who wrote the line.

**In the terminal**
```bash
pskit logs -s prod --json -n 200
```
Each JSON line shows the field.

**In studio**
1. **Logs**: picking one server reads only that server [docs/cluster.md#live-logs]."""),
]
