# Code page in studio

Search terms: code editor, edit handler, file tree, new file, VS Code, code-server, full VS Code, Docker editor, Python version, Node.js version, Ctrl+S, open in new tab, PSKIT_STUDIO_HOST_ROOT

The **Code** page edits handler code in the browser. Sidebar: **Code** ({}). The switch at the top right picks the
**Built-in editor** (no Docker needed) or **Full VS Code** (code-server in Docker, with your project mounted). Both
edit the real project files.

## Edit handler code in the built-in editor

The studio built-in editor is a file tree and a VS Code-style editor (CodeMirror: Python, YAML, JSON and JavaScript
highlighting, search, tabs).

1. Open **Code**, or click **Code** on a function row or **Open code** in the function wizard (it opens the handler
   file).
2. **Find file…** filters the tree. **↻** reloads it.
3. Click a file to open it in a tab. A dot on a tab means unsaved changes; **✕** closes it (unsaved: **Close
   <path>?** with **Discard changes**).
4. Edit and press **Ctrl+S** (Cmd+S). The toast says "Saved <path>".
5. If another editor saved the file after you opened it, studio asks **<path> changed on disk** with **Overwrite** or
   **Reload theirs**.

Create a file with **+**: type a relative path (default `app/`, e.g. `app/new_module.py`) and click **Create**.

Limits: the editor only reaches files inside the project. It never shows `.pskit/`, `.git/`, `.venv/`, `venv/`,
`node_modules/`, `__pycache__` and tool caches, and refuses binary files and files over 1 MiB.

## Open the project in full VS Code from studio

**Full VS Code** runs [code-server](https://github.com/coder/code-server) in Docker with the project mounted at
`/home/coder/project`, and embeds it in the page.

1. Open **Code** and switch to **Full VS Code**.
2. If Docker is missing or not running, studio shows **Docker is needed for full VS Code** with the steps: install
   Docker Desktop (Windows, macOS) or Docker Engine (Linux), check `docker version`, come back and press **Pull &
   start** (the image is about 600 MB, downloaded once). **Check again** re-checks.
3. The bar shows the Docker version, **running** / **stopped**, and **image not pulled yet** when needed.
4. Optional: change **image** (default from `--vscode-image`), **Python** (image default, or 3.9 to 3.13) and
   **Node.js** (none, or 18.x to 24.x). The first start with a combination builds an image
   `pskit-code-server:<tag>-py<X>-node<Y>` (CPython from `uv python install`, Node.js from nodejs.org with its
   SHA-256 checked, and the Python extension); its Dockerfile is kept in `.pskit/studio/vscode/`.
5. Click **Pull & start** (or **Start**). The log streams while it starts.
6. VS Code opens in the page. **Open in new tab ↗** opens it alone. **Stop** removes the container; your files stay.
7. Changing the runtimes while it runs offers **Restart with these runtimes** (the container is replaced, files kept).

The container listens on 127.0.0.1 only and runs with `--auth none`. On Linux and macOS it runs as your user, so new
files are not owned by root. A container that is already running is reused.

Running studio itself in a container: mount the Docker socket and set `PSKIT_STUDIO_HOST_ROOT` to the project's path
on the host:

```bash
docker run --rm -p 127.0.0.1:8770:8770 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$PWD":/work -w /work \
  -e PSKIT_STUDIO_HOST_ROOT="$PWD" \
  python:3.12-slim sh -c "pip install py-serverless-kit && apt-get update && apt-get install -y docker.io && pskit studio --host 0.0.0.0"
```

Start studio with another code-server image:

```bash
pskit studio --vscode-image codercom/code-server:4.96.4
```

## See also

- [Functions page](functions.md)
- [Handlers](../handlers.md) and [Node.js handlers](../nodejs.md)
- [Create functions](../functions/create.md)
- [Studio guide](README.md)
