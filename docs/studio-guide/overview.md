# Overview & provider page in studio

Search terms: overview, provider, switch provider, change cloud, region, runtime, memory, timeout, architecture, log retention, environment variables, tags, provider options, packaging, on-prem deployment, saved server, deploy method, host tuning

The **Overview & provider** page holds service-wide settings. Every function inherits them unless it overrides
them. Sidebar: **Overview & provider** (◎). Everything here edits the `service:`, `provider:`, `providers:` and
`package:` sections of `pskit.yml`.

## Rename the service in studio

The **Service** section has one field, **Service name** (`service:` in `pskit.yml`): 2 to 32 lowercase letters,
digits or dashes. Renaming a deployed service creates new cloud resources on the next deploy.

## Switch the provider in studio

The **Provider** section shows the same provider cards as the New project page (chips for HTTP, Schedule, Queue,
Storage, Topic, SMTP, Native workflows). The provider's notes appear under the cards.

1. Click another provider's card.
2. Studio opens **Switch to <Provider>?**:
   - If something will not run there, it lists "These won't run on <Provider>:" (up to 12 items) and offers
     **Switch & disable on <Provider>** and **Switch only (fix later)**.
   - If everything is supported, it says so and offers **Switch provider**.
3. **Switch & disable on <Provider>** writes `enabled: false` (or a reduced trigger list) only under
   `providers.<new provider>`, so the other clouds keep those triggers and workflows.
4. In both cases the old `provider.options` and `provider.region` move to `providers.<old provider>`, so switching back
   restores them. A runtime the new provider does not offer is cleared. Handler code does not change.
5. The top bar's **validate & deploy as** follows the new provider. Press **Save**.

The written result, switching from AWS to GCP:

```yaml
provider:
  name: gcp
  region: us-central1
providers:
  aws:
    region: eu-west-1
    options: {}
```

From the terminal, edit `provider.name` in `pskit.yml`, or try another provider without editing it:
`pskit validate -p gcp`.

## Fix "providers.<cloud> overrides a setting" in studio

When `pskit.yml` has a `providers.<current provider>` block that overrides values shown on this page, a yellow box
says those values win when deploying and lists them. **Use the values shown here** moves them under `provider:`
(keeping settings only the override has). Save afterwards.

## Set defaults for every function in studio

The **Defaults for every function** section writes `provider.*` keys:

| Field | `pskit.yml` key | Notes |
|---|---|---|
| **Region** | `provider.region` | A list of the provider's regions, or free text; empty = provider default |
| **Stage** | `provider.stage` | `dev`, `test`, `staging`, `prod` or your own (lowercase, up to 16) |
| **Runtime** | `provider.runtime` | Python and Node.js versions the provider supports |
| **Memory (MB)** | `provider.memory` | 64 to 32768; default 256 MB |
| **Timeout (s)** | `provider.timeout` | Up to the provider's maximum (shown); default 30 s |
| **Architecture** | `provider.architecture` | `x86_64` (default) or `arm64` |
| **Log retention (days)** | `provider.log_retention_days` | Default 14 days |

Changing **Runtime** between Python and Node.js when functions exist asks **Switch the service to Node.js?** (or
Python): a service is either Python or Node.js; existing handlers stay as they are and new functions get stubs in
the new language.

## Set environment variables and tags for every function

The **Environment variables** section ("available to every function") edits `provider.environment` as key/value rows.
Names must match `[A-Za-z_][A-Za-z0-9_]*`. Use `${env:NAME}` for secrets instead of literal values. The **Tags**
section edits `provider.tags` (**Add tag**).

## Set provider options in studio

The **<Provider> options** section (hint `provider.options`) shows the provider's own options: for example the GCP
project, the Azure subscription, the Oracle compartment or the Cloudflare account id. Required options are marked.
Each provider's options are listed in [Providers](../providers/README.md).

## Change packaging in studio

The **Packaging** section (closed by default, hint `package`) edits `package:`:

| Field | Key | Default |
|---|---|---|
| **Source directory** | `package.source` | `.` (relative to `pskit.yml`) |
| **Requirements file** | `package.requirements` | `requirements.txt` |
| **Exclude globs** | `package.exclude` | e.g. `tests/**`, `*.md` |
| **Vendor dependencies** | `package.vendor` | provider decides; on = force `pip install` into the bundle, off = skip |

## Choose where the on-prem host runs in studio

The **On-premises deployment** section (hint `provider.options.deploy`) appears when the provider is `onprem`. It
edits `provider.options.deploy`.

1. **Saved server**: pick a server saved under [Resources → On-prem services → Servers](servers.md), or
   **+ Add a server…** / **+ Add server** to open the server form. A saved server writes
   `deploy: {method: ssh, server: NAME}` (or `docker`); its host, user, port and login come from the saved server.
   **None: use the method below** clears it.
2. **Where the host runs**: **This machine** (`local`), **SSH server** (`ssh`: scp plus a process or systemd) or
   **Docker** (a container, locally or on a server over SSH).
3. The fields under it depend on the method:

   | Method | Fields |
   |---|---|
   | This machine | Python, Target OS, Target arch, Node.js, Node.js archive URL / SHA-256, Host Python |
   | SSH server | SSH host (required), SSH user, SSH port, Private key (with **Browse…**), Known hosts, Use sudo, Remote path, Install as, Python, Target OS / arch, CPython archive URL / SHA-256, Node.js fields |
   | Docker | Image, Container name, Docker host, Restart policy, Publish, Extra docker args, the SSH fields (optional), Install Docker on the server, Target OS / arch |

4. With an SSH server (or Docker with a host) and no saved server, **Test SSH connection** runs
   `ssh user@host echo pskit-ok` and shows **connected** or **failed: see the log**.

A badge shows where this stage is deployed now, and the deployed function groups. Missing `ssh`, `scp` or Docker on
this machine are checked on [Setup & credentials](setup.md).

The written YAML for a saved server:

```yaml
provider:
  name: onprem
  options:
    deploy:
      method: ssh
      server: app-1
```

From the terminal: `pskit deploy --server app-1` deploys to a saved server once; the YAML above makes it permanent.
Details: [on-prem servers](../onprem/servers.md) and [on-prem provider](../providers/onprem/README.md).

## Configure built-in services and host tuning for on-prem

The **Built-in services** section (hint `provider.options.services`) sets where on-prem queues, buckets and topics
live. For each of **Queue**, **Storage** and **Topic** choose **Built-in** (folders the host creates) or **Existing
folder** with a path such as `/var/pskit/queues`. To attach an external queue or bucket per resource, use the
[Resources page drivers](resources.md#pick-an-on-prem-driver-for-a-resource).

The **Host tuning** section (closed by default) edits `provider.options` keys of the on-prem host:
`execution_retention` (default 500), `workflow_workers` (8), `log_buffer` (5000), `log_level` (`INFO`; DEBUG to
CRITICAL) and `capture_output` (on).

## See also

- [Setup & credentials](setup.md)
- [Providers](../providers/README.md) and [on-prem provider](../providers/onprem/README.md)
- [Function configuration](../functions/configuration.md)
- [Stages](../deployment/stages.md)
- [Placement](placement.md)
