# Oracle Cloud (OCI) Functions provider

Search terms: oracle, OCI, Oracle Cloud Infrastructure, OCI Functions, Fn project, container image, OCIR,
image_repository, compartment_id, subnet_ids, API Gateway, Events rule, object storage, ~/.oci/config

The Oracle provider (`provider.name: oracle`) deploys each function as an **OCI Functions** function. OCI Functions run
**container images only**, so pskit writes a `Dockerfile` into the bundle and either uses an image you built or builds
and pushes one with your local Docker. Tier: **experimental**.

| Item | Value |
|---|---|
| Terraform plugin | `oracle/oci >= 6.0` |
| Default region | `us-ashburn-1` |
| Triggers | http (API Gateway), storage (Object Storage + Events). No schedule, queue or topic. |
| Workflows | embedded orchestrator function (capped by its timeout) |
| Python | `python3.9`, `python3.11` (default `python3.11`) |
| Node.js | `nodejs18`, `nodejs20` (`fnproject/node` images) |
| Max timeout | 300 s |
| Dependencies | installed inside the Docker build (`fdk` is added for Python, `@fnproject/fdk` for Node.js) |

## Set up Oracle Cloud credentials step by step

The OCI Terraform plugin reads `~/.oci/config` by default.

1. Install the OCI CLI (`pip install oci-cli`) and run `oci setup config`. It creates an API key, prints its public key
   and writes `~/.oci/config`. Upload the public key in the console: profile menu -> **My profile** -> **API keys** ->
   **Add API key**.
2. Find the values you need: **Identity & Security** -> **Compartments** -> your compartment -> *OCID* (for
   `compartment_id`), and **Networking** -> **Virtual cloud networks** -> your VCN -> **Subnets** -> *OCID* (for
   `subnet_ids`).
3. Pick how the image is made:
   - `image_repository`: install Docker, create an auth token (profile -> **Auth tokens** -> **Generate token**) and run
     `docker login <region-key>.ocir.io` (user `<namespace>/<user name>`, password = the token).
   - `image`: build and push the image yourself (steps below).
4. Optional environment: `OCI_COMPARTMENT_ID` (used by the scaffold as `${env:OCI_COMPARTMENT_ID}`),
   `OCI_CLI_CONFIG_FILE` (another config file).
5. Run `pskit doctor -p oracle` to check Terraform, the OCI CLI and the config file.

In studio, **Setup & credentials** -> **Provider** `oracle` shows the same checks and an **Environment variables**
section with **Set for this session**.

## Configure the oracle provider block in pskit.yml

These are all the Oracle options pskit reads:

```yaml
provider:
  name: oracle
  region: us-ashburn-1
  runtime: python3.11
  options:
    compartment_id: ocid1.compartment.oc1..aaaa        # required
    subnet_ids: [ocid1.subnet.oc1..aaaa]                # required (Functions application + default gateway subnet)
    image_repository: iad.ocir.io/mytenancy/orders      # pskit runs docker build + push (tag = artifact hash), OR
    # image: iad.ocir.io/mytenancy/orders:1.0           # an image you pushed yourself
    gateway_subnet_id: ocid1.subnet.oc1..bbbb           # optional, default: first of subnet_ids
    gateway_endpoint_type: PUBLIC                       # optional: PUBLIC (default) or PRIVATE
    # Terraform provider authentication (all optional; default ~/.oci/config, profile DEFAULT):
    config_file_profile: DEFAULT
    auth: APIKey
    tenancy_ocid: ocid1.tenancy.oc1..aaaa
    user_ocid: ocid1.user.oc1..aaaa
    fingerprint: aa:bb:...
    private_key_path: ~/.oci/oci_api_key.pem
```

| Option | Required | Meaning |
|---|---|---|
| `compartment_id` | yes | Compartment for the application, gateway, buckets and Events rules. |
| `subnet_ids` | yes | Subnets of the Functions application. |
| `image` / `image_repository` | one of them | Pre-built image, or a repository pskit builds and pushes to. |
| `gateway_subnet_id` | no | Subnet of the API Gateway. |
| `gateway_endpoint_type` | no | `PUBLIC` or `PRIVATE`. |
| `config_file_profile`, `auth`, `tenancy_ocid`, `user_ocid`, `fingerprint`, `private_key_path` | no | Copied into the Terraform `oci` provider block. |

`functions.<fn>.options` is merged into `oci_functions_function`. `provider.architecture: arm64` uses the
`GENERIC_ARM` shape and builds a `linux/arm64` image. Studio: **Overview & provider** -> **Oracle Cloud Functions
options** shows **Compartment OCID**, **Subnet OCIDs**, **Function image**, **Image repository**, **Gateway subnet
OCID** and **Gateway endpoint type**; set the authentication keys on the **YAML** page.

## Build the Oracle function image yourself

With `options.image`, build and push before `pskit deploy`. pskit writes the build context (bundle + `Dockerfile` +
`func.yaml` + `func.py` or `func.js`) when it packages:

```bash
pskit package -p oracle -s dev
docker login iad.ocir.io
docker build -t iad.ocir.io/mytenancy/orders:1.0 .pskit/oracle-dev/build
docker push iad.ocir.io/mytenancy/orders:1.0
pskit deploy -p oracle -s dev
```

