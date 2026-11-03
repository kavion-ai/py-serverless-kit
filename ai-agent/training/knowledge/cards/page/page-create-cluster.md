# Studio: Create cluster

How to open: Scaling cluster > + New cluster

The button is also on the empty state "No cluster yet".

What it is for: Install Docker Swarm, Kubernetes (k3s), or HashiCorp Nomad on a saved master server. The drawer title is "New scaling cluster". The studio posts to the cluster create endpoint, which calls `create_cluster`. The server requires orchestrator to be swarm, kubernetes, or nomad.

What you see: Cluster name. The field lowercases what you type. The initial value is prod, or prod-2, prod-3, and so on when that name is already used. The error text is "lowercase letter first; lowercase letters, digits and -", and "already used" when the name is taken. Help says you refer to it with `pskit deploy --cluster <name>` and with provider.options.cluster. Orchestrator is a segmented control of the orchestrators the API returned. Its help includes that orchestrator's summary and the ports to open between servers. Master server is required. Its help says it runs the control plane and the main replica (schedules, queues, logs, data), and needs root or passwordless sudo. Servers already in a cluster, and a cluster's load-balancer server, are excluded (`inCluster`). Cluster address is optional. The help says it is the master's IP the other servers reach, for example its private IP, and the default is its SSH host. Master serves requests is a toggle labeled "Send requests to the master too, not only to the joined servers". The code comment says Nomad keeps the master as a backup, and Swarm and k3s send it requests. The initial value follows that: on unless the orchestrator is nomad.

What you can do: Create starts the job. The button says Installing… while it runs. When the job succeeds, the drawer calls `onCreated` with the name. You can add a server from the master picker without leaving the drawer. The empty-state steps say to use Use for this project, set replicas, then deploy. Join more servers any time from Scaling cluster > + Join server

```
pskit deploy --cluster prod
```

Tips and limits: If the top-bar provider is not onprem, the page warns that clusters run on-prem functions and links to Overview. Create does not deploy the project's functions. The name you type is the cluster name, not the top-bar stage.

Sources: `dashboard-ui/src/studio/views/Cluster.tsx`, `src/py_serverless_kit/studio/server.py`, `docs/studio.md#what-you-can-do`
