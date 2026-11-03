# On-premises: On-premises deploy on this machine

- **Terraform:** built-in `terraform_data` (no plugin download). Create/destroy run `onprem_deploy.py` via `local-exec`
- **Credentials:** none for `method: local`. For `method: ssh` (or `scp`), a `.pem` (`options.deploy.pem` or `identity_file`) or the SSH agent. `pskit deploy` asks for the `.pem` on a terminal; Enter keeps the agent. For `method: docker` on a server, a `.pem` is required, plus OpenSSH on the laptop and a Docker CLI to build the image. `docker_host: tcp://`, `unix://`, or `npipe://` still talks to that daemon and does not use SSH
- **Dependencies:** native pip wheels for a local host; manylinux / Windows / macOS wheels matching `deploy.target_os` and `architecture` for a remote host. `tzdata` is vendored so cron timezones work on Windows

**Resources:** `terraform_data.host` with create (`onprem_deploy.py apply`) and destroy (`onprem_deploy.py destroy`) `local-exec` provisioners.

These steps run on the on-premises provider. Saved servers are named once and then reused by deploy, services, and clusters. Open the matching studio page from the left navigation. Scaling cluster, Load balancers, Network map, and Resources are the pages for this work.

```
pskit validate
pskit resources onprem catalog
```

pskit resources onprem catalog lists the services and runtimes the create command can start. Passwords generated for a service are stored in the env file and under .pskit/, and they are left out of pskit.yml.
