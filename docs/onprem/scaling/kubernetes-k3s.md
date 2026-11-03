# Kubernetes (k3s) scaling cluster

Search terms: Kubernetes, k3s, kubectl, ServiceLB, create cluster, join node, drain node, k8s, scale out,
master, worker, pskit cluster kubernetes

A Kubernetes scaling cluster in pskit uses [k3s](https://k3s.io), a lightweight Kubernetes that needs no Docker on
the servers. pskit installs k3s over SSH on a **master** server and joins more servers as agents. k3s ServiceLB
answers on the functions' port (default 8080) of **every** server and spreads requests over the web replicas.

## Before you create a Kubernetes (k3s) cluster

A Kubernetes (k3s) cluster needs:

* Docker running on **your** machine (pskit builds the function image there and copies it to every node; the pods
  use `imagePullPolicy: Never`, so no registry is needed).
* Linux servers (x86_64 or arm64) with SSH, and root or passwordless `sudo`.
* Outbound HTTPS from each server the first time (`get.k3s.io`, GitHub downloads).
* The k3s ports open between the servers: TCP 6443 (to the master), UDP 8472 (all to all), TCP 10250 (master to
  workers). See [Firewall rules](../firewall.md).
* The servers saved once: `pskit resources onprem servers add edge1 --ssh root@10.0.0.5 --pem ~/.ssh/edge.pem`.

## Create a Kubernetes (k3s) cluster in studio

The studio creates a k3s cluster from the **Scaling cluster** page.

1. Open **Scaling cluster** in the sidebar and click **+ New cluster**.
2. In **New scaling cluster** set **Cluster name**, pick **Orchestrator → Kubernetes (k3s)**, choose the
   **Master server**, and optionally the **Cluster address (optional)** (the master's private IP).
3. Leave **Master serves requests** on (the k3s default) or turn it off.
4. Click **Create** and follow the job output. pskit runs the k3s installer (`server --write-kubeconfig-mode 644
   --tls-san <address>`) and creates the `pskit` namespace.

## Create a Kubernetes (k3s) cluster from the terminal

The `pskit cluster create` command with `--orchestrator kubernetes` installs k3s on the master.

```bash
pskit cluster create prod --orchestrator kubernetes --master edge1 --advertise 10.0.0.5
```

Every pskit workload runs in the Kubernetes namespace `pskit`. On the master you can inspect it with
`sudo k3s kubectl -n pskit get pods`.

## Join a server to a Kubernetes (k3s) cluster

Joining a server to a k3s cluster installs the k3s agent with a token read from the master, and copies the images
already deployed.

**In studio**: on **Scaling cluster**, in the **Servers** card click **+ Join server**, pick the **Server**, then
**Join**.

**From the terminal**

```bash
pskit cluster join prod edge2 --advertise 10.0.0.6
```

## Deploy functions to a Kubernetes (k3s) cluster

Deploying to a k3s cluster applies two Deployments, `<stack>-main` (one pod pinned to the master with the data in
`/var/lib/pskit/<stack>`) and `<stack>-web` (`replicas` pods), plus a LoadBalancer Service on the functions' port.
Pods have readiness and liveness probes on `/__pskit/health`.

**In studio**

1. On **Scaling cluster** turn on **Deploy this project's functions to prod** and set **Web replicas**,
   **CPU per replica** and **Memory per replica (MB)** (they become the pods' resource requests).
2. Save, open **Deploy**, choose **Run on → Scaling cluster**, and deploy.

**From the terminal**

```yaml
provider:
  name: onprem
  options:
    cluster: {name: prod, replicas: 3, cpu: 0.5, memory: 512}
```

```bash
pskit deploy
```

## Decide whether the k3s master serves requests

The k3s master can take requests next to the joined servers, or stay a backup. On k3s the default is on. With it
off, web pods get a node affinity that keeps them off the master while another node can run them, and load
balancers list the master as a `backup`.

```bash
pskit cluster set prod --no-master-serves     # or the switch on the cluster card
pskit deploy                                  # moves the web pods off the master
```

## Remove (drain) a node from a Kubernetes (k3s) cluster

Removing a node from a k3s cluster takes it off the load balancers, runs `kubectl drain` (pods move to the other
nodes), stops the agent, and deletes the node from the cluster.

**In studio**: click **Remove** on the server's row in **Servers**, then **Remove server**.

**From the terminal**

```bash
pskit cluster leave prod edge2
```

## Remove the whole Kubernetes (k3s) cluster

Removing the whole k3s cluster stops the deployments, runs the k3s uninstall scripts on every agent and on the
master (images included), and forgets the cluster. The main replicas' data in `/var/lib/pskit/<stack>` stays unless
you delete it.

**In studio**: **Remove** on the master's row, type the name, then **Uninstall** or **Uninstall and delete data**.

**From the terminal**

```bash
pskit cluster remove prod --uninstall [--delete-data]
```

## See also

* [Scaling options compared](README.md), [Docker Swarm](docker-swarm.md), [Nomad](nomad.md)
* [Replicas, scale and capacity alerts](replicas-and-alerts.md)
* [Load balancers](../load-balancers.md), [Firewall rules](../firewall.md)
* Reference: [cluster.md](../../cluster.md)
