## In studio
1. Open this path:
Scaling cluster > + New cluster

## In the terminal
1. Run:

```
pskit cluster create prod --orchestrator swarm --master app-1
```

## In code

Orchestrator is swarm, kubernetes, or nomad. The master is a saved server. The studio create drawer collects the same fields.

## How the functions run in a cluster Each deployment (`pskit-<service>-<stage>`)

runs the function host image as two workloads: * **web** replicas serve your HTTP routes and `invoke()` calls. Adding replicas or servers adds HTTP capacity. * The **main** replica runs on the master with the data volume.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
