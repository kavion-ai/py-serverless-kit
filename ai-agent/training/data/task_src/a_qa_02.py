"""Category A (docs Q&A and how-to), batch 2: on premises (clusters, load balancers, placement, servers, network).
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(21, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="beginner",
      sources=["docs/cluster.md#scaling-cluster-on-premises", "docs/cluster.md#set-up"],
      user="my api runs on one server and it gets slow at lunch time. can pskit spread it over 3 machines?",
      steps=[S("search_docs", query="run functions on several servers scaling cluster",
               docs=[D("docs/cluster.md", "scaling-cluster-on-premises", end="watches capacity.", words=300),
                     D("docs/cluster.md", "set-up", words=120)])],
      final="""Yes. Create a **scaling cluster**: one master server plus joined servers, run by Docker Swarm, Kubernetes (k3s) or Nomad. pskit installs everything over SSH and copies the function image to every server, so you don't need a container registry [docs/cluster.md#scaling-cluster-on-premises].

**In studio**
1. Save the three machines once: **Resources > On-prem services > Servers > + Add server** (for example app-1, app-2, app-3).
2. Open **Scaling cluster** and click **+ New cluster**. Pick the *Orchestrator* (Swarm is the simplest) and app-1 as *Master server*.
3. Click **+ Join server** for app-2 and app-3.
4. Turn on *Deploy this project's functions to prod* and click **Save**.
5. Open **Deploy**, choose *Run on: Scaling cluster* and click **Deploy**.

**In the terminal**
```bash
pskit resources onprem servers add app-1 --ssh root@192.0.2.10 --pem ~/.ssh/app.pem
pskit cluster create prod -o swarm --master app-1
pskit cluster join prod app-2
pskit cluster join prod app-3
pskit deploy --cluster prod
```

**In code**
```yaml
provider:
  name: onprem
  options:
    cluster: {name: prod, replicas: 3}
    port: 8080
```

