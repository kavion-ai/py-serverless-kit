# Studio: New load balancer

How to open: Load balancers > + Create load balancer

The drawer title is "New load balancer".

What it is for: Install OpenResty on one saved server over SSH and give projects and clusters a path on one URL. The drawer text says pskit installs Docker on the server over SSH and runs OpenResty there. The server must not be part of a cluster, and it must reach the functions' port on every server behind it. Users call `http://ADDRESS/PATH/`, with a port in the URL when the port is not 80.

What you see: Name, lowercased as you type. Placeholder edge. The error text is "lowercase letter first; lowercase letters, digits and - (up to 31)", and "already used" when the name is taken. Help says projects refer to it as provider.options.balancer and with `pskit lb status <name>`. Server is required. Help says a saved server outside every cluster, not used by another load balancer, with root or passwordless sudo. Port, help "80: http://its-address/". Address in the URL is optional. Help says it is the IP or name users reach it at, and the default is its SSH host. How it spreads requests uses `AlgorithmPicker` with `state.algorithms` and `state.default_algorithm`. Help says you can change it later with Update, and a project can pick another algorithm for its own route. Weights appear when the algorithm uses them. Attach clusters now is shown when the account has clusters. Help says every deployment on them gets /<service>/ on this load balancer. A cluster that contains the chosen server is marked "(contains this server)".

What you can do: Create is disabled until name, server, and port are set and weights are valid. The label is Installing… while the job runs. The studio create handler calls `create_balancer`, then `attach_cluster` for each cluster you ticked. Those are the same functions `pskit lb create` and `pskit lb attach` use. The algorithm ids listed by the product are the ones `pskit lb algorithms` prints.

```
pskit lb status edge
```

Tips and limits: Create installs the balancer. It does not deploy functions. Forget, on an existing balancer, only stops this project managing it. Remove stops the process. The address field's placeholder in the source is a private address. Use a documentation-range address such as 192.0.2.10 if you need an example.

Sources: `dashboard-ui/src/studio/views/LoadBalancers.tsx`, `src/py_serverless_kit/studio/server.py`, `docs/load-balancers.md`
