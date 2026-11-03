# Build a full application in studio, click by click (orders service)

Search terms: studio tutorial, end to end studio, web UI, no YAML, click by click, build in browser, pskit studio walkthrough, orders app studio, Hana, create function form

This guide builds the same **orders service** as [end-to-end-cli.md](end-to-end-cli.md), but only by clicking in
`pskit studio`: HTTP API, queue consumer, storage processor, nightly schedule, topic fan-out, a workflow, a
database and a cache, then deploy, test and logs. Read the CLI guide's first section for what each function does.
Every label below is the exact text on screen.

## Start pskit studio in an empty folder

`pskit studio` is a local web server; everything runs on your machine with your credentials.

1. Install pskit (`pip install "py-serverless-kit[aws]"`), create an empty folder and start studio in it:

   ```bash
   mkdir orders && cd orders
   pskit studio --open            # default port 8770; -d PATH for another folder
   ```

2. The browser opens the link the command printed. The link carries a session token; if you open studio
   without it you see *This studio session needs its link*: open the printed link again.
3. The folder has no `pskit.yml`, so studio shows **Create a pskit project**.

## Create the project in the Create a pskit project screen

The **Create a pskit project** screen writes `pskit.yml`, `app/handlers.py`, `requirements.txt` and a test, the
same files as `pskit init`.

1. **Service name**: type `orders`.
2. **Provider**: click the **AWS Lambda** card.
3. **Language**: **Python**.
4. **Template**: **HTTP API** (one HTTP function, the smallest start). *Everything* adds many samples you would
   delete again.
5. Click **Create project**. If files already exist, a *Files already exist* dialog offers **Overwrite**.
   Page details: [studio-guide/new-project.md](../studio-guide/new-project.md).

Studio opens with the sidebar on the left: **Overview & provider**, **Setup & credentials**, **Functions**,
**Workflows**, **Resources**, **Scaling cluster**, **Load balancers**, **Network map**, **Code**, **Test**,
**Deploy**, **Logs**, **YAML**. The top bar has **validate & deploy as** (provider) and **stage**, undo / redo, the
problems counter, **Validate**, **Save**, **⇅ Settings** and the theme switch. Page guide:
[studio-guide/README.md](../studio-guide/README.md).

## How saving works in studio

Every form edits a **draft** in the browser. Nothing is written until you click **Save** in the top bar (or press
Ctrl+S); the button shows a dot while there are unsaved changes and reads **Saved** after. Save writes
`pskit.yml`, keeps a backup in `.pskit/studio/backups/` and creates handler stubs for new functions (toast:
*Saved pskit.yml · created N handler stubs*). Undo / redo: Ctrl+Z / Ctrl+Shift+Z.

The draft is validated as you type. The problems button in the top bar shows *N errors · N warnings*; click it
for the **Problems** list, and click a problem to jump to the page that fixes it. Sidebar items show a red count
when they have problems.

## Check the machine on Setup & credentials

The **Setup & credentials** page checks the tools and credentials this machine needs to deploy, the same as
`pskit doctor`.

1. Click **Setup & credentials**. Pick **Provider**: *AWS Lambda* and your **Operating system**.
2. Read **Checks**: each row is *ready*, *missing*, *check* or *optional*. Click **How to fix** on a missing row
   for install steps.
3. No AWS credentials yet? Open **AWS credentials (aws configure)**, fill **Profile**, **Access key ID**,
   **Secret access key**, **Default region** (and **Session token** only for temporary credentials), then
   **Save profile**. It writes `~/.aws/credentials`.
4. **Environment variables** lists variables Terraform and the provider read; **Set for this session** applies
   to deploys started from this studio only.
5. **Project environment** creates `.venv` and installs `requirements.txt` (**Create .venv and install**).
6. Click **Check again** until the badge reads *ready to deploy to AWS Lambda*.

Page details: [studio-guide/setup.md](../studio-guide/setup.md).

## Set the service defaults on Overview & provider

