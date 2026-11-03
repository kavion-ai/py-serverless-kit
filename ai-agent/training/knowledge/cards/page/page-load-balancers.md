# Studio: Load balancers

How to open: Left navigation label Load balancers.

What it is for: One URL in front of projects and clusters, installed over SSH. The empty-state text says + Create load balancer: name it, pick the server and how it spreads requests, and pskit installs it over SSH.

What you see: The action + Create load balancer. The create form has the label "How it spreads requests" with help "Change it any time with Update; a project can pick another one for its own route." It also has "Attach clusters now (optional)", help "Every deployment on them gets /<service>/ on this load balancer." A balancer that is in use shows Forget. The confirm title is "Forget load balancer <name>?" and the body says only this project stops managing it, it keeps running on the server, and you can add it back with + Create load balancer using the same name and server. The confirm label is Forget. A routes heading is "Routes". An attach control is + Attach cluster. The sync help says it rewrites settings on the server and reloads OpenResty without dropping requests, and that routes which chose their own algorithm keep it.

What you can do: Create calls `create_balancer` (the same function as `pskit lb create`). Update calls `update_balancer` (`pskit lb update`). Sync calls `sync_balancer` (`pskit lb sync`). Attach calls `attach_cluster` (`pskit lb attach`). Forget calls `forget_balancer` and leaves the process running (`pskit lb forget`). Remove calls `remove_balancer`, which is what `pskit lb remove` calls. The command that prints the algorithm ids is `pskit lb algorithms`. The form label for that choice is How it spreads requests.

Tips and limits: Forget and remove are different. The Forget dialog says the balancer keeps running for other projects and clusters. Algorithm choices come from the form backed by `pskit lb algorithms`. A project route can use a different algorithm from the balancer default. The help text on the form says that, and so does the sync sentence about routes that chose their own algorithm.

Sources: `dashboard-ui/src/studio/views/LoadBalancers.tsx`, `src/py_serverless_kit/studio/server.py`, `src/py_serverless_kit/cli/main.py`, `docs/load-balancers.md`
