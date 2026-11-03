# pskit studio guide

Search terms: pskit studio, studio, web UI, browser editor, sidebar, launch studio, token URL, draft, save, validate, keyboard shortcuts, undo, redo, ailogs, vscode-image

`pskit studio` is a local web app that edits a pskit project with forms. Everything it produces is an ordinary
`pskit.yml` plus code files, so the CLI, CI and code review keep working. This guide walks through every page of the
studio, button by button. The concepts behind each page (what a trigger is, how a cluster works) are explained in the
topic guides it links to.

## Install and start pskit studio

pskit studio ships with the `py-serverless-kit` package; there is nothing extra to install.

1. Install pskit (Python 3.9 or newer):

   ```bash
   pip install py-serverless-kit
   ```

2. Go to your project folder (the one holding `pskit.yml`), or to an empty folder for a new project:

   ```bash
   cd my-service
   pskit studio --open
   ```

3. The terminal prints the address, with a session token after `#token=`:

   ```text
   pskit studio for /home/me/my-service
   Open http://127.0.0.1:8770/#token=q3V...  (Ctrl+C to stop)
   ```

4. With `--open` the browser opens that link. Without it, copy the link into the browser.
5. Press **Ctrl+C** in the terminal to stop studio.

When the folder has no `pskit.yml`, studio shows the [New project](new-project.md) page instead of the sidebar.

## pskit studio command-line flags

The `pskit studio` command takes these options (from `pskit studio --help`):

| Option | Default | What it does |
|---|---|---|
| `-d, --dir DIRECTORY` | `.` | The project root (the folder with `pskit.yml`, or an empty folder) |
| `--host TEXT` | `127.0.0.1` | Bind address. Any address other than loopback prints a warning, because studio edits files and runs deploys |
| `--port INTEGER` | `8770` | Port |
| `--open` | off | Open the link in the browser |
| `--vscode-image TEXT` | `codercom/code-server:4.96.4` | Image for **Code → Full VS Code** (also the `PSKIT_STUDIO_VSCODE_IMAGE` variable) |
| `--ailogs BOOLEAN` | off | Print every step of Hana's chats in this terminal: messages, model requests and answers, tool calls with arguments and results, plans, cards, errors. Passwords stay hidden. `--ailogs` or `--ailogs=true` |

Examples:

```bash
pskit studio --open
pskit studio -d path/to/project --port 8800
pskit studio --ailogs=true        # Hana's conversations, tool calls and results in this terminal
```

## The studio session token and the link

Every studio API call needs the session token from the printed link (`#token=...`). A new token is made each time
studio starts. The token stays in the browser tab and is never written to disk.

- If you open `http://127.0.0.1:8770/` without the token, studio shows **This studio session needs its link**. Open
  the printed link again, or restart with `pskit studio --open`.
- Anyone who has the link has full access to the project and your cloud credentials. Do not share it.
- `--host 0.0.0.0` makes studio reachable from other machines. Only do this on a trusted network.

Studio also refuses requests with a foreign `Host` header or a cross-site `Origin`, and caps request bodies at 2 MiB.

## The studio sidebar map

The studio sidebar lists the same 13 pages for every provider, in this order. A number next to **Functions**,
**Workflows** and **Resources** counts the entries; a red number counts validation problems on that page.

| # | Sidebar label | Page guide | What you do there |
|---|---|---|---|
| 1 | Overview & provider | [overview.md](overview.md) | Service name, provider cards, defaults for every function, provider options, on-prem deployment |
| 2 | Setup & credentials | [setup.md](setup.md) | Tool and credential checks, AWS profile, session variables, `.venv`, move settings to another machine |
| 3 | Functions | [functions.md](functions.md) | Function table and the 4-step **Create function** wizard; trigger forms in [trigger-forms.md](trigger-forms.md) |
| 4 | Workflows | [workflows.md](workflows.md) | Visual state-machine builder |
| 5 | Resources | [resources.md](resources.md) | Buckets, queues, topics, databases; drivers; tester; data viewer; [on-prem services](onprem-services.md) and [servers](servers.md) |
| 6 | Scaling cluster | [cluster.md](cluster.md) | Docker Swarm, k3s or Nomad over several servers |
| 7 | Load balancers | [load-balancers.md](load-balancers.md) | Shared on-prem load balancers |
| 8 | Network map | [network.md](network.md) | Machines and the connections each must accept or open |
| 9 | Code | [code.md](code.md) | Built-in editor or **Full VS Code** |
| 10 | Test | [test.md](test.md) | Run a function locally or send a real event |
| 11 | Deploy | [deploy.md](deploy.md) | Validate, package, plan, deploy, info, remove; placement; firewall |
| 12 | Logs | [logs.md](logs.md) | Live logs and stored log streams |
| 13 | YAML | [yaml.md](yaml.md) | Preview, diff and raw edit of `pskit.yml` |