The **Overview & provider** page holds the `service`, `provider` and `package` settings every function
inherits.

1. **Service** section: **Service name** is `orders`.
2. **Provider** section: **AWS Lambda** is selected. Clicking another card switches the provider (a dialog lists
   triggers the new provider cannot run).
3. **Defaults for every function**: **Region** `us-east-1`, **Stage** `dev`, **Runtime** `python3.12`,
   **Memory (MB)** `256`, **Timeout (s)** `15`, **Architecture** `x86_64`, **Log retention (days)** `14`.
4. **Environment variables**: click **Add variable** three times and enter:

   | Name | Value |
   |---|---|
   | `LOG_LEVEL` | `INFO` |
   | `ORDERS_DB_URL` | `${env:ORDERS_DB_URL, }` |
   | `CACHE_URL` | `${env:CACHE_URL, }` |

5. **Tags**: add `team` = `shop`.
6. **Packaging**: **Exclude globs** `tests/**`.
7. Click **Save**.

Page details: [studio-guide/overview.md](../studio-guide/overview.md).

## Remove the sample function on Functions

The HTTP API template created a sample function you don't need.

1. Click **Functions**. The table lists `hello`.
2. In its row click **Delete**, then **Delete** in *Delete function hello?*. The handler code is not deleted; you
   can remove `app/handlers.py` later on the **Code** page.

## Add the resources on the Resources page

The **Resources** page declares the queue, topic, bucket, database and cache once. Triggers and handlers refer to
them by key.

1. Click **Resources**, then **+ Add resource**. The **Add resource** drawer opens.
2. Queue: **Key** `order-jobs`, **Type** `queue`, **Mode** **Managed by pskit**. Click **Add**.
3. Topic: **+ Add resource**, **Key** `order-events`, **Type** `topic`, **Managed by pskit**, **Add**.
4. Bucket: **+ Add resource**, **Key** `receipts`, **Type** `storage`, **Managed by pskit**, **Native name**
   `orders-receipts-${opt:stage}-change-me` (S3 names are global: make it unique), **Add**.
5. Database: **+ Add resource**, **Key** `orders-db`, **Type** `database`. **Mode** switches to **External /
   existing** (pskit does not create databases). Under **Connection** click **Add connection value**: `url_env` =
   `ORDERS_DB_URL`. Leave **Bound functions** empty (every function). **Add**.
6. Cache: **Key** `cache`, **Type** `cache`, **External / existing**, **Connection** `url_env` = `CACHE_URL`.
   Under **Bound functions** tick `get-order` and `list-orders` once those functions exist (come back after the
   next sections and click the row to edit it, then **Apply**). **Add**.
7. Click **Save**.

Each row has **How to use** (libraries, `pskit.yml`, code and tests for that resource), **Test** and **Delete**.
**Guides** opens the per-cloud resource guides. Page details: [studio-guide/resources.md](../studio-guide/resources.md).

## Create the HTTP functions with the Create function wizard

The **Create function** wizard has four steps: **Basics**, **Triggers**, **Environment & permissions**,
**Review**. Create `create-order` first.

1. **Functions** → **+ Create function**.
2. **Basics**: **Function name** `create-order`; **Description** `Store a new order and queue it`; **Handler**
   `app.api.create_order` (it is derived from the name until you edit it). Leave **Runtime** on *inherit*,
   **Memory (MB)** and **Timeout (s)** empty. Click **Next: Triggers →**.
3. **Triggers**: under **Add a trigger** click **HTTP endpoint**. In the trigger form set **Route** to `POST` and
   `/orders`, **Auth** `none`, and switch **CORS** on.
4. **Next: Environment & permissions →**: nothing to add. **Next: Review →** shows **Changes to pskit.yml** as a
   diff. Leave **Create the handler stub in the code now** on.
5. Click **Create function**.

Repeat for the two read endpoints:

| Function name | Handler | HTTP endpoint route |
|---|---|---|
| `get-order` | `app.api.get_order` | `GET` `/orders/{id}` |
| `list-orders` | `app.api.list_orders` | `GET` `/orders` |

