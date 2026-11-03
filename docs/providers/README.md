# Providers: where pskit deploys your functions

Search terms: provider, cloud, capability matrix, tier, stable beta experimental, switch provider, providers override,
multi-cloud, pskit providers, entry point, third-party provider, plug-in, which cloud, compare clouds

A **provider** is the place pskit deploys a service to: one of ten clouds or your own servers (`onprem`). You pick it
with `provider.name` in `pskit.yml`, with `--provider` on the command line, or with the provider cards in studio. Your
handler code is the same on every provider; only `pskit.yml` changes.

| Provider | Name in `pskit.yml` | Page |
|---|---|---|
| AWS Lambda | `aws` | [aws/README.md](aws/README.md) |
| Azure Functions | `azure` | [azure/README.md](azure/README.md) |
| Google Cloud Functions (2nd gen) | `gcp` | [gcp/README.md](gcp/README.md) |
| Alibaba Cloud Function Compute 3.0 | `alibaba` | [alibaba/README.md](alibaba/README.md) |
| Tencent Cloud SCF | `tencent` | [tencent/README.md](tencent/README.md) |
| Huawei Cloud FunctionGraph | `huawei` | [huawei/README.md](huawei/README.md) |
| Oracle Cloud (OCI) Functions | `oracle` | [oracle/README.md](oracle/README.md) |
| IBM Cloud Code Engine functions | `ibm` | [ibm/README.md](ibm/README.md) |
| DigitalOcean Functions | `digitalocean` | [digitalocean/README.md](digitalocean/README.md) |
| Cloudflare Workers | `cloudflare` | [cloudflare/README.md](cloudflare/README.md) |
| On-premises (your machine or servers) | `onprem` | [onprem/README.md](onprem/README.md) |

## Provider capability matrix (triggers, workflows, runtimes)

The provider capability matrix below is printed by `pskit providers` from the installed version. Run
`pskit providers --json` for the machine-readable form (it also lists `notes` and the Terraform plugin).

| Provider | Tier | http | schedule | queue | storage | topic | smtp | Workflows | Python | Node.js | Max timeout | Default region |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `aws` | stable | yes | yes | yes | yes | yes | - | native (Step Functions) | 3.9-3.13 | 18, 20, 22 | 900 s | `us-east-1` |
| `azure` | stable | yes | yes | yes | yes | yes | - | embedded, native opt-in (Logic Apps) | 3.9-3.12 | 18, 20, 22 | 600 s | `eastus` |
| `gcp` | stable | yes | yes | yes | yes | yes | - | native (Cloud Workflows) | 3.9-3.13 | 18, 20, 22 | 3600 s | `us-central1` |
| `alibaba` | beta | yes | yes | - | yes | yes | - | embedded | 3.9, 3.10, 3.12 | 18, 20 | 3600 s | `cn-hangzhou` |
| `tencent` | beta | yes | yes | - | yes | - | - | embedded | 3.9, 3.10 | 18 | 900 s | `ap-guangzhou` |
| `huawei` | beta | yes | yes | - | yes | yes | - | embedded | 3.9, 3.10, 3.12 | 18 | 900 s | `cn-north-4` |
| `ibm` | beta | yes | - | - | - | - | - | embedded | 3.11 | 18, 20 | 120 s | `us-south` |
| `digitalocean` | beta | yes | yes | - | - | - | - | embedded | 3.9, 3.11 | 18 | 900 s | none |
| `oracle` | experimental | yes | - | - | yes | - | - | embedded | 3.9, 3.11 | 18, 20 | 300 s | `us-ashburn-1` |
| `cloudflare` | experimental | yes | yes | - | - | - | - | embedded | 3.11-3.13 | 18, 20, 22 (JavaScript) | 900 s | none |
| `onprem` | experimental | yes | yes | yes | yes | yes | yes | embedded (in the host, no timeout cap) | 3.9-3.14 | 18, 20, 22, 24 | 3600 s | `local` |

- A trigger marked `-` is a validation error on that provider, for example *IBM Cloud Code Engine does not support
  `queue` events in pskit (supported: http)*.
- "embedded" means pskit adds a function `<workflow>-orchestrator` that runs the workflow with its own engine. On a
  cloud, that run is capped by the function timeout (validation warns). See
  [deployment/workflows.md](../deployment/workflows.md).
