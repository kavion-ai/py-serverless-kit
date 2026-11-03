"""Serialize hand-authored shard 016 and 017 conversations. Not a template generator."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "ai-agent" / "training" / "tools"))
import check_knowledge as ck  # noqa: E402
import check_quality as cq  # noqa: E402

AUTHORED = Path(__file__).resolve().parent
SLOTS = AUTHORED.parent / "slots"

TEXTS = {}


def add(sid, user, answer, query=None):
    TEXTS[sid] = (user, answer, query)


add(
    "k_cmd_0641",
    "Want `--save` when creating jobs redis so it stay in file?",
    "`pskit resources onprem` creates services for on-premises functions with Docker, here or on an SSH server. "
    "The group command has no flags. `--save` belongs on `create`.\n\n"
    "**In the terminal**\n\n"
    "1. See which services and runtimes can be created.\n\n"
    "```\n"
    "pskit resources onprem catalog\n"
    "```\n\n"
    "2. Create jobs as redis, attach worker, and pass `--save`.\n\n"
    "```\n"
    "pskit resources onprem create jobs --service redis --attach worker --save\n"
    "```",
)

add(
    "k_cmd_0642",
    "After `--save`, will orders-db come back on next deploy?",
    "Yes, if orders-db is still in `pskit.yml`. The next deploy creates it again, so remove it from `resources:` "
    "or the trigger before you delete it. Deleting a deployed resource runs `terraform destroy -target=...`. "
    "A kept resource is removed from `.pskit/<provider>-<stage>/kept/`, and that folder is removed when the last one is gone. "
    "Credentials are the same as for `pskit deploy`. [docs/cli.md#pskit-resources-onprem].\n\n"
    "`pskit resources onprem` is the group that creates those Docker services, here or on an SSH server.",
    "recreate resource after deploy",
)

add(
    "k_cmd_0643",
    "Drop `orders-db` from resources before destroy or it return?",
    "Yes. Drop it first. If orders-db is still in `pskit.yml`, the next deploy creates it again, so remove it from "
    "`resources:` or the trigger, then delete. That delete runs `terraform destroy -target=...`. "
    "[docs/cli.md#pskit-resources-onprem].",
    "remove resource before destroy",
)

add(
    "k_cmd_0644",
    "`jobs` still under resources, deploy recreates it back?",
    "Yes. Leave jobs in `pskit.yml` and the next deploy creates it again. Remove it from `resources:` or the trigger first. "
    "[docs/cli.md#pskit-resources-onprem].",
    "pskit.yml resource next deploy",
)

add(
    "k_cmd_0645",
    "Once last `jobs` is gone, kept folder gone too?",
    "Yes. Kept resources are deleted from `.pskit/<provider>-<stage>/kept/`, and that workspace is removed when the last one is gone. "
    "Also take jobs out of `pskit.yml`, or the next deploy creates it again. Credentials match `pskit deploy`. "
    "[docs/cli.md#pskit-resources-onprem].",
    "kept workspace last resource",
)

add(
    "k_cmd_0646",
    "`jobs` kept workspace removed after the last delete?",
    "Yes. `.pskit/<provider>-<stage>/kept/` is removed when the last kept resource is gone. "
    "[docs/cli.md#pskit-resources-onprem].",
    "kept folder removed",
)

add(
    "k_cmd_0647",
    "`--pem` key.pem plus `--ssh` for orders-db?",
    "`--pem` is the private key for `--ssh`. Both are flags on `create`, not on the group command.\n\n"
    "**In the terminal**\n\n"
    "1. Create orders-db as postgres on that host and pass `--save`.\n\n"
    "```\n"
    "pskit resources onprem create orders-db --service postgres --ssh deploy@192.0.2.10 --pem key.pem --save\n"
    "```",
)

add(
    "k_cmd_0648",
    "Does `pskit.yml` still holding orders-db recreate it?",
    "Yes. Still listed in `pskit.yml` means the next deploy creates it again. Remove orders-db from `resources:` or the trigger first. "
    "The delete runs `terraform destroy -target=...`. [docs/cli.md#pskit-resources-onprem].",
    "destroy target recreates resource",
)

add(
    "k_cmd_0649",
    "Deleting `jobs`: same credentials as `pskit deploy`?",
    "Yes. Credentials for that delete are the same as for `pskit deploy`. [docs/cli.md#pskit-resources-onprem].",
    "delete resource credentials",
)

add(
    "k_cmd_0650",
    "`--on` for jobs alerts, not just `--cpu` 90?",
    "`--on` turns alerts on. `--cpu` only sets the CPU percent, and the default is 90. It does not switch alerts on by itself.\n\n"
    "**In the terminal**\n\n"
    "1. Turn jobs alerts on and leave CPU at the default percent.\n\n"
    "```\n"
    "pskit resources onprem alerts jobs --on --cpu 90\n"
    "```",
)

add(
    "k_cmd_0651",
    "`--off` on cache keeps the alert settings?",
    "`--off` turns cache alerts off and keeps the settings.",
)

add(
    "k_cmd_0652",
    "Post `--webhook` alerts for orders-db, exact command?",
    "`--webhook` POSTs each alert to that URL. A Slack or Teams incoming webhook works, and so does any other URL.\n\n"
    "**In the terminal**\n\n"
    "1. Turn alerts on and set the webhook for orders-db.\n\n"
    "```\n"
    "pskit resources onprem alerts orders-db --on --webhook https://example.com/hooks/alerts\n"
    "```",
)

add(
    "k_cmd_0653",
    "`--function` worker with `--stage` on jobs?",
    "`--function` names the project function that runs with each alert. `--stage` is the deployed on-prem stage that runs it. The default is any.\n\n"
    "**In the terminal**\n\n"
    "1. Point jobs alerts at worker on the staging on-prem stage.\n\n"
    "```\n"
    "pskit resources onprem alerts jobs --on --function worker --stage staging\n"
    "```",
)

add(
    "k_cmd_0654",
    "`--test` fires one alert for jobs right now?",
    "`--test` sends a test alert now.\n\n"
    "**In the terminal**\n\n"
    "1. Send the test for jobs.\n\n"
    "```\n"
    "pskit resources onprem alerts jobs --test\n"
    "```",
)

add(
    "k_cmd_0655",
    "Cron should pass `--check` on orders-db, yes?",
    "`--check` measures now and alerts when a limit is crossed. It is the flag meant for cron.\n\n"
    "**In the terminal**\n\n"
    "1. Run one check against orders-db.\n\n"
    "```\n"
    "pskit resources onprem alerts orders-db --check\n"
    "```",
)

add(
    "k_cmd_0656",
    "Defaults for `--memory` and `--disk` on cache?",
    "`--memory` defaults to 90 percent. `--disk` defaults to 85 percent of the data disk.\n\n"
    "| Flag | Default |\n"
    "| --- | --- |\n"
    "| `--memory` | 90 percent |\n"
    "| `--disk` | 85 percent |",
)

add(
    "k_cmd_0657",
    "`--lag` 60 with `--cooldown` 30 on jobs?",
    "`--lag` is how many seconds a replica may lag, default 60. `--cooldown` is minutes between alerts, default 30.\n\n"
    "| Flag | Meaning | Default |\n"
    "| --- | --- | --- |\n"
    "| `--lag` | Replica delay before an alert | 60 seconds |\n"
    "| `--cooldown` | Gap between alerts | 30 minutes |",
)

add(
    "k_cmd_0658",
    "`--config` other.yml when setting alerts on jobs?",
    "`--config` chooses the config file. pskit.yml is the default, so pass it only when the file is different.\n\n"
    "**In the terminal**\n\n"
    "1. Turn jobs alerts on using other.yml.\n\n"
    "```\n"
    "pskit resources onprem alerts jobs --config other.yml --on\n"
    "```",
)

add(
    "k_cmd_0659",
    "Pick `--on` or `--off` for cache alerts?",
    "`--on` turns cache alerts on. `--off` turns them off. Either way, the settings are kept.",
)

add(
    "k_cmd_0660",
    "Show `--cpu` `--memory` `--disk` `--lag` defaults?",
    "Defaults are CPU 90, memory 90, disk 85, and replica lag 60 seconds. Passing the flags sets those limits. The key alone shows the service alerts.\n\n"
    "**In the terminal**\n\n"
    "1. Show orders-db alerts.\n\n"
    "```\n"
    "pskit resources onprem alerts orders-db\n"
    "```\n\n"
    "2. Set the four limits explicitly.\n\n"
    "```\n"
    "pskit resources onprem alerts orders-db --cpu 90 --memory 90 --disk 85 --lag 60\n"
    "```",
)

add(
    "k_cmd_0661",
    "Need `-o` dump of orders-db before a rollback?",
    "`-o` writes the dump to a file you name. The default path is `.pskit/backups/<key>-<time>.<ext>`. "
    "Take that file before you change data. This command does not restore, so the file is the copy you keep for a rollback.\n\n"
    "**In the terminal**\n\n"
    "1. Dump orders-db to a named file.\n\n"
    "```\n"
    "pskit resources onprem backup orders-db -o orders-db.dump\n"
    "```",
)

add(
    "k_cmd_0662",
    "Missing `-d` backups folder: does orders-db dump fail?",
    "No. `-d` creates the folder when it is missing, then writes `<key>-<time>.<ext>` into it. What breaks is a folder you cannot write, not a folder that is merely absent.\n\n"
    "**In the terminal**\n\n"
    "1. Dump orders-db into backups.\n\n"
    "```\n"
    "pskit resources onprem backup orders-db -d backups\n"
    "```",
)

add(
    "k_cmd_0663",
    "Full disk under `.pskit/backups` while dumping jobs?",
    "The default file is `.pskit/backups/<key>-<time>.<ext>`. This command does not free disk. If that folder cannot hold the file, pass `-o` or `-d` and point at a path with room.",
)

add(
    "k_cmd_0664",
    "`--output` path for cache, or `.pskit/backups` name?",
    "`--output` is one exact file. Without it, the name is `.pskit/backups/<key>-<time>.<ext>`.\n\n"
    "**In the terminal**\n\n"
    "1. Write the cache dump to a file you choose.\n\n"
    "```\n"
    "pskit resources onprem backup cache --output cache.dump\n"
    "```",
)

add(
    "k_cmd_0665",
    "`--dir` backups for orders-db, not a random folder?",
    "`--dir` is the folder that receives `<key>-<time>.<ext>`. It is created when missing. Keep those files together if you need them for a rollback.\n\n"
    "**In the terminal**\n\n"
    "1. Dump orders-db into backups.\n\n"
    "```\n"
    "pskit resources onprem backup orders-db --dir backups\n"
    "```",
)

add(
    "k_cmd_0666",
    "`-c` pskit.yml and `-o` for the jobs dump?",
    "`-c` selects the config file, and pskit.yml is already the default. `-o` is the dump file. Use both when you want a named copy before a change.\n\n"
    "**In the terminal**\n\n"
    "1. Dump jobs from pskit.yml into jobs.dump.\n\n"
    "```\n"
    "pskit resources onprem backup jobs -c pskit.yml -o jobs.dump\n"
    "```",
)

add(
    "k_cmd_0667",
    "Wrong key with `--output`: whose data gets dumped?",
    "KEY picks the service. `--output` only picks the file. A wrong key writes that other service's data into the file, so a later rollback would start from the wrong dump.",
)

add(
    "k_cmd_0668",
    "Nightly `--dir` backups of orders-db for rollback?",
    "Each default name includes the time, so a new run does not reuse the same `<key>-<time>.<ext>` file. `--dir` only chooses the folder. This command does not delete older dumps and it does not restore.\n\n"
    "**In the terminal**\n\n"
    "1. Write a new orders-db dump into backups.\n\n"
    "```\n"
    "pskit resources onprem backup orders-db --dir backups\n"
    "```",
)

add(
    "k_cmd_0669",
    "Dump jobs with `-o` before this deploy changes data?",
    "Yes. Dump first. `-o` sets the file you will keep. A later change does not put the old bytes back. This command only writes the dump.\n\n"
    "**In the terminal**\n\n"
    "1. Save jobs to a file named for this moment.\n\n"
    "```\n"
    "pskit resources onprem backup jobs -o jobs-before.dump\n"
    "```",
)

add(
    "k_cmd_0670",
    "`--config` staging.yml plus `--dir` backups for cache?",
    "`--config` picks the config file. `--dir` picks the folder, and creates it if needed. Neither flag changes the service.\n\n"
    "**In the terminal**\n\n"
    "1. Dump cache using staging.yml into backups.\n\n"
    "```\n"
    "pskit resources onprem backup cache --config staging.yml --dir backups\n"
    "```",
)

add(
    "k_cmd_0671",
    "Does `-d` backups rewrite pskit.yml for orders-db?",
    "No. `-d` only chooses the dump folder. It does not rewrite pskit.yml. `-c` would select a different config file, and pskit.yml stays the default.\n\n"
    "**In the terminal**\n\n"
    "1. Dump orders-db into backups while reading pskit.yml.\n\n"
    "```\n"
    "pskit resources onprem backup orders-db -c pskit.yml -d backups\n"
    "```",
)

add(
    "k_cmd_0672",
    "`--json` on catalog before creating a prod service?",
    "`pskit resources onprem catalog` lists services and runtimes that can be created. `--json` prints that list as JSON. Check it before you create, so you do not guess a name.\n\n"
    "**In the terminal**\n\n"
    "1. Print the catalog as JSON.\n\n"
    "```\n"
    "pskit resources onprem catalog --json\n"
    "```",
)

add(
    "k_cmd_0673",
    "Which runtimes does `--json` catalog actually print?",
    "`--json` prints the services and runtimes that can be created, as JSON. The help does not include sample rows, so read the command output for the names.",
)

add(
    "k_cmd_0674",
    "Is `--json` the only flag on catalog?",
    "Yes. `--json` is the only option. It prints JSON. With no flag you still get the catalog of services and runtimes that can be created.",
)

add(
    "k_cmd_0675",
    "Print catalog `--json` so we see creatable runtimes?",
    "Yes. That flag prints JSON for the services and runtimes that can be created. Catalog does not attach a function. It only prints the list.\n\n"
    "**In the terminal**\n\n"
    "1. Print JSON before you pick a runtime.\n\n"
    "```\n"
    "pskit resources onprem catalog --json\n"
    "```",
)

add(
    "k_cmd_0676",
    "Lambda layers aside, catalog `--json` for on-prem?",
    "This is not a layer list. `--json` prints the on-prem services and runtimes that can be created.\n\n"
    "**In the terminal**\n\n"
    "1. Print that catalog as JSON.\n\n"
    "```\n"
    "pskit resources onprem catalog --json\n"
    "```",
)

add(
    "k_cmd_0677",
    "ElastiCache habit: does catalog `--json` list services?",
    "Not an ElastiCache page. `--json` prints JSON for the services and runtimes that can be created. The command help does not name the rows. Read the JSON.",
)

add(
    "k_cmd_0678",
    "Which flag, `--json`, prints the creatable services?",
    "The flag is `--json`. It prints the services and runtimes that can be created.\n\n"
    "**In the terminal**\n\n"
    "1. Ask the catalog for JSON.\n\n"
    "```\n"
    "pskit resources onprem catalog --json\n"
    "```",
)

add(
    "k_cmd_0679",
    "Not Step Functions. Catalog `--json` of services we can create?",
    "Right, this is not Step Functions. `--json` prints which on-prem services and runtimes can be created.\n\n"
    "**In the terminal**\n\n"
    "1. Print the catalog.\n\n"
    "```\n"
    "pskit resources onprem catalog --json\n"
    "```",
)

add(
    "k_cmd_0680",
    "Skip IAM. `--json` on catalog lists creatable services?",
    "IAM will not list these. `--json` prints JSON from `pskit resources onprem catalog`, the services and runtimes that can be created.\n\n"
    "**In the terminal**\n\n"
    "1. Print it.\n\n"
    "```\n"
    "pskit resources onprem catalog --json\n"
    "```",
)

add(
    "k_cmd_0681",
    "Layer list analog: `--json` on the on-prem catalog?",
    "A layer list is the wrong picture. `--json` prints the on-prem services and runtimes that can be created.\n\n"
    "**In the terminal**\n\n"
    "1. Print the catalog as JSON.\n\n"
    "```\n"
    "pskit resources onprem catalog --json\n"
    "```",
)

add(
    "k_cmd_0682",
    "Plain catalog or `--json` while testing what exists?",
    "Plain text is the default. `--json` is the same list of services and runtimes, printed for a script.\n\n"
    "**In the terminal**\n\n"
    "1. Read it as text.\n\n"
    "```\n"
    "pskit resources onprem catalog\n"
    "```\n\n"
    "2. Read the same catalog as JSON.\n\n"
    "```\n"
    "pskit resources onprem catalog --json\n"
    "```",
)

add(
    "k_cmd_0683",
    "`--shell` on cache, or the redis-cli client?",
    "This does not SSH you into a box to type redis-cli yourself. With no COMMAND, cache opens an interactive redis-cli. `--shell` is sh in the container instead of that client.\n\n"
    "**In the terminal**\n\n"
    "1. Open the cache client.\n\n"
    "```\n"
    "pskit resources onprem console cache\n"
    "```\n\n"
    "2. Or open a shell instead.\n\n"
    "```\n"
    "pskit resources onprem console cache --shell\n"
    "```",
)

add(
    "k_cmd_0684",
    "Run `LLEN` against cache, not a log group?",
    "Correct, this is not a log group. COMMAND runs inside the service and prints the output. For cache, the example command is `LLEN jobs`.\n\n"
    "**In the terminal**\n\n"
    "1. Run that one command.\n\n"
    "```\n"
    "pskit resources onprem console cache \"LLEN jobs\"\n"
    "```",
)

add(
    "k_cmd_0685",
    "`-c` pskit.yml with the orders-db count query?",
    "`-c` only picks the config file. pskit.yml is the default. The SQL is the COMMAND, and orders-db is the KEY.\n\n"
    "**In the terminal**\n\n"
    "1. Run the count against orders-db.\n\n"
    "```\n"
    "pskit resources onprem console orders-db \"SELECT count(*) FROM orders;\" -c pskit.yml\n"
    "```",
)

add(
    "k_cmd_0686",
    "In main.py, must `--shell` stay off by default?",
    "The callback for `pskit resources onprem console` is in `src/py_serverless_kit/cli/main.py`. `--shell` defaults off: it is sh in the container instead of the service client. "
    "This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text is what says the command runs a client or one COMMAND.",
)

add(
    "k_cmd_0687",
    "Console callback and `--shell`: any `.remove(` in main.py?",
    "No. The console callback in `src/py_serverless_kit/cli/main.py` has no `.remove(`. That only describes this function. `--shell` only switches to sh in the container.",
)

add(
    "k_cmd_0688",
    "Keep `--config` defaulting to pskit.yml if console changes?",
    "Yes. `--config` defaults to pskit.yml, and `-c` is the same flag. A change should keep that default, because the help says the config file default is pskit.yml. "
    "The callback is in `src/py_serverless_kit/cli/main.py`.\n\n"
    "**In the terminal**\n\n"
    "1. Pass `-c` only when the file is not pskit.yml.\n\n"
    "```\n"
    "pskit resources onprem console cache -c pskit.yml\n"
    "```",
)

add(
    "k_cmd_0689",
    "redis-cli for cache: help text only, or main.py logic?",
    "The help text says cache with no COMMAND is an interactive redis-cli, and the help text is what says what the command does. "
    "The callback lives in `src/py_serverless_kit/cli/main.py`. The note that this function body has no `click.confirm` only describes this function.",
)

add(
    "k_cmd_0690",
    "`--shell` means sh. Where is that callback defined?",
    "`--shell` is a shell (sh) in the container instead of the service's client. The callback is in `src/py_serverless_kit/cli/main.py`.\n\n"
    "**In the terminal**\n\n"
    "1. Open sh for cache.\n\n"
    "```\n"
    "pskit resources onprem console cache --shell\n"
    "```",
)

add(
    "k_cmd_0691",
    "Would adding confirm change `--shell` behavior in main.py?",
    "The current console function body has no `click.confirm`. That only describes this function, not a second rule. "
    "Adding a confirm would be behavior the help does not describe. `--shell` would still mean sh in the container unless the help changes too. "
    "The callback is in `src/py_serverless_kit/cli/main.py`.",
)

add(
    "k_cmd_0692",
    "Besides `--shell`, is `--config` the other console flag?",
    "Yes. The options are `--shell` and `-c` or `--config`. Nothing else is listed.\n\n"
    "**In the terminal**\n\n"
    "1. Run one command in secrets, using the default file.\n\n"
    "```\n"
    "pskit resources onprem console secrets \"kv get secret/db-password\" --config pskit.yml\n"
    "```",
)

add(
    "k_cmd_0693",
    "KEY versus COMMAND on orders-db: which is the SQL?",
    "KEY is the service name, orders-db. COMMAND is optional and is what you run, so the SQL is COMMAND. With no COMMAND you get the service client instead.\n\n"
    "**In the terminal**\n\n"
    "1. Pass the count as COMMAND.\n\n"
    "```\n"
    "pskit resources onprem console orders-db \"SELECT count(*) FROM orders;\"\n"
    "```",
)

add(
    "k_cmd_0694",
    "`--service` required: where does create live in main.py?",
    "`--service` is required. See `pskit resources onprem catalog` for the names. The create callback is in `src/py_serverless_kit/cli/main.py`. "
    "This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says it starts a service, or installs a runtime, and adds it as a resource.\n\n"
    "**In the terminal**\n\n"
    "1. Read the catalog.\n\n"
    "```\n"
    "pskit resources onprem catalog\n"
    "```\n\n"
    "2. Create jobs with the required flag and `--save`.\n\n"
    "```\n"
    "pskit resources onprem create jobs --service redis --save\n"
    "```",
)

add(
    "k_cmd_0695",
    "`--save` writes pskit.yml. What must stay true?",
    "`--save` writes the resource and its triggers into pskit.yml. A change must keep that help true. "
    "The callback is in `src/py_serverless_kit/cli/main.py`. This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`, and that only describes this function.",
)

add(
    "k_cmd_0696",
    "`--replica` plus `--primary`: which file owns create?",
    "Create lives in `src/py_serverless_kit/cli/main.py`. With `--replica`, `--primary` is the saved server that takes writes, each `--replica` serves reads, and `--balancer` gives functions one address.\n\n"
    "**In the terminal**\n\n"
    "1. Create a replicated orders-db and save it.\n\n"
    "```\n"
    "pskit resources onprem create orders-db --service postgres --primary db1 --replica db2 --balancer lb1 --sync async --save\n"
    "```",
)

add(
    "k_cmd_0697",
    "`--local` versus `--ssh`: callback file for create?",
    "The callback is in `src/py_serverless_kit/cli/main.py`. `--local` creates the service on this machine even if the functions deploy over SSH. `--ssh` is `user@host` of the server, with an optional port.\n\n"
    "**In the terminal**\n\n"
    "1. Force jobs onto this machine.\n\n"
    "```\n"
    "pskit resources onprem create jobs --service redis --local --save\n"
    "```",
)

add(
    "k_cmd_0698",
    "`--cluster` with `--node`: what a change must keep?",
    "`--node` is only meaningful with `--cluster`. It names the cluster's saved server to run on. Without `--node`, the cluster server with the most free memory is used. "
    "Keep that pairing. The callback is in `src/py_serverless_kit/cli/main.py`, and the lack of `click.confirm` only describes this function.\n\n"
    "**In the terminal**\n\n"
    "1. Place jobs on one saved server of the cluster.\n\n"
    "```\n"
    "pskit resources onprem create jobs --service redis --cluster prod --node edge1 --save\n"
    "```",
)

add(
    "k_cmd_0699",
    "`--password-env` DB_PASSWORD with `--save` into pskit.yml?",
    "`--password-env` reads the password from that environment variable. Do not type the password on the command line. `--save` writes the resource and triggers into pskit.yml.",
)

add(
    "k_cmd_0700",
    "`--import` of a dump: must create avoid confirm?",
    "`--import` loads a dump once the database is up. The current create function body has no `click.confirm`. That only describes this function. The help text is what says what the command does. The callback is in `src/py_serverless_kit/cli/main.py`.",
)

add(
    "k_cmd_0701",
    "Start `jobs` redis. Is `--service` the flag?",
    "`--service` is the flag, and it is required. It names what to start. Catalog shows the names you can pass.\n\n"
    "**In the terminal**\n\n"
    "1. Look at the catalog.\n\n"
    "```\n"
    "pskit resources onprem catalog\n"
    "```\n\n"
    "2. Start jobs and save it.\n\n"
    "```\n"
    "pskit resources onprem create jobs --service redis --save\n"
    "```",
)

add(
    "k_cmd_0702",
    "`--ssh` deploy host for orders-db, with `--pem` key.pem?",
    "`--ssh` is the user and host of the server. `--pem` is the private key file for that SSH login.\n\n"
    "**In the terminal**\n\n"
    "1. Create orders-db on the server and save it.\n\n"
    "```\n"
    "pskit resources onprem create orders-db --service postgres --ssh deploy@192.0.2.10 --pem key.pem --save\n"
    "```",
)

add(
    "k_cmd_0703",
    "Is `-a` the same as `--attach` for worker?",
    "Yes. `-a` and `--attach` are the same flag. It adds a trigger on that function. You can repeat it.\n\n"
    "**In the terminal**\n\n"
    "1. Create jobs and attach worker.\n\n"
    "```\n"
    "pskit resources onprem create jobs --service redis --attach worker --save\n"
    "```",
)

add(
    "k_cmd_0704",
    "`--local` for jobs even if functions use `--ssh`?",
    "`--local` creates the service on this machine even when the functions deploy over SSH.\n\n"
    "**In the terminal**\n\n"
    "1. Create jobs locally and save it.\n\n"
    "```\n"
    "pskit resources onprem create jobs --service redis --local --save\n"
    "```",
)

add(
    "k_cmd_0705",
    "Redis Commander for `cache`. Do I pass `--port`?",
    "You do not have to. `pskit resources onprem gui` starts the web UI. For cache, that is Redis Commander, and its default port is 8082. `--port` only changes that port.\n\n"
    "**In the terminal**\n\n"
    "1. Start the cache UI with the generated password.\n\n"
    "```\n"
    "pskit resources onprem gui cache\n"
    "```",
)

add(
    "k_cmd_0706",
    "`--login none` on cache: keep it private?",
    "Yes. `--login none` means no sign-in. Keep that UI on 127.0.0.1 or a tunnel.\n\n"
    "**In the terminal**\n\n"
    "1. Start cache with no login.\n\n"
    "```\n"
    "pskit resources onprem gui cache --login none\n"
    "```",
)

add(
    "k_cmd_0707",
    "`--check` when the cache UI will not open?",
    "`--check` is the flag. It looks at the container, ports, server, and firewall to find out why the web UI does not open.\n\n"
    "**In the terminal**\n\n"
    "1. Check the cache UI.\n\n"
    "```\n"
    "pskit resources onprem gui cache --check\n"
    "```",
)

add(
    "k_cmd_0708",
    "`--remove` only the cache web UI, not redis?",
    "`--remove` stops and deletes the companion web UI. It does not say it deletes the service itself.\n\n"
    "**In the terminal**\n\n"
    "1. Remove the cache UI.\n\n"
    "```\n"
    "pskit resources onprem gui cache --remove\n"
    "```",
)

add(
    "k_cmd_0709",
    "`--password-env` GUI_PASSWORD for the cache UI?",
    "`--password-env` reads your UI password from that environment variable. If you omit it, the password is generated.\n\n"
    "**In the terminal**\n\n"
    "1. Start cache using the variable.\n\n"
    "```\n"
    "pskit resources onprem gui cache --password-env GUI_PASSWORD\n"
    "```",
)

add(
    "k_cmd_0710",
    "Redis Commander `--port` 8082 to open cache?",
    "8082 is already the Redis Commander default. Pass `--port` only when you want a different UI port.\n\n"
    "**In the terminal**\n\n"
    "1. Start cache on that default port.\n\n"
    "```\n"
    "pskit resources onprem gui cache --port 8082\n"
    "```",
)

add(
    "k_cmd_0711",
    "`-c` pskit.yml and `--login password` for cache?",
    "`-c` picks the config file, and pskit.yml is the default. `--login password` is also the default sign-in for the companion UI.\n\n"
    "**In the terminal**\n\n"
    "1. Start cache with both spelled out.\n\n"
    "```\n"
    "pskit resources onprem gui cache -c pskit.yml --login password\n"
    "```",
)

add(
    "k_cmd_0712",
    "Adminer default `--port` 8089, or do I set one?",
    "Adminer's default port is 8089. Redis Commander's default is 8082. The cache example starts Redis Commander, so you only pass `--port` to override the UI port.\n\n"
    "**In the terminal**\n\n"
    "1. Start the cache UI on the Redis Commander default.\n\n"
    "```\n"
    "pskit resources onprem gui cache\n"
    "```",
)

add(
    "k_cmd_0713",
    "`--login` choices on cache: password or none?",
    "`--login` accepts `password` or `none`. The default is password. `none` means no login, so keep the UI private.\n\n"
    "| Value | Meaning |\n"
    "| --- | --- |\n"
    "| password | Sign in to the companion UI |\n"
    "| none | No login. Keep it on 127.0.0.1 or a tunnel |\n\n"
    "**In the terminal**\n\n"
    "1. Start cache with no sign-in.\n\n"
    "```\n"
    "pskit resources onprem gui cache --login none\n"
    "```",
)

add(
    "k_cmd_0714",
    "`--check` mentions firewall. Then try `--port`?",
    "`--check` looks at the container, ports, server, and firewall. `--port` only changes the UI port. It does not open a firewall by itself.\n\n"
    "**In the terminal**\n\n"
    "1. Find out why cache does not open.\n\n"
    "```\n"
    "pskit resources onprem gui cache --check\n"
    "```",
)

add(
    "k_cmd_0715",
    "Generated password, or `--password-env` for cache GUI?",
    "If you skip `--password-env`, the UI password is generated. Pass the flag when the password should come from an environment variable.\n\n"
    "**In the terminal**\n\n"
    "1. Start cache with your variable.\n\n"
    "```\n"
    "pskit resources onprem gui cache --password-env GUI_PASSWORD\n"
    "```",
)

add(
    "k_cmd_0716",
    "`--json` optional when listing on-prem services?",
    "`pskit resources onprem list` shows services created from this project. `--json` is optional. It only changes the print format to JSON.\n\n"
    "**In the terminal**\n\n"
    "1. Print the list as text.\n\n"
    "```\n"
    "pskit resources onprem list\n"
    "```\n\n"
    "2. Print the same list as JSON.\n\n"
    "```\n"
    "pskit resources onprem list --json\n"
    "```",
)

add(
    "k_cmd_0717",
    "`--config` pskit.yml: list services from this project?",
    "`--config` picks the config file. pskit.yml is the default. The list is still the services created from this project.\n\n"
    "**In the terminal**\n\n"
    "1. List from pskit.yml.\n\n"
    "```\n"
    "pskit resources onprem list --config pskit.yml\n"
    "```",
)

add(
    "k_cmd_0718",
    "`--json` so a script can read the service list?",
    "Yes. `--json` prints the services created from this project as JSON.\n\n"
    "**In the terminal**\n\n"
    "1. Print JSON for the script.\n\n"
    "```\n"
    "pskit resources onprem list --json\n"
    "```",
)

add(
    "k_cmd_0719",
    "Does `--json` change which services `list` shows?",
    "No. `--json` changes the format, not which services are included. Both forms list services created from this project.",
)

add(
    "k_cmd_0720",
    "`-c` other.yml versus pskit.yml for on-prem list?",
    "`-c` and `--config` are the same flag. pskit.yml is the default. Point the flag at other.yml only when that is the file you want.\n\n"
    "**In the terminal**\n\n"
    "1. List from the default file.\n\n"
    "```\n"
    "pskit resources onprem list -c pskit.yml\n"
    "```\n\n"
    "2. List from the other file.\n\n"
    "```\n"
    "pskit resources onprem list --config other.yml\n"
    "```",
)


def build(slots, call_start):
    rows = []
    n = call_start
    for slot in slots:
        sid = slot["id"]
        user, answer, query = TEXTS[sid]
        messages = [
            {
                "role": "system",
                "content": ck.SYSTEM_BEFORE_ENV
                + f"Environment: provider={slot['provider']} stage={slot['stage']} mode={slot['mode']} page={slot['page']}",
            },
            {"role": "user", "content": user},
        ]
        if slot["grounding"] == "search":
            n += 1
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": f"call_{n:02d}",
                            "type": "function",
                            "function": {
                                "name": "search_docs",
                                "arguments": json.dumps({"query": query}),
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": f"call_{n:02d}",
                    "name": "search_docs",
                    "content": slot["excerpt"],
                }
            )
        messages.append({"role": "assistant", "content": answer})
        rows.append(
            {
                "id": sid,
                "messages": messages,
                "meta": {
                    "category": slot["category"],
                    "card_ids": slot["card_ids"],
                    "grounding": slot["grounding"],
                    "persona": slot["persona"],
                    "sources": slot["sources"],
                },
            }
        )
    return rows


def validate(name, rows, slots):
    errors = []
    known = ck.cli_index()
    headings = ck.heading_index()
    keys = ck.schema_keys()
    blob = ck.studio_blob()
    if len(rows) != len(slots):
        errors.append(f"{name}: {len(rows)} != {len(slots)}")
    for i, (obj, slot) in enumerate(zip(rows, slots), 1):
        where = f"{name}:{i}"
        if obj["id"] != slot["id"]:
            errors.append(f"{where}: id")
        meta = obj["meta"]
        if set(meta) != {"category", "card_ids", "grounding", "persona", "sources"}:
            errors.append(f"{where}: meta keys {sorted(meta)}")
        for field in ("category", "card_ids", "grounding", "persona", "sources"):
            if meta[field] != slot[field]:
                errors.append(f"{where}: meta {field}")
        messages = obj["messages"]
        ck.check_messages(messages, where, errors)
        blob_text = "\n".join(m.get("content") or "" for m in messages)
        ck.check_pskit_lines(blob_text, known, where, errors)
        ck.check_sources(meta.get("sources") or [], headings, where, errors)
        ck.check_ips(blob_text, where, errors)
        ck.check_yaml(blob_text, keys, where, errors)
        ck.check_python(blob_text, where, errors)
        ck.check_studio_paths(blob_text, blob, where, errors)
        env = f"provider={slot['provider']} stage={slot['stage']} mode={slot['mode']} page={slot['page']}"
        if env not in messages[0]["content"]:
            errors.append(f"{where}: missing env")
        if not messages[0]["content"].startswith(ck.SYSTEM_BEFORE_ENV):
            errors.append(f"{where}: system")
        user = next(m["content"] for m in messages if m["role"] == "user")
        low = user.lower()
        for banned in ("can you explain", "how do i", "what does the", "i just opened", "on call for"):
            if low.startswith(banned):
                errors.append(f"{where}: banned opening")
        if slot["grounding"] == "search":
            tool = next(m for m in messages if m["role"] == "tool")
            if tool["content"] != slot["excerpt"]:
                errors.append(f"{where}: excerpt mismatch")
            if len(tool["content"]) < 300:
                errors.append(f"{where}: excerpt short {len(tool['content'])}")
        else:
            if any(m.get("tool_calls") or m.get("role") == "tool" for m in messages):
                errors.append(f"{where}: unexpected tool")
        five = " ".join(user.split()[:5]).lower()
        if not any(tok in five for tok in ("--", " -c", "-c ", "pskit.yml", "jobs", "orders-db", "cache", "catalog", ".pskit", "key.pem", "redis-cli", "llen", "main.py", "worker")):
            # still require a flag-like token or resource token in the first five words
            if "--" not in five and "pskit.yml" not in five and not any(w.strip("`.,:;?") in {"jobs", "orders-db", "cache", "catalog", "worker", "llen"} for w in five.split()):
                errors.append(f"{where}: first five lack a card token: {five!r}")
    ck.check_training_shape(rows, errors)
    answers = {}
    openings = {}
    user5 = {}
    for row in rows:
        cid = row["id"]
        messages = row["messages"]
        for message in messages:
            if message.get("role") == "assistant" and (message.get("content") or "").strip():
                answers.setdefault(message["content"].strip(), []).append(cid)
            if message.get("role") != "user":
                continue
            text = message.get("content") or ""
            openings.setdefault(" ".join(text.lower().split()[:4]), []).append(cid)
            user5.setdefault(" ".join(text.lower().split()[:5]), []).append(cid)
            if cq.TITLE_LEAK.search(text):
                errors.append(f"Q3 {cid}")
        for message in messages:
            if message.get("role") != "assistant":
                continue
            text = message.get("content") or ""
            low = text.lower()
            for phrase in cq.FILLER:
                if phrase in low:
                    errors.append(f"Q2 {cid}: {phrase}")
            part = cq.in_code_part(text)
            if part is not None and "```" not in part:
                errors.append(f"Q4 {cid}")
            first = text.strip().splitlines()[0] if text.strip() else ""
            word = first.split()[0] if first.split() else ""
            mid = word[:1].islower() and word.isalpha() and word not in ("pskit", "hi", "hello")
            if first and (mid or __import__("re").search(r"\|\s*\|---", first)):
                errors.append(f"Q5 {cid}: {first[:60]!r}")
        answer = cq.final_answer(messages)
        if "**In the terminal**" in answer and "```" not in ck._section(answer, "In the terminal"):
            errors.append(f"{cid}: terminal section has no fence")
        if "**In studio**" in answer or "**In code**" in answer:
            errors.append(f"{cid}: unexpected section")
        if ck._code_repeats_terminal(answer):
            errors.append(f"{cid}: code repeats terminal")
    for text, ids in answers.items():
        if len(ids) > 1:
            errors.append(f"dup answer {ids}")
    for opening, ids in openings.items():
        if len(ids) > 1:
            errors.append(f"Q6 {opening!r} {ids}")
    for opening, ids in user5.items():
        if len(ids) > 1:
            errors.append(f"five {opening!r} {ids}")
    norms = []
    for row in rows:
        user = next(m["content"] for m in row["messages"] if m["role"] == "user")
        norms.append((row["id"], ck.normalize_q(user)))
    for i, (a, na) in enumerate(norms):
        for b, nb in norms[i + 1 :]:
            if na == nb:
                errors.append(f"dup q {a} {b}")
            elif len(na) >= 20 and ck.jaccard(na, nb) >= 0.92:
                errors.append(f"near {a} {b} {ck.jaccard(na, nb):.2f}")
    howto = 0
    for obj in rows:
        text = "\n".join((m.get("content") or "") for m in obj["messages"] if m.get("role") == "assistant")
        if "In studio" in text or "In the terminal" in text:
            howto += 1
    print(f"{name} howto={howto}/{len(rows)} = {howto / len(rows):.1%} errors={len(errors)}")
    for msg in errors:
        print("ERROR", msg)
    return errors


def main():
    s16 = json.loads((SLOTS / "shard_016.json").read_text(encoding="utf-8"))
    s17 = json.loads((SLOTS / "shard_017.json").read_text(encoding="utf-8"))
    missing = [s["id"] for s in s16 + s17 if s["id"] not in TEXTS]
    extra = sorted(set(TEXTS) - {s["id"] for s in s16 + s17})
    if missing or extra:
        raise SystemExit(f"missing={missing} extra={extra}")
    rows16 = build(s16, 0)
    rows17 = build(s17, 0)
    for name, rows in ("shard_016.jsonl", rows16), ("shard_017.jsonl", rows17):
        path = AUTHORED / name
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(f"wrote {path} {len(rows)}")
    try:
        errors = validate("shard_016.jsonl", rows16, s16) + validate("shard_017.jsonl", rows17, s17)
    except Exception as exc:
        print(f"validate failed: {exc}")
        return
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
