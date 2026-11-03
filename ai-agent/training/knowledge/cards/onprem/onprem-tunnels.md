## When connections time out `TimeoutError` / `ConnectTimeoutError` / `ECONNREFUSED` from

a script almost always mean a firewall: the program can't
open a TCP connection to that port. The service is usually fine (`pskit resources onprem status <key>`).

| Situation | Fix |
|---|---|
| Talking to a service directly (Redis, ElasticMQ, Postgres, ...) on a cloud VM | use the pskit client / HTTP above (host port only), or `pskit resources onprem tunnel <key>` (SSH; prints the variables pointing at `127.0.0.1`), or open the port **to your IP** in the security group / NSG |
| The host port itself times out | `pskit client tunnel`, then `PSKIT_HOST=http://127.0.0.1:8080`; or open the port to your IP; and set `provider.options.host: 0.0.0.0` so the host listens on the network |
| `HTTP 401` | the host has an `admin_token`: `PSKIT_ADMIN_TOKEN=...` or `token=` |

Generated direct-client examples use short connect timeouts (about 5 s), so a closed port fails quickly with this
explanation in mind instead of hanging. The studio flags it too: *On-prem services → Details* shows when this machine
cannot reach a service, and *Call from code* checks the host.