- The smtp trigger (mail received by an SMTP server) exists only on premises. See [triggers/smtp.md](../triggers/smtp.md).
- With no `runtime` in `pskit.yml`, pskit uses `python3.12`, or the newest Python the provider has below it (for
  example `python3.11` on IBM). Node.js defaults to `nodejs20`, or the newest version below it.

## Provider tiers: stable, beta and experimental

The provider tier tells you how much the generated Terraform has been tested.

| Tier | Meaning |
|---|---|
| stable | Validated against the real provider plugin; the full trigger set works. |
| beta | Passes `terraform validate`; event payloads follow the vendor documentation. |
| experimental | Works with notable constraints (container images, Pyodide, or a process on your own servers). Read the provider page first. |

Studio shows the tier as a badge (`beta`, `experimental`) on each provider card in **Overview & provider**. Stable
providers have no badge.

## Pick a provider for your project

Use the provider capability matrix and these questions to pick a provider:

1. **Which triggers do you need?** Queues work on `aws`, `azure`, `gcp` and `onprem` only. Topics also on `alibaba`
   and `huawei`. IBM Code Engine has HTTP only.
2. **Do you need long workflows?** Native engines (`aws`, `gcp`, `azure` with `engine: native`) and `onprem` are not
   capped by one function's timeout. Everywhere else the whole workflow must finish inside the orchestrator's timeout.
3. **Do you need third-party Python packages?** Cloudflare Python Workers run on Pyodide: only the standard library and
   Pyodide's built-in packages. Everywhere else `requirements.txt` is installed.
4. **No cloud account, or your own hardware?** Use `onprem`: one long-running process on this machine, a server over
   SSH, Docker, or a scaling cluster. See [onprem/README.md](onprem/README.md).
5. **Need tooling on this machine?** Run `pskit doctor -p <provider>`. It lists the missing tools (Terraform, the cloud
   CLI, Docker for Oracle, `doctl` for DigitalOcean) and how to install them.

## Switch a project to another provider in studio

Switching provider in studio keeps your old settings so you can switch back.

1. Run `pskit studio --open` in the project folder.
2. In the sidebar, click **Overview & provider**.
3. In the **Provider** section, click the card of the new provider (for example **IBM Cloud Code Engine**).
4. A dialog **Switch to IBM Cloud Code Engine?** opens:
   - If everything is supported, it says *Every function, trigger and workflow is supported on ...*. Click
     **Switch provider**.
   - If some triggers or workflows are not supported, it lists them. Click **Switch & disable on IBM Cloud Code Engine**
     to switch them off only for that provider (written under `providers.ibm`), or **Switch only (fix later)**.
5. The current `provider.options` and `provider.region` move to `providers.<old provider>` in `pskit.yml`. Saved
   options of the new provider (from `providers.<new provider>`) move back under `provider:`.
6. Fill the new section **<Provider> options** (for example **IBM Cloud Code Engine options**) on the same page.
7. Click **Save** in the top bar (or press Ctrl+S).

To deploy to another provider for one run without changing `provider.name`, use the top bar selector
**validate & deploy as** and the **stage** field. The **Deploy** page then runs as that provider and stage.

## Switch provider from the terminal

From the terminal you switch provider for one command with `--provider` (`-p`):

```bash
pskit validate -p huawei            # check the config against Huawei
pskit deploy -p cloudflare -s dev   # deploy this stage to Cloudflare
pskit info -p cloudflare -s dev
pskit remove -p cloudflare -s dev --yes
```

Each provider and stage has its own Terraform workspace and state in `.pskit/<provider>-<stage>/`, so deploying the
same project to two providers does not mix them. To change the default, edit `provider.name` in `pskit.yml`.

A new project for a provider: `pskit init my-api -p digitalocean`. It writes `provider.name`, the default region and
the required options as `${env:...}` placeholders (see each provider page).

## Override settings per provider with `providers:` in pskit.yml

The `providers:` block holds per-provider overrides. When a provider is selected, its block is deep-merged over the
rest of the file. Keys of `provider:` (`region`, `runtime`, `memory`, `timeout`, `options`, ...) may be written
directly under the provider name:

