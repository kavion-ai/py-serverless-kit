## In studio
1. Use Scale on the cluster page.

## In the terminal
1. Run:

```
pskit cluster scale prod --replicas 3
```

## In code

scale sets the web replica count now. The command help says the value lasts until the next deploy, and options.cluster.replicas keeps it.

## Monitor, scale and add servers when it is full

The studio's **Scaling cluster page shows every server's CPU (over one second), memory and disk with the limits, the orchestrator's view (ready, drained, offline), each deployment's running / desired replicas, and replicas that cannot be placed. It refreshes every 30 seconds.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
