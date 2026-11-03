# Functions page in studio

Search terms: functions page, create function, function wizard, edit function, handler, own folder, requirements, duplicate function, delete function, disable function, enabled, IAM, permissions, concurrency, log level, split function, shared file

The **Functions** page lists the project's functions and opens the four-step **Create function** wizard, modelled on
the AWS Lambda console. Sidebar: **Functions** (λ); the number is the count of functions. Each function is a handler
plus the triggers that call it (`functions:` in `pskit.yml`).

## Read the functions table in studio

The studio functions table has one row per function. Click a row (or its name) to edit it.

| Column | What it shows |
|---|---|
| **Function** | Name, description, an **error** badge, the placement group (on premises) and a **shared file** badge when its handler file holds other functions |
| **Kind** | `http`, `scheduled`, `http+event`, `event-driven` or `invoke-only`, from its triggers |
| **Deploy** | **● Enabled**, **◐ Disabled on <Provider>** or **○ Disabled everywhere** (see below) |
| **Triggers** | One chip per trigger, or "direct invoke" |
| **Runtime** | Runtime · memory · timeout; grey values are inherited from Overview |
| **Handler** | `package.module.function` |

Row buttons: **Test** (opens the [Test page](test.md) on it), **Code** (opens the handler in the [Code page](code.md)),
**Own folder** (only on shared files), **Duplicate** and **Delete**. The search box filters by name, handler and
trigger. Under the table, studio lists the generated `<workflow>-orchestrator` functions pskit adds itself on clouds
without a native workflow engine.

## Enable or disable a function on one provider

