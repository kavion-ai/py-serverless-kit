# Studio: Workflows

How to open: Left navigation label Workflows. Opening a name in the list shows the editor for that workflow. A missing name shows the header "Workflow not found".

What it is for: docs/studio.md calls this a visual step-function builder: an auto-laid-out diagram (next, choice, default and catch edges) and a palette. The inspector edits each state. Engine (auto / native / embedded) and timeout are on the workflow.

What you see: The list has a modal titled New workflow, with Name, Cancel and Create. Each row has Delete. The confirm title is "Delete workflow <name>?" and the confirm label is Delete. After confirm, the workflow key is removed from the draft and a toast says it is not saved yet. The editor palette is aria-label "Add state". The state types in `TYPE_INFO` are task ("Call a function"), choice ("Branch on the data"), wait ("Pause for N seconds"), pass ("Pass data through / inject a value"), parallel ("Run branches at the same time"), map ("Run steps for every item in a list"), succeed ("Stop successfully") and fail ("Stop with an error"). Section Settings contains Engine and Timeout (s). The timeout help says "Whole-run limit; TIMED_OUT when exceeded." An empty diagram says "Add a state from the palette."

What you can do: Add a state from the palette. The editor text says a new state is chained after the selected one. Click a state to edit it. Task states pick a function. Choice rules use the operators from `meta.workflow.choice_operators`, or the fallback list equals, not_equals, gt, gte, lt, lte, in, contains, matches, is_null, is_present. docs/studio.md says parallel branches and map iterators open as nested workflows, and that retry and catch are edited in the inspector.

Tips and limits: Delete updates the in-memory draft only. The top-bar Save writes pskit.yml. Engine values auto, native and embedded are the ones named in docs/studio.md. The diagram layout code lives in `dashboard-ui/src/studio/views/flow.ts`, imported by this view.

Sources: `dashboard-ui/src/studio/views/Workflows.tsx`, `docs/studio.md#what-you-can-do`
