# Studio: Code

How to open: Left navigation label Code. A Code action on a function row opens this page on that file.

What it is for: The subtitle says "Edit handler code here, or open the whole project in VS Code (code-server in Docker)." docs/studio.md describes a file tree and a CodeMirror editor (Python, YAML, JSON highlighting, search, tabs, Ctrl+S), or Full VS Code.

What you see: A segmented control labeled Editor with "Built-in editor" and "Full VS Code". The built-in editor has a search field whose placeholder is "Find file…" and a button titled "New file". The Full VS Code panel includes the steps that tell you to press "Pull & start", and the buttons Open in new tab and Stop.

What you can do: Edit and save files inside the project. docs/studio.md#security says the file editor only reaches files inside the project. It never touches `.pskit/`, `.git/`, `.venv/`, `node_modules/` or `__pycache__`, and it refuses binary files or files over 1 MiB. Full VS Code checks for the Docker CLI and a running daemon, then Pull & start pulls the image if needed and starts a container. The default image in the `pskit studio` option table is `codercom/code-server:4.96.4` (`--vscode-image`, also the environment variable `PSKIT_STUDIO_VSCODE_IMAGE`). The container name pattern in the doc is `pskit-studio-<id>`, the project is mounted at `/home/coder/project`, and the publish address is 127.0.0.1 only. Stop removes the container. Files stay in the project folder.

Tips and limits: The top-bar Ctrl+S handler in App.tsx does not run when the current view is Code, so the editor handles save itself. docs/studio.md says the first start with a Python and Node selection builds an image tagged from those versions, and later starts reuse it. Changing runtimes while it is running offers Restart with these runtimes. The doc says it runs with `--auth none` because it is reachable only from this machine.

Sources: `dashboard-ui/src/studio/views/Code.tsx`, `docs/studio.md#what-you-can-do`, `docs/studio.md#full-vs-code-code-server-in-docker`, `docs/studio.md#security`
