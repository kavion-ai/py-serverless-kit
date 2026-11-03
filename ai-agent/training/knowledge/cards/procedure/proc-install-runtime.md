## In studio
1. Open this path:
Resources > + On-prem service

## In the terminal
1. Run:

```
pskit resources onprem create tools-python --service python
```

2. Run:

```
pskit resources onprem create tools-node --service nodejs
```

## In code

The catalog kind runtime installs software on a saved server. python, nodejs, and docker are catalog ids.

## Install software on a server

The catalog's *Install on a server* groups install with the server's package manager (apt, dnf, yum or apk), over SSH: | Software | Versions | Notes | |---|---|---| | **Python 3** | `system` (default), 3.13, 3.12, 3.11, 3.10, 3.9, 3.14 | `system`: the distribution's python3 with venv and pip.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
