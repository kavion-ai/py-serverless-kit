# Docker Swarm scaling cluster

Search terms: Docker Swarm, swarm cluster, swarm init, swarm join, routing mesh, create cluster, join server,
drain server, remove server, master, worker, scale out, pskit cluster

A Docker Swarm scaling cluster runs your on-prem functions on a **master** server plus any number of **joined**
servers. pskit installs Docker and Swarm over SSH, copies the function image to every server (no registry needed),
and deploys. Swarm's routing mesh answers on the functions' port (default 8080) of **every** server and spreads the
requests over the web replicas.

## Before you create a Docker Swarm cluster

A Docker Swarm cluster needs a few things on your machine and on the servers:

* Docker running on **your** machine (pskit builds the function image there).
* Linux servers (x86_64 or arm64) with SSH, and root or passwordless `sudo`.
* Each server saved once in pskit (see [Servers](../servers.md)):

  ```bash
  pskit resources onprem servers add edge1 --ssh root@10.0.0.5 --pem ~/.ssh/edge.pem
  pskit resources onprem servers add edge2 --ssh root@10.0.0.6 --pem ~/.ssh/edge.pem
  ```

* The Swarm ports open between the servers: TCP 2377 (to the master), TCP and UDP 7946, UDP 4789. See
  [Firewall rules](../firewall.md).
* The project's provider set to `onprem`.

## Create a Docker Swarm cluster in studio

The studio creates a Docker Swarm cluster from the **Scaling cluster** page.

1. Open **Scaling cluster** in the sidebar.
2. Click **+ New cluster**. The **New scaling cluster** drawer opens.
3. Fill in:
   * **Cluster name**: a lowercase letter first, then lowercase letters, digits and `-` (default `prod`).
   * **Orchestrator**: **Docker Swarm**. The help text lists the ports to open between servers.
   * **Master server**: a saved server, or **+ Add a server** to save one in place.
   * **Cluster address (optional)**: the master's private IP that the other servers reach. Default: its SSH host.
   * **Master serves requests**: the switch **Send requests to the master too, not only to the joined servers**.
     On by default for Swarm (see [The master and requests](#decide-whether-the-swarm-master-serves-requests)).
4. Click **Create**. The button shows **Installing…** while the job runs; the job output shows each step and the
   firewall rules the cluster needs.
5. When it succeeds, the page shows the cluster card: master, number of servers, and the **Servers** table.

## Create a Docker Swarm cluster from the terminal

The `pskit cluster create` command installs Docker and `swarm init` on the master and saves the cluster.

```bash
pskit cluster create prod --orchestrator swarm --master edge1 --advertise 10.0.0.5
```

| Option | Meaning |
|---|---|
| `-o, --orchestrator` | `swarm`, `kubernetes` or `nomad` (required) |
| `--master` | saved server that runs the control plane and the main replica (required) |
| `--advertise` | the master's address the other servers use (default: its SSH host); use the private IP in one network |
| `--master-serves / --no-master-serves` | send requests to the master too (Swarm default: on) |

The command prints the firewall rules the cluster needs. Clusters are saved in `.pskit/onprem-clusters.json`.

## Join a server to a Docker Swarm cluster

Joining a server to a Docker Swarm cluster installs Docker, runs `swarm join` with a token read from the master,
and copies the images already deployed. You can join while functions are running.

**In studio**

1. Open **Scaling cluster** and select the cluster (tabs at the top when there are several).
2. In the **Servers** card click **+ Join server** (or **+ Join a server now** in the red "cluster is full" banner).
3. In the **Join a server to prod** drawer pick a **Server** (or **+ Add a server**) and, optionally, its
   **Cluster address (optional)**.
4. Click **Join**. The job output follows; the server then appears in the **Servers** table.

**From the terminal**

```bash
pskit cluster join prod edge2 --advertise 10.0.0.6
```

Joining again is safe. A server left half-joined, or still in an old swarm, leaves that membership first. pskit
refuses a server that manages another swarm with nodes or services, or whose swarm is locked.

## Deploy functions to a Docker Swarm cluster

Deploying to a Docker Swarm cluster builds the image on your machine, copies it to every server, and runs
`docker stack deploy` on the master. The stack is named `pskit-<service>-<stage>`.

**In studio**

1. On the **Scaling cluster** page turn on **Deploy this project's functions to prod**
   (`provider.options.cluster`).
2. Set **Web replicas** (default 2), **CPU per replica** (default 0.25) and **Memory per replica (MB)** (default 256).
3. Save the project, then open **Deploy**, pick **Run on → Scaling cluster** and the cluster, and deploy.

**From the terminal**, write the cluster into `pskit.yml` and deploy:

```yaml
provider:
  name: onprem
  options:
    cluster:
      name: prod
      replicas: 3          # web replicas (1..500, default 2), plus 1 main replica on the master
      cpu: 0.25            # CPU cores each replica reserves
      memory: 256          # MB each replica reserves
    port: 8080
```

```bash
pskit deploy                     # or, without options.cluster: pskit deploy --cluster prod
pskit info                       # deployed on: cluster prod (master edge1 (10.0.0.5))
```

`pskit deploy --cluster prod` once moves the stage to the cluster; `pskit deploy --server edge1` moves it back to one
server. The old place keeps running until you `pskit remove` it there.

## Decide whether the Swarm master serves requests

The Docker Swarm master can take requests next to the joined servers, or stay a backup. On Swarm the default is on.

| Setting | What happens on Swarm |
|---|---|
| on | load balancers send requests to every server, and web replicas may run on the master |
| off | web replicas stay off the master while another server can run them; load balancers list the master as a `backup` only |

Change it with the **Send requests to the master edge1 too** switch on the cluster card, or:

```bash
pskit cluster set prod --no-master-serves
```

Load balancers update at once. Web replicas move on or off the master at the next `pskit deploy`.

## Remove (drain) a server from a Docker Swarm cluster

Removing a server from a Docker Swarm cluster first takes it off every load balancer, then drains it
(`docker node update --availability drain`) so its replicas move to the other servers, then leaves the swarm.

**In studio**: in the **Servers** table click **Remove** on the server's row, then **Remove server** to confirm.
The saved server is kept.

**From the terminal**

```bash
pskit cluster leave prod edge2        # --yes to skip the question
```

## Remove the whole Docker Swarm cluster

The Swarm master cannot leave on its own. Removing the whole cluster stops the deployments, removes the cluster's
load balancer, runs `docker swarm leave` on every server, and forgets the cluster. Docker and the saved servers stay.

**In studio**: click **Remove** on the master's row, type the cluster name, then **Uninstall** (or **Uninstall and
delete data** to also delete the main replicas' data). **Forget** on the cluster card only stops managing it.

**From the terminal**

```bash
pskit cluster remove prod --uninstall               # keep the main replicas' data (a Docker volume on the master)
pskit cluster remove prod --uninstall --delete-data
pskit cluster remove prod                           # only forget it; nothing is uninstalled
```

## See also

* [Scaling options compared](README.md), [Kubernetes (k3s)](kubernetes-k3s.md), [Nomad](nomad.md)
* [Replicas, scale and capacity alerts](replicas-and-alerts.md)
* [Load balancers](../load-balancers.md), [Firewall rules](../firewall.md)
* Reference: [cluster.md](../../cluster.md)
