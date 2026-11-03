# Project-wide settings: layering, variables, secrets and local settings

Search terms: pskit.yml, config, configuration, extends, providers overrides, stages overrides, variables, ${env},
${opt}, ${self}, ${file}, ${tf}, .env, env_file, secrets, escape hatch, terraform extra, pskit doctor, setup check,
credentials, pskit settings export, import, move to another machine

This page covers the features that apply to the whole `pskit.yml` and the whole project: where pskit finds the
config, how files and overrides are layered, variables, secrets and `.env` files, escape hatches into Terraform,
the setup check (`pskit doctor`), and moving local settings to another machine (`pskit settings`). The key-by-key
reference is [configuration.md](../configuration.md).

## Where pskit finds pskit.yml

pskit looks in the current folder for `pskit.yml`, `pskit.yaml`, `serverless_kit.yml` or `serverless_kit.yaml`, in
that order. Pass `-c FILE` to use another file: `pskit deploy -c pskit.gcp.yml`. Unknown keys are rejected, so a typo
fails at once with the path of the bad key.

```yaml
service: orders          # required: 2-32 chars, lowercase letters, digits and -, starts with a letter
provider: {...}          # required: name, region, stage, runtime, memory, timeout, environment, options, ...
package: {...}           # what goes into the bundle
functions: {...}
workflows: {...}
resources: {...}
hooks: {...}             # shell commands around package / deploy / remove
custom: {...}            # free-form values for ${self:custom.x}
providers: {...}         # per-cloud overrides
stages: {...}            # per-stage overrides
extends: base.yml        # inherit another file
```

In studio, every page writes this file. The **YAML** page shows and edits it directly. Click **Save** (Ctrl+S) to
write it; the **Deploy** page asks you to save before it runs a command.

## Inherit another file with extends

`extends` makes one file start from another. Use it to keep a shared base and one small file per cloud or team.

```yaml
# pskit.gcp.yml
extends: pskit.yml            # or a list: [base.yml, team.yml]
provider:
  name: gcp
  options: {project: my-proj}
```

```bash
pskit deploy -c pskit.gcp.yml -s dev
```

Relative paths resolve from the extending file. A circular `extends` is an error.

## Override values for one cloud with providers:

The `providers:` block holds overrides per provider. Only the block of the active provider (`provider.name` or
`-p`) is used; it is deep-merged into the config. Inside a block, provider keys (`region`, `stage`, `runtime`,
`memory`, `timeout`, `architecture`, `environment`, `tags`, `iam`, `log_retention_days`, `options`, `state`,
`terraform`) can be written directly, as a shorthand for `provider: {...}`.

```yaml
provider:
  name: aws
  region: us-east-1
providers:
  gcp:
    region: europe-west1
    options: {project: my-proj}
  azure:
    region: westeurope
    functions:
      create-order: {memory: 1024}
```

One file now deploys to three clouds: `pskit deploy -p aws`, `-p gcp`, `-p azure`. In studio, the provider picked in
**Overview & provider** writes `provider.name`; the top bar's **validate & deploy as** picks the target for one run.

## Switch a function, trigger or workflow off on one cloud

Not every cloud runs every trigger. Keep the item for the other clouds and turn it off only where it can't run:

```yaml
providers:
  cloudflare:
    functions:
      thumbnails: {enabled: false}            # not deployed to Cloudflare
      api: {events: [{http: GET /orders}]}    # on Cloudflare, api gets only this trigger (lists replace)
    workflows:
      order-pipeline: {enabled: false}
```

`pskit validate` reports disabled functions and workflows as warnings; a workflow that calls a disabled function is
an error. In studio the **Deploy** page lists what can't run on the target with **Disable trigger on PROVIDER**,
**Disable function on PROVIDER**, **Disable workflow on PROVIDER** and **Disable all of them on PROVIDER**; items
already switched off show **Enable again** or **Use the normal triggers**.

## Override values for one stage with stages:

The `stages:` block holds overrides for one stage, used when the active stage (`-s`, else `provider.stage`, else
`dev`) matches. `stages.<stage>.providers.<cloud>` changes one stage on one provider only. Examples and the stage
rules: [stages](stages.md).

## Merge order: which value wins

pskit builds the final config in this order; later wins:

1. For each file of the `extends` chain, parents first: that file's own values, then that file's
   `providers.<active provider>` block. So a child file's values beat its parent's per-provider overrides.
2. `stages.<active stage>`, merged across all files (the child wins).
3. `stages.<active stage>.providers.<active provider>`.
4. CLI flags: `--provider`, `--stage`, `--region`.

Mappings are deep-merged key by key. Lists are replaced, not appended. Variables are resolved after the merge.

## Use variables: env, opt, self, file

Variables fill values in when the config is loaded.

