# On-prem deploy methods: local, SSH and Docker

Search terms: deploy method, options.deploy, method local, method ssh, scp, method docker, remote docker, systemd,
python bundle, portable CPython, node bundle, pem, identity_file, sshpass, known_hosts, sudo, saved server, --server

`provider.options.deploy` decides **where the on-prem host runs** and how pskit gets it there. Every method still runs
through Terraform: `terraform_data.host` calls `onprem_deploy.py apply` on this machine, which then starts the host
locally, over SSH, or in Docker. The target never needs pskit installed.

| `method` | What runs | Target needs | This machine needs |
|---|---|---|---|
| `local` (default) | a detached process on this machine | Python (the interpreter that runs `pskit`) | nothing extra |
| `ssh` (alias `scp`) | `release.tar.gz` extracted on the server, then a process or a systemd unit | SSH; Python only with `python: system`; passwordless `sudo` for systemd | OpenSSH (`ssh`, `scp`) |
| `docker` | an image built here, run as a container here or on a server | SSH for a remote server; Docker (installed when missing) | Docker CLI; OpenSSH for a remote server |

A scaling cluster (`options.cluster`) uses `docker` on the cluster's master for you; see
[onprem/scaling/README.md](../../onprem/scaling/README.md).

## Write options.deploy in pskit.yml (short forms)

`options.deploy` takes a mapping, or a short string:

```yaml
deploy: local                              # same as {method: local}
deploy: ssh                                # needs host somewhere (a saved server, or --server)
deploy: ssh://pskit@10.0.1.12:22/opt/pskit/orders   # -> method ssh, user, host, port, path
deploy: {server: edge1}                    # a saved server: host, user, port and login come from it
```

In a mapping, `ssh: {...}`, `docker: {...}`, `python_bundle: {url, sha256, home}` and `node_bundle: {url, sha256, home}`
may group keys; they are flattened. Aliases: `via` = `method`, `os` = `target_os`, `arch` = `target_arch` (`amd64` and
`aarch64` are accepted), `pem` / `identity` = `identity_file`, `remote_path` = `path`, `name` = `container`, `args` =
`docker_args`.

## Deploy the on-prem host on this machine (method local)

`method: local` starts a detached process on this machine with the Python that runs `pskit`. Data goes to
`.pskit/onprem-data/<service>-<stage>` unless `data_dir` is set.

```yaml
provider:
  name: onprem
  options:
    port: 8080
    deploy:
      method: local
      python: system          # auto | system | bundle (bundle downloads a portable CPython for provider.runtime)
      target_os: auto         # auto = this OS
      target_arch: auto       # auto = this CPU
```

If `provider.runtime` differs from the interpreter running `pskit`, validation warns and the host still uses the
running one; set `python: bundle` to run exactly `provider.runtime`. In studio: **Overview & provider** ->
**On-premises deployment** -> **Deploy method** **This machine**.

## Deploy the on-prem host to a server over SSH (method ssh)

`method: ssh` packs one `release.tar.gz` (bundle, `onprem_ctl.py`, `pskit_host.json`, `pskit-run.sh`, the systemd unit
and `python/` when used), copies it with `scp`, extracts it in `path`, then restarts the host and waits until
`http://127.0.0.1:<port>/__pskit/health` answers on the server. A failed start includes `systemctl status` and
`journalctl` output when a unit is used.

```yaml
options:
  host: 0.0.0.0                   # accept traffic from other machines
  port: 8080
  deploy:
    method: ssh
    host: 10.0.1.12               # required (or a saved server)
    user: pskit                   # default: $PSKIT_ONPREM_USER, $USER / $USERNAME, else pskit
    port: 22
    pem: ${env:PSKIT_SSH_KEY}     # empty: the SSH agent / ~/.ssh keys
    known_hosts: accept-new       # accept-new | ignore | path to a known_hosts file
    path: /opt/pskit/orders       # default /opt/pskit/<service>-<stage> (C:/pskit/... for target_os windows)
    install: systemd              # process (default) | systemd (linux only)
    sudo: true                    # sudo -n for mkdir/chown of path and for systemd
    python: bundle                # system (default) needs Python on the server
    target_os: linux              # auto = linux for remote targets
    target_arch: x86_64           # auto = provider.architecture
```

With `sudo: true`, apply runs `sudo -n mkdir` on `path` and gives it to the SSH user. `install: systemd` writes
`/etc/systemd/system/pskit-<service>-<stage>.service` and runs `systemctl restart`; `install: process` runs
`onprem_ctl.py start`. Wheels are downloaded for `target_os` / `target_arch`. Studio: **Deploy method** **SSH server**,
then **SSH host**, **SSH user**, **SSH port**, **Private key**, **Known hosts**, **Use sudo**, **Remote path**,
**Install as**, **Python**, **Target OS**, **Target arch**, and **Test SSH connection**.

## Log in to an SSH server: key, agent or password

The SSH login for `ssh` and remote `docker` uses one of these:

| Login | Keys |
|---|---|
| Key file | `pem` (or `identity_file`). Must work with `ssh -o BatchMode=yes` (no passphrase prompt; load a protected key into the agent). |
| SSH agent / default keys | no key set (or `auth: agent`); `~/.ssh/config` applies. `pskit deploy` in a terminal asks for a `.pem` path; Enter keeps the agent. |
| Password | `password_file: <file>`, or `auth: password` plus `SSHPASS` in the environment. Uses `sshpass`; the password never appears on a command line or in Terraform state. |

