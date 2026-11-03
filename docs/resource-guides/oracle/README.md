# Oracle Cloud (OCI) resources

How to attach OCI services you created in the [OCI console](https://cloud.oracle.com) to an OCI Functions deployment
made with pskit.

| `type` | OCI service | Trigger in pskit | Guide |
|---|---|---|---|
| `storage` | Object Storage bucket | ✓ Events rule | [storage.md](storage.md) |
| `queue` | OCI Queue | – (SDK only) | [queue.md](queue.md) |
| `topic` | Notifications topic | – (SDK only) | [topic.md](topic.md) |
| `database` | Autonomous Database, MySQL HeatWave | – | [database.md](database.md) |
| `cache` | OCI Cache (Redis / Valkey) | – | [cache.md](cache.md) |
| `custom` | Vault secrets, Streaming, any other service | – | [custom.md](custom.md) |

## Values you need for every OCI resource

| Value | Where |
|---|---|
| OCID | resource details page → *OCID* → **Copy** |
| Compartment OCID | **Identity & Security → Compartments** → the compartment → *OCID* |
| Region identifier | **Governance & Administration → Tenancy details**, or the region menu (for example `us-ashburn-1`) |
| Object Storage namespace | **Tenancy details** → *Object storage namespace* (also on every bucket's details page) |
| VCN / subnet OCIDs | **Networking → Virtual cloud networks** → the VCN → **Subnets** |

## How pskit runs on OCI (why some steps matter)

- All functions run in one **Functions application** attached to `provider.options.subnet_ids`. Databases, caches and
  other private endpoints are reachable when they are in (or routed from) that VCN and the security lists / NSGs
  allow the port.
- Environment variables (your `environment:` plus the `PSKIT_RESOURCE_*` bindings) become the function's
  **configuration**. They are visible in the console (function → **Configuration**) and stored in Terraform state.
  Keep real secrets in [Vault](custom.md#vault-secrets).
- Managed resources that no event uses are a validation error on OCI: create them in the console and declare them
  with `external: true`.
- The only event triggers on OCI are `http` and `storage`. Queues, topics, databases and caches are bound to functions
  and used through the OCI SDK or a client library.
- pskit creates no IAM policies. For functions to call OCI APIs **without keys**, use **resource principals**:
  1. **Identity & Security → Domains** → your domain (usually *Default*) → **Dynamic groups** → **Create dynamic
     group**, rule: `ALL {resource.type = 'fnfunc', resource.compartment.id = '<compartment OCID>'}`.
  2. **Identity & Security → Policies** → **Create Policy** with the statements each guide lists, for example
     `Allow dynamic-group pskit-functions to use queues in compartment <name>`.
  3. In the handler: `signer = oci.auth.signers.get_resource_principals_signer()`, then `Client(config={}, signer=signer)`.
- `pskit trigger` / `pskit resources send` can only send HTTP requests on OCI; for other types `--list` prints the
  console steps.

## Credentials for deploying

`~/.oci/config` (created by `oci setup config`), or `provider.options` `config_file_profile`, `tenancy_ocid`,
`user_ocid`, `fingerprint`, `private_key_path`. OCI Functions run container images: set `provider.options.image`, or
`image_repository` and let pskit build and push it.
