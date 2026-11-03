# Studio: Create function wizard

How to open: Functions > + Create function

The same wizard edits an existing function. The header is "Create function", or "Edit <name>" when a function is already selected. The subtitle is "Target: <provider display name>. Triggers the provider can't run are disabled."

What it is for: Add or change one function in the draft. docs/studio.md describes four steps: basics, triggers, environment and permissions, and a review that shows a YAML diff. Applying the wizard updates the in-memory draft. The toast says "Created <name> (not saved yet)" or "Updated <name> (not saved yet)". The top bar Save writes pskit.yml.

What you see: The stepper labels are Basics, Triggers, Environment & permissions, and Review. Basics has Function name, Deploy, Description, and Handler. The handler help says it is derived from the name until you edit it. A new function starts with its own folder (`subproject` state begins true). The Dependencies toggle is "Own folder with its own <requirements.txt or package.json>". On premises, Basics also has Runs on, which writes provider.options.placement. Runtime, Memory (MB), Timeout (s), and Architecture can inherit the provider defaults. Triggers has section Add a trigger. Types the provider cannot run are listed as "Not available on <provider>", with the providers that can run them. Environment & permissions has Environment variables (hint "merged over the provider-wide ones"), Concurrency & tags, Permissions (IAM), and Provider-specific options when the provider has function fields. Review is section Changes to pskit.yml, a before/after diff, and the toggle "Create the handler stub in the code now (otherwise when you save)".

What you can do: Next moves one step. The button text is "Next: <step>". ← Back goes to the previous step and is disabled on Basics. Cancel returns to the function list. Open code is shown only while editing, and it links to the handler file. Create function or Apply changes calls `apply`. If fields are blocking, the toast is "Fix the highlighted fields first" and the review shows "Some steps have errors. Fix them before creating the function." Renaming asks "Rename <old> to <new>?" and updates workflow task states and resource bindings. A new handler stub is written with `api.ensureHandler` when the review toggle is on. If that call fails, the stub is queued and the toast says it will be created on save.

Tips and limits: Suggested Python handlers look like `functions.<name>.handler.main`. Node handlers look like `functions.<name>.index.main`. Disabled functions stay in pskit.yml. The Deploy help for a new function says "Off: kept in pskit.yml but never deployed."

Sources: `dashboard-ui/src/studio/views/Functions.tsx`, `docs/studio.md#what-you-can-do`
