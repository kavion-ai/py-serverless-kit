"""Render a representative project for every provider and run ``terraform validate``.

Usage::

    python scripts/validate_all_providers.py                 # all providers
    python scripts/validate_all_providers.py --provider gcp  # one provider
    python scripts/validate_all_providers.py --keep          # keep the temp dirs
    python scripts/validate_all_providers.py --language node # only the Node.js variant

Each provider is rendered as a Python and as a Node.js service (providers without
Node.js support are skipped for the latter).

Needs terraform (or tofu, via PSKIT_TERRAFORM_BIN) and network access to download
provider plugins. Set TF_PLUGIN_CACHE_DIR to reuse plugin downloads between runs.
No cloud credentials are needed: ``validate`` never calls the cloud APIs.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.core.project import Project
from py_serverless_kit.providers.registry import available, get_provider
from py_serverless_kit.terraform.runner import TerraformError, find_binary

# Placeholder values for options a provider requires. `terraform validate`
# checks types and references only, so fake ids are fine.
DUMMY_OPTIONS = {
    "gcp": {"project": "pskit-validate"},
    "azure": {"subscription_id": "00000000-0000-0000-0000-000000000000"},
    "oracle": {
        "compartment_id": "ocid1.compartment.oc1..example",
        "subnet_ids": ["ocid1.subnet.oc1..example"],
        "image": "iad.ocir.io/namespace/pskit-validate:latest",
    },
    "digitalocean": {"namespace": "fn-00000000-0000-0000-0000-000000000000"},
    "cloudflare": {"account_id": "0123456789abcdef0123456789abcdef", "workers_subdomain": "example"},
    "huawei": {"apig_instance_id": "00000000000000000000000000000000"},
}

HANDLERS = """
from py_serverless_kit import Event, Context


def api(event: Event, ctx: Context):
    return {"ok": True}


def job(event: Event, ctx: Context):
    return {"type": event.type}


def step(event: Event, ctx: Context):
    return event.data