For `/orders/{id}` the form shows *Path parameters: id → event.http.path_params["id"]*. Click **Save**. Every
trigger field: [studio-guide/trigger-forms.md](../studio-guide/trigger-forms.md); the wizard:
[studio-guide/functions.md](../studio-guide/functions.md).

## Create the queue consumer and the storage processor

The queue and storage triggers point at the resources you added.

1. **+ Create function**, **Function name** `process-order`, **Handler** `app.worker.process_order`, **Timeout
   (s)** `60`. **Next: Triggers →**.
2. Click the **Queue** card. **Source**: **Project resource**, **Resource** `order-jobs`. Set **Batch size** `5`,
   **Dead letter** `order-jobs-dlq`, **Max receive** `3`. (Without a resource, **Create new queue** plus **Create
   & select** adds one to Resources on the spot.)
3. Go to **Review** and click **Create function**.
4. **+ Create function**, **Function name** `receipt-uploaded`, **Handler** `app.files.receipt_uploaded`.
5. Click the **Storage** card. **Source**: **Project resource**, **Resource** `receipts`. **Fire on**: `created`.
   **Prefix** `incoming/`, **Suffix** `.pdf`.
6. **Review** → **Create function**, then **Save**.

## Create the nightly schedule and the topic subscribers

1. **+ Create function**, `nightly-report`, **Handler** `app.reports.nightly_report`, **Memory (MB)** `512`,
   **Timeout (s)** `300`.
2. Click the **Schedule** card. **Run**: **Cron expression**, **Cron** `0 2 * * *` (the form explains it in
   words). **Timezone** `Europe/Berlin`. **Input** `{"report": "daily"}`. **Enabled**: *active*. (Choose **Every…**
   for a rate, or **At a specific time** to pick days and HH:MM without cron.)
3. **Review** → **Create function**.
4. **+ Create function**, `notify-email`, **Handler** `app.notify.email`. Click **Topic**, **Source** **Project
   resource**, **Resource** `order-events`. **Create function**.
5. **+ Create function**, `notify-analytics`, **Handler** `app.notify.analytics`. **Topic**, resource
   `order-events`, **Filter** `{"status": ["paid"]}`. **Create function**.
6. **Save**. Now edit the `cache` resource on **Resources** and tick `get-order` and `list-orders` under **Bound
   functions**, **Apply**, **Save**.

## Create the workflow step functions

The three workflow steps have no trigger. Create each with **+ Create function**, fill **Basics**, skip
**Triggers** (the page says *No triggers. The function can still be called with invoke() or from a workflow.*)
and click **Create function**:

| Function name | Handler |
|---|---|
| `reserve-stock` | `app.fulfil.reserve_stock` |
| `charge-payment` | `app.fulfil.charge_payment` |
| `ship-order` | `app.fulfil.ship_order` |

Click **Save**. The **Functions** table now lists 11 functions; each row has **Test**, **Code**, **Duplicate** and
**Delete**.

## Build the fulfil-order workflow on the Workflows page

The **Workflows** page draws the state machine and edits one state at a time. On AWS it compiles to Step
Functions.

1. **Workflows** → **+ Create workflow**. In **New workflow**, **Name** `fulfil-order`, **Create**. The editor
   opens with one `Start` state.
2. Open **Settings**: **Description** `Reserve stock, charge the card, ship`, **Engine** `auto`, **Timeout (s)**
   `900`.
3. Add states from the palette above the diagram: click **task** three times, **choice**, **wait** and **fail**
   once each. Click a state in the diagram to edit it on the right.
4. For each task: **State name** (type it, then **Rename**) and **Function**:
   `Reserve` → `reserve-stock`, `Charge` → `charge-payment`, `Ship` → `ship-order`. Rename the others
   `CheckAmount`, `ManualReview`, `Cancelled`. Select `Start` and delete it.
