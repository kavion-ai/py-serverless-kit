# Functions on several servers (on premises)

By default every function of a project runs in one host: on one machine, or on every server of a cluster. **Placement** splits them: each group of functions runs on its own server (or cluster), with only its own code and dependencies, and the groups work together as one project. Per group: one of `server`, `cluster` or `local: true` (the default group may leave it out and use `options.deploy` / `--server` as before), `functions`, and optionally `port` (needed when two groups share a server) and `advertise` (the URL the other groups call, when the server's own address is not reachable). The studio's **Deploy** page has the same editor ("Where functions run"), and each function shows where it runs.
## Each function is its own sub-project

Create functions in their own folder with their own dependencies: The studio does this for new functions ("Own folder with its own requirements.txt"). A function's sub-project is the nearest folder above its handler with a `requirements.txt` (Python) or `package.json` (Node.js). * Every cloud: the sub-projects' requirements are added to the bundle, so the code runs unchanged anywhere. * On premises with placement: **each server installs only the requirements of its functions**, and the folders of functions placed elsewhere are left out of its bundle. Two functions on one server that pin conflicting versions fail the deploy with a clear message: place them on different servers. * Node.js sub-projects get their own `node_modules` in their folder, so each function resolves its own versions.
### Requirements: global plus per function

Each server installs: * the project's `requirements.txt` (global: what every function needs), and * the `requirements.txt` of each of **its** functions' folders (`functions/<name>/requirements.txt`), never those of functions placed elsewhere.
### Functions that share a code file

Each server's copy of a shared code file holds only the handlers of its own functions: pskit removes the others (and the imports only they used) from that group's bundle; your source is not changed. Module-level helpers stay. `pskit_host.json` on the server lists what was removed (`stripped`). Moving them to their own folders is still cleaner, and gives each its own requirements: Functions whose handlers sit side by side in one file (`app/handlers.py` with `hello`, `get_item`, `create_item`, as `pskit init` makes them) are shared code. Validation warns when they are in different groups. Split them: The function, the module-level helpers and imports it uses (relative imports made absolute) move to `functions/<name>/handler.py`. Its `requirements.txt` gets the lines of the project's `requirements.txt` that its imports name, and its handler in `pskit.yml` is updated.

```text
provider:
  name: onprem
  options:
    host: 0.0.0.0
    placement:
      default: api                      # functions not listed here, and every workflow, run in this group
      groups:
        api:   {server: app1}           # a saved server
        gpu:   {server: gpu1, functions: [resize, ocr]}
        batch: {cluster: prod, functions: [report]}             # a scaling cluster ({name: prod, replicas: 3})
        local: {local: true, functions: [dev-tool], port: 8081} # this machine
```
