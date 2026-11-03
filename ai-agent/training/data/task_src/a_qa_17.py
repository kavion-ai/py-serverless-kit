"""Category A (docs Q&A and how-to), batch 17: on-prem Network map page, firewall rules, and the Setup & credentials
page for on-prem deploys (checks, SSH connection, Terraform/OpenTofu, settings). Hand-written; assembled by
tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


SV = "docs/resource-guides/onprem/services.md"
WHERE = "where-a-server-is-used-and-how-the-servers-connect"
NET = "docs/onprem-network.md"
NET0 = "network-and-firewall-rules-on-premises"
NET3 = "3-deploy-to-one-server-method-ssh-docker-or---server-name"
NET4 = "4-functions-on-several-servers-provideroptionsplacement"
ST = "docs/studio.md"
SETUP = "setup-logs-and-provider-differences"
PR = "docs/providers.md"
OP = "onprem-on-premises"
TS = "docs/troubleshooting.md"
CLI = "docs/cli.md"

MAP = D(SV, WHERE, start="The **Network map** page draws", end="from local files only.")

CONVERSATIONS = [
    A(321, provider="onprem", stage="dev", mode="ask", page="Network map", persona="beginner",
      sources=[f"{SV}#{WHERE}", f"{NET}#{NET0}"],
      user="on the network map some lines are solid, some are dashed and some dotted. what does that mean?",
      steps=[S("search_docs", query="network map solid dashed dotted lines",
               docs=[MAP, D(NET, NET0, start="**Legend:**", end="**Legend:**")])],
      final="""The line style tells you how much the connection matters [docs/resource-guides/onprem/services.md#where-a-server-is-used-and-how-the-servers-connect]:
- **solid**: required. It doesn't work without it.
- **dashed**: needed only for a feature you use.
- **dotted**: optional. If it's blocked, pskit falls back to an SSH tunnel.

Click a server on the map to see each port it must accept or open, and why.

**In studio**
1. **Network map**: the *required*, *feature* and *optional* checkboxes at the top show or hide each kind of line.
2. Click a machine to open its *Inbound — accept* and *Outbound — open* tables."""),

    A(322, provider="onprem", stage="dev", mode="ask", page="Network map", persona="informal_non_native",
      sources=[f"{SV}#servers-several-machines", f"{SV}#{WHERE}"],
      user="network map page is empty, it say no servers and no connections yet. what i must do?",
      steps=[S("search_docs", query="network map empty save server",
               docs=[D(SV, "servers-several-machines", end="Machine**, the shell and the terminal."), MAP])],
      final="""Nothing is wrong. The map only draws servers pskit knows about, and connections that come from what you deploy or create on them [docs/resource-guides/onprem/services.md#where-a-server-is-used-and-how-the-servers-connect].

**In studio**
1. **Resources > On-prem services > Servers > + Add server**: name, host, user, port, *Log in with*.
2. Use the server: pick it in **Deploy > Machine** and deploy, or create a cluster, a load balancer or a service on it.
3. Go back to **Network map** and press **Refresh**.

**In the terminal**
```bash
pskit resources onprem servers add app-1 --ssh deploy@192.0.2.10 --pem ~/.ssh/app-1.pem
pskit deploy --server app-1
```
[docs/resource-guides/onprem/services.md#servers-several-machines]"""),

    A(323, provider="onprem", stage="prod", mode="ask", page="Network map", persona="detailed_spec",
      sources=[f"{SV}#{WHERE}"],
      user="Before I open the Network map for our prod project: does that page connect to the servers or scan our network to draw the lines? Our security team must approve any scanning.",
      steps=[S("search_docs", query="network map how it works scans servers local files",
               docs=[MAP])],
      final="""No. The Network map doesn't scan anything. It reads the same rules as `pskit firewall`, from local files only: your `pskit.yml` and what pskit saved about servers, deploys, clusters, load balancers and services [docs/resource-guides/onprem/services.md#where-a-server-is-used-and-how-the-servers-connect].

The lines show the connections each server *needs*, not traffic pskit measured. To check that a port is really open, use the tools you already have, or **Resources > On-prem services > Details > Check web UI** for a one-click service's UI."""),

    A(324, provider="onprem", stage="prod", mode="ask", page="Network map", persona="terse_expert",
      sources=[f"{NET}#{NET0}"],
      user="same rules as the network map, but per server and as json for ansible. command?",
      steps=[S("search_docs", query="pskit firewall json per server",
               docs=[D(NET, NET0, start="**You do not have to work these out by hand.**",
                       end="cluster and load balancer pages) and in each job's output:")])],
      final="""**In the terminal**
```bash
pskit firewall --server app-1 --json
```
Leave out `--server` to get every server of the project. Without `--json` it prints the rules with `ufw` commands [docs/onprem-network.md#network-and-firewall-rules-on-premises]."""),

    A(325, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{NET}#{NET0}", f"{NET}#{NET3}"],
      user="deploy output ends with:\nFirewall - deploy shop/prod on app-1 (open these; docs/onprem-network.md):\n  app-1 (192.0.2.10)\n    [REQUIRED] inbound  TCP 8080  from users\ndo i have to do this, or did pskit open it?",
      steps=[S("search_docs", query="firewall rules printed after deploy required inbound users",
               docs=[D(NET, NET0, start="**You do not have to work these out by hand.**",
                       end="cluster and load balancer pages) and in each job's output:"),
                     D(NET, NET3, start="**After deploy (running)**", end="A host bound to `127.0.0.1` is only reachable")])],
      final="""You do it. pskit *prints* the rules a step made necessary, with ready `ufw` commands, so you can apply them on your firewall [docs/onprem-network.md#network-and-firewall-rules-on-premises].

This rule is **REQUIRED**: users call your HTTP routes on port 8080 of app-1. Also set `options.host: 0.0.0.0`, so the host listens on the network and not only on `127.0.0.1` [docs/onprem-network.md#3-deploy-to-one-server-method-ssh-docker-or---server-name].

The port from your own machine to 8080 is optional: logs and tests go through SSH when it's closed.

To see all rules again later:
```bash
pskit firewall --server app-1
```"""),

    A(326, provider="onprem", stage="dev", mode="ask", page="Network map", persona="beginner",
      sources=[f"{SV}#{WHERE}"],
      user="where on the network map can i see which ports server db-1 needs and what it is used for?",
      steps=[S("search_docs", query="network map click server inbound outbound ports used in",
               docs=[MAP, D(SV, WHERE, end="`pskit resources onprem servers usage [NAME] [--json]`.")])],
      final="""Click the server on the map. You get its inbound and outbound ports, why each one is needed, and where the server is used [docs/resource-guides/onprem/services.md#where-a-server-is-used-and-how-the-servers-connect].

**In studio**
1. Open **Network map**.
2. Click **db-1** on the map, or in the *Machines* list next to it.
3. Read *Inbound — accept* and *Outbound — open*. *Used in* lists the functions, services and replicas on db-1.
4. **All machines** goes back to the full map.

**In the terminal**
```bash
pskit firewall --server db-1
pskit resources onprem servers usage db-1
```"""),

    A(327, provider="onprem", stage="prod", mode="ask", page="Network map", persona="informal_non_native",
      sources=[f"{NET}#{NET4}"],
      user="i split functions in 2 groups, api on app-1 and resize on gpu-box. network map now show line between them both ways. really need?",
      steps=[S("search_docs", query="placement groups ports between group hosts",
               docs=[D(NET, NET4, end="still keep these ports to the servers' network.")])],
      final="""Yes, it's required. Each group is its own host and the groups call each other directly, so every group host must reach the port of every other group host: `invoke()`, routes of the other group, workflow steps, queues and buckets owned by the other group [docs/onprem-network.md#4-functions-on-several-servers-provideroptionsplacement].

So open:
- on gpu-box: TCP 8080 (or the group's `port`) from app-1;
- on app-1: its port from gpu-box. The default group also gets the logs and counts of the other groups.

Calls between groups carry a shared token, but keep these ports limited to your servers' network."""),

    A(328, provider="onprem", stage="prod", mode="ask", page="Network map", persona="aws_migrator",
      sources=[f"{NET}#{NET0}", f"{NET}#the-machines"],
      user="On AWS, Terraform created our security groups. Moving to on-prem servers: does pskit configure the firewalls on the machines, or is that on us?",
      steps=[S("search_docs", query="does pskit open firewall ports ufw",
               docs=[D(NET, NET0, start="**You do not have to work these out by hand.**",
                       end="cluster and load balancer pages) and in each job's output:")])],
      final="""It's on you. pskit doesn't change firewalls. It tells you exactly what to open: each step (deploy, cluster create / join, load balancer, service create) prints the rules it made necessary, with your servers' names, addresses and `ufw` commands [docs/onprem-network.md#network-and-firewall-rules-on-premises].

**In the terminal**
```bash
pskit firewall
pskit firewall --json
```
The first lists everything the project needs now, per server. The second is for your own automation.

**In studio**
1. **Network map**: every server with its inbound and outbound connections.
2. **Deploy > Firewall**: the ports each server must allow.

On cloud VMs, the provider's firewall (security group, NSG, VPC firewall) needs the same rules."""),

    A(329, provider="onprem", stage="dev", mode="ask", page="Setup", persona="informal_non_native",
      sources=[f"{ST}#{SETUP}", f"{TS}#provider-gotchas"],
      user="setup page show red cross for ssh and scp. i am on windows and want deploy to my linux server",
      steps=[S("search_docs", query="setup checks ssh scp missing windows onprem",
               docs=[D(ST, SETUP, end="- test the SSH connection of an on-prem deploy.")])],
      final="""A deploy to a server copies the release with `scp` and starts it over `ssh`, so both must be on your PC. The Setup check shows the download link and the steps for your OS [docs/studio.md#setup-logs-and-provider-differences].

**In studio**
1. **Setup & credentials**: pick *Windows* under *Operating system*.
2. Open the red row and follow its install steps (Windows has an OpenSSH client).
3. Open a new terminal, restart `pskit studio`, then press **Check again**.

**In the terminal**
```bash
pskit doctor -p onprem
```
It runs the same checks and prints the same fix."""),

    A(330, provider="onprem", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=[f"{ST}#{SETUP}", f"{CLI}#pskit-doctor"],
      user="before my first deploy over ssh, how can i check that pskit can really log in to the server?",
      steps=[S("search_docs", query="test ssh connection onprem deploy",
               docs=[D(ST, SETUP, end="- test the SSH connection of an on-prem deploy."),
                     D(CLI, "pskit-doctor", end="timeout. It doesn't take the common project options.")])],
      final="""Use the studio's SSH test. `pskit doctor` only checks your machine (ssh/scp, host and key are set); it doesn't connect anywhere [docs/cli.md#pskit-doctor].

**In studio**
1. **Setup & credentials > On-premises connection**: choose *SSH server*, fill in host, user, port and the key file.
2. In **Checks**, press **Test connection** on the SSH row [docs/studio.md#setup-logs-and-provider-differences].

**In the terminal**
For a saved server, log in once and see what it has:
```bash
pskit resources onprem servers test app-1
```"""),

    A(331, provider="onprem", stage="dev", mode="ask", page="Setup", persona="detailed_spec",
      sources=[f"{ST}#what-you-can-do", f"{ST}#{SETUP}"],
      user="Setup & credentials has an 'On-premises connection' box and the Overview page has deploy settings too. Which settings are where, and do both write the same thing?",
      steps=[S("search_docs", query="on-premises connection setup overview deploy method host port",
               docs=[D(ST, "what-you-can-do", start="| **Overview & provider** |", end="| **Overview & provider** |"),
                     D(ST, SETUP, end="- test the SSH connection of an on-prem deploy.")])],
      final="""Both edit `provider.options.deploy` in the same draft.

- **Setup & credentials > On-premises connection**: only what the connection test needs. *Where the host runs* (*This machine*, *SSH server* or *Docker*), plus host, user, port, key file, `known_hosts`, `sudo` and `docker_host`.
- **Overview & provider**: everything else for on-prem. Deploy method, host, port, admin token, services and host tuning, plus remote path, install mode and image [docs/studio.md#what-you-can-do].

Nothing is written until you press **Save**. Then `pskit.yml` has one `provider.options.deploy` block, whichever page you used."""),

    A(332, provider="onprem", stage="dev", mode="ask", page="Setup", persona="aws_migrator",
      sources=[f"{PR}#{OP}"],
      user="For AWS I keep keys in ~/.aws. What credentials does pskit need for an on-prem deploy, for local, SSH and Docker?",
      steps=[S("search_docs", query="onprem credentials pem ssh agent docker",
               docs=[D(PR, OP, start="- **Credentials:**", end="- **Credentials:**")])],
      final="""No cloud credentials. Only an SSH login for remote targets [docs/providers.md#onprem-on-premises]:

| Method | What it needs |
|---|---|
| `local` | nothing |
| `ssh` / `scp` | a `.pem` (`deploy.pem` or `identity_file`) or the SSH agent. `pskit deploy` asks for the `.pem` in a terminal; Enter keeps the agent |
| `docker` on a server | a `.pem`, plus OpenSSH and a Docker CLI on your laptop to build the image |

**In code**
```yaml
provider:
  name: onprem
  options:
    deploy:
      method: ssh
      host: 192.0.2.10
      user: deploy
      pem: ${env:PSKIT_SSH_KEY}
```
`PSKIT_SSH_KEY` holds the path of the key file."""),

    A(333, provider="onprem", stage="dev", mode="ask", page="Setup", persona="pasted_error",
      sources=[f"{PR}#{OP}"],
      user="WARNING: [provider.runtime] the host runs with this interpreter (python3.12), not python3.11. Use the same Python for `pskit deploy` and the functions, or set options.deploy.python: bundle.\n\nmethod is local. do i have to care?",
      steps=[S("search_docs", query="local host runs with this interpreter runtime warning",
               docs=[D(PR, OP, start="**Limits:**", end="**Limits:**")])],
      final="""It's only a warning. With `method: local` the host runs with the Python that runs `pskit` (3.12 here), not the `runtime: python3.11` you pinned [docs/providers.md#onprem-on-premises]. Your functions run on 3.12.

Pick one:
1. Remove `provider.runtime`, or set it to `python3.12`, so the config says what really runs.
2. Run pskit from a 3.11 environment if you need 3.11.
3. Set `options.deploy.python: bundle`, as the warning says, to ship that interpreter with the host."""),

    A(334, provider="onprem", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=[f"{PR}#{OP}", f"{TS}#installation-and-tooling"],
      user="pskit doctor says terraform is missing. i only deploy to my own pc with onprem, do i really need terraform?",
      steps=[S("search_docs", query="onprem terraform needed terraform_data",
               docs=[D(PR, OP, start="- **Terraform:**", end="- **Terraform:**"),
                     D(TS, "installation-and-tooling", start="**`Neither terraform nor tofu was found on PATH`**",
                       end="or `provider.terraform.binary`) at the binary.")])],
      final="""Yes. On-prem deploys run through Terraform too, but they only use Terraform's built-in `terraform_data`, so there's no provider plugin to download [docs/providers.md#onprem-on-premises]. You don't need Terraform for `pskit dev` or `pskit invoke`.

Install Terraform 1.5 or later, or OpenTofu [docs/troubleshooting.md#installation-and-tooling].

**In studio**
1. **Setup & credentials**: open the *Terraform (or OpenTofu)* row and follow the steps for your OS.
2. Press **Check again**.

**In the terminal**
```bash
pskit doctor -p onprem
```"""),

    A(335, provider="onprem", stage="dev", mode="ask", page="Setup", persona="informal_non_native",
      sources=[f"{CLI}#environment-variables", "docs/configuration.md#terraform"],
      user="my company use opentofu not terraform. onprem deploy can work with tofu?",
      steps=[S("search_docs", query="opentofu instead of terraform binary",
               docs=[D(TS, "faq", start="**Can I use OpenTofu?**", end="`provider.terraform.binary: tofu`."),
                     D("docs/configuration.md", "terraform")])],
      final="""Yes. pskit looks for `terraform`, then `tofu`. To choose it yourself [docs/configuration.md#terraform]:

**In the terminal**
```bash
export PSKIT_TERRAFORM_BIN=tofu
pskit deploy -s dev
```

**In code**
```yaml
provider:
  name: onprem
  terraform:
    binary: tofu
```"""),

    A(336, provider="onprem", stage="dev", mode="ask", page="Setup", persona="detailed_spec",
      sources=[f"{PR}#{OP}", f"{NET}#1-always-the-admin-machine-reaches-every-server-over-ssh"],
      user="Our admin machine has no internet access. Will an on-prem deploy over SSH still work, or does Terraform or pskit download things during deploy?",
      steps=[S("search_docs", query="air-gapped onprem deploy downloads terraform plugin",
               docs=[D(PR, OP, start="- **Terraform:**", end="- **Terraform:**"),
                     D(NET, "1-always-the-admin-machine-reaches-every-server-over-ssh", start="| 🟥 | Admin machine, **outbound** |",
                       end="pskit copies the function image itself over SSH, so no registry is needed.")])],
      final="""Terraform itself needs nothing: on-prem uses the built-in `terraform_data`, so there's no plugin download [docs/providers.md#onprem-on-premises].

pskit itself may go online [docs/onprem-network.md#1-always-the-admin-machine-reaches-every-server-over-ssh]:
- **PyPI / npm** while packaging your `requirements.txt` dependencies;
- **`python: bundle`**: the portable CPython. Use `python_home` (a tree you already have) or `python_url` + `python_sha256` (an internal mirror);
- **Docker base images** for `method: docker`.

With no dependencies to fetch and `python: system` on the server, an SSH deploy only needs port 22 to the server."""),

    A(337, provider="onprem", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=[f"{ST}#{SETUP}"],
      user="the studio has a Browse button for my ssh key. does the studio read my private key file then?",
      steps=[S("search_docs", query="private key browse studio reads file",
               docs=[D(ST, SETUP, start="- **Private key**", end="- **Private key**")])],
      final="""No. **Browse…** only lists folders and files on the machine running studio, starting in `~/.ssh`, with names and sizes. File contents are never read [docs/studio.md#setup-logs-and-provider-differences]. The studio saves just the path in `provider.options.deploy`. `ssh` reads the key when you deploy."""),

    A(338, provider="onprem", stage="dev", mode="ask", page="Setup", persona="pasted_error",
      sources=[f"{TS}#installation-and-tooling"],
      user="deploy from windows fails while unpacking the bundled python:\n[WinError 206] The filename or extension is too long\nproject is in C:\\Users\\me\\Documents\\work\\clients\\shop\\services\\orders-api",
      steps=[S("search_docs", query="WinError 206 path too long windows bundled CPython",
               docs=[D(TS, "installation-and-tooling", start="**Paths too long on Windows**",
                       end="Or keep the project in a short path such as `C:\\src\\app`.")])],
      final="""Windows hit its path-length limit. A bundled CPython has deep folders, and your project path is long too [docs/troubleshooting.md#installation-and-tooling].

**In the terminal**
Fix it once for the whole system, in an admin PowerShell:
```powershell
New-ItemProperty -Path HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
```
Or move the project to a short path such as `C:\\src\\orders-api`, then run the deploy again."""),

    A(339, provider="onprem", stage="dev", mode="ask", page="Setup", persona="terse_expert",
      sources=["docs/cli.md#pskit-settings"],
      user="pskit settings export: does it carry the terraform state of my onprem stages?",
      steps=[S("search_docs", query="settings export terraform state included",
               docs=[D(CLI, "pskit-settings", start="| `.pskit/onprem-<stage>/onprem_deployed.json`", end="folder, or on another OS, after the import.")])],
      final="""No, and on-prem doesn't need it. The file carries `onprem_deployed.json` and `deployment.json` of each on-prem stage: where it was last deployed, with its admin token. So `pskit logs`, `test`, `info` and the studio reach the host at once after the import [docs/cli.md#pskit-settings].

**In the terminal**
```bash
pskit settings export -o shop.pskit-settings
pskit settings import shop.pskit-settings --dry-run
```

**In studio**
1. **Setup & credentials > Move settings to another machine** (or **⇅ Settings** in the header).

Send the passphrase by another channel than the file."""),

    A(340, provider="onprem", stage="dev", mode="ask", page="Setup", persona="informal_non_native",
      sources=[f"{CLI}#pskit-doctor"],
      user="doctor for onprem with docker method, what it check? my docker desktop is closed now",
      steps=[S("search_docs", query="doctor onprem docker method checks daemon",
               docs=[D(CLI, "pskit-doctor", end="timeout. It doesn't take the common project options.")])],
      final="""For `method: docker` it checks the Docker CLI **and a running daemon** [docs/cli.md#pskit-doctor]. With Docker Desktop closed, that row fails, and `pskit doctor` exits with 1 when something required is missing. The image is built on your machine, so start Docker Desktop before you deploy.

**In the terminal**
```bash
pskit doctor -p onprem
```

**In studio**
1. **Setup & credentials** runs the same checks.
2. Start Docker Desktop, then press **Check again**."""),
]