```yaml
service: shop
provider:
  name: aws
  region: eu-west-1
functions:
  report:
    handler: app.report.handler
    events:
      - schedule: {rate: 1 hour}
providers:
  ibm:
    runtime: python3.11            # same as provider: {runtime: python3.11}
    options:
      resource_group: Default
    functions:
      report:
        events: []                 # lists are replaced, not merged: no schedule on IBM
  onprem:
    options: {host: 127.0.0.1, port: 8088}
```

Merge order (later wins): `extends:` files, the file itself, `providers.<name>`, `stages.<stage>`, then
`stages.<stage>.providers.<name>`, then CLI flags (`--provider`, `--stage`, `--region`). Dictionaries merge key by key;
lists and plain values are replaced. An unknown name under `providers:` is an error that lists the known providers.

Studio shows a warning on **Overview & provider** when `providers.<current provider>` overrides a value shown on that
page (those values win when deploying). Click **Use the values shown here** to move them under `provider:`, then
**Save**. See [deployment/stages.md](../deployment/stages.md) for `stages:`.

## Switch triggers and workflows off on one provider

To keep a trigger on most clouds but drop it on one, set the function's events for that provider only. To skip a
function or workflow on one provider, use `enabled: false` under `providers.<name>`:

```yaml
providers:
  cloudflare:
    functions:
      worker: {enabled: false}       # not deployed on Cloudflare
    workflows:
      nightly: {enabled: false}
```

In studio, the **Deploy** page does this for you: when the target provider cannot run something, a dialog
**Not available on <Provider>** lists it. **Disable on <Provider> and deploy** writes these overrides and saves;
**Deploy anyway** runs the command as is (it fails validation).

## Add a third-party provider with an entry point

pskit loads providers from the `py_serverless_kit.providers` entry-point group, so another package can add a cloud
without changing pskit. A provider subclasses `py_serverless_kit.providers.base.Provider`, sets `name`, `capabilities`,
`runtimes` and `max_timeout`, and implements `shim_files()` and `render_resources()` (which must emit the `pskit`
Terraform output). Register it in your package:

```toml
[project.entry-points."py_serverless_kit.providers"]
mycloud = "pskit_mycloud:MyCloudProvider"
```

After `pip install` of that package, `pskit providers` lists `mycloud`, and `provider: {name: mycloud}` or
`--provider mycloud` selects it. A provider name is 2-32 characters: a lowercase letter, then letters, digits, `_` or
`-`. New providers start as `tier = "experimental"`. The full example is in
[architecture.md](../architecture.md#third-party-providers); the contributor checklist is in
[`deploy_docs/CONTRIBUTING.md`](../../deploy_docs/CONTRIBUTING.md).

## Settings common to every provider

These provider settings work on every provider; each provider page lists what it does with them.

| Key | Meaning |
|---|---|
| `provider.region` | Region; the provider's default region when empty. |
| `provider.runtime`, `memory`, `timeout`, `architecture` | Defaults for every function (a function can override them). |
| `provider.environment`, `tags` | Variables for every function; tags or labels where the cloud has them. |
| `provider.iam` | `statements` (AWS) or `role` (an existing role, agency or service account). |
| `provider.options` | Provider-specific settings (see each provider page). |
| `functions.<fn>.options` | Merged into that function's Terraform resource: an escape hatch for any argument. |
| `provider.state` | Terraform backend (`backend`, `config`); local state in `.pskit/<provider>-<stage>/` by default. |
| `provider.terraform.extra` | Extra Terraform JSON merged into the generated `main.tf.json`. |

Resources are tagged `pskit-service`, `pskit-stage` and `managed-by: py-serverless-kit` where the cloud has tags.
Full key reference: [configuration.md](../configuration.md).

## See also

- [guide/concepts.md](../guide/concepts.md): provider, stage, service and the other words used here
- [deployment/README.md](../deployment/README.md): every deployment type
- [deployment/deploy-remove-info.md](../deployment/deploy-remove-info.md): deploy, info and remove in detail
- [triggers/README.md](../triggers/README.md): trigger x provider matrix with the details of each trigger
- [resource-guides/README.md](../resource-guides/README.md): attach cloud services you already have
- [providers.md](../providers.md): the older one-page provider reference
