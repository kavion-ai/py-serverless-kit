# On premises: run functions on your own machines

Search terms: on-prem, on premises, self-hosted, own servers, onprem provider, pskit host, local deploy, SSH deploy,
Docker deploy, saved servers, on-prem services, bare metal, VM

The `onprem` provider runs your functions on machines you control: this computer, any Linux server you reach with
SSH, a Docker container, or a scaling cluster of servers. One process, the **pskit host**, serves the HTTP routes
(port 8080 by default), runs schedules, consumes queues, watches buckets and runs workflows. Around it pskit can save
your servers, start the services the functions need (Redis, PostgreSQL, MinIO, ...) and install software, all over
SSH and Docker, without any cloud API.

## Map of the on-prem pages

The on-prem documentation is split by task:

| Page | What it covers |
|---|---|
| [Saved servers](servers.md) | add a server (IP, user, `.pem` key, password), test it, see where it is used, forget it |
| [Terminal, console and software](terminal-and-software.md) | install Docker, Python, Node.js, nginx ...; Shell, Console, browser Terminal, SSH tunnel |
| [On-prem services](services/README.md) | the one-click catalog: one page per service (Redis, Kafka, PostgreSQL, MinIO, OpenBao, SMTP, ...) |
| [On-prem resources and drivers](resources.md) | resource types, the queue / storage / topic drivers, a service as a resource, `resource()` in handlers |
| [Cloud resources on premises](cloud-resources.md) | attach SQS, S3, Azure Queue / Blob, Pub/Sub, GCS, OSS, R2, COS, OBS, Spaces ... to on-prem functions |
| [AWS compatible servers](aws-compatible/README.md) | pskit's own S3 and Secrets Manager compatible servers in depth |
| [Scaling](scaling/README.md) | Docker Swarm, Kubernetes (k3s), Nomad, replicas and alerts |
| [Load balancers](load-balancers.md) | algorithms, shared or separate balancers, attaching them |
| [Database scaling](database-scaling.md) | primary + read replicas, database load balancer |
| [Placement](placement.md) | function groups on different servers |
| [Network map](network-map.md) and [firewall](firewall.md) | which ports each server must accept and open |

## Deploy methods for on-prem functions

On-prem functions deploy with `provider.options.deploy`. The method decides where the host runs:

| Method | Where the host runs | Set it with |
|---|---|---|
| `local` (default) | this machine, as a process | nothing, or `deploy: local` |
| `ssh` (alias `scp`) | a Linux server: the bundle is copied over SSH and the host started there | `deploy: {server: edge1}` (a saved server) or `deploy: {method: ssh, host: ..., user: ..., pem: ...}` |
| `docker` | a container, on this machine or a server | `deploy: {method: docker, ...}` |
| scaling cluster | replicas on several servers | `provider.options.cluster: NAME` or `pskit deploy --cluster NAME` |

```yaml
provider:
  name: onprem
  runtime: python3.12
  options:
    port: 8080
    deploy: {server: edge1, path: /opt/shop}     # a saved server; method ssh
```

`pskit deploy --server edge1` (or **Deploy → Machine** in studio) picks a machine for one run, and later commands
follow the stage's last deploy. Every option, the docker and cluster variants and function groups are explained in
[deployment](../deployment/README.md); the provider block in [the on-prem provider page](../providers/onprem/README.md).

## Set up an on-prem project in studio, step by step

An on-prem project in studio goes from nothing to deployed functions with a service in these steps:

1. Start studio with `pskit studio` in the project folder (see [studio guide](../studio-guide/README.md)).
2. In the top bar pick **onprem** as the target provider (or create the project with the onprem provider).
3. Save a server: **Resources → Servers → + Add server** (or **Overview & provider → On-premises deployment → +
   Add server**), then **Save and test**. See [saved servers](servers.md).
4. Choose where the functions run: **Overview & provider → On-premises deployment → Saved server**.
5. Create a service the functions use: **Resources → + On-prem service**, pick for example **Redis**, set **Where:
   One SSH server** and the server, tick the **Trigger functions**, **Create**. See [on-prem services](services/README.md).
6. Click **Save** in the top bar, then open **Deploy** and deploy the stage.
7. Test it: **Resources → Test** on the resource, and watch **Logs**.

## Set up an on-prem project from the terminal

The same on-prem project from the terminal:

```bash
pskit resources onprem servers add edge1 --ssh ubuntu@10.0.0.5 --pem ~/.ssh/edge1.pem    # saves and tests
pskit resources onprem create jobs --service redis --server edge1 --attach worker --save
pskit deploy --server edge1
pskit resources send jobs -d '{"order_id": 1}'
pskit logs -f
```

## Files pskit keeps for on-prem work

pskit keeps on-prem state in the project, on the machine where you run pskit:

| File | Holds | In git? |
|---|---|---|
| `.pskit/onprem-servers.json` | saved servers (connection details) | no |
| `.pskit/ssh/*.pass` | SSH passwords typed in studio (owner-only) | no |
| `.pskit/onprem-services.json` | created services and installs, with credentials | no |
| `.pskit/backups/` | service backups | no |
| `.pskit/onprem-<stage>/` | deploy output, Terraform state, last deploy target | no |
| `.env.onprem` (`provider.options.env_file`) | service passwords and other variables the host loads at start | no (added to `.gitignore`) |
| `pskit.yml` | resources, triggers, `options.deploy` | yes |

Keep `.pskit/` and the env file out of version control. Moving to another computer: studio **⇅ Settings** imports and
exports the project's settings.

## See also

- [Deployment](../deployment/README.md)
- [On-prem provider](../providers/onprem/README.md)
- [Concepts](../guide/concepts.md)
- [Existing on-prem resource guides](../resource-guides/onprem/README.md)
- [Cluster reference](../cluster.md), [load balancers reference](../load-balancers.md),
  [placement reference](../placement.md), [network reference](../onprem-network.md)
