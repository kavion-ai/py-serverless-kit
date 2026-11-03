"""``pskit`` command line interface."""

from __future__ import annotations

import functools
import json
import os
import sys
import traceback
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import click

from .._version import __version__
from ..config.loader import ConfigError
from ..config.schema import NODE_RUNTIMES, PROVIDERS, PYTHON_RUNTIMES

COMMON_ERRORS: tuple = ()


def _errors() -> tuple:
    global COMMON_ERRORS
    if not COMMON_ERRORS:
        from ..core.deployer import DeployError
        from ..packaging.builder import BuildError
        from ..providers.base import ProviderError
        from ..providers.schedule import ScheduleError
        from ..terraform.runner import TerraformError

        COMMON_ERRORS = (ConfigError, DeployError, BuildError, ProviderError, ScheduleError, TerraformError)
    return COMMON_ERRORS


def echo(msg: str = "") -> None:
    click.echo(msg)


def info(msg: str) -> None:
    click.secho(msg, fg="cyan")


def ok(msg: str) -> None:
    click.secho(msg, fg="green")


def fail(msg: str) -> None:
    click.secho(msg, fg="red", err=True)


def warn(msg: str) -> None:
    click.secho(msg, fg="yellow")


def project_options(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Options shared by every command that loads the project."""

    @click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
    @click.option(
        "-p", "--provider", default=None, help=f"Override provider.name ({', '.join(PROVIDERS)}, or a plug-in)."
    )
    @click.option("-s", "--stage", default=None, help="Stage, e.g. dev / staging / prod.")
    @click.option("-r", "--region", default=None, help="Override provider.region.")
    @click.option("--server", "server", default=None,
                  help="On premises: use this saved SSH server (pskit resources onprem servers list); 'local' "
                       "for this machine. Default: the server the stage was last deployed to.")
    @click.option("--cluster", "cluster", default=None,
                  help="On premises: run the functions on this scaling cluster (pskit cluster list) instead of one "
                       "server. Default: options.cluster, else where the stage was last deployed.")
    @click.option("-v", "--verbose", is_flag=True, help="Show tracebacks on errors.")
    @functools.wraps(fn)
    def wrapper(
        *args: Any,
        config_path: Optional[str],
        provider: Optional[str],
        stage: Optional[str],
        region: Optional[str],
        server: Optional[str],
        cluster: Optional[str],
        verbose: bool,
        **kwargs: Any,
    ) -> Any:
        from ..core.project import Project

        if server and cluster:
            raise click.UsageError("pick one: --cluster NAME (several servers) or --server NAME (one server)")
        if server:
            from ..core.onprem_servers import SERVER_ENV

            os.environ[SERVER_ENV] = server
        if cluster:
            from ..core.onprem_servers import CLUSTER_ENV

            os.environ[CLUSTER_ENV] = cluster
        try:
            project = Project.load(config_path, provider=provider, stage=stage, region=region)
            return fn(project, *args, **kwargs)
        except click.exceptions.Exit:
            raise
        except click.ClickException:
            raise
        except _errors() as exc:
            if verbose:
                traceback.print_exc()
            fail(f"Error: {exc}")
            sys.exit(1)
        except KeyError as exc:
            if verbose:
                traceback.print_exc()
            fail(f"Error: {exc.args[0] if exc.args else exc}")
            sys.exit(1)

    return wrapper


CONTEXT = {"help_option_names": ["-h", "--help"], "max_content_width": 120}

ROOT_EPILOG = """\b
Getting started
  init        Scaffold a project              pskit init my-api -p aws -t full
  studio      Build it in the browser         pskit studio --open
  doctor      Check tools and credentials     pskit doctor -p azure
\b
Develop
  dev         Local server, hot reload        pskit dev --port 3000
  invoke      Call one function locally       pskit invoke -f hello -d '{"name": "Ada"}'
  validate    Check config for a provider     pskit validate -p gcp -s prod
\b
Deploy
  package     Build zip + Terraform only      pskit package -s dev
  plan        terraform plan                  pskit plan --destroy
  deploy      Package and apply               pskit deploy -s prod --confirm
                                              pskit deploy --cluster prod   (on premises: on a scaling cluster)
  info        What is deployed (URLs, ids)    pskit info --refresh
  remove      Destroy the stage               pskit remove -s dev --yes
  tf          Any terraform command           pskit tf -- state list
\b
Operate
  logs        Tail deployed logs              pskit logs -f --function worker
  trigger     Send a real test event          pskit trigger -f worker -e 0 -d '{"id": 1}'
  dashboard   Deployment dashboard            pskit dashboard --serve --open
  cluster     create | join | leave | set | status | check | watch | alerts | requests | scale | balancer | list | remove
              pskit cluster create prod --orchestrator swarm --master edge1
              pskit cluster join prod edge2
              pskit cluster set prod --master-serves
              pskit cluster balancer set prod lb1
              pskit cluster leave prod edge2 --yes
              pskit cluster status prod
              pskit cluster check prod
              pskit cluster watch prod --interval 60
              pskit cluster alerts prod --function notify-devops --test
              pskit cluster scale prod --replicas 6
              pskit cluster requests prod --follow
              pskit cluster list
              pskit cluster remove prod --yes
              pskit cluster remove prod --uninstall --yes
  firewall    Ports each on-prem server must open    pskit firewall --server edge2
  function    split: a function into its own folder  pskit function split get-item
  lb          algorithms | create | update | list | status | attach | detach | routes | sync | logs | remove | forget
              pskit lb algorithms
              pskit lb create edge --server lb1 --algorithm least_time
              pskit lb update edge --algorithm weighted_round_robin --weight app1=3
              pskit lb list
              pskit lb status edge
              pskit lb attach edge --cluster prod
              pskit lb detach edge --cluster prod
              pskit lb routes remove edge xyz
              pskit lb sync edge
              pskit lb logs edge -n 200
              pskit lb remove edge --yes
              pskit lb forget edge
  settings    export | import  (.pskit settings and secrets to another machine, encrypted)
              pskit settings export -o prod.pskit-settings
              pskit settings import prod.pskit-settings
  client      info | install-node | tunnel
              pskit client info
              pskit client install-node
              pskit client tunnel
  resources   list | send | check | usage | data | clear | delete | onprem
              pskit resources list -s dev
              pskit resources delete aws_s3_bucket.b_uploads -s dev
              pskit resources send jobs -d '{"order_id": 1}'
              pskit resources check orders-db
              pskit resources usage jobs
              pskit resources data jobs --offset 0 -n 20
              pskit resources clear jobs --yes
              pskit resources onprem create jobs --service redis --attach worker --save
  workflow    run | show | start | executions | status | cancel
              pskit workflow run order -i '{"id": 1}' --history
              pskit workflow start order -i @input.json --wait
              pskit workflow executions order --status FAILED
              pskit workflow status <execution-id> --watch
              pskit workflow cancel <execution-id>
              pskit workflow show order --format asl
\b
Reference
  providers   Capability matrix of every cloud   pskit providers --json
\b


Project options (most commands): -c/--config FILE  -p/--provider NAME  -s/--stage NAME  -r/--region NAME  -v/--verbose
Run `pskit COMMAND --help` for every option of a command. Docs: docs/cli.md"""


@click.group(context_settings=CONTEXT, epilog=ROOT_EPILOG)
@click.version_option(__version__, prog_name="py-serverless-kit")
def cli() -> None:
    """py-serverless-kit: write Python functions once, deploy them to any cloud.

    \b
    Typical flow:
      pskit doctor                   # check terraform, CLIs and credentials
      pskit init my-api --provider aws
      pskit dev                      # run locally
      pskit deploy --stage dev       # terraform apply
      pskit dashboard --open         # see everything you deployed
    """


# ----------------------------------------------------------------------------- init
@cli.command()
@click.argument("directory", default=".", type=click.Path(file_okay=False))
@click.option("--name", default=None, help="Service name (default: directory name).")
@click.option("-p", "--provider", default="aws", type=click.Choice(PROVIDERS), show_default=True)
@click.option(
    "-t", "--template", default="http", type=click.Choice(["http", "events", "workflow", "full"]), show_default=True
)
@click.option(
    "-l",
    "--language",
    default=None,
    type=click.Choice(["python", "javascript", "typescript"]),
    help="Handler language (default: python, or javascript with a nodejs --runtime).",
)
@click.option(
    "--runtime",
    default=None,
    type=click.Choice(list(PYTHON_RUNTIMES + NODE_RUNTIMES)),
    help="Runtime written to pskit.yml (default python3.12 / nodejs20).",
)
@click.option("--typescript", "--ts", "ts", is_flag=True, help="Shorthand for --language typescript.")
@click.option("--force", is_flag=True, help="Overwrite existing files.")
def init(
    directory: str,
    name: Optional[str],
    provider: str,
    template: str,
    language: Optional[str],
    runtime: Optional[str],
    ts: bool,
    force: bool,
) -> None:
    """Scaffold a new project (pskit.yml, handlers, tests).

    
    Examples:
      pskit init my-api --provider aws
      pskit init . -p gcp -t workflow
      pskit init svc -p onprem -t full --name orders
      pskit init api -p aws --typescript          # Node.js 20 + TypeScript
      pskit init api -p gcp --runtime nodejs22    # JavaScript
    """
    import re

    from .templates import render

    target = Path(directory).resolve()
    service = name or re.sub(r"[^a-z0-9-]", "-", target.name.lower()).strip("-") or "my-service"
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,31}", service):
        raise click.BadParameter(f"invalid service name {service!r}; use --name", param_hint="--name")
    if ts:
        language = "typescript"
    if language is None:
        language = "javascript" if runtime and runtime.startswith("nodejs") else "python"
    node = language in ("javascript", "typescript")
    if runtime and runtime.startswith("nodejs") != node:
        raise click.BadParameter(f"runtime {runtime} does not match language {language}", param_hint="--runtime")
    runtime = runtime or ("nodejs20" if node else "python3.12")
    files = render(template, service, provider, runtime=runtime, typescript=language == "typescript")
    target.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = target / rel
        if path.exists() and not force:
            echo(f"  skip   {rel} (exists)")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if node:
            path.write_bytes(content.encode("utf-8"))  # LF on every OS
        else:
            path.write_text(content, "utf-8")
        echo(f"  create {rel}")
    if node:
        from ..packaging.node import write_types

        if write_types(target) is not None:
            echo("  create .pskit/types/pskit/index.d.ts (types for `import ... from \"pskit\"`)")
    ok(f"\nCreated {language} service '{service}' for {provider} in {target}")
    echo("Next steps:")
    if directory != ".":
        echo(f"  cd {directory}")
    if node:
        echo("  npm install          # when you add dependencies to package.json")
    echo("  pskit dev            # local server with hot reload")
    echo("  pskit deploy         # deploy with terraform")


# ----------------------------------------------------------------------------- validate
@cli.command()
@project_options
def validate(project) -> None:  # noqa: ANN001
    """Validate the config against the selected provider.

    
    Examples:
      pskit validate
      pskit validate -p azure -s prod
    """
    issues = project.validate()
    cfg = project.config
    info(
        f"{cfg.service} -> {project.provider.display_name} [{project.provider.tier}] stage={cfg.provider.stage} region={project.region}"
    )
    echo(f"  {len(cfg.functions)} function(s), {len(cfg.workflows)} workflow(s)")
    for name, engine in project.engines.items():
        echo(f"  workflow {name}: {engine} engine")
    for issue in issues:
        (fail if issue.level == "error" else echo)(f"  {issue}")
    if any(i.level == "error" for i in issues):
        sys.exit(1)
    ok("Configuration is valid.")


# ----------------------------------------------------------------------------- package / plan / deploy / remove
@cli.command()
@project_options
@click.option("--skip-deps", is_flag=True, help="Do not pip-install requirements into the bundle.")
def package(project, skip_deps: bool) -> None:  # noqa: ANN001
    """Build the artifact and Terraform (no cloud calls).

    Writes .pskit/<provider>-<stage>/artifact.zip and main.tf.json.

    
    Examples:
      pskit package
      pskit package -p gcp -s prod --skip-deps
    """
    from ..core.deployer import Deployer

    result = Deployer(project, echo=echo).package(skip_deps=skip_deps)
    ok(f"Packaged into {project.work_dir} ({result.resource_count} terraform resources)")


@cli.command()
@project_options
@click.option("--skip-deps", is_flag=True)
@click.option("--destroy", is_flag=True, help="Plan a destroy instead.")
def plan(project, skip_deps: bool, destroy: bool) -> None:  # noqa: ANN001
    """Show the terraform plan (what would change).

    
    Examples:
      pskit plan -s dev
      pskit plan --destroy
    """
    from ..core.deployer import Deployer

    changed = Deployer(project, echo=echo).plan(skip_deps=skip_deps, destroy=destroy)
    ok("Plan has changes." if changed else "No changes.")


@cli.command()
@project_options
@click.option("--skip-deps", is_flag=True, help="Do not pip-install requirements into the bundle.")
@click.option("--confirm", is_flag=True, help="Show the plan and apply it (instead of -auto-approve).")
@click.option("--upgrade", is_flag=True, help="terraform init -upgrade (update provider plugins).")
@click.option("--no-dashboard", is_flag=True, help="Do not regenerate the dashboard.")
def deploy(project, skip_deps: bool, confirm: bool, upgrade: bool, no_dashboard: bool) -> None:  # noqa: ANN001
    """Package and deploy with terraform apply.

    
    Examples:
      pskit deploy
      pskit deploy -s prod --confirm      # review the plan first
      pskit deploy -p onprem --skip-deps
    """
    from ..core.deployer import Deployer
    from ..dashboard.generator import write_dashboard

    _ask_onprem_pem(project)
    record = Deployer(project, echo=echo).deploy(skip_deps=skip_deps, auto_approve=not confirm, upgrade=upgrade)
    where = (record.get("deployed_on") or {}).get("label") or record["region"]
    ok(f"\nDeployed {record['service']} ({record['stage']}) to {record['provider_display']} {where}")
    _print_record(record)
    if not no_dashboard:
        path = write_dashboard(project.root)
        echo(f"\nDashboard: {path.as_uri()}")


@cli.command()
@project_options
@click.option("-y", "--yes", is_flag=True, help="Do not ask for confirmation.")
@click.option(
    "--keep-resources",
    is_flag=True,
    help="Keep managed buckets, queues and topics (and their data); destroy only functions and triggers.",
)
def remove(project, yes: bool, keep_resources: bool) -> None:  # noqa: ANN001
    """Destroy every resource of this service/stage.

    
    Examples:
      pskit remove -s dev
      pskit remove -s dev --yes
      pskit remove -s dev --keep-resources   # keep buckets, queues, topics
    """
    from ..core.deployer import Deployer
    from ..dashboard.generator import write_dashboard

    cfg = project.config
    if not yes:
        what = "functions and triggers (keeping buckets, queues and topics)" if keep_resources else "ALL resources"
        click.confirm(
            f"Destroy {what} of '{cfg.service}' stage '{cfg.provider.stage}' on {project.provider.display_name}?",
            abort=True,
        )
    kept = Deployer(project, echo=echo).remove(auto_approve=True, keep_resources=keep_resources)
    if kept:
        info(f"Kept {len(kept)} resource(s); they are no longer managed by pskit. Delete them in the console when done.")
    write_dashboard(project.root)
    ok("Removed.")


# ----------------------------------------------------------------------------- trigger (test events)
@cli.command(short_help="Send a real test event to a deployed function.")
@project_options
@click.option("-f", "--function", "function", default=None, help="Function to test (all with --list).")
@click.option("-e", "--event", "index", type=int, default=None, help="Trigger number (0 = first; see --list).")
@click.option("--direct", is_flag=True, help="Invoke the function directly instead of through a trigger.")
@click.option("-d", "--data", default=None, help="Payload JSON or @file.json (default: a sample for the trigger).")
@click.option("--path", "path", default=None, help="HTTP path incl. query string (http triggers), e.g. /items/1?x=y.")
@click.option("--list", "show", is_flag=True, help="Show how to test each trigger: payload, commands, console steps.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def trigger(  # noqa: ANN001
    project, function: Optional[str], index: Optional[int], direct: bool, data: Optional[str], path: Optional[str],
    show: bool, as_json: bool,
) -> None:
    """Send a real test event to a deployed function (queue message, upload, HTTP call...).

    \b
    Examples:
      pskit trigger --list                          # how to test every function
      pskit trigger -f worker -e 0 -d '{"order_id": 1}'      # e.g. an SQS message
      pskit trigger -f thumbnails -e 0 -d '{"key": "in/a.png", "content": "x"}'
      pskit trigger -f api -e 0 --path '/items/1'
      pskit trigger -f nightly --direct              # invoke without the trigger
    Test locally (nothing deployed) with `pskit invoke`.
    """
    from ..core.deployer import Deployer
    from ..core.testing import TriggerError, guide, send
    from ..local.runner import parse_data

    record = Deployer(project, echo=echo).load_record()
    info_ = guide(project, record)
    if show or function is None:
        rows = [f for f in info_["functions"] if function in (None, f["name"])]
        if as_json:
            click.echo(json.dumps(rows, indent=2, default=str))
            return
        if not info_["deployed"]:
            info(f"{info_['provider']}/{info_['stage']} is not deployed: only local tests (pskit invoke) apply.")
        for fn in rows:
            echo(click.style(f"\n{fn['name']}", bold=True) + (f"  {fn['description']}" if fn["description"] else ""))
            for t in fn["triggers"]:
                label = "direct invoke" if t["index"] < 0 else f"#{t['index']} {t['summary']}"
                echo(f"  {label}")
                echo(f"    payload: {json.dumps(t['sample'])}   ({t['payload_help']})")
                for cmd in t["local"]:
                    echo(f"    local:   {cmd}")
                remote = t["remote"]
                for cmd in remote["pskit"]:
                    echo(f"    deployed: {cmd}")
                if not remote["supported"] and info_["deployed"]:
                    echo(f"    deployed: {remote['reason']}")
                for cmd in remote["cli"]:
                    echo(f"    cloud CLI: {cmd}")
                for i, step in enumerate(remote["console"], 1):
                    echo(f"    console {i}. {step}")
        return
    if direct and index is not None:
        raise click.UsageError("use --event or --direct, not both")
    triggers = next((f["triggers"] for f in info_["functions"] if f["name"] == function), None)
    if triggers is None:
        raise click.UsageError(f"unknown function {function!r}")
    chosen = -1 if direct else (index if index is not None else triggers[0]["index"])
    sample = next((t["sample"] for t in triggers if t["index"] == chosen), None)
    payload = parse_data(data) if data is not None else sample
    try:
        result = send(project, record, function, chosen, payload, path=path)
    except TriggerError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
        return
    ok(f"Sent {result.get('kind')} event to {function}")
    click.echo(json.dumps(result, indent=2, default=str))
    info("Watch what the function did: pskit logs -f --function " + function)


# ----------------------------------------------------------------------------- resources
@cli.group()
def resources() -> None:
    """List or delete the buckets, queues and topics pskit created.

    \b
    Examples:
      pskit resources list -s dev
      pskit resources delete aws_s3_bucket.b_uploads -s dev
      pskit resources delete --all-kept -s dev     # after `pskit remove --keep-resources`
    """


def _resource_rows(project: Any) -> dict:
    from ..core.deployer import Deployer

    return Deployer(project, echo=echo).cloud_resources()


@resources.command("list", short_help="Deployed and kept buckets, queues and topics.")
@project_options
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def resources_list(project, as_json: bool) -> None:  # noqa: ANN001
    """Deployed and kept buckets, queues and topics, with their Terraform addresses."""
    found = _resource_rows(project)
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    rows = found["deployed"] + found["kept"]
    if not rows:
        echo("No buckets, queues or topics created by pskit for this stage.")
        return
    echo(f"{'status':<10}{'kind':<8}{'name':<40}address")
    for r in rows:
        echo(f"{r['status']:<10}{r['kind']:<8}{r['name'][:39]:<40}{r['address']}")
    if found["kept"]:
        info("Kept resources were left by `pskit remove --keep-resources`; delete them with `pskit resources delete`.")


@resources.command("send", short_help="Send a test message / object to a queue, bucket or topic.")
@project_options
@click.argument("key", required=False)
@click.option("-d", "--data", default=None, help="Payload JSON or @file.json (default: a sample).")
@click.option("--list", "show", is_flag=True, help="How to test every resource: payload, commands, console steps.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def resources_send(project, key: Optional[str], data: Optional[str], show: bool, as_json: bool) -> None:  # noqa: ANN001
    """Test a resource: a message to a queue, an object to a bucket, a message to a topic.

    \b
    Examples:
      pskit resources send --list
      pskit resources send jobs -d '{"order_id": 1}'
      pskit resources send uploads -d '{"key": "in/a.csv", "content": "a,b"}'
      pskit resources send events -d '{"message": {"id": 1}, "attributes": {"type": "order"}}'
    Functions bound to the resource receive it through their triggers; watch them with `pskit logs -f`.
    """
    from ..core.deployer import Deployer
    from ..core.testing import TriggerError, resource_guide, send_resource
    from ..local.runner import parse_data

    record = Deployer(project, echo=echo).load_record()
    if show or key is None:
        info_ = resource_guide(project, record)
        rows = [r for r in info_["resources"] if key in (None, r["key"])]
        if as_json:
            click.echo(json.dumps(rows, indent=2, default=str))
            return
        if not rows:
            echo("No resources in pskit.yml.")
        for r in rows:
            label = f"{r['type']} {r['name']}" + (" (external)" if r["external"] else "")
            echo(click.style(f"\n{r['key']}", bold=True) + f"  {label}  -> {', '.join(r['functions']) or 'no functions'}")
            if r["sendable"]:
                echo(f"    payload: {json.dumps(r['sample'])}   ({r['payload_help']})")
                for cmd in r["remote"]["pskit"]:
                    echo(f"    pskit:     {cmd}")
                if not r["remote"]["supported"]:
                    echo(f"    pskit:     {r['remote']['reason']}")
                for cmd in r["remote"]["cli"]:
                    echo(f"    cloud CLI: {cmd}")
                for i, step in enumerate(r["remote"]["console"], 1):
                    echo(f"    console {i}. {step}")
            else:
                echo(f"    env vars:  {', '.join(r['env'])}")
                echo("    read it in a handler: resource(" + json.dumps(r["key"]) + ").get(\"<connection key>\")")
        return
    try:
        result = send_resource(project, record, key, parse_data(data) if data is not None else None)
    except TriggerError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
        return
    ok(f"Sent to {result['kind']} {result['name']}")
    click.echo(json.dumps(result, indent=2, default=str))
    if result.get("functions"):
        info("Bound functions: " + ", ".join(result["functions"]) + ". Watch them: pskit logs -f")


@resources.command("check", short_help="Check that a resource is reachable (connection, depth).")
@project_options
@click.argument("key")
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def resources_check(project, key: str, as_json: bool) -> None:  # noqa: ANN001
    """Check resource KEY: from the on-prem host once deployed there, else from this machine.

    \b
    Queues report how many messages wait, buckets how many objects they hold; databases,
    caches and custom services get a connection check (Redis answers PING).
    """
    from ..core.deployer import Deployer
    from ..core.testing import TriggerError, check_resource

    try:
        result = check_resource(project, Deployer(project, echo=echo).load_record(), key)
    except TriggerError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(result, indent=2))
    elif result.get("ok"):
        ok(f"{key}: {result['detail']} ({result['ms']} ms, from {result['checked_from']})")
    else:
        fail(f"{key}: {result['detail']} (from {result['checked_from']})")
    if not result.get("ok"):
        raise SystemExit(1)


@resources.command("usage", short_help="End-to-end guide: libraries, pskit.yml, code, tests for a resource.")
@project_options
@click.argument("key")
def resources_usage(project, key: str) -> None:  # noqa: ANN001
    """How to use resource KEY: what to install (Python / Node.js), the pskit.yml, handler code,
    local and deployed tests, provider notes and troubleshooting, as Markdown.

    \b
    Examples:
      pskit resources usage jobs
      pskit resources usage orders-db -p onprem > docs/orders-db.md
    """
    from ..core.deployer import Deployer
    from ..core.resource_usage import usage
    from ..core.testing import TriggerError

    try:
        out = usage(project, Deployer(project, echo=echo).load_record(), key)
    except TriggerError as exc:
        raise click.ClickException(str(exc)) from None
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    # Guides quote docs with arrows and dashes a legacy Windows console cannot print.
    click.echo(out["markdown"].encode(encoding, "replace").decode(encoding))


@resources.command("data", short_help="Browse what an on-prem queue, topic or bucket holds (paginated).")
@project_options
@click.argument("key")
@click.option("--offset", default=0, show_default=True, help="Skip this many items.")
@click.option("-n", "--limit", default=20, show_default=True, help="Items per page (max 500).")
@click.option("--prefix", default="", help="Buckets: only keys below this prefix.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def resources_data(project, key: str, offset: int, limit: int, prefix: str, as_json: bool) -> None:  # noqa: ANN001
    """Show a page of resource KEY: waiting messages (nothing is consumed) or objects.

    \b
    Examples:
      pskit resources data jobs
      pskit resources data jobs --offset 20 -n 20
      pskit resources data uploads --prefix in/
    """
    from ..core.deployer import Deployer
    from ..core.testing import TriggerError, browse_resource

    try:
        page = browse_resource(project, Deployer(project, echo=echo).load_record(), key, offset, limit, prefix)
    except TriggerError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(page, indent=2))
        return
    total = page.get("total")
    if not page.get("supported"):
        info(f"{page.get('note')}" + (f" (depth {total})" if total is not None else ""))
        return
    shown = len(page["items"])
    info(f"{key}: items {offset + 1 if shown else 0}-{offset + shown} of {total if total is not None else '?'}")
    for item in page["items"]:
        if page["type"] == "storage":
            echo(f"  {item['size']:>10}  {item['key']}")
        else:
            extra = " (leased)" if item.get("leased") else ""
            echo(f"  {item['id'][:24]:<26}{item['body'][:100]}{extra}")
    if total is not None and offset + shown < total:
        echo(f"next page: pskit resources data {key} --offset {offset + shown} -n {limit}")


@resources.command("clear", short_help="Delete the data of a built-in on-prem queue, bucket or topic.")
@project_options
@click.argument("key")
@click.option("-y", "--yes", is_flag=True, help="Do not ask for confirmation.")
def resources_clear(project, key: str, yes: bool) -> None:  # noqa: ANN001
    """Delete every message / object of built-in resource KEY on the on-prem host (the resource stays)."""
    from ..core.deployer import Deployer
    from ..core.testing import TriggerError, purge_resource

    if not yes:
        click.confirm(f"Delete all data of {key} on the on-prem host?", abort=True)
    try:
        result = purge_resource(project, Deployer(project, echo=echo).load_record(), key)
    except TriggerError as exc:
        raise click.ClickException(str(exc)) from None
    ok(f"Deleted {result['deleted']} item(s) from {result['path']}")


@resources.command("delete", short_help="Delete buckets, queues or topics by address.")
@project_options
@click.argument("addresses", nargs=-1)
@click.option("--all-kept", is_flag=True, help="Delete every resource kept by `pskit remove --keep-resources`.")
@click.option("-y", "--yes", is_flag=True, help="Do not ask for confirmation.")
def resources_delete(project, addresses: tuple, all_kept: bool, yes: bool) -> None:  # noqa: ANN001
    """Delete buckets, queues or topics (and their data) by address. See `pskit resources list`."""
    from ..core.deployer import Deployer

    targets = list(addresses)
    if all_kept:
        targets += [r["address"] for r in _resource_rows(project)["kept"] if r["address"] not in targets]
    if not targets:
        raise click.UsageError("pass one or more addresses (see `pskit resources list`) or --all-kept")
    if not yes:
        click.confirm(f"Permanently delete {len(targets)} resource(s) and their data: {', '.join(targets)}?", abort=True)
    deleted = Deployer(project, echo=echo).delete_resources(targets)
    ok(f"Deleted {len(deleted)} resource(s).")


# ----------------------------------------------------------------------------- resources onprem
@resources.group("onprem")
def resources_onprem() -> None:
    """Create services for on-premises functions with Docker, here or on an SSH server.

    \b
    Examples:
      pskit resources onprem catalog
      pskit resources onprem create jobs --service redis --attach worker --save
      pskit resources onprem create orders-db --service postgres --ssh ubuntu@10.0.0.5 --pem key.pem --save
      pskit resources onprem create py --service python --ssh ubuntu@10.0.0.5 --pem key.pem
      pskit resources onprem servers add edge1 --ssh ubuntu@10.0.0.5 --pem key.pem
      pskit resources onprem create node --service nodejs --version 22 --server edge1
      pskit resources onprem create cache --service redis --cluster prod   # the server with the most free memory
      pskit resources onprem create orders-db --service postgres --primary db1 --replica db2 --replica db3 \\
          --balancer lb1 --sync sync                                 # primary + 2 read replicas behind pgpool-II
      pskit resources onprem console cache "INFO server"
      pskit resources onprem terminal --server edge1
      pskit resources onprem status jobs
      pskit resources onprem backup orders-db
      pskit resources onprem remove jobs --delete-data --save
    Credentials go to the on-prem env file (default .env.onprem), never into pskit.yml.
    """


def _raw_project(config_path: Optional[str]) -> tuple:
    import yaml

    from ..config.loader import DEFAULT_FILES

    if config_path:
        path = Path(config_path).resolve()
    else:
        found = [Path.cwd() / name for name in DEFAULT_FILES if (Path.cwd() / name).is_file()]
        if not found:
            raise click.ClickException("no pskit.yml here; run inside a project or pass -c")
        path = found[0]
    raw = yaml.safe_load(path.read_text("utf-8")) or {}
    if not isinstance(raw, dict):
        raise click.ClickException(f"{path} is not a mapping")
    return path.parent, path, raw


def _save_raw(path: Path, raw: dict) -> None:
    from ..studio.project import dump_yaml

    path.write_bytes(dump_yaml(raw).encode("utf-8"))
    ok(f"Updated {path.name} (comments are not kept)")


def _env_value(name: str) -> str:
    if name not in os.environ:
        raise click.ClickException(f"environment variable {name} is not set")
    return os.environ[name]


def _service_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    from ..core.onprem_services import ServiceError

    try:
        return fn(*args, **kwargs)
    except ServiceError as exc:
        raise click.ClickException(str(exc)) from None


@resources_onprem.command("catalog", short_help="Services and runtimes that can be created.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def resources_onprem_catalog(as_json: bool) -> None:
    from ..core.onprem_services import catalog

    items = catalog()
    if as_json:
        click.echo(json.dumps(items, indent=2))
        return
    echo(f"{'id':<11}{'use as':<16}{'port':<7}notes")
    for item in items:
        roles = ", ".join(item["roles"]) or "runtime"
        echo(f"{item['id']:<11}{roles:<16}{str(item.get('port') or ''):<7}{item['notes']}")


@resources_onprem.command("create", short_help="Start a service (or install a runtime) and add it as a resource.")
@click.argument("key")
@click.option("--service", "service", required=True, help="See `pskit resources onprem catalog`.")
@click.option("--role", default=None, help="queue, cache, database, storage or custom (default: the first one).")
@click.option("--port", type=int, default=None, help="Port published on the server (default: the service's).")
@click.option("--image", default=None, help="Docker image (default: the catalog's).")
@click.option("--address", default=None, help="Address functions use to reach it (default: SSH host / 127.0.0.1).")
@click.option("--bind", default=None, help="Interface the port listens on (default: 0.0.0.0 over SSH, else 127.0.0.1).")
@click.option("--ssh", "ssh", default=None, help="user@host[:port] of the server. Default: options.deploy, else here.")
@click.option("--pem", default=None, help="Private key for --ssh (empty: the SSH agent or your default key).")
@click.option("--ssh-password-file", default=None, help="SSH with a password read from this file (uses sshpass).")
@click.option("--ssh-password-env", default=None,
              help="SSH with a password from this environment variable (uses sshpass; never stored).")
@click.option("--sudo", is_flag=True, help="Run docker / installs with sudo -n on the server.")
@click.option("--local", "local", is_flag=True, help="Create it on this machine even if the functions deploy over SSH.")
@click.option("--server", "server", default=None, help="A saved SSH server (pskit resources onprem servers list).")
@click.option("--cluster", "cluster", default=None,
              help="Run it on a server of this scaling cluster (default with options.cluster): the one with the most "
                   "free memory, or --node.")
@click.option("--node", "node", default=None, help="With --cluster: the cluster's saved server to run it on.")
@click.option("--version", "version", default=None, help="Software version to install (nodejs 22 / 20 / 18, java 21, go ...).")
@click.option("--user", "login", default=None, help="User to create (default: pskit; Redis / Valkey: default).")
@click.option("--password", default=None, help="Password to set (default: a generated one). Prefer --password-env.")
@click.option("--password-env", default=None, help="Read the password from this environment variable.")
@click.option("-a", "--attach", multiple=True, help="Add a trigger on this function (queue / storage / smtp). Repeatable.")
@click.option("--domains", default=None, help="smtp: the domains it receives mail for, comma separated.")
@click.option("--functions-url", default=None, help="smtp: the pskit host's URL (default: found from the deploy).")
@click.option("--max-size-mb", type=float, default=None, help="smtp: largest mail accepted (default 25).")
@click.option("--gui", is_flag=True, help="Also start its web UI (Adminer, Redis Commander, Kafka UI, Mongo Express).")
@click.option("--gui-login", type=click.Choice(["password", "none"]), default=None,
              help="Web UI sign-in: password (default) or none (keep it on 127.0.0.1, a private network or a tunnel).")
@click.option("--gui-password-env", default=None, help="Your own web UI password, from this environment variable.")
@click.option("--replica", "replicas", multiple=True,
              help="Database: a saved server for a read replica (repeatable). Makes it replicated: the primary is "
                   "--primary. 'local' runs every member on this machine.")
@click.option("--primary", "primary", default=None, help="With --replica: the saved server that takes the writes.")
@click.option("--balancer", "balancer", default=None,
              help="With --replica: the saved server for the load balancer (pgpool-II / ProxySQL) that gives the "
                   "functions one address. Not for MongoDB (the driver routes).")
@click.option("--balancer-port", type=int, default=None, help="With --balancer: its port (6432 / 6033).")
@click.option("--sync", "sync", type=click.Choice(["async", "sync"]), default=None,
              help="With --replica: async (default, fastest) or sync (a commit waits for a replica).")
@click.option("--import", "import_file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Database: load this dump once it is up (.sql, .sql.gz, .dump; MongoDB .archive).")
@click.option("--alert-webhook", default=None, help="Alerts (CPU, memory, disk, replica lag, down) to this URL.")
@click.option("--alert-function", default=None, help="Alerts run this function of the project (deployed host).")
@click.option("--save", is_flag=True, help="Write the resource (and triggers) into pskit.yml.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
@click.option("--json", "as_json", is_flag=True, help="Print the created entry as JSON.")
def resources_onprem_create(  # noqa: PLR0913
    key: str,
    service: str,
    role: Optional[str],
    port: Optional[int],
    image: Optional[str],
    address: Optional[str],
    bind: Optional[str],
    ssh: Optional[str],
    pem: Optional[str],
    ssh_password_file: Optional[str],
    ssh_password_env: Optional[str],
    sudo: bool,
    local: bool,
    login: Optional[str],
    password: Optional[str],
    password_env: Optional[str],
    attach: tuple,
    gui: bool,
    gui_login: Optional[str],
    gui_password_env: Optional[str],
    server: Optional[str],
    cluster: Optional[str],
    node: Optional[str],
    version: Optional[str],
    domains: Optional[str],
    functions_url: Optional[str],
    max_size_mb: Optional[float],
    replicas: tuple,
    primary: Optional[str],
    balancer: Optional[str],
    balancer_port: Optional[int],
    sync: Optional[str],
    import_file: Optional[str],
    alert_webhook: Optional[str],
    alert_function: Optional[str],
    save: bool,
    config_path: Optional[str],
    as_json: bool,
) -> None:
    """Create KEY: a Docker container on this machine or an SSH server, ready for the on-prem host.

    A database with --replica is replicated: --primary takes the writes, each --replica serves reads, and
    --balancer gives the functions one address that splits them."""
    from ..core import onprem_services as svc

    root, path, raw = _raw_project(config_path)
    target: Optional[dict] = None
    if node and not cluster:
        raise click.ClickException("--node goes with --cluster NAME")
    if cluster and (local or server or ssh):
        raise click.ClickException("pick one place: --cluster, --server, --ssh or --local")
    if local:
        target = {"method": "local"}
    elif cluster:
        target = {"cluster": cluster, **({"server": node} if node else {}), **({"sudo": True} if sudo else {})}
    elif server:
        target = {"server": server, **({"sudo": True} if sudo else {})}
    elif ssh:
        user, _, rest = ssh.rpartition("@")
        host, _, ssh_port = rest.partition(":")
        target = {"method": "ssh", "user": user or "root", "host": host, "port": int(ssh_port or 22), "sudo": sudo}
        if pem:
            target["identity_file"] = pem
        if ssh_password_file:
            target["password_file"] = ssh_password_file
        elif ssh_password_env:
            target["password"] = _env_value(ssh_password_env)
    elif ssh_password_file or ssh_password_env or pem:
        raise click.ClickException("--pem / --ssh-password-* go with --ssh user@host")
    if password_env:
        password = _env_value(password_env)
    gui_password = _env_value(gui_password_env) if gui_password_env else None
    topology: Optional[dict] = None
    if replicas:
        if local or cluster or ssh:
            raise click.ClickException("a replicated database runs on --primary / --replica servers, not --local, "
                                       "--cluster or --ssh")
        topology = {"mode": "replicated", "sync": sync or "async", "primary": primary or server or "",
                    "replicas": list(replicas), "balancer": balancer or ""}
        if balancer_port:
            topology["balancer_port"] = balancer_port
        target = None
    elif primary or balancer or balancer_port or sync:
        raise click.ClickException("--primary, --balancer and --sync go with --replica SERVER")
    body = {
        "key": key,
        "service": service,
        "user": login,
        "password": password,
        "role": role,
        "port": port,
        "image": image,
        "address": address,
        "bind": bind,
        "attach": list(attach),
        "target": target,
        "gui": gui or None,
        "gui_login": gui_login if gui else None,
        "gui_password": gui_password if gui else None,
        "version": version,
        "domains": domains,
        "functions_url": functions_url,
        "max_size_mb": max_size_mb,
        "topology": topology,
        "import": {"path": import_file} if import_file else None,
        "alert": {"webhook": alert_webhook or "", "function": alert_function or ""}
        if alert_webhook or alert_function else None,
    }
    entry = _service_call(svc.create, root, {k: v for k, v in body.items() if v is not None}, raw, echo)
    if as_json:
        click.echo(json.dumps(svc.public_entry(entry), indent=2))
    if entry.get("kind") == "runtime":
        ok(f"{service} is installed on {svc.describe_target(entry['target'])}")
        return
    if save:
        _save_raw(path, _service_call(svc.apply_to_raw, raw, entry))
    elif not as_json:
        info("Add this to pskit.yml (or rerun with --save):")
        click.echo(svc.snippet(entry))
    if entry["resource"]["type"] == "smtp":
        click.echo(svc.service_usage(root, key, probe=False)["markdown"])
    elif entry["resource"]["type"] in ("queue", "storage", "topic"):
        info(f"Test it: pskit deploy, then pskit resources send {key}")
    elif entry.get("role") == "secrets":
        store = "" if key == "secrets" else f", store=\"{key}\""
        info(f'Read secrets in a handler: get_secret("name"{store}); add some with put_secret or the console')
    else:
        info(f'Read it in a handler: resource("{key}"); the password is in ctx.env[res["password_env"]]')


@resources_onprem.group("replicas", short_help="Read replicas of a replicated database: list, add, remove.")
def resources_onprem_replicas() -> None:
    """Read replicas of a database created with --replica. The load balancer and the env file follow."""


@resources_onprem.command("monitor", short_help="Live CPU, memory, disk, connections and replica lag of a service.")
@click.argument("key")
@click.option("--watch", "every", type=int, default=0, help="Repeat every N seconds until Ctrl+C.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_monitor(key: str, every: int, as_json: bool, config_path: Optional[str]) -> None:
    import time

    from ..core.onprem_monitor import sample

    root, _path, _raw = _raw_project(config_path)
    while True:
        data = _service_call(sample, root, key)
        if as_json:
            click.echo(json.dumps(data, indent=2))
        else:
            echo(f"{key} ({data['service']}) at {data['at']}")
            for c in data["containers"]:
                where = c.get("server") or "this machine"
                usage = "  ".join(f"{label} {c[k]:g}%" for k, label in (("cpu", "CPU"), ("memory", "mem"),
                                                                         ("disk", "disk")) if c.get(k) is not None)
                echo(f"  {c['name']:<10}{c['role']:<9}{where:<18}{c['state']:<10}{usage}")
            db = data.get("database") or {}
            if db:
                echo(f"  connections {db.get('connections', '?')}, data {db.get('size_mb', '?')} MB")
            for name, lag in (data.get("lag") or {}).items():
                echo(f"  replica {name}: " + ("replication stopped" if lag is None else f"{lag} s behind"))
        if not every:
            return
        time.sleep(max(2, every))


@resources_onprem.command("alerts", short_help="Alerts of a service: show, set, test or check now.")
@click.argument("key")
@click.option("--on/--off", "enabled", default=None, help="Turn the alerts on or off (settings are kept).")
@click.option("--webhook", default=None, help="POST alerts to this URL (Slack / Teams incoming webhook, any URL).")
@click.option("--function", "function", default=None, help="Run this function of the project with each alert.")
@click.option("--stage", default=None, help="The deployed on-prem stage that runs the function (default: any).")
@click.option("--cpu", type=int, default=None, help="Alert at this CPU percent of a container (default 90).")
@click.option("--memory", type=int, default=None, help="... memory percent (default 90).")
@click.option("--disk", type=int, default=None, help="... percent of the data disk used (default 85).")
@click.option("--lag", "lag_seconds", type=int, default=None, help="... seconds a replica is behind (default 60).")
@click.option("--cooldown", "cooldown_minutes", type=int, default=None, help="Minutes between alerts (default 30).")
@click.option("--test", "test", is_flag=True, help="Send a test alert now.")
@click.option("--check", "check_now", is_flag=True, help="Measure now and alert when over a limit (for cron).")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_alerts(key: str, enabled: Optional[bool], webhook: Optional[str], function: Optional[str],
                            stage: Optional[str], cpu: Optional[int], memory: Optional[int], disk: Optional[int],
                            lag_seconds: Optional[int], cooldown_minutes: Optional[int], test: bool, check_now: bool,
                            config_path: Optional[str]) -> None:
    """The studio checks services with alerts on while it runs; `--check` from cron does the same without it."""
    from ..core import onprem_monitor as mon
    from ..core.onprem_services import _entry

    root, _path, _raw = _raw_project(config_path)
    changes = {k: v for k, v in {"enabled": enabled, "webhook": webhook, "function": function, "stage": stage,
                                 "cpu": cpu, "memory": memory, "disk": disk, "lag_seconds": lag_seconds,
                                 "cooldown_minutes": cooldown_minutes}.items() if v is not None}
    if changes:
        if "enabled" not in changes and not mon.alert_settings(_service_call(_entry, root, key))["enabled"]:
            changes["enabled"] = True
        _service_call(mon.set_alert, root, key, changes)
    settings = mon.alert_settings(_service_call(_entry, root, key))
    echo(f"{key}: alerts {'on' if settings['enabled'] else 'off'}; CPU {settings['cpu']}%, memory "
         f"{settings['memory']}%, disk {settings['disk']}%, replica lag {settings['lag_seconds']} s, down "
         f"{'yes' if settings['down'] else 'no'}; every {settings['interval_seconds']} s, cooldown "
         f"{settings['cooldown_minutes']} min")
    echo(f"  to: {', '.join(x for x in (settings['function'] and 'function ' + settings['function'], settings['webhook']) if x) or 'nowhere yet'}")
    if test:
        record = _service_call(mon.send_alert, root, key, _service_call(mon.sample, root, key), [], test=True)
        (ok if record["sent"] else warn)(f"test alert: sent to {', '.join(record['sent']) or 'nothing'}"
                                         + (f"; {'; '.join(record['errors'])}" if record["errors"] else ""))
    if check_now:
        result = _service_call(mon.check, root, key)
        if not result["reasons"]:
            ok("all within the limits")
        for reason in result["reasons"]:
            warn(reason)
        if result.get("alert"):
            echo(f"  alert: {result['alert']}")


@resources_onprem_replicas.command("list", short_help="Members, their state and replication lag.")
@click.argument("key")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_replicas_list(key: str, config_path: Optional[str]) -> None:
    from ..core.onprem_services import status

    root, _path, _raw = _raw_project(config_path)
    topo = _service_call(status, root, key).get("topology")
    if not topo:
        raise click.ClickException(f"{key!r} runs on a single server; it has no replicas")
    lb = topo.get("balancer")
    echo(f"{key}: {topo['sync']} replication" + (f", load balancer {lb['kind']}" if lb else ""))
    for m in [*(topo.get("members") or []), *([lb] if lb else [])]:
        where = m["server"] or "this machine"
        echo(f"  {m['name']:<8}{m['role']:<10}{where:<22}{m['address'] + ':' + str(m['port']):<22}{m.get('state', '')}")
        for line in str(m.get("replication") or "").splitlines():
            echo(f"            {line.strip()}")
    if topo.get("report"):
        echo("")
        echo(topo["report"])


@resources_onprem_replicas.command("add", short_help="Start one more read replica on a saved server.")
@click.argument("key")
@click.argument("server", required=False)
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_replicas_add(key: str, server: Optional[str], config_path: Optional[str]) -> None:
    """Add a replica of KEY on SERVER (a saved server; omit it when every member runs on this machine)."""
    from ..core.onprem_replication import add_replica

    root, _path, _raw = _raw_project(config_path)
    entry = _service_call(add_replica, root, key, server or "", echo)
    ok(f"{key} now has {len(entry['topology']['members']) - 1} replica(s)")


@resources_onprem_replicas.command("remove", short_help="Stop one read replica (by name r2, or its server).")
@click.argument("key")
@click.argument("name")
@click.option("--delete-data", is_flag=True, help="Also delete the replica's data volume.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_replicas_remove(key: str, name: str, delete_data: bool, config_path: Optional[str]) -> None:
    from ..core.onprem_replication import remove_replica

    root, _path, _raw = _raw_project(config_path)
    entry = _service_call(remove_replica, root, key, name, echo, delete_data=delete_data)
    ok(f"{key} now has {len(entry['topology']['members']) - 1} replica(s)")


@resources_onprem.command("list", short_help="Services created from this project.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def resources_onprem_list(config_path: Optional[str], as_json: bool) -> None:
    from ..core.onprem_services import list_services

    root, _path, _raw = _raw_project(config_path)
    items = list_services(root)
    if as_json:
        click.echo(json.dumps(items, indent=2))
        return
    if not items:
        echo("No on-prem services yet. Create one: pskit resources onprem create <key> --service redis")
        return
    echo(f"{'key':<20}{'service':<11}{'as':<10}{'where':<28}endpoint")
    for item in items:
        where = item["target_label"]
        endpoint = f"{item.get('address')}:{item.get('port')}" if item.get("port") else ""
        echo(f"{item['key']:<20}{item['service']:<11}{item.get('role') or 'runtime':<10}{where[:27]:<28}{endpoint}")


@resources_onprem.command("status", short_help="State, health and connection details of a service.")
@click.argument("key")
@click.option("--reveal", is_flag=True, help="Show passwords and URLs from the env file.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_status(key: str, reveal: bool, config_path: Optional[str]) -> None:
    from ..core.onprem_services import status

    root, _path, _raw = _raw_project(config_path)
    click.echo(json.dumps(_service_call(status, root, key, reveal=reveal), indent=2))


@resources_onprem.command("usage", short_help="Connect to a service from any program: code, terminal, security.")
@click.argument("key")
@click.option("--reveal", is_flag=True, help="Show passwords and URLs in the guide.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_usage(key: str, reveal: bool, config_path: Optional[str]) -> None:
    """How to use service KEY from any program: connection details, Python / Node.js clients, terminal tools."""
    from ..core.onprem_services import service_usage

    root, _path, _raw = _raw_project(config_path)
    text = _service_call(service_usage, root, key, reveal=reveal)["markdown"]
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    click.echo(text.encode(encoding, "replace").decode(encoding))


@resources_onprem.command("tunnel", short_help="Reach a service on a server through SSH (firewalled port).")
@click.argument("key")
@click.option("--local-port", type=int, default=None, help="Port on this machine (default: the remote port).")
@click.option("--remote-port", type=int, default=None, help="Port on the server (default: the service's; e.g. its web UI).")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_tunnel(
    key: str, local_port: Optional[int], remote_port: Optional[int], config_path: Optional[str]
) -> None:
    """Forward 127.0.0.1:<port> here to the service on its SSH server, until Ctrl+C.

    \b
    Use it when the service's port is closed in the server's firewall (connections time out):
    scripts on this machine then connect to 127.0.0.1 with the variables printed below.
    """
    import subprocess

    from ..core import onprem_services as svc

    root, _path, _raw = _raw_project(config_path)
    entry = _service_call(svc._entry, root, key)
    if entry.get("kind") == "runtime":
        raise click.ClickException(f"{key} is a runtime, not a service")
    remote = int(remote_port or entry["port"])
    port = int(local_port or remote)
    argv = _service_call(svc.tunnel_argv, entry["target"], port, remote)
    if remote != int(entry["port"]):
        info(f"Open http://127.0.0.1:{port}/ in your browser.")
    info(f"Forwarding 127.0.0.1:{port} -> {entry['address']}:{entry['port']} over SSH. Ctrl+C to stop.")
    for name, value in sorted(svc.local_env(entry, port).items()):
        echo(f"  export {name}='{value}'")
    if not entry.get("env"):
        echo(f"  connect your client to 127.0.0.1:{port}")
    try:
        raise SystemExit(subprocess.call(argv))
    except KeyboardInterrupt:
        ok("Tunnel closed.")


@resources_onprem.command("gui", short_help="Start (or --remove) the web UI of a service.")
@click.argument("key")
@click.option("--port", type=int, default=None, help="Port for the UI (default: Adminer 8089, Redis Commander 8082, ...).")
@click.option("--login", "gui_login", type=click.Choice(["password", "none"]), default="password", show_default=True,
              help="Sign-in of the companion UI; none = no login (keep it private).")
@click.option("--password-env", default=None, help="Your own UI password from this environment variable (default: generated).")
@click.option("--check", is_flag=True, help="Find out why a web UI does not open (container, ports, server, firewall).")
@click.option("--remove", is_flag=True, help="Stop and delete the companion web UI.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_gui(  # noqa: PLR0913
    key: str,
    port: Optional[int],
    gui_login: str,
    password_env: Optional[str],
    check: bool,
    remove: bool,
    config_path: Optional[str],
) -> None:
    """Web UIs of service KEY: built in (RabbitMQ, MinIO, ...) or a companion pskit starts next to it.

    \b
    pskit resources onprem gui cache                     # start Redis Commander (generated password)
    pskit resources onprem gui cache --login none        # no sign-in: keep it on 127.0.0.1 or a tunnel
    pskit resources onprem gui cache --check             # it does not open? find out why

    
    Companions: Adminer (PostgreSQL / MySQL / MariaDB), Redis Commander (Redis, Valkey, KeyDB, Dragonfly),
    Kafka UI (Kafka, Apache Kafka), Mongo Express (MongoDB). They share a private Docker network with the service.
    """
    from ..core import onprem_services as svc

    root, _path, _raw = _raw_project(config_path)
    if remove:
        _service_call(svc.remove_gui, root, key, echo)
        ok(f"Removed the web UI of {key}")
        return
    if check:
        result = _service_call(svc.gui_check, root, key, echo)
        if result["ok"]:
            ok("Every web UI answers from this machine.")
            return
        raise SystemExit(1)
    entry = _service_call(svc._entry, root, key)
    password = _env_value(password_env) if password_env else ""
    wants_change = port is not None or gui_login != "password" or bool(password)
    if svc.companion_for(str(entry.get("service"))) and (not isinstance(entry.get("gui"), dict) or wants_change):
        _service_call(svc.add_gui, root, key, echo, port=port, login=gui_login, password=password)
        entry = _service_call(svc._entry, root, key)
    links = svc.gui_links(entry)
    if not links:
        raise click.ClickException(f"{entry.get('service')} has no web UI")
    for link in links:
        echo(f"  {link['label']:<24} {link['url']:<32} login: {link['login']}")
    if entry.get("target", {}).get("method") == "ssh":
        info(f"Does not open? pskit resources onprem gui {key} --check  "
             f"(or skip the firewall: pskit resources onprem tunnel {key} --remote-port {links[0]['port']})")


# ----------------------------------------------------------------------------- saved SSH servers


@resources_onprem.group("servers")
def resources_onprem_servers() -> None:
    """Saved SSH servers: name a machine once, then create services, install software, open shells and deploy to it.

    \b
    pskit resources onprem servers add edge1 --ssh ubuntu@10.0.0.5 --pem ~/.ssh/edge1.pem
    pskit resources onprem servers add lab --ssh root@192.168.1.20 --ssh-password-env LAB_PW
    pskit resources onprem servers test edge1
    pskit resources onprem create cache --service redis --server edge1
    pskit deploy --server edge1                 # or provider.options.deploy: {server: edge1}
    """


@resources_onprem_servers.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_servers_list(as_json: bool, config_path: Optional[str]) -> None:
    from ..core.onprem_servers import list_servers

    root, _path, _raw = _raw_project(config_path)
    servers = list_servers(root)
    if as_json:
        click.echo(json.dumps(servers, indent=2))
        return
    if not servers:
        info("No saved servers. Add one: pskit resources onprem servers add NAME --ssh user@host [--pem FILE]")
        return
    for item in servers:
        login = "password" if item.get("password_file") else ("key " + item["identity_file"]) if item.get(
            "identity_file") else "agent / default key"
        extra = "".join(f"  {k}={item[k]}" for k in ("home", "bind", "data_dir") if item.get(k))
        echo(f"  {item['name']:<16} {item['label']:<36} {login}{'  sudo' if item.get('sudo') else ''}{extra}")


@resources_onprem_servers.command("add")
@click.argument("name")
@click.option("--ssh", "ssh", required=True, help="user@host[:port]")
@click.option("--pem", default=None, help="Private key (empty: the SSH agent or your default key).")
@click.option("--ssh-password-env", default=None, help="Log in with the password in this variable (sshpass).")
@click.option("--ssh-password-file", default=None, help="Log in with the password in this file (sshpass).")
@click.option("--sudo", is_flag=True, help="Run docker / installs with sudo -n.")
@click.option("--description", default="", help="A note shown in the studio.")
@click.option("--home", default="", help="Where pskit keeps files there (default /opt/pskit; cluster files in ~).")
@click.option("--bind", default="", help="Address the functions and services listen on (0.0.0.0, 127.0.0.1 or an IP).")
@click.option("--data-dir", "data_dir", default="", help="Where data lives there (default: Docker volumes / the app).")
@click.option("--test/--no-test", "run_test", default=True, help="Log in once after saving (default: yes).")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_servers_add(  # noqa: PLR0913
    name: str, ssh: str, pem: Optional[str], ssh_password_env: Optional[str], ssh_password_file: Optional[str],
    sudo: bool, description: str, home: str, bind: str, data_dir: str, run_test: bool, config_path: Optional[str],
) -> None:
    """Save (or replace) server NAME.

    \b
    --home /srv/pskit --bind 10.0.0.5 --data-dir /data/pskit are this server's defaults: functions deploy to
    <home>/<service>-<stage> and listen on the bind address, services publish their port on it and keep their data
    in <data-dir>/<container>, a cluster master keeps the main replica's data in <data-dir>/<stack>.
    """
    from ..core import onprem_servers as srv

    root, _path, _raw = _raw_project(config_path)
    user, _, rest = ssh.rpartition("@")
    host, _, ssh_port = rest.partition(":")
    raw: dict = {"host": host, "user": user or "root", "port": int(ssh_port or 22), "sudo": sudo,
                 "home": home, "bind": bind, "data_dir": data_dir}
    if ssh_password_env:
        raw.update({"auth": "password", "password": _env_value(ssh_password_env)})
    elif ssh_password_file:
        raw.update({"auth": "password", "password_file": ssh_password_file})
    elif pem:
        raw.update({"auth": "key", "identity_file": pem})
    else:
        raw["auth"] = "agent"
    try:
        srv.save_server(root, name, raw, description=description)
    except srv.ServerError as exc:
        raise click.ClickException(str(exc)) from None
    ok(f"Saved server {name}")
    if run_test:
        _print_server_test(srv.test_server(root, name))


def _print_server_test(result: dict) -> None:
    if not result.get("ok"):
        raise click.ClickException(f"cannot use {result.get('name')}: {result.get('error')}")
    for key, value in result["facts"].items():
        echo(f"  {key:<14} {value or '-'}")
    ok(f"{result['name']} answers over SSH")


@resources_onprem_servers.command("check", short_help="Which saved servers answer on their SSH port (no login).")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_servers_check(config_path: Optional[str]) -> None:
    from ..core.onprem_servers import reachability

    root, _path, _raw = _raw_project(config_path)
    for name, item in sorted(reachability(root).items()):
        (ok if item["ok"] else warn)(f"{name}: " + (f"{item['ms']} ms" if item["ok"] else item["error"]))


@resources_onprem_servers.command("top", short_help="Live CPU, memory and disk use of a saved server.")
@click.argument("name")
@click.option("--watch", "every", type=int, default=0, help="Repeat every N seconds until Ctrl+C.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_servers_top(name: str, every: int, config_path: Optional[str]) -> None:
    import time

    from ..core.onprem_servers import ServerError, server_metrics

    root, _path, _raw = _raw_project(config_path)
    while True:
        try:
            m = server_metrics(root, name)
        except ServerError as exc:
            raise click.ClickException(str(exc)) from None
        if not m.get("reachable"):
            raise click.ClickException(f"{name}: {m.get('error')}")
        echo(f"{name}: CPU {m.get('cpu')}% of {m.get('cpus')}, memory {m.get('memory')}% of {m.get('memory_mb')} MB, "
             f"disk {m.get('disk')}% of {m.get('disk_gb')} GB, load {m.get('load')}")
        if not every:
            return
        time.sleep(max(1, every - 1))


@resources_onprem_servers.command("usage", short_help="Where each saved server is used (functions, clusters, ...).")
@click.argument("name", required=False)
@click.option("--json", "as_json", is_flag=True)
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_servers_usage(name: Optional[str], as_json: bool, config_path: Optional[str]) -> None:
    """Where saved server NAME (or every server) is used: deploy target, function groups, clusters, load
    balancers, services and installed software, with the functions behind each. Reads local files only."""
    from ..core.onprem_usage import describe, server_usage

    root, _path, raw = _raw_project(config_path)
    usage = server_usage(root, raw)
    if name:
        if name not in usage:
            raise click.ClickException(f"no saved server {name!r} (servers: {', '.join(usage) or 'none'})")
        usage = {name: usage[name]}
    if as_json:
        click.echo(json.dumps(usage, indent=2))
        return
    if not usage:
        info("No saved servers. Add one: pskit resources onprem servers add NAME --ssh user@host [--pem FILE]")
    for server, uses in usage.items():
        if not uses:
            echo(f"  {server}: not used anywhere")
            continue
        echo(f"  {server}:")
        for use in uses:
            echo(f"    - {describe(use)}")


@resources_onprem_servers.command("test")
@click.argument("name")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_servers_test(name: str, config_path: Optional[str]) -> None:
    """Log in and show the OS, CPU, memory, disk, Docker access, sudo and installed runtimes."""
    from ..core import onprem_servers as srv

    root, _path, _raw = _raw_project(config_path)
    try:
        _print_server_test(srv.test_server(root, name))
    except srv.ServerError as exc:
        raise click.ClickException(str(exc)) from None


@resources_onprem_servers.command("remove")
@click.argument("name")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_servers_remove(name: str, config_path: Optional[str]) -> None:
    """Forget server NAME (services already created there keep running)."""
    from ..core import onprem_servers as srv

    root, _path, raw = _raw_project(config_path)
    try:
        warnings = srv.remove_server(root, name, raw)
    except srv.ServerError as exc:
        raise click.ClickException(str(exc)) from None
    ok(f"Removed server {name}")
    for line in warnings:
        click.secho(f"  WARNING: {line}", fg="yellow")


# ----------------------------------------------------------------------------- consoles and terminals


@resources_onprem.command("console", short_help="Run commands in a service (redis-cli, psql, mongosh, rpk, ...).")
@click.argument("key")
@click.argument("command", nargs=-1)
@click.option("--shell", is_flag=True, help="A shell (sh) in the container instead of the service's client.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_console(key: str, command: tuple, shell: bool, config_path: Optional[str]) -> None:
    """Open the service's client in this terminal, or run one COMMAND and print the output.

    \b
    pskit resources onprem console cache                    # interactive redis-cli
    pskit resources onprem console cache "LLEN jobs"
    pskit resources onprem console orders-db "SELECT count(*) FROM orders;"
    pskit resources onprem console secrets "kv get secret/db-password"
    pskit resources onprem console cache --shell            # sh inside the container
    """
    from ..core import onprem_console as con

    root, _path, _raw = _raw_project(config_path)
    if command:
        try:
            result = con.run_line(root, key, " ".join(command), shell=shell)
        except (con.ConsoleError, Exception) as exc:  # noqa: BLE001 - ServiceError too
            raise click.ClickException(str(exc)) from None
        click.echo(result["output"].rstrip())
        raise SystemExit(result["exit_code"])
    import subprocess

    argv = _service_call(con.interactive_argv, root, key, shell=shell)
    raise SystemExit(subprocess.call(argv))  # noqa: S603


@resources_onprem.command("shell", short_help="A shell on a saved SSH server (or run one command there).")
@click.argument("server")
@click.argument("command", nargs=-1)
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_shell(server: str, command: tuple, config_path: Optional[str]) -> None:
    """SSH to SERVER with its saved login; with COMMAND, run it and print the output."""
    from ..core import onprem_console as con
    from ..core import onprem_servers as srv
    from ..core.onprem_services import _ssh_argv

    root, _path, _raw = _raw_project(config_path)
    try:
        target = srv.server_target(root, server)
    except srv.ServerError as exc:
        raise click.ClickException(str(exc)) from None
    if command:
        result = con.run_server(target, " ".join(command))
        click.echo(result["output"].rstrip())
        raise SystemExit(result["exit_code"])
    import subprocess

    argv = _ssh_argv(target, "")[:-1]
    if "BatchMode=yes" in argv:                      # an interactive login may ask for a key passphrase
        i = argv.index("BatchMode=yes")
        del argv[i - 1:i + 1]
    argv.insert(argv.index("ssh") + 1, "-t")
    raise SystemExit(subprocess.call(argv))  # noqa: S603


@resources_onprem.command("terminal", short_help="A full terminal in the browser (Docker): a server or a service.")
@click.argument("key", required=False)
@click.option("--server", "server", default=None, help="SSH to this saved server.")
@click.option("--shell", is_flag=True, help="With KEY: sh in the container instead of the service's client.")
@click.option("--list", "list_them", is_flag=True, help="Show running terminals.")
@click.option("--stop", "stop", default=None, help="Stop a terminal by name (pskit-term-7681), or 'all'.")
@click.option("--open/--no-open", "open_browser", default=True, help="Open it in the browser.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_terminal(  # noqa: PLR0913
    key: Optional[str], server: Optional[str], shell: bool, list_them: bool, stop: Optional[str], open_browser: bool,
    config_path: Optional[str],
) -> None:
    """ttyd in Docker on 127.0.0.1 (secret URL): an SSH session to a server, or the client / sh of a service.

    \b
    pskit resources onprem terminal --server edge1
    pskit resources onprem terminal cache            # redis-cli in the browser
    pskit resources onprem terminal --list
    pskit resources onprem terminal --stop all
    """
    from ..core import onprem_terminal as term

    if list_them or stop:
        running = term.list_terminals()
        for item in running:
            if stop in ("all", item["name"]):
                term.stop_terminal(item["name"])
                ok(f"Stopped {item['name']}")
            elif list_them:
                echo(f"  {item['name']:<18} {item['title']:<36} {item['status']}")
        if list_them and not running:
            info("No terminals running.")
        return
    if not key and not server:
        raise click.ClickException("give a service KEY or --server NAME")
    root, _path, _raw = _raw_project(config_path)
    try:
        result = term.start_terminal(root, echo, server=server, key=key, shell=shell)
    except (term.TerminalError, Exception) as exc:  # noqa: BLE001 - ServiceError / ServerError too
        raise click.ClickException(str(exc)) from None
    ok(f"Open {result['url']}  (stop: pskit resources onprem terminal --stop {result['name']})")
    if open_browser:
        import webbrowser

        webbrowser.open(result["url"])


@resources_onprem.command("ssh-key", short_help="Install an SSH key on a server that takes a password (once).")
@click.argument("destination")
@click.option("--key", "key_path", default=None, help="Key to install (default: ~/.ssh/pskit_ed25519, created if missing).")
@click.option("--password-env", default=None, help="Send the password from this variable (needs sshpass); default: asked.")
def resources_onprem_ssh_key(destination: str, key_path: Optional[str], password_env: Optional[str]) -> None:
    """Log in to DESTINATION (user@host[:port]) with its password once and install a key, then use the key.

    \b
    pskit resources onprem ssh-key azureuser@13.72.87.80
    pskit resources onprem create jobs --service elasticmq --ssh azureuser@13.72.87.80 --pem ~/.ssh/pskit_ed25519

    Works on Windows too (no sshpass needed: ssh asks the password in this terminal).
    """
    from ..core import onprem_services as svc

    user, _, rest = destination.rpartition("@")
    host, _, ssh_port = rest.partition(":")
    target = {"method": "ssh", "user": user or "root", "host": host, "port": int(ssh_port or 22)}
    password = _env_value(password_env) if password_env else ""
    path = _service_call(svc.install_ssh_key, target, echo, key_path=key_path, password=password)
    ok(f"Key login works. Use --pem {path} (studio: Private key), or in pskit.yml: provider.options.deploy.pem: {path}")


@resources_onprem.command("logs", short_help="The service container's recent output.")
@click.argument("key")
@click.option("-n", "--tail", default=200, show_default=True)
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_logs(key: str, tail: int, config_path: Optional[str]) -> None:
    from ..core.onprem_services import logs

    root, _path, _raw = _raw_project(config_path)
    click.echo(_service_call(logs, root, key, tail=tail))


@resources_onprem.command("backup", short_help="Dump a service's data to .pskit/backups.")
@click.argument("key")
@click.option("-o", "--output", default=None, help="File to write (default: .pskit/backups/<key>-<time>.<ext>).")
@click.option("-d", "--dir", "folder", default=None, type=click.Path(file_okay=False),
              help="Folder to write <key>-<time>.<ext> into (created when missing).")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_backup(key: str, output: Optional[str], folder: Optional[str], config_path: Optional[str]) -> None:
    import time

    from ..core.onprem_services import SERVICES, _entry, backup

    root, _path, _raw = _raw_project(config_path)
    dest = Path(output).resolve() if output else None
    if folder and not output:
        spec = SERVICES.get(str(_service_call(_entry, root, key).get("service"))) or {}
        Path(folder).mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        dest = Path(folder).resolve() / f"{key}-{stamp}.{spec.get('backup_ext') or 'dump'}"
    saved = _service_call(backup, root, key, echo, dest=dest)
    ok(f"Backup written to {saved}")


@resources_onprem.command("remove", short_help="Stop and delete a service container.")
@click.argument("key")
@click.option("--delete-data", is_flag=True, help="Also delete its data volume.")
@click.option("--save", is_flag=True, help="Also remove the resource and its triggers from pskit.yml.")
@click.option("-y", "--yes", is_flag=True, help="Do not ask for confirmation.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def resources_onprem_remove(key: str, delete_data: bool, save: bool, yes: bool, config_path: Optional[str]) -> None:
    from ..core import onprem_services as svc

    root, path, raw = _raw_project(config_path)
    if not yes:
        what = "the container and its data" if delete_data else "the container (data is kept)"
        click.confirm(f"Delete {what} of {key}?", abort=True)
    _service_call(svc.remove, root, key, echo, delete_data=delete_data)
    if save:
        _save_raw(path, svc.remove_from_raw(raw, key))
    ok(f"Removed {key}")


# ----------------------------------------------------------------------------- cluster
@cli.group(short_help="Scale on-prem functions over several servers (Swarm, Kubernetes, Nomad).")
def cluster() -> None:
    """Run on-prem functions on a master server plus joined servers: Docker Swarm, Kubernetes (k3s) or Nomad.

    \b
    Examples:
      pskit cluster create prod --orchestrator swarm --master edge1
      pskit cluster join prod edge2                # also while functions are running
      pskit cluster set prod --no-master-serves    # master only as a backup; joined servers take the requests
      pskit cluster status prod                    # CPU / memory / disk of every server, replicas, full?
      pskit cluster alerts prod --function notify-devops --webhook https://hooks.slack.com/...
      pskit cluster watch prod                     # check every minute, alert when every server is full
      pskit cluster scale prod --replicas 6
      pskit cluster requests prod --follow          # which server handled each request, live
      pskit cluster leave prod edge2
      pskit cluster remove prod --uninstall        # uninstall from the master and every server, then forget
      pskit cluster balancer set prod lb1          # one URL (OpenResty on lb1) for every server
      pskit lb attach edge --cluster prod          # or a shared load balancer: http://<edge>/<service>/

    Functions use it with provider.options.cluster in pskit.yml (cluster: prod, or {name: prod, replicas: 3}),
    or per deploy: pskit deploy --cluster prod (the stage remembers it; pskit deploy --server NAME goes back to one
    server). Resources run on one server of it: pskit resources onprem create cache --service redis --cluster prod.
    Saved servers come from: pskit resources onprem servers add.
    """


def _cluster_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    from ..core.onprem_cluster import ClusterError
    from ..core.onprem_services import ServiceError

    try:
        return fn(*args, **kwargs)
    except (ClusterError, ServiceError) as exc:
        raise click.ClickException(str(exc)) from None


def _cluster_root(config_path: Optional[str]) -> Path:
    root, _path, _raw = _raw_project(config_path)
    return root


_CONFIG_OPTION = click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
_ALGORITHM_OPTION = click.option(
    "--algorithm", default=None,
    help="round_robin, sticky_round_robin, weighted_round_robin, ip_hash, least_connections or least_time"
         " (pskit lb algorithms explains each).")
_WEIGHT_OPTION = click.option(
    "--weight", "weights", multiple=True, metavar="SERVER=N",
    help="Weight 1..100 of a saved server (weighted round robin, least connections, least time). Repeat it.")


def _weights(values: Tuple[str, ...]) -> Optional[Dict[str, int]]:
    if not values:
        return None
    out: Dict[str, int] = {}
    for value in values:
        server, sep, number = value.partition("=")
        if not sep or not server.strip() or not number.strip().isdigit():
            raise click.BadParameter(f"{value!r}: use SERVER=N, for example edge1=3", param_hint="--weight")
        out[server.strip()] = int(number)
    return out


@cluster.command("list")
@click.option("--json", "as_json", is_flag=True)
@_CONFIG_OPTION
def cluster_list(as_json: bool, config_path: Optional[str]) -> None:
    """Clusters, their servers and deployments."""
    from ..core.onprem_cluster import list_clusters

    items = list_clusters(_cluster_root(config_path))
    if as_json:
        click.echo(json.dumps(items, indent=2))
        return
    if not items:
        info("No clusters. Create one: pskit cluster create NAME --orchestrator swarm --master SERVER")
        return
    for item in items:
        master = " (master)" if item.get("master_serves") else " (master, backup only)"
        servers = ", ".join(f"{n['server']}{master if n.get('role') == 'master' else ''}" for n in item["nodes"])
        echo(f"  {item['name']:<14} {item['orchestrator_label']:<18} {servers}")
        balancer = item.get("balancer") or {}
        if balancer:
            echo(f"      load balancer: {balancer['server']} ({balancer.get('address')}, port {balancer.get('port')})")
        for stack, dep in sorted(item["deployments"].items()):
            url = (balancer.get("urls") or {}).get(stack)
            echo(f"      {stack}: {dep.get('replicas')} replica(s) {url or dep.get('endpoint')}")


@cluster.command("create")
@click.argument("name")
@click.option("--orchestrator", "-o", type=click.Choice(["swarm", "kubernetes", "nomad"]), required=True)
@click.option("--master", required=True, help="Saved server that runs the control plane and the main replica.")
@click.option("--advertise", default="", help="The master's address other servers use (default: its host).")
@click.option("--nomad-version", default="", help="Nomad release to install (default: the tested one).")
@click.option("--master-serves/--no-master-serves", "master_serves", default=None,
              help="Send requests to the master too, next to the joined servers. Off: the master is only a backup, "
                   "used while every other server is down. Default: off on Nomad, on on Swarm and k3s.")
@_CONFIG_OPTION
def cluster_create(name: str, orchestrator: str, master: str, advertise: str, nomad_version: str,
                   master_serves: Optional[bool], config_path: Optional[str]) -> None:
    """Install the orchestrator on MASTER and save cluster NAME."""
    from ..core.onprem_cluster import create_cluster

    _cluster_call(create_cluster, _cluster_root(config_path), name, orchestrator, master, echo, advertise=advertise,
                  nomad_version=nomad_version, serve_on_master=master_serves)
    ok(f"Cluster {name} created. In pskit.yml: provider.options.cluster: {name}")


@cluster.command("set")
@click.argument("name")
@click.option("--master-serves/--no-master-serves", "master_serves", default=None,
              help="Send requests to the master too (on), or use it only while every other server is down (off).")
@_CONFIG_OPTION
def cluster_set(name: str, master_serves: Optional[bool], config_path: Optional[str]) -> None:
    """Change how cluster NAME spreads requests. The load balancers follow at once; Swarm and k3s move web
    replicas on or off the master at the next pskit deploy."""
    from ..core.onprem_cluster import set_master_serves

    if master_serves is None:
        raise click.UsageError("nothing to change: pass --master-serves or --no-master-serves")
    _cluster_call(set_master_serves, _cluster_root(config_path), name, master_serves, echo)
    ok(f"{name}: the master {'serves requests' if master_serves else 'is only a backup'}")


@cluster.command("join")
@click.argument("name")
@click.argument("server")
@click.option("--advertise", default="", help="This server's address in the cluster network (default: its host).")
@_CONFIG_OPTION
def cluster_join(name: str, server: str, advertise: str, config_path: Optional[str]) -> None:
    """Add saved SERVER to cluster NAME (installs the agent and copies the deployed images)."""
    from ..core.onprem_cluster import join_server

    _cluster_call(join_server, _cluster_root(config_path), name, server, echo, advertise=advertise)
    ok(f"{server} joined {name}")


@cluster.command("leave")
@click.argument("name")
@click.argument("server")
@click.option("--yes", is_flag=True, help="Do not ask.")
@_CONFIG_OPTION
def cluster_leave(name: str, server: str, yes: bool, config_path: Optional[str]) -> None:
    """Drain SERVER (replicas move to the others) and remove it from cluster NAME."""
    from ..core.onprem_cluster import leave_server

    if not yes:
        click.confirm(f"Remove {server} from cluster {name}?", abort=True)
    _cluster_call(leave_server, _cluster_root(config_path), name, server, echo)
    ok(f"{server} left {name}")


def _print_cluster_status(current: dict) -> None:
    def pct(value: Any) -> str:
        return "-" if value is None else f"{value:.0f}%"

    cap = current["capacity"]
    echo(f"  {'server':<14} {'role':<7} {'state':<9} {'cpu':>5} {'mem':>5} {'disk':>5}  load")
    for n in current["nodes"]:
        if not n.get("reachable"):
            echo(f"  {n['server']:<14} {n.get('role') or '':<7} {'offline':<9}  {n.get('error', '')}")
            continue
        flag = "  FULL (" + ", ".join(n["over"]) + ")" if n["full"] else ""
        state = n.get("state") or ""
        if n.get("availability") and n["availability"] != "Active":
            state = n["availability"]
        echo(f"  {n['server']:<14} {n.get('role') or '':<7} {state:<9} {pct(n.get('cpu')):>5} {pct(n.get('memory')):>5}"
             f" {pct(n.get('disk')):>5}  {n.get('load', '')}{flag}")
    lb = current.get("balancer")
    if lb:
        if not lb.get("reachable"):
            echo(f"  {lb['server']:<14} {'lb':<7} {'offline':<9}  {lb.get('error', '')}")
        else:
            echo(f"  {lb['server']:<14} {'lb':<7} {'nginx ' + str(lb.get('state')):<9} {pct(lb.get('cpu')):>5}"
                 f" {pct(lb.get('memory')):>5} {pct(lb.get('disk')):>5}  {lb.get('load', '')}")
        for stack, url in sorted((lb.get("urls") or {}).items()):
            echo(f"  balancer {stack}: {url}")
        if not lb.get("running"):
            fail(f"the load balancer on {lb['server']} is not running: pskit cluster balancer sync {current['name']}")
    echo(f"  limits: cpu {cap['cpu']}%  memory {cap['memory']}%  disk {cap['disk']}%")
    for w in current["workloads"]:
        echo(f"  workload {w['name']}: {w['running']}/{w['desired']} running")
    for r in current.get("resources") or []:
        echo(f"  resource {r['key']} ({r['service']}) on {r['server']}  {r.get('address') or ''}:{r.get('port') or ''}")
    for item in current["pending"]:
        echo(f"  pending  {item}")
    if current["full"]:
        fail("FULL: " + "; ".join(current["reasons"]) + f". Add a server: pskit cluster join {current['name']} SERVER")
    else:
        ok("capacity left on at least one server")
    sent = current.get("alert")
    if sent:
        echo(f"  alert: {json.dumps(sent)}")


@cluster.command("status")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@_CONFIG_OPTION
def cluster_status(name: str, as_json: bool, config_path: Optional[str]) -> None:
    """Every server's CPU, memory and disk, the replicas, and whether the cluster is full."""
    from ..core.onprem_cluster import status

    current = _cluster_call(status, _cluster_root(config_path), name)
    if as_json:
        click.echo(json.dumps(current, indent=2))
        return
    _print_cluster_status(current)


@cluster.command("check")
@click.argument("name")
@click.option("--alert/--no-alert", default=True, help="Send the alert when the cluster is full (default: yes).")
@_CONFIG_OPTION
def cluster_check(name: str, alert: bool, config_path: Optional[str]) -> None:
    """Status once; when full, call the alert function / webhook (respecting the cooldown). Exit 3 when full."""
    from ..core.onprem_cluster import check

    current = _cluster_call(check, _cluster_root(config_path), name, alert=alert)
    _print_cluster_status(current)
    if current["full"]:
        raise SystemExit(3)


@cluster.command("watch")
@click.argument("name")
@click.option("--interval", default=60, show_default=True, type=click.IntRange(15, 86400), help="Seconds.")
@_CONFIG_OPTION
def cluster_watch(name: str, interval: int, config_path: Optional[str]) -> None:
    """Check every INTERVAL seconds until Ctrl+C (run it on an always-on machine, e.g. a systemd unit)."""
    import time

    from ..core.onprem_cluster import check

    root = _cluster_root(config_path)
    while True:
        echo(time.strftime("%Y-%m-%d %H:%M:%S"))
        try:
            _print_cluster_status(_cluster_call(check, root, name))
        except click.ClickException as exc:
            fail(exc.message)
        time.sleep(interval)


@cluster.command("alerts")
@click.argument("name")
@click.option("--function", "function", default=None, help="Function called with the capacity event (\"\" clears).")
@click.option("--stage", default=None, help="Stage whose deployed host runs it (default: any deployed stage).")
@click.option("--webhook", default=None, help="Also POST the event here (Slack / Teams / any URL; \"\" clears).")
@click.option("--cooldown", default=None, type=int, help="Minutes between two alerts (default 30).")
@click.option("--cpu", default=None, type=int, help="A server is full at this CPU percent (default 85).")
@click.option("--memory", default=None, type=int, help="... memory percent (default 85).")
@click.option("--disk", default=None, type=int, help="... disk percent (default 90).")
@click.option("--test", is_flag=True, help="Send a test alert now.")
@_CONFIG_OPTION
def cluster_alerts(name: str, function: Optional[str], stage: Optional[str], webhook: Optional[str],
                   cooldown: Optional[int], cpu: Optional[int], memory: Optional[int], disk: Optional[int], test: bool,
                   config_path: Optional[str]) -> None:
    """Who hears about a full cluster, and when a server counts as full."""
    from ..core import onprem_cluster as clu

    root = _cluster_root(config_path)
    alert = {k: v for k, v in (("function", function), ("stage", stage), ("webhook", webhook),
                               ("cooldown_minutes", cooldown)) if v is not None}
    capacity = {k: v for k, v in (("cpu", cpu), ("memory", memory), ("disk", disk)) if v is not None}
    item = _cluster_call(clu.save_settings, root, name, {"alert": alert, "capacity": capacity})
    a, cap = item["alert"], item["capacity"]
    echo(f"  function {a['function'] or '-'}  stage {a['stage'] or 'any'}  webhook {a['webhook'] or '-'}"
         f"  cooldown {a['cooldown_minutes']} min")
    echo(f"  full at: cpu {cap['cpu']}%  memory {cap['memory']}%  disk {cap['disk']}%")
    if test:
        result = _cluster_call(clu.send_alert, root, name, {"orchestrator": item["orchestrator"]}, test=True)
        if result["errors"]:
            raise click.ClickException("; ".join(result["errors"]))
        ok("Test alert sent to " + ", ".join(result["sent"]))


@cluster.command("requests")
@click.argument("name")
@click.option("--stack", default=None, help="The deployment (default: the first one on the cluster).")
@click.option("-f", "--follow", is_flag=True, help="Keep printing new requests until Ctrl+C.")
@click.option("-n", "--lines", default=50, type=click.IntRange(1, 500), help="How many recent requests first.")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
def cluster_requests(name: str, stack: Optional[str], follow: bool, lines: int, config_path: Optional[str]) -> None:
    """Recent requests of one deployment, and how HTTP is spread across each server (live with --follow)."""
    import time

    from ..core import onprem_cluster as clu
    from ..core.onprem_control import HostUnavailable

    def show_balance(page: dict, totals: dict) -> None:
        balance = page.get("balance") or {}
        rows = balance.get("servers") or []
        if not rows:
            return
        echo(str(balance.get("note") or ""))
        echo(f"  {'server':<16} {'serves':<6} {'requests':>8} {'share':>7}  url")
        total = sum(totals.values())
        for row in rows:
            count = int(totals.get(row.get("server") or "", 0))
            share = round(100.0 * count / total, 1) if total else 0.0
            echo(f"  {str(row.get('server') or ''):<16} {str(row.get('serves') or ''):<6} {count:>8} {share:>6.1f}%"
                 f"  {row.get('url') or ''}")

    root = _cluster_root(config_path)
    since = 0
    totals: dict = {}
    first = True
    try:
        while True:
            try:
                page = _cluster_call(clu.requests_feed, root, name, stack or "", since, lines if not since else 500)
            except (HostUnavailable, PermissionError, KeyError) as exc:
                raise click.ClickException(str(exc)) from None
            fresh = False
            rendered = []
            for r in page["items"]:
                if r.get("method"):
                    key = str(r.get("server") or "")
                    totals[key] = totals.get(key, 0) + 1
                    fresh = True
                what = f"{r.get('method')} {r.get('path')}" if r.get("method") else str(r.get("event_type") or "")
                rendered.append(
                    f"  {str(r.get('ts') or '')[11:19]}  {r.get('server') or '-':<12} {r.get('replica') or '-':<22}"
                    f" {str(r.get('status') or ''):>3} {r.get('duration_ms') or 0:>8} ms  {r.get('function')}: {what}"
                )
            if first or fresh:
                show_balance(page, totals)
                first = False
            for line in rendered:
                echo(line)
            since = int(page.get("next") or since)
            if not follow:
                return
            time.sleep(2)
    except KeyboardInterrupt:
        pass


@cluster.command("scale")
@click.argument("name")
@click.option("--replicas", required=True, type=click.IntRange(0, 500))
@click.option("--stack", default=None, help="Deployment (default: this project's stage, pskit-<service>-<stage>).")
@click.option("-s", "--stage", default=None, help="Stage of this project (default: the configured stage).")
@_CONFIG_OPTION
def cluster_scale(name: str, replicas: int, stack: Optional[str], stage: Optional[str],
                  config_path: Optional[str]) -> None:
    """Set the web replicas now (until the next deploy; keep it in options.cluster.replicas)."""
    from ..core import onprem_cluster as clu
    from ..core.onprem_cluster_scripts import stack_name

    root, _path, raw = _raw_project(config_path)
    if not stack:
        provider = raw.get("provider") or {}
        stack = stack_name(str(raw.get("service") or ""), str(stage or provider.get("stage") or "dev"))
    _cluster_call(clu.scale, root, name, stack, replicas, echo)


@cluster.command("remove")
@click.argument("name")
@click.option("--uninstall", is_flag=True,
              help="Also take off what pskit installed: deployments, load balancer, the agent on every joined server"
                   " and the orchestrator on the master.")
@click.option("--delete-data", is_flag=True, help="With --uninstall: also delete the main replicas' data on the master.")
@click.option("--yes", is_flag=True, help="Do not ask.")
@_CONFIG_OPTION
def cluster_remove(name: str, uninstall: bool, delete_data: bool, yes: bool, config_path: Optional[str]) -> None:
    """Forget cluster NAME (the servers and anything running on them are left as they are).

    With --uninstall the deployments stop and Docker Swarm / k3s / Nomad is removed from the master and every
    joined server first. Docker itself and the saved servers stay.
    """
    from ..core.onprem_cluster import remove_cluster

    if delete_data and not uninstall:
        raise click.UsageError("--delete-data needs --uninstall")
    if not yes:
        question = (f"Uninstall cluster {name} from all its servers (its deployments stop"
                    + (" and their data is deleted" if delete_data else "") + ")?") if uninstall else \
            f"Forget cluster {name}?"
        click.confirm(question, abort=True)
    _cluster_call(remove_cluster, _cluster_root(config_path), name, echo, uninstall=uninstall, delete_data=delete_data)


@cluster.group("balancer")
def cluster_balancer() -> None:
    """A load balancer in front of the cluster: one more saved server (outside the cluster) running OpenResty.

    \b
    Examples:
      pskit cluster balancer set prod lb1             # http://<lb1>/ spreads over the cluster's servers
      pskit cluster balancer set prod lb1 --port 8000 --algorithm least_time
      pskit cluster balancer set prod lb1 --algorithm weighted_round_robin --weight edge1=3 --weight edge2=1
      pskit cluster balancer logs prod -n 200         # one line per request, with the server that answered
      pskit cluster balancer sync prod                # rewrite its config now (deploy / join / leave do it)
      pskit cluster balancer remove prod

    pskit deploy, pskit remove, cluster join and cluster leave update it. Logs, tests and the admin API keep
    using the master. A second deployment on the same cluster needs its own port:
    provider.options.cluster.balancer_port. To share one load balancer by path between clusters and projects,
    use pskit lb instead. Algorithms and their trade-offs: pskit lb algorithms.
    """


@cluster_balancer.command("set")
@click.argument("name")
@click.argument("server")
@click.option("--port", default=80, show_default=True, type=click.IntRange(1, 65535),
              help="Port users call on the load balancer.")
@click.option("--address", default="", help="Its address in the URL users call (default: the server's host).")
@_ALGORITHM_OPTION
@_WEIGHT_OPTION
@_CONFIG_OPTION
def cluster_balancer_set(name: str, server: str, port: int, address: str, algorithm: Optional[str],
                         weights: Tuple[str, ...], config_path: Optional[str]) -> None:
    """Make saved SERVER the load balancer of cluster NAME (installs Docker and OpenResty there)."""
    from ..core.onprem_cluster import set_balancer

    item = _cluster_call(set_balancer, _cluster_root(config_path), name, server, echo, port=port, address=address,
                         algorithm=algorithm, weights=_weights(weights))
    ok(f"{server} is the load balancer of {name}")
    for stack, url in sorted((item.get("balancer") or {}).get("urls", {}).items()):
        echo(f"  {stack}: {url}")


@cluster_balancer.command("remove")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Do not ask.")
@_CONFIG_OPTION
def cluster_balancer_remove(name: str, yes: bool, config_path: Optional[str]) -> None:
    """Stop the load balancer of cluster NAME (the functions keep running on the cluster)."""
    from ..core.onprem_cluster import remove_balancer

    if not yes:
        click.confirm(f"Stop the load balancer of cluster {name}? Its URL stops answering.", abort=True)
    _cluster_call(remove_balancer, _cluster_root(config_path), name, echo)


@cluster_balancer.command("sync")
@click.argument("name")
@_CONFIG_OPTION
def cluster_balancer_sync(name: str, config_path: Optional[str]) -> None:
    """Rewrite the load balancer's config from the cluster's servers and deployments."""
    from ..core.onprem_cluster import sync_balancer

    _cluster_call(sync_balancer, _cluster_root(config_path), name, echo, strict=True)
    ok("load balancer updated")


@cluster_balancer.command("logs")
@click.argument("name")
@click.option("-n", "--lines", default=100, show_default=True, type=click.IntRange(1, 10000))
@_CONFIG_OPTION
def cluster_balancer_logs(name: str, lines: int, config_path: Optional[str]) -> None:
    """The load balancer's recent requests (upstream= is the server that answered) and errors."""
    from ..core.onprem_cluster import balancer_logs

    click.echo(_cluster_call(balancer_logs, _cluster_root(config_path), name, lines).rstrip("\n"))


# ----------------------------------------------------------------------------- functions
@cli.group("function", short_help="Give a function its own folder, code and requirements.txt.")
def function_group() -> None:
    """Functions as sub-projects: functions/<name>/ with their own code and requirements.txt, so a server of
    provider.options.placement gets only the code and dependencies of the functions it runs.

    \b
    Examples:
      pskit function split get-item
      pskit function split --all --dry-run
    """


@function_group.command("split")
@click.argument("names", nargs=-1)
@click.option("--all", "split_all", is_flag=True, help="Every function that shares a code file with another.")
@click.option("--dry-run", is_flag=True, help="Only show what would move.")
@_CONFIG_OPTION
def function_split(names: Tuple[str, ...], split_all: bool, dry_run: bool, config_path: Optional[str]) -> None:
    """Move functions out of a shared code file into functions/<name>/handler.py with their own requirements.txt.

    \b
    Examples:
      pskit function split get-item
      pskit function split --all --dry-run

    The helpers and imports the function uses are copied; the function is removed from the shared file unless code
    there still calls it; its handler in pskit.yml is updated; requirements.txt gets the project requirements its
    imports name.
    """
    from ..core import function_split as fsplit

    root = _cluster_root(config_path)
    if split_all:
        names = tuple(n for group in fsplit.shared_in_project(root).values() for n in group)
        if not names:
            echo("Every function already has its own folder (or its own code file).")
            return
    if not names:
        raise click.UsageError("name a function, or use --all")
    for name in names:
        try:
            result = (fsplit.plan if dry_run else fsplit.split)(root, name)
        except fsplit.SplitError as exc:
            raise click.ClickException(str(exc)) from None
        for line in fsplit.describe(result):
            echo(("would move " if dry_run and line == fsplit.describe(result)[0] else "") + line)


# ----------------------------------------------------------------------------- firewall
@cli.command(short_help="Ports each on-prem server must open (inbound / outbound), with server names.")
@click.option("--server", "only", default="", help="Only this server (name or address).")
@click.option("--json", "as_json", is_flag=True)
@_CONFIG_OPTION
def firewall(only: str, as_json: bool, config_path: Optional[str]) -> None:
    """The firewall rules this project's on-prem servers need now: deployments, function groups, clusters, load
    balancers and resources, per server, with who connects and why, and ufw commands.

    \b
    Examples:
      pskit firewall
      pskit firewall --server edge2
      pskit firewall --json

    Each step also prints the rules it adds (cluster create / join, deploy, lb create / attach, resources onprem
    create). REQUIRED: it does not work without it; NEEDED: for that feature; optional: pskit falls back to SSH.
    Every role and port: docs/onprem-network.md.
    """
    from ..core import onprem_network as network

    servers = network.by_server(network.project(_cluster_root(config_path)))
    if only:
        servers = [s for s in servers if only in (s["server"], s["address"])]
    if as_json:
        click.echo(json.dumps(servers, indent=2))
        return
    if not servers:
        echo("Nothing on premises yet (deploy, create a cluster or a load balancer first).")
        return
    rules = [r for s in servers for r in s["rules"]]
    for line in network.lines("this project", rules):
        echo(line)


# ----------------------------------------------------------------------------- load balancers
@cli.group("lb", short_help="Shared on-prem load balancers: one URL, a path per project or cluster.")
def lb_group() -> None:
    """Load balancers shared by projects and clusters: http://<lb>/xyz/, http://<lb>/abc/, ...

    \b
    Examples:
      pskit lb algorithms                              # the 6 algorithms, static / dynamic, pros and cons
      pskit lb create edge --server lb1 --algorithm least_time
      pskit lb attach edge --cluster prod               # every deployment on prod: http://<lb1>/<service>/
      pskit lb status edge                              # its routes (all projects), health, server use
      pskit lb update edge --algorithm weighted_round_robin --weight app1=3 --weight app2=1
      pskit lb routes remove edge xyz
      pskit lb logs edge -n 200
      pskit lb remove edge

    A project puts itself on one in pskit.yml: provider.options.balancer: edge (path: the service name), or
    {name: edge, path: xyz, algorithm: sticky_round_robin}. pskit deploy updates its route, pskit remove drops it.
    Routes are kept on the load balancer server, so projects in other folders or on other machines share it:
    there, pskit lb create edge --server lb1 finds the running one and adds it.
    """


def _lb_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    from ..core.onprem_balancers import BalancerError
    from ..core.onprem_cluster import ClusterError
    from ..core.onprem_services import ServiceError

    try:
        return fn(*args, **kwargs)
    except (BalancerError, ClusterError, ServiceError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None


@lb_group.command("algorithms")
@click.option("--json", "as_json", is_flag=True)
def lb_algorithms(as_json: bool) -> None:
    """The load balancing algorithms: how each picks a server, static or dynamic, pros, cons, when to use it."""
    from ..core.onprem_lb import DEFAULT_ALGORITHM, catalog

    items = catalog()
    if as_json:
        click.echo(json.dumps(items, indent=2))
        return
    for kind, title in (("static", "Static: the rule is fixed, live load is not measured"),
                        ("dynamic", "Dynamic: decided per request from live measurements")):
        echo(click.style(title, bold=True))
        for item in (i for i in items if i["kind"] == kind):
            default = " (default)" if item["name"] == DEFAULT_ALGORITHM else ""
            echo(f"  {click.style(item['name'], fg='cyan')}{default}: {item['summary']}")
            for pro in item["pros"]:
                echo(f"      + {pro}")
            for con in item["cons"]:
                echo(f"      - {con}")
            echo(f"      best for: {item['best_for']}")
        echo("")


@lb_group.command("create")
@click.argument("name")
@click.option("--server", required=True, help="Saved server that runs it (outside the clusters it serves).")
@click.option("--port", default=None, type=click.IntRange(1, 65535), help="Port users call (default 80).")
@click.option("--address", default="", help="Its address in the URLs (default: the server's host).")
@_ALGORITHM_OPTION
@_WEIGHT_OPTION
@_CONFIG_OPTION
def lb_create(name: str, server: str, port: Optional[int], address: str, algorithm: Optional[str],
              weights: Tuple[str, ...], config_path: Optional[str]) -> None:
    """Make saved SERVER load balancer NAME (Docker and OpenResty there), or add the one already running there."""
    from ..core.onprem_balancers import create_balancer

    item = _lb_call(create_balancer, _cluster_root(config_path), name, server, echo, port=port, address=address,
                    algorithm=algorithm, weights=_weights(weights))
    ok(f"load balancer {name}: {item['url']} ({item['algorithm_label']}, {item['kind']})")


@lb_group.command("update")
@click.argument("name")
@click.option("--port", default=None, type=click.IntRange(1, 65535))
@click.option("--address", default=None)
@_ALGORITHM_OPTION
@_WEIGHT_OPTION
@_CONFIG_OPTION
def lb_update(name: str, port: Optional[int], address: Optional[str], algorithm: Optional[str],
              weights: Tuple[str, ...], config_path: Optional[str]) -> None:
    """Change the port, default algorithm, weights or address (routes on the default algorithm switch too)."""
    from ..core.onprem_balancers import update_balancer

    item = _lb_call(update_balancer, _cluster_root(config_path), name, echo, port=port, address=address,
                    algorithm=algorithm, weights=_weights(weights))
    ok(f"load balancer {name}: {item['url']} ({item['algorithm_label']})")


@lb_group.command("list")
@click.option("--json", "as_json", is_flag=True)
@_CONFIG_OPTION
def lb_list(as_json: bool, config_path: Optional[str]) -> None:
    """Load balancers this project uses."""
    from ..core.onprem_balancers import list_balancers

    items = list_balancers(_cluster_root(config_path))
    if as_json:
        click.echo(json.dumps(items, indent=2))
        return
    if not items:
        echo("No load balancers yet: pskit lb create NAME --server SERVER")
        return
    for item in items:
        clusters = f", clusters: {', '.join(item['clusters'])}" if item["clusters"] else ""
        echo(f"  {item['name']}: {item['url']} on {item['server']} ({item['algorithm_label']}{clusters})")


@lb_group.command("status")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@_CONFIG_OPTION
def lb_status(name: str, as_json: bool, config_path: Optional[str]) -> None:
    """Whether it runs, its server's use, and every route on it (from every project)."""
    from ..core.onprem_balancers import status

    current = _lb_call(status, _cluster_root(config_path), name)
    if as_json:
        click.echo(json.dumps(current, indent=2))
        return
    state = current.get("state")
    echo(f"{name}: {current['url']} on {current['server']} - {state}, default {current['algorithm_label']}")
    if current.get("reachable") is False:
        fail(f"{current['server']} does not answer: {current.get('error')}")
    if current.get("cpu") is not None:
        echo(f"  server: cpu {current.get('cpu')}%, memory {current.get('memory')}%, disk {current.get('disk')}%")
    if current.get("drift"):
        echo("  note: another project changed its settings; pskit lb sync takes them from this project again")
    for route in current.get("routes") or []:
        mark = "" if route.get("mine") else " (another project)"
        inherit = " (default)" if route.get("inherits") else ""
        servers = ", ".join(b.get("server") or b["address"] for b in route.get("backends") or [])
        echo(f"  {route['url']} -> {route['owner']}{mark}: {route['effective_algorithm']}{inherit} over {servers}")
    if not current.get("routes"):
        echo("  no routes yet: pskit lb attach NAME --cluster CLUSTER, or provider.options.balancer in pskit.yml")
    if state != "running":
        fail(f"load balancer {name} is not running: pskit lb sync {name}")


@lb_group.command("attach")
@click.argument("name")
@click.option("--cluster", "cluster_name", required=True, help="Cluster whose deployments it serves.")
@_CONFIG_OPTION
def lb_attach(name: str, cluster_name: str, config_path: Optional[str]) -> None:
    """Serve every deployment of a cluster on load balancer NAME (http://<lb>/<service>/), now and on deploys."""
    from ..core.onprem_balancers import attach_cluster

    _lb_call(attach_cluster, _cluster_root(config_path), name, cluster_name, echo)
    ok(f"{name} serves cluster {cluster_name}")


@lb_group.command("detach")
@click.argument("name")
@click.option("--cluster", "cluster_name", required=True)
@_CONFIG_OPTION
def lb_detach(name: str, cluster_name: str, config_path: Optional[str]) -> None:
    """Stop serving a cluster's deployments on load balancer NAME."""
    from ..core.onprem_balancers import detach_cluster

    _lb_call(detach_cluster, _cluster_root(config_path), name, cluster_name, echo)
    ok(f"{name} no longer serves cluster {cluster_name}")


@lb_group.group("routes")
def lb_routes() -> None:
    """Routes on a load balancer (pskit lb status lists them)."""


@lb_routes.command("remove")
@click.argument("name")
@click.argument("path")
@click.option("--yes", is_flag=True, help="Do not ask.")
@_CONFIG_OPTION
def lb_routes_remove(name: str, path: str, yes: bool, config_path: Optional[str]) -> None:
    """Remove the route at PATH (xyz, or port-8081) from load balancer NAME, whichever project owns it."""
    from ..core.onprem_balancers import remove_route

    if not yes:
        click.confirm(f"Remove /{path.strip('/')} from load balancer {name}?", abort=True)
    _lb_call(remove_route, _cluster_root(config_path), name, path, echo)


@lb_group.command("sync")
@click.argument("name")
@_CONFIG_OPTION
def lb_sync(name: str, config_path: Optional[str]) -> None:
    """Rewrite the load balancer from this project's settings: every route, and attached clusters."""
    from ..core.onprem_balancers import sync_balancer

    _lb_call(sync_balancer, _cluster_root(config_path), name, echo)
    ok(f"load balancer {name} updated")


@lb_group.command("logs")
@click.argument("name")
@click.option("-n", "--lines", default=100, show_default=True, type=click.IntRange(1, 10000))
@_CONFIG_OPTION
def lb_logs(name: str, lines: int, config_path: Optional[str]) -> None:
    """Recent requests (upstream= is the server that answered) and errors."""
    from ..core.onprem_balancers import logs

    click.echo(_lb_call(logs, _cluster_root(config_path), name, lines).rstrip("\n"))


@lb_group.command("remove")
@click.argument("name")
@click.option("--force", is_flag=True, help="Also when other projects still use it (their URLs stop too).")
@click.option("--yes", is_flag=True, help="Do not ask.")
@_CONFIG_OPTION
def lb_remove(name: str, force: bool, yes: bool, config_path: Optional[str]) -> None:
    """Stop load balancer NAME on its server and forget it."""
    from ..core.onprem_balancers import remove_balancer

    if not yes:
        click.confirm(f"Stop load balancer {name}? Every URL on it stops answering.", abort=True)
    _lb_call(remove_balancer, _cluster_root(config_path), name, echo, force=force)
    ok(f"load balancer {name} removed")


@lb_group.command("forget")
@click.argument("name")
@_CONFIG_OPTION
def lb_forget(name: str, config_path: Optional[str]) -> None:
    """Forget load balancer NAME in this project only (it keeps running for other projects)."""
    from ..core.onprem_balancers import forget_balancer

    _lb_call(forget_balancer, _cluster_root(config_path), name)
    ok(f"forgot {name}")


# ----------------------------------------------------------------------------- settings
@cli.group(short_help="Export / import this project's .pskit settings and secrets (encrypted).")
def settings() -> None:
    """Move the settings .pskit keeps out of git to another machine: one passphrase-encrypted file.

    \b
    Inside: saved servers, scaling clusters (and load balancers), on-prem services with their passwords,
    SSH passwords and the SSH keys the servers use (also from ~/.ssh), where each on-prem stage was last
    deployed, studio test events, and env files named by env_file in pskit.yml. Not inside: Terraform state.

    \b
    Examples:
      pskit settings export -o prod.pskit-settings     # asks for a passphrase (twice)
      pskit settings import prod.pskit-settings --dry-run
      pskit settings import prod.pskit-settings        # merges; --replace drops entries the file lacks
      PSKIT_SETTINGS_PASSPHRASE=... pskit settings import prod.pskit-settings --yes   # from a script
    """


def _passphrase(confirm: bool) -> str:
    value = os.environ.get("PSKIT_SETTINGS_PASSPHRASE")
    if value:
        return value
    return str(click.prompt("Passphrase", hide_input=True, confirmation_prompt=confirm))


@settings.command("export")
@click.option("-o", "--output", default=None, help="File to write (default: <service>.pskit-settings).")
@click.option("--with-config", is_flag=True, help="Also include pskit.yml (the functions, resources and providers).")
@_CONFIG_OPTION
def settings_export(output: Optional[str], with_config: bool, config_path: Optional[str]) -> None:
    """Write every local setting and secret of this project to one encrypted file."""
    from ..core.settings_bundle import SettingsError, env_files_of, export_settings

    root, _path, raw = _raw_project(config_path)
    target = Path(output or f"{raw.get('service') or 'pskit'}.pskit-settings")
    try:
        text, summary = export_settings(root, _passphrase(True), env_files=env_files_of(raw), pskit_version=__version__,
                                        config=with_config)
    except SettingsError as exc:
        raise click.ClickException(str(exc)) from None
    target.write_bytes(text.encode("utf-8"))
    for group, names in sorted((summary.get("entries") or {}).items()):
        echo(f"  {group}: {', '.join(names) or '-'}")
    echo(f"  {len(summary['files'])} file(s), {len(summary['keys'])} SSH key file(s) from outside the project")
    for warning in summary["warnings"]:
        echo(f"  WARNING: {warning}")
    ok(f"wrote {target}. It holds passwords and keys: share it only with the passphrase kept apart.")


@settings.command("import")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--replace", is_flag=True, help="Drop saved servers, clusters and services the file does not have.")
@click.option("--dry-run", is_flag=True, help="Only show what would change.")
@click.option("--yes", is_flag=True, help="Do not ask.")
@_CONFIG_OPTION
def settings_import(file: str, replace: bool, dry_run: bool, yes: bool, config_path: Optional[str]) -> None:
    """Write the settings of an exported FILE into this project (the current ones are backed up first)."""
    from ..core.settings_bundle import SettingsError, decrypt, import_settings, preview

    root, _path, _raw = _raw_project(config_path)
    try:
        payload = decrypt(Path(file).read_text("utf-8"), _passphrase(False))
        plan = preview(root, payload, replace=replace)
    except SettingsError as exc:
        raise click.ClickException(str(exc)) from None
    echo(f"  exported {plan.get('created_at')} with pskit {plan.get('pskit_version') or '?'} from {plan.get('source_root')}")
    for group, change in sorted(plan["stores"].items()):
        parts = [f"{k} {', '.join(v)}" for k, v in change.items() if v]
        echo(f"  {group}: {'; '.join(parts) or 'nothing'}")
    for item in plan["changes"]:
        echo(f"  {item['action']:<8} {item['path']}")
    for key in plan["key_files"]:
        echo(f"  key      {key['source']} -> {key['path']}")
    if dry_run:
        return
    if not yes:
        click.confirm(f"Import into {root}?", abort=True)
    result = import_settings(root, payload, replace=replace)
    if result.get("backup"):
        echo(f"  previous settings saved to {result['backup']}")
    ok(f"imported {len(result['written'])} file(s)")


# ----------------------------------------------------------------------------- client
@cli.group(short_help="Call the on-prem host from scripts.")
def client() -> None:
    """Use the deployed on-prem host from any program: Python / Node.js client, HTTP, tunnel.

    \b
    Examples:
      pskit client info                      # endpoint, token, reachability, code to copy
      pskit client install-node              # ./node_modules/pskit for scripts outside pskit
      pskit client tunnel                    # 127.0.0.1:8080 here -> the host on its server
    """


def _host_control(project: Any) -> Any:
    from ..core.deployer import Deployer
    from ..core.onprem_control import control_for

    if project.config.provider.name != "onprem":
        raise click.ClickException("the pskit client talks to an on-prem host: use -p onprem")
    record = Deployer(project, echo=echo).load_record()
    control = control_for(record or {}, project.root) if record else None
    if control is None:
        raise click.ClickException("the on-prem host is not deployed yet: run `pskit deploy`")
    return control


@client.command("info", short_help="Endpoint, token, reachability and code to call the host.")
@project_options
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def client_info(project, as_json: bool) -> None:  # noqa: ANN001
    """How to call the deployed host from scripts: Python, Node.js and curl, checked for reachability."""
    from ..core.client_guide import client_guide

    control = _host_control(project)
    guide = client_guide(project, control.base_url, bool(control.token))
    if as_json:
        click.echo(json.dumps(guide, indent=2))
        return
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    click.echo(guide["markdown"].encode(encoding, "replace").decode(encoding))


@client.command("install-node", short_help="Put the pskit Node.js package (with PskitClient) in node_modules.")
@click.option("--dir", "target_dir", default=".", show_default=True, help="Project whose node_modules gets it.")
def client_install_node(target_dir: str) -> None:
    """Copy the `pskit` package (no dependencies) to <dir>/node_modules/pskit, for scripts outside pskit."""
    from ..packaging.node import copy_runtime

    dest = Path(target_dir).resolve() / "node_modules" / "pskit"
    copy_runtime(dest)
    ok(f"Installed pskit into {dest}")
    echo('Use it: const { PskitClient } = require("pskit");')


@client.command("tunnel", short_help="Forward the host's port here over SSH (firewalled host port).")
@project_options
@click.option("--local-port", type=int, default=None, help="Port on this machine (default: the host's port).")
def client_tunnel(project, local_port: Optional[int]) -> None:  # noqa: ANN001
    """127.0.0.1:<port> here -> the on-prem host on its SSH server, until Ctrl+C."""
    import subprocess

    from ..core.onprem_services import tunnel_argv
    from ..providers.onprem_spec import parse_deploy

    cfg = project.config
    spec = parse_deploy(cfg.provider.options, service=cfg.service, stage=cfg.provider.stage,
                        runtime=cfg.provider.runtime, architecture=cfg.provider.architecture)
    if not spec.ssh_host:
        raise click.ClickException("the host runs on this machine; no tunnel needed")
    remote = int(cfg.provider.options.get("port") or 8080)
    port = int(local_port or remote)
    target = {"method": "ssh", "host": spec.ssh_host, "user": spec.ssh_user or "root", "port": spec.ssh_port,
              "identity_file": spec.identity_file or "", "known_hosts": spec.known_hosts}
    argv = tunnel_argv(target, port, remote)
    info(f"Forwarding 127.0.0.1:{port} -> {spec.ssh_host}:{remote}. In another terminal: export PSKIT_HOST=http://127.0.0.1:{port}")
    try:
        raise SystemExit(subprocess.call(argv))
    except KeyboardInterrupt:
        ok("Tunnel closed.")


def _ask_onprem_pem(project: Any) -> None:
    """Ask for the server ``.pem`` when a remote deploy has none yet.

    Asked only when a terminal is attached; an empty answer keeps the SSH agent
    or the default key. A password login (``password_file`` / ``auth: password``) asks nothing.
    """
    if project.config.provider.name != "onprem":
        return
    from ..providers.onprem_spec import assign_pem, parse_deploy, targets_remote_docker, uses_password

    cfg = project.config
    try:
        spec = parse_deploy(
            cfg.provider.options,
            service=cfg.service,
            stage=cfg.provider.stage,
            runtime=cfg.provider.runtime,
            architecture=cfg.provider.architecture,
        )
    except ValueError:
        return
    remote_docker = targets_remote_docker(spec)
    remote_ssh = spec.method == "ssh"
    if not remote_docker and not remote_ssh:
        return
    if (spec.identity_file and os.path.isfile(spec.identity_file)) or uses_password(spec) or spec.auth == "agent":
        return
    who = f"{spec.ssh_user}@{spec.ssh_host}" if spec.ssh_user else spec.ssh_host
    if not sys.stdin.isatty():
        if spec.identity_file:
            raise click.ClickException(f"SSH private key not found: {spec.identity_file}")
        return
    if remote_docker:
        echo(f"On-premises Docker deploy builds an image on this machine and copies it to {who}.")
        echo("If Docker is not installed on that server, it is installed before the image is loaded.")
    else:
        echo(f"On-premises SSH deploy copies one archive to {who} and starts the host.")
    echo("Enter a .pem path, or press Enter to use the SSH agent or the default key "
         "(password login: options.deploy.password_file or auth: password with SSHPASS).")
    entered = click.prompt("Path to the SSH private key (.pem)", default="", show_default=False)
    text = str(entered).strip()
    if not text:
        return
    candidate = Path(text).expanduser()
    if not candidate.is_file():
        raise click.ClickException(f"SSH private key not found: {text}")
    assign_pem(cfg.provider.options, str(candidate))


# ----------------------------------------------------------------------------- info / dashboard
def _print_record(record: dict) -> None:
    if record.get("endpoint"):
        echo(f"endpoint: {record['endpoint']}")
    if record.get("deployed_on"):
        echo(f"deployed on: {record['deployed_on'].get('label')}")
    echo("functions:")
    for f in record["functions"]:
        triggers = ", ".join(e["summary"] for e in f["events"]) or "direct invoke"
        echo(f"  {f['name']:<24} {f['kind']:<13} {triggers}")
        for u in f.get("urls") or []:
            echo(f"      {u['method']:<6} {u['url']}")
        if f.get("url") and not f.get("urls"):
            echo(f"      url: {f['url']}")
        if f.get("arn") or f.get("id"):
            echo(f"      id:  {f.get('arn') or f.get('id')}")
    if record.get("workflows"):
        echo("workflows:")
        for w in record["workflows"]:
            echo(f"  {w['name']:<24} {w['engine']:<9} {w.get('id') or ''}")


@cli.command("info")
@project_options
@click.option("--json", "as_json", is_flag=True, help="Machine readable output.")
@click.option("--refresh", is_flag=True, help="Re-read terraform outputs.")
def info_cmd(project, as_json: bool, refresh: bool) -> None:  # noqa: ANN001
    """Show what is deployed (functions, URLs, ids).

    
    Examples:
      pskit info
      pskit info -s prod --refresh --json
    """
    from ..core.deployer import Deployer
    from ..dashboard.generator import local_record

    deployer = Deployer(project, echo=echo)
    record = deployer.refresh_info() if refresh else deployer.load_record()
    if record is None:
        record = local_record(project)
        record["status"] = "not deployed"
    if as_json:
        click.echo(json.dumps(record, indent=2, default=str))
        return
    info(
        f"{record['service']} | {record['stage']} | {record['provider_display']} | {record.get('region')} | {record['status']}"
    )
    _print_record(record)


@cli.command()
@click.option(
    "-d", "--dir", "directory", default=".", type=click.Path(file_okay=False, exists=True), help="Project root."
)
@click.option("-o", "--output", default=None, type=click.Path(dir_okay=False), help="Write HTML here.")
@click.option("--serve", is_flag=True, help="Serve the dashboard with live logs and workflow executions.")
@click.option("--host", "bind_host", default="127.0.0.1", show_default=True, help="Bind address for --serve.")
@click.option("--port", default=8765, show_default=True)
@click.option("--open", "open_browser", is_flag=True, help="Open in the browser.")
def dashboard(
    directory: str, output: Optional[str], serve: bool, bind_host: str, port: int, open_browser: bool
) -> None:
    """Generate (and optionally serve) the deployment dashboard.

    
    Examples:
      pskit dashboard --open
      pskit dashboard --serve --open      # live logs and workflow executions
      pskit dashboard -o site/index.html
    """
    from ..dashboard.generator import collect_records, local_record, write_dashboard

    root = Path(directory).resolve()
    records = collect_records(root)
    if not records:
        try:
            from ..core.project import Project

            records = [local_record(Project.load(cwd=root))]
            echo("No deployments yet - showing the configured (local) view.")
        except ConfigError:
            pass
    path = write_dashboard(root, records, Path(output).resolve() if output else None)
    ok(f"Dashboard written to {path}")
    if serve:
        from ..dashboard.server import is_loopback, make_server

        try:
            httpd = make_server(root, bind_host, port)
        except OSError as exc:
            raise click.ClickException(f"cannot listen on {bind_host}:{port}: {exc}") from exc
        shown = "127.0.0.1" if bind_host in ("0.0.0.0", "::") else bind_host  # noqa: S104
        if ":" in shown and not shown.startswith("["):
            shown = f"[{shown}]"
        url = f"http://{shown}:{httpd.server_address[1]}/"
        if not is_loopback(bind_host):
            fail(
                f"warning: listening on {bind_host}. Anyone who can reach this port can read logs and "
                "start or cancel workflow executions."
            )
        echo(f"Serving on {url} (Ctrl+C to stop)")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()
    elif open_browser:
        webbrowser.open(path.as_uri())


@cli.command()
@click.option(
    "-d", "--dir", "directory", default=".", type=click.Path(file_okay=False, exists=True), help="Project root."
)
@click.option("--host", "bind_host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", default=8770, show_default=True)
@click.option("--open", "open_browser", is_flag=True, help="Open in the browser.")
@click.option("--vscode-image", default=None, help="code-server image for the full VS Code view.")
@click.option(
    "--ailogs",
    type=click.BOOL,
    default=False,
    is_flag=False,
    flag_value=True,
    help="Print every step of Hana's chats in this terminal: messages, model requests and answers, tool calls "
    "with arguments and results, plans, cards, errors (passwords stay hidden). --ailogs or --ailogs=true.",
)
def studio(
    directory: str, bind_host: str, port: int, open_browser: bool, vscode_image: Optional[str], ailogs: bool
) -> None:
    """Edit the project in the browser (writes pskit.yml).

    Build functions, triggers, workflows and resources with forms, edit code and deploy.

    
    Examples:
      pskit studio --open
      pskit studio -d path/to/project --port 8800
      pskit studio --ailogs=true        # Hana's conversations, tool calls and results in this terminal
    """
    from ..studio.hana import ailog
    from ..studio.server import is_loopback, make_server, studio_url

    if ailogs:
        ailog.enable()
    root = Path(directory).resolve()
    try:
        httpd = make_server(root, bind_host, port, vscode_image=vscode_image)
    except OSError as exc:
        raise click.ClickException(f"cannot listen on {bind_host}:{port}: {exc}") from exc
    url = studio_url(httpd)
    if not is_loopback(bind_host):
        fail(
            f"warning: listening on {bind_host}. The studio edits files and runs deploys; anyone with the "
            "link (it contains the session token) can do the same."
        )
    ok(f"pskit studio for {root}")
    echo(f"Open {url}  (Ctrl+C to stop)")
    if ailog.enabled():
        echo("Hana AI logs are on: every chat step is printed here (passwords stay hidden).")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


# ----------------------------------------------------------------------------- doctor
@cli.command()
@click.option("-p", "--provider", default=None, help="Provider to check (default: provider.name in pskit.yml).")
@click.option("-c", "--config", "config_path", default=None, help="Config file (default: pskit.yml).")
@click.option("--json", "as_json", is_flag=True, help="Machine readable output.")
def doctor(provider: Optional[str], config_path: Optional[str], as_json: bool) -> None:
    """Check terraform, the cloud CLI and credentials.

    Lists what is missing for the provider and how to install or configure it
    on this OS. Works without a pskit.yml when -p is given. Exits with 1 if
    anything required is missing.

    \b
    Examples:
      pskit doctor
      pskit doctor -p azure
      pskit doctor -p onprem --json
    """
    import yaml

    from ..config.loader import find_config
    from ..core.setup_check import check, os_key

    raw: dict = {}
    try:
        path = find_config(config_path)
        loaded = yaml.safe_load(path.read_text("utf-8"))
        raw = loaded if isinstance(loaded, dict) else {}
    except (ConfigError, OSError, yaml.YAMLError):
        if config_path:
            raise click.ClickException(f"cannot read {config_path}") from None
    if isinstance(raw.get("provider"), str):
        raw["provider"] = {"name": raw["provider"]}
    name = provider or str((raw.get("provider") or {}).get("name") or "")
    if not name:
        raise click.UsageError("no pskit.yml here; pass the provider, e.g. `pskit doctor -p aws`")
    if name not in PROVIDERS:
        raise click.BadParameter(f"unknown provider {name!r}; use one of {', '.join(PROVIDERS)}", param_hint="-p")
    report = check(name, raw if (raw.get("provider") or {}).get("name", name) == name else None, Path.cwd())
    if as_json:
        click.echo(json.dumps(report, indent=2))
    else:
        try:
            "✓✗".encode(getattr(sys.stdout, "encoding", None) or "ascii")
            good, bad = "✓", "✗"
        except (LookupError, UnicodeEncodeError):
            good, bad = "+", "x"
        marks = {"ok": (good, "green"), "missing": (bad, "red"), "warning": ("!", "yellow"), "info": ("i", "cyan")}
        info(f"pskit doctor: {name}")
        here = os_key()
        for item in report["checks"]:
            mark, color = marks.get(item["status"], ("?", None))
            echo(click.style(f" {mark} ", fg=color) + f"{item['title']}: {item['detail']}")
            fix = item.get("fix") or {}
            if item["status"] in ("ok",) or not (fix.get("summary") or fix.get("steps", {}).get(here)):
                continue
            if fix.get("summary"):
                echo(f"     {fix['summary']}")
            for step in (fix.get("steps") or {}).get(here) or []:
                echo(f"       {step}")
            for command in fix.get("commands") or []:
                echo(f"       $ {command}")
            for link in fix.get("links") or []:
                echo(f"       {link['label']}: {link['url']}")
        if report["ok"]:
            ok("Everything required is in place.")
        else:
            fail(f"Some required pieces are missing ({bad}).")
    if not report["ok"]:
        sys.exit(1)


# ----------------------------------------------------------------------------- local
@cli.command()
@project_options
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=3000, show_default=True)
@click.option("--env-file", default=".env", show_default=True)
def dev(project, host: str, port: int, env_file: str) -> None:  # noqa: ANN001
    """Run a local server with hot reload.

    Routes HTTP requests to your handlers and reloads them when files change.

    
    Examples:
      pskit dev
      pskit dev --port 8080 --env-file .env.local
    """
    from ..local.runner import LocalRunner
    from ..local.server import serve

    serve(LocalRunner(project, env_file=env_file), host=host, port=port, echo=echo)


@cli.command()
@project_options
@click.option("-f", "--function", "function", required=True, help="Function name from the config.")
@click.option(
    "-t",
    "--type",
    "kind",
    default=None,
    type=click.Choice(["http", "schedule", "queue", "storage", "topic", "invoke", "workflow", "smtp"]),
    help="Event type (default: the function's first event, or invoke).",
)
@click.option("-d", "--data", default=None, help="JSON payload or @file.json.")
@click.option("--method", default=None, help="HTTP method (http events).")
@click.option("--path", "path", default=None, help="HTTP path incl. query string (http events).")
@click.option("-H", "--header", "headers", multiple=True, help="HTTP header 'Name: value' (repeatable).")
@click.option("--env-file", default=".env", show_default=True)
def invoke(
    project,
    function: str,
    kind: Optional[str],
    data: Optional[str],
    method: Optional[str],  # noqa: ANN001
    path: Optional[str],
    headers: tuple,
    env_file: str,
) -> None:
    """Invoke a function locally with a synthetic event.

    
    Examples:
      pskit invoke -f hello
      pskit invoke -f hello -t http --method POST --path "/hello?x=1" -d '{"name": "Ada"}'
      pskit invoke -f worker -t queue -d @message.json
    """
    from ..local.runner import LocalRunner, build_event, parse_data, response_to_dict

    fn = project.config.functions.get(function)
    if fn is None:
        raise KeyError(f"unknown function {function!r}; known: {', '.join(sorted(project.config.functions))}")
    first = fn.events[0] if fn.events else None
    kind = kind or (first.type if first else "invoke")
    parsed_headers = {}
    for raw_header in headers:
        hname, sep, hvalue = raw_header.partition(":")
        if not sep:
            raise click.BadParameter(f"expected 'Name: value', got {raw_header!r}", param_hint="--header")
        parsed_headers[hname.strip()] = hvalue.strip()
    http_kw: dict = {"headers": parsed_headers or None}
    if kind == "http":
        route = next(iter(fn.events_of("http")), None)
        http_kw["method"] = method or (route.method if route and route.method != "ANY" else "GET")
        http_kw["path"] = path or (route.path if route else "/")
    payload = parse_data(data)
    if kind == "schedule" and payload is None and fn.events_of("schedule"):
        payload = fn.events_of("schedule")[0].input
    runner = LocalRunner(project, env_file=env_file)
    try:
        result = runner.invoke(function, build_event(kind, payload, **http_kw))
    except _errors() as exc:
        fail(f"Error: {exc}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - user code failed; show it like the cloud would
        stack = getattr(exc, "stack", "")
        if stack:
            click.echo(stack, err=True)
        else:
            traceback.print_exc()
        fail(f"{function} raised {getattr(exc, 'error', None) or type(exc).__name__}: {exc}")
        sys.exit(1)
    finally:
        runner.close()
    click.echo(json.dumps(response_to_dict(result), indent=2, default=str))


# ----------------------------------------------------------------------------- workflows
@cli.group()
def workflow() -> None:
    """Run or inspect workflows (state machines).

    
    Examples:
      pskit workflow run order -i '{"id": 1}' --history    # local, embedded engine
      pskit workflow show order --format asl
      pskit workflow start order -i @input.json --wait     # the deployed workflow
      pskit workflow executions order --status FAILED
      pskit workflow status <execution-id> --watch
      pskit workflow cancel <execution-id>
    """


@workflow.command("run")
@project_options
@click.argument("name")
@click.option("-i", "--input", "data", default=None, help="JSON input or @file.json.")
@click.option("--sleep", is_flag=True, help="Honour wait states (default: skip waiting).")
@click.option("--history", is_flag=True, help="Print the execution history.")
def workflow_run(project, name: str, data: Optional[str], sleep: bool, history: bool) -> None:  # noqa: ANN001
    """Run a workflow locally on the embedded engine.

    
    Examples:
      pskit workflow run order -i '{"id": 1}'
      pskit workflow run order -i @input.json --history --sleep
    """
    from ..local.runner import LocalRunner, parse_data
    from ..runtime.workflow import WorkflowFailed

    runner = LocalRunner(project)
    try:
        result = runner.run_workflow(name, parse_data(data), sleep=sleep)
    except WorkflowFailed as exc:
        fail(f"FAILED {exc.error}: {exc.cause}")
        if history:
            click.echo(json.dumps(exc.history, indent=2))
        sys.exit(2)
    finally:
        runner.close()
    ok("SUCCEEDED")
    click.echo(json.dumps(result["output"], indent=2, default=str))
    if history:
        click.echo(json.dumps(result["history"], indent=2))


@workflow.command("show")
@project_options
@click.argument("name")
@click.option("--format", "fmt", default="auto", type=click.Choice(["auto", "asl", "gcp", "json"]), show_default=True)
def workflow_show(project, name: str, fmt: str) -> None:  # noqa: ANN001
    """Print the compiled workflow definition.

    
    Examples:
      pskit workflow show order
      pskit workflow show order --format gcp
    """
    from ..workflows import definition_dict
    from ..workflows.asl import compile_asl
    from ..workflows.gcp import compile_gcp

    wf = project.config.workflows.get(name)
    if wf is None:
        raise KeyError(f"unknown workflow {name!r}")
    definition = definition_dict(wf)
    if fmt == "auto":
        fmt = {"aws": "asl", "gcp": "gcp"}.get(project.config.provider.name, "json")
    if fmt == "asl":
        out: Any = compile_asl(definition, lambda f: f"<arn of {f}>", wf.description, wf.timeout or 0)
    elif fmt == "gcp":
        out, warnings = compile_gcp(definition, lambda f: f"<url of {f}>", name)
        for w in warnings:
            fail(f"warning: {w}")
    else:
        out = definition
    click.echo(json.dumps(out, indent=2))


def _deployed_record(project: Any) -> dict:
    from ..core.deployer import Deployer

    record = Deployer(project, echo=echo).load_record()
    if record is None:
        raise click.ClickException(
            f"{project.config.provider.name}/{project.config.provider.stage} is not deployed yet; run `pskit deploy`"
        )
    return record


def _remote(call: Callable[[], Any]) -> Any:
    """Run a control-API / cloud-SDK call and turn its failures into CLI errors."""
    from ..core.executions import ExecutionError

    try:
        return call()
    except (ExecutionError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None


def _execution_backend(project: Any) -> Any:
    from ..core.executions import backend_for

    return backend_for(_deployed_record(project), project.root)


def _print_execution_line(item: dict) -> None:
    status = str(item.get("status") or "?")
    color = {"SUCCEEDED": "green", "RUNNING": "cyan"}.get(status, "red")
    started = str(item.get("started_at") or "")[:19].replace("T", " ")
    took = f"{item['duration_ms']:.0f} ms" if isinstance(item.get("duration_ms"), (int, float)) else ""
    current = f"@ {item['current_state']}" if status == "RUNNING" and item.get("current_state") else ""
    click.echo(
        f"{item.get('execution_id')}  {item.get('workflow', ''):<18} "
        + click.style(f"{status:<10}", fg=color)
        + f" {started:<19} {took:>10} {current}"
    )


@workflow.command("start")
@project_options
@click.argument("name")
@click.option("-i", "--input", "data", default=None, help="JSON input or @file.json.")
@click.option("--wait", is_flag=True, help="Wait for the result (on-prem; native engines return at once).")
@click.option("--json", "as_json", is_flag=True)
def workflow_start(project, name: str, data: Optional[str], wait: bool, as_json: bool) -> None:  # noqa: ANN001
    """Start a deployed workflow and print its execution id.

    
    Examples:
      pskit workflow start order -i '{"id": 1}'
      pskit workflow start order -i @input.json --wait --json
    """
    from ..local.runner import parse_data

    backend = _execution_backend(project)
    result = _remote(lambda: backend.start(name, parse_data(data), wait=wait))
    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
        return
    ok(f"execution_id: {result.get('execution_id')}")
    echo(f"status:       {result.get('status')}")
    if result.get("console"):
        echo(f"console:      {result['console']}")
    if "output" in result and result.get("status") == "SUCCEEDED":
        click.echo(json.dumps(result["output"], indent=2, default=str))
    elif result.get("error"):
        fail(f"{result.get('error')}: {result.get('cause') or ''}")
    if result.get("status") == "RUNNING":
        echo(f"Follow it with: pskit workflow status {result.get('execution_id')} --watch")


@workflow.command("executions")
@project_options
@click.argument("name", required=False)
@click.option("--status", default=None, help="RUNNING, SUCCEEDED, FAILED, TIMED_OUT, CANCELLED or ABORTED.")
@click.option("-n", "--limit", default=20, show_default=True)
@click.option("--offset", default=0, show_default=True, help="Skip this many (on-prem).")
@click.option("--token", default=None, help="Next-page token printed by a previous call (AWS/GCP).")
@click.option("--json", "as_json", is_flag=True)
def workflow_executions(  # noqa: ANN001
    project, name: Optional[str], status: Optional[str], limit: int, offset: int, token: Optional[str], as_json: bool
) -> None:
    """List executions of the deployed workflows (newest first).

    
    Examples:
      pskit workflow executions
      pskit workflow executions order --status FAILED -n 50
    """
    backend = _execution_backend(project)
    result = _remote(lambda: backend.list(workflow=name, status=status, limit=limit, offset=offset, token=token))
    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
        return
    if not result.get("supported", True):
        raise click.ClickException(result.get("reason") or "execution history is not available here")
    items = result.get("items") or []
    if not items:
        echo("No executions yet.")
    for item in items:
        _print_execution_line(item)
    total = result.get("total")
    if isinstance(total, int) and total > offset + len(items):
        echo(f"... {total - offset - len(items)} more (use --offset {offset + len(items)})")
    elif result.get("next_token"):
        echo(f"... more (use --token {result['next_token']})")


@workflow.command("status")
@project_options
@click.argument("execution_id")
@click.option("-w", "--workflow", "name", default=None, help="Workflow name (helps AWS/GCP resolve the id).")
@click.option("--history", is_flag=True, help="Print the state history.")
@click.option("--watch", is_flag=True, help="Poll until the execution finishes.")
@click.option("--json", "as_json", is_flag=True)
def workflow_status(  # noqa: ANN001
    project, execution_id: str, name: Optional[str], history: bool, watch: bool, as_json: bool
) -> None:
    """Show one execution: status, current state, output or error.

    
    Examples:
      pskit workflow status <execution-id>
      pskit workflow status <execution-id> -w order --history --watch
    """
    import time

    backend = _execution_backend(project)
    record = _remote(lambda: backend.get(execution_id, name))
    while watch and record.get("status") == "RUNNING":
        if not as_json:
            echo(f"RUNNING @ {record.get('current_state') or '-'}")
        time.sleep(2)
        record = _remote(lambda: backend.get(execution_id, name))
    if as_json:
        click.echo(json.dumps(record, indent=2, default=str))
        return
    _print_execution_line(record)
    if record.get("console"):
        echo(f"console: {record['console']}")
    if record.get("status") == "SUCCEEDED":
        click.echo(json.dumps(record.get("output"), indent=2, default=str))
    elif record.get("error") or record.get("cause"):
        fail(f"{record.get('error')}: {record.get('cause') or ''}")
    if history:
        for step in record.get("history") or []:
            extra = f" ({step['error']})" if step.get("error") else ""
            echo(f"  {str(step.get('ts') or '')[11:23]}  {step.get('event', ''):<6} {step.get('state')}{extra}")


@workflow.command("cancel")
@project_options
@click.argument("execution_id")
@click.option("-w", "--workflow", "name", default=None, help="Workflow name (AWS/GCP).")
def workflow_cancel(project, execution_id: str, name: Optional[str]) -> None:  # noqa: ANN001
    """Cancel a running execution (stops before its next state).

    
    Examples:
      pskit workflow cancel <execution-id>
      pskit workflow cancel <execution-id> -w order
    """
    backend = _execution_backend(project)
    record = _remote(lambda: backend.cancel(execution_id, name))
    _print_execution_line(record)


# ----------------------------------------------------------------------------- logs
@cli.command()
@project_options
@click.option("-f", "--follow", is_flag=True, help="Keep printing new entries.")
@click.option("-n", "--lines", default=100, show_default=True, help="How many recent entries to show first.")
@click.option("--function", "function", default=None, help="Only this function.")
@click.option("--level", default=None, help="Minimum level: DEBUG, INFO, WARNING, ERROR.")
@click.option(
    "--source",
    default=None,
    type=click.Choice(["function", "host", "stdout", "stderr", "invocation"]),
    help="Only one kind of entry.",
)
@click.option("-q", "--grep", "text", default=None, help="Only entries containing this text.")
@click.option("--json", "as_json", is_flag=True, help="One JSON object per line.")
@click.option("--streams", "list_streams", is_flag=True, help="List log streams (per function / container) instead.")
@click.option("--delete", "delete_ids", multiple=True, metavar="STREAM", help="Delete a log stream (repeatable).")
@click.option("--delete-all", is_flag=True, help="Delete every log stream (of --function, or of all functions).")
@click.option("-y", "--yes", is_flag=True, help="Don't ask for confirmation before deleting.")
def logs(  # noqa: ANN001
    project,
    follow: bool,
    lines: int,
    function: Optional[str],
    level: Optional[str],
    source: Optional[str],
    text: Optional[str],
    as_json: bool,
    list_streams: bool,
    delete_ids: tuple,
    delete_all: bool,
    yes: bool,
) -> None:
    """Show, list or delete logs of a deployment.

    \b
    On premises: the host's buffer (handlers, print output, invocations).
    A Nomad cluster reads every server, so web-replica lines show with the main replica.
    AWS: CloudWatch Logs (needs boto3). GCP: Cloud Logging (needs
    google-cloud-logging, read only). Azure: Log Analytics when a
    `log_analytics_workspace_id` output exists. Elsewhere: use the console
    link from `pskit info`.
    """
    import time

    from ..core.cloud_logs import LogError, log_backend

    record = _deployed_record(project)
    backend = log_backend(record, project.root)
    if not backend.supported:
        raise click.ClickException(backend.reason)

    def call(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except LogError as exc:
            raise click.ClickException(str(exc)) from None
        except KeyError as exc:
            raise click.ClickException(str(exc.args[0] if exc.args else exc)) from None
        except (OSError, ValueError) as exc:
            raise click.ClickException(str(exc)) from None

    if delete_ids or delete_all:
        if not backend.can_delete:
            raise click.ClickException(backend.reason or "deleting logs is not supported for this deployment")
        what = (
            f"{len(delete_ids)} log stream(s)"
            if delete_ids
            else (f"every log stream of {function}" if function else "every log stream of every function")
        )
        where = f"{project.config.provider.name}/{project.config.provider.stage}"
        if not yes and not click.confirm(f"Delete {what} of {where}? This cannot be undone", default=False):
            raise click.Abort()
        result = call(lambda: backend.delete(ids=list(delete_ids) or None, function=function, all=delete_all and not function))
        ok(f"Deleted {result.get('deleted', 0)} log stream(s)" if backend.mode == "time" else f"Deleted {result.get('deleted', 0)} entries")
        for error in result.get("errors") or []:
            fail(f"  {error}")
        return

    if list_streams:
        page = call(lambda: backend.streams(function))
        items = page.get("items") or []
        if as_json:
            for item in items:
                click.echo(json.dumps(item, default=str))
            return
        if not items:
            echo("No log streams.")
            return
        for item in items:
            last = str(item.get("last") or "")[:19].replace("T", " ")
            size = item.get("count") if item.get("count") is not None else item.get("bytes")
            echo(f"{last:<20} {str(item.get('function') or 'host'):<24} {size if size is not None else '':>10}  {item.get('id')}")
        return

    def fetch(since: int, limit: int) -> dict:
        return dict(
            call(lambda: backend.query(since=since, limit=limit, level=level, function=function, q=text, source=source))
        )

    colors = {"ERROR": "red", "CRITICAL": "red", "WARNING": "yellow", "DEBUG": "bright_black"}

    def show(entries: list) -> None:
        for entry in entries:
            if as_json:
                click.echo(json.dumps(entry, default=str))
                continue
            who = entry.get("function") or entry.get("source")
            stamp = str(entry.get("ts") or "")[:23].replace("T", " ")
            click.echo(
                click.style(f"{stamp} {entry.get('level', ''):<7}", fg=colors.get(entry.get("level", "")))
                + f" [{who}] {entry.get('message', '')}"
            )

    page = fetch(0, lines)
    show(page.get("entries") or [])
    cursor = int(page.get("next") or 0)
    while follow:
        try:
            time.sleep(1 if backend.mode == "seq" else 3)
            page = fetch(cursor, 500)
        except KeyboardInterrupt:
            break
        if page.get("gap"):
            fail("... some entries were dropped from the host's buffer ...")
        show(page.get("entries") or [])
        cursor = int(page.get("next") or cursor)


# ----------------------------------------------------------------------------- providers / terraform
@cli.command()
@click.option("--json", "as_json", is_flag=True)
def providers(as_json: bool) -> None:
    """List supported clouds and what each supports.

    
    Examples:
      pskit providers
      pskit providers --json
    """
    from ..providers.registry import available, get_provider

    rows = []
    for name in available():
        try:
            rows.append(get_provider(name).describe())
        except Exception as exc:  # noqa: BLE001 - a broken plug-in must not hide the others
            rows.append({"name": name, "tier": "unavailable", "error": str(exc)})
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    cols = ["http", "schedule", "queue", "storage", "topic", "workflow_native"]
    echo(f"{'provider':<14}{'tier':<14}" + "".join(f"{c.replace('workflow_native', 'workflows'):<11}" for c in cols))
    for r in rows:
        caps = set(r.get("capabilities", []))
        line = f"{r['name']:<14}{r.get('tier', ''):<14}"
        for c in cols:
            if c == "workflow_native":
                line += f"{'native' if c in caps else 'embedded':<11}"
            else:
                line += f"{'yes' if c in caps else '-':<11}"
        echo(line)


@cli.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@project_options
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def tf(project, args: tuple) -> None:  # noqa: ANN001
    """Run any terraform command in the generated workspace.

    
    Examples:
      pskit tf -- state list
      pskit tf -s prod -- output -json
    """
    from ..terraform.runner import TerraformRunner

    if not (project.work_dir / "main.tf.json").is_file():
        raise click.ClickException("nothing generated yet; run `pskit package` first")
    runner = TerraformRunner(project.work_dir, binary=project.config.provider.terraform.binary)
    sys.exit(runner.passthrough(list(args)))


def main(argv: Optional[list] = None) -> None:
    os.environ.setdefault("PSKIT_LOG_FORMAT", "text")
    cli.main(args=argv, prog_name="pskit")


if __name__ == "__main__":  # pragma: no cover
    main()
