# Logs page in studio

Search terms: logs, live logs, tail logs, log viewer, log level filter, log streams, delete logs, CloudWatch, Cloud Logging, Log Analytics, on-prem logs, pskit logs, function logs

The **Logs** page shows the logs of the functions deployed to the provider and stage in the top bar. Sidebar:
**Logs** (☰). Logs are read with this machine's credentials (see [Setup & credentials](setup.md) when they cannot be
read). It does the same as `pskit logs`. Where logs come from on each cloud is in [Logs](../deployment/logs.md).

| Provider | Source |
|---|---|
| On premises | The host's buffer: handlers, print output, invocations |
| AWS | CloudWatch Logs (needs boto3) |
| GCP | Cloud Logging (needs `google-cloud-logging`, read only) |
| Azure | Log Analytics, when a `log_analytics_workspace_id` output exists |
| Others | Use the console link from `pskit info` |

## Watch live logs in studio

The studio log viewer tails the deployed functions' logs.

1. Pick the provider and stage in the top bar, then open **Logs**.
2. On premises, the bar at the top picks the **Server** to read from (default: the server this stage was deployed to).
   When its port (default 8080) is closed to this machine, the logs are read over SSH. On a cluster or with several
   placement groups, the bar says **Source**: every replica or every group together; a line's `node` and `group`
   fields say where it ran.
3. Filter with **Search messages…**, **Level** (DEBUG, INFO, WARNING, ERROR, CRITICAL), **Function** and **Source**
   (function, invocation, stdout, stderr, host).
4. **❚❚ Pause** stops the tail and **▶ Resume** continues. **Clear** empties the view (the logs on the server are
   kept). **Load older** at the top loads earlier entries. **Console ↗** opens the provider's console when there is
   one.

The same logs show inside a function's wizard (step 3, **Live logs**) and on the Test page (**Show the function's
logs**). The studio address `#/logs/<function>` shows one function only.

```bash
pskit logs -f
pskit logs -f --function worker --level WARNING
pskit logs -q "order 42" -n 200
pskit logs --server app-1          # on premises: read from this saved server
```

## Delete stored log streams in studio

The **Stored logs** section (closed by default) lists the stored log streams, on AWS and on premises.

1. Open **Stored logs** and pick a **Function** (or all functions). **↻ Refresh** reloads.
2. The table lists **Function**, **Stream**, **Last event** and **Size**. Tick streams (or the select-all box).
3. Click **Delete selected (N)**, or **Delete all logs of <function>** / **Delete all logs**. Confirm **Delete logs?**
   with **Delete**; this cannot be undone.

Where listing is not available, the section says "Log streams unavailable".

```bash
pskit logs --streams
pskit logs --delete STREAM --yes
pskit logs --delete-all --function worker --yes
```

## Set a function's log level in studio

The **Log level** of a function is set in step 3 of the [function
wizard](functions.md#wizard-step-3-environment--permissions): **inherit**, **DEBUG**, **INFO**, **WARNING** or
**ERROR**. It writes `PSKIT_LOG_LEVEL` into the function's environment, and `ctx.logger` output below that level is
dropped. For every function at once, set `PSKIT_LOG_LEVEL` under **Environment variables** on [Overview](overview.md).
On premises, the host's own level is **Host tuning → log_level**.

## See also

- [Logs everywhere](../deployment/logs.md)
- [Test page](test.md)
- [Monitoring and the dashboard](../deployment/monitoring-and-dashboard.md)
- [Troubleshooting](../troubleshooting.md)
