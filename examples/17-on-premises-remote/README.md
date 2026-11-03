# 17 · On-premises, remote server

Example 16 runs the host on the laptop that runs `pskit deploy`. This example
copies the same kind of host onto a machine you SSH into — a factory box, a
VM, or a rack server. The handler code does not change.

Three ways to get code from this laptop onto that server:

| `options.deploy.method` | What the server needs | What the laptop needs | When to use it |
| --- | --- | --- | --- |
| `local` | this machine (example 16) | Python + pskit | laptop / the server *is* the deploy machine |
| `ssh` or `scp` | SSH. Python only if `python: system` | OpenSSH (`ssh`, `scp`) and a `.pem` or the SSH agent | most on-prem Linux boxes |
| `docker` | SSH. Docker is installed at deploy when it is missing | Docker CLI, OpenSSH, and a `.pem` for the server | the server should run a container, with or without Docker already installed |

When the server has **no Python**, pick one of:

- `method: ssh` (or `method: scp`) and `python: bundle` — pskit downloads a portable CPython
  ([python-build-standalone](https://github.com/astral-sh/python-build-standalone))
  at apply time, packs it into one `release.tar.gz`, copies that file, and restarts systemd (this file)
- `method: docker` — the image is `FROM python:3.12-slim` and is built on this
  machine. The server does not need Python. If it also has no Docker, deploy
  installs Docker and then loads the image
- `python_home: /path/to/portable-python` — air-gapped: you already have a
  CPython tree, pskit copies it instead of downloading

## This file (SSH + bundled Python + systemd)

```bash
export PSKIT_ONPREM_HOST=10.0.1.12          # SSH target
export PSKIT_ONPREM_USER=pskit
export PSKIT_SSH_KEY=$HOME/.ssh/factory.pem # optional; pskit deploy asks when this is empty
export PSKIT_ONPREM_URL=http://10.0.1.12:8090
pskit deploy
curl http://10.0.1.12:8090/hello?name=Ada
curl http://10.0.1.12:8090/__pskit/health
pskit remove                                 # systemctl stop; data dir stays
```

`pskit deploy` packs the host into one archive, copies it with `scp`, runs
`systemctl restart`, and returns only after `http://127.0.0.1:8090/__pskit/health`
answers on the server. A failed start prints `systemctl status` and `journalctl`.

The SSH user needs passwordless `sudo` to write `/etc/systemd/system`
(`deploy.sudo: true`). On a terminal, leave the `.pem` prompt empty to use the
SSH agent. The key must be accepted with `BatchMode` (no passphrase prompt).
If OpenSSH says the `.pem` is too open, run `chmod 600` on Linux or macOS, or
`icacls` on Windows. Wheels are vendored as manylinux x86_64 because
`target_os: linux`.

Shorthand for the same method:

```yaml
deploy: ssh://pskit@10.0.1.12/opt/pskit/factory-api
```

## Docker instead

The image is built on the laptop. It is copied to the server with the `.pem`
and started there. The server does not need Python. If `docker` is not on the
server, deploy installs it (apt, dnf, yum, or apk), waits until the daemon
answers, loads the image, and returns only after the container answers
`/__pskit/health`. `pskit deploy` asks for the `.pem` path when `pem` is empty.

```yaml
provider:
  options:
    host: 0.0.0.0
    port: 8090
    deploy:
      method: docker
      host: 10.0.1.12
      user: pskit
      pem: ~/.ssh/factory.pem
      image: pskit/factory-api:dev
      restart: unless-stopped
```

```bash
pskit deploy
# Path to the SSH private key (.pem): C:\keys\factory.pem
```

Leave out `host` to build and run the container on the laptop instead. Data
lives in a volume named after the container. The SSH user needs passwordless
`sudo` when Docker has to be installed.

## Server already has Python

```yaml
deploy:
  method: ssh
  host: 10.0.1.12
  user: pskit
  path: /opt/pskit/factory-api
  python: system          # uses python3.12 on the server
  install: process        # start a detached process instead of systemd
```

## Air-gapped bundle

Download the install_only archive once on a machine with network, copy it in,
and point at the unpacked tree:

```yaml
deploy:
  method: ssh
  host: 10.0.1.12
  python: bundle
  python_home: ./vendor/python     # portable CPython directory, copied as-is
```

Or set `python_url` + `python_sha256` to an internal mirror of the
python-build-standalone `install_only` tarball.

## Bind address

`options.host` is the address the process binds on the **target**. Use
`0.0.0.0` so other machines can call it. `advertise` is the URL written into
`pskit info` and the dashboard.
