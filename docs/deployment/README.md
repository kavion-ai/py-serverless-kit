# Deploy your project: every deployment type

Search terms: deploy, deployment, deployment types, terraform apply, serverless, lambda, on-prem, on premises, ssh
server, docker, scaling cluster, swarm, k3s, nomad, placement, function groups, pipeline, .pskit folder,
deployment.json, studio Deploy page

pskit turns one `pskit.yml` into a running deployment. It never calls cloud APIs itself: it writes Terraform JSON and
runs Terraform. The same project can go to any cloud, to one of your own machines, or to several servers. This page
lists every way to deploy, explains the pipeline every deploy goes through, and shows the Deploy page in studio.

## Pick a deployment type

pskit has seven deployment types. Each row says where the functions run, when to pick it, and how to select it.

| Deployment type | Where the functions run | Pick it when | How to select it | Depth |
|---|---|---|---|---|
| Cloud (serverless) | the cloud's function service (Lambda, Cloud Functions, Azure Functions, ...) | you want a managed cloud and pay per call | `provider.name: aws` (or another cloud), `pskit deploy` | [providers](../providers/README.md) |
| On-prem, this machine | one host process on the machine that runs `pskit` | local testing, a single office machine, demos | `provider.name: onprem`, `options.deploy.method: local` (the default) | [on-prem](../onprem/README.md) |
| On-prem, SSH server | one host process (or a systemd unit on Linux) on a server | one server you reach over SSH | `options.deploy: {method: ssh, host: ...}` or `--server NAME` | [servers](../onprem/servers.md) |
| On-prem, Docker | one container, on this machine or on a server | the server has no Python, or you want a container | `options.deploy.method: docker` | [on-prem provider](../providers/onprem/README.md) |
| On-prem, function groups | each group of functions on its own server or cluster | GPU functions on a GPU server, the API on another | `options.placement` | [placement](../onprem/placement.md) |
| On-prem, scaling cluster | replicas spread over a master and joined servers | more traffic than one server can take | `options.cluster: NAME` or `--cluster NAME` | [scaling](../onprem/scaling/README.md) |
| Several clouds at once | one deployment per provider and stage, each with its own state | the same code on AWS and GCP, or a cloud plus on-prem | `-p aws`, `-p gcp`, `-p onprem` on the same project | [per-cloud overrides](settings-and-config.md#override-values-for-one-cloud-with-providers) |

Run `pskit providers` to print which triggers and workflow engine each provider supports in your installed version.

## How a deploy works: validate, package, plan, deploy, info

Every deploy goes through the same pipeline. Each step is also a command, so you can stop after any of them.

1. **Validate** (`pskit validate`): pskit loads `pskit.yml`, merges `extends`, `providers:` and `stages:` overrides,
   resolves `${env|opt|self|file}` variables, and checks the result against the provider. Errors stop the deploy.
2. **Package** (`pskit package`): pskit builds the bundle (`artifact.zip`: your code, the vendored runtime,
   dependencies) and renders `main.tf.json`. No cloud calls. The `before_package` and `after_package` hooks run here.
3. **Plan** (`pskit plan`): `terraform init` and `terraform plan` show what would change. `--destroy` plans a removal.
4. **Deploy** (`pskit deploy`): package, `terraform init`, then `terraform apply`. The `before_deploy` and
   `after_deploy` hooks run around it. pskit reads the Terraform outputs and writes `deployment.json`, then
   regenerates the dashboard (skip it with `--no-dashboard`).
5. **Info** (`pskit info`): prints the deployed functions, URLs, ids and console links from `deployment.json`.
   `--refresh` reads the Terraform outputs again first.

```bash
pskit validate -s dev
pskit package -s dev
pskit plan -s dev
pskit deploy -s dev
pskit info -s dev
```

`pskit deploy` runs `terraform apply -auto-approve`. Add `--confirm` to see the plan and apply only that plan.

## What pskit writes to the .pskit folder

The `.pskit/` folder holds everything pskit generates. It is git-ignored (pskit writes `.pskit/.gitignore` with `*`).
Each provider and stage pair gets its own folder, so each has its own Terraform workspace and state.

| Path | What it is |
|---|---|
| `.pskit/<provider>-<stage>/build/` | the staged bundle before it is zipped |
| `.pskit/<provider>-<stage>/artifact.zip` | the deterministic bundle: same inputs, same hash |
| `.pskit/<provider>-<stage>/main.tf.json` | the generated Terraform configuration |
| `.pskit/<provider>-<stage>/terraform.tfstate` | the Terraform state (unless you set a remote backend) |
| `.pskit/<provider>-<stage>/deployment.json` | the deployment record: functions, URLs, ids, workflows, resources, outputs, status |
| `.pskit/<provider>-<stage>/kept/` | resources kept by `pskit remove --keep-resources` |
| `.pskit/onprem-<stage>/onprem_deployed.json` | on premises: the server or cluster the stage was last deployed to |
| `.pskit/dashboard/index.html` | the deployment dashboard ([monitoring](monitoring-and-dashboard.md)) |

`deployment.json` has `status` `deployed` or `removed`. `pskit info`, `pskit logs`, the dashboard and the studio
Logs page all read it. Run any other Terraform command in the folder with `pskit tf`:

```bash
pskit tf -s dev -- state list
pskit tf -s prod -- output -json
```

## Deploy to a cloud with Terraform

A cloud deploy creates serverless functions, their triggers and managed resources with the cloud's Terraform
provider. You need Terraform (or OpenTofu) and the cloud's credentials on this machine.

1. Check the machine: `pskit doctor -p aws` (studio: **Setup & credentials**). See
   [settings and config](settings-and-config.md#check-tools-and-credentials-with-pskit-doctor).
2. Set the provider in `pskit.yml`:

   ```yaml
   service: orders
   provider:
     name: aws
     region: eu-west-1
   functions:
     hello:
       handler: app.handlers.hello
       events:
         - http: GET /hello
   ```

3. Deploy and read the URLs:

   ```bash
   pskit deploy -s dev
   pskit info -s dev
   ```

To try the same project on another cloud, pass `-p`: `pskit deploy -p gcp -s dev`. Each cloud needs its own
`provider.options` (for example the GCP project). Put them under `providers.<cloud>` so one file serves every cloud
([settings and config](settings-and-config.md#override-values-for-one-cloud-with-providers)). The per-cloud pages
under [providers](../providers/README.md) list credentials, options and limits.

## Deploy on premises on this machine

The on-premises provider with `method: local` starts one long-lived host process on the machine that runs `pskit`.
That process serves HTTP and runs schedules, queues, storage events, topics and workflows. Terraform uses only its
built-in `terraform_data`, so no cloud plugin is downloaded.

```yaml
provider:
  name: onprem
  options:
    port: 8080
    deploy:
      method: local
```

```bash
pskit deploy -p onprem -s dev
pskit info -p onprem -s dev        # the endpoint, e.g. http://127.0.0.1:8080
```

`pskit remove` stops the process and keeps its data folder. Full options: [on-prem provider](../providers/onprem/README.md).

## Deploy on premises to a server over SSH

The SSH deploy method copies one `release.tar.gz` to a server with `scp`, then starts a process or a systemd unit
and waits until `/__pskit/health` answers. The simplest setup is a saved server.

1. Save the server once (studio: **Resources** → **On-prem services** → **Servers**):

   ```bash
   pskit resources onprem servers add edge1 --ssh root@10.0.0.5 --pem ~/.ssh/edge.pem
   ```

2. Deploy to it, once with a flag or always with `pskit.yml`:

   ```bash
   pskit deploy -p onprem -s prod --server edge1
   ```

   ```yaml
   provider:
     name: onprem
     options:
       host: 0.0.0.0              # listen on every interface so other machines can call it
       deploy:
         server: edge1
         path: /opt/pskit/orders
   ```

Use `python: bundle` under `deploy:` when the server has no Python. Details on saved servers and SSH keys:
[servers](../onprem/servers.md). Ports to open: [firewall](../onprem/firewall.md) or `pskit firewall --server edge1`.

## Deploy on premises in Docker

The Docker deploy method builds an image that already contains Python (or Node.js) and runs it as a container.
Without `host` the container runs on this machine. With `host` the image is built here, copied over SSH and started
on the server; Docker is installed there first when it is missing.

```yaml
provider:
  name: onprem
  options:
    deploy:
      method: docker
      host: 10.0.1.12           # leave out to run the container on this machine
      user: pskit
      image: pskit/orders:dev
```

```bash
pskit deploy -p onprem -s dev
```

This machine needs a running Docker daemon (`pskit doctor -p onprem` checks it). Every `deploy:` key is in the
[on-prem provider](../providers/onprem/README.md) page.

## Put groups of functions on different servers

Placement splits the functions of one project into groups, and each group runs on its own server, cluster or this
machine. Each server installs only the requirements of its own functions. Workflows run on the default group.

```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    placement:
      default: api
      groups:
        api: {server: app1}
        gpu: {server: gpu1, functions: [resize, ocr]}
        batch: {cluster: prod, functions: [report]}
```

```bash
pskit deploy -p onprem -s prod      # deploys every group; each group runs where its group says
```

In studio, open **Deploy**, expand **Where functions run**, pick **Split functions across servers**, then set
**Runs on** for each group. Full guide: [placement](../onprem/placement.md).

## Run functions on a scaling cluster

A scaling cluster runs the functions as replicas on a master server plus joined servers. pskit installs and drives
one of three orchestrators over SSH: Docker Swarm (`swarm`), Kubernetes with k3s (`kubernetes`) or HashiCorp Nomad
(`nomad`). There is 1 main replica on the master plus web replicas (default 2) spread over the servers.

```bash
pskit cluster create prod --orchestrator swarm --master edge1
pskit cluster join prod edge2
pskit deploy -p onprem -s prod --cluster prod
pskit cluster status prod
```

```yaml
provider:
  name: onprem
  options:
    cluster:
      name: prod
      replicas: 3
```

In studio: **Scaling cluster** → **+ New cluster**, then **Deploy** → **Run on** → **Scaling cluster**. Compare the
orchestrators in [scaling](../onprem/scaling/README.md); per-orchestrator pages:
[Docker Swarm](../onprem/scaling/docker-swarm.md), [k3s](../onprem/scaling/kubernetes-k3s.md),
[Nomad](../onprem/scaling/nomad.md).

## Where an on-prem deploy goes and how the stage remembers it

An on-prem deploy picks its target in this order; the first match wins:

1. `--cluster NAME` (studio: **Run on** → **Scaling cluster**).
2. `--server NAME` or `--server local` (studio: **Run on** → **One machine**).
3. `options.cluster` in `pskit.yml`, then `options.deploy` (`server`, `host`, `method`).
4. Where the stage was last deployed.

After a successful deploy the stage remembers its machine in `.pskit/onprem-<stage>/onprem_deployed.json`.
`pskit logs`, `pskit trigger`, `pskit info`, the dashboard and the studio Test and Logs pages then talk to that host.
Moving a stage to another server leaves the old one running until you `pskit remove` it there. Keep one stage per
machine to keep deployments apart.

Before each on-prem deploy pskit also checks the on-prem services (Redis, Postgres, MinIO, ...) the functions use.
When the functions move to another server or cluster, pskit switches a service address it picked itself to one that
works from the new place, and warns when it cannot (for example a service bound to `127.0.0.1` only). After the
deploy it updates SMTP services, load balancer routes (`options.balancer`) and prints the firewall rules each server
needs.

## Deploy from studio on the Deploy page

The studio **Deploy** page runs the same `pskit` commands in the project folder, with your shell's credentials.

1. Start studio: `pskit studio --open`.
2. In the top bar, pick the target in **validate & deploy as** (the provider) and type the **stage**.
3. Click **Deploy** in the sidebar.
4. If a box says *N items won't run on PROVIDER*, click **Disable all of them on PROVIDER** (or one of the
   **Disable trigger / function / workflow on PROVIDER** buttons). This writes `providers.<cloud>` overrides, so
   other clouds keep them. Save with **Save** (Ctrl+S).
5. On premises only: in **Run on**, pick **One machine** and a **Machine**, or **Scaling cluster** and a cluster.
   With placement, the box shows each group and where it runs instead.
6. Click one of the action cards: **Validate**, **Package**, **Plan**, **Deploy**, **Info** or **Remove**.
7. When pskit.yml has unsaved changes, studio asks **Save and run** or **Run without saving**.
8. A deploy to a stage that starts with `prod`, and every **Remove**, asks you to type `provider/stage` to confirm.
9. The output appears below the cards. **Cancel** stops a running job; **follow** keeps the newest line in view.

The **Remove** toggle under the cards decides what Remove does: *Remove also deletes buckets, queues and topics*
(default) or *Remove keeps buckets, queues and topics (and their data)* (`--keep-resources`).

Further down the page: **Firewall** (on premises), **Invoke a function locally** (`pskit invoke`), **Run a workflow
locally** (`pskit workflow run --history`) and **Recent jobs**. Click a job to see its output again, the cross to
forget one, or **Clear finished** to forget all finished jobs. Only one deploy-type job runs at a time.

## Follow an on-prem deploy step by step in studio

For on-prem **Deploy** and **Remove** jobs the studio output has two tabs: **Steps** and **Raw log**. The Steps tab
splits the job into rows that show *waiting*, *running*, *done*, *failed* or *cancelled*:

| Step | What happens |
|---|---|
| **Check & build** | validation and packaging |
| **Terraform plan** | the plan |
| one row per host or group | the `terraform_data` resource of that host; with placement, one row per group |
| **Terraform apply** / **Terraform destroy** | the other resources and the outputs |
| **Load balancer** | routes of this deployment on its load balancers (when there are any) |
| **Firewall** | ports each server must open: REQUIRED, NEEDED (for a feature) or optional |
| **Done** | the endpoints, as links |

A failed row opens by itself and shows the error, the end of the host's log, and a *Stopped here* box. The Raw log
tab has every line. Cloud deploys show the raw output only.

## Commands and flags for deploying

These options work on `validate`, `package`, `plan`, `deploy`, `remove`, `info`, `logs`, `invoke`, `trigger`, `tf`
and the `workflow` commands:

| Option | Meaning |
|---|---|
| `-c, --config FILE` | config file (default: `pskit.yml`, `pskit.yaml`, `serverless_kit.yml`, `serverless_kit.yaml`) |
| `-p, --provider NAME` | override `provider.name` |
| `-s, --stage NAME` | the stage (default `provider.stage`, else `dev`) |
| `-r, --region NAME` | override `provider.region` |
| `--server NAME` | on premises: a saved SSH server, or `local` for this machine |
| `--cluster NAME` | on premises: a scaling cluster (not together with `--server`) |
| `-v, --verbose` | print tracebacks on errors |

| Command | Own flags |
|---|---|
| `pskit package` | `--skip-deps` (do not pip-install requirements into the bundle) |
| `pskit plan` | `--skip-deps`, `--destroy` |
| `pskit deploy` | `--skip-deps`, `--confirm` (show the plan, apply that plan), `--upgrade` (`terraform init -upgrade`), `--no-dashboard` |
| `pskit info` | `--json`, `--refresh` |
| `pskit remove` | `-y, --yes`, `--keep-resources` |
| `pskit tf -- ARGS` | any Terraform command in the generated folder (needs `pskit package` first) |

Removing and reading what is deployed: [deploy, remove and info](deploy-remove-info.md).

## Run your own commands around a deploy with hooks

Hooks are shell commands pskit runs at fixed points of the pipeline. They run in the project root with
`PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and `PSKIT_WORK_DIR` set. A non-zero exit stops the command.

```yaml
hooks:
  before_package: ["python scripts/gen_schema.py"]
  after_deploy: ["python scripts/smoke_test.py"]
```

Allowed hooks: `before_package`, `after_package`, `before_deploy`, `after_deploy`, `before_remove`, `after_remove`.

## Share Terraform state with a team

Terraform state lives in `.pskit/<provider>-<stage>/terraform.tfstate` by default, only on this machine. For a team
or CI, set a remote backend so everyone deploys against the same state:

```yaml
provider:
  state:
    backend: s3
    config:
      bucket: my-tf-state
      key: orders/${opt:stage}.tfstate
      region: us-east-1
```

Any Terraform backend type works (`s3`, `gcs`, `azurerm`, `http`, `remote`, ...). For on-prem stages, keep state
local with `stages.<stage>.providers.onprem.state: {backend: null}` (see [stages](stages.md)). On-prem settings that
are not in Terraform state (saved servers, clusters, services) move with `pskit settings export`
([settings and config](settings-and-config.md#move-local-settings-to-another-machine)).

## See also

- [Stages](stages.md)
- [Deploy, remove and info](deploy-remove-info.md)
- [Workflows](workflows.md)
- [Logs](logs.md)
- [Monitoring and dashboard](monitoring-and-dashboard.md)
- [Settings and config](settings-and-config.md)
- [Providers](../providers/README.md) and [on-prem overview](../onprem/README.md)
- [Studio guide](../studio-guide/README.md)
- Existing reference: [cli.md](../cli.md), [cluster.md](../cluster.md), [placement.md](../placement.md),
  [architecture.md](../architecture.md)
