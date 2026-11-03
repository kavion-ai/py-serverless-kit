# Function groups on different servers (placement)

Search terms: placement, function groups, split functions, different servers, GPU server, group, default group,
gateway, invoke between servers, peer, cross-server calls, Runs on, pskit function split, own folder

Placement splits one on-prem project's functions into **groups**, each running on its own saved server, scaling
cluster, or this machine, with only its own code and dependencies. The groups still work as one project: they call
each other, share workflows, queues and topics, and send their logs to one place. Placement is set in
`provider.options.placement`.

## When to use function groups

Function groups solve problems a single host or a cluster cannot:

* one function needs special hardware (GPU, lots of memory) and the rest do not;
* two functions need conflicting library versions;
* a heavy batch job should not slow down the API;
* a part of the project must run on a cluster while the rest stays on one server.

To serve **more of the same** traffic, use a [scaling cluster](scaling/README.md) instead. Groups and clusters
combine: a group can run on a cluster.

## The placement settings in pskit.yml

`provider.options.placement` has three keys: `default`, `groups` and `gateway`.

```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    placement:
      default: api                      # functions not listed, and every workflow, run here
      gateway: true                     # optional: every group answers every route
      groups:
        api:   {server: app1}
        gpu:   {server: gpu1, functions: [resize, ocr]}
        batch: {cluster: prod, functions: [report]}          # or {cluster: {name: prod, replicas: 3}}
        tools: {local: true, functions: [dev-tool], port: 8081}
```

| Group key | Meaning |
|---|---|
| `server` / `cluster` / `local: true` | where the group runs: one of them (the default group may leave it out and use `options.deploy` or `--server`) |
| `functions` | the functions in this group; a function is in at most one group |
| `port` | the group's port; needed when two groups share a server |
| `advertise` | the URL the other groups call (`http://HOST:PORT`) when the server's own address is not reachable |

Group names are a lowercase letter, then letters, digits or `-` (up to 21). A function that orchestrates a workflow
must stay in the default group.

## Split functions across servers in studio (Deploy page)

The studio edits placement on the **Deploy** page, in the **Where functions run** box.

1. Open **Deploy**. In **Where functions run** pick **Split functions across servers** (instead of **All functions
   on one target**).
2. Each group has a card. Set **Group name**, **Runs on** (**This machine (local)**, a server under **Saved servers**,
   or a cluster under **Scaling clusters**; the default group can keep **The deploy target above**), and optionally
   **Port** and **Advertise URL**.
3. Under **Functions (N of M)** tick the functions of the group (**All here** / **None** for all at once).
4. Click **+ Add group** for another group. **Make default** makes a group the default; **Remove group** moves its
   functions to the default group. **Move functions to another group** with **Group to move to** and **Move** moves
   several at once.
5. Tick **One URL: every group answers every route and passes other groups' routes on** if you want one address
   (see [Give the project one URL](#give-a-split-project-one-url-gateway)).
6. Save and deploy. After the deploy each group shows its endpoint.

## Put one function in a group in studio (Functions page)

The **Functions** page has a **Runs on** field per function.

1. Open **Functions** and edit a function.
2. In **Runs on** pick an existing group, or **+ New group…**.
3. For a new group fill **Group name** and **Runs on** (**Saved server**, **Cluster** or **This machine**), plus
   **Port** when two groups share a server. The first time, **Other functions** names the default group that keeps
   the rest.
4. Save. The function shows a badge with its group.

## Split functions from the terminal

From the terminal, edit `provider.options.placement` in `pskit.yml` and deploy. One deploy applies every group.

```bash
pskit validate            # checks groups, ports, queues and shared code files
pskit deploy              # every group in one Terraform apply
pskit info                # each group's endpoint and functions
pskit firewall            # the ports the groups need between them
```

`--server NAME` and `--cluster NAME` move only the default group; other groups run where `pskit.yml` puts them.

## Give each function its own folder and requirements

With placement, each server installs only the requirements of its own functions. A function's sub-project is the
nearest folder above its handler with a `requirements.txt` (Python) or `package.json` (Node.js); the project's
`requirements.txt` is installed everywhere.

Functions whose handlers share one file are stripped per server (other handlers and the imports only they use are
removed from that group's bundle), and validation warns. Splitting them is cleaner:

```bash
pskit function split get-item create-item     # or: pskit function split --all --dry-run
```

In the studio: **Functions → Own folder**. Python only; move a Node.js handler by hand. Details:
[placement.md](../placement.md#each-function-is-its-own-sub-project).

## How function groups call each other

Every group is an independent host. Each knows where every function lives (a peer map) and calls other groups over
HTTP at `/__pskit/peer/<function>` with a shared token (`x-pskit-token`, kept in `.pskit/onprem-<stage>/peer-token`,
out of git). Your code does not change:

```python
from py_serverless_kit import invoke


def upload(event, ctx):
    # runs on group api; resize lives on group gpu (another server)
    result = invoke("resize", {"key": event.data["key"], "width": 800})
    return {"thumbnail": result["key"]}
```

| You do | What happens |
|---|---|
| `invoke("resize", ...)` on group `api` | runs on `gpu`; the result, or the error with its type, comes back |
| a workflow step that is a function in another group | runs there; `Retry` / `Catch` match its error type by name |
| start a workflow on any group | it runs and is recorded on the default group |
| send to a built-in queue whose consumer is on `gpu` | stored on `gpu`, consumed there |
| publish to a topic with subscribers on two groups | delivered on both |
| read or write a built-in bucket | on the group whose function it triggers (else the default group) |
| `pskit logs`, the studio's **Logs** | the default group receives every group's logs and counts |

A built-in queue or bucket belongs to one group, so its consumers must be in that group. To share one across
groups, give it a driver every server reaches (`redis`, `sqs`, `s3`, ...). A forwarded request is never forwarded
again.

## Give a split project one URL (gateway)

By default each group answers only its own HTTP routes; a route of another group gets a `404` naming that group's
URL. With `placement.gateway: true` every group answers every route and passes other groups' routes on.

Behind a load balancer (`options.balancer`, or a group cluster with a load balancer) `gateway` is on unless you set
it to `false`, and the load balancer gives the project one route `/<service>/` to the servers of every group. A load
balancer attached to clusters reaches only those clusters' servers; see [Load balancers](load-balancers.md).

## Ports between function groups

The group hosts call each other on their ports, so open every group host's port to every other group host (a full
mesh), and the default group's port for logs and workflow starts. See
[Firewall rules for function groups](firewall.md#firewall-rules-for-function-groups-placement).

## See also

* [Scaling options compared](scaling/README.md)
* [Load balancers](load-balancers.md), [Firewall rules](firewall.md), [Network map](network-map.md)
* Reference: [placement.md](../placement.md)
