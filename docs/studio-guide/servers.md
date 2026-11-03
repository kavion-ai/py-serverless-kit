# Servers panel in studio

Search terms: servers, saved server, add server, SSH server, VM, machine, pem key, ssh password, sudo, test server, live CPU memory disk, shell, terminal, forget server, used in, home path, bind address, data directory

The **Servers** panel saves each SSH machine once (key file, SSH agent or password). Saved servers are then picked by
name everywhere: deploys, function groups, services, clusters and load balancers. The panel sits at the bottom of the
[On-prem services](onprem-services.md) panel on the **Resources** page (sidebar **Resources**). Servers are stored in
`.pskit/onprem-servers.json`, not in `pskit.yml`. The concepts are in [On-prem servers](../onprem/servers.md).

## Add a server in studio

The studio **Add a server** drawer saves one SSH machine and tests it.

1. Open **Resources** and scroll to **Servers**. Click **+ Add server**. (The same form opens from **+ Add a server…**
   on Overview, the Runs on picker, the cluster join drawer and the load balancer drawers.)
2. Fill in the connection:

   | Field | Notes |
   |---|---|
   | **Name** (required) | How you pick it: `edge1`, `db-box`, `lab` ... |
   | **Host** (required) | IP or DNS name |
   | **User** | The SSH user |
   | **SSH port** | Default 22 |
   | **Log in with** | **Key file (.pem)**, **SSH agent / default key** or **Password** |
   | **Private key (.pem)** | The key file, e.g. `~/.ssh/server.pem` |
   | **SSH password** | Saved in `.pskit/ssh/` (owner-only, out of git) and used through `sshpass` (Linux / macOS) |
   | **Use sudo** | The user is not root and not in the docker group |

3. Optional, under **On this server (optional)**:

   | Field | What it sets |
   |---|---|
   | **Home path** | Where pskit keeps files. Functions deploy to `<home>/<service>-<stage>`; cluster scripts go to `<home>/pskit-cluster`. Empty: `/opt/pskit` for functions, the SSH user's home for cluster files |
   | **Bind address** | Where the functions' host and services listen: `0.0.0.0`, `127.0.0.1` (reached over SSH) or one of the server's IPs. A specific IP is also its cluster address |
   | **Data directory** | Where data lives: services keep data in `<data>/<container>` instead of a Docker volume, and the built-in queues and buckets go there (`provider.options.data_dir`) |
   | **Description** | A note shown in studio |

4. Click **Save and test**. Studio saves the server and logs in once.

On Windows, `sshpass` is not available: install a key once with `pskit resources onprem ssh-key user@host`, then use
**Key file**.

From the terminal:

```bash
pskit resources onprem servers add app-1 --ssh ubuntu@10.0.1.12 --pem ~/.ssh/app.pem --sudo
pskit resources onprem servers add lab --ssh admin@lab.local:2222 --ssh-password-env LAB_PASSWORD
pskit resources onprem servers list
```

## Test and watch a saved server in studio

The Servers table has one row per server: a reachability mark (green when the SSH port answers, with the time), the
**Name**, **Connection**, **Login** and **Used in**. **Re-check** probes every SSH port again (no login).

- **Test** logs in and shows the OS, CPU, memory, disk, Docker access and sudo. The mark then says "Test passed (SSH
  login, Docker, sudo)" or "Test failed".
- **Live** (**Live ●** while on) shows CPU, RAM and disk bars of the server, refreshed every 4 s while on.

```bash
pskit resources onprem servers check
pskit resources onprem servers test app-1
pskit resources onprem servers top app-1
```

## Open a shell or a terminal on a saved server

**Shell** opens **Shell on <name>**: type one command per line and see its output (↑ / ↓ for history, `clear` to
clear). **Full terminal** in it, or **Terminal** on the row, opens a full SSH terminal in the browser (ttyd in Docker on
this machine; the first start builds a small image, about a minute). It listens on 127.0.0.1 behind a secret URL;
closing the panel keeps it running and **Stop terminal** removes it.

```bash
pskit resources onprem shell app-1                 # interactive
pskit resources onprem shell app-1 docker ps       # one command
pskit resources onprem terminal --help
```

## Install software or create a service on a saved server

**Install / create** on a server row opens the [Create a service](onprem-services.md#create-an-on-prem-service-in-studio)
drawer with that server picked: start Redis, PostgreSQL, MinIO and more there, or install Docker, Python, Node.js,
nginx, Java, Go, Caddy, Certbot, PM2, Git and tools. See
[Terminal and software](../onprem/terminal-and-software.md).

## See where a server is used, edit it or forget it

**Used in** on a server row shows how many places name the server; click it to open **Where <name> is used**: deploy
targets, function groups, clusters, load balancers and services, the functions relying on it, and a link to the
[Network map](network.md).

**Edit** opens the same form (**Edit server <name>**). **Forget** asks **Forget server <name>?**: services already
created there keep running and pskit only forgets the connection. The dialog lists where the server is still used;
forgetting is refused while a cluster uses it (take it out of the cluster first).

```bash
pskit resources onprem servers usage
pskit resources onprem servers remove app-1
```

## See also

- [On-prem servers](../onprem/servers.md)
- [On-prem services panel](onprem-services.md)
- [Overview: on-prem deployment](overview.md#choose-where-the-on-prem-host-runs-in-studio)
- [Network map](network.md)
- [Move settings to another machine](setup.md#move-studio-settings-to-another-machine)
