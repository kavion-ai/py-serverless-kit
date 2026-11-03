## In studio
1. Open this path:
Deploy > Remove

## In the terminal
1. Run:

```
pskit remove --keep-resources
```

2. Run:

```
pskit remove -y
```

## In code

pskit remove asks for confirmation unless -y is set. --keep-resources destroys functions and triggers and leaves buckets, queues, and topics.

## Project environment, trigger resources and remove - **Setup & credentials → Project

environment** creates `.venv` with the Python you pick (every interpreter found on this machine is listed, including the Windows `py` launcher's) and installs `requirements.txt` into it, or recreates it from scratch. Node.js services get **npm install** (`npm ci` when there is a lockfile). The output streams in the page.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
