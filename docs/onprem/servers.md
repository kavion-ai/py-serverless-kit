# Saved servers: add, test, use and forget SSH machines

Search terms: saved server, SSH server, add server, pem key, private key, SSH password, sshpass, test connection,
forget server, used in, server usage, ssh-key, VM, IP address, home path, bind address, data directory

A saved server is an SSH machine you name once (for example `edge1`). After that every on-prem feature can use it by
name: create services on it, install software, open a shell or a browser terminal, deploy the functions to it, put it
in a scaling cluster or run a load balancer on it. pskit keeps the list in `.pskit/onprem-servers.json` on this
machine (connection details only, out of git).

## What a saved server stores

A saved server stores how to log in and three optional defaults for that machine:

| Field (studio) | CLI flag | Meaning |
|---|---|---|
| **Name** | `NAME` argument | how you pick it: a letter, then letters, digits, `_ . -` (max 63). `local` is reserved for this machine |
| **Host** | `--ssh user@host[:port]` | IP address or DNS name |
| **User** | the `user@` part (default `root`) | SSH user: `ubuntu`, `azureuser`, `ec2-user`, `root`, ... |
| **SSH port** | the `:port` part (default 22) | 1-65535 |
| **Log in with** | `--pem`, `--ssh-password-env`, `--ssh-password-file` | *Key file (.pem)*, *SSH agent / default key* or *Password* |
| **Use sudo** | `--sudo` | run `docker` and installs with `sudo -n` (the user is not root and not in the `docker` group) |
| **Home path** | `--home /srv/pskit` | where pskit keeps files: functions in `<home>/<service>-<stage>`, cluster files in `<home>/pskit-cluster`. Default `/opt/pskit` (cluster files: the SSH user's home) |
| **Bind address** | `--bind 10.0.0.5` | the address the functions' host and services listen on: `0.0.0.0`, `127.0.0.1` or one of the server's IPs (also its cluster address) |
| **Data directory** | `--data-dir /data/pskit` | services keep data in `<data>/<container>` (a folder instead of a Docker volume); the functions' built-in queues and buckets go there too |
| **Description** | `--description "..."` | a note shown in the list |

A typed SSH password is saved to `.pskit/ssh/<user>@<host>-<port>.pass` (owner-only), never in the JSON,
`pskit.yml` or Terraform state.

## Add a server in studio

The studio adds a saved server from the *Servers* card on the Resources page, or from the Overview page.

1. Open **Resources** in the sidebar and scroll to the *On-prem services* card. The **Servers** card is inside it.
2. Click **+ Add server**. The *Add a server* drawer opens.
3. Fill in **Name** (for example `edge1`), **Host** (`13.72.87.80` or `server.example.com`), **User** (default
   `ubuntu`) and **SSH port** (default 22).
4. Under **Log in with** pick:
   - **Key file (.pem)** and type the path in **Private key (.pem)**, for example `~/.ssh/server.pem` (an AWS or Azure
     `.pem`, `id_ed25519`, ...);
   - **SSH agent / default key**: nothing to fill in; pskit logs in like `ssh user@host` in a terminal (agent,
     `~/.ssh/id_*`, `~/.ssh/config`);
   - **Password** and type it in **SSH password** (see [log in with a password](#log-in-to-a-server-with-a-password)).
5. Tick **Use sudo** when the user is not root and not in the `docker` group.
6. Optional, under *On this server*: **Home path**, **Bind address**, **Data directory**, **Description**.
7. Click **Save and test**. The server appears in the list and pskit logs in once: the row shows the OS, CPU,
   memory, free disk, Docker (and whether it is usable directly or via sudo), sudo, and installed Python, Node.js and
   nginx. A failed login shows the error under the row.

The Overview page has the same form: **Overview & provider → On-premises deployment → Saved server → + Add a
server…** (or **+ Add server**). A server saved there also becomes the deploy target of the stage.

You can also ask Hana (the **Ask Hana** button): paste the IP, the SSH user and the `.pem` path, an
`ssh -i key.pem ubuntu@1.2.3.4` command, or Terraform outputs such as `public_ip = "..."`, and she adds the server.
See [Hana](../assistant.md).

## Add a server from the terminal

`pskit resources onprem servers add NAME --ssh user@host[:port]` saves a server and logs in once to test it
(`--no-test` skips that).

```bash
pskit resources onprem servers add edge1 --ssh ubuntu@10.0.0.5 --pem ~/.ssh/edge1.pem
pskit resources onprem servers add db-box --ssh azureuser@13.72.87.80              # SSH agent / default key
pskit resources onprem servers add lab --ssh root@192.168.1.20:2222 --ssh-password-env LAB_PW --sudo
pskit resources onprem servers add big --ssh ubuntu@10.0.0.9 --pem key.pem \
    --home /srv/pskit --bind 10.0.0.9 --data-dir /data/pskit --description "8 CPU, 32 GB"
pskit resources onprem servers list [--json]
```

Running `servers add` again with the same name replaces the entry.

## Log in to a server with a password

A password login uses **sshpass**, so the password never appears on a command line. sshpass must be installed on the
machine that runs pskit (`sudo apt install sshpass`, `sudo dnf install sshpass`, or
`brew install hudochenkov/sshpass/sshpass`), and the server must allow `PasswordAuthentication`.

On Windows (no sshpass), or to stop using the password, install a key once. `ssh-key` creates
`~/.ssh/pskit_ed25519` when missing, logs in with the password one time (ssh asks for it in this terminal), adds the
public key to `~/.ssh/authorized_keys` on the server and checks that the key alone logs in:

```bash
pskit resources onprem ssh-key azureuser@13.72.87.80              # add :2222 for another port
pskit resources onprem servers add az1 --ssh azureuser@13.72.87.80 --pem ~/.ssh/pskit_ed25519
```

`--key PATH` installs another key; `--password-env VAR` sends the password from a variable (needs sshpass).

## Test a server connection

The saved server test logs in once over SSH and reports what pskit needs.

- **Check marks**: when the Servers card opens, every server's SSH port is probed at once (no login). ✓ means the
  port answers (with the time in ms on hover), ✗ shows the reason. **Re-check** probes again.
- **Test** on a row logs in and shows OS, architecture, CPUs, memory, free disk, Docker and Docker access, sudo,
  Python, Node.js and nginx. The check mark then shows the test result.
- **Live** shows CPU, RAM and disk use, refreshed every few seconds until you click it again.

```bash
pskit resources onprem servers check            # SSH port of every server, no login
pskit resources onprem servers test edge1       # log in: OS, CPU, memory, disk, Docker, sudo, runtimes
pskit resources onprem servers top edge1 --watch 5
```

## See where a server is used

The *Used in* column of the Servers card says, for each saved server, every place in this project that names it.
It reads only local files (`pskit.yml`, `.pskit/onprem-*.json` and deploy records), so it works while the server is
down. Click **Used in N places** (or *not used anywhere*) to open *Where &lt;name&gt; is used*:

| Kind (column *As*) | Comes from |
|---|---|
| Deploy target | `provider.options.deploy.server` in `pskit.yml` |
| Deployed | a stage was last deployed there |
| Function group | a `provider.options.placement` group runs there ([placement](placement.md)) |
| Cluster / Cluster load balancer | master or joined server of a scaling cluster, or its load balancer |
| Load balancer | a named load balancer runs there ([load balancers](load-balancers.md)) |
| Service / database | a one-click service, or a primary, replica or database load balancer |
| Installed software | Docker, Node.js, nginx, ... installed by pskit |

Each line lists the functions that rely on it and links to the page that manages it. The
[network map](network-map.md) shows the same servers with the ports they must accept and open.

```bash
pskit resources onprem servers usage            # every server
pskit resources onprem servers usage edge1 --json
```

## Edit or forget a server

**Edit** on a row opens *Edit server &lt;name&gt;* with the same fields; leave **SSH password** empty to keep the
saved one. Services already created on the server keep their own copy of the connection, so editing does not move
them.

**Forget** removes the saved server from this project; services and software already on it keep running.

1. Click **Forget** on the row. The confirmation *Forget server &lt;name&gt;?* lists where it is still used.
2. If the server is in a scaling cluster, forgetting is refused: take it out first (`pskit cluster leave CLUSTER
   SERVER`, or remove the cluster).
3. Click **Forget**. Any other place that still names it (the deploy target in `pskit.yml`, a resource) is shown as a
   warning: point it at another saved server. A saved password file no other server uses is deleted.

```bash
pskit resources onprem servers remove lab
```

## Use a saved server everywhere

A saved server name works in every on-prem command and picker:

| Task | Studio | CLI |
|---|---|---|
| Create a service there | create form **Where: One SSH server → Server**, or **Install / create** on the row | `pskit resources onprem create KEY --service ID --server edge1` |
| Install software | **Install / create** on the row | `pskit resources onprem create node --service nodejs --server edge1` |
| Run commands | **Shell** on the row | `pskit resources onprem shell edge1 "docker ps"` |
| Full terminal | **Terminal** on the row | `pskit resources onprem terminal --server edge1` |
| Deploy the functions there | **Overview → Saved server**, or **Deploy → Machine** for one run | `pskit deploy --server edge1` |
| Logs, tests, sends | **Logs → Server** | `pskit logs --server edge1`, `pskit resources send --server edge1 jobs` |

In `pskit.yml` a stage deploys to a saved server with `provider.options.deploy.server`. The server's host, user,
port and login replace those in `options.deploy`; `method` stays `ssh`, `scp` or `docker` (anything else becomes
`ssh`), and the server's home, bind and data directory fill in when `pskit.yml` does not set them:

```yaml
provider:
  name: onprem
  options:
    deploy: {server: edge1, path: /opt/shop}
```

A name that is no longer saved stops the deploy with *no saved SSH server 'X'*, the saved names and close matches.
Details: [deployment](../deployment/README.md).

## See also

- [On-prem overview](README.md)
- [Terminal, console and software](terminal-and-software.md)
- [On-prem services](services/README.md)
- [Scaling clusters](scaling/README.md)
- [Network map](network-map.md) and [firewall](firewall.md)
- [Deployment](../deployment/README.md)