| Syntax | Resolves to |
|---|---|
| `${env:NAME}` | the environment variable `NAME`; an error when it is not set |
| `${env:NAME, default}` | the variable, or `default` (an empty default is allowed: `${env:KEY, }`) |
| `${opt:stage}`, `${opt:provider}`, `${opt:region}` | the effective values of the command (`${opt:stage, dev}` allowed) |
| `${self:dotted.path}` | any value of the merged config, e.g. `${self:service}`, `${self:custom.table}` |
| `${file(path.json)}` | a file relative to the config: `.json` / `.yml` parsed, other files as stripped text |

```yaml
custom:
  table: ${self:service}-${opt:stage}-orders
  limits: ${file(config/limits.json)}
provider:
  name: aws
  region: ${env:AWS_REGION, eu-west-1}
  memory: ${self:custom.limits.dev.memory}     # a whole-value variable keeps its type (an int here)
  environment:
    TABLE_NAME: ${self:custom.table}
```

Variables can nest; all unresolved ones are reported together. Two forms are left alone: `${tf:...}` becomes a live
Terraform reference (see below), and any other `${...}`, such as `${aws:username}` in an IAM policy, stays literal.
Every other `${` in your values is escaped, so Terraform never reads it.

## Keep secrets out of pskit.yml

Don't write passwords or keys in `pskit.yml`. Use one of these instead:

- `${env:NAME}` for values that CI or your shell provides at deploy time: `PAYMENT_API_KEY: ${env:PAYMENT_API_KEY, }`.
- `${tf:...}` to reference a secret manager resource created in `provider.terraform.extra`.
- On premises: `provider.options.env_file` (default `.env.onprem`). It holds `KEY=VALUE` lines that are copied next to
  the host and loaded when it starts; they never go into Terraform state. On-prem services pskit creates write their
  passwords there.
- Handlers read secrets at run time with `get_secret` (see [handlers.md](../handlers.md)).

`${env:...}` reads the environment of the process that runs pskit. In studio, **Setup & credentials** →
**Environment variables** → **Set for this session** sets a variable for deploys started from that studio until it
stops; nothing is written to disk.

## Use a .env file for local runs

`pskit dev` and `pskit invoke` load a `.env` file from the project root into the function's environment
(`KEY=VALUE` lines, `#` comments, optional quotes, an optional `export ` prefix). Pick another file with
`--env-file`:

```bash
pskit dev --env-file .env.local
pskit invoke -f hello --env-file .env.test
```

`.env` and `.env.*` are never packed into the bundle. They are not read by `pskit deploy` either: export the values
in your shell or CI, and reference them with `${env:...}`.

## Reach Terraform directly with escape hatches

When pskit doesn't model something, these escape hatches pass raw values to Terraform:

| Need | Use |
|---|---|
| An argument pskit doesn't model (VPC, layers, tracing, ...) | `functions.<fn>.options`, merged into the provider's function resource |
| Provider-level settings | `provider.options` (per provider: [providers](../providers/README.md)) |
| Extra cloud resources (tables, buckets, alarms, outputs) | `provider.terraform.extra`: raw Terraform JSON, deep-merged |
| Reference those resources | `${tf:<expression>}` in `iam.statements`, `environment`, ... |

```yaml
provider:
  name: aws
  terraform:
    extra:
      resource:
        aws_dynamodb_table:
          orders: {name: orders-${opt:stage}, billing_mode: PAY_PER_REQUEST, hash_key: id,
                   attribute: [{name: id, type: S}]}
functions:
  create-order:
    handler: app.orders.create
    environment:
      TABLE_NAME: ${tf:aws_dynamodb_table.orders.name}
    options:
      tracing_config: {mode: Active}
```

`provider.terraform` also takes `binary` (default: `terraform`, then `tofu`; or `PSKIT_TERRAFORM_BIN`),
`required_version` and `provider_version`. On premises, `terraform.extra` resources of other clouds are left out with
a warning. Example: [`examples/11-custom-terraform`](../../examples/11-custom-terraform).

## Check tools and credentials with pskit doctor

`pskit doctor` checks what this machine needs to deploy to a provider and tells you how to fix what's missing, for
Windows, macOS and Linux. It runs only local, fast checks: tools on `PATH`, credentials in environment variables and
the standard config files. It never prints a secret.

```bash
pskit doctor                  # the provider in pskit.yml
pskit doctor -p azure         # works without a pskit.yml
pskit doctor -p onprem --json
```

| Check | For |
|---|---|
| Python, Terraform (or OpenTofu) | every provider |
| the cloud CLI (`aws`, `az`, `gcloud`, `aliyun`, `tccli`, `hcloud`, `oci`, `ibmcloud`, `doctl`, `wrangler`) | clouds; optional, used to sign in |
| credentials | clouds: environment variables, profiles, sign-in files |
| required `provider.options` (for example the GCP project) | clouds that need them |
| optional Python packages | clouds: let studio browse resources and read logs |
| deploy method, `ssh` and `scp`, SSH host and key, Docker CLI and daemon | on premises, by `options.deploy.method` |

