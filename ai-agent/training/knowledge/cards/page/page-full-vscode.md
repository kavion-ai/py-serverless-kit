# Studio: Full VS Code

How to open: Code > Full VS Code

The segmented control is labeled Editor. The other choice is Built-in editor.

What it is for: Run code-server in Docker on this project and embed it. docs/studio.md says the project is mounted at /home/coder/project, the container is published on 127.0.0.1 only, and Stop removes the container while files stay in the project folder. The default image in that doc's option table is codercom/code-server:4.96.4, also set with `pskit studio --vscode-image` or PSKIT_STUDIO_VSCODE_IMAGE.

What you see: Until `api.vscode` returns, the label is "Checking Docker…". If Docker is missing, the heading is "Docker is needed for full VS Code" and the steps say to install Docker Desktop or Docker Engine, come back and press "Pull & start", and, if studio itself is in a container, mount the Docker socket and set PSKIT_STUDIO_HOST_ROOT to the project path on the host. Check again reloads the status. The built-in editor works without Docker, which that panel states. When Docker is available, badges show the Docker version, running or stopped, and "image not pulled yet" when the image is absent. Fields are image, Python (option "image default", versions from the status or 3.13, 3.12, 3.11, 3.10, 3.9), and Node.js (option "none", or 24, 22, 20, 18 as "<version>.x"). The Python title says CPython is installed with uv python install. The Node.js title says the official Node.js build is installed in the editor container.

What you can do: The start button is "Pull & start" when the image is not present, otherwise Start. While the job runs it says Starting…. Open in new tab is shown when a URL is available. Restart with these runtimes is shown when the container is running and the Python or Node selection differs. Its title says the container is recreated and your files are kept. Stop calls `api.vscodeStop` and toasts "VS Code stopped". The running note says the container only listens on 127.0.0.1, and files saved in VS Code are the project files.

```
pskit studio --open
```

Tips and limits: docs/studio.md says the editor runs with `--auth none` because it is reachable only from this machine, and that on Linux and macOS it runs as your user so new files are not owned by root. Changing the image field is disabled while the container is running.

Sources: `dashboard-ui/src/studio/views/Code.tsx`, `docs/studio.md#full-vs-code-code-server-in-docker`
