"""Category A (docs Q&A and how-to), batch 22 (10 conversations): on-prem leftovers. Network map and unused
servers, advertise URLs, local invoke with an env file, queue directories, deploy targets, client tunnel, cluster
switch, visibility timeout, and local Node.js. Error texts were checked with real `pskit validate` runs.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


PR = "docs/providers.md"
OP = "onprem-on-premises"
SV = "docs/resource-guides/onprem/services.md"
WHERE = "where-a-server-is-used-and-how-the-servers-connect"
NET3 = "3-deploy-to-one-server-method-ssh-docker-or---server-name"

CONVERSATIONS = [
    A(421, provider="onprem", stage="prod", mode="ask", page="Network map", persona="informal_non_native",
      sources=[f"{SV}#{WHERE}", f"{SV}#servers-several-machines"],
      user="on network map i click one box and it say 'Not a saved server'. but my functions run there?",
      steps=[S("search_docs", query="network map machine not a saved server",
               docs=[D(SV, WHERE, start="The **Network map** page draws", end="from local files only."),
                     D(SV, "servers-several-machines", end="Machine**, the shell and the terminal.")])],
      final="""That box is an address pskit knows from a deploy or a service, for example a `deploy.host` typed in `pskit.yml`, but not a saved server. The map still shows its ports [docs/resource-guides/onprem/services.md#where-a-server-is-used-and-how-the-servers-connect].

Save it once to manage it like the others (test, shell, **Deploy > Machine**, services):

**In studio**
1. **Resources > On-prem services > Servers > + Add server**: same host, user and port [docs/resource-guides/onprem/services.md#servers-several-machines].
2. **Network map > Refresh**.

**In the terminal**
```bash
pskit resources onprem servers add app-1 --ssh deploy@192.0.2.10 --pem ~/.ssh/app-1.pem
```"""),

    A(422, provider="onprem", stage="prod", mode="ask", page="Overview", persona="beginner",
      sources=[f"docs/onprem-network.md#{NET3}", f"{PR}#{OP}"],
      user="pskit info shows my api as http://192.0.2.10:8080 but users use https://api.example.com through our proxy. can pskit show the real url?",
      steps=[S("search_docs", query="advertise url pskit info proxy dns",
               docs=[D("docs/onprem-network.md", NET3, start="Set `options.host: 0.0.0.0` (bind)", end="A host bound to `127.0.0.1` is only reachable"),
                     D(PR, OP, start="`options.host` is the bind address **on the target**.", end="`options.host` is the bind address **on the target**.")])],
      final="""Yes, set `options.advertise`. It's the URL stored in `pskit info`. Without it, SSH and remote Docker deploys use `http://<server>:<port>` [docs/providers.md#onprem-on-premises].

**In code**
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    port: 8080
    advertise: https://api.example.com
```
Deploy again, then `pskit info -s prod` shows the new URL. `advertise` changes only what pskit reports; the proxy still forwards to port 8080 [docs/onprem-network.md#3-deploy-to-one-server-method-ssh-docker-or---server-name]."""),

    A(423, provider="onprem", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/local-development.md#environment"],
      user="local invoke of worker with the vars from .env.onprem instead of .env?",
      steps=[S("search_docs", query="invoke env file local environment",
               docs=[D("docs/local-development.md", "environment", end="`provider.environment` and the function's `environment`, and finally load `.env` (or `--env-file`):")])],
      final="""**In the terminal**
```bash
pskit invoke -f worker -t queue -d '[{"id": 1}]' --env-file .env.onprem
```
The file is loaded last, after `provider.environment` and the function's `environment` [docs/local-development.md#environment]."""),

    A(424, provider="onprem", stage="dev", mode="ask", page="Network map", persona="beginner",
      sources=[f"{SV}#{WHERE}"],
      user="i saved many test servers months ago. how do i find the ones nothing uses anymore and delete them?",
      steps=[S("search_docs", query="servers not used anywhere forget",
               docs=[D(SV, WHERE, end="`pskit resources onprem servers usage [NAME] [--json]`.")])],
      final="""Servers that nothing names say *not used anywhere* in the **Used in** column. **Forget** shows that list again before it asks [docs/resource-guides/onprem/services.md#where-a-server-is-used-and-how-the-servers-connect].

**In studio**
1. **Resources > On-prem services > Servers**: look for *not used anywhere*.
2. Press **Forget** on that row and confirm.

On **Network map**, the *servers not used anywhere* checkbox shows or hides them on the map.

**In the terminal**
```bash
pskit resources onprem servers usage
pskit resources onprem servers remove old-lab
```
Forgetting a server only removes it from pskit; nothing on the machine is stopped."""),

    A(425, provider="onprem", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{PR}#{OP}"],
      user="On our server, queues should live under /var/pskit/queues (a separate, backed-up disk) and the bucket files under /srv/files. How do I point the on-prem services there?",
      steps=[S("search_docs", query="services queue directory path storage directory",
               docs=[D(PR, OP, start="- **Dependencies:**", words=60),
                     D(PR, OP, start="Omitted services default to `builtin`", end="Omitted services default to `builtin`")])],
      final="""Use `options.services` with `use: directory` and a `path` [docs/providers.md#onprem-on-premises]:

**In code**
```yaml
provider:
  name: onprem
  options:
    services:
      queue: {use: directory, path: /var/pskit/queues}
      storage: {use: directory, path: /srv/files}
```
The paths are on the server. Services you leave out stay `builtin` and are created at start under `data_dir`. `existing: true` on a queue or bucket makes the host wait until that directory exists instead of creating it."""),

    A(426, provider="onprem", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{PR}#{OP}"],
      user="ERROR: [provider.options.deploy] options.deploy.install: systemd is only valid when target_os is linux\n\nthe server is windows server 2022 over ssh",
      steps=[S("search_docs", query="install systemd linux only target_os windows",
               docs=[D(PR, OP, start="**Deploy targets**", end="| `ssh` or `scp` |")])],
      final="""systemd exists only on Linux, so `install: systemd` can't be used for a Windows server. Use `install: process`, which starts the host as a normal process [docs/providers.md#onprem-on-premises].

**In code**
```yaml
provider:
  name: onprem
  options:
    deploy:
      method: ssh
      host: 192.0.2.30
      user: admin
      target_os: windows
      install: process
```
Run validate again; the error is gone."""),

    A(427, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/client.md#when-connections-time-out"],
      user="port 8080 on server closed for my pc and i not allowed open it. i want call my api from my browser for test",
      steps=[S("search_docs", query="host port times out tunnel",
               docs=[D("docs/client.md", "when-connections-time-out", start="| The host port itself times out |", end="| The host port itself times out |")])],
      final="""Use a tunnel over SSH. It forwards the host's port to your PC [docs/client.md#when-connections-time-out].

**In the terminal**
```bash
pskit client tunnel -s dev
```
Keep it running, then open `http://127.0.0.1:8080/...` in your browser. If 8080 is busy on your PC, add `--local-port 9080` and use that port."""),

    A(428, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="beginner",
      sources=["docs/studio.md#what-you-can-do", "docs/cluster.md#set-up"],
      user="what does the switch 'Deploy this project's functions to …' on the cluster page do?",
      steps=[S("search_docs", query="deploy this project's functions to switch cluster page",
               docs=[D("docs/studio.md", "what-you-can-do", start="| **Scaling cluster** |", end="| **Scaling cluster** |")])],
      final="""It writes `provider.options.cluster` into `pskit.yml`, so this project's deploys go to that cluster from now on [docs/studio.md#what-you-can-do].

**In studio**
1. **Scaling cluster**: open the cluster and turn on the switch.
2. Press **Save**, then **Deploy > Deploy**.

**In code**
The same, written by hand:
```yaml
provider:
  name: onprem
  options:
    cluster: prod
```
For a single deploy without changing the file, use `pskit deploy --cluster prod`."""),

    A(429, provider="onprem", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{PR}#{OP}", "docs/events.md#queue"],
      user="On SQS we set the visibility timeout to 6x the Lambda timeout. On the on-prem built-in queue, what's the default, and can I set it?",
      steps=[S("search_docs", query="visibility timeout default on premises queue",
               docs=[D(PR, OP, start="| queue | one JSON file per message.", end="| queue | one JSON file per message.")])],
      final="""Same rule. The on-prem queue honours `visibility_timeout`, and its default is `max(30, 6 x timeout)` [docs/providers.md#onprem-on-premises].

**In code**
```yaml
functions:
  worker:
    handler: app.jobs.work
    timeout: 60
    events:
      - queue:
          name: jobs
          visibility_timeout: 600
          dead_letter: jobs-dlq
          max_receive: 5
```
Leave it out to get 360 s here (6 x 60)."""),

    A(430, provider="onprem", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{PR}#{OP}"],
      user="WARNING: [provider.options.deploy.node] Node.js functions need `node` on PATH on this machine (https://nodejs.org/en/download), or set options.deploy.node: bundle to download it at deploy.\n\nmethod local, runtime nodejs20",
      steps=[S("search_docs", query="node system bundle local deploy node on PATH",
               docs=[D(PR, OP, start="`node: system` (the default) needs `node` on PATH", end="`node: system` (the default) needs `node` on PATH")])],
      final="""With `node: system` (the default), the host needs `node` on PATH. Locally `pskit deploy` stops with a link to the installer when it's missing [docs/providers.md#onprem-on-premises].

Two fixes:
1. Install Node.js 20 and open a new terminal.
2. Or let pskit download it at deploy:

**In code**
```yaml
provider:
  name: onprem
  runtime: nodejs20
  options:
    deploy:
      method: local
      node: bundle
```"""),
]
