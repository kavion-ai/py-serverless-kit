## Install software on a server

The catalog's *Install on a server* groups install with the server's package manager (apt, dnf, yum or apk), over SSH:

| Software | Versions | Notes |
|---|---|---|
| **Python 3** | `system` (default), 3.13, 3.12, 3.11, 3.10, 3.9, 3.14 | `system`: the distribution's python3 with venv and pip. A version: that exact CPython (standalone build through uv, any distribution) in `/opt/pskit-python`, linked as `/usr/local/bin/python3.X`; the host then runs with `python: system` and `runtime: python3.X` |
| Docker | distribution | installed and started |
| **Node.js** | 22 (default), 24, 20, 18 | NodeSource packages with npm (Alpine: its own version) |
| Java (OpenJDK) | 21, 17 | headless runtime |
| Go | 1.23.4 (any `1.x.y`) | official toolchain in `/usr/local/go` |
| **nginx** | distribution | enabled and started; put a reverse proxy to the pskit host in `/etc/nginx/conf.d/` |
| Caddy | 2.8.4 | the `caddy` binary (automatic HTTPS) |
| Certbot | distribution | with the nginx plugin where available |
| PM2 | npm | needs Node.js first |
| Git, basic tools | distribution | curl, wget, unzip, jq, htop, tmux, netcat |

Studio: *Servers → Install / create* opens the catalog with that server chosen. Each install is listed with the
services; *Details* runs its version check. pskit never uninstalls software (*Remove* only forgets it).
