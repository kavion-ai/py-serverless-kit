## In studio
1. Use the server row Test action after the server is saved.

## In the terminal
1. Run:

```
pskit resources onprem servers test app-1
```

2. Run:

```
pskit resources onprem servers check
```

## In code

test logs in and reports OS, CPU, memory, disk, Docker, sudo, and runtimes. check only probes the SSH port.

## Servers: several machines

Save each machine once under **On-prem services → Servers → + Add server** (name, host, user, port, *Log in with*, sudo), or with the CLI. Every place that asks *where* then offers it: the create form's **Server** list, **Deploy → Machine**, the shell and the terminal. They live in `.pskit/onprem-servers.json` (connection details only; a typed password goes to `.pskit/ssh/`, owner-only).

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
