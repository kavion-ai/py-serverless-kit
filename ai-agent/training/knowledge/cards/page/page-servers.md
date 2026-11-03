# Studio: Servers

How to open: The Servers panel is on the On-prem services area opened from Resources. The cluster empty state links to Resources, then On-prem services, then Servers. The panel heading is Servers.

What it is for: Save each SSH machine once, then reuse it for services, installs, a shell, a terminal, or a deploy. The intro says you deploy with `pskit deploy --server NAME` or Deploy, then Machine.

What you see: Re-check (Checking… while the first reachability probe runs). Its title is "Probe every server's SSH port again". + Add server opens a drawer titled "Add a server", or "Edit server <name>" when editing. The button is Save and test, or Saving… while the request runs. Fields: Name (error "start with a letter; letters, digits, _ . -", or "already saved"), Host (error "host name or IP"), User, SSH port, Log in with, Private key (.pem) for a key login, SSH password for a password login, Use sudo, Home path, Bind address, Data directory, and Description. Log in with is Key file (.pem), SSH agent / default key, or Password. The table columns are a reachability mark, Name, Connection, Login, and Used in. Row actions include Test, Live (title "Live CPU, RAM and disk use (every 4 s while on)"), Shell (title "Run commands on the server"), Terminal (title "A full SSH terminal in the browser (Docker)"), Install / create, Edit, and Forget.

What you can do: Save and test calls `api.onpremServerSave`. An empty user is stored as the string root. SSH port is sent as the number you set, or 22. A password login is described as saved in .pskit/ssh/ (owner-only, out of git) and used through sshpass on Linux and macOS. The password help says that on Windows you run `pskit resources onprem ssh-key` once and then use the key. Home path help says an empty value means /opt/pskit for functions and the SSH user's home for cluster files. Bind address help allows 0.0.0.0, 127.0.0.1, or one of the server's IPs, and says empty means 127.0.0.1 for functions and 0.0.0.0 for services. Forget asks "Forget server <name>?". Shell opens "Shell on <name>". Terminal opens a drawer that embeds the terminal URL.

```
pskit deploy --server app-1
```

Tips and limits: This card does not copy the host placeholder or the user placeholder from the form. Use a documentation-range address such as 192.0.2.10 and the login deploy when you need an example. Install / create opens the create-service flow with that server selected.

Sources: `dashboard-ui/src/studio/components/OnPremMachines.tsx`, `docs/studio.md#project-environment-trigger-resources-and-remove`
