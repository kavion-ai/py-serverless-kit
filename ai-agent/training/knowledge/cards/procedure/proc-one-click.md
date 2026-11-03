## In studio
1. Open this path:
Resources > + On-prem service

## In the terminal
1. Run:

```
pskit resources onprem create orders-db --service postgres
```

2. Run:

```
pskit resources onprem create jobs --service redis
```

## In code

The create command starts a container on this machine or an SSH server and can attach a trigger. The password is generated into the env file.

## From the command line

Without `--save` the command prints the YAML to paste. `--save` rewrites `pskit.yml` (comments are not kept).

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
