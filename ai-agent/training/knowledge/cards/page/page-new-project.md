# Studio: New project

How to open: This screen replaces the studio shell when the folder has no pskit.yml. It is not in the left navigation. `App.tsx` renders `NewProject` in that case. docs/studio.md says the page appears when the folder has no pskit.yml.

What it is for: Scaffold a project. The heading is "Create a pskit project". The intro says there is no pskit.yml in this folder yet, and that you pick a name, a cloud and a starting point.

What you see:
- Service name. Help text: 2–32 characters, lowercase letters, digits and dashes, used to name every cloud resource. The error text says the name must start with a letter. The field lowercases what you type. The initial value in the component is my-service.
- Provider, shown as provider cards from `meta.providers`.
- Language: Python, JavaScript, TypeScript. JavaScript and TypeScript are disabled when the selected provider has no Node runtimes. The disabled title is "This provider runs Python only in pskit". Help text says Python handlers live in app/*.py, JavaScript in src/*.js, and TypeScript in src/*.ts compiled with tsc when packaging.
- Template: HTTP API ("One HTTP function. The smallest start."), Events ("HTTP plus schedule, queue, storage and topic examples."), Workflow ("HTTP plus a small step-function workflow."), Everything ("All of the above.").

What you can do: Create project calls `api.init`. While that runs the label is Creating…. The studio endpoint is POST project/init, handled by `init_project` in `src/py_serverless_kit/studio/project.py`. That function checks the service name with `[a-z][a-z0-9-]{1,31}`, checks the provider is one of `PROVIDERS`, and checks the template is http, events, workflow or full. It then calls `render` from `cli/templates.py`. `pskit init` calls that same `render`. Studio sets the Python runtime string to python3.12. For JavaScript or TypeScript it uses the provider's `default_runtime_for("node")`. If a pskit.yml already exists, the API returns 409 and the UI asks "Files already exist" with confirm label Overwrite, then calls init again with force.

Tips and limits: Overwrite is only offered after that 409. The screen does not show the top bar. After a project exists, the left navigation is Overview & provider, Setup & credentials, Functions, Workflows, Resources, Scaling cluster, Load balancers, Network map, Code, Test, Deploy, Logs, YAML.

Sources: `dashboard-ui/src/studio/views/NewProject.tsx`, `dashboard-ui/src/studio/App.tsx`, `src/py_serverless_kit/studio/project.py`, `src/py_serverless_kit/cli/main.py`, `docs/studio.md#what-you-can-do`
