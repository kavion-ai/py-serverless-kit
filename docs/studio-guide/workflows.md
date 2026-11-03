# Workflows page in studio

Search terms: workflows page, workflow builder, state machine, step functions, visual editor, task, choice, wait, pass, parallel, map, succeed, fail, retry, catch, engine, native, embedded, orchestrator

The **Workflows** page is a visual state-machine builder. Sidebar: **Workflows** (⇉); the number counts workflows. It
edits `workflows:` in `pskit.yml`. How workflows run on each cloud, and how to start them, is in
[Build and run workflows](../deployment/workflows.md).

## Read the workflow list in studio

The studio workflow list shows one card per workflow: its name, description (or "N states, starts at X"), up to 8
state chips with their type icons, the engine badge and the **Deploy** dropdown (**● Enabled**, **◐ Disabled on
<Provider>**, **○ Disabled everywhere**, the same as for functions). **Delete** asks **Delete workflow <name>?**.

The page subtitle says how workflows run on the current provider:

- AWS and GCP: they compile to the native engine (Step Functions / Cloud Workflows) unless you pick embedded.
- Azure: they run on the embedded engine by default; pick engine native to compile them to Azure Logic Apps.
- Other providers: they run on pskit's embedded engine inside a generated `<workflow>-orchestrator` function.

## Create a workflow in studio

The studio **+ Create workflow** button starts a new workflow with one state.

1. Open **Workflows** and click **+ Create workflow**.
2. In **New workflow**, type the **Name** (letters, digits, `-` and `_`; start with a letter). Default `my-workflow`.
3. Click **Create**. Studio writes `start_at: Start` and a `Start` pass state that ends, and opens the editor.
4. Add states (next sections), then press **Save**.

The same in `pskit.yml`:

```yaml
workflows:
  order:
    start_at: Validate
    states:
      Validate: {type: task, function: validate-order, next: Charge}
      Charge: {type: task, function: charge, end: true}
```

## Add and connect states in the workflow builder

The studio workflow editor has a palette, a diagram and an inspector.

1. The palette buttons add a state: **task** (call a function), **choice** (branch on the data), **wait** (pause for N
   seconds), **pass** (pass data through or inject a value), **parallel** (run branches at the same time), **map**
   (run steps for every item in a list), **succeed** and **fail**.
2. A new state is chained after the selected state when that state simply ends (task, pass, wait, parallel, map).
3. **Starts at** picks the first state.
4. The diagram is laid out automatically, with edges for next, choice rules, the default and catch. States with
   problems are marked. Click a state (or press Enter on it) to open it in the inspector.
5. In the inspector, **Then** chooses **Go to** a state or **End** (for task, pass, wait, parallel and map).

## Edit a state in the workflow inspector

The studio workflow inspector edits the selected state. Every state has **State name** (with **Rename**; transitions
into it are updated), **Comment** and **Delete** (asks **Delete state <name>?**; transitions into it are removed and
those states end instead).

| State type | Fields |
|---|---|
| **task** | **Function** (required; pick one, or **+ New** to open the Create function wizard), **Timeout (s)** |
| **wait** | **Wait**: **Fixed seconds** (**Seconds**) or **From the data** (**Seconds path**, e.g. `$.delay`) |
| **pass** | **Result**: JSON written at the result path; empty passes the input through |
| **fail** | **Error** (e.g. `Order.Rejected`) and **Cause** |
| **map** | **Items path** (e.g. `$.items`), **Max concurrency** (0 / empty = unlimited), **Steps per item**: **Edit iterator (N states) →** |
| **parallel** | **Branches**: **Branch N · M states →** opens a branch; ✕ removes it; **+ Add branch** |
| **choice** | **Rules** and **Otherwise** (next section) |

**Data paths** (task, pass, wait, parallel, map, choice) has **Input path** (e.g. `$.order`) and **Result path**
(`$` replaces the data; empty keeps the default; `null` discards the result).

Parallel branches and map iterators open as nested workflows. A breadcrumb (for example `order › Fan › branch 1`
or `order › Loop › each item`) leads back.

## Write choice rules in the workflow builder

The choice state's **Rules** are checked top to bottom; the first match wins.

1. Click **+ Add rule**.
2. Pick the rule kind: **if**, **if not**, **all of** or **any of**. **all of** / **any of** hold several conditions
   (**+ condition**, ✕ to remove one).
3. Each condition has a variable (e.g. `$.status`), an operator (`equals`, `not_equals`, `gt`, `gte`, `lt`, `lte`,
   `in`, `contains`, `matches`, `is_null`, `is_present`), a value type (`string`, `number`, `boolean`, `null`,
   `json`) and the value. `matches` takes a glob such as `order-*`.
4. **then go to** picks the next state ("pick a state" until set). ↑ moves a rule up; ✕ removes it.
5. **Otherwise** is the default state. Without one, a run that matches nothing fails with `States.NoChoiceMatched`.

## Add retry and catch to a workflow state

Task, parallel and map states have **Retry (N)** and **Catch (N)** blocks.

- **+ retry rule**: **on errors** (comma separated, `*` = all errors, or e.g. `TimeoutError, Payment.Declined`),
  **attempts** (default 3), **interval s** (1), **backoff ×** (2) and **max delay s**.
- **+ catch rule**: **on errors**, **go to** a state, and **error at** (where the error is put, default `$.error`).

## Set the workflow engine and timeout in studio

The **Settings** section at the top of the editor (closed by default) has **Description**, **Engine** and
**Timeout (s)**.

- **Engine**: **auto**, **native** or **embedded**. auto / native use the provider's workflow service; embedded uses a
  generated orchestrator function. **native** is disabled where pskit has no native engine for the provider.
- **Timeout (s)**: whole-run limit; the run ends as `TIMED_OUT` when exceeded.

## Run a workflow from studio or the terminal

Studio runs a workflow locally from the [Deploy page](deploy.md#invoke-a-function-or-run-a-workflow-locally): **Run a
workflow locally**, pick the **Workflow**, type the **Input (JSON)** and click **Run**. It runs
`pskit workflow run <name> --history`.

```bash
pskit workflow run order -i '{"id": 1}' --history          # locally
pskit workflow start order -i @input.json --wait           # deployed
pskit workflow executions order --status FAILED
pskit workflow show order --format asl
```

## See also

- [Build and run workflows](../deployment/workflows.md)
- [Workflow reference](../workflows.md) and [workflow executions](../workflow-executions.md)
- [Functions page](functions.md)
- [Deploy page](deploy.md)
