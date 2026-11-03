# Stages: dev, staging and prod deployments

Search terms: stage, stages, environment, dev, staging, prod, production, --stage, -s, per-stage overrides,
stages:, ${opt:stage}, promote, separate deployments

A stage is one independent copy of your service: `dev`, `staging`, `prod`, or any name you choose. Each provider and
stage pair has its own Terraform workspace and state, its own cloud resource names and its own `deployment.json`.
Deploying `dev` never touches `prod`.

## Choose the stage for a command

The stage of a command comes from, first match wins:

1. the `-s` / `--stage` flag: `pskit deploy -s prod`;
2. `provider.stage` in `pskit.yml` (after `providers:` overrides);
3. `dev`.

A stage name is 1 to 16 characters: a lowercase letter first, then lowercase letters, digits or `-`
(`[a-z][a-z0-9-]{0,15}`). `Prod` or `my_stage` is rejected by `pskit validate`.

```bash
pskit deploy -s dev
pskit deploy -s staging
pskit deploy -s prod --confirm      # review the plan before applying to prod
pskit info -s prod
```

Every command that loads the project accepts `-s`: `validate`, `package`, `plan`, `deploy`, `remove`, `info`, `logs`,
`invoke`, `trigger`, `tf` and the `workflow` commands.

## Choose the stage in studio

Studio has two stage settings:

- **Top bar → stage**: the stage that **Validate**, the **Deploy** page, **Test** and **Logs** use. It starts with
  `provider.stage` from `pskit.yml` (or `dev`). Typing in it changes nothing in `pskit.yml`; studio lowercases the
  text and drops characters a stage can't have.
- **Overview & provider → Defaults for every function → Stage**: writes `provider.stage`, the default stage for the
  CLI.

Steps to deploy `prod` from studio:

1. In the top bar, type `prod` in **stage**.
2. Open **Deploy** in the sidebar and click **Deploy**.
3. Studio asks you to type `provider/prod` to confirm, because the stage starts with `prod`. Type it and confirm.

## Give each stage its own values with stages:

The `stages:` block holds overrides for one stage. When the active stage matches, its block is deep-merged over the
rest of the file: mappings merge key by key, lists are replaced.

```yaml
service: shop
provider:
  name: aws
  region: eu-west-1
  memory: 256
  environment:
    LOG_LEVEL: DEBUG
functions:
  api:
    handler: app.handlers.api
    events:
      - http: GET /items

stages:
  prod:
    provider:
      region: eu-central-1
      memory: 1024
      environment:
        LOG_LEVEL: WARNING
    functions:
      api: {concurrency: 50}
```

`pskit deploy -s prod` uses 1024 MB in `eu-central-1`; `pskit deploy -s dev` keeps 256 MB in `eu-west-1`. Studio has
no form for `stages:`; edit it on the **YAML** page. Full merge order: [settings and config](settings-and-config.md#merge-order-which-value-wins).

## Use the stage name inside values

`${opt:stage}` is the effective stage of the command. Use it to name things per stage:

```yaml
custom:
  table: ${self:service}-${opt:stage}-orders
provider:
  environment:
    TABLE_NAME: ${self:custom.table}
    API_BASE_URL: https://api-${opt:stage}.example.com
```

`${opt:stage, dev}` gives a default. Other variables: [settings and config](settings-and-config.md#use-variables-env-opt-self-file).

## Change one stage on one provider only

A stage block can name a provider again with `stages.<stage>.providers.<cloud>`. This is applied last, so it can
replace a stage value for one target. The common case: a remote state backend for `prod` on the clouds, but local
state when `prod` runs on premises.

```yaml
stages:
  prod:
    provider:
      state:
        backend: s3
        config: {bucket: acme-terraform-state, key: shop/prod.tfstate, region: eu-central-1}
    providers:
      onprem:
        region: local
        state: {backend: null}
```

## Where each stage lives

Each stage is kept apart in three places:

| Place | Per stage |
|---|---|
| Cloud resource names | `<service>-<stage>-<function>`, lowercased; long names get a stable hash |
| Local folder | `.pskit/<provider>-<stage>/` with its own bundle, `main.tf.json`, state and `deployment.json` |
| Tags | `pskit-service`, `pskit-stage`, `managed-by: py-serverless-kit` where the cloud supports tags |

So `aws` `dev`, `aws` `prod` and `gcp` `prod` are three deployments. The dashboard lists all of them on one page.

## Stages on premises: one stage per machine

On premises a stage remembers the server or cluster it was last deployed to
(`.pskit/onprem-<stage>/onprem_deployed.json`). `pskit logs`, `pskit trigger`, the dashboard and the studio Test and
Logs pages use that host. Give each machine its own stage, for example `dev` on this machine and `prod` on `edge1`:

```bash
pskit deploy -p onprem -s dev --server local
pskit deploy -p onprem -s prod --server edge1
```

Two stages on one server need different ports (`provider.options.port`), for example in `stages.dev.provider.options`.
Details: [deployment types](README.md#where-an-on-prem-deploy-goes-and-how-the-stage-remembers-it).

## Promote a change from dev to prod

Stages share the same code; only their overrides differ. A typical flow:

1. `pskit deploy -s dev`, then test: `pskit trigger -f api -s dev`, `pskit logs -s dev`.
2. `pskit plan -s prod` to read what would change in prod.
3. `pskit deploy -s prod --confirm` to apply exactly the reviewed plan.
4. `pskit info -s prod` for the prod URLs.

In CI, set a remote state backend for shared stages so every runner sees the same state. Example:
[`examples/15-ci-cd-deploy`](../../examples/15-ci-cd-deploy).

## Remove a stage

`pskit remove -s dev` destroys every resource of that stage only. Other stages and providers are not touched.
`--keep-resources` keeps buckets, queues and topics with their data. See
[deploy, remove and info](deploy-remove-info.md#remove-a-stage-with-pskit-remove).

## See also

- [Deployment types](README.md)
- [Settings and config](settings-and-config.md)
- [Deploy, remove and info](deploy-remove-info.md)
- Example: [`examples/10-stages-and-config`](../../examples/10-stages-and-config)
- Existing reference: [configuration.md](../configuration.md#stages-per-stage-overrides)
