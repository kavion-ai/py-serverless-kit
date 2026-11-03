# Studio: Test a resource

How to open: Resources > Test

The Test a resource section is the same tester. The section title is "Test a resource" and the hint is "<provider> / <stage>" from the top bar.

What it is for: Send a real message or object to a queue, bucket, or topic, and show how bound functions read the resource. docs/studio.md says this works for managed resources after deploy and for external ones right away. Database, cache, and custom resources show the PSKIT_RESOURCE_* variables and a Python or Node.js snippet.

What you see: If the saved pskit.yml has no resources, the text says to add one and save, and that triggers which create their own queue or bucket can be tested on the Test page. The Resource select shows "<key> · <type> <name>" plus "(external)" or "(managed)". Used by lists functions bound to it. The help says they get its PSKIT_RESOURCE_* variables. Test connection is a button (Checking… while it runs). Its help says it is checked from `item.check.where` and shows a terminal command. A sendable resource has Object for storage, or Message otherwise, Reset to sample, and a primary button whose label is `item.action`. How to test is In the studio, Terminal, or "<provider> console" (the console tab is disabled when there are no console steps). Use it in a handler has a Language control and Python handler and Node.js handler fields.

What you can do: The send button asks "<action> to <name>?" with confirm label Send. The body says this is real: an object is uploaded or a message is delivered, and names bound functions that have a trigger. Confirm starts the studio job resource-send. In jobs.py that command is `pskit resources send`. The button is disabled when `item.remote.supported` is false, and the reason is shown. The in-studio steps say external resources work without deploying and managed resources exist after Deploy. The terminal tab includes the lines the UI builds:

```
pskit resources send --list
pskit logs -f
```

Tips and limits: The confirm is the studio's confirm dialog, not a typed production confirmation. Sending uses the top-bar provider and stage. Unsaved resources are not in this list until you save. The Test page is a different screen: it invokes a function, while this section sends to the resource.

Sources: `dashboard-ui/src/studio/components/ResourceTester.tsx`, `src/py_serverless_kit/studio/jobs.py`, `docs/studio.md#project-environment-trigger-resources-and-remove`
