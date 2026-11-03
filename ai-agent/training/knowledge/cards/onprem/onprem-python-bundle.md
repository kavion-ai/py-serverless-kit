# On-premises: Portable Python for an on-premises host

When the server has **no Python**, use `python: bundle` (a portable CPython from python-build-standalone is fetched at apply and copied with the app) or `method: docker` (the image is `FROM python:<minor>-slim`). From Windows, a Linux bundle is copied out of the downloaded archive and is not unpacked into the project (those trees contain test paths longer than `MAX_PATH`). Air-gapped: `python_home` (copy a tree you already have) or `python_url` + `python_sha256` (internal mirror of an `install_only` tarball).

SSH and `scp` write `pskit-run.sh` plus `release.tar.gz` (the staged bundle, `onprem_ctl.py`, `pskit_host.json`, the unit when `install: systemd`, and `python/` when `python: bundle`). With `sudo: true`, apply runs `sudo -n mkdir` on `path` and `chown`s that directory to the SSH user (`deploy` cannot create `/opt/pskit` itself), then copies the files. Apply does not delete `data_dir`. `install: systemd` runs `systemctl restart`. `install: process` runs `onprem_ctl.py start`. Either way the deploy fails if `http://127.0.0.1:<port>/__pskit/health` does not answer, and the failure includes `systemctl status` and `journalctl` when a unit was used.

**Limits:** no cloud authorizer and no IAM mapping. A `terraform.extra` resource from another cloud (`aws_*`, `google_*`, `azurerm_*`, and the other cloud prefixes) is omitted with a warning. A state backend of `s3`, `gcs` or `azurerm` warns; set `provider.state.backend` empty (see `providers.onprem` in examples 11 and 15) to keep state on this machine. Delivery is at-least-once. A missed schedule fires once on the next poll, not as a burst. The host does not kill a handler at `timeout`; `ctx.remaining_time_ms()` still counts down. If `method` is `local` and `provider.runtime` is not the interpreter running `pskit`, validation warns and the host still uses that interpreter. `python: bundle` needs network on first apply unless `python_home` or a cached archive under `~/.cache/pskit/python-standalone` is present. systemd units are written to `/etc/systemd/system` (set `sudo: true` unless the SSH user is root). That `sudo` is non-interactive (`sudo -n`), so the sudoers rule must not ask for a password.

An address or login copied from the source was rewritten in this card. Addresses use 192.0.2.0/24, a documentation range. The login in those examples is deploy.

```text
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1          # bind address on the *target*. 0.0.0.0 is advertised as 127.0.0.1 unless advertise is set
    port: 8080               # 1-65535. Give each service its own port
    advertise: https://fn.internal.example   # optional URL written into outputs
    data_dir: .pskit/onprem-data             # default .pskit/onprem-data/<service>-<stage> (local); <path>/data on SSH
    poll_seconds: 0.5
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"  # header x-pskit-token on /__pskit/* except health
    env_file: .env.onprem      # KEY=VALUE secrets copied next to the host (host.env) and loaded at start;
                               # read by <name>_env driver options and handlers, never written to Terraform state
    execution_retention: 500   # finished workflow executions kept under <data_dir>/executions
    workflow_workers: 8        # workflow runs executing at once; further starts wait for a worker
    log_buffer: 5000           # log entries kept in memory for /__pskit/logs (min 100)
    log_level: INFO            # minimum level captured from `logging`
    capture_output: true       # also record print() / stdout / stderr lines
    services:
```
