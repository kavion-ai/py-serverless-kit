## How the functions run in a cluster

Each deployment (`pskit-<service>-<stage>`) runs the function host image as two workloads:

* **web** replicas serve your HTTP routes and `invoke()` calls. Adding replicas or servers adds HTTP capacity.
* The **main** replica runs on the master with the data volume. It owns everything stateful: schedules run once,
  not once per replica; built-in queues, topics and buckets live in one place; workflow executions are recorded
  there; queue, storage and topic triggers run there.
* A web replica hands those to main. `submit_queue()`, `put_object()`, workflow starts and `/__pskit/*` admin
  calls are forwarded to it. Its log lines and invocation counts are sent to main every second, tagged with
  `replica`, so `pskit logs`, the studio's **Logs** view and `/__pskit/stats` show the whole cluster.
* Resources with a driver (Redis, SQS, S3, MinIO, ...) are used directly by every replica, as on one server.

Your handler code does not change.

### Nomad does not need a load balancer

Swarm and k3s publish the functions' port on every server and spread HTTP across the web replicas. Nomad does not.
The main replica listens on the master's port. Each web replica listens on its own server's port, one per server.
`pskit deploy` waits until the main replica answers `http://127.0.0.1:<port>/__pskit/health` on the master. That
check does not go through a load balancer, and the deploy succeeds without one.

Send traffic to the master and the main replica handles it. Send traffic to another server and that server's web
replica handles it. For a single URL that spreads requests across the web replicas, let pskit run a
load balancer on one more server, or put your own nginx,
HAProxy or Traefik in front.

While that wait runs, the deploy prints each Nomad allocation and the main replica's logs every 10 seconds, as
they happen. If the port never answers, the output ends with `nomad job status` and those logs.
