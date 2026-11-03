## 1. Always: the admin machine reaches every server over SSH

| | From | To | Port | Why |
|---|---|---|---|---|
| 🟥 | Admin machine | **every** saved server (function, cluster, load balancer, resource) | **TCP *22*** (the server's SSH port) | scripts, copying the release / image (`scp`), logs, tests, status |
| 🟥 | every server, **outbound** | Internet **TCP 443 / 80** | — | first time only: install Docker (`get.docker.com`, distro repos), pull images (Docker Hub), k3s (`get.k3s.io`, GitHub), Nomad (`releases.hashicorp.com`) |
| 🟥 | Admin machine, **outbound** | Internet **TCP 443** | — | PyPI / npm while packaging; `python: bundle` / `node: bundle` downloads; Docker base images for `method: docker` |

Servers with no Internet: preinstall Docker (and k3s / Nomad), and load the images yourself (`docker load`).
pskit copies the function image itself over SSH, so no registry is needed.

These steps run on the on-premises provider. Saved servers are named once and then reused by deploy, services, and clusters. Open the matching studio page from the left navigation. Scaling cluster, Load balancers, Network map, and Resources are the pages for this work.

```
pskit validate
pskit resources onprem catalog
```

pskit resources onprem catalog lists the services and runtimes the create command can start. Passwords generated for a service are stored in the env file and under .pskit/, and they are left out of pskit.yml.