Your handler code doesn't change. Before you start: Docker must run on your own machine (it builds the image), and the servers need Linux with SSH and root or passwordless `sudo` [docs/cluster.md#set-up]."""),

    A(22, provider="onprem", stage="staging", mode="auto", page="Cluster", persona="terse_expert",
      sources=["docs/cluster.md#nomad-does-not-need-a-load-balancer"],
      user="nomad cluster. does deploy fail without an LB in front?",
      steps=[S("search_docs", query="nomad cluster load balancer required deploy health",
               docs=[D("docs/cluster.md", "nomad-does-not-need-a-load-balancer", end="HAProxy or Traefik in front.")])],
      final="""No. On Nomad, `pskit deploy` waits until the main replica answers `/__pskit/health` on the master, at `127.0.0.1:<port>`. That check doesn't go through a load balancer, so the deploy succeeds without one [docs/cluster.md#nomad-does-not-need-a-load-balancer].

How traffic works without a load balancer:
- Requests to the master's port go to the main replica.
- Requests to another server's port go to that server's web replica.

If you want one URL for all servers, add pskit's load balancer on one more server, or put your own nginx, HAProxy or Traefik in front:
```bash
pskit cluster balancer set staging lb-1
```"""),

    A(23, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="informal_non_native",
      sources=["docs/load-balancers.md#the-six-algorithms", "docs/load-balancers.md#create-one-and-put-projects-on-it"],
      user="my app keep login session in memory. lb send user to other server and he is logout. which algorithm i choose?",
      steps=[S("search_docs", query="load balancer algorithm sticky session",
               docs=[D("docs/load-balancers.md", "the-six-algorithms", start="| Algorithm | Kind |",
                       end="can favor one fast server until it slows down |")]),
             S("search_docs", query="project balancer algorithm pskit.yml route",
               docs=[D("docs/load-balancers.md", "create-one-and-put-projects-on-it", start="A project names it in", end="redirects to `/shop/`.", words=200)])],
      final="""Use `sticky_round_robin`. The user's first request picks a server, and a cookie keeps the session on that server [docs/load-balancers.md#the-six-algorithms]. If your clients can't keep cookies (devices, API clients), use `ip_hash` instead.

Two things to know: busy users can make the load uneven, and sessions still move when a server joins or leaves.

**In studio**
1. Open **Load balancers**.
2. For a new one, click **+ Create load balancer** and pick sticky round robin under *How it spreads requests*.
3. For only this project's route, change *Algorithm for this route* on the load balancer and save.

**In the terminal**
```bash
pskit lb update edge --algorithm sticky_round_robin
```

**In code** (only this project's route)
```yaml
provider:
  name: onprem
  options:
    balancer: {name: edge, algorithm: sticky_round_robin}
```
The next `pskit deploy` updates the route [docs/load-balancers.md#create-one-and-put-projects-on-it]."""),

    A(24, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="detailed_spec",
      sources=["docs/cluster.md#the-master-and-requests"],
      user="We run a Docker Swarm cluster. The master also holds our schedules and the built-in queues, and under load the HTTP traffic competes with that. Can we keep requests off the master? And what happens if both workers go down?",
      steps=[S("search_docs", query="cluster master serves requests backup",
               docs=[D("docs/cluster.md", "the-master-and-requests", end="users who call the master's own address still reach it.", words=400)])],
      final="""Yes. Turn **Master serves requests** off. On Swarm it is on by default [docs/cluster.md#the-master-and-requests].

With it off:
- Load balancers list the master only as a `backup`. It gets traffic only while every other server is down, so if both workers fail, the master takes the requests.
- Swarm also keeps web replicas off the master while another server can run them.
- Users who call the master's own address still reach it. The setting only affects load balancers.

**In studio**
1. Open **Scaling cluster** and select the cluster.
2. Turn off the *Master serves requests* switch. The load balancers are updated right away.
3. Open **Deploy** and deploy again, so the web replicas move off the master.

**In the terminal**
```bash
pskit cluster set prod --no-master-serves
pskit deploy --cluster prod
```
You need the second deploy on Swarm and k3s, because replicas only move at the next `pskit deploy`."""),

    A(25, provider="onprem", stage="prod", mode="auto", page="Cluster", persona="terse_expert",
      sources=["docs/cluster.md#live-requests-which-server-handled-what"],
      user="terminal only: show me which server answered each request on cluster prod",
      steps=[S("search_docs", query="cluster requests which server handled request",
               docs=[D("docs/cluster.md", "live-requests-which-server-handled-what", start="```bash", words=300,
                       end="(admin token required).")])],
      final="""**In the terminal**
1. Follow the requests live: time, server, replica, status, duration and function. A balance table with each server's share of HTTP comes first:
```bash
pskit cluster requests prod --follow
```
2. If several deployments share the cluster, pick one:
```bash
pskit cluster requests prod --follow --stack pskit-shop-prod
```
3. If you use the cluster's own load balancer, its access log shows the upstream server for each request:
```bash
pskit cluster balancer logs prod -n 200
```
[docs/cluster.md#live-requests-which-server-handled-what]"""),

    A(26, provider="onprem", stage="dev", mode="ask", page="Network map", persona="beginner",
      sources=["docs/resource-guides/onprem/services.md#where-a-server-is-used-and-how-the-servers-connect",
               "docs/onprem-network.md#network-and-firewall-rules-on-premises"],
      user="what is this network map page? do i have to do something here?",
      steps=[S("search_docs", query="network map page servers connections",
               docs=[D("docs/resource-guides/onprem/services.md", "where-a-server-is-used-and-how-the-servers-connect",
                       start="The **Network map** page", end="from local files only.")]),
             S("search_docs", query="firewall rules pskit firewall",
               docs=[D("docs/onprem-network.md", "network-and-firewall-rules-on-premises", start="**You do not have to work these out by hand.**",
                       end="in each job's output:")])],
      final="""You don't have to do anything there. It's a map that helps you open the right firewall ports.

The **Network map** draws every saved server and the connections it must accept (inbound) and open (outbound): SSH from this machine, callers of your functions, cluster ports, load balancer to servers, functions to services, and downloads [docs/resource-guides/onprem/services.md#where-a-server-is-used-and-how-the-servers-connect].
- Solid line: required
- Dashed line: needed for a feature
- Dotted line: optional (pskit falls back to an SSH tunnel)

**In studio**
1. Open **Network map**.
2. Click a server to see its inbound and outbound ports, why each one is needed, and where the server is used.

**In the terminal**
```bash
pskit firewall
pskit firewall --server app-1
```
`pskit firewall` lists the same rules per server, and deploy, cluster and load balancer commands print them too [docs/onprem-network.md#network-and-firewall-rules-on-premises]. The map reads local files only and doesn't contact your servers."""),

    A(27, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="pasted_error",
      sources=["docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full"],
      user="FULL: all 2 server(s) are over a capacity limit; 2 replica(s) cannot be placed. Add a server: pskit cluster join prod SERVER\n\nwhat now??",
      steps=[S("search_docs", query="cluster full replicas cannot be placed add server",
               docs=[D("docs/cluster.md", "monitor-scale-and-add-servers-when-it-is-full", start="The cluster counts as **full**",
                       end="so its replicas move to the others.")])],
      final="""Your cluster is full. Both servers are over a limit (by default CPU 85 %, memory 85 %, disk 90 %), and the orchestrator can't find room for 2 replicas [docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full]. Add a server, then raise the replicas if you want more copies.

**In studio**
1. Open **Scaling cluster** and click **+ Join server**. You can save a new server in the same dialog.
2. When it shows *ready*, change the replica count of the deployment and click **Scale**.

**In the terminal**
```bash
pskit cluster join prod app-3
pskit cluster status prod
pskit cluster scale prod --replicas 6
```

**In code**
`pskit cluster scale` lasts only until the next deploy. To keep the count, set it in pskit.yml:
```yaml
provider:
  name: onprem
  options:
    cluster: {name: prod, replicas: 6}
```
You can join a server while the functions keep running."""),

    A(28, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="detailed_spec",
      sources=["docs/cluster.md#alert-devops-optional"],
      user="Our ops team wants a message in their Teams channel when the cluster runs out of capacity. We'd also like to send a test alert before this really happens. Where is that set up?",
      steps=[S("search_docs", query="cluster capacity alert webhook teams test",
               docs=[D("docs/cluster.md", "alert-devops-optional", words=60),
                     D("docs/cluster.md", "alert-devops-optional", start="**Who checks?**", end="exits with status 3 when the cluster is full.")])],
      final="""Use the cluster alert with a webhook. When the cluster is full, pskit POSTs to your Teams (or Slack, Google Chat, any URL) webhook at most once per cooldown (default 30 minutes) [docs/cluster.md#alert-devops-optional]. You can also call one of your own deployed functions.

**In studio**
1. Open **Scaling cluster** and select the cluster.
2. In the alert settings, paste the Teams URL in *Webhook (optional)* and set *Cooldown (minutes)*.
3. Optionally, adjust *CPU full at %*, *Memory full at %* and *Disk full at %*.
4. Send a test alert with the test button.

**In the terminal**
```bash
pskit cluster alerts prod --webhook https://hooks.example.com/teams-ops --cooldown 30
pskit cluster alerts prod --test
pskit cluster watch prod --interval 60
```

Checks only run where pskit runs: while the studio is open with *Watch while the studio runs* on, or with `pskit cluster watch` on an always-on machine (or `pskit cluster check prod` from cron, which exits with status 3 when the cluster is full). Store the real webhook URL outside git if it holds a secret token."""),

    A(29, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/placement.md#functions-on-several-servers-on-premises", "docs/placement.md#requirements-global-plus-per-function"],
      user="Two of our functions, resize and ocr, need the GPU machine gpu-box. Everything else should stay on app-1. Can that be one project, and does gpu-box then install the API's dependencies too?",
      steps=[S("search_docs", query="functions on different servers placement groups",
               docs=[D("docs/placement.md", "functions-on-several-servers-on-premises", end="each function shows where it runs.")]),
             S("search_docs", query="placement requirements per server",
               docs=[D("docs/placement.md", "requirements-global-plus-per-function")])],
      final="""Yes, with **placement**. Each group of functions runs on its own server, and the groups work together as one project [docs/placement.md#functions-on-several-servers-on-premises].

gpu-box installs the project's global `requirements.txt`, plus only the `requirements.txt` of its own functions' folders, never those of functions placed elsewhere [docs/placement.md#requirements-global-plus-per-function].

**In code**
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    placement:
      default: api
      groups:
        api: {server: app-1}
        gpu: {server: gpu-box, functions: [resize, ocr]}
```
Functions not listed, and every workflow, run in the default group.

**In studio**
1. Open **Deploy** and expand **Where functions run**.
2. Add the group `gpu` on gpu-box and tick resize and ocr.
3. Click **Save**, then **Deploy**. When you create a new function, its *Runs on* field picks the group.

**In the terminal**
```bash
pskit validate
pskit deploy -s dev
```
The groups call each other on their ports, so open the port of each group host to the other one (`pskit firewall` lists the rules)."""),

    A(30, provider="onprem", stage="staging", mode="auto", page="Deploy", persona="pasted_error",
      sources=["docs/placement.md#deploy-urls-and-load-balancers"],
      user="GET http://192.0.2.10:8080/resize -> 404, body says the function is in group gpu with its URL. I want ONE url for all of it",
      steps=[S("search_docs", query="placement 404 other group route one URL gateway",
               docs=[D("docs/placement.md", "deploy-urls-and-load-balancers", start="Each server answers only the HTTP routes",
                       end="passed on to the right group.")])],
      final="""That's expected with placement. Each server answers only the routes of the functions it runs, and a route from another group gets a `404` naming that group's URL [docs/placement.md#deploy-urls-and-load-balancers]. Turn on `gateway`, so every group answers every route and passes the others on.

**In code**
```yaml
provider:
  name: onprem
  options:
    placement:
      gateway: true
```
Keep your existing `default` and `groups`. If the project uses a load balancer (`options.balancer: edge`), `gateway` is already on unless you set it to `false`.

**In studio**
1. Open **Deploy** and expand **Where functions run**.
2. Tick *One URL: every group answers every route and passes other groups' routes on*.
3. Click **Save**, then **Deploy**.

**In the terminal**
```bash
pskit deploy -s staging
```
A request that one group already forwarded is never forwarded again, so configs that disagree can't create loops."""),

    A(31, provider="onprem", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/placement.md#functions-that-share-a-code-file"],
      user="which command moves get-item and create-item out of app/handlers.py into their own folders?",
      steps=[S("search_docs", query="split functions shared handlers file own folder",
               docs=[D("docs/placement.md", "functions-that-share-a-code-file", start="Functions whose handlers sit side by side",
                       end="a Node.js handler by hand.", words=300)])],
      final="""**In the terminal**
1. Preview the change:
```bash
pskit function split get-item create-item --dry-run
```
2. Run it:
```bash
pskit function split get-item create-item
```

Each function moves to `functions/<name>/handler.py`, together with the module-level helpers and imports it uses. It gets its own `requirements.txt` with the lines its imports name, and its `handler` in pskit.yml is updated. Helpers are copied, not moved, so a module-level dict is no longer shared between the split functions. This works for Python handlers only [docs/placement.md#functions-that-share-a-code-file]."""),

    A(32, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="terse_expert",
      sources=["docs/load-balancers.md#shared-between-projects-and-machines", "docs/load-balancers.md#commands"],
      user="two repos, two services. can both sit behind the same pskit lb?",
      steps=[S("search_docs", query="share load balancer between projects",
               docs=[D("docs/load-balancers.md", "shared-between-projects-and-machines")]),
             S("search_docs", query="lb forget remove force",
               docs=[D("docs/load-balancers.md", "commands", start="pskit lb remove edge", end="it keeps running for the others")])],
      final="""Yes. The routes live on the load balancer server, not in one project, so projects in other folders or on other machines share it by path, e.g. `/orders/` and `/billing/` [docs/load-balancers.md#shared-between-projects-and-machines].

**In the terminal**
In the second repo:
```bash
pskit lb create edge --server lb-1
pskit lb status edge
```
`lb create` finds the running load balancer and adds it with its port and algorithm unchanged. `lb status` lists every route and marks the routes of other projects.

**In code**
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    balancer: edge
```

Notes:
- A path belongs to one deployment. If you pick a path another project already uses, you get an error and must choose another path.
- To stop using it in one repo, run `pskit lb forget edge`. It keeps running for the others. `pskit lb remove edge` stops it and needs `--force` while other projects still use it [docs/load-balancers.md#commands]."""),

    A(33, provider="onprem", stage="prod", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resource-guides/onprem/services.md#databases-one-server-or-a-primary-with-read-replicas"],
      user="i want postgres on my own servers but with copies on other servers for reading. is that possible?",
      steps=[S("search_docs", query="postgres primary read replicas on-prem",
               docs=[D("docs/resource-guides/onprem/services.md", "databases-one-server-or-a-primary-with-read-replicas", words=150),
                     D("docs/resource-guides/onprem/services.md", "databases-one-server-or-a-primary-with-read-replicas",
                       start="Handlers do not change.", end="the replicas, comma separated |")])],
      final="""Yes. Create the database as **Primary + read replicas**. The primary takes every write, each read replica on another server keeps a copy and answers reads, and an optional load balancer (pgpool-II for PostgreSQL) gives your functions one address [docs/resource-guides/onprem/services.md#databases-one-server-or-a-primary-with-read-replicas].

**In studio**
1. Save the servers first in **Resources > On-prem services > Servers**.
2. Click **+ Create service**, pick PostgreSQL, and under *Scaling* choose *Primary + read replicas*.
3. Pick the primary (db-1), the replicas (db-2, db-3) and, optionally, the load balancer server.

**In the terminal**
```bash
pskit resources onprem create orders-db --service postgres --primary db-1 --replica db-2 --replica db-3 --balancer lb-1 --save
pskit resources onprem replicas list orders-db
```

**In code**
Your handlers don't change. They read these variables from `.env.onprem`:
- `PSKIT_ORDERS_DB_URL`: the load balancer, or the primary when there is none
- `PSKIT_ORDERS_DB_WRITE_URL`: the primary
- `PSKIT_ORDERS_DB_READ_URLS`: the replicas, comma separated

Put each member on its own server. If the PostgreSQL primary fails, the replicas keep serving reads, but promoting one is a manual step today."""),

    A(34, provider="onprem", stage="dev", mode="auto", page="Resources", persona="informal_non_native",
      sources=["docs/resource-guides/onprem/services.md#ssh-login-key-agent-or-password"],
      user="my server dont have ssh key, only password login. pskit can use it? i am on windows",
      steps=[S("search_docs", query="ssh password login server windows sshpass",
               docs=[D("docs/resource-guides/onprem/services.md", "ssh-login-key-agent-or-password", start="Password logins go through **sshpass**",
                       end="and checks that the key works:")])],
      final="""Yes, but on Windows the easiest way is to install a key once. pskit's password logins use **sshpass**, which Windows doesn't have [docs/resource-guides/onprem/services.md#ssh-login-key-agent-or-password].

**In the terminal**
1. Install a key with your password one time:
```bash
pskit resources onprem ssh-key ubuntu@192.0.2.20
```
pskit creates `~/.ssh/pskit_ed25519`, asks for the password once, adds the key to the server's `authorized_keys` and checks that it works.
2. Save the server with that key:
```bash
pskit resources onprem servers add app-1 --ssh ubuntu@192.0.2.20 --pem ~/.ssh/pskit_ed25519
```

**In studio**
1. Open **Resources > On-prem services > Servers > + Add server**.
2. For *Log in with*, choose the key file `~/.ssh/pskit_ed25519`.

On Linux or macOS you can log in with the password directly. Install sshpass and use `--ssh-password-env NAME`. The server must allow `PasswordAuthentication`."""),

    A(35, provider="onprem", stage="prod", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resource-guides/onprem/services.md#where-a-server-is-used-and-how-the-servers-connect"],
      user="in the studio, where do i click to see what still uses db-1 before i forget it?",
      steps=[S("search_docs", query="where is a server used before forget",
               docs=[D("docs/resource-guides/onprem/services.md", "where-a-server-is-used-and-how-the-servers-connect",
                       end="`pskit resources onprem servers usage [NAME] [--json]`.")])],
      final="""**In studio**
1. Open **Resources > On-prem services > Servers**.
2. Find db-1 and read its **Used in** column. It lists every place that names the server: the deploy target, the stage last deployed there, function groups, clusters, load balancers, services and database replicas, with the functions behind each one.
3. If it says *not used anywhere*, it's safe to click **Forget**. **Forget** shows the same list again before it asks.

[docs/resource-guides/onprem/services.md#where-a-server-is-used-and-how-the-servers-connect]"""),

    A(36, provider="onprem", stage="staging", mode="ask", page="Cluster", persona="terse_expert",
      sources=["docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full"],
      user="k3s test cluster is done. how do I tear it all down incl. the master and k3s itself?",
      steps=[S("search_docs", query="remove whole cluster uninstall master",
               docs=[D("docs/cluster.md", "monitor-scale-and-add-servers-when-it-is-full",
                       start="**Remove the whole cluster, master included.**",
                       end="Without `--uninstall`, `pskit cluster remove` only forgets the cluster.")])],
      final="""Use `pskit cluster remove` with `--uninstall`. Without it, the command only forgets the cluster [docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full].

**In the terminal**
```bash
pskit cluster remove staging --uninstall
```
Add `--delete-data` if the main replicas' data on the master should go too.

**In studio**
1. Open **Scaling cluster** and select the cluster.
2. Click *Remove* on the master's row. Choose *Uninstall and delete data* if you want the data gone too.

It stops the deployments and removes the cluster's load balancer. It uninstalls the agent from every joined server, then k3s from the master (with its images) and the `pskit-cluster` folder. Docker itself and your saved servers stay. A server that doesn't answer is reported and skipped.

This deletes running workloads, so I won't run it for you. Run it yourself when you're sure."""),

    A(37, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resource-guides/onprem/services.md#install-software-on-a-server"],
      user="server app-1 has python 3.8 only. my function need 3.12. pskit can install it?",
      steps=[S("search_docs", query="install python version on server",
               docs=[D("docs/resource-guides/onprem/services.md", "install-software-on-a-server", end="| Docker | distribution | installed and started |"),
                     D("docs/resource-guides/onprem/services.md", "install-software-on-a-server", start="pskit resources onprem create py312",
                       end="pskit never uninstalls software (*Remove* only forgets it).")])],
      final="""Yes. pskit can install an exact CPython 3.12 on the server over SSH. It goes to `/opt/pskit-python` and is linked as `/usr/local/bin/python3.12`. Your host then runs with `python: system` and `runtime: python3.12` [docs/resource-guides/onprem/services.md#install-software-on-a-server].

**In studio**
1. Open **Resources > On-prem services > Servers**.
2. On app-1, click *Install / create* and choose Python 3, version 3.12.

**In the terminal**
```bash
pskit resources onprem create py312 --service python --version 3.12 --server app-1
```

**In code**
```yaml
provider:
  name: onprem
  runtime: python3.12
  options:
    deploy: {server: app-1, python: system}
```

pskit never uninstalls software. *Remove* only forgets it. If you'd rather not install anything, `python: bundle` copies a portable CPython with the app."""),

    A(38, provider="onprem", stage="prod", mode="auto", page="Load balancers", persona="detailed_spec",
      sources=["docs/cluster.md#load-balancer-one-url-for-the-whole-cluster-optional",
               "docs/resource-guides/onprem/services.md#install-software-on-a-server"],
      user="Can the load balancer pskit installs terminate HTTPS with a Let's Encrypt certificate? Our users must reach the API over https.",
      steps=[S("search_docs", query="load balancer https tls certificate",
               docs=[D("docs/cluster.md", "load-balancer-one-url-for-the-whole-cluster-optional", start="What nginx does with each request:",
                       end="or use your own nginx / HAProxy instead of this one.")]),
             S("search_docs", query="install caddy certbot nginx on server",
               docs=[D("docs/resource-guides/onprem/services.md", "install-software-on-a-server", start="| **nginx** | distribution |",
                       end="| Certbot | distribution | with the nginx plugin where available |")])],
      final="""No. pskit's load balancer speaks plain HTTP. For HTTPS, put your own TLS terminator in front of it, or use your own nginx or HAProxy instead [docs/cluster.md#load-balancer-one-url-for-the-whole-cluster-optional]. It passes `X-Forwarded-Proto`, so your handlers can still see the original scheme.

pskit can install the TLS tools for you on a server [docs/resource-guides/onprem/services.md#install-software-on-a-server]:
1. **Caddy** (automatic HTTPS) or **nginx** with **Certbot**, through *Install / create* on the server in **Resources > On-prem services > Servers**, or:
```bash
pskit resources onprem create web --service nginx --server lb-1
```
2. Point the TLS proxy at the pskit load balancer's port, and send users to the HTTPS address.

The Nginx Proxy Manager one-click service (reverse proxy with Let's Encrypt) is another option."""),

    A(39, provider="onprem", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=["docs/cli.md#pskit-settings"],
      user="i cloned the project on my new laptop and all my saved servers and the cluster are gone??",
      steps=[S("search_docs", query="move saved servers to another machine",
               docs=[D("docs/cli.md", "pskit-settings", end="SSH passwords typed in the studio |")])],
      final="""They aren't lost. They're stored in `.pskit`, which is kept out of git, so a fresh clone doesn't have them. Move them with an encrypted settings file [docs/cli.md#pskit-settings].

**In studio**
1. On the old laptop, click **⇅ Settings** in the top bar and export. Choose a passphrase of at least 8 characters.
2. On the new laptop, click **⇅ Settings**, import the file and enter the passphrase.

**In the terminal**
Old laptop:
```bash
pskit settings export -o shop.pskit-settings
```
New laptop:
```bash
pskit settings import shop.pskit-settings --dry-run
pskit settings import shop.pskit-settings
```
`--dry-run` shows what would change first. By default entries merge by name.

The file holds saved servers, clusters, on-prem services with their passwords, and SSH keys. Send the file and the passphrase through different channels."""),

    A(40, provider="onprem", stage="prod", mode="ask", page="Network map", persona="terse_expert",
      sources=["docs/onprem-network.md#6-scaling-cluster-join-a-server-pskit-cluster-join-prod-edge2-and-run"],
      user="k3s: ports between nodes?",
      steps=[S("search_docs", query="k3s ports between cluster servers firewall",
               docs=[D("docs/onprem-network.md", "6-scaling-cluster-join-a-server-pskit-cluster-join-prod-edge2-and-run",
                       end="Leaving (`pskit cluster leave`) needs only SSH.", words=400)])],
      final="""For k3s, open these between cluster servers only [docs/onprem-network.md#6-scaling-cluster-join-a-server-pskit-cluster-join-prod-edge2-and-run]:
- **TCP 6443** to the master (API, agents register)
- **UDP 8472** all to all (Flannel VXLAN)
- **TCP 10250** master to workers (kubelet, logs)

You also need:
- TCP `FN_PORT` (default 8080) from every server to the master, for the main replica
- TCP 22 from your admin machine to the joining server and the master
- outbound 443 from the joining server for the k3s download
- users to `FN_PORT` on every server, or only to the load balancer if you have one

To get the exact `ufw` lines for your servers:
```bash
pskit firewall --server app-2
```"""),
]