The **Deploy** dropdown in a function row (and in the wizard's Basics step) has three choices:

| Choice | Written to `pskit.yml` |
|---|---|
| **● Enabled** | nothing (the default) |
| **◐ Disabled on <Provider>** | `providers.<provider>.functions.<name>.enabled: false` |
| **○ Disabled everywhere** | `functions.<name>.enabled: false` |

A disabled function stays in `pskit.yml` but is not deployed.

## Duplicate or delete a function in studio

**Duplicate** creates `<name>-copy` with the same settings and opens it. HTTP triggers are not copied, because
routes must be unique.

**Delete** asks **Delete function <name>?**. If a workflow calls the function, the dialog names it: those workflows do
not validate until you point their task states at another function. The function and its triggers are removed from
`pskit.yml` and from every resource's `functions:` list. The handler code is not deleted.

## Give a function its own folder in studio

A function whose handler shares a Python file with other functions gets a **shared file** badge and an **Own folder**
button. On premises with placement, a yellow bar also says "N functions share a code file" with **Give each function
its own folder**.

1. Click **Own folder** (or the bar's button). If the draft is unsaved, studio asks **Save first?** (**Save and
   continue**), because the move rewrites `pskit.yml` on disk.
2. **Move <name> to its own folder?** shows the plan: the handler and the module-level helpers and imports it uses move
   to `functions/<name>/` with its own `requirements.txt`. Helpers are copied, so other functions keep theirs.
3. Click **Move it** (or **Move N functions**). The toast says where the function now lives.
4. If the plan names unknown imports, check the new `requirements.txt` for them.

From the terminal: `pskit function split get-item`. Python only.

## Create a function with the studio wizard

The studio **Create function** wizard has four steps: **Basics**, **Triggers**, **Environment & permissions** and
**Review**. A red dot on a step means it has errors.

1. Open **Functions** and click **+ Create function** (or **Create your first function**).
2. Fill in each step (sections below). Use **Next: <step> →** and **← Back**, or click a step name.
3. On **Review**, click **Create function**. **Cancel** (top right) leaves without changes.
4. The toast says "Created <name> (not saved yet)". Press **Save** in the top bar.

The subtitle says the target provider: "Triggers the provider can't run are disabled." Editing an existing function
opens the same wizard titled **Edit <name>**, with **Open code** and **Apply changes**.

The terminal equivalent is to add the function to `pskit.yml` by hand:

```yaml
functions:
  resize:
    handler: functions.resize.handler.main
    memory: 512
    events:
      - storage: {bucket: uploads, events: [created]}
```

Details on every key: [Create functions](../functions/create.md) and [Function configuration](../functions/configuration.md).

## Wizard step 1: Basics

The Basics step of the studio function wizard sets the name, handler and resources of the function.

| Field | Notes |
|---|---|
| **Function name** (required) | Starts with a letter; letters, digits, `-` and `_` (max 63). Default `my-function` |
| **Deploy** | New function: a toggle (**enabled** / **disabled everywhere**). Existing: the three-way dropdown above |
| **Description** | "What does it do?" |
| **Handler** (required) | `package.module.function`, for example `app.handlers.process`. Derived from the name until you edit it |
| **Dependencies** (new functions) | **Own folder with its own requirements.txt** (or `package.json`), on by default |
| **Runs on** (on premises) | The placement group (server) it runs in; see [placement.md](placement.md#pick-where-one-function-runs-runs-on) |
| **Runtime** | Empty = inherit from Overview |
| **Memory (MB)** | Empty = inherit |
| **Timeout (s)** | Up to the provider's maximum; empty = inherit |
| **Architecture** | **inherit**, **x86_64** or **arm64** |

With **Own folder** on, the handler becomes `functions.<name>.handler.main` (Python) or
`functions.<name>.index.main` (Node.js), and studio creates `functions/<name>/requirements.txt` (or `package.json`):
that function's own dependencies, installed only with it. Off, the handler is `app.handlers.<name_with_underscores>`
(Node.js: `src.handlers.<camelCase>`) and it uses the project's dependencies. On premises with placement, the help
line says which servers install which requirements.

Renaming an existing function asks **Rename <old> to <new>?**: workflow task states and resource bindings that name it
are updated too.

## Wizard step 2: Triggers

The Triggers step of the studio function wizard adds the events that call the function.

1. **Add a trigger** shows a card per trigger type the provider supports: **HTTP endpoint**, **Schedule**, **Queue**,
   **Storage**, **Topic** and **E-mail (SMTP)**. A card may say "N provider limitations" in orange.
2. Types the provider cannot run are listed under "Not available on <Provider>:" with the providers that can.
3. Click a card. A new section opens with the trigger's form; each type's form is described in
   [trigger-forms.md](trigger-forms.md).
4. Each trigger section has **Disable on <Provider>** (keep the trigger for other providers but do not create it on
   this one; writes `providers.<provider>.functions.<name>.events`) and **Remove**. A disabled trigger shows the badge
   **off on <Provider>**.
5. A trigger with an error shows **fix** and a red message, for example "route GET /items is already used by another
   function", "pick a rate or a cron expression", "a name or resource is required", "a bucket or resource is
   required" or "pick the SMTP server (an smtp resource) that receives the mail".

No triggers is fine: "The function can still be called with invoke() or from a workflow."

## Wizard step 3: Environment & permissions

The Environment & permissions step of the studio function wizard has five sections:

- **Logging**: **Log level** (**inherit**, **DEBUG**, **INFO**, **WARNING**, **ERROR**) sets `PSKIT_LOG_LEVEL` in
  the function's environment; `ctx.logger` output below it is dropped. **Live logs** (existing functions) shows the
  deployed function's logs for the top bar's provider and stage; see [logs.md](logs.md).
- **Environment variables** ("merged over the provider-wide ones"): `functions.<name>.environment`.
- **Concurrency & tags**: **Reserved concurrency / max instances** (`concurrency`, empty = provider default) and
  **Tags**.
- **Permissions (IAM)** (closed, "advanced"): **Existing role** (an ARN or service account instead of the one pskit
  creates; `iam.role`) and statements with **Effect** (**Allow** / **Deny**), **Actions** (comma separated, e.g.
  `s3:GetObject, dynamodb:Query`) and **Resources** (comma separated ARNs; empty = `*`). **+ Add statement** adds
  one; **Remove** drops it.
- **Provider-specific options** (`functions.<name>.options`), when the provider has any.

## Wizard step 4: Review

The Review step of the studio function wizard shows **Changes to pskit.yml** as a diff of the function entry (and of
`provider.options.placement` when **Runs on** changed it).

- **Create the handler stub in the code now (otherwise when you save)** is on by default. On, studio writes the stub
  immediately ("Created handler stub in app/handlers.py"); off, it writes it after the next **Save**.
- The stub has the right signature for the trigger types (for example a queue handler returns a `BatchResult`).
- "Some steps have errors. Fix them before creating the function." blocks **Create function**.

## See also

- [Trigger forms](trigger-forms.md)
- [Functions overview](../functions/README.md), [create](../functions/create.md),
  [configuration](../functions/configuration.md), [invoke and test](../functions/invoke-and-test.md)
- [Triggers](../triggers/README.md)
- [Placement](placement.md)
- [Test page](test.md) and [Code page](code.md)
