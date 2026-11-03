# Create a function

Search terms: create function, new function, add function, handler, scaffold, pskit init, own folder, sub-project, requirements.txt per function, pskit function split, Node.js handler, TypeScript handler, handler stub

This page shows how to add a pskit function in studio and from the terminal, where its code lives (one shared code
file or its own folder with its own dependencies) and how to write the handler in Python, JavaScript or TypeScript.

## Create a function in studio

The studio **Functions** page has a four-step wizard that writes the `functions:` entry for you and can create the
handler code.

1. Start studio in the project folder: `pskit studio --open` (default address `http://127.0.0.1:8770`).
2. In the sidebar, click **Functions**, then **+ Create function** (top right). With no functions yet, the empty
   table also has a **Create your first function** button.
3. Step **1 Basics**:
   - **Function name**: letters, digits, `-` and `_`, starting with a letter (max 63). Default `my-function`.
   - **Deploy**: on by default. Off writes `enabled: false` (kept in `pskit.yml`, never deployed).
   - **Description**: free text.
   - **Handler**: derived from the name until you edit it (see the next section for the format).
   - **Dependencies**: the toggle **Own folder with its own requirements.txt** (`package.json` for Node.js) is on by
     default. See [Choose between a shared code file and an own folder](#choose-between-a-shared-code-file-and-an-own-folder).
   - **Runs on** (on-premises only): the placement group, server or cluster this function runs on.
   - **Runtime**, **Memory (MB)**, **Timeout (s)**, **Architecture**: leave them on `inherit` to use the provider values.
4. Click **Next: Triggers →**. Click a trigger card (**HTTP endpoint**, **Schedule**, **Queue**, **Storage**,
   **Topic**, **E-mail (SMTP)**) and fill its form. Cards the selected provider cannot run are hidden; a line under
   the cards names them and the providers that support them. No trigger at all is fine: the function is invoke-only.
5. Click **Next: Environment & permissions →** to set the log level, environment variables, concurrency, tags and
   IAM ([configuration.md](configuration.md)).
6. Click **Next: Review →**. You see a diff of the `pskit.yml` change. The toggle **Create the handler stub in the
   code now (otherwise when you save)** is on by default.
7. Click **Create function**. A toast says `Created <name> (not saved yet)` and, with the stub toggle on,
   `Created handler stub in <file>`.
8. Click **Save** in the top bar (or press Ctrl+S) to write `pskit.yml`. Until then the change is only a draft.

The new row appears on the Functions page with **Test**, **Code**, **Duplicate** and **Delete** buttons. **Code**
opens the handler file on the **Code** page.

## Create a function from the terminal

pskit has no `pskit function add` command. From the terminal you add a function by editing `pskit.yml` and writing
the handler; `pskit init` scaffolds a whole new project with example functions.

1. New project (skip if you already have one):

   ```bash
   pskit init my-api -p aws              # http template: hello, get-item, create-item
   pskit init my-api -p aws -t full      # + schedule, queue, storage and a workflow
   pskit init my-api -p gcp --typescript # Node.js 20 + TypeScript
   cd my-api
   ```

   Templates (`-t`): `http`, `events`, `workflow`, `full`. A Python project gets `pskit.yml`, `app/__init__.py`,
   `app/handlers.py`, `requirements.txt`, `tests/test_handlers.py` and `.gitignore`.
2. Add the function to `pskit.yml`:

   ```yaml
   functions:
     send-invoice:
       handler: functions.send_invoice.handler.main
       description: E-mails an invoice
       events:
         - http: POST /invoices
   ```
3. Write the handler file (`functions/send_invoice/handler.py`, with an empty `functions/__init__.py` and
   `functions/send_invoice/__init__.py`) and, for an own folder, `functions/send_invoice/requirements.txt`.
4. Check it: `pskit validate` (add `-p gcp` to check another cloud).
5. Run it: `pskit invoke -f send-invoice -d '{"order": 1}'`.

## Write the handler path

The pskit `handler:` value is `package.module.function` (or `package.module:function`), relative to
`package.source` (default: the project folder).

| Handler | File | Function |
|---|---|---|
| `app.handlers.hello` | `app/handlers.py` (or `app/handlers/__init__.py`) | `hello` |
| `functions.resize.handler.main` | `functions/resize/handler.py` | `main` |
| `handler:on_mail` | `handler.py` | `on_mail` |

Rules checked by `pskit validate`: each part starts with a letter or `_`; the function name after the last `.` or `:`
must exist when the code is imported. Node.js uses the same form: `src.handlers.hello` is the `hello` export of
`src/handlers.ts` (or `.js`, `.mjs`, `.cjs`, or `src/handlers/index.js`).

## Choose between a shared code file and an own folder

A pskit function's code either sits in a shared module with other functions or in its own folder (a sub-project).

| Layout | Handler | Dependencies |
|---|---|---|
| Shared code file | `app.handlers.get_item` | the project's `requirements.txt` (or `package.json`) |
| Own folder | `functions.get_item.handler.get_item` | `functions/get_item/requirements.txt` (or `package.json`) plus the project's |

A folder becomes a function's own folder when it (or a parent below `package.source`) holds a `requirements.txt`
(Python) or `package.json` (Node.js). On every cloud its requirements are added to the bundle. On premises with
`provider.options.placement`, each server gets only the code and requirements of the functions placed on it, and
Node.js sub-projects get their own `node_modules`. See [../onprem/placement.md](../onprem/placement.md).

```text
functions/
  resize/
    __init__.py
    handler.py          # handler: functions.resize.handler.main
    requirements.txt    # only what resize needs (Pillow, ...)
  report/
    index.js            # handler: functions.report.index.main
    package.json        # only what report needs
```

In studio the wizard's **Own folder with its own requirements.txt** toggle (new functions only) suggests the handler
`functions.<name_with_underscores>.handler.main` (`index.main` for Node.js) and creates the folder with an empty
dependency file. Turn it off to suggest `app.handlers.<name>` in the shared file.

## Move an existing function to its own folder

`pskit function split` moves a Python function out of a shared code file into `functions/<name>/handler.py`.

```bash
pskit function split get-item           # one function
pskit function split --all --dry-run    # show what would move for every function sharing a file
pskit function split --all
```

```text
would move cover: app/handlers.py -> functions/cover/handler.py (handler functions.cover.handler.cover)
  copied helpers: _PIXEL, get_book (still in app/handlers.py for the others)
```

What it does:

- Copies the handler plus the module-level helpers and imports it uses (helpers stay in the old file too).
- Removes the handler from the old file, unless code left there still calls it ("kept in ... too").
- Writes `functions/<name>/requirements.txt` with the lines of the project's `requirements.txt` that its imports
  name. Imports with no matching line are listed in a comment to check.
- Updates `handler:` in `pskit.yml`.

In studio: on the **Functions** page a function that shares a file shows a **shared file** badge and an **Own folder**
button. Click it, save first if asked (**Save and continue**), read the plan, then click **Move it**. On premises with
placement a banner offers **Give each function its own folder** for all of them.

Limits: Python only (a Node.js handler is moved by hand to `functions/<name>/index.js` with a `package.json`); the
function must not already have its own folder; `functions/<name>/handler.py` must not exist.

## Write a Python handler

A pskit Python handler takes the event and, optionally, the context. It can be `async`.

```python
from py_serverless_kit import BadRequest, Context, Event


def create_order(event: Event, ctx: Context):
    order = event.http.json()                 # invalid JSON -> 400 automatically
    if "amount" not in order:
        raise BadRequest("amount is required")
    ctx.logger.info("order received", extra={"amount": order["amount"]})
    return {"id": 42, **order}, 201           # JSON body + status


async def ping(event: Event):                 # one argument and async both work
    return "pong"
```

Studio's stubs are made per first trigger type (`http`, `schedule`, `queue`, `storage`, `topic`, invoke). Keep code
Python 3.9 compatible if any target cloud runs 3.9. Handler code must not import cloud SDKs for portable features;
see [../handlers.md](../handlers.md).

## Write a Node.js or TypeScript handler

A pskit service is either Python or Node.js: `provider.runtime: nodejs18 | nodejs20 | nodejs22 | nodejs24` makes
every function Node.js. TypeScript is compiled for you.

```ts
import { NotFound } from "pskit";
import type { Context, Event } from "pskit";

export async function getItem(event: Event, ctx: Context) {
  const id = event.http!.pathParams.id;
  if (id !== "1") throw new NotFound("no such item");
  ctx.logger.info("found", { id });
  return { id, name: "lamp" };
}
```

The API mirrors Python in camelCase (`pathParams`, `requestId`, `remainingTimeMs()`, `invoke("fn", data)`). A
function's `runtime:` may pick another Node.js version, never Python. Details: [../nodejs.md](../nodejs.md).

## Common errors when creating a function

| Message | Fix |
|---|---|
| `handler 'x' must be 'package.module.function' (or 'module:function')` | use at least `module.function` |
| `name 'X' must start with a letter and use letters, digits, - or _` | rename the function |
| `function 'x' uses nodejs20 but the service runtime is python3.12` | one language per service |
| `route GET /items is used by both 'a' and 'b'` | each `METHOD /path` belongs to one function |
| `<file> has a syntax error at line N` (studio stub, split) | fix the file first |
| `x already has its own folder` (split) | nothing to do |

## See also

- [README.md](README.md)
- [configuration.md](configuration.md)
- [invoke-and-test.md](invoke-and-test.md)
- [../triggers/README.md](../triggers/README.md)
- [../studio-guide/functions.md](../studio-guide/functions.md)
- [../nodejs.md](../nodejs.md)
- [../onprem/placement.md](../onprem/placement.md)
