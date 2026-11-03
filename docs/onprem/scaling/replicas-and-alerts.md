# Replicas, scaling and capacity alerts for a cluster

Search terms: replicas, web replicas, scale, pskit cluster scale, capacity, cluster full, alert, DevOps alert,
webhook, Slack, cluster status, watch, cron

A scaling cluster runs one **main** replica on the master and a number of **web** replicas spread over the servers.
This page explains how to change the number of web replicas, how pskit measures whether the cluster is full, and
how to get an alert (one of your functions, a webhook, or both) when it is.

## Set the number of web replicas for a cluster deployment

The number of web replicas of a cluster deployment comes from `provider.options.cluster.replicas` (1..500, default
2). Every replica also reserves CPU (`cpu`, default 0.25 cores) and memory (`memory`, default 256 MB). The
reservations decide how many replicas fit on a server.

**In studio**

1. Open **Scaling cluster** and select the cluster.
2. With **Deploy this project's functions to prod** on, set **Web replicas**, **CPU per replica** and
   **Memory per replica (MB)**.
3. Save the project, then deploy. The value is kept for every later deploy.

**From the terminal**, edit `pskit.yml` and deploy:

```yaml
provider:
  name: onprem
  options:
    cluster: {name: prod, replicas: 4, cpu: 0.5, memory: 512}
```

## Scale a cluster deployment now, without a deploy

Scaling a cluster deployment now changes the running web replicas at once. It lasts until the next deploy, which
uses `options.cluster.replicas` again.

**In studio**: in the **Deployed functions** card, change the number in **Web replicas** for the deployment and
click **Scale**. The **Running** column shows `web: running/desired`.

**From the terminal**

```bash
pskit cluster scale prod --replicas 6                      # this project's stage
pskit cluster scale prod --replicas 0 --stack pskit-shop-dev   # another deployment on the cluster
```

`--replicas` takes 0..500. On Nomad there is at most one web replica per joined server, so join servers to go
higher.

## Watch the servers of a cluster: CPU, memory, disk, replicas

The cluster status shows each server's CPU (over one second), memory and disk with the limits, the orchestrator's
view (ready, drained, offline), each deployment's running and desired replicas, and replicas that cannot be placed.

**In studio**: the **Scaling cluster** page refreshes every 30 seconds. Click **Refresh** to check now. A server over
a limit shows a **full** badge; a green line says "Capacity left on N of M server(s)".

**From the terminal**

```bash
pskit cluster status prod            # --json for scripts
pskit cluster list                   # every cluster, its servers and deployments
pskit resources onprem servers top edge2   # live use of one saved server
```

## When a cluster counts as full

A scaling cluster counts as **full** when any of these holds:

* every reachable, schedulable server is over a limit (default CPU 85 %, memory 85 %, disk 90 %);
* replicas cannot be placed: no server has the CPU or memory a replica reserves;
* no server is ready.

In the studio a red banner "The cluster is full" lists the reasons and the replicas that cannot be placed, with a
**+ Join a server now** button. The fix is to [join a server](docker-swarm.md#join-a-server-to-a-docker-swarm-cluster)
and then raise the replicas.

## Set up capacity alerts when a cluster is full in studio

Capacity alerts call one of your functions and / or POST to a webhook when the cluster is full, at most once per
cooldown (default 30 minutes).

1. Open **Scaling cluster**, scroll to the **When every server is full** card.
2. Set **CPU full at %**, **Memory full at %**, **Disk full at %**.
3. Pick an **Alert function** (a function of this project, deployed on any on-prem stage) and optionally its
   **Stage**.
4. Optionally enter a **Webhook (optional)** URL (Slack, Teams, Google Chat or any URL).
5. Set **Cooldown (minutes)**.
6. Turn on **Watch while the studio runs** and set **every (seconds)** (default 60).
7. Click **Save**, then **Send test alert** to try it. **Check & alert** on the cluster card checks now.
8. Sent alerts are listed under **Recent alerts**.

## Set up capacity alerts when a cluster is full from the terminal

The `pskit cluster alerts` command stores the same alert settings.

```bash
pskit cluster alerts prod --function notify-devops --stage prod --webhook https://hooks.slack.com/services/XXX
pskit cluster alerts prod --cpu 80 --memory 90 --disk 90 --cooldown 30
pskit cluster alerts prod --test          # send a test alert now
pskit cluster alerts prod --function ""   # clear the function ("" also clears --webhook)
```

Checks run where pskit runs. Without the studio open, run one of these on an always-on machine:

```bash
pskit cluster watch prod --interval 60    # until Ctrl+C (systemd unit, tmux, ...); 15..86400 seconds
pskit cluster check prod                  # once, for cron; exit status 3 when full
pskit cluster check prod --no-alert       # status only
```

## Write an alert function for a full cluster

The alert function gets the capacity event in `event.data`: `type` (`pskit.cluster.capacity`), `test`, `cluster`,
`orchestrator`, `full`, `subject`, `message`, `reasons`, `nodes` (server, role, cpu, memory, disk, over, ...),
`workloads`, `pending`, `capacity` and `checked_at`. The webhook body has `text` plus the same fields.

```python
import json
import os
from urllib.request import Request, urlopen


def notify_devops(event, ctx):
    alert = event.data
    lines = [alert["message"]] + [
        "{0}: cpu {1}% memory {2}% disk {3}%".format(n["server"], n["cpu"], n["memory"], n["disk"])
        for n in alert["nodes"]
    ]
    body = json.dumps({"text": "\n".join(lines)}).encode("utf-8")
    req = Request(os.environ["CHAT_WEBHOOK"], data=body, headers={"Content-Type": "application/json"})
    urlopen(req, timeout=10).read()
    return {"sent": True}
```

A mail example with `smtplib` is in [cluster.md](../../cluster.md#alert-devops-optional).

## Follow live requests and logs across cluster servers

The **Live requests** card on **Scaling cluster** lists each request with the **server** and **replica** that
handled it, method, path, status, duration and function, plus each server's URL and its share of HTTP. Turn
**Live** on to poll every 2 seconds. The **Live logs** card tails the selected deployment.

```bash
pskit cluster requests prod --follow     # -n 50 for more history, --stack for another deployment
pskit logs -f                            # the whole cluster, as on one machine
```

## Alerts for on-prem services and databases

On-prem services (including replicated databases) have their own alerts for CPU, memory, disk, replica lag and a
container down. See [Database scaling](../database-scaling.md#monitor-a-replicated-database-and-alert-on-lag).

## See also

* [Scaling options compared](README.md)
* [Docker Swarm](docker-swarm.md), [Kubernetes (k3s)](kubernetes-k3s.md), [Nomad](nomad.md)
* [Load balancers](../load-balancers.md)
* Reference: [cluster.md](../../cluster.md#monitor-scale-and-add-servers-when-it-is-full)
