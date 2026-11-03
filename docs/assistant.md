# Hana, the studio's AI assistant

Hana is the AI assistant built into `pskit studio`. She answers questions about pskit, gives how-to steps for
studio, the terminal and code, and works on your project: she reads it, proposes a plan, edits `pskit.yml` and
handler code, and checks the result with `validate` and a local invoke.

Hana is a small model (1.5B parameters, fine-tuned from Qwen2.5-1.5B-Instruct, Apache-2.0) created and developed by
Asif Khan (https://www.linkedin.com/in/asif-khan-31b7a8187/). She runs on your machine or your server, on a CPU, and
nothing you type is sent to a cloud.

- Model: [ak2311581/hana-pskit-1.5b](https://huggingface.co/ak2311581/hana-pskit-1.5b) and its GGUF files
  [ak2311581/hana-pskit-1.5b-GGUF](https://huggingface.co/ak2311581/hana-pskit-1.5b-GGUF)
- Docker image: `ak2311581/hana-pskit:1.0` (llama.cpp server, OpenAI-compatible API)

## Open the chat

Click Hana's round avatar at the bottom right of every studio page, or press **Ctrl+I** (**Cmd+I** on macOS). The
chat window stays open while you move between pages; Hana is told which page you are on, the provider and the
stage selected in the top bar.

In the window:

- **⤢** switches the size: normal, large, full screen (remembered).
- **Explain**: the current page, your project, the validation problems, or Hana's last answer in simpler steps.
- **⋯**: **New chat**, **Clear this chat**, **Delete all chats**.
- **Ask first / Auto-approve**: see below.

## Who answers: the model first, then studio

Every message goes to Hana's model first; it searches the docs, reads the project and decides what to do. Then
studio looks at the same message:

- when studio can **do** what you asked (add servers, create services, clusters, load balancers, functions, resources,
  a deploy ...), its cards are added under the model's answer (**Studio can do this directly**); nothing runs until
  you click;
- when the model had no real answer ("I can't ...") or failed, studio's answer is added (**From studio:**).

**⋯** > **Studio actions answer first** switches the order: studio answers right away when it recognises the
request, and the model answers everything else. Studio's answers come from your project and the CLI, so they
don't invent flags or keys; the model can.

When studio has a card that changes `pskit.yml` or code (create functions, move them into their own apps, add a
resource, write missing code, a workflow, a remove), **studio answers first** and the model is not asked, so the
two never make two different changes. A short answer to a question studio just asked ("Which function should I
remove?" → "step01, step02") is read together with that question. When the model says it changed something
("Done", "I added ...") but no file was written in that answer, studio adds a note saying nothing changed.

## Docs first: studio searches the docs before Hana answers

Before Hana's model answers a message, studio searches the pskit docs with that message and hands the model the 3
best matching sections (a `search_docs` step you see in the chat). The system message tells Hana to answer from those
excerpts, cite them as `[docs/path.md#section]`, search again with other words when they don't cover the question, and
say she did not find it in the docs instead of guessing. A short reply such as "yes" or "do it" is searched together
with your previous message. Studio skips the search when it already ran a command for you in that turn.

The search covers the knowledge cards Hana was trained on plus every section of every page under `docs/` (the
guides, studio guide, functions, triggers, deployment, on-prem and provider pages), so new docs are found before the
model is retrained. Maintainers: the docs index is `src/py_serverless_kit/studio/hana/docs.jsonl.gz`; rebuild it
with `python scripts/build_hana_docs_index.py` after changing `docs/` (`--check` only checks, and a test fails when
it is out of date).

## Creating functions: own app or an existing one, and names already taken

"create step01 step02 step03 functions" opens a **Create functions** card, and Hana asks what you didn't say:

- **Where the code goes**: each function as **its own app** (`functions/step01/handler.py` with its own
  `requirements.txt`, see [placement](placement.md#each-function-is-its-own-sub-project)), or **added to an existing
  app** (pick the module, e.g. `app/handlers.py`). Say it in the message to skip the question: "... as separate
  apps", "... in app/handlers".
- **Names already in pskit.yml**: for each one, **update it** (its code stays; the trigger is applied and, with own
  app, its code moves into its folder), **create it under another name** (`step01-2`), or **skip** it. Nothing is
  overwritten unless you pick update.

**Create** stays disabled until both are answered. You can also answer in the chat ("separate apps", "rename").

Functions that already share a file move into their own apps with "make step01, step02 and step03 separate apps"
or "remove app/steps and create a different app for each function": a **Move into separate apps** card lists each
move (`app/steps.py` → `functions/step01/handler.py`, with the requirements its imports need). The shared file is
deleted when no function and no other file uses it.

The same goes for other names: a resource you name that already exists ("add a queue named jobs") gets **Replace
it** or **Add it as jobs-2** on its card. A service, cluster or load balancer name that is taken ("create a cluster
named web") gets a free name on the card and a note saying how to change the existing one instead; studio never
replaces a running service, cluster or load balancer.

## Removing a function, workflow or resource

"remove the hello function" opens a **Remove function hello** card that lists everything that goes: the
`functions.hello` entry in `pskit.yml` (backed up first) and its handler: only `hello()` is cut from its file when
other code lives there, the whole file is deleted when nothing else is in it, and the code stays when another
function uses the same handler. A function a workflow still runs is not removed: Hana names the workflow to change
first. Workflows and resources are removed the same way (a resource that functions still mention gets a warning).
Asking for a name that doesn't exist (or no longer exists) gets the list of what does.

## Servers and on-prem services: cards you confirm

Some things live in studio's own settings rather than in `pskit.yml`, and studio does them for Hana:

- **Add a server**: ask ("add a server for me"), or paste what you have: an `ssh -i key.pem user@host` command,
  Terraform outputs such as `public_ip = "..."` and `ssh_user = "..."`, or the path of the `.pem` file. An **Add
  server** card opens with the host, user, port and key file filled in. Check them and click **Save & test**:
  studio saves the server (as on the Servers page) and logs in once over SSH to check it. The card has every field
  of the Servers form, and what you write fills them: "ssh port 2222", "with sudo", "home /srv/pskit", "data
  /data/pskit", "bind 10.0.0.5", "description: lab box", "log in with a password" or "ssh agent". A password is
  typed in the card only: one written in the chat is hidden (`password is <hidden>`) before it is saved or sent to
  the model.
- **Create an on-prem service**: "create redis on app-1 as cache", "create a postgres database" (on-premises). A
  **Create on-prem service** card opens with the service, its name, its role and the server. **Create** runs the
  same job as Resources > On-prem services and shows its log.
- **List**: "how many servers are there?", "what services do I have?" answer from the project's real settings.
- **Change a saved server**: "for this server add the home path and data path", "set home to /opt/pskit and data
  to /data/pskit for app-1". An **Update server** card opens with the saved values and the fields you named
  highlighted. Pasting a machine that is already saved updates it instead of adding a copy.
- **Remove**: "remove server-1" opens a **Remove server** card (studio only forgets the server; nothing on the
  machine changes, and it refuses while a cluster uses it). "remove redis-1" opens **Remove service**; deleting its
  data as well needs the service name typed in.
- **What can you do?** gets the list of what Hana can and can't do.

"This server" / "it" means the server the chat was last about.

Nothing runs until you click. The outcome ("Saved server app-1, SSH test passed") is added to the chat, so you can
continue ("now create redis on it").

## Where Hana runs

The first time, the panel asks where the model should run:

| Choice | What studio does |
|---|---|
| **Docker on this machine** (recommended when Docker runs) | `docker pull ak2311581/hana-pskit:1.0`, then runs it as the container `pskit-hana` on `127.0.0.1:8790` (another free port if that one is taken), restarting with Docker. Needs Docker Desktop / the docker service. |
| **Hugging Face (no Docker)** (recommended otherwise) | Installs `llama-cpp-python` (a prebuilt CPU package) if needed, downloads the GGUF from [ak2311581/hana-pskit-1.5b-GGUF](https://huggingface.co/ak2311581/hana-pskit-1.5b-GGUF) to `~/.cache/pskit/hana/` (an interrupted download resumes) and runs it inside studio. Pick **Best answers** (q8_0, 1.6 GB) or **Smaller and faster** (q4_k_m, 1.0 GB). |
| **A saved server (Docker over SSH)** | The same image on one of your saved servers, bound to the server's `127.0.0.1`. Studio opens an SSH tunnel (`ssh -N -L`) to it and keeps it open while studio runs. |
| **A model server I already run** | Any OpenAI-compatible URL: `llama-server`, Ollama, vLLM, LM Studio. An API key can be read from an environment variable; only the variable's *name* is stored. |

The choice is saved in `.pskit/studio/hana.json`. **⚙** in the panel changes it; **Stop & remove** deletes the
container (and the tunnel) and forgets the choice.

The model needs about 2 GB of RAM and no GPU; an answer takes a few seconds to about 30 s on a laptop CPU. To use
another image (for example a GPU build), type it in the **Image** field.

Run the image yourself:

```bash
docker run -d --name pskit-hana -p 127.0.0.1:8790:8080 ak2311581/hana-pskit:1.0
```

then pick **A model server I already run** with `http://127.0.0.1:8790`. Keep the port on `127.0.0.1`: the model
server has no login.

## Ask before changes, or auto-approve

| | Ask before changes (default) | Auto-approve |
|---|---|---|
| Questions, docs search, reading files, validate | run at once | run at once |
| A change (pskit.yml, a file, running a handler locally) | Hana shows a **Plan** card first: **Approve** or **Reject**, with an optional note she reads | the plan runs at once |
| A change without a plan | you **Allow** or **Don't allow** that single step | runs |
| Deploy, remove, anything in a cloud | never: Hana points to the Deploy page or the command | never |

When Hana needs information she asks with a **Hana asks** card (pick an option or type the answer). **Stop** ends
the current answer.

Every change is checked: after editing, Hana runs `pskit validate` and, when code changed, a local invoke. Before
`pskit.yml` is written, a backup goes to `.pskit/studio/backups/` (as with studio's **Save**). When Hana changed
files, studio reloads the project; if you have unsaved edits, it tells you instead, and **Save** asks before
overwriting.

## What Hana can and can't do

Hana's tools:

| Tool | What it does |
|---|---|
| `search_docs` | searches the pskit docs, CLI and studio pages shipped with pskit (studio also runs it once before every answer) |
| `get_project`, `read_file` | reads `pskit.yml` (literal secrets are hidden) and project files (up to 200 lines) |
| `get_validation`, `validate` | `pskit validate` for the current provider and stage |
| `propose_plan`, `ask_user` | the Plan and Hana asks cards |
| `set_config` | sets one value in `pskit.yml` (comments in the file are not kept, as with Save) |
| `write_file` | writes a project file |
| `invoke_local` | `pskit invoke` on this machine with a test event |
| `run_command` | a shell command in the project folder or on a saved server, after you click **Run** (below) |

Hana never reads or writes `.env` files, keys (`*.pem`, `*.key`), `.pskit/` or anything outside the project. She
has no network access of her own.

### Running terminal commands

Hana runs shell commands with **your click on every command**: ask "list the servers", "show the docker
containers on app-1" or "u execute and give me the list", and a **Hana wants to: run a command** card shows the
exact command and where it runs:

- **in the project folder** on this machine (`pskit ...` runs studio's own pskit), or
- **on a saved server** over SSH (the same login as the Servers page).

Nothing runs until you click **Run**; **Don't allow** runs nothing. This holds in *Auto-approve* too. The exit
code and the output (cut to fit) go back to Hana, and she answers from them. A command times out after 120 s.
Commands that wipe or stop a machine (`rm -rf /`, `mkfs`, `dd` to a disk, `shutdown`, `reboot` ...) are refused
even when you click.

The published model was not trained on `run_command` yet. It is in her tool list, and the end of her system
message says she has a terminal and names your saved servers (`Saved servers: app-1, app-2`), so she can pick the
`server`. The next training run includes it. Until then studio proposes the command itself for these requests,
and she answers from the output after you click **Run**:

| You write | Studio runs (after your click) |
|---|---|
| "install docker on VM_01_2cpu", "access app-1 and install nginx" | `pskit resources onprem create docker --service docker --server AZ_VM_01_2cpu` (any runtime of `pskit resources onprem catalog`; part of a server's name is enough when only one server has it) |
| "run \`docker ps\` on app-2", "run docker ps on app-2" | `docker ps` on app-2 over SSH |
| "execute pskit validate" | `pskit validate` in the project folder |
| "can you execute it", "run it" | the command in Hana's previous answer |

And when she writes a command in a code block for something you asked to *see or do* (not "how do I ..."), studio
turns it into the same **Run** card, so you don't have to copy it.

Answers that studio has from your real settings come first, without the model: the saved servers, on-prem
services, clusters, load balancers, this project's functions / workflows / resources, "what can you do?" and "who
are you?".

Limits:

- She is a small model and can be wrong. Read the plan before approving, and check her answers against the docs
  she cites (`[docs/...]`).
- Tool use was trained on AWS, Azure, GCP and on-premises. For the other providers she answers from what she learned
  about pskit, with less practice at changing projects.
- She was trained for pskit 2.10.

## Chats

Chats are saved per project in `.pskit/studio/hana/sessions/` (the last 30). Pick one from the list at the top of
the panel; **⋯** has **New chat**, **Clear this chat** and **Delete all chats** (asks first; project files are not
touched). Long chats are shortened automatically to fit the model's context (old tool results first, then the
oldest messages).

## See everything Hana does: `--ailogs`

```bash
pskit studio --ailogs=true      # or: --ailogs, or PSKIT_HANA_AILOGS=1
```

The studio's terminal then prints every step of every chat, as it happens:

| Entry | What it shows |
|---|---|
| `USER` | your message, with the provider, stage, mode and page Hana was told |
| `STUDIO ACTION` / `CARD` | the request was answered by studio (servers, services, clusters, ...): the reply and each card's data |
| `MODEL` | no studio action matched, so the model answers |
| `MODEL REQUEST` | each request to the model: messages, an estimate of the tokens, the tools; on the first one the system prompt and the history |
| `MODEL ANSWER` | the model's text and tool calls, the time it took and the token usage |
| `TOOL CALL` / `TOOL RESULT` | each tool with its arguments, and its result (long results are cut in the middle; the length is shown) |
| `WAITING` / `USER ANSWER` | plans, questions and steps waiting for you, and what you answered |
| `CHANGED FILES`, `CARD RESULT`, `ERROR`, `END` | files Hana changed, the outcome of a card you ran, errors, and the end of the turn with its time |

Passwords are hidden before anything is logged, as everywhere else in the chat.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Docker is installed but not running" | Start Docker Desktop / the docker service, then **Install & start** |
| The model is not answering | **Check again**; for Docker: `docker logs pskit-hana`. The first start loads the model (up to a minute) |
| Saved server: tunnel closed | Test the server login on the Overview page; the server needs Docker |
| Hana answers as "Qwen" from another client | Send her system prompt: `hana_system_prompt.txt` in the model repo (studio always does) |
