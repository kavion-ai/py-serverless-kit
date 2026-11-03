# Studio: How to use

How to open: Resources > How to use

The button title is "Libraries, pskit.yml, Python / Node.js code and tests". The drawer title is "How to use <key>".

What it is for: Show the end-to-end guide for that resource at the top-bar provider and stage. The component loads `api.resourceUsage`, which returns markdown. docs/studio.md says the guide includes the library to install for Python and Node.js, how pskit packages it, the pskit.yml and trigger, handler code, local tests (`pskit invoke`, `pskit dev`), deployed tests, and provider notes.

What you see: The intro says the guide is for "<provider> / <stage>, from the saved pskit.yml". If the draft is dirty it adds "you have unsaved changes: save to include them". Copy guide copies `doc.markdown`. Test it closes toward the resource test. The same intro prints the terminal command with the resource key and the top-bar provider and stage. A matching command from the CLI help is:

```
pskit resources usage orders-db -p onprem -s dev
```

What you can do: Read the rendered markdown in the drawer. Copy it. Jump to Test it to send a message or object, for types that support that. An on-prem service has a second drawer with the same title pattern, "How to use <service key>", implemented by `ServiceUsageDrawer`. That one calls `api.onpremUsage` and has a toggle "Show passwords and URLs". Its terminal line is `pskit resources onprem usage <key>`. The flag that shows passwords in the CLI guide is `--reveal`.

```
pskit resources onprem usage inbound-mail --reveal
```

Tips and limits: The resource guide is generated from the saved pskit.yml, so a new resource appears after Save. The on-prem service guide can reveal passwords and URLs. Leave that toggle off when someone else can see the screen. DNS guide on an smtp row opens the service usage drawer for that key. The record values themselves are described in docs/smtp/README.md.

Sources: `dashboard-ui/src/studio/views/Resources.tsx`, `dashboard-ui/src/studio/components/OnPremServices.tsx`, `docs/studio.md#project-environment-trigger-resources-and-remove`