Each line starts with a mark: `✓` ready, `✗` missing, `!` to check, `i` optional (`+` and `x` on terminals that
can't print `✓` and `✗`). Missing items print how to fix them for this OS. The exit code is 1 when anything required
is missing, so CI can stop early.

## Fix setup problems in studio on Setup & credentials

The studio **Setup & credentials** page runs the same checks and can fix several of them in place.

1. Click **Setup & credentials** in the sidebar.
2. Pick the **Provider** and the **Operating system** (guessed from your browser). The badge says *ready to deploy
   to PROVIDER*, *N missing* or *N to check*.
3. In **Checks**, click **How to fix** on a row for links, steps for your OS and commands with **Copy**. Some rows
   have an action button: **Sign in (az login)**, **Sign in (gcloud)**, **Sign in (gcloud ADC)**,
   **Sign in (aws sso)**, **Test connection** (SSH), **Add credentials** or **Set variables**.
4. AWS: **AWS credentials (aws configure)** writes `~/.aws/credentials`: **Profile**, **Access key ID**, **Secret
   access key**, **Default region**, **Session token**, then **Save profile**.
5. **Environment variables**: type a value and click **Set for this session**, or **Clear**.
6. On premises: **On-premises connection** sets **Where the host runs** (*This machine*, *SSH server*, *Docker*) and
   its fields. Save pskit.yml afterwards.
7. Click **Check again** at the top after a fix.

## Move local settings to another machine

`.pskit/` is git-ignored, so a fresh clone has no saved servers, clusters, load balancers, on-prem services or SSH
logins. `pskit settings export` packs them into one passphrase-encrypted file; `pskit settings import` writes them
into the project on the other machine.

```bash
pskit settings export -o prod.pskit-settings                # asks for a passphrase twice (at least 8 characters)
pskit settings export --with-config                         # also include pskit.yml
pskit settings import prod.pskit-settings --dry-run         # only show what would change
pskit settings import prod.pskit-settings                   # merge; the file's entries win
pskit settings import prod.pskit-settings --replace         # also drop entries the file does not have
PSKIT_SETTINGS_PASSPHRASE=... pskit settings import prod.pskit-settings --yes   # from a script
```

The default file name is `<service>.pskit-settings`. Import backs up the current settings to `.pskit/backups/`
first and prints where.

## What the settings file holds and how it is protected

The settings file holds:

- saved servers, scaling clusters, load balancers and on-prem services, with service passwords and tokens
  (`.pskit/onprem-servers.json`, `onprem-clusters.json`, `onprem-balancers.json`, `onprem-services.json`);
- SSH passwords typed in studio (`.pskit/ssh/`) and the SSH key files the servers point to, also those outside the
  project such as `~/.ssh/edge.pem` (copied into `.pskit/ssh/keys/` on import);
- where each on-prem stage was last deployed (`onprem_deployed.json`, `deployment.json`), so `pskit logs`, tests,
  `info` and studio reach it right away;
- studio test events, and env files named by `env_file` in `pskit.yml` (inside the project only);
- `pskit.yml` itself with `--with-config`.

It never holds Terraform state: on-prem deploys don't need it, and a cloud stage's state belongs in a remote backend
([deployment types](README.md#share-terraform-state-with-a-team)).

The file is always encrypted: scrypt derives the keys from your passphrase, and the content is authenticated, so a
wrong passphrase or a changed file is refused before anything is written. Send the passphrase another way than the
file.

## Move settings in studio

The settings export and import are also in studio, in two places: the **⇅ Settings** button in the top bar (drawer
*Import / export settings and config*) and the bottom of **Setup & credentials** (*Move settings to another machine*).

1. Export: type the **Passphrase** and **Again**, keep or clear *Include pskit.yml (functions, resources, providers)*,
   click **Export settings**. The browser downloads the file and lists what is in it.
2. Import on the other machine: pick the **Settings file**, type the **Passphrase**, click **Preview**.
3. Read the table: **Settings**, **Added**, **Replaced**, **Kept** (or **Removed** with the *Replace* switch on).
4. Click **Import into this project** and confirm. When the file brought `pskit.yml`, studio reloads the project.

## See also

- [Deployment types](README.md)
- [Stages](stages.md)
- [Deploy, remove and info](deploy-remove-info.md) (keeping buckets, queues and topics on remove)
- [On-prem servers](../onprem/servers.md)
- Existing reference: [configuration.md](../configuration.md)
- Example: [`examples/10-stages-and-config`](../../examples/10-stages-and-config)
