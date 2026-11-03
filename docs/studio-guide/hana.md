# Hana panel in studio

Search terms: Hana, AI assistant, chat, ask Hana, Ctrl+I, plan card, approve, reject, auto-approve, ask first, install model, Docker model, Hugging Face GGUF, llama-cpp, OpenAI-compatible, run command card, studio cards, ailogs

Hana is the AI assistant built into pskit studio. She answers pskit questions and can change the project after you
approve her plan, checking every change with `validate`. Her model runs on this machine, on a saved server, or at
any OpenAI-compatible URL; nothing is sent to a cloud. This page covers the panel's controls. What Hana can do, her
tools and her limits are described in full in [assistant.md](../assistant.md).

## Open the Hana chat panel

The Hana chat panel opens from any studio page.

1. Click the round avatar **Ask Hana** at the bottom right, or press **Ctrl+I** (Cmd+I on macOS). The panel stays
   open while you move between pages (remembered in the browser).
2. The header shows **Hana** with a status dot (hover for the model's state), then:
   - **⤢**: window size, cycling normal, large and full screen (remembered);
   - **⚙** (**Where Hana runs**): the model setup below;
   - **✕**: close (Ctrl+I).
3. The bar under the header has the chat list (pick a saved chat or **New chat**), the approval mode (**Ask first** /
   **Auto-approve**), **Explain** and **⋯**.
4. Type in **Ask Hana… (Enter to send, Shift+Enter for a new line)** and press Enter or **Send**. **Stop** ends the
   current answer. Hover your own message and click the edit icon (**Edit this message**) to change and resend it.

Hana is told the page you are on and the provider and stage in the top bar.

## Install Hana's model from studio

The first time, the Hana panel asks **Where should Hana run?** The choice is saved in `.pskit/studio/hana.json`.

| Choice | What studio does |
|---|---|
| **Docker on this machine** | Pulls `ak2311581/hana-pskit:1.0` and runs it as the container `pskit-hana` on `127.0.0.1:8790` (another free port if taken). The tested setup |
| **Hugging Face (no Docker)** | Installs `llama-cpp-python` if needed, downloads the GGUF to `~/.cache/pskit/hana/` and runs it inside studio. **Model size**: **Best answers (1.6 GB, about 2 GB of RAM)** or **Smaller and faster (1.0 GB, about 1.4 GB of RAM)** |
| **A saved server** | Runs the Docker image on one of your [saved servers](servers.md) (**Server**) and connects through an SSH tunnel |
| **A model server I already run** | Any **OpenAI-compatible URL** (llama-server, Ollama, vLLM, LM Studio), with an optional API key environment variable (only the variable's name is stored, e.g. `HANA_API_KEY`) |

1. Pick a card. **Recommended** marks the best choice for this machine; **In use** marks the current one.
2. Optional: change **Docker image** (for example a GPU build).
3. Click **Install & start** (**Download & start** for Hugging Face; **Reinstall & start** for the current choice).
   The progress shows in the panel ("Installing Hana…").
4. If the model does not answer, click **Check again**. The first start loads the model (up to a minute).

To stop: open **⚙** and click **Stop & remove** (Docker or server), **Stop** (Hugging Face) or **Forget** (a model
server). The dialog offers **Stop, keep the image** / **Stop, keep the file**, or **Stop and delete the image** /
**Stop and delete the file** to free the disk.

The model needs about 2 GB of RAM and no GPU. Run the image yourself and then pick **A model server I already run**
with `http://127.0.0.1:8790`:

```bash
docker run -d --name pskit-hana -p 127.0.0.1:8790:8080 ak2311581/hana-pskit:1.0
```

## Approve or reject Hana's changes

The approval mode list sets what happens when Hana wants to change something. Its tooltip: "Ask: you approve each
plan before Hana changes anything. Auto: plans run at once."

| | **Ask first** (default) | **Auto-approve** |
|---|---|---|
| Questions, docs search, reading files, validate | run at once | run at once |
| A change (`pskit.yml`, a file, running a handler locally) | a **Plan** card: **Approve** or **Reject**, with **Optional note (e.g. use 4 workers)** she reads | runs at once |
| A single step without a plan | **Allow** or **Don't allow** | runs |
| A terminal command (`run_command`) | **Run** or **Don't allow** | **Run** or **Don't allow** (always asks) |

When Hana needs information, a **Hana asks** card shows options or a **Your answer** box. After a change Hana runs
`pskit validate` (and a local invoke when code changed). Before `pskit.yml` is written, a backup goes to
`.pskit/studio/backups/`. When Hana changed files, studio reloads the project; with unsaved edits it tells you
instead.

## Use studio cards in the Hana chat

Studio itself answers some requests with action cards under Hana's answer ("**Studio can do this directly**";
nothing runs until you click), or adds "**From studio:**" when the model had no real answer. The cards:

| Card | Opens for requests like | Button |
|---|---|---|
| **Add server** / **Update server <name>** | "add a server", an `ssh -i key.pem user@host` line, Terraform outputs | **Save & test** |
| **Create on-prem service** | "create redis on app-1 as cache" | **Create** |
| **Remove server <name>** / **Remove service <key>** | "remove server-1", "remove redis-1" | **Remove <name>** (deleting service data needs the key typed) |
| **Create functions** | "create step01 step02 functions" (asks own app or existing app, and what to do with names taken) | **Create N functions** |
| **Move into separate apps** | "make step01 and step02 separate apps" | **Move N** |
| **Remove function / workflow / resource <name>** | "remove the hello function" | **Remove <name>** |
| **Create workflow** | workflow requests | **Create (N steps)** |
| **Add resource** / **Replace resource <key>** | "add a queue named jobs" | **Add** / **Replace** |
| **Write the missing code** | handlers that have no code yet | **Write the code** |
| **Create scaling cluster** | cluster requests | **Create (N servers)** |
| **Create load balancer** | load balancer requests | **Create** |
| **Deploy this project** | "deploy it" | **Deploy** (a `prod*` stage needs the stage name typed) |

**⋯ → Studio actions answer first (then the model)** switches the order so studio answers first when it recognises
the request. The outcome of a card ("Saved server app-1, SSH test passed") is added to the chat. Details:
[assistant.md](../assistant.md#servers-and-on-prem-services-cards-you-confirm).

## Explain pages, the project or validation with Hana

The **Explain** menu sends a ready question:

- **Explain the <page> page**: what the current page is for;
- **Explain my project**: what each function does and how they connect;
- **Explain the N validation problems** (or "Explain validation (no problems now)");
- **Explain your last answer more simply**.

## Manage Hana chats

Chats are saved per project in `.pskit/studio/hana/sessions/` (the last 30). The chat list at the top switches
between them. **⋯** has **New chat**, **Clear this chat** and **Delete all chats…** (asks **Delete all chats?**;
project files are not touched). Long chats are shortened automatically to fit the model's context.

## Log every Hana step in the terminal

`pskit studio --ailogs=true` (or `--ailogs`, or `PSKIT_HANA_AILOGS=1`) prints every step of every chat in the
terminal running studio: your messages, studio actions and cards, model requests and answers, tool calls and results,
waiting plans, changed files and errors. Passwords are hidden. The entry types are listed in
[assistant.md](../assistant.md#see-everything-hana-does---ailogs).

```bash
pskit studio --ailogs=true
```

## See also

- [Hana, the studio's AI assistant](../assistant.md)
- [Studio guide](README.md)
- [Servers panel](servers.md)
