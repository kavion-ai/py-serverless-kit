# Functions on several servers (on premises)

By default every function of a project runs in one host: on one machine, or on every server of a
[cluster](cluster.md). **Placement** splits them: each group of functions runs on its own server (or cluster),
with only its own code and dependencies, and the groups work together as one project.

```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    placement:
      default: api                      # functions not listed here, and every workflow, run in this group
      groups:
        api:   {server: app1}           # a saved server
        gpu:   {server: gpu1, functions: [resize, ocr]}
        batch: {cluster: prod, functions: [report]}             # a scaling cluster ({name: prod, replicas: 3})
        local: {local: true, functions: [dev-tool], port: 8081} # this machine
```

Per group: one of `server`, `cluster` or `local: true` (the default group may leave it out and use
`options.deploy` / `--server` as before), `functions`, and optionally `port` (needed when two groups share a
server) and `advertise` (the URL the other groups call, when the server's own address is not reachable).

The studio's **Deploy** page has the same editor ("Where functions run"), and each function shows where it runs.

## Each function is its own sub-project

Create functions in their own folder with their own dependencies:

```
functions/
  resize/
    __init__.py
    handler.py            # handler: functions.resize.handler.main
    requirements.txt      # Pillow, ... only what resize needs
  report/
    index.js              # handler: functions.report.index.main
    package.json          # Node.js: its own node_modules
```

The studio does this for new functions ("Own folder with its own requirements.txt"). A function's sub-project is
the nearest folder above its handler with a `requirements.txt` (Python) or `package.json` (Node.js).

* Every cloud: the sub-projects' requirements are added to the bundle, so the code runs unchanged anywhere.
* On premises with placement: **each server installs only the requirements of its functions**, and the folders of
  functions placed elsewhere are left out of its bundle. Two functions on one server that pin conflicting versions
  fail the deploy with a clear message: place them on different servers.
* Node.js sub-projects get their own `node_modules` in their folder, so each function resolves its own versions.

### Requirements: global plus per function

Each server installs:

* the project's `requirements.txt` (global: what every function needs), and
* the `requirements.txt` of each of **its** functions' folders (`functions/<name>/requirements.txt`), never those of
  functions placed elsewhere.

### Functions that share a code file

Each server's copy of a shared code file holds only the handlers of its own functions: pskit removes the others
(and the imports only they used) from that group's bundle; your source is not changed. Module-level helpers stay.
`pskit_host.json` on the server lists what was removed (`stripped`). Moving them to their own folders is still
cleaner, and gives each its own requirements:

Functions whose handlers sit side by side in one file (`app/handlers.py` with `hello`, `get_item`,
`create_item`, as `pskit init` makes them) are shared code. Validation warns when they are in different groups.
Split them:

```bash
pskit function split get-item create-item     # or: pskit function split --all --dry-run
```

```
get-item: app/handlers.py -> functions/get_item/handler.py (handler functions.get_item.handler.get_item)
  copied helpers: _ITEMS (still in app/handlers.py for the others)
```

The function, the module-level helpers and imports it uses (relative imports made absolute) move to
`functions/<name>/handler.py`. Its `requirements.txt` gets the lines of the project's `requirements.txt` that its
imports name, and its handler in `pskit.yml` is updated. Helpers are copied, not moved, so a module-level value
such as a dict is no longer shared between the split functions; it never was across servers. The function stays
in the shared file too if code there still calls it. In the studio: **Functions → Own folder**. Python only: move
a Node.js handler by hand.

When you create a function in the studio, its **Runs on** field picks the group, or creates one: a saved server, a
cluster or this machine, and a port when two groups share a server.

## How the groups work together

Every group is an independent host. Each one knows where every function lives and calls the others over HTTP
with a shared secret (`.pskit/onprem-<stage>/peer-token`, out of git):

| You do | What happens |
|---|---|
| `invoke("resize", data)` in a function on `api` | runs on `gpu`, the result (or the error, with its type) comes back |
| an HTTP request to `api` for a route of `resize` | `404` with the URL on `gpu` (each server answers only its own routes); with `placement.gateway: true` (on by default behind a load balancer that reaches both groups) `api` passes it to `gpu` |
| a **workflow** step that is a function on another server | runs there; `Retry` / `Catch` match its error type by name |
| start a workflow on any group | it runs (and is recorded) on the default group; executions stay in one place |
| send to a built-in queue whose consumer runs on `gpu` | the message is stored on `gpu` and its consumer runs there |
| publish to a topic with subscribers on two groups | delivered on both |
| read / write a built-in bucket | on the group whose function it triggers (else the default group) |
| `pskit logs`, the studio's logs | the default group receives every group's logs and invocation counts |

Rules that keep this simple:

* A built-in queue or bucket belongs to **one** group: its consumers must be in that group. To share one across
  groups, give it a driver every server reaches (`redis`, `sqs`, `s3`, ...); validation tells you.
* Workflows always run on the default group; their steps run wherever their functions are.
* A request already forwarded by a group is never forwarded again (no loops when configs disagree).

The group hosts call each other on their ports: open them between the servers ([network and firewall
rules](onprem-network.md#4-functions-on-several-servers-provideroptionsplacement)).

## Deploy, URLs and load balancers

`pskit deploy` deploys every group in one Terraform apply (`terraform_data.host` for the default group — the same
resource as before, so adding placement to a deployed stage moves nothing — and `terraform_data.host_<group>` for
the others; unit `pskit-<service>-<stage>-<group>`, folder `onprem_app_<group>`, data (queues, buckets, logs) in
`<data_dir>/groups/<group>`). `pskit info` and
`deployment.json` list each group's endpoint and functions.

Each server answers only the HTTP routes of the functions it runs; a route of another group gets a `404` that
names the group and its URL. For one URL for the whole project, let every server answer every route:

```yaml
    placement:
      gateway: true        # every group answers every route, passing other groups' routes on
```

With `options.balancer: edge` `gateway` is on unless you set it to `false`: that load balancer gives the project
one route (`/<service>/`) to the servers of **every** group, and a request that lands on another group's server is
passed on to the right group.

A load balancer attached to a cluster (`pskit lb attach edge --cluster prod`), or a cluster's own load balancer,
reaches only the servers of the clusters it serves. Unless `gateway` is set, a group's servers then pass on only the
routes of the groups behind the **same** load balancer. So with groups on clusters `c1` and `c2`, both attached to
`edge`, `http://edge/<service>/<route>` works for the functions of both; with only `c1` attached, it serves only
`c1`'s functions, and a route of a group on `c2` or on a server gets the `404` naming that group's URL.

`--server NAME` / `--cluster NAME` move the default group only; the other groups always run where `pskit.yml`
puts them.