With `options.image_repository`, a `terraform_data.image` resource runs
`docker build --platform linux/amd64 -t <repo>:<first 16 hex of the artifact hash> build && docker push ...` during
apply (`linux/arm64` with `architecture: arm64`), so a new image is built only when the code changes. Every function of the service uses the same image; the
pskit runtime picks the handler from `PSKIT_FUNCTION`.

## Terraform resources pskit creates on Oracle Cloud

| Resource | When |
|---|---|
| `terraform_data.image` | with `image_repository` (docker build + push) |
| `oci_functions_application` | once (all functions) |
| `oci_functions_function` | one per function; environment goes into `config` |
| `oci_apigateway_gateway` + `oci_apigateway_deployment` | when any http event exists; path prefix `/<service>` |
| data `oci_objectstorage_namespace` + `oci_objectstorage_bucket` (object events on) | per storage bucket unless `existing: true` |
| `oci_events_rule` | per storage event (action type `FAAS`) |

Resources get `freeform_tags` with `pskit-service`, `pskit-stage` and `managed-by`.

## How triggers map to Oracle Cloud services

| pskit trigger | OCI implementation |
|---|---|
| `http` | Route on the API Gateway deployment, backend `ORACLE_FUNCTIONS_BACKEND`. `{path+}` -> `{path*}`. With `cors`, `OPTIONS` is added to the route methods. Only `auth: none`. |
| `storage` | Events rule on `createobject` + `updateobject` (`created`) and `deleteobject` (`deleted`) for that bucket. Prefix / suffix cannot be filtered (warning): filter in the handler. An `existing` bucket must have **Emit Object Events** on (warning). |
| `schedule`, `queue`, `topic` | Not available (validation error). |

## Use resources on Oracle Cloud

A managed `storage` resource must be used by a trigger on OCI; any other service (Queue, Notifications, Autonomous
Database, OCI Cache, Vault) is created in the console and declared with `external: true`. Handlers reach it through
`PSKIT_RESOURCE_<KEY>_*` variables and the OCI SDK. Guides: [resource-guides/oracle/README.md](../../resource-guides/oracle/README.md).

## Run workflows on Oracle Cloud

OCI has no native workflow engine in pskit. Each workflow runs in a generated function `<workflow>-orchestrator` with an
HTTP route `POST /workflows/<name>` on the gateway; the run must finish within 300 s. Start one with
`pskit workflow start <name> -p oracle`. See [deployment/workflows.md](../../deployment/workflows.md).

## Find Oracle endpoints after deploy

`pskit info -p oracle` shows each function's OCID (`id`), the API Gateway deployment `endpoint` (it already contains
`/<service>`) as `base_url` for HTTP functions, and a console link. A route `GET /hello` is at `<endpoint>/hello`.

## Permissions on Oracle Cloud

pskit creates no IAM policies. Add these yourself (**Identity & Security** -> **Policies** -> **Create Policy**):

```text
ALLOW any-user to use functions-family in compartment <name> where ALL {request.principal.type = 'ApiGateway'}
```

and a similar statement for Events rules that invoke functions. Validation prints this warning whenever an http event
exists. For functions that call OCI APIs without keys, use resource principals (dynamic group + policy), as described
in [resource-guides/oracle/README.md](../../resource-guides/oracle/README.md).

## Read logs of an Oracle deployment

`pskit logs` and the studio **Logs** page cannot read OCI logs yet (*pskit can't read Oracle Cloud Functions logs yet.
Open the function's console link instead.*). Enable logs on the application in the console (Functions -> application
-> **Logs**) and use the `console` link from `pskit info`.

## Oracle limits and gotchas

- Container images only; Docker is needed on this machine for `image_repository`.
- No schedule, queue or topic triggers. HTTP `auth` must be `none` (check tokens in the handler).
- Max timeout 300 s, also for embedded workflows.
- Storage events cannot filter by prefix or suffix.
- `memory` per function is passed as `memory_in_mbs`; `func.yaml` uses `provider.memory`.

## Deploy to Oracle Cloud from the terminal

```bash
pskit doctor -p oracle
pskit validate -p oracle -s dev     # compartment, subnets, image, auth
pskit deploy -p oracle -s dev       # builds/pushes the image when image_repository is set
pskit info -p oracle -s dev
pskit remove -p oracle -s dev --yes
```

## Deploy to Oracle Cloud in studio

1. Run `pskit studio --open`.
2. **Overview & provider** -> **Provider** -> click **Oracle Cloud Functions** -> confirm the switch.
3. Fill **Compartment OCID**, **Subnet OCIDs**, and **Image repository** (or **Function image**). Click **Save**.
4. **Setup & credentials** -> check that the OCI config is found and Docker is installed.
5. **Deploy** -> **Deploy** -> confirm. The job log shows the Docker build and Terraform output.
6. **Info** shows the gateway URL. **Remove** destroys the stage after you type `oracle/<stage>`.

## Minimal Oracle Cloud example

```yaml
service: hello-oci
provider:
  name: oracle
  region: us-ashburn-1
  runtime: python3.11
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID}
    subnet_ids: ["${env:OCI_SUBNET_ID}"]
    image_repository: iad.ocir.io/mytenancy/hello-oci
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
```

## See also

- [Providers index](../README.md)
- [resource-guides/oracle/README.md](../../resource-guides/oracle/README.md)
- [triggers/http.md](../../triggers/http.md), [triggers/storage.md](../../triggers/storage.md)
- [deployment/deploy-remove-info.md](../../deployment/deploy-remove-info.md)
