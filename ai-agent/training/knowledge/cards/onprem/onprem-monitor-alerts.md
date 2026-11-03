## Monitoring and alerts

The **Servers** list shows a check mark per server: ✓ when its SSH port answers (all probed at once when the list
opens, **Re-check** to probe again), ✗ with the reason otherwise; *Test* replaces it with the result of a full login
check. **Live** on a server shows its CPU, RAM and disk use, refreshed every few seconds, until you switch it off.

A service's **Details** has **Live monitoring**: switch it on to see, every 5 seconds, each container's CPU, memory and
the disk holding its data (for a replicated database: the primary, every replica and the load balancer), the open
connections, the data size and how far each replica is behind. Nothing is measured while it is off.

**Alerts** (optional, in the create form or in Details) send a message when a limit is crossed: CPU, memory or disk
percent of a container, replica lag in seconds, or a container that is down. They go to

- a **function** of the project, run through the deployed host with the alert as `event.data`
  (`{kind: "pskit.database.alert", key, service, reasons, message, sample}`). *Create a new function* adds
  `<key>-alert` to `pskit.yml` with a handler stub; deploy the project to run it;
- a **webhook**: Slack, Teams or Google Chat incoming webhooks show the message; any other URL gets the JSON.

An alert goes out at most once per cooldown (30 minutes by default). The studio checks every minute while it runs;
without it, run the check from cron on any machine with the project:
