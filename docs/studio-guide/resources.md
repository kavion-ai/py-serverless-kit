# Resources page in studio

Search terms: resources page, add resource, bucket, queue, topic, database, cache, custom, smtp, managed, external, browse account, on-prem driver, connection, bound functions, test a resource, resource data, in the cloud, kept resources, resource guides, how to use

The **Resources** page declares the buckets, queues, topics, databases, caches and other services your functions use,
once for every cloud. Sidebar: **Resources** (▤); the number counts resources. It edits `resources:` (and, for
on-prem drivers on another provider, `providers.onprem.resources`). The page also holds the
[On-prem services](onprem-services.md) panel with the [Servers](servers.md) panel, the **Test a resource** section and
the **In the cloud** section.

## Read the resources table in studio

The studio resources table has one row per resource. Click a row to edit it.

| Column | What it shows |
|---|---|
| **Resource** | The key (`resource("key")` in handlers) and the native name |
| **Type** | `storage`, `queue`, `topic`, `database`, `cache`, `custom` or `smtp` |
| **Mode** | **managed** or **external**, plus `on-prem <service> · <server>` when a one-click service backs it |
| **On-prem driver** | The on-prem driver, or `builtin` |
| **Bound to** | Functions that use it: ⚡ = through a trigger; others through code that calls `resource("key")`. Below: `functions: N of M`, or "variables available to all N functions" |

Row buttons: **How to use**, **DNS guide** (SMTP services), **Data** (on-prem queue, storage and topic),
**Test** and **Delete**. Header buttons: **Guides**, **+ SMTP server**, **+ On-prem service** and
**+ Add resource**.

When a one-click on-prem service exists that is not in `pskit.yml`, a box "On-prem services not in the resource list
yet:" shows a **+ <key> (<service>)** button per service; it adds the resource (and its triggers) to the draft.

## Add a resource in studio

The studio **Add resource** drawer declares one resource.

1. Click **+ Add resource**.
2. **Key** (required): how handlers refer to it (`resource("key")`) and how triggers use it (`resource: key`).
3. **Type**: `storage`, `queue`, `topic`, `database`, `cache`, `custom` or `smtp`.
4. **Mode**: **Managed by pskit** (pskit creates it on deploy and removes it with `pskit remove`; only for storage,
   queue, topic and smtp) or **External / existing** (it already exists or runs elsewhere; pskit never creates or
   deletes it).
