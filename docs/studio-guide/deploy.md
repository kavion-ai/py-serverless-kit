# Deploy page in studio

Search terms: deploy, validate, package, plan, terraform plan, info, remove, destroy, keep resources, typed confirmation, prod stage, run on machine, cluster deploy, deploy steps, raw log, recent jobs, invoke locally, run workflow locally, unsupported triggers

The **Deploy** page runs pskit in the project folder as the provider and stage in the top bar: validate, package,
plan, deploy, info and remove, with a live log. Sidebar: **Deploy** (▲). Credentials come from your shell
environment, as with the CLI (see [Setup & credentials](setup.md)). Every button runs the matching `pskit` command
(`python -m py_serverless_kit <command> --provider P --stage S`), never through a shell. The concepts are in
[Deploy, remove and info](../deployment/deploy-remove-info.md).

## Deploy a project from studio

The studio **Deploy** action builds the bundle and runs `terraform apply`.

1. Pick the provider and stage in the top bar (**validate & deploy as**, **stage**).
2. Open **Deploy**. If the draft has unsaved changes, a yellow box says so; commands use `pskit.yml` on disk.
3. On premises, choose where it runs in the **Run on** bar (next section).
4. Click **Deploy** ("Build and apply").
5. Studio may ask:
   - **Save first?** with **Save and run** or **Run without saving**;
   - **Not available on <Provider>** when triggers or workflows cannot run there (see below);
   - **Deploy to <provider>/<stage> on <machine>?** on premises, which warns when the stage moves from another
     machine or cluster;
   - for a stage whose name starts with `prod`: **This is a production stage.** Type `<provider>/<stage>` and click
     **Deploy**.
6. The output streams below. Only one deploy-type job (package, plan, deploy, remove, resources delete) runs at a
   time; starting another says "Another deploy-type job is running."
7. The cancel button in the console stops the job.

```bash
pskit deploy -p aws -s dev
pskit deploy -s prod --confirm
```

## Validate, package, plan and show info from studio

The other action cards of the studio Deploy page:

| Card | Hint | Command |
|---|---|---|
| **Validate** | Check the configuration against the provider | `pskit validate -p P -s S` |
| **Package** | Build the bundle and Terraform without deploying | `pskit package -p P -s S` |
| **Plan** | `terraform plan`: what would change | `pskit plan -p P -s S` |
| **Deploy** | Build and apply | `pskit deploy -p P -s S` |
| **Info** | What is deployed | `pskit info -p P -s S` |
| **Remove** | Destroy every resource of this stage | `pskit remove -p P -s S --yes` |

Output goes to `.pskit/<provider>-<stage>/`.

## Remove a deployed stage from studio

The studio **Remove** action destroys the stage. It always needs a typed confirmation.

1. Set the switch under the cards first: **Remove also deletes buckets, queues and topics** (on, default) or
   **Remove keeps buckets, queues and topics (and their data)** (off). External resources are never deleted.
2. Click **Remove**.
3. **Remove <provider>/<stage>?** explains what goes: on = every function, trigger and managed resource including
   buckets, queues and topics and their data; off = functions, triggers and gateways, while managed buckets, queues
   and topics are kept and pskit stops managing them.
4. Type `<provider>/<stage>` (for example `aws/dev`) and click **Remove**.

Kept resources can be deleted later under [Resources → In the cloud](resources.md#delete-deployed-or-kept-cloud-resources-in-studio).

```bash
pskit remove -s dev --yes
pskit remove -s dev --yes --keep-resources
```

## Fix triggers and workflows that won't run on the target provider

The **N items won't run on <Provider>** section on the Deploy page lists what the target provider cannot run, each
marked **unsupported**:

- **Disable trigger on <Provider>** / **Disable function on <Provider>** for a trigger;
- **Disable workflow on <Provider>** for a workflow;
- **Disable all of them on <Provider>**.

They write `providers.<provider>` overrides, so the other providers keep them. Save, then deploy. Items already
switched off show under "Already switched off on <Provider>" with **Enable again** or **Use the normal triggers**.

Running validate, package, plan or deploy with problems asks **Not available on <Provider>**: **Disable on <Provider>
and <command>** saves the overrides and runs; **<Command> anyway** runs as is (and fails).

## Choose the machine or cluster for an on-prem deploy

The **Run on** bar appears on the Deploy page when the target provider is `onprem`.

- **One machine**: **Machine** picks a saved server, this machine, or the default: "Same as the last deploy: <label>"
  or "From pskit.yml (provider.options.deploy)". The same as `pskit deploy --server NAME` (`--server local` for this
  machine). The stage remembers the machine of its last deploy; Test, Logs, `pskit trigger` and `pskit logs` use it.
- **Scaling cluster** (when a cluster exists): pick the cluster. The functions run as 1 main replica on the master
  plus the web replicas of `provider.options.cluster.replicas`. The same as `pskit deploy --cluster NAME`.
- With [placement](placement.md) groups that have their own targets, the bar shows "Split over N groups" instead and
  each group's **Runs on** decides.

A badge shows where the stage is deployed now and the deployed groups and load balancers. Saved servers come from
[Resources → On-prem services → Servers](servers.md). To make the choice permanent per stage, set
`provider.options.deploy.server`. Use one stage per machine to keep deployments apart.

The **Where functions run** section below the bar is the [placement editor](placement.md), and the **Firewall**
section is the [Firewall panel](firewall.md).

## Read the deploy steps of an on-prem deploy

On premises, deploy and remove output has two tabs: **Steps** and **Raw log**. **Steps** lists:

1. **Check & build**
2. **Terraform plan**
3. One step per placement group (or the single host): the group name, a **default** badge, where it runs, its
   endpoint and what it is doing
4. **Terraform apply** (remove: **Terraform destroy**)
5. **Load balancer** (when used)
6. **Firewall**: the ports each server must allow, with `ufw` commands
7. **Done**

Each step shows waiting, running, done, failed or cancelled; click it to see its output. A failed step shows
**Stopped here** (or "Deploying <group> failed") with the error and the end of the host's log. **Raw log** shows the
full output.

## Invoke a function or run a workflow locally

Two sections at the bottom of the studio Deploy page run code on this machine:

- **Invoke a function locally** (`pskit invoke`): pick the **Function**, the **Event** type (`default` = the
  function's first trigger, `http`, `schedule`, `queue`, `storage`, `topic`, `smtp`, `invoke`), the **Path** for
  HTTP, the **Payload (JSON)**, then **Invoke**.
- **Run a workflow locally** (`pskit workflow run --history`), when workflows exist: pick the **Workflow**, type the
  **Input (JSON)**, then **Run**.

The [Test page](test.md) has a fuller version of local and deployed tests.

## Review recent deploy jobs

The **Recent jobs** section lists the last jobs with their status (succeeded, running, cancelled, failed), the
command and when it started. Click one to show its output again; ✕ removes a finished job; **Clear finished** forgets
every finished job (running jobs are kept). Studio keeps the last 20 jobs in memory while it runs.

## See also

- [Deploy, remove and info](../deployment/deploy-remove-info.md)
- [All deployment types](../deployment/README.md) and [stages](../deployment/stages.md)
- [Placement](placement.md), [Firewall](firewall.md), [Scaling cluster](cluster.md)
- [Test page](test.md) and [Logs page](logs.md)