5. **Starts at**: `Reserve`.
6. `Reserve`: **Then** **Go to** `CheckAmount`. Open **Catch (0)**, **+ catch rule**: errors `OutOfStock`, next
   `Cancelled`, result path `$.error`.
7. `CheckAmount` (choice): **+ Add rule**, kind **if**, `$.total` `gt` `1000` → `ManualReview`. **Otherwise**
   `Charge`.
8. `ManualReview` (wait): **Wait** **Fixed seconds**, **Seconds** `60`, **Then** **Go to** `Charge`.
9. `Charge`: **Then** **Go to** `Ship`. **Data paths** → **Result path** `$.payment`. **Retry (0)** → **+ retry
   rule**: errors `PaymentGatewayTimeout`, 3 attempts, interval 2, backoff 2. **Catch** → `PaymentDeclined` →
   `Cancelled`, result path `$.error`.
10. `Ship`: **Then** **End**. `Cancelled` (fail): **Error** `OrderCancelled`, **Cause** `Out of stock or payment
    declined`.
11. **Save**. More: [studio-guide/workflows.md](../studio-guide/workflows.md).

## Write the handler code on the Code page

The **Code** page edits project files in the browser (**Built-in editor**), or in a full VS Code in Docker
(**Full VS Code**).

1. Click **Code**. The file tree shows `app/` with the stub files Save created (`api.py`, `worker.py`, ...).
2. Click **+** (*New file*), type `app/store.py`, **Create**. Paste the `store.py` code from
   [end-to-end-cli.md](end-to-end-cli.md#write-the-store-helper-for-the-database-and-cache). Click **Save (Ctrl+S)**.
3. Do the same for `app/messaging.py`.
4. Open each stub (`app/api.py`, `app/worker.py`, `app/files.py`, `app/reports.py`, `app/notify.py`,
   `app/fulfil.py`) and replace it with the code from the CLI guide. **Save (Ctrl+S)** each.
5. Open `requirements.txt` and set it to `boto3`, `psycopg[binary]`, `redis` (one per line). **Save**.
6. Delete the old `app/handlers.py` or leave it; nothing refers to it.

Back on **Setup & credentials** → **Project environment**, click **Install requirements** so local runs can
import them. Page details: [studio-guide/code.md](../studio-guide/code.md).

## Add the stage override and hooks on the YAML page

Studio has no form for `stages:` and `hooks:`; the **YAML** page edits the raw file.

1. Click **YAML**. **Preview** shows what Save writes; **Diff vs disk** compares with the file.
2. Choose **Edit raw YAML**, add at the end:

   ```yaml
   stages:
     prod:
       provider:
         memory: 512
         environment:
           LOG_LEVEL: WARNING
       functions:
         process-order:
           concurrency: 10
   hooks:
     before_deploy: ["pytest -q"]
   ```

3. Click **Apply to draft**; the forms update. Click **Save**. Comments in `pskit.yml` are not preserved.
   Page details: [studio-guide/yaml.md](../studio-guide/yaml.md).

## Test the functions locally on the Test page

The **Test functions** page runs a handler on this machine with a sample event, or sends a real event once
deployed.

1. Click **Test** and pick `create-order` in the list.
2. **1. Choose the event**: the `POST /orders` trigger.
3. **2. Edit the event**: **Request** `/orders`, **Payload (JSON)**
   `{"items": [{"sku": "A1", "price": 5, "qty": 2}]}`. **Saved events** keeps it for later.
4. **3. Run it**: click **▶ Run locally**. The output shows status 201 and the order.
5. Try `get-order` with **Request** `/orders/abc` (404), and `process-order` with `{"order_id": "abc"}`.
6. Run the workflow locally: **Deploy** → **Run a workflow locally**, **Workflow** `fulfil-order`, **Input
   (JSON)** `{"id": "o1", "total": 20, "items": [{"sku": "A1", "qty": 1}]}`, **Run**. **Invoke a function
   locally** on the same page does the same as `pskit invoke`.

**How to test this** on each function lists the studio, terminal and console steps. Page details:
[studio-guide/test.md](../studio-guide/test.md).

## Deploy the dev stage on the Deploy page

The **Deploy** page runs pskit in the project folder as the provider and stage from the top bar.

1. Top bar: **validate & deploy as** *AWS Lambda*, **stage** `dev`.
2. Set the database and cache URLs for this session: **Setup & credentials** → **Environment variables**, or
   start studio from a shell where `ORDERS_DB_URL` and `CACHE_URL` are exported.
3. Click **Deploy**. Click the **Validate** card, then **Plan** to see what Terraform will create.
4. Click the **Deploy** card and confirm **Deploy** in *Deploy to aws/dev?*. With unsaved changes you are asked
   **Save and run** first. The output streams below; **Recent jobs** keeps the history.
5. Click **Info** for the endpoint, function ids and console links.

Page details: [studio-guide/deploy.md](../studio-guide/deploy.md).

## Send real events and read logs

1. **Test** → `create-order` → **☁ Send to aws / dev** sends the request to the deployed API. Switch on **Show the
   function's logs** to watch them next to the result.
2. `process-order` → **☁ Send to aws / dev** sends a real SQS message; `nightly-report` invokes it now.
3. **Resources** → **Test** on `order-events` publishes a message; both topic subscribers run.
4. Click **Logs**: live logs of every function of `aws` / `dev`. Filter with **Search messages…**, **Level**,
   **Function** (*All functions*), **Source**; **❚❚ Pause** / **▶ Resume**, **Clear**, **Console ↗** opens
   CloudWatch. **Stored logs** lists and deletes log streams.

Workflow executions after deploy: `pskit workflow start fulfil-order -i ...` or `pskit dashboard --serve --open`
([deployment/workflows.md](../deployment/workflows.md)). Logs page: [studio-guide/logs.md](../studio-guide/logs.md).

## Deploy the prod stage and remove a stage

1. Top bar **stage**: type `prod`. Validation now uses the `stages.prod` overrides.
2. **Deploy** → **Plan**, then **Deploy**. *Deploy to aws/prod?* says *This is a production stage.*: type
   `aws/prod` and click **Deploy**.
3. To remove a stage: set the stage in the top bar, choose the switch under the action cards (**Remove keeps
   buckets, queues and topics (and their data)** or, switched on, **Remove also deletes buckets, queues and
   topics**), click **Remove**, type `aws/dev` (provider/stage) in *Remove aws/dev?* and click **Remove**.
   External resources are never deleted.

## Ask Hana to do the same steps

Hana, the AI assistant, can do many of the steps above from a chat message. Click **Ask Hana** at the bottom
right (or Ctrl+I). The first time, pick where her model runs (Docker on this machine is recommended).

1. Keep **Ask first** (top of the panel): Hana shows a **Plan** card and changes nothing until you click
   **Approve**. **Auto-approve** runs plans at once.
2. Examples:

   | You type | What happens |
   |---|---|
   | "explain my project" | a summary of functions, triggers and resources |
   | "create get-order list-orders functions in app/api" | a **Create functions** card |
   | "add a queue named order-jobs" | a plan that adds the resource |
   | "create a workflow fulfil-order with reserve-stock, charge-payment, ship-order" | a **Create workflow** card |
   | "how do I add a cron schedule at 2am Berlin time?" | steps with links to the docs |
   | "execute pskit validate" | a **Run** card; the command runs after your click |

3. Hana validates after every change and backs up `pskit.yml` first. Deploy and remove stay on the **Deploy**
   page. Everything she can and can't do: [assistant.md](../assistant.md).

## See also

- [Learning path](README.md) and [concepts](concepts.md)
- [The same app from the terminal](end-to-end-cli.md)
- [The same app on your own servers](end-to-end-onprem-cluster.md)
- [Studio guide](../studio-guide/README.md)
- [Studio reference](../studio.md)
- [Hana](../assistant.md)
