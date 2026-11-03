"""Serialize hand-written shard conversations. Not a template generator."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "ai-agent" / "training" / "tools"))
from check_knowledge import (  # noqa: E402
    FENCE,
    PARA_END_RE,
    SYSTEM_BEFORE_ENV,
    check_ips,
    check_messages,
    check_pskit_lines,
    check_sources,
    check_training_shape,
    cli_index,
    heading_index,
)

REMOVE = (
    "[docs/cli.md#pskit-remove]\n"
    "With `--keep-resources` the kept resources are taken out of the Terraform state first, so pskit no longer manages them: "
    "delete them in the cloud console when you no longer need them, or import them into another stack. "
    "The code-upload bucket is not kept. On Azure the storage account, Service Bus namespace and resource group that hold "
    "kept queues, containers or topics are kept as well. Supported on AWS, GCP, Azure, Alibaba, Tencent, Huawei and Oracle; "
    "the other providers create no buckets, queues or topics."
)
RES = (
    "[docs/cli.md#pskit-resources-onprem]\n"
    "Deleting a deployed resource runs `terraform destroy -target=...`. If it is still in `pskit.yml`, the next deploy creates "
    "it again, so remove it from `resources:` (or the trigger) first. Kept resources are deleted from their own small workspace "
    "in `.pskit/<provider>-<stage>/kept/`, which is removed when the last one is gone. Credentials are the same as for `pskit deploy`."
)


def env(provider, stage, mode, page):
    return SYSTEM_BEFORE_ENV + f"Environment: provider={provider} stage={stage} mode={mode} page={page}"


def search(query, excerpt, n):
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": f"call_{n:02d}",
                    "type": "function",
                    "function": {"name": "search_docs", "arguments": json.dumps({"query": query})},
                }
            ],
        },
        {"role": "tool", "tool_call_id": f"call_{n:02d}", "name": "search_docs", "content": excerpt},
    ]


def close_paragraphs(text: str) -> str:
    chunks = re.split(r"\n\s*\n", text)
    fixed = []
    for chunk in chunks:
        masked = FENCE.sub("CODE", chunk)
        blob = " ".join(ln.strip() for ln in masked.splitlines() if ln.strip())
        bad = (
            len(blob) > 80
            and not PARA_END_RE.search(blob)
            and not blob.startswith(("#", "|", "-", "*", "CODE"))
            and not blob.startswith(("Related:", "Sources:", "Options:"))
        )
        if bad:
            chunk = chunk.rstrip() + "\n."
        fixed.append(chunk)
    return "\n\n".join(fixed)


def row(sid, provider, stage, mode, page, user, answer, meta, tool=None):
    answer = close_paragraphs(answer)
    messages = [
        {"role": "system", "content": env(provider, stage, mode, page)},
        {"role": "user", "content": user},
    ]
    if tool:
        messages.extend(tool)
    messages.append({"role": "assistant", "content": answer})
    return {"id": sid, "messages": messages, "meta": meta}


def meta(card, grounding, persona, sources):
    return {
        "category": "k_cmd",
        "card_ids": [card],
        "grounding": grounding,
        "persona": persona,
        "sources": sources,
    }


SRC_MAIN = ["src/py_serverless_kit/cli/main.py"]
SRC_REMOVE = ["src/py_serverless_kit/cli/main.py", "docs/cli.md#pskit-remove"]
SRC_REMOVE_DOC = ["docs/cli.md#pskit-remove"]
SRC_RES = ["src/py_serverless_kit/cli/main.py", "docs/cli.md#pskit-resources-onprem"]
SRC_RES_DOC = ["docs/cli.md#pskit-resources-onprem"]
SRC_PSKIT = ["src/py_serverless_kit/cli/main.py", "docs/cli.md#pskit-resources-onprem"]

rows = []

rows.append(row(
    "k_cmd_0561", "onprem", "prod", "ask", "Overview",
    "Run pskit --version before prod rollout so we know the build.",
    "`--version` prints the version and exits. pskit is the CLI for writing Python functions once and deploying them to any cloud.\n\n"
    "**In the terminal**\n\n"
    "1. Confirm the build, then check terraform, CLIs and credentials.\n"
    "```\n"
    "pskit --version\n"
    "pskit doctor\n"
    "```\n"
    "2. Run locally, then deploy this stage.\n"
    "```\n"
    "pskit dev\n"
    "pskit deploy --stage prod\n"
    "```\n"
    "There is no studio button for the root command. After a deploy, `pskit dashboard --open` shows what landed.",
    meta("cmd-pskit", "closed", "ops_engineer", SRC_PSKIT),
))

rows.append(row(
    "k_cmd_0562", "aws", "dev", "auto", "Setup",
    "Will --keep-resources spare the code-upload bucket on this dev teardown?",
    "No. The code-upload bucket is not kept. `--keep-resources` only pulls the kept buckets, queues and topics out of Terraform state, so pskit no longer manages them. Delete those in the cloud console when you are done, or import them into another stack. AWS is supported. Example: `pskit remove -s dev --keep-resources`. [docs/cli.md#pskit-remove].",
    meta("cmd-remove", "search", "ops_engineer", SRC_REMOVE_DOC),
    search("keep-resources code-upload bucket", REMOVE, 1),
))

rows.append(row(
    "k_cmd_0563", "azure", "staging", "ask", "Functions",
    "Does --keep-resources also keep the storage account on Azure?",
    "Yes. On Azure the storage account, Service Bus namespace and resource group that hold kept queues, containers or topics are kept as well. The code-upload bucket is still not kept.\n\n"
    "**In studio**\n\n"
    "1. Deploy > Remove.\n\n"
    "**In the terminal**\n\n"
    "1. Keep managed buckets, queues and topics, and destroy only functions and triggers.\n"
    "```\n"
    "pskit remove -s staging --keep-resources\n"
    "```\n"
    "Those kept resources leave Terraform state. Delete them in the console later, or import them into another stack. [docs/cli.md#pskit-remove].",
    meta("cmd-remove", "search", "ops_engineer", SRC_REMOVE_DOC),
    search("Azure keep-resources storage account", REMOVE, 2),
))

rows.append(row(
    "k_cmd_0564", "gcp", "prod", "auto", "Workflows",
    "After --keep-resources, who owns queues if prod rollback needs them?",
    "pskit does not. Kept queues are taken out of Terraform state first, so you own them in the cloud console (or you import them into another stack).\n\n"
    "| Piece | What remains |\n"
    "| --- | --- |\n"
    "| Queues, buckets, topics you kept | Left in GCP, no longer managed |\n"
    "| Code-upload bucket | Not kept |\n"
    "| Functions and triggers | Destroyed |\n\n"
    "GCP is in the supported set. [docs/cli.md#pskit-remove].",
    meta("cmd-remove", "search", "ops_engineer", SRC_REMOVE_DOC),
    search("keep-resources terraform state ownership", REMOVE, 3),
))

rows.append(row(
    "k_cmd_0565", "alibaba", "dev", "ask", "Resources",
    "Where in studio does --keep-resources sit for Alibaba?",
    "In studio, the remove action is Deploy > Remove. Alibaba is supported, so kept buckets, queues and topics leave Terraform state and stay in the console until you delete or import them. The code-upload bucket is not kept.\n\n"
    "**In studio**\n\n"
    "1. Deploy > Remove.\n\n"
    "**In the terminal**\n\n"
    "1. Pass the flag so only functions and triggers are destroyed.\n"
    "```\n"
    "pskit remove -s dev --keep-resources\n"
    "```\n"
    "Studio still asks you to confirm. [docs/cli.md#pskit-remove].",
    meta("cmd-remove", "search", "ops_engineer", SRC_REMOVE_DOC),
    search("keep-resources Alibaba supported", REMOVE, 4),
))

rows.append(row(
    "k_cmd_0566", "tencent", "staging", "auto", "Cluster",
    "Once --keep-resources drops Terraform state, what breaks on the next change?",
    "pskit no longer manages the kept topics. Destroy still removes functions and triggers only. Tencent is supported. Delete the topics in the console when you no longer need them, or import them into another stack. The code-upload bucket is not kept. [docs/cli.md#pskit-remove].",
    meta("cmd-remove", "search", "ops_engineer", SRC_REMOVE_DOC),
    search("keep-resources no longer manages", REMOVE, 5),
))

rows.append(row(
    "k_cmd_0567", "huawei", "prod", "ask", "Load balancers",
    "Which flag, --yes or --keep-resources, should prod use when buckets must survive?",
    "`--keep-resources` is the flag that keeps managed buckets, queues and topics (and their data) and destroys only functions and triggers. `--yes` only skips the confirm.\n\n"
    "**In studio**\n\n"
    "1. Deploy > Remove.\n\n"
    "**In the terminal**\n\n"
    "1. Keep the data. Add `--yes` only when you already accept the destroy.\n"
    "```\n"
    "pskit remove -s prod --keep-resources\n"
    "```\n"
    "Without `--yes`, the prompt starts with Destroy and names the service, the stage and the provider.",
    meta("cmd-remove", "closed", "ops_engineer", SRC_REMOVE),
))

rows.append(row(
    "k_cmd_0568", "oracle", "dev", "auto", "Network map",
    "Is --keep-resources keeping the code-upload bucket on Oracle?",
    "The code-upload bucket is not kept on Oracle either. Oracle is supported, so the queues, buckets and topics you keep leave Terraform state for you to delete in the console or import into another stack. Command: `pskit remove -s dev --keep-resources`. [docs/cli.md#pskit-remove].",
    meta("cmd-remove", "search", "ops_engineer", SRC_REMOVE_DOC),
    search("Oracle code-upload bucket keep-resources", REMOVE, 6),
))

rows.append(row(
    "k_cmd_0569", "ibm", "staging", "ask", "Code",
    "Does IBM honor --keep-resources at all for queues?",
    "No. IBM is outside the supported set, and those other providers create no buckets, queues or topics, so the flag has nothing to retain. A remove still destroys the stage. Supported keep is AWS, GCP, Azure, Alibaba, Tencent, Huawei and Oracle. [docs/cli.md#pskit-remove].",
    meta("cmd-remove", "search", "ops_engineer", SRC_REMOVE_DOC),
    search("keep-resources unsupported providers", REMOVE, 7),
))

rows.append(row(
    "k_cmd_0570", "digitalocean", "prod", "auto", "Test",
    "Prod teardown with --keep-resources on DigitalOcean, anything kept?",
    "Nothing. DigitalOcean creates no buckets, queues or topics, so `--keep-resources` does not leave a data store behind on this prod remove. The flag applies on AWS, GCP, Azure, Alibaba, Tencent, Huawei and Oracle only. [docs/cli.md#pskit-remove].",
    meta("cmd-remove", "search", "ops_engineer", SRC_REMOVE_DOC),
    search("DigitalOcean keep-resources nothing to keep", REMOVE, 8),
))

rows.append(row(
    "k_cmd_0571", "cloudflare", "dev", "ask", "Deploy",
    "Cloudflare Deploy > Remove with --keep-resources, any buckets left?",
    "In studio, Deploy > Remove still asks you to confirm, but Cloudflare creates no buckets, queues or topics, so `--keep-resources` retains nothing.\n\n"
    "**In studio**\n\n"
    "1. Deploy > Remove.\n\n"
    "**In the terminal**\n\n"
    "1. Destroy the dev stage. The keep flag does not leave buckets behind here.\n"
    "```\n"
    "pskit remove -s dev --keep-resources\n"
    "```\n"
    "Supported keep is AWS, GCP, Azure, Alibaba, Tencent, Huawei and Oracle. [docs/cli.md#pskit-remove].",
    meta("cmd-remove", "search", "ops_engineer", SRC_REMOVE_DOC),
    search("Cloudflare keep-resources no buckets", REMOVE, 9),
))

rows.append(row(
    "k_cmd_0572", "onprem", "staging", "auto", "Logs",
    "On-prem logs and --keep-resources buckets, do we retain any?",
    "No. This on-prem host is not in the supported set, and those other providers create no buckets, queues or topics. `--keep-resources` does not leave cloud buckets behind. A remove still destroys the stage pskit manages. [docs/cli.md#pskit-remove].",
    meta("cmd-remove", "search", "ops_engineer", SRC_REMOVE_DOC),
    search("on-prem keep-resources no buckets", REMOVE, 10),
))

rows.append(row(
    "k_cmd_0573", "aws", "prod", "ask", "YAML",
    "aws_s3_bucket.b_uploads still in pskit.yml after a prod delete?",
    "Yes, the next prod deploy creates it again while that address is still under `resources:` or still wired as a trigger. Take it out of `pskit.yml` first. Deleting a deployed resource runs `terraform destroy -target=...`. Kept copies are deleted from `.pskit/aws-prod/kept/`, and that folder is removed when the last one is gone. Credentials match `pskit deploy`.\n\n"
    "**In code**\n\n"
    "1. Remove that one key from `resources:` and leave any other keys in place.\n"
    "```yaml\n"
    "resources: {}\n"
    "```\n"
    "An empty map drops every key under that block.\n\n"
    "**In the terminal**\n\n"
    "1. `pskit resources` lists or deletes buckets, queues and topics pskit created. Delete this address after the file change.\n"
    "```\n"
    "pskit resources delete aws_s3_bucket.b_uploads -s prod\n"
    "```\n"
    "[docs/cli.md#pskit-resources-onprem].",
    meta("cmd-resources", "search", "ops_engineer", SRC_RES_DOC),
    search("delete resource still in pskit.yml", RES, 11),
))

rows.append(row(
    "k_cmd_0574", "azure", "dev", "auto", "none",
    "pskit resources list -s dev shows buckets after remove, right?",
    "Yes. `pskit resources` lists or deletes the buckets, queues and topics pskit created. Use it after `pskit remove --keep-resources`.\n\n"
    "**In the terminal**\n\n"
    "1. List this stage. The group command itself has no options.\n"
    "```\n"
    "pskit resources list -s dev\n"
    "```\n"
    "2. Delete one address, or every resource that remove kept.\n"
    "```\n"
    "pskit resources delete aws_s3_bucket.b_uploads -s dev\n"
    "```\n"
    "```\n"
    "pskit resources delete --all-kept -s dev\n"
    "```\n"
    "There is no studio button for the group command.",
    meta("cmd-resources", "closed", "ops_engineer", SRC_RES),
))

rows.append(row(
    "k_cmd_0575", "gcp", "staging", "ask", "Overview",
    "Leave aws_s3_bucket.b_uploads inside pskit.yml and staging rebuilds it?",
    "Yes. If it is still in `pskit.yml`, the next deploy creates it again, so remove it from `resources:` or from the trigger first.\n\n"
    "**In code**\n\n"
    "1. Drop that key before you deploy again.\n"
    "```yaml\n"
    "resources: {}\n"
    "```\n\n"
    "**In the terminal**\n\n"
    "1. Delete the deployed address. This runs `terraform destroy -target=...`.\n"
    "```\n"
    "pskit resources delete aws_s3_bucket.b_uploads -s staging\n"
    "```\n"
    "Kept resources come out of `.pskit/gcp-staging/kept/`, which is removed when the last one is gone. Use the same credentials as `pskit deploy`. [docs/cli.md#pskit-resources-onprem].",
    meta("cmd-resources", "search", "ops_engineer", SRC_RES_DOC),
    search("pskit.yml recreate after delete", RES, 12),
))

rows.append(row(
    "k_cmd_0576", "alibaba", "prod", "auto", "Setup",
    "SQS leftover and --all-kept after we detached the queues?",
    "`--all-kept` is how you delete every bucket, queue and topic left by `pskit remove --keep-resources`. That is the cleanup for queues you detached, closer to deleting leftover SQS queues than to deleting the Lambda functions.\n\n"
    "**In the terminal**\n\n"
    "1. Remove the entries from `pskit.yml` first, or the next deploy creates them again.\n"
    "2. Then delete every kept resource.\n"
    "```\n"
    "pskit resources delete --all-kept -s prod\n"
    "```\n"
    "They are deleted from `.pskit/alibaba-prod/kept/`, and that workspace goes away when the last one is gone. Credentials are the same as `pskit deploy`. [docs/cli.md#pskit-resources-onprem].",
    meta("cmd-resources", "search", "aws_migrator", SRC_RES_DOC),
    search("all-kept delete kept resources", RES, 13),
))

rows.append(row(
    "k_cmd_0577", "tencent", "dev", "ask", "Functions",
    "aws_s3_bucket.b_uploads like an SQS URL, one delete target?",
    "Yes. That address is one target for `pskit resources delete`, the same idea as naming one queue instead of the whole stack. If it is still in `pskit.yml`, the next deploy creates it again, so remove it from `resources:` or the trigger first. The delete runs `terraform destroy -target=...`. [docs/cli.md#pskit-resources-onprem].",
    meta("cmd-resources", "search", "aws_migrator", SRC_RES_DOC),
    search("delete one resource address", RES, 14),
))

rows.append(row(
    "k_cmd_0578", "huawei", "staging", "auto", "Workflows",
    "Kept workspace and --all-kept cleanup, does the folder vanish?",
    "Yes, once the last kept resource is gone. Until then each one is deleted from `.pskit/huawei-staging/kept/`.\n\n"
    "**In the terminal**\n\n"
    "1. Clear every resource that `pskit remove --keep-resources` left behind.\n"
    "```\n"
    "pskit resources delete --all-kept -s staging\n"
    "```\n"
    "Take them out of `pskit.yml` first or the next deploy creates them again. Same credentials as `pskit deploy`. [docs/cli.md#pskit-resources-onprem].",
    meta("cmd-resources", "search", "aws_migrator", SRC_RES_DOC),
    search("kept workspace removed when empty", RES, 15),
))

rows.append(row(
    "k_cmd_0579", "oracle", "prod", "ask", "Resources",
    "--all-kept versus one address like aws_s3_bucket.b_uploads?",
    "Use one address for one bucket, queue or topic. Use `--all-kept` after `pskit remove --keep-resources` when every kept resource should go.\n\n"
    "| Goal | Command |\n"
    "| --- | --- |\n"
    "| One address | `pskit resources delete aws_s3_bucket.b_uploads -s prod` |\n"
    "| Every kept resource | `pskit resources delete --all-kept -s prod` |\n\n"
    "If the name is still in `pskit.yml`, the next deploy creates it again. Kept state lives in `.pskit/oracle-prod/kept/` until the last delete. [docs/cli.md#pskit-resources-onprem].",
    meta("cmd-resources", "search", "aws_migrator", SRC_RES_DOC),
    search("all-kept versus one address", RES, 16),
))

rows.append(row(
    "k_cmd_0580", "ibm", "dev", "auto", "Cluster",
    "List with -s dev before we drop kept queues?",
    "Yes, list first. `pskit resources` lists or deletes the buckets, queues and topics this service created, which is what you run after `pskit remove --keep-resources`.\n\n"
    "**In the terminal**\n\n"
    "1. List dev. Flags belong on the subcommand, not on the group.\n"
    "```\n"
    "pskit resources list -s dev\n"
    "```\n"
    "2. Delete every kept resource when the list is the set you mean to drop.\n"
    "```\n"
    "pskit resources delete --all-kept -s dev\n"
    "```\n"
    "Run that delete only after the list matches the queues you mean to drop.",
    meta("cmd-resources", "closed", "aws_migrator", SRC_RES),
))

rows.append(row(
    "k_cmd_0581", "digitalocean", "staging", "ask", "Load balancers",
    "pskit resources delete --all-kept then the next deploy, what returns?",
    "Anything still listed in `pskit.yml`. Remove it from `resources:` or from the trigger, or the next deploy creates it again.\n\n"
    "**In code**\n\n"
    "1. Delete the key you do not want recreated.\n"
    "```yaml\n"
    "resources: {}\n"
    "```\n\n"
    "**In the terminal**\n\n"
    "1. Delete every kept resource. That runs `terraform destroy -target=...`.\n"
    "```\n"
    "pskit resources delete --all-kept -s staging\n"
    "```\n"
    "The small workspace `.pskit/digitalocean-staging/kept/` is removed when the last one is gone. Credentials are the same as `pskit deploy`. [docs/cli.md#pskit-resources-onprem].",
    meta("cmd-resources", "search", "aws_migrator", SRC_RES_DOC),
    search("next deploy recreates resources", RES, 17),
))

rows.append(row(
    "k_cmd_0582", "cloudflare", "prod", "auto", "Network map",
    "Next deploy and aws_s3_bucket.b_uploads address, will it rebuild?",
    "Yes if that resource is still in `pskit.yml`. Remove it from `resources:` or the trigger before the delete, or the next deploy creates it again. The delete is `terraform destroy -target=...`. Kept resources are removed from `.pskit/cloudflare-prod/kept/`, and the folder goes away with the last one. [docs/cli.md#pskit-resources-onprem].",
    meta("cmd-resources", "search", "aws_migrator", SRC_RES_DOC),
    search("rebuild resource if still in yaml", RES, 18),
))

rows.append(row(
    "k_cmd_0583", "onprem", "dev", "ask", "Code",
    "On-prem --all-kept and pskit.yml resources, which do I edit first?",
    "Edit `pskit.yml` first. If the resource is still under `resources:` or still used as a trigger, the next deploy creates it again.\n\n"
    "**In code**\n\n"
    "1. Remove the on-prem entry you are dropping.\n"
    "```yaml\n"
    "resources: {}\n"
    "```\n\n"
    "**In the terminal**\n\n"
    "1. Then delete every kept resource from the kept workspace.\n"
    "```\n"
    "pskit resources delete --all-kept -s dev\n"
    "```\n"
    "That workspace is `.pskit/onprem-dev/kept/`, and it is removed when the last one is gone. Credentials match `pskit deploy`. The delete runs `terraform destroy -target=...`. [docs/cli.md#pskit-resources-onprem].",
    meta("cmd-resources", "search", "aws_migrator", SRC_RES_DOC),
    search("edit pskit.yml before resource delete", RES, 19),
))

rows.append(row(
    "k_cmd_0584", "aws", "staging", "auto", "Test",
    "Like a health check, --json for one reachable queue?",
    "`--json` prints the reachability check as JSON. The command checks that KEY is reachable (connection, depth).\n\n"
    "**In the terminal**\n\n"
    "1. Check one resource on staging.\n"
    "```\n"
    "pskit resources check jobs -s staging --json\n"
    "```\n"
    "There is no studio button. The callback does not ask you to confirm.",
    meta("cmd-resources-check", "closed", "aws_migrator", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0585", "azure", "prod", "ask", "Deploy",
    "Which flag prints JSON, --json or another switch?",
    "`--json` is the flag that prints the check as JSON.\n\n"
    "**In the terminal**\n\n"
    "1. Check KEY on prod. `-s` selects the stage.\n"
    "```\n"
    "pskit resources check jobs -s prod --json\n"
    "```\n"
    "Purpose: check that a resource is reachable (connection, depth). No studio button, and no confirm prompt.",
    meta("cmd-resources-check", "closed", "aws_migrator", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0586", "gcp", "dev", "auto", "Logs",
    "main.py resources check skips click.confirm, is that required?",
    "Yes. The `pskit resources check` callback in `src/py_serverless_kit/cli/main.py` has no `click.confirm`, and it does not call deploy, plan or remove. Keep it that way. The command only checks that KEY is reachable (connection, depth). `--json` prints JSON.",
    meta("cmd-resources-check", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0587", "alibaba", "staging", "ask", "YAML",
    "pskit.yml via -c and --json, both on one check?",
    "Yes. `-c` points at the config file and defaults to `pskit.yml`. `--json` prints the result as JSON.\n\n"
    "**In the terminal**\n\n"
    "1. Check KEY with both flags.\n"
    "```\n"
    "pskit resources check jobs -c pskit.yml -s staging --json\n"
    "```\n"
    "You do not edit `pskit.yml` to run the check. There is no studio path.",
    meta("cmd-resources-check", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0588", "tencent", "prod", "auto", "none",
    "Contributor note: --server local versus the last deploy target?",
    "`--server local` checks from this machine. Omit it and the default is the server the stage was last deployed to. Saved SSH servers come from `pskit resources onprem servers list`. The callback in `src/py_serverless_kit/cli/main.py` must stay without `click.confirm`.",
    meta("cmd-resources-check", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0589", "huawei", "dev", "ask", "Overview",
    "--cluster flag on resources check, what must stay true?",
    "`--cluster` runs the check on that scaling cluster instead of one server. The default is `options.cluster`, else where the stage was last deployed. Do not add `click.confirm` or a deploy, plan or remove call in `src/py_serverless_kit/cli/main.py`.\n\n"
    "**In the terminal**\n\n"
    "1. Name the cluster and print JSON.\n"
    "```\n"
    "pskit resources check jobs --cluster prod -s dev --json\n"
    "```",
    meta("cmd-resources-check", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0590", "oracle", "staging", "auto", "Setup",
    "Where is --verbose wired for resources check?",
    "`-v` / `--verbose` is the option on `pskit resources check` in `src/py_serverless_kit/cli/main.py`. It shows tracebacks on errors and defaults off. It must not add a confirm prompt. The check is still reachability: connection and depth.",
    meta("cmd-resources-check", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0591", "ibm", "prod", "ask", "Functions",
    "IBM prod check uses -s, or does -p matter more?",
    "Pass whichever override you need. `-s prod` selects the stage. `-p ibm` overrides `provider.name`. Neither one replaces the other.\n\n"
    "**In the terminal**\n\n"
    "1. Check KEY with both overrides.\n"
    "```\n"
    "pskit resources check jobs -p ibm -s prod --json\n"
    "```",
    meta("cmd-resources-check", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0592", "digitalocean", "dev", "auto", "Workflows",
    "Keep --json output stable in the check callback?",
    "`--json` only switches the print format. A change in `src/py_serverless_kit/cli/main.py` must leave the callback free of `click.confirm`, deploy, plan and remove. Reachability is still connection and depth for KEY.",
    meta("cmd-resources-check", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0593", "cloudflare", "staging", "ask", "Resources",
    "--provider cloudflare on resources check, which form?",
    "`-p` and `--provider` are the same option. They override `provider.name` for this run.\n\n"
    "**In the terminal**\n\n"
    "1. Check one resource on staging.\n"
    "```\n"
    "pskit resources check jobs -p cloudflare -s staging\n"
    "```\n"
    "Add `--json` when you want JSON. No studio button for this command.",
    meta("cmd-resources-check", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0594", "onprem", "prod", "auto", "Cluster",
    "--server local for resources check on this prod host?",
    "Yes. `--server local` means this machine. Leave it off to use the server the stage was last deployed to.\n\n"
    "**In the terminal**\n\n"
    "1. Check KEY on the local on-prem host.\n"
    "```\n"
    "pskit resources check jobs --server local -s prod\n"
    "```\n"
    "`--cluster` is the other on-prem switch (`pskit cluster list`). The command does not ask you to confirm.",
    meta("cmd-resources-check", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0595", "aws", "dev", "ask", "Load balancers",
    "resources clear and -y/--yes in main.py, what must not change?",
    "Keep the confirm, and keep `-y` / `--yes` as the skip. The prompt must still start `Delete all data of {key} on the on-prem host?`. The callback is `pskit resources clear` in `src/py_serverless_kit/cli/main.py`. It deletes the data of a built-in on-prem queue, bucket or topic, and KEY stays required.",
    meta("cmd-resources-clear", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0596", "azure", "staging", "auto", "Network map",
    "resources clear -y skips click.confirm, show the real command?",
    "Yes. `-y` / `--yes` means do not ask for confirmation. Without it, `click.confirm` runs and the prompt starts `Delete all data of {key} on the on-prem host?`.\n\n"
    "**In the terminal**\n\n"
    "1. Delete the data of KEY on the on-prem host and skip the prompt.\n"
    "```\n"
    "pskit resources clear jobs -s staging --yes\n"
    "```\n"
    "There is no studio button. This is only for a built-in on-prem queue, bucket or topic.",
    meta("cmd-resources-clear", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0597", "gcp", "prod", "ask", "Code",
    "Does --yes skip the clear prompt for KEY?",
    "Yes. `--yes` (short `-y`) skips the confirm for `pskit resources clear`. Otherwise the prompt starts `Delete all data of {key} on the on-prem host?`. KEY is required. The command deletes the data of a built-in on-prem queue, bucket or topic.",
    meta("cmd-resources-clear", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0598", "alibaba", "dev", "auto", "Test",
    "Built-in queue clear needs --yes when we must not prompt?",
    "Yes. `--yes` skips the prompt on that on-prem data wipe.\n\n"
    "**In the terminal**\n\n"
    "1. Delete the data of KEY without asking.\n"
    "```\n"
    "pskit resources clear jobs --yes -s dev\n"
    "```\n"
    "Without the flag the prompt starts `Delete all data of {key} on the on-prem host?`. No studio button. This does not clear a cloud queue.",
    meta("cmd-resources-clear", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0599", "tencent", "staging", "ask", "Deploy",
    "main.py confirm for resources clear, what text must stay?",
    "Keep the prompt starting `Delete all data of {key} on the on-prem host?` on the `pskit resources clear` callback in `src/py_serverless_kit/cli/main.py`. `-y` / `--yes` still means do not ask. KEY stays required. The command still deletes the data of a built-in on-prem queue, bucket or topic.",
    meta("cmd-resources-clear", "closed", "contributor", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0600", "huawei", "prod", "auto", "Logs",
    "--cluster with resources clear KEY, same default as deploy?",
    "Yes. `--cluster` uses that scaling cluster. The default is `options.cluster`, else where the stage was last deployed. `--server` picks a saved SSH server, or `local` for this machine.\n\n"
    "**In the terminal**\n\n"
    "1. Clear the on-prem data on the cluster and skip the prompt.\n"
    "```\n"
    "pskit resources clear jobs --cluster prod -s prod --yes\n"
    "```\n"
    "The callback lives in `src/py_serverless_kit/cli/main.py` and still confirms unless `--yes` is set.",
    meta("cmd-resources-clear", "closed", "contributor", SRC_MAIN),
))

# shard 015
rows.append(row(
    "k_cmd_0601", "oracle", "dev", "ask", "YAML",
    "pskit resources clear jobs --yes, is that the whole command?",
    "Yes. That deletes the data of the built-in on-prem resource named jobs, and `--yes` skips the confirm.\n\n"
    "**In the terminal**\n\n"
    "1. Clear jobs. `-c` defaults to `pskit.yml`, so you can omit it.\n"
    "```\n"
    "pskit resources clear jobs -s dev --yes\n"
    "```\n"
    "Without `--yes` the prompt starts `Delete all data of {key} on the on-prem host?`. No studio button.",
    meta("cmd-resources-clear", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0602", "ibm", "staging", "auto", "none",
    "What is --yes on resources clear for?",
    "`--yes` (also `-y`) means do not ask for confirmation. The prompt it skips starts `Delete all data of {key} on the on-prem host?`. `pskit resources clear` deletes the data of a built-in on-prem queue, bucket or topic. KEY is required.",
    meta("cmd-resources-clear", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0603", "digitalocean", "prod", "ask", "Overview",
    "pskit.yml default and resources clear, do I pass -c?",
    "Only when the file is not `pskit.yml`. `-c` / `--config` defaults to that file.\n\n"
    "**In the terminal**\n\n"
    "1. Clear KEY on prod and skip the prompt.\n"
    "```\n"
    "pskit resources clear jobs -s prod --yes\n"
    "```\n"
    "This wipes data of a built-in on-prem queue, bucket or topic. It is not a cloud-bucket delete. No studio button.",
    meta("cmd-resources-clear", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0604", "cloudflare", "dev", "auto", "Setup",
    "--server local when I clear a queue on this machine?",
    "Use `--server local` when the queue is on this machine. Leave the flag off and clear uses the server the stage was last deployed to.\n\n"
    "**In the terminal**\n\n"
    "1. Delete the data on the local host. You are asked to confirm unless you add `--yes`.\n"
    "```\n"
    "pskit resources clear jobs --server local -s dev\n"
    "```\n"
    "The prompt starts `Delete all data of {key} on the on-prem host?`.",
    meta("cmd-resources-clear", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0605", "onprem", "staging", "ask", "Functions",
    "Clear jobs data with --yes on the staging host?",
    "Yes. `--yes` skips the question. The command deletes the data of that built-in on-prem queue, bucket or topic.\n\n"
    "**In the terminal**\n\n"
    "1. Clear jobs on staging.\n"
    "```\n"
    "pskit resources clear jobs -s staging --yes\n"
    "```\n"
    "KEY is the resource name. There is no studio button.",
    meta("cmd-resources-clear", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0606", "aws", "prod", "auto", "Workflows",
    "pskit resources data jobs --offset, how does the next page work?",
    "`--offset` skips that many items. The page size defaults to 20. `-n` / `--limit` changes it, up to 500.\n\n"
    "**In the terminal**\n\n"
    "1. Open the first page of the on-prem queue, topic or bucket.\n"
    "```\n"
    "pskit resources data jobs\n"
    "```\n"
    "2. Skip 20 and take the next 20.\n"
    "```\n"
    "pskit resources data jobs --offset 20 -n 20\n"
    "```\n"
    "That second command is the next page.\n\n"
    "**In studio**\n\n"
    "1. Resources > Data.",
    meta("cmd-resources-data", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0607", "azure", "dev", "ask", "Resources",
    "Where in studio is Resources > Data for a queue?",
    "In studio, open Resources > Data. That browses what an on-prem queue, topic or bucket holds.\n\n"
    "**In studio**\n\n"
    "1. Resources > Data.\n\n"
    "**In the terminal**\n\n"
    "1. Browse KEY. `--json` prints the page as JSON.\n"
    "```\n"
    "pskit resources data jobs -s dev --json\n"
    "```",
    meta("cmd-resources-data", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0608", "gcp", "staging", "auto", "Cluster",
    "Same page with --offset 20 and -n 20 still?",
    "Yes, unless you set `-n`. `--offset 20` skips 20 items. `-n` / `--limit` defaults to 20 and the max is 500.\n\n"
    "**In the terminal**\n\n"
    "1. Use the same page size as the help example.\n"
    "```\n"
    "pskit resources data jobs --offset 20 -n 20\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Data.",
    meta("cmd-resources-data", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0609", "alibaba", "prod", "ask", "Load balancers",
    "--prefix in/ on the uploads bucket, only those keys?",
    "Yes. `--prefix` is for buckets, and it keeps only keys below that prefix.\n\n"
    "**In the terminal**\n\n"
    "1. Browse objects under `in/`.\n"
    "```\n"
    "pskit resources data uploads --prefix in/\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Data.",
    meta("cmd-resources-data", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0610", "tencent", "dev", "auto", "Network map",
    "--limit 20 versus --offset 0, which one pages?",
    "Both. `--offset` skips items and defaults to 0. `-n` / `--limit` is how many items to show, default 20, max 500.\n\n"
    "| Flag | Default | Role |\n"
    "| --- | --- | --- |\n"
    "| `--offset` | 0 | Skip this many items |\n"
    "| `-n`, `--limit` | 20 | Items per page |\n\n"
    "Example from the help: `pskit resources data jobs --offset 20 -n 20`.",
    meta("cmd-resources-data", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0611", "huawei", "staging", "ask", "Code",
    "--json for resources data jobs, do the pages stay?",
    "Yes. `--json` prints that page as JSON. `--offset` and `-n` still choose the window.\n\n"
    "**In the terminal**\n\n"
    "1. Print one page.\n"
    "```\n"
    "pskit resources data jobs -s staging --json -n 20\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Data.",
    meta("cmd-resources-data", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0612", "oracle", "prod", "auto", "Test",
    "Browse jobs with -n 20 on the prod host?",
    "`-n 20` asks for 20 items, which is also the default. The command browses an on-prem queue, topic or bucket.\n\n"
    "**In the terminal**\n\n"
    "1. Read one page on prod.\n"
    "```\n"
    "pskit resources data jobs -n 20 -s prod\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Data.",
    meta("cmd-resources-data", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0613", "ibm", "dev", "ask", "Deploy",
    "pskit.yml and resources data --prefix, do I change the file?",
    "No. `--prefix` only filters a bucket browse to keys below that prefix. `-c` selects another config when you are not using `pskit.yml`. You do not edit the file to look at the data. Studio path for the same browse is Resources > Data.",
    meta("cmd-resources-data", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0614", "digitalocean", "staging", "auto", "Logs",
    "--server local to read jobs data from this machine?",
    "Yes. `--server local` reads from this machine. The default is the server the stage was last deployed to.\n\n"
    "**In the terminal**\n\n"
    "1. Browse the on-prem resource locally.\n"
    "```\n"
    "pskit resources data jobs --server local -s staging\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Data.",
    meta("cmd-resources-data", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0615", "cloudflare", "prod", "ask", "YAML",
    "Resources > Data page and --prefix in/, same filter?",
    "Yes. `--prefix in/` is the terminal filter for bucket keys below `in/`. The studio path is Resources > Data.\n\n"
    "**In studio**\n\n"
    "1. Resources > Data.\n\n"
    "**In the terminal**\n\n"
    "1. Apply the prefix on prod.\n"
    "```\n"
    "pskit resources data uploads --prefix in/ -s prod\n"
    "```",
    meta("cmd-resources-data", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0616", "onprem", "dev", "auto", "none",
    "On-prem jobs queue and --offset, can I skip the first items?",
    "Yes. `--offset` skips that many items. The default is 0, and `-n` sets the page size (default 20, max 500).\n\n"
    "**In the terminal**\n\n"
    "1. Skip the first 20 items on this on-prem queue, topic or bucket.\n"
    "```\n"
    "pskit resources data jobs --offset 20 -n 20\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Data.",
    meta("cmd-resources-data", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0617", "aws", "staging", "ask", "Overview",
    "pskit resources delete --all-kept please, after we kept them?",
    "`--all-kept` deletes every resource kept by `pskit remove --keep-resources`, including their data. You still confirm unless you pass `--yes`.\n\n"
    "**In studio**\n\n"
    "1. Resources > Delete.\n\n"
    "**In the terminal**\n\n"
    "1. Delete every kept bucket, queue and topic on staging.\n"
    "```\n"
    "pskit resources delete --all-kept -s staging\n"
    "```\n"
    "The prompt starts with Permanently delete, then the count and the addresses.",
    meta("cmd-resources-delete", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0618", "azure", "prod", "auto", "Setup",
    "--yes with resources delete addresses, skip the question?",
    "Yes. `--yes` means do not ask for confirmation.\n\n"
    "**In the terminal**\n\n"
    "1. Delete one address on prod without a prompt.\n"
    "```\n"
    "pskit resources delete aws_s3_bucket.b_uploads -s prod --yes\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Delete.",
    meta("cmd-resources-delete", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0619", "gcp", "dev", "ask", "Functions",
    "Which screen has Resources > Delete for one bucket?",
    "In studio, use Resources > Delete for one bucket, queue or topic.\n\n"
    "**In studio**\n\n"
    "1. Resources > Delete.\n\n"
    "**In the terminal**\n\n"
    "1. Pass the address. `--all-kept` is only when you want every resource left by `pskit remove --keep-resources`.\n"
    "```\n"
    "pskit resources delete aws_s3_bucket.b_uploads -s dev\n"
    "```\n"
    "Leave `--yes` off when you want the confirm.",
    meta("cmd-resources-delete", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0620", "alibaba", "staging", "auto", "Workflows",
    "aws_s3_bucket.b_uploads and -s staging, one shot delete?",
    "Yes. Pass that address and `-s staging`. The command deletes buckets, queues or topics by address, and their data.\n\n"
    "**In the terminal**\n\n"
    "1. Delete that one address. Omit `--yes` if you want the confirm.\n"
    "```\n"
    "pskit resources delete aws_s3_bucket.b_uploads -s staging\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Delete.",
    meta("cmd-resources-delete", "closed", "beginner", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0621", "tencent", "prod", "ask", "Resources",
    "I want Resources > Delete but I not sure the command.",
    "The button is Resources > Delete. The command is `pskit resources delete`, and it removes buckets, queues or topics by address, plus their data.\n\n"
    "**In studio**\n\n"
    "1. Resources > Delete.\n\n"
    "**In the terminal**\n\n"
    "1. Delete every resource kept by `pskit remove --keep-resources`.\n"
    "```\n"
    "pskit resources delete --all-kept -s prod\n"
    "```\n"
    "It asks you to confirm unless you pass `--yes`.",
    meta("cmd-resources-delete", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0622", "huawei", "dev", "auto", "Cluster",
    "--all-kept flag, it delete every kept thing?",
    "Yes. `--all-kept` deletes every resource kept by `pskit remove --keep-resources`, and their data. Without `--yes` the prompt starts with Permanently delete and lists the addresses. Pass addresses instead when you want only some of them.",
    meta("cmd-resources-delete", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0623", "oracle", "staging", "ask", "Load balancers",
    "Permanently delete prompt and --yes, I can skip the ask?",
    "Yes. `--yes` means do not ask. Without it the prompt starts with Permanently delete, then the count and the addresses.\n\n"
    "**In the terminal**\n\n"
    "1. Delete every kept resource and skip the prompt.\n"
    "```\n"
    "pskit resources delete --all-kept -s staging --yes\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Delete.",
    meta("cmd-resources-delete", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0624", "ibm", "prod", "auto", "Network map",
    "-s prod with resources delete, this the right stage?",
    "Yes. `-s prod` is the same as `--stage prod`. Add one or more addresses, or `--all-kept` for everything `pskit remove --keep-resources` left behind. `--yes` skips the confirm.",
    meta("cmd-resources-delete", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0625", "digitalocean", "dev", "ask", "Code",
    "One address aws_s3_bucket.b_uploads without --all-kept is ok?",
    "Yes. `--all-kept` is optional. One address deletes just that bucket, queue or topic, and its data.\n\n"
    "**In the terminal**\n\n"
    "1. Delete that address on dev.\n"
    "```\n"
    "pskit resources delete aws_s3_bucket.b_uploads -s dev\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Delete.",
    meta("cmd-resources-delete", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0626", "cloudflare", "staging", "auto", "Test",
    "--yes so it not ask me, that the skip flag?",
    "Yes. `--yes` (short `-y`) means do not ask for confirmation. The prompt you skip starts with Permanently delete and names every address. Use it on `pskit resources delete`.",
    meta("cmd-resources-delete", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0627", "onprem", "prod", "ask", "Deploy",
    "On-prem --all-kept from Deploy page, or somewhere else?",
    "Not from Deploy. Deploy removes the whole stage. Deleting kept buckets, queues or topics by address is a different command.\n\n"
    "**In studio**\n\n"
    "1. Resources > Delete.\n\n"
    "**In the terminal**\n\n"
    "1. Delete every resource kept by `pskit remove --keep-resources` on this on-prem prod stage.\n"
    "```\n"
    "pskit resources delete --all-kept -s prod\n"
    "```\n"
    "Add `--server local` if the data is on this machine. The prompt starts with Permanently delete unless you pass `--yes`.",
    meta("cmd-resources-delete", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0628", "aws", "dev", "auto", "Logs",
    "Which button, Resources > Load or the terminal list?",
    "In studio, press Load. The terminal command for the same list is `pskit resources list`.\n\n"
    "**In studio**\n\n"
    "1. Resources > Load.\n\n"
    "**In the terminal**\n\n"
    "1. List deployed and kept buckets, queues and topics. `--json` prints JSON.\n"
    "```\n"
    "pskit resources list -s dev --json\n"
    "```",
    meta("cmd-resources-list", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0629", "azure", "staging", "ask", "YAML",
    "--json on resources list please, for a small script?",
    "`--json` prints the deployed and kept buckets, queues and topics as JSON.\n\n"
    "**In the terminal**\n\n"
    "1. List staging as JSON.\n"
    "```\n"
    "pskit resources list -s staging --json\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Load.",
    meta("cmd-resources-list", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0630", "gcp", "prod", "auto", "none",
    "-s prod for resources list, that show kept too?",
    "Yes. The command lists deployed and kept buckets, queues and topics. `-s prod` selects prod.\n\n"
    "**In the terminal**\n\n"
    "1. List prod.\n"
    "```\n"
    "pskit resources list -s prod\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Load.",
    meta("cmd-resources-list", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0631", "alibaba", "dev", "ask", "Overview",
    "Show me kept buckets with --json, which flags matter?",
    "`--json` is the print switch. These are the flags on `pskit resources list`.\n\n"
    "| Flag | What it does |\n"
    "| --- | --- |\n"
    "| `--json` | Print JSON |\n"
    "| `-s`, `--stage` | Stage, such as dev |\n"
    "| `-p`, `--provider` | Override provider.name |\n"
    "| `-c`, `--config` | Config file, default pskit.yml |\n"
    "| `-v`, `--verbose` | Tracebacks on errors |\n\n"
    "Example: `pskit resources list -s dev --json`. The studio control is Resources > Load, not a second command.",
    meta("cmd-resources-list", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0632", "tencent", "staging", "auto", "Setup",
    "pskit resources list -s staging give the names back?",
    "Yes. It lists deployed and kept buckets, queues and topics for that stage.\n\n"
    "**In the terminal**\n\n"
    "1. List staging.\n"
    "```\n"
    "pskit resources list -s staging\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Load.",
    meta("cmd-resources-list", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0633", "huawei", "prod", "ask", "Functions",
    "--provider huawei on resources list, I add -p?",
    "Yes. `-p huawei` and `--provider huawei` are the same option. They override `provider.name`.\n\n"
    "**In the terminal**\n\n"
    "1. List prod for that provider.\n"
    "```\n"
    "pskit resources list -p huawei -s prod\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Load.",
    meta("cmd-resources-list", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0634", "oracle", "dev", "auto", "Workflows",
    "--verbose when list is empty, it show a traceback?",
    "Only when something errors. `-v` / `--verbose` shows tracebacks and defaults to off. An empty result is still just the list of deployed and kept buckets, queues and topics. Add `--json` if you want that list as JSON.",
    meta("cmd-resources-list", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0635", "ibm", "staging", "ask", "Resources",
    "Resources > Load button and --json, they the same list?",
    "In studio, Resources > Load is that list. `--json` is only the terminal print format for the same deployed and kept buckets, queues and topics.\n\n"
    "**In studio**\n\n"
    "1. Resources > Load.\n\n"
    "**In the terminal**\n\n"
    "1. Print JSON for staging.\n"
    "```\n"
    "pskit resources list --json -s staging\n"
    "```",
    meta("cmd-resources-list", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0636", "digitalocean", "prod", "auto", "Cluster",
    "-c pskit.yml for resources list, that the default file?",
    "Yes. `-c` / `--config` defaults to `pskit.yml`. Pass `-c` only for a different file.\n\n"
    "**In the terminal**\n\n"
    "1. List prod from that file.\n"
    "```\n"
    "pskit resources list -c pskit.yml -s prod\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Load.",
    meta("cmd-resources-list", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0637", "cloudflare", "dev", "ask", "Load balancers",
    "--region flag on resources list, when I need it?",
    "`-r` / `--region` overrides `provider.region` for this run. Use it when the region in the config is not the one you want to read. The list is still deployed and kept buckets, queues and topics. Example: `pskit resources list -s dev -r region-1`.",
    meta("cmd-resources-list", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0638", "onprem", "staging", "auto", "Network map",
    "--server local and resources list, for this machine only?",
    "`--server local` lists from this machine. The default is the server the stage was last deployed to.\n\n"
    "**In the terminal**\n\n"
    "1. List deployed and kept buckets, queues and topics on this machine.\n"
    "```\n"
    "pskit resources list --server local -s staging\n"
    "```\n\n"
    "**In studio**\n\n"
    "1. Resources > Load.",
    meta("cmd-resources-list", "closed", "informal_non_native", SRC_MAIN),
))

rows.append(row(
    "k_cmd_0639", "aws", "prod", "ask", "Code",
    "jobs with --save still in pskit.yml, next deploy make it again?",
    "Yes if jobs is still under `resources:` or still used as a trigger. Remove that entry first, or the next deploy creates it again. Deleting a deployed resource runs `terraform destroy -target=...`.\n\n"
    "**In code**\n\n"
    "1. Drop the jobs key from `resources:` before the next deploy.\n"
    "```yaml\n"
    "resources: {}\n"
    "```\n\n"
    "**In the terminal**\n\n"
    "1. The on-prem create example that includes `--save` is how that service is added. It does not delete anything.\n"
    "```\n"
    "pskit resources onprem create jobs --service redis --attach worker --save\n"
    "```\n"
    "Kept resources are deleted from `.pskit/onprem-prod/kept/`, and that folder is removed when the last one is gone. Credentials are the same as `pskit deploy`. [docs/cli.md#pskit-resources-onprem].",
    meta("cmd-resources-onprem", "search", "informal_non_native", SRC_RES_DOC),
    search("delete on-prem resource still in pskit.yml", RES, 20),
))

rows.append(row(
    "k_cmd_0640", "azure", "dev", "auto", "Test",
    "orders-db --service postgres and pskit.yml, I delete the block first?",
    "Yes. Remove orders-db from `resources:` or from the trigger before you delete the deployed resource. If it is still in `pskit.yml`, the next deploy creates it again.\n\n"
    "**In code**\n\n"
    "1. Take the block out first.\n"
    "```yaml\n"
    "resources: {}\n"
    "```\n\n"
    "**In the terminal**\n\n"
    "1. This is the create command for that on-prem Postgres service, not the delete.\n"
    "```\n"
    "pskit resources onprem create orders-db --service postgres --ssh deploy@192.0.2.10 --pem key.pem --save\n"
    "```\n"
    "A delete runs `terraform destroy -target=...`. Kept resources live in `.pskit/onprem-dev/kept/` until the last one is gone. Credentials match `pskit deploy`. [docs/cli.md#pskit-resources-onprem].",
    meta("cmd-resources-onprem", "search", "informal_non_native", SRC_RES_DOC),
    search("on-prem postgres delete and pskit.yml", RES, 21),
))


def main():
    out_dir = ROOT / "ai-agent" / "training" / "data" / "authored"
    shard14 = [r for r in rows if r["id"] <= "k_cmd_0600"]
    shard15 = [r for r in rows if r["id"] >= "k_cmd_0601"]
    # ids are zero-padded so string compare works inside this range
    assert [r["id"] for r in shard14] == [f"k_cmd_{i:04d}" for i in range(561, 601)], [r["id"] for r in shard14]
    assert [r["id"] for r in shard15] == [f"k_cmd_{i:04d}" for i in range(601, 641)]
    for name, group in (("shard_014.jsonl", shard14), ("shard_015.jsonl", shard15)):
        path = out_dir / name
        text = "\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in group) + "\n"
        path.write_bytes(text.encode("utf-8"))
        print(f"wrote {path.name} records={len(group)} bytes={path.stat().st_size}")

    slots = {}
    for name in ("shard_014.json", "shard_015.json"):
        for slot in json.loads((ROOT / "ai-agent" / "training" / "data" / "slots" / name).read_text(encoding="utf-8")):
            slots[slot["id"]] = slot
    errors = []
    known = cli_index()
    headings = heading_index()
    for rec in rows:
        sid = rec["id"]
        slot = slots[sid]
        where = sid
        check_messages(rec["messages"], where, errors)
        blob = "\n".join(m.get("content") or "" for m in rec["messages"])
        check_pskit_lines(blob, known, where, errors)
        check_sources(rec["meta"]["sources"], headings, where, errors)
        check_ips(blob, where, errors)
        if rec["meta"] != {
            "category": slot["category"],
            "card_ids": slot["card_ids"],
            "grounding": slot["grounding"],
            "persona": slot["persona"],
            "sources": slot["sources"],
        }:
            errors.append(f"{sid}: meta mismatch")
        env_line = rec["messages"][0]["content"].splitlines()[-1]
        expect = f"Environment: provider={slot['provider']} stage={slot['stage']} mode={slot['mode']} page={slot['page']}"
        if env_line != expect:
            errors.append(f"{sid}: env {env_line!r}")
        if slot["grounding"] == "search":
            tool = next(m for m in rec["messages"] if m["role"] == "tool")
            if tool["content"] != slot["excerpt"]:
                errors.append(f"{sid}: excerpt mismatch")
            if len(tool["content"]) < 300:
                errors.append(f"{sid}: excerpt short")
        else:
            if any(m["role"] == "tool" or m.get("tool_calls") for m in rec["messages"]):
                errors.append(f"{sid}: unexpected tool")
        user = next(m["content"] for m in rec["messages"] if m["role"] == "user")
        five = " ".join(user.split()[:5]).lower()
        if user.split()[:1] and user.lower().startswith(("can you explain", "how do i", "what does the", "i just opened", "on call for")):
            errors.append(f"{sid}: bad opening")
        rec["_five"] = five
    check_training_shape(rows, errors)
    fives = {}
    for rec in rows:
        fives.setdefault(rec["_five"], []).append(rec["id"])
    for five, ids in fives.items():
        if len(ids) > 1:
            errors.append(f"dup five {five!r} {ids}")
    for label, group in (("014", rows[:40]), ("015", rows[40:])):
        howto = 0
        for rec in group:
            text = "\n".join(m.get("content") or "" for m in rec["messages"] if m["role"] == "assistant")
            if "In studio" in text or "In the terminal" in text:
                howto += 1
        print(f"shard {label} how-to {howto}/{len(group)}")
        if howto * 2 < len(group):
            errors.append(f"shard {label} how-to under half")
    print(f"errors={len(errors)}")
    for msg in errors:
        print("ERROR", msg)
    return 1 if errors else 0



if __name__ == "__main__":
    raise SystemExit(main())