5. **Native name**: managed = defaults to the key (pskit adds service and stage where the provider needs it);
   external = the exact name. For external storage, queues and topics, **Browse account…** lists what exists (see
   [trigger forms](trigger-forms.md#pick-an-existing-queue-bucket-or-topic-from-your-cloud-account)).
6. **Connection**: key/value pairs handed to handlers as `PSKIT_RESOURCE_<KEY>_<NAME>`. Use `${env:VAR}` for secrets,
   never a literal password.
7. **Bound functions**: tick functions; none ticked = every function (generated orchestrators excluded).
8. **Provider-specific options** (folded): `resources.<key>.options` for the main provider.
9. Click **Add** (**Apply** when editing). Press **Save**.

For a type without on-prem drivers, a **<type> guide** button opens the step-by-step guide for the provider. When
adding a queue, bucket, database, cache or custom resource, a box offers **Create a <type> on premises** (a one-click
Docker service; see [onprem-services.md](onprem-services.md)).

```yaml
resources:
  uploads:
    type: storage
  orders-db:
    type: database
    external: true
    connection: {url: "${env:ORDERS_DB_URL}"}
    functions: [api]
```

## Pick an on-prem driver for a resource

The **On-premises driver** box in the resource drawer appears for queue, storage and topic resources. It sets where the
on-prem host reads the resource from.

- When the provider is `onprem`, it is stored in `resources.<key>.options`. On another provider it goes to
  `providers.onprem.resources.<key>.options`, so the main provider is not affected.
- Drivers are grouped by cloud. Queues: Built-in (files), Directory, Redis, Redis / Valkey stream, Amazon SQS, Azure
  Storage Queue, Google Pub/Sub, Alibaba Cloud MNS, Cloudflare Queues, Another on-prem host, Custom class. Storage:
  Built-in (folder), Directory, S3 / S3-compatible, Amazon S3, Alibaba OSS, Tencent COS, Huawei OBS, Oracle Object
  Storage, IBM Cloud Object Storage, DigitalOcean Spaces, Cloudflare R2, MinIO, Wasabi, Backblaze B2, Akamai (Linode),
  Scaleway, Azure Blob Storage, Google Cloud Storage, Custom class. Topics: Built-in, Directory.
- Each driver shows its own fields. A secret field can instead be read from an environment variable on the host
  (`<key>_env`).
- **Custom class**: **Class** (`package.module:ClassName`) and **Constructor arguments** (keyword arguments; a key
  ending in `_env` is read from the host's environment). Queue classes implement submit / claim / settle / depth /
  recover, storage classes scan / put / get / delete (see `examples/19-custom-drivers`).
- **How to set up a <type>** opens the on-prem guide.

More: [On-prem resources and drivers](../onprem/resources.md) and
[cloud resources for on-prem functions](../onprem/cloud-resources.md).

## Delete a resource in studio

**Delete** on a resource row asks **Delete resource <key>?**. Triggers that use it are named; they stop validating
until you change them. What the dialog offers depends on the resource:

| Resource | Buttons |
|---|---|
| Backed by a one-click on-prem service | **pskit.yml only**, **Stop service, keep data**, **Delete service and data** |
| Built-in on-prem queue / bucket / topic | **Delete, keep data**, **Delete with its data** (clears it on the host) |
| Managed cloud resource | **Delete**: the next deploy deletes it in the cloud with its data (or delete it now under **In the cloud**) |
| External resource | **Delete**: nothing is deleted in the cloud |

Bound functions lose its `PSKIT_RESOURCE_*` variables.

## Open the How to use guide of a resource

**How to use** on a resource row opens an end-to-end guide for that resource, for the top bar's provider and stage,
built from the saved `pskit.yml`: the library to install for Python and Node.js, the `pskit.yml` and trigger, handler
code, local tests (`pskit invoke`, `pskit dev`), deployed tests and provider notes. On premises it adds complete
client programs. **Copy guide** copies it as Markdown; **Test it** jumps to the tester. The terminal shows the same:

```bash
pskit resources usage jobs -p onprem -s dev
```

## Test a resource in studio

The **Test a resource** section (or **Test** on a row) sends a message to a queue, uploads an object to a bucket or
publishes to a topic, for managed resources (after deploy) and external ones (right away). It reads the saved
`pskit.yml`.

1. **Resource**: pick one (`key · type name (external / managed)`). **Used by** lists the bound functions.
2. **Test connection** checks that the resource is reachable and shows **OK** or **Failed** with the time. The help
   names where it is checked from and the terminal command.
3. Edit the **Message** or **Object** JSON (**Reset to sample** restores the sample).
4. Click the action button: **Send a message** (queue), **Upload an object** (bucket) or **Publish a message**
   (topic). Confirm with **Send**; this is real, and bound functions with a trigger on it receive it.
5. **How to test** shows the same three ways: **In the studio**, **Terminal** (pskit and the cloud CLI with copy
   buttons) and **<Provider> console** (click-by-click).
6. **Use it in a handler** shows Python / Node.js code and the library to add.

For database, cache and custom resources, studio does not send anything: it lists the `PSKIT_RESOURCE_*` variables
and a Python and Node.js snippet; then call that function from the [Test page](test.md) (Direct invoke).

```bash
pskit resources send jobs -d '{"order_id": 1}'
pskit resources check orders-db
pskit resources send --list -p aws -s dev
```

## Browse the data of an on-prem queue, topic or bucket

**Data** on a resource row (on-prem target) opens **Data in <key>**, read by the deployed on-prem host. Messages are
looked at, not consumed.

- Buckets: a **prefix** filter, a table of **Key** and **Size**, **Preview**, **Delete** and paging.
- Queues and topics: **Message**, **Body** (click to expand) and **Info**, and **Delete** on built-in queues.
- **Refresh** reloads. Drivers that cannot be listed show a note and, when known, how many are waiting.

```bash
pskit resources data jobs --offset 0 -n 20
pskit resources clear jobs --yes      # delete the data of a built-in queue, bucket or topic
```

## Delete deployed or kept cloud resources in studio

The **In the cloud (<provider> / <stage>)** section (closed by default) lists the buckets, queues and topics pskit
created for the top bar's provider and stage, from the Terraform state.

1. Click **Load** (it runs `terraform init` and reads the state). **Refresh** reloads.
2. Each row shows **deployed** or **kept** (left by Remove with the keep switch), the kind, name and address.
3. Delete one with **Delete**, tick several and use **Delete selected (N)**, or **Delete all kept (N)**.
4. The dialog lists them and says everything in them is deleted permanently. Type `delete` and click
   **Delete permanently**. Deployed ones still in `pskit.yml` come back on the next deploy.

```bash
pskit resources list -s dev
pskit resources delete aws_s3_bucket.b_uploads -s dev
```

## Read the resource guides inside studio

**Guides** (page header) opens **Resource guides**: the step-by-step guides of `docs/resource-guides` for every cloud.
Pick the cloud ("General (all clouds, compatibility)", "On premises", AWS, ...) and the page (**Overview**, **Existing
cloud code**, or a resource type). The resource drawer's guide buttons open the right page directly.

## See also

- [Resources reference](../resources.md) and [resource usage](../resource-usage.md)
- [On-prem services panel](onprem-services.md) and [Servers panel](servers.md)
- [On-prem resources](../onprem/resources.md) and [cloud resources on premises](../onprem/cloud-resources.md)
- [Trigger forms](trigger-forms.md)
- [Resource guides](../resource-guides/README.md)
