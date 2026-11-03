# Monitoring and alerts in studio

Search terms: monitoring, live monitoring, CPU, memory, disk, replica lag, alerts, webhook, Slack, Teams, alert function, cooldown, server usage, container down, cluster full

Studio shows live CPU, memory and disk use of on-prem servers, service containers and cluster servers, and can alert
a function or a webhook when a limit is crossed. There is no Monitoring sidebar page; the panels sit next to what they
measure. For cloud monitoring and the deployment dashboard, see
[Monitoring and the dashboard](../deployment/monitoring-and-dashboard.md).

| Where | What it shows |
|---|---|
| Resources → Servers → **Live** | One server's CPU, RAM and disk, every 4 s |
| Resources → On-prem services → **Details** → **Live monitoring** | Every container of a service, connections, data size, replica lag |
| Resources → On-prem services → **Details** → **Alerts** | Alerts for one service |
| Scaling cluster → **Servers** and **When every server is full** | See [cluster.md](cluster.md#alert-when-every-cluster-server-is-full) |

## Watch a server's CPU, memory and disk in studio

The **Live** button on a row of the [Servers panel](servers.md) shows **CPU** (cores and load), **RAM** (total GB) and
**Disk** (of the `/` disk) bars for that server, refreshed every 4 s while it is on (**Live ●**). Click it again to
stop.

```bash
pskit resources onprem servers top app-1
```

## Watch a service's containers in studio

The **Live monitoring** switch in a service's **Details** turns on measuring ("On (every 5 s)"). Nothing is measured
while it is off.

1. Open **Resources** → **On-prem services** → **Details** on a service.
2. Turn on **Live monitoring**.
3. A table lists each container (members and load balancer of a replicated database) with **State**, **CPU**,
   **Memory** and **Disk (data)** bars. A bar shows the alert limit when alerts are on.

```bash
pskit resources onprem monitor orders-db --watch 5
```

## Turn on alerts for an on-prem service

The **Alerts** card in a service's **Details** (and the **Alerts** box when you create a database) sends an alert when
a container crosses a limit. The badge says **on** or **off**; "last check" shows the last result.

1. **Run a function**: **No function**, an existing function, or **+ Create a new function: <name>** (adds that
   function to `pskit.yml` with a handler stub; it gets `event.data = {kind, key, service, reasons, message,
   sample}`; deploy the project to run it).
2. **Webhook**: a Slack, Teams or Google Chat incoming webhook, or any URL; it gets the alert as JSON (`text` is the
   message).
3. Limits: **CPU %**, **Memory %**, **Disk %**, **Replica lag (s)** (replicated databases) and **Cooldown (min)**.
4. **Also when a container is down**.
5. Click **Turn alerts on** (later **Save**). **Turn off** keeps the settings. **Send a test alert** sends one now;
   **Check now** measures and alerts when over a limit.
6. The recent alerts are listed under the card.

When creating a database, the same fields sit behind **Alert me (optional): CPU, memory, disk, replica lag, a
container down**.

```bash
pskit resources onprem alerts orders-db --on --webhook https://hooks.slack.com/... --cpu 80 --cooldown 30
pskit resources onprem alerts orders-db --function notify-devops --test
pskit resources onprem alerts orders-db --check     # for cron
```

## See also

- [Replicas and alerts on a cluster](../onprem/scaling/replicas-and-alerts.md)
- [Scaling cluster page](cluster.md)
- [On-prem services panel](onprem-services.md) and [Servers panel](servers.md)
- [Monitoring and the dashboard](../deployment/monitoring-and-dashboard.md)