Pages that only work on premises stay in the sidebar for every provider. **Scaling cluster** and **Load balancers**
show a warning box when the project's provider is not `onprem` (switch it in Overview). **Network map** lists on-prem
machines only. The **Run on** machine picker, **Where functions run** and **Firewall** on the Deploy page, and the
**Data** button on Resources, appear only when the target provider is `onprem`.

Panels that are not sidebar pages have their own guides: [Hana, the AI assistant](hana.md), the
[Firewall panel](firewall.md), [Placement (Where functions run)](placement.md), [Replication](replication.md) and
[Monitoring and alerts](monitoring.md).

## The studio top bar

The studio top bar is the same on every page:

| Control | What it does |
|---|---|
| ☰ (narrow windows) | Opens the sidebar |
| Service name (λ logo) | Goes to Overview |
| **validate & deploy as** | The provider used for validation, Deploy, Test and Logs. It does not change `pskit.yml` |
| **stage** | The stage for validation, Deploy, Test and Logs (lowercase letters, digits and `-`, up to 16 characters) |
| ↶ / ↷ | Undo / redo |
| **N errors · N warnings** | Opens the **Problems** panel; click a problem to jump to the page and field it concerns |
| **Validate** | Validates the draft now |
| **Save** / **Saved** | Writes `pskit.yml` (a dot means unsaved changes) |
| **⇅ Settings** | Opens **Import / export settings and config** (see [setup.md](setup.md#move-studio-settings-to-another-machine)) |
| ◐ | Light / dark theme, remembered in this browser |

The round Hana avatar at the bottom right (**Ask Hana**) opens the [Hana panel](hana.md).

## How studio drafts, validates and saves pskit.yml

Studio keeps every edit in an in-memory draft. Nothing touches disk until you press **Save**.

1. Each change (a form field, a wizard's **Create function**, a delete) updates the draft. Toasts say "(not saved
   yet)".
2. About 0.6 s after you stop typing, studio validates the draft with the same checks as `pskit validate`, for the
   provider and stage in the top bar. The **Problems** button and the red counts in the sidebar update.
3. Press **Save** (or **Ctrl+S**). Studio writes `pskit.yml`, then writes any handler stubs it queued, and shows
   "Saved pskit.yml · created N handler stubs".
4. Before each save the old file is copied to `.pskit/studio/backups/` (the last 20 are kept).

Rules worth knowing:

- Values keep their written form: `${env:API_KEY}`, `${self:...}` and `${opt:...}` are saved as written.
- Comments in `pskit.yml` are not kept, and key order follows the studio layout.
- A config with validation errors can still be saved, so you can stop half-way.
- If `pskit.yml` changed on disk after studio loaded it, **Save** opens **pskit.yml changed on disk** with
  **Cancel**, **Reload (discard my changes)** and **Overwrite**.
- Closing the tab with unsaved changes asks first.
- Commands on the Deploy and Test pages read `pskit.yml` from disk; they ask **Save first?** when the draft differs.

The same model works from the terminal: edit `pskit.yml` in any editor, then run `pskit validate`.

## Studio keyboard shortcuts

Studio keyboard shortcuts work on every page (**Cmd** instead of **Ctrl** on macOS):

| Keys | Action |
|---|---|
| Ctrl+S | Save `pskit.yml` (on the Code page: save the open file) |
| Ctrl+Z | Undo (outside text fields) |
| Ctrl+Shift+Z or Ctrl+Y | Redo (outside text fields) |
| Ctrl+I | Open or close Hana |
| Ctrl+F (in an editor) | Search in the file |

Undo keeps up to 100 steps and works across pages.

## Where pskit studio stores its files

Studio writes these files in the project. `.pskit/` stays out of git.

| Path | What it holds |
|---|---|
| `pskit.yml` | The project (written by **Save**) |
| `.pskit/studio/backups/pskit.<timestamp>.yml` | The previous `pskit.yml` before each save (last 20) |
| `.pskit/studio/test-events.json` | Saved test events from the Test page |
| `.pskit/studio/vscode/` | The Dockerfile of the Full VS Code image |
| `.pskit/studio/hana.json` | Where Hana's model runs |
| `.pskit/studio/hana/sessions/` | Hana's chats (the last 30) |
| `.pskit/onprem-servers.json`, `onprem-services.json`, `onprem-clusters.json`, `onprem-balancers.json` | Saved servers, one-click services, clusters and load balancers |
| `.pskit/ssh/` | SSH passwords saved for servers (owner-only) |
| `.pskit/backups/` | Service backups and settings-import backups |

Move these to another machine with **⇅ Settings** or `pskit settings export` / `pskit settings import`.

## See also

- [Studio end to end, click by click](../guide/end-to-end-studio.md)
- [Concepts](../guide/concepts.md)
- [The same application from the terminal](../guide/end-to-end-cli.md)
- [Older studio overview](../studio.md) and [CLI reference](../cli.md)