"""


JS_HANDLERS = """
exports.api = async (event, ctx) => ({ ok: true });
exports.job = async (event, ctx) => ({ type: event.type });
exports.step = async (event, ctx) => event.data;
"""
LANGUAGES = ("python", "node")


def project_yaml(name: str, language: str = "python") -> str:
    text = _project_yaml(name)
    if language == "python":
        return text
    config = json.loads(text)
    config["provider"]["runtime"] = get_provider(name).default_runtime_for(language)
    return json.dumps(config, indent=2)


def _project_yaml(name: str) -> str:
    caps = get_provider(name).capabilities
    functions = {
        "api": {
            "handler": "app.handlers.api",
            "events": [{"http": "GET /items/{id}"}, {"http": {"path": "/items", "method": "POST", "cors": True}}],
        },
        "step": {"handler": "app.handlers.step"},
    }
    if "schedule" in caps:
        functions["cron"] = {
            "handler": "app.handlers.job",
            "events": [{"schedule": "5 minutes"}, {"schedule": {"cron": "0 3 * * *", "input": {"x": 1}}}],
        }
    if "queue" in caps:
        functions["queue-worker"] = {
            "handler": "app.handlers.job",
            "events": [{"queue": {"name": "pskit-validate-jobs"}}],
        }
    if "storage" in caps:
        functions["uploads"] = {
            "handler": "app.handlers.job",
            "events": [{"storage": {"bucket": "pskit-validate-uploads-1250000000", "suffix": ".csv"}}],
        }
    if "topic" in caps:
        functions["subscriber"] = {"handler": "app.handlers.job", "events": [{"topic": "pskit-validate-events"}]}
    resources: dict = {"db": {"type": "database", "external": True, "connection": {"host": "db.internal"}}}
    if get_provider(name).standalone_resources:
        # Managed resources no event uses, plus external ones bound by name (looked up with data sources).
        resources.update(
            {
                "files": {"type": "storage", "name": "pskit-validate-files-1250000000"},
                "tasks": {"type": "queue", "name": "pskit-validate-tasks"},
                "alerts": {"type": "topic", "name": "pskit-validate-alerts"},
                "shared": {"type": "queue", "external": True, "name": "pskit-validate-shared"},
            }
        )
    config = {
        "service": "pskit-validate",
        "provider": {"name": name, "options": DUMMY_OPTIONS.get(name, {})},
        "resources": resources,
        "functions": functions,
        "workflows": {
            "flow": {
                "start_at": "A",
                "states": {
                    "A": {
                        "type": "task",
                        "function": "step",
                        "retry": [{"errors": ["*"], "max_attempts": 2}],
                        "next": "B",
                    },
                    "B": {
                        "type": "choice",
                        "choices": [{"variable": "$.ok", "equals": True, "next": "C"}],
                        "default": "C",
                    },
                    "C": {"type": "succeed"},
                },
            }
        },
    }
    if name == "azure":
        # Native workflows are opt-in on Azure (Logic Apps): validate both engines.
        config["workflows"]["native-flow"] = {
            "engine": "native",
            "start_at": "A",
            "states": {
                "A": {
                    "type": "task",
                    "function": "step",
                    "retry": [{"errors": ["*"], "max_attempts": 2}],
                    "catch": [{"errors": ["*"], "next": "Failed"}],
                    "next": "B",
                },
                "B": {
                    "type": "choice",
                    "choices": [{"variable": "$.ok", "equals": True, "next": "Fan"}],
                    "default": "C",
                },
                "Fan": {
                    "type": "parallel",
                    "branches": [{"start_at": "P", "states": {"P": {"type": "pass", "result": {"x": 1}}}}],
                    "result_path": "$.fan",
                    "next": "Each",
                },
                "Each": {
                    "type": "map",
                    "items_path": "$.items",
                    "iterator": {"start_at": "I", "states": {"I": {"type": "task", "function": "step"}}},
                    "result_path": "$.out",
                    "next": "C",
                },
                "C": {"type": "wait", "seconds": 1, "next": "Done"},
                "Done": {"type": "succeed"},
                "Failed": {"type": "fail", "error": "Boom", "cause": "task failed"},
            },
        }
    return json.dumps(config, indent=2)  # JSON is valid YAML


def validate(name: str, keep: bool, language: str = "python") -> bool:
    if language == "node" and not get_provider(name).node_runtimes:
        print(f"[{name}/node] skipped: no Node.js support")
        return True
    label = name if language == "python" else f"{name}/{language}"
    tmp = Path(tempfile.mkdtemp(prefix=f"pskit-validate-{name}-{language}-"))
    try:
        (tmp / "app").mkdir()
        if language == "node":
            (tmp / "app" / "handlers.js").write_text(textwrap.dedent(JS_HANDLERS))
        else:
            (tmp / "app" / "__init__.py").write_text("")
            (tmp / "app" / "handlers.py").write_text(textwrap.dedent(HANDLERS))
        (tmp / "pskit.yml").write_text(project_yaml(name, language))
        project = Project.load(cwd=tmp)
        errors = [str(i) for i in project.validate() if i.level == "error"]
        if errors:
            print(f"[{label}] config errors:\n  " + "\n  ".join(errors))
            return False
        try:
            Deployer(project, echo=lambda _m: None).package(skip_deps=True)
        except Exception as exc:  # noqa: BLE001 - report and go on with the other variants
            print(f"[{label}] package failed: {type(exc).__name__}: {exc}")
            return False
        tf = find_binary()
        for args in (["init", "-backend=false", "-input=false", "-no-color"], ["validate", "-no-color"]):
            proc = subprocess.run([tf, *args], cwd=project.work_dir, capture_output=True, text=True)
            if proc.returncode != 0:
                print(f"[{label}] terraform {args[0]} failed:\n{proc.stdout}\n{proc.stderr}")
                return False
        print(f"[{label}] OK - {project.work_dir / 'main.tf.json'}" if keep else f"[{label}] OK")
        return True
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", action="append", help="provider(s) to validate (default: all)")
    parser.add_argument("--keep", action="store_true", help="keep generated directories")
    parser.add_argument(
        "--language", choices=(*LANGUAGES, "all"), default="all", help="runtime language variant(s) (default: all)"
    )
    args = parser.parse_args()
    try:
        find_binary()
    except TerraformError as exc:
        print(f"{exc}\n\nThis check is optional: it needs Terraform locally. CI runs it for you.", file=sys.stderr)
        return 2
    names = args.provider or available()
    languages = LANGUAGES if args.language == "all" else (args.language,)
    results = {f"{n}/{lang}": validate(n, args.keep, lang) for n in names for lang in languages}
    failed = [n for n, ok in results.items() if not ok]
    print(
        f"\n{len(results) - len(failed)}/{len(results)} provider variants valid"
        + (f"; failed: {', '.join(failed)}" if failed else "")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
