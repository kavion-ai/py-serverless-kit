# On-premises service: Nginx Proxy Manager (reverse proxy, Let's Encrypt)

The catalog id is `nginx-proxy-manager`. Kind is service. Group is Web. Image is jc21/nginx-proxy-manager:latest. Published port is 81. Extra ports are 80, 443. Roles are custom. Backup is no. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Admin UI. GUI login choices are none.

Catalog notes: Point domains at your functions (port 8080) and services with free HTTPS certificates, from a web UI. First login admin@example.com / changeme (you are asked to change it). Needs ports 80 and 443 free.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-nginx-proxy-manager --service nginx-proxy-manager
pskit resources onprem status sample-nginx-proxy-manager
```

pskit resources onprem usage sample-nginx-proxy-manager prints how to connect. pskit resources onprem logs sample-nginx-proxy-manager shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