`sshpass` does not exist on Windows: run `pskit resources onprem ssh-key user@host` once (it asks the password and
installs `~/.ssh/pskit_ed25519`), then set `pem` to that key. If Windows OpenSSH says the key is unprotected, restrict it
with `icacls`. More: [onprem/servers.md](../../onprem/servers.md).

## Run the on-prem host in Docker (method docker)

`method: docker` builds an image that already contains Python (`FROM python:<minor>-slim`; Node.js services use
`node:<major>-bookworm-slim` plus Debian's `python3`). The host inside listens on `0.0.0.0`; data is in
`/var/pskit/data`.

```yaml
deploy:
  method: docker
  image: pskit/orders:dev          # default pskit-<service>-<stage>:<stage>
  container: pskit-orders          # default pskit-<service>-<stage>
  restart: unless-stopped          # docker run --restart
  publish: "8080:8080"             # default <port>:<port>
  docker_args: ["--memory", "512m"]
  docker_host: tcp://10.0.1.12:2376   # optional: unix://, tcp://, npipe:// or ssh://user@host
```

**On this machine** (no `host`, no `ssh://` docker host): `docker build`, `docker rm -f`, `docker run`. No SSH.

**On a server** (`host: ...`, or `docker_host: ssh://user@host`): the image is built here, saved to a tar, copied with
`scp` to `~/pskit-images/<container>/`, and a script on the server installs Docker when missing (apt, dnf, yum or apk;
`install_docker: true` is the default), waits for `docker info`, runs `docker load` and `docker run`, deletes the tar,
and waits for `/__pskit/health`. A failure includes `docker logs`. `sudo` defaults to `true` here (needed to install
and start `dockerd` unless the user is root). Set `install_docker: false` to refuse a server without Docker. A
`tcp://`, `unix://` or `npipe://` `docker_host` talks to that daemon directly and does not use SSH.

Studio: **Deploy method** **Docker**, then **Image**, **Container name**, **Docker host**, **Restart policy**,
**Publish**, **Extra docker args**, the SSH fields, and **Install Docker on the server**.

## Ship Python or Node.js to a server that has none

When the server has no Python, use `python: bundle` (a portable CPython from python-build-standalone is downloaded at
apply, cached under `~/.cache/pskit/python-standalone`, and copied with the app) or `method: docker`. Air-gapped:

```yaml
deploy:
  python: bundle
  python_url: https://mirror.internal/cpython-3.12.12+20251010-x86_64-unknown-linux-gnu-install_only.tar.gz
  python_sha256: <sha256>
  # python_home: /opt/python3.12        # or copy a tree you already have
```

Node.js services (`provider.runtime: nodejs18`..`nodejs24`) still run the Python host (`host_python`, default
`python3.12`); each function runs in a `node` worker. `node: system` (default) needs `node` on PATH;
`node: bundle` downloads the official nodejs.org build for `target_os` / `target_arch` (cached under
`~/.cache/pskit/nodejs`); `node_url` + `node_sha256` use a mirror; `node_home` copies `bin/node` from a local install.

## Deploy to a saved server and remember the machine

A saved server holds host, user, port, login, sudo and home path once (`pskit resources onprem servers add`). Use it:

- In `pskit.yml`: `deploy: {server: edge1}`. Its host, user, port and login replace those keys; `path`, `python`,
  `install`, ... stay. A `method` other than `ssh`, `scp` or `docker` becomes `ssh`.
- For one run: `pskit deploy --server edge1` (or `PSKIT_DEPLOY_SERVER=edge1`); `--server local` deploys on this
  machine; `--cluster prod` (or `PSKIT_DEPLOY_CLUSTER=prod`) deploys on a scaling cluster.
- In studio: **Overview & provider** -> **On-premises deployment** -> **Saved server** (or **+ Add server**), or per
  run on **Deploy** -> **Run on** **One machine** -> **Machine**.

After a successful deploy, `.pskit/onprem-<stage>/onprem_deployed.json` records the server, login, port and admin token.
The next `pskit deploy` without `--server` (and without `server`, `host` or a non-local `method` in `pskit.yml`) goes
to the same machine, and `pskit trigger`, `pskit logs`, `pskit info`, the dashboard and studio's **Test** and **Logs**
talk to it. `pskit deploy` prints `deployed on: <server> (<host>)`. Use one stage per machine to keep deployments apart.

## Remove an on-prem deployment

`pskit remove` runs `onprem_deploy.py destroy`: it stops the local process, the remote process or systemd unit, or the
container. It never deletes `data_dir`. `--keep-resources` keeps managed buckets, queues and topics. In studio:
**Deploy** -> **Remove** -> type `onprem/<stage>` -> **Remove**.

## See also

- [README.md](README.md): on-prem provider options
- [host-api.md](host-api.md): control API, admin token, logs
- [onprem/servers.md](../../onprem/servers.md), [onprem/terminal-and-software.md](../../onprem/terminal-and-software.md)
- [onprem/placement.md](../../onprem/placement.md), [onprem/scaling/README.md](../../onprem/scaling/README.md)
- [onprem/firewall.md](../../onprem/firewall.md)
