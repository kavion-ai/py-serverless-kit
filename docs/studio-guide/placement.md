# Placement (Where functions run) in studio

Search terms: placement, function groups, split functions across servers, runs on, default group, GPU server, gateway, one URL, provider.options.placement, group port, advertise URL

Placement splits an on-prem project's functions over several servers, clusters or this machine: each group is its own
host with only its functions. Studio edits `provider.options.placement` in two places: the **Where functions run**
section of the [Deploy page](deploy.md) (target provider `onprem`) and the **Runs on** field of the
[function wizard](functions.md). How placement works is in [On-prem placement](../onprem/placement.md).

## Split functions across servers in studio

The **Where functions run** section on the Deploy page (hint `provider.options.placement`) turns placement on.

1. Open **Deploy** with the top bar on `onprem`, and open **Where functions run**.
2. Pick **Split functions across servers** (instead of **All functions on one target**). Studio creates groups.
3. Each group card has:
   - the **Group name** (editable);
   - a **default** badge or a **Make default** button: functions not ticked in another group, and every workflow,
     run in the default group;
   - **Runs on**: **This machine (local)**, a saved server, or a scaling cluster. Empty on the default group = the
     machine or cluster picked in **Run on** above;
   - **Port** (needed when two groups share a server) and **Advertise URL** (the address other groups call, when it
     differs from the server's);
   - **Functions (N of M)**: tick functions to move them into this group. Unticking functions in a group offers
     **Move <functions> to** another group with **Move** / **Cancel**;
   - **Remove group** (its functions move to the default group).
4. **+ Add group** adds a group on the first saved server (or this machine).
5. **One URL: every group answers every route and passes other groups' routes on** (`placement.gateway`): on = any
   server can take any request; off = each server answers only its own functions' routes. It is on by default behind
   a load balancer.
6. Press **Save**, then **Deploy**. The Run on bar then shows "Split over N groups" and each group's target.

Each server installs only what its functions need (the `requirements.txt` of their `functions/<name>/` folders).
Functions call each other, queues, buckets, workflows and HTTP routes across servers automatically. Logs of every
group show on the default group.

```yaml
provider:
  name: onprem
  options:
    placement:
      default: api
      groups:
        api: {server: app-1}
        gpu: {server: gpu-1, functions: [resize, classify]}
```

The exact YAML shape is in [On-prem placement](../onprem/placement.md) and [placement reference](../placement.md).

## Pick where one function runs (Runs on)

The **Runs on** field in step 1 of the function wizard (on premises) picks the placement group of one function.

- With placement: pick a group, or **Where the project deploys (the deploy target)**.
- **+ New group…** opens a box: **Other functions** (the name of the default group for every other function),
  **Group name**, **Runs on** (**Saved server** with a server picker or **+ Add a server**, **Cluster**, or **This
  machine**) and **Port** (two groups on one server need different ports).
- The function list shows each function's group as a badge.

The review step shows the change to `provider.options.placement` in the diff.

## See where groups were deployed

After a deploy, the Run on bar on the Deploy page and the Overview's on-prem section show the deployed groups: a
table of **Group**, **Where**, **Endpoint** and **Functions**, and, when used, the **Load balancer** and **URL**. The
deploy steps view shows one step per group.

## See also

- [On-prem placement](../onprem/placement.md)
- [Deploy page](deploy.md)
- [Functions page](functions.md)
- [Give a function its own folder](functions.md#give-a-function-its-own-folder-in-studio)
