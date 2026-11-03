"""Category A (docs Q&A and how-to), batch 19: on-prem troubleshooting. Real `pskit validate` messages for on-prem
options and deploy settings (checked by running validate on scratch projects), plus deploy, HTTP and tooling problems
from docs/troubleshooting.md and docs/providers.md. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


PR = "docs/providers.md"
OP = "onprem-on-premises"
TS = "docs/troubleshooting.md"
CF = "docs/configuration.md"

OPTIONS = D(PR, OP, start="- **Dependencies:**", words=60)
TARGETS = D(PR, OP, start="**Deploy targets**", end="| `docker` |")
GOTCHA = D(TS, "provider-gotchas", start="| onprem |", end="| onprem |")

CONVERSATIONS = [
    A(361, provider="onprem", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{PR}#{OP}"],
      user="ERROR: [provider.options.workflow_workers] options.workflow_workers must be an integer >= 1\n\ni set 0 because this service has no workflows",
      steps=[S("search_docs", query="workflow_workers option onprem",
               docs=[OPTIONS])],
      final="""`workflow_workers` is how many workflow runs execute at once; further starts wait for a worker. It must be at least 1 [docs/providers.md#onprem-on-premises].

You don't need it at all without workflows. Delete the line, and the default (8) applies but is never used.

**In code**
```yaml
provider:
  name: onprem
  options:
    port: 8080
```"""),

    A(362, provider="onprem", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{PR}#{OP}", f"{PR}#logs-and-stats"],
      user="ERROR: [provider.options.log_level] options.log_level must be DEBUG, INFO, WARNING or ERROR\n\nI wrote log_level: verbose because I want everything",
      steps=[S("search_docs", query="onprem log_level option levels",
               docs=[OPTIONS])],
      final="""`verbose` isn't a level. `log_level` is the minimum level captured from `logging`. Use `DEBUG` to get everything [docs/providers.md#onprem-on-premises].

**In code**
```yaml
provider:
  name: onprem
  options:
    log_level: DEBUG
    capture_output: true
```
`capture_output: true` (the default) also records `print()` and stderr lines. Then filter when you read them:
```bash
pskit logs --level debug -f
```"""),

    A(363, provider="onprem", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=[f"{PR}#{OP}"],
      user="validate say WARNING: [provider.options.prot] unknown option 'prot' is ignored. but host still start on 8080, i want 9000??",
      steps=[S("search_docs", query="onprem options port",
               docs=[OPTIONS])],
      final="""It's a typo: `prot` instead of `port`. Unknown options are ignored, so the host used the default port 8080 [docs/providers.md#onprem-on-premises].

**In code**
```yaml
provider:
  name: onprem
  options:
    port: 9000
```
Run validate again (the warning goes away), then deploy."""),

    A(364, provider="onprem", stage="staging", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{PR}#{OP}", "docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine"],
      user="ERROR: [provider.options.deploy] options.deploy.host is required when method is ssh\n\nbut I saved the server as app-1 already",
      steps=[S("search_docs", query="deploy ssh host saved server",
               docs=[D(PR, OP, start="**The stage remembers its machine.**", end="**The stage remembers its machine.**"),
                     D("docs/resource-guides/onprem/services.md", "deploy-the-functions-to-a-chosen-machine",
                       start="The saved server's host, user, port and login replace those in `options.deploy`",
                       end="The saved server's host, user, port and login replace those in `options.deploy`")])],
      final="""`method: ssh` without `host` and without `server` gives pskit no target. Name the saved server instead of typing the host. Its host, user, port and login then fill in `options.deploy` [docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine].

**In code**
```yaml
provider:
  name: onprem
  options:
    deploy:
      server: app-1
      path: /opt/pskit/shop
```
`method` defaults to `ssh` with a server.

**In studio**
1. **Overview & provider**: set the on-prem deploy to *SSH server* and choose `app-1`, then **Save**."""),

    A(365, provider="onprem", stage="dev", mode="ask", page="Overview", persona="terse_expert",
      sources=[f"{CF}#provider"],
      user="options.deploy.method must be one of local, ssh, docker (scp is an alias of ssh). wanted rsync for speed",
      steps=[S("search_docs", query="deploy method local ssh scp docker",
               docs=[TARGETS])],
      final="""There's no rsync method. `ssh` already sends one `release.tar.gz`, extracts it on the server and restarts the process or unit [docs/providers.md#onprem-on-premises].

```yaml
provider:
  options:
    deploy: {method: ssh, server: app-1}
```"""),

    A(366, provider="onprem", stage="prod", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{PR}#{OP}"],
      user="ERROR: [provider.options.deploy] options.deploy.install: systemd is not used with method docker\n\nwe want the container to come back after a reboot",
      steps=[S("search_docs", query="docker restart policy systemd onprem",
               docs=[TARGETS])],
      final="""`install: systemd` is only for `method: ssh`: it runs the host as a systemd unit. With `method: docker` the container is started by Docker on the server [docs/providers.md#onprem-on-premises].

For "back after a reboot", remove `install` and use the restart policy:

**In code**
```yaml
provider:
  name: onprem
  options:
    deploy:
      method: docker
      server: app-1
      image: pskit/shop:prod
      restart: unless-stopped
```
The Docker service on the server must start at boot for this to work."""),

    A(367, provider="onprem", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=[f"{PR}#{OP}"],
      user="warning say the remote host must already have python3.12 on PATH. my server have only 3.10. what best?",
      steps=[S("search_docs", query="server has no python bundle docker",
               docs=[D(PR, OP, start="When the server has **no Python**", end="When the server has **no Python**")])],
      final="""Don't depend on the server's Python. Two ways [docs/providers.md#onprem-on-premises]:
1. `python: bundle`: pskit fetches a portable CPython at apply and copies it with the app.
2. `method: docker`: the image is `FROM python:<minor>-slim`.

**In code**
```yaml
provider:
  name: onprem
  runtime: python3.12
  options:
    deploy:
      method: ssh
      server: app-1
      python: bundle
```
A third way is installing Python 3.12 on the server with `pskit resources onprem create py312 --service python --version 3.12 --server app-1`, and keeping `python: system`."""),

    A(368, provider="onprem", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{PR}#{OP}"],
      user="WARNING: [provider.options.deploy.sudo] installing Docker on the server uses sudo unless the SSH user is root. Set options.deploy.sudo: true.\n\nI set sudo: false because our security team does not allow sudo",
      steps=[S("search_docs", query="remote docker sudo install docker daemon",
               docs=[D(PR, OP, start="Remote Docker (`method: docker` plus `host`", end="Remote Docker (`method: docker` plus `host`")])],
      final="""The SSH user needs passwordless `sudo` only when Docker must be installed, or when the user can't talk to the daemon [docs/providers.md#onprem-on-premises].

Without sudo, prepare the server once:
1. An admin installs Docker on the server.
2. The SSH user is allowed to use the Docker daemon.
3. Turn off the install step:

**In code**
```yaml
provider:
  name: onprem
  options:
    deploy:
      method: docker
      server: app-1
      sudo: false
      install_docker: false
```
With `install_docker: false`, pskit refuses a server that has no Docker instead of trying to install it."""),

    A(369, provider="onprem", stage="prod", mode="ask", page="YAML", persona="pasted_error",
      sources=[f"{TS}#configuration", f"{PR}#{OP}"],
      user="Error: unresolved variables: env:PSKIT_ADMIN_TOKEN\n\nonly happens on my laptop for dev, CI has the variable",
      steps=[S("search_docs", query="unresolved variables env default",
               docs=[D(TS, "configuration", start="**`unresolved variables: env:FOO`**", end="Set the variable, or give a default"),
                     OPTIONS])],
      final="""`${env:PSKIT_ADMIN_TOKEN}` has no default, so pskit stops when the variable isn't set [docs/troubleshooting.md#configuration]. Add an empty default, as in the on-prem reference [docs/providers.md#onprem-on-premises]:

**In code**
```yaml
provider:
  name: onprem
  options:
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"
```
On your laptop the token is then empty, so `/__pskit/*` has no token check. That's fine for a host on `127.0.0.1`. CI still sets the real token for prod."""),

    A(370, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=[f"{TS}#deploy-and-state"],
      user="i change nothing and deploy again, terraform still want update my onprem host. why?",
      steps=[S("search_docs", query="changed nothing terraform wants to update",
               docs=[D(TS, "deploy-and-state", start="**Changed nothing but Terraform wants to update the function**",
                       end="Inspect `.pskit/<provider>-<stage>/build/`.")])],
      final="""The bundle is built byte for byte the same from the same inputs. So a change means something really changed: a source file, a dependency, or `pskit_manifest.json` [docs/troubleshooting.md#deploy-and-state].

Look in `.pskit/onprem-dev/build/` to find it. Typical causes:
- a file in the project folder that you didn't mean to ship (logs, data);
- an unpinned line in `requirements.txt` that installed a newer version.

**In the terminal**
```bash
pskit plan -s dev
```
The plan shows what changes before you deploy."""),

    A(371, provider="onprem", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=[f"{CF}#variables", f"{CF}#stages-per-stage-overrides"],
      user="ERROR: [provider.options.port] options.port must be an integer from 1 to 65535\n\nI have port: ${env:APP_PORT, 8080} and APP_PORT=9000",
      steps=[S("search_docs", query="variable type env value integer port",
               docs=[D(CF, "variables", start="When a value is exactly one variable", end="When a value is exactly one variable"),
                     D(CF, "stages-per-stage-overrides")])],
      final="""An environment variable is always text, so `port` becomes the string `"9000"` (or `"8080"` from the default), and the port check wants an integer. Only a variable that points at a number keeps that type [docs/configuration.md#variables].

Use real numbers, per stage:

**In code**
```yaml
provider:
  name: onprem
  options:
    port: 8080
stages:
  prod:
    provider:
      options: {port: 9000}
```
Or keep the number in `custom` and refer to it: `port: ${self:custom.port}` with `custom: {port: 9000}`. Both validate."""),

    A(372, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=[f"{TS}#http"],
      user="my react app on localhost:5173 calls my onprem function, browser says CORS error. how fix?",
      steps=[S("search_docs", query="CORS error browser",
               docs=[D(TS, "http", start="**CORS errors in the browser**", end="Preflights are answered by the runtime")])],
      final="""Turn on CORS for the route. The pskit runtime answers the browser's preflight itself [docs/troubleshooting.md#http].

**In code**
```yaml
functions:
  api:
    handler: app.handlers.api
    events:
      - http:
          path: /orders
          method: GET
          cors:
            origins: ["http://localhost:5173"]
```
`cors: true` allows every origin. Listing `origins` limits who can call. Deploy again afterwards."""),

    A(373, provider="onprem", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=[f"{TS}#http"],
      user="curl -X PUT http://192.0.2.10:8080/orders/7 -> 405 Method Not Allowed\nallow: GET, POST",
      steps=[S("search_docs", query="405 method not allowed allow header",
               docs=[D(TS, "http", start="**405 Method Not Allowed**", end="Use `method: ANY` to accept everything.")])],
      final="""The path matched a route, but no route takes `PUT`. The `allow` header lists what does: `GET` and `POST` [docs/troubleshooting.md#http].

**In code**
Add a PUT route:
```yaml
functions:
  update-order:
    handler: app.orders.update
    events:
      - http: PUT /orders/{id}
```
`method: ANY` on one route accepts every method."""),

    A(374, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{PR}#{OP}", f"{TS}#provider-gotchas"],
      user="curl: (7) Failed to connect to 192.0.2.10 port 8080: Connection refused\n\nbut pskit logs and the Test page work fine for this server",
      steps=[S("search_docs", query="connection refused other machines bind 0.0.0.0",
               docs=[D(PR, OP, start="**Ports closed to this machine.**", end="**Ports closed to this machine.**")])],
      final="""The host listens only on `127.0.0.1` on the server, which is the default. pskit itself still works because it goes over SSH to `127.0.0.1:<port>` when it can't reach the port [docs/providers.md#onprem-on-premises].

**In code**
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    port: 8080
```
Deploy again, and allow TCP 8080 in the server's firewall. If you only need access from your own machine, `pskit client tunnel` forwards the port over SSH instead."""),

    A(375, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{PR}#{OP}", f"{TS}#provider-gotchas"],
      user="Our deploy key has a passphrase. pskit deploy over SSH fails with a permission error, although ssh with the same key works when I type the passphrase. What's going on?",
      steps=[S("search_docs", query="ssh key passphrase BatchMode agent",
               docs=[D(PR, OP, start="Remote Docker (`method: docker` plus `host`", end="Remote Docker (`method: docker` plus `host`")])],
      final="""pskit runs `ssh` without prompts: the key must be accepted by `ssh -o BatchMode=yes`. A key with a passphrase can't be used that way [docs/providers.md#onprem-on-premises].

Load the key into the SSH agent and let pskit use the agent:

**In the terminal**
```bash
ssh-add ~/.ssh/deploy_key
pskit deploy -s dev
```

**In code**
Leave out `pem`, so the agent's key is used:
```yaml
provider:
  name: onprem
  options:
    deploy:
      method: ssh
      host: 192.0.2.10
      user: deploy
```"""),

    A(376, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=[f"{PR}#{OP}"],
      user="my server is arch linux with pacman. docker method can install docker there?",
      steps=[S("search_docs", query="install docker package manager apt dnf yum apk",
               docs=[D(PR, OP, start="`pem` / `identity_file` (a key file); nothing", end="is reported and left unchanged.")])],
      final="""No. pskit installs Docker only with apt, dnf, yum or apk. A server with another package manager is reported and left unchanged [docs/providers.md#onprem-on-premises].

So install Docker yourself with `pacman`, start it, and then deploy. To be sure pskit never tries to install it:

**In code**
```yaml
provider:
  name: onprem
  options:
    deploy:
      method: docker
      server: app-1
      install_docker: false
```"""),

    A(377, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{TS}#provider-gotchas"],
      user="i deployed a second project on my pc with onprem and now the first project stopped answering. why?",
      steps=[S("search_docs", query="two onprem services same machine port",
               docs=[GOTCHA])],
      final="""Each on-prem service is its own process, so each needs its own `options.port` [docs/troubleshooting.md#provider-gotchas]. Both used the default 8080.

**In code**
In the second project:
```yaml
provider:
  name: onprem
  options:
    port: 8081
```
Deploy the second project again, then the first, so each owns its port."""),

    A(378, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{PR}#{OP}", f"{TS}#installation-and-tooling"],
      user="pip install failed while vendoring dependencies\n\ndeploying from my x86 laptop to an arm64 server (method ssh), package is a compiled one",
      steps=[S("search_docs", query="vendoring wheels remote host architecture",
               docs=[D(PR, OP, start="- **Dependencies:**", end="- **Dependencies:**"),
                     D(TS, "installation-and-tooling", start="**`pip install failed while vendoring dependencies`**",
                       end="for pure-Python packages, check that they ship a wheel at all.")])],
      final="""For a remote host pskit downloads wheels for the target's OS and architecture, not your laptop's. Here pip found no arm64 Linux wheel of that package [docs/providers.md#onprem-on-premises].

Fixes [docs/troubleshooting.md#installation-and-tooling]:
1. Pin a version that publishes manylinux arm64 wheels.
2. Pass extra pip flags with `package.pip_args`.

**In code**
Tell pskit the target, so it doesn't have to guess:
```yaml
provider:
  name: onprem
  architecture: arm64
  options:
    deploy:
      method: ssh
      server: app-1
      target_arch: arm64
```"""),

    A(379, provider="onprem", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{CF}#provider", f"{PR}#{OP}"],
      user="Our pskit.yml has iam.statements allowing sqs:SendMessage from the AWS days. What happens to them on the on-prem host? Validate says nothing.",
      steps=[S("search_docs", query="iam statements onprem ignored",
               docs=[D(CF, "provider", start="| `iam.statements` |", end="| `iam.statements` |"),
                     D(PR, OP, start="**Limits:**", words=20)])],
      final="""They do nothing on-prem: the on-prem provider has no IAM mapping [docs/providers.md#onprem-on-premises]. `iam.statements` are AWS-style permissions for the clouds that map them [docs/configuration.md#provider].

On-prem, access comes from what the host process can reach:
- for an SQS queue in AWS, the credentials the queue driver uses;
- for built-in queues, nothing extra.

Keep the statements for the AWS deploys. They don't hurt the on-prem one."""),

    A(380, provider="onprem", stage="dev", mode="ask", page="Setup", persona="detailed_spec",
      sources=[f"{TS}#deploy-and-state", f"{CF}#state-remote-terraform-backend"],
      user="Two of us deploy the same on-prem dev stage, each from our own laptop. Now Terraform on my laptop seems to know nothing about my colleague's deploy. Is that expected?",
      steps=[S("search_docs", query="state another machine deploy conflicts",
               docs=[D(TS, "deploy-and-state", start="**State conflicts", end="`pskit tf -- init -migrate-state`."),
                     D(CF, "state-remote-terraform-backend", end="is git-ignored. For teams and CI, use a remote backend:")])],
      final="""Yes. By default state lives in `.pskit/onprem-dev/terraform.tfstate` on each laptop, so each of you has your own [docs/configuration.md#state-remote-terraform-backend].

Options:
1. **Shared state**: put `provider.state` on a remote backend you both reach, then move the current state there with `pskit tf -- init -migrate-state` [docs/troubleshooting.md#deploy-and-state].
2. **One deployer**: let one person or a CI job deploy the stage.
3. **One stage each**, e.g. `dev-asha` and `dev-ben`, each on its own port or server.

To share saved servers and where the stage was deployed, use `pskit settings export` / `import`."""),
]
