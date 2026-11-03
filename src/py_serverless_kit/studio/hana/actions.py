"""Studio actions in the chat: things the model was not trained to do, done by studio itself.

Hana's model only knows the 10 project tools (pskit.yml and files). Saved servers and on-prem services live in
studio's own state (``.pskit/``), so for those the chat recognises the request, answers from the real state (lists)
or fills in a card from what the user wrote (host, user, .pem path, ``ssh`` command, folders, service, server). The
user checks the card and clicks; it calls the same studio API as the Servers / On-prem services pages. Nothing
changes without the click.

Intents, in this order: what can you do / list servers / list services / remove a server or service / change a
saved server / add a server / create a service. ``detect`` returns ``None`` when it is none of these (the model
answers) or ``{"reply": text, "card": {...} | None, "direct": True}``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_IP = re.compile(r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b")
_SSH_CMD = re.compile(r"\bssh\s+(?P<opts>(?:-[A-Za-z]\s+\S+\s+)*)(?P<user>[A-Za-z_][\w.-]*)@(?P<host>[\w.-]+)")
_PEM = re.compile(r"""(?P<path>(?:[A-Za-z]:[\\/]|/|~[\\/]|\.{1,2}[\\/])?[^\s"'=,;]*\.(?:pem|key))\b""")
_PEM_ABS = re.compile(r"""((?:\b[A-Za-z]:[\\/]|(?<![\w.])/|~[\\/])[^\s"'=,;:]*\.(?:pem|key))\b""")
_KV = re.compile(r"""\b(?P<key>[a-z_]*(?:user|ip|host|port)[a-z_]*)\s*[:=]\s*"?(?P<value>[^\s",]+)"?""", re.I)
_SERVER_NAME = re.compile(r"\b(?:named?|call(?:ed)?|as)\s+[\"'`]?(?P<name>[A-Za-z][\w.-]{0,62})", re.I)
_KEY_NAME = re.compile(r"\b(?:named?|call(?:ed)?)\s+[\"'`]?(?P<name>[A-Za-z][\w-]{0,62})", re.I)
_DO = re.compile(r"\b(create|add|save|connect|register|set ?up|setup|make|install|start|run|spin up|provision|"
                 r"want|need|would like|build)\b"
                 r"|\b(do it|create it|add it|save it)\b", re.I)
_LIST = re.compile(r"\b(how many|list|lst|lis|show( me)?|which|what|any|count|do (i|we) have|are there|is there)\b",
                   re.I)
_REMOVE = re.compile(r"\b(remove|delete|forget|drop|uninstall|get rid of|destroy)\b", re.I)
_EDIT = re.compile(r"\b(change|set|update|edit|modify|add|use|put|fix|rename)\b", re.I)
_HOWTO = re.compile(r"^\s*(?:no,?\s+)?(?:i\s+mean\s+)?(how (do|can|to|should|i)|where|explain|tell me how)\b", re.I)
_SERVER_WORD = re.compile(r"\b(servers?|severs?|sever|servs?|srvs?|svrs?|machines?|vms?|hosts?|ec2|instances?)\b",
                          re.I)
_SERVICE_WORD = re.compile(r"\b(services?|databases?|dbs?|caches?|queues?|brokers?|containers?)\b", re.I)
_THIS = re.compile(r"\b(this|that|the|same|it|its)\s+(server|machine|host|one)\b|\b(it|its)\b", re.I)
_TOOLS_Q = re.compile(r"\b(what can (you|u) do|(do|have) (you|u) (have )?(any )?tools|your tools|what tools|"
                      r"capabilit|how many (functions?|funtions?|tools?) do (you|u) have)", re.I)
# server fields a user can name, and the words for them
_FIELDS = {"home": r"\bhome\b", "data_dir": r"\bdata\b", "bind": r"\bbind\b|\blisten", "port": r"\bport\b",
           "user": r"\buser\b", "identity_file": r"\bpem\b|\bkey\b", "host": r"\b(ip|host|address)\b",
           "sudo": r"\bsudo\b", "auth": r"\b(password|passwd|agent|log ?in with)\b",
           "description": r"\b(description|desc|note|label)\b"}
_FIELD_LABELS = {"home": "the home folder", "data_dir": "the data folder", "bind": "the listen address",
                 "description": "the description"}
_POSIX_PATH = re.compile(r"(?<![\w:.])(/[\w.-]+(?:/[\w.-]+)*)")

# words people use for catalog services (catalog ids and labels are matched too)
_ALIASES = {"postgresql": "postgres", "pg": "postgres", "mongo": "mongodb", "rabbit": "rabbitmq",
            "vault": "openbao", "mqtt": "mosquitto", "redpanda": "kafka", "postgressql": "postgres",
            "postgress": "postgres", "postgre": "postgres", "postgresdb": "postgres", "psql": "postgres",
            "postgressdb": "postgres", "rediss": "redis", "rabitmq": "rabbitmq", "mongodbb": "mongodb",
            "mysqldb": "mysql", "maria": "mariadb"}
_ONPREM_WORDS = re.compile(r"\b(servers?|machines?|on-?prem\w*|docker|services?|vms?|ec2)\b", re.I)

CAPABILITIES = (
    "Here is what I can do in this studio:\n\n"
    "**On your project (pskit.yml and code), with a plan you approve first**\n"
    "- add or change functions, triggers (http, schedule, queue, storage, topic), resources and settings\n"
    "- put each function in its own app (`functions/<name>/` with its own `requirements.txt`) or in an existing one: "
    "I ask which, and what to do when a name is already taken (update it, use another name, or skip)\n"
    "- move existing functions into their own apps (\"make step01 and step02 separate apps\")\n"
    "- write handler code, then check it with `pskit validate` and a local invoke\n"
    "- find and fix validation errors\n\n"
    "**Servers and on-prem services, with a card you confirm**\n"
    "- list, add, change (home / data folder, user, key, port) and remove saved servers: paste the IP, user and "
    "`.pem` path, or the `ssh` command\n"
    "- list, create and remove on-prem services: Redis, PostgreSQL, MySQL, RabbitMQ, ElasticMQ, MinIO, MongoDB and "
    "more\n\n"
    "**Terminal, after you click Run on each command**\n"
    "- run commands in the project folder or on a saved server (\"run docker ps on app-1\", \"install docker on "
    "app-1\", \"execute pskit validate\") and answer from the output\n\n"
    "**Answers**\n"
    "- how to do something in studio, the terminal or code, with links to the docs\n\n"
    "I never deploy: the **Deploy** page does that, and it asks you first."
)


IDENTITY = ("I'm **Hana**, the AI assistant built into pskit studio, created and developed by Asif Khan "
            "(https://www.linkedin.com/in/asif-khan-31b7a8187/). I help you build, change, debug and deploy pskit "
            "services: ask me how to do something, or ask me to change this project, add servers, create services "
            "or clusters.")
VAGUE = ("I'm not sure what you mean. You can ask me for example:\n\n"
         "- \"what is this project for?\"\n- \"add a GET /health endpoint that returns ok\"\n"
         "- \"validate my project and fix the problems\"\n- \"how many servers do we have?\"\n"
         "- \"deploy the code to server-1\"")
_IDENTITY = re.compile(
    r"\b(who|what)\s+(are|r)\s+(you|u)\b|\b(your|ur|you'?re|youre|u\s+are)\s+name\b|\bname\s+is\s+hana\b|"
    r"\b(tum|tu|aap|ap)\s+(kon|kaun)\b|\b(kon|kaun)\s+(ho|hai|h)\b|\bwho\s+(made|created|built|developed|trained)"
    r"\s+(you|u)\b|\b(tumhara|aapka|apka|tera)\s+naam\b|\bintroduce yourself\b|\bare (you|u) (an? )?(ai|bot|human)\b",
    re.I)
_VAGUE = {"what", "wat", "wht", "huh", "hmm", "hm", "kya", "eh", ""}  # not "ok": that can answer Hana's question
_HINGLISH = re.compile(r"\b(tum|tu|aap|ap|kya|kaun|kon|hai|ho|hain|kaise|kaisa|mujhe|mera|meri|karo|kar|nahi|"
                       r"haan|batao|bata|kyun|kab|kahan|yeh|woh|accha|theek|bhai|chahiye|gi|ji)\b", re.I)
_PROJECT_Q = re.compile(
    r"\b(what|explain|describe|summar\w*|tell me about|overview of|purpose of)\b[^.?!]{0,40}\b(this|my|the|our)\s+"
    r"(project|service|app|application|code)\b(?!\s+for\s+me)|"
    r"\b(what|why)\b[^.?!]{0,30}\b(project|service|app)\s+(is\s+)?(for|about)\b(?!\s+me)", re.I)
_LIST_ITEMS = re.compile(r"\b(list|show|how many|which|what are|what all|names? of|count|enumerate|all the)\b", re.I)


def _event_text(event: Any) -> str:
    if not isinstance(event, dict) or not event:
        return str(event)
    kind, value = next(iter(event.items()))
    if isinstance(value, str):
        return f"{kind} `{value}`"
    if isinstance(value, dict):
        main = value.get("path") or value.get("rate") or value.get("cron") or value.get("name") or value.get("queue") \
            or value.get("bucket") or value.get("topic") or ""
        method = value.get("method")
        label = f"{method} {main}".strip() if method else str(main)
        return f"{kind} `{label}`" if label else str(kind)
    return str(kind)


def project_summary(root: Path) -> str:
    """What the project is, read from pskit.yml (never guessed): service, provider, functions with their
    triggers, workflows and resources."""
    from .edits import raw_config

    raw = raw_config(root)
    if not raw:
        return ""
    provider: Dict[str, Any] = raw["provider"] if isinstance(raw.get("provider"), dict) else {}
    where = " ".join(str(provider.get(k)) for k in ("name", "region", "runtime") if provider.get(k))
    lines = [f"This project is the service **{raw.get('service', '?')}**, deployed to **{where or 'no provider set'}**."]
    functions = raw.get("functions") if isinstance(raw.get("functions"), dict) else {}
    if functions:
        lines += ["", f"**Functions ({len(functions)})**"]
        for name, fn in functions.items():
            fn = fn if isinstance(fn, dict) else {}
            events: List[Any] = fn["events"] if isinstance(fn.get("events"), list) else []
            triggers = ", ".join(_event_text(e) for e in events) or "no trigger (called directly or by a workflow)"
            desc = f" ({fn['description']})" if fn.get("description") else ""
            lines.append(f"- **{name}**: `{fn.get('handler', '?')}`, {triggers}{desc}")
    else:
        lines += ["", "It has no functions yet."]
    workflows = raw.get("workflows") if isinstance(raw.get("workflows"), dict) else {}
    if workflows:
        lines += ["", f"**Workflows ({len(workflows)})**"]
        for name, wf in workflows.items():
            states = (wf or {}).get("states") if isinstance(wf, dict) else None
            lines.append(f"- **{name}**: {len(states) if isinstance(states, dict) else 0} step(s)")
    resources = raw.get("resources") if isinstance(raw.get("resources"), dict) else {}
    if resources:
        lines += ["", f"**Resources ({len(resources)})**"]
        for name, res in resources.items():
            kind = (res or {}).get("type") if isinstance(res, dict) else ""
            lines.append(f"- **{name}**" + (f": {kind}" if kind else ""))
    lines += ["", "I read this from pskit.yml. Ask me about any function, or to change something."]
    return "\n".join(lines)


def items_list(root: Path, kind: str) -> str:
    """The project's functions / workflows / resources, from pskit.yml."""
    from .edits import raw_config

    raw = raw_config(root)
    section = raw.get({"function": "functions", "workflow": "workflows", "resource": "resources"}[kind])
    section = section if isinstance(section, dict) else {}
    if not raw:
        return ""
    if not section:
        return f"This project has no {kind}s yet." + (" Ask me to add one, e.g. \"add a GET /hello endpoint\"."
                                                      if kind == "function" else "")
    lines = [f"This project has **{len(section)}** ({spelled(len(section))}) {kind}{'s' if len(section) != 1 else ''}:",
             ""]
    for name, item in section.items():
        item = item if isinstance(item, dict) else {}
        if kind == "function":
            events: List[Any] = item["events"] if isinstance(item.get("events"), list) else []
            triggers = ", ".join(_event_text(e) for e in events) or "no trigger"
            lines.append(f"- **{name}**: `{item.get('handler', '?')}`, {triggers}")
        elif kind == "workflow":
            states: Dict[str, Any] = item["states"] if isinstance(item.get("states"), dict) else {}
            steps = " → ".join(str((s or {}).get("function") or k) for k, s in states.items())
            lines.append(f"- **{name}**: {steps or 'no steps'}")
        else:
            lines.append(f"- **{name}**" + (f": {item['type']}" if item.get("type") else ""))
    page = {"function": "Functions", "workflow": "Workflows", "resource": "Resources"}[kind]
    lines += ["", f"From pskit.yml; details on the **{page}** page."]
    return "\n".join(lines)


_RESOURCE_WORDS = {"queue": "queue", "queues": "queue", "bucket": "storage", "buckets": "storage",
                   "storage": "storage", "topic": "topic", "topics": "topic", "database": "database",
                   "databases": "database", "db": "database", "dbs": "database", "cache": "cache", "caches": "cache",
                   "smtp": "smtp", "mailbox": "smtp"}
_RESOURCE_RX = re.compile(r"\b(queues?|buckets?|storage|topics?|databases?|dbs?|caches?|smtp|mailbox)\b")
_NOT_RESOURCE_NAMES = {"a", "an", "the", "new", "one", "two", "three", "four", "five", "and", "more", "some", "of",
                       "add", "create", "make", "resource", "resources", "managed", "external", "s3", "sqs", "sns",
                       "redis", "postgres", "mysql", "with", "for", "me", "my", "this", "that"}


def _resources_intent(text: str, lowered: str, root: Path, provider: str) -> Optional[Dict[str, Any]]:
    """"add a jobs queue, 2 buckets and a database named orders" -> one card per resource."""
    from .edits import EXTERNAL_RESOURCES, free_name, names, raw_config

    raw = raw_config(root)
    if not raw:
        return None
    matches = list(_RESOURCE_RX.finditer(lowered))
    if not matches:
        return None
    existing = names(raw, "resource")
    taken = list(existing)
    cards: List[Dict[str, Any]] = []
    plan = ["Here is what I understood:", ""]
    for m in matches:
        kind = _RESOURCE_WORDS[m.group(1)]
        before = re.search(r"([a-z][\w-]*)\s+$", lowered[:m.start()])
        after = re.match(r"\s+(?:named|called)\s+([a-z][\w-]*(?:\s*(?:,|and)\s*[a-z][\w-]*)*)", lowered[m.end():])
        wanted: List[str] = []
        if after:
            wanted = [w for w in re.split(r"\s*(?:,|and)\s*", after.group(1)) if w]
        elif before and before.group(1) not in _NOT_RESOURCE_NAMES and not before.group(1).isdigit() \
                and before.group(1) not in _NUMBER_WORDS:
            wanted = [before.group(1)]  # "a jobs queue"
        count = max(len(wanted), _count_before(lowered, m.start() - (len(before.group(1)) + 1 if before and wanted
                                                                      else 0)))
        for i in range(count):
            key = wanted[i] if i < len(wanted) else ""
            conflict = ""
            if key and key in existing and key not in [c["key"] for c in cards]:
                conflict = key  # named by the user and already there: ask, don't rename silently
            elif not key or key in taken:
                base = {"storage": "bucket"}.get(kind, kind)
                n = 1
                while f"{base}-{n}" in taken:
                    n += 1
                key = f"{base}-{n}"
            taken.append(key)
            card: Dict[str, Any] = {"kind": "resource", "key": key, "type": kind, "provider": provider}
            if conflict:
                other = free_name(key, taken + existing)
                taken.append(other)
                was = raw["resources"].get(key) if isinstance(raw.get("resources"), dict) else None
                card.update(exists=True, suggested=other,
                            existing_type=str((was or {}).get("type") or "") if isinstance(was, dict) else "",
                            conflict=f"{key} is already a resource in pskit.yml: replace it, or use {other}")
            cards.append(card)
            what = {"storage": "bucket", "smtp": "mail inbox (smtp)"}.get(kind, kind)
            if conflict:
                plan.append(f"{len(cards)}. **{key}** already exists"
                            + (f" (a {card['existing_type']})" if card.get("existing_type") else "")
                            + f". **Replace** it with a new {what}, or add it as **{card['suggested']}**? Pick on its "
                              "card.")
                continue
            plan.append(f"{len(cards)}. **{key}**: " + ("an existing " if kind in EXTERNAL_RESOURCES else "a new ")
                        + what
                        + (" (pskit hands its host / port to the functions; pskit doesn't create databases or caches)"
                           if kind in EXTERNAL_RESOURCES else f" that pskit creates ({provider or 'the provider'})"))
    if not cards:
        return None
    plan += ["", "One card each, written to pskit.yml (backed up first) and validated when you click **Add**. Then a "
             "function can use it, e.g. \"trigger worker from the jobs queue\"."]
    return _many("\n".join(plan), cards)


# "separate apps", "own folder with its own requirements", "different app for each function"
_SEPARATE = re.compile(
    r"\b(separate|seperate|seprate|sepearte|sepearate|own|individual|different|diffrent|differnt|independent|"
    r"isolated|dedicated|distinct)\b[^.?!]{0,40}?\b(apps?|applications?|folders?|projects?|sub-?projects?|"
    r"requirements?(?:\.txt)?|modules?|packages?|dirs?|directories|files?)\b|\bsub-?projects?\b|"
    r"\b(?:each|every)\s+(?:function|funtion|fn)?\s*(?:in|as|with|gets?|has|have)\s+(?:its|their|an?)\s+own\b", re.I)
# "in app/handlers", "to the existing app", "same file as hello"
_SHARED = re.compile(r"\b(?:in|into|to|inside|under)\s+(?:the\s+)?(?:existing|same|current|shared|one|single)\s+"
                     r"(?:apps?|modules?|files?|folders?|handlers?)\b|\b(?:same|one|single|shared)\s+(?:app|module|"
                     r"file)\b", re.I)
_DECISION = {"update": re.compile(r"\b(update|replace|overwrite|change|modify|keep|reuse|use)\b(?!\s+(?:a\s+)?"
                                  r"(?:another|other|different|new)\s+name)", re.I),
             "rename": re.compile(r"\b(rename|another name|other name|different name|new name|give .{0,12}name|"
                                  r"-2\b|suffix)", re.I),
             "skip": re.compile(r"\b(skip|leave|ignore|don'?t (?:create|touch|change))\b", re.I)}
_NOT_FUNCTION_NAMES = {"code", "codes", "handler", "handlers", "stub", "stubs", "boilerplate", "lambda", "app", "apps",
                       "separate", "seperate", "own", "different", "diffrent", "each", "every", "folder", "folders",
                       "requirement", "requirements", "module", "file", "files", "function", "functions", "funtion",
                       "funtions", "empty", "simple", "basic", "python", "node", "http", "api", "rest", "scheduled"}


def placement_in(text: str, modules: List[str]) -> Tuple[str, str]:
    """Where the user wants the code: ``("separate", "")``, ``("module", "app.handlers")`` or ``("", "")`` (not
    said: Hana asks). A module is matched when its path is written ("app/handlers", "app.handlers", "handlers.py")."""
    low = text.lower()
    for module in modules:
        path = module.replace(".", "/")
        last = module.rsplit(".", 1)[-1]
        if re.search(rf"(?<![\w/.]){re.escape(path)}(?:\.py)?\b|(?<![\w.]){re.escape(module)}\b|"
                     rf"(?<![\w/.]){re.escape(last)}\.py\b", low) and not _SEPARATE.search(low):
            return "module", module
    if _SEPARATE.search(low):
        return "separate", ""
    if _SHARED.search(low):
        return "module", modules[0] if modules else ""
    return "", ""


def decision_in(text: str) -> str:
    """For a name that already exists: ``update`` / ``rename`` / ``skip``, or "" when the user didn't say."""
    low = text.lower()
    for choice in ("rename", "skip", "update"):
        if _DECISION[choice].search(low):
            return choice
    return ""


def _trigger_in(lowered: str) -> Tuple[str, str]:
    trigger = "http" if re.search(r"\b(http|endpoints?|api|routes?|rest|get|post)\b", lowered) else \
        "schedule" if re.search(r"\b(schedule\w*|every|cron|hourly|daily|minutes?)\b", lowered) else "none"
    every = re.search(r"\bevery\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?)\b", lowered)
    if every:
        n, unit = int(every.group(1)), every.group(2)
        unit = "minute" if unit.startswith("min") else "hour" if unit.startswith(("hour", "hr")) else "day"
        return trigger, f"{n} {unit}{'s' if n != 1 else ''}"
    return trigger, "5 minutes"


def _functions_intent(text: str, lowered: str, root: Path) -> Optional[Dict[str, Any]]:
    """"create step01 step02 step03 functions" -> one card: each function in pskit.yml with its handler code.

    Hana asks (on the card, and in the reply) what the message didn't say: whether each function is its own app
    (``functions/<name>/`` with its own requirements.txt) or goes into an existing module, and, for a name that is
    already in pskit.yml, whether to update that function, create it under another name or skip it."""
    from .edits import free_name, handler_module, modules, names, raw_config, separate_handler

    raw = raw_config(root)
    if not raw:
        return None
    existing = names(raw, "function")
    asked = [n for n in _new_function_names(text, names(raw, "workflow")) if n not in _NOT_FUNCTION_NAMES]
    if not asked:
        return None
    new = [n for n in asked if n not in existing]
    taken = [n for n in asked if n in existing]
    if taken and not new:
        code = _code_intent(lowered, root)  # they exist: what may be missing is their code
        if code is not None and code.get("cards"):
            return code
    trigger, schedule = _trigger_in(lowered)
    shared = modules(root, raw)
    placement, module = placement_in(text, shared)
    module = module or handler_module(raw)
    decision = decision_in(text) if taken else ""
    suggested = {n: free_name(n, existing + asked) for n in taken}
    language = "node" if str((raw.get("provider") or {}).get("runtime") or "").startswith("nodejs") else "python"
    lines = ["Here is what I understood:", ""]
    if new:
        lines.append(f"1. Create the function{'s' if len(new) > 1 else ''} " + ", ".join(f"**{n}**" for n in new)
                     + ": an entry in pskit.yml and its handler code.")
    lines.append(f"{len(lines) - 1}. Trigger: " + {"none": "none (called directly or by a workflow)",
                                                   "http": "HTTP `GET /<name>` each",
                                                   "schedule": f"a schedule, every {schedule}"}[trigger] + ".")
    if placement == "separate":
        example = separate_handler(asked[0], language).rsplit(".", 2)[0].replace(".", "/")
        lines.append(f"{len(lines) - 1}. Each function is **its own app**: `{example}/` with its own "
                     "`requirements.txt` (only its dependencies; on premises with placement only its server gets it).")
    elif placement == "module":
        lines.append(f"{len(lines) - 1}. The code goes into the existing `{module.replace('.', '/')}.py`.")
    questions: List[str] = []
    if not placement:
        users = [n for n, fn in (raw.get("functions") or {}).items() if isinstance(fn, dict)
                 and str(fn.get("handler") or "").startswith(module + ".")]
        questions.append("**Where should the code go?** Each function as **its own app** (`functions/<name>/` with "
                         "its own `requirements.txt`), or **added to an existing app**: `"
                         + module.replace(".", "/") + ".py`" + (f" (shared with {', '.join(users[:4])})" if users
                                                                 else "") + "?")
    if taken and not decision:
        questions.append("**" + ", ".join(taken) + f"** already exist{'s' if len(taken) == 1 else ''}. "
                          + "Update " + ("it" if len(taken) == 1 else "them") + " (keep the code, apply this trigger"
                          + (" and move it into its own app" if placement == "separate" else "") + "), create "
                          + ("it" if len(taken) == 1 else "them") + " under another name ("
                          + ", ".join(f"**{suggested[n]}**" for n in taken) + "), or skip?")
    elif taken:
        verb = {"update": "update the existing", "rename": "create under another name", "skip": "skip"}[decision]
        lines.append(f"{len(lines) - 1}. Already there: " + ", ".join(f"**{n}**" for n in taken) + f": {verb}"
                     + (" (" + ", ".join(f"{n} → **{suggested[n]}**" for n in taken) + ")" if decision == "rename"
                        else "") + ".")
    if questions:
        lines += ["", "Before I create anything, tell me (pick on the card, or answer here):", ""]
        lines += [f"- {q}" for q in questions]
    lines += ["", "Nothing changes until you click **Create** on the card: pskit.yml is backed up first, then "
              "validated."]
    card = {"kind": "functions", "names": asked, "trigger": trigger, "schedule": schedule, "module": module,
            "modules": shared or [module], "placement": placement, "existing": taken,
            "decisions": {n: decision for n in taken if decision}, "suggested": suggested}
    out = _many("\n".join(lines), [card])
    if questions:  # a typed answer ("separate apps", "rename") is read together with this request
        out["followup"] = {"prefix": text, "answers": "placement" if not placement else "decision"}
    return out


def _separate_intent(text: str, lowered: str, root: Path) -> Optional[Dict[str, Any]]:
    """"make step01, step02 and step03 separate apps", "remove app/steps and create a different app for each
    function": existing functions move from their shared file into their own folders with their own
    requirements.txt (a card lists what moves; nothing changes until the click)."""
    from ...core import function_split
    from .edits import modules, names, raw_config

    raw = raw_config(root)
    if not raw or not _SEPARATE.search(lowered):
        return None
    functions = names(raw, "function")
    handlers = {n: str((fn or {}).get("handler") or "") for n, fn in (raw.get("functions") or {}).items()
                if isinstance(fn, dict)}
    targets = [n for n in functions if _mentions(n, lowered)]
    if not targets:  # "app/steps", "steps.py": the functions whose code is in that file
        for module in modules(root, raw):
            path = module.replace(".", "/")
            if re.search(rf"(?<![\w/.]){re.escape(path)}(?:\.py)?\b|(?<![\w.]){re.escape(module)}\b|"
                         rf"(?<![\w/.]){re.escape(module.rsplit('.', 1)[-1])}\.py\b", lowered):
                targets += [n for n, h in handlers.items() if h.startswith(module + ".") and n not in targets]
    if not targets and re.search(r"\b(each|every|all)\b", lowered) and _ITEM_WORDS["function"].search(lowered):
        shared = set(modules(root, raw))
        targets = [n for n, h in handlers.items() if h.rsplit(".", 1)[0] in shared]
    if not targets:
        return None
    lines = ["Here is what I understood: each of these functions becomes **its own app**, a folder with its code "
             "and its own `requirements.txt`:", ""]
    plans: List[Dict[str, Any]] = []
    for fn in targets:
        try:
            p = function_split.plan(root, fn)
        except function_split.SplitError as exc:
            lines.append(f"- **{fn}**: stays as it is ({exc})")
            continue
        plans.append({"function": fn, "from": p["from"], "to": p["to"], "requirements": p["requirements"]})
        lines.append(f"- **{fn}**: `{p['from']}` → `{p['to']}`"
                     + (f" (requirements: {', '.join(p['requirements'])})" if p["requirements"] else ""))
    if not plans:
        return {"reply": "\n".join(lines) + "\n\nNothing to move.", "card": None, "direct": True}
    sources = sorted({p["from"] for p in plans})
    lines += ["", "Its handler in pskit.yml points at the new file; helpers it uses are copied. "
              + ", ".join(f"`{s}`" for s in sources) + " is deleted when nothing else is left in it. Click **Move** "
              "on the card (pskit.yml is backed up first, then validated)."]
    return _many("\n".join(lines), [{"kind": "separate", "functions": [p["function"] for p in plans], "plans": plans}])


def _code_intent(lowered: str, root: Path) -> Optional[Dict[str, Any]]:
    from .edits import missing_code, names, raw_config

    raw = raw_config(root)
    if not raw:
        return None
    named = [n for n in names(raw, "function") if _mentions(n, lowered)]
    missing = missing_code(root, named or None)
    if not missing:
        which = ", ".join(f"**{n}**" for n in named) if named else "every function"
        return {"reply": f"The code is already there for {which}: each handler exists in its file. Ask me to change "
                         "a function's code, e.g. \"make hello return the time\".", "card": None, "direct": True}
    lines = ["These functions are in pskit.yml but their code is missing, so they would fail when called:", ""]
    handlers = {str(n): str((fn or {}).get("handler") or "") for n, fn in (raw.get("functions") or {}).items()
                if isinstance(fn, dict)}
    for m in missing:
        twins = [n for n, h in handlers.items() if h == m["handler"] and n != m["function"]]
        lines.append(f"- **{m['function']}**: `{m['handler']}`"
                     + (f" (file `{m['file']}` has no such function)" if m["file"] else " (no file yet)")
                     + (f". Note: **{', '.join(twins)}** uses the same handler, so they run the same code; if "
                        f"they should differ, change {m['function']}'s handler on the **Functions** page" if twins else ""))
    lines += ["", "Click **Write the code** to create a handler stub for each (existing code is not changed). Then "
              "ask me to fill in what each one should do."]
    return _many("\n".join(lines), [{"kind": "code", "items": missing}])


def history_depth_exceeded(history: List[Dict[str, Any]]) -> bool:
    return any(d.get("role") == "_redo" for d in history[-2:])


def pending_followup(history: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The question studio asked in its last answer (``{"prefix", "names" | "answers"}``), when nothing happened
    since: no other message and no card run. ``history`` may end with the message being answered."""
    items = list(history)
    if items and items[-1].get("role") == "user":
        items = items[:-1]
    for item in reversed(items):
        role = item.get("role")
        if role == "assistant":
            follow = item.get("followup")
            return follow if isinstance(follow, dict) and follow.get("prefix") else None
        if role in ("user", "note", "_redo"):
            return None
    return None


def _server_question(lowered: str, root: Path) -> Optional[Dict[str, Any]]:
    """A question about one saved server (no change asked): answered from its saved settings."""
    from ...core.onprem_servers import list_servers

    if not re.search(r"\b(what|which|show|tell|details?|info|where|is|are)\b|\?", lowered) or re.search(
            r"\b(set|change|update|add|make|remove|delete|forget|create|deploy|install)\b", lowered):
        return None
    try:
        servers = list_servers(root)
    except Exception:  # noqa: BLE001
        return None
    hit = next((s for s in servers if _mentions(str(s["name"]), lowered)), None)
    if hit is None:
        return None
    fields = [("address", f"{hit.get('host')}"), ("SSH user", hit.get("user") or "root"),
              ("SSH port", str(hit.get("port") or 22)),
              ("log in with", "password" if hit.get("password_file") else "key file" if hit.get("identity_file")
               else "SSH agent / default key"),
              ("key file", hit.get("identity_file") or ""), ("sudo", "yes" if hit.get("sudo") else "no"),
              ("home (root) folder", hit.get("home") or "default (/opt/pskit for functions)"),
              ("data folder", hit.get("data_dir") or "default (Docker volumes)"),
              ("listen address", hit.get("bind") or "default (127.0.0.1 for functions, 0.0.0.0 for services)"),
              ("description", hit.get("description") or "")]
    asked = [label for key, label in (("home", "home (root) folder"), ("root", "home (root) folder"),
                                      ("data", "data folder"), ("listen", "listen address"), ("bind", "listen address"),
                                      ("user", "SSH user"), ("port", "SSH port"), ("ip", "address"),
                                      ("address", "address"), ("host", "address"), ("key", "key file"),
                                      ("pem", "key file"), ("sudo", "sudo")) if re.search(rf"\b{key}\b", lowered)]
    shown = [(label, value) for label, value in fields if value and (not asked or label in asked)]
    lines = [f"**{hit['name']}** ({hit.get('label') or hit.get('host')}):", ""]
    lines += [f"- {label}: `{value}`" for label, value in shown]
    lines += ["", f"To change it, say for example \"set the data folder of {hit['name']} to /data/pskit\"."]
    return {"reply": "\n".join(lines), "card": None, "direct": True, "first": True}


def _new_function_names(text: str, existing: List[str]) -> List[str]:
    """``create step-01 step-02 step-03 functions`` / ``functions named a, b and c`` -> the names to create."""
    found: List[str] = []
    stop = {"a", "an", "the", "new", "some", "few", "three", "two", "four", "five", "and", "first", "then", "me", "for",
            "all", "these", "those", "named", "called", "more", "my", "of", "to", "also", "write", "just", "please",
            "u", "you", "i", "both", "them", "it", "too"}

    def name_like(word: str) -> bool:  # step-01, worker2, send_mail: clearly a name, not an English word
        return bool(re.search(r"[-_\d]", word))

    # 1) "create step-01 step-02 step-03 functions": the words right before "function(s)"
    for m in re.finditer(r"\b(?:crea\w*|cerate|add|make|new|write)\s+((?:[a-z][\w-]*[\s,]+(?:and\s+)?){1,12}?)"
                         r"(?:new\s+)?fun\w*", text, re.I):
        words = [w for w in re.findall(r"[a-z][a-z0-9_-]*", m.group(1).lower()) if w not in stop]
        if words and (all(name_like(w) for w in words) or len(words) <= 2):
            found += [w for w in words if w not in found]
    # 2) "functions named alpha, beta and gamma" (the list ends at "then", "and a/the ...", "workflow" or ".")
    for m in re.finditer(r"\bfun\w*\s+(?:named|called)\s+(.+?)(?=\band\s+then\b|\bthen\b|\band\s+(?:a|an|the)\b|"
                         r"\bwork\s*flow|\b(?:as|with|that|which|for|on|to|using|runs?|running|every)\b|[.;\n]|$)",
                         text, re.I):
        words = [w for w in re.findall(r"[a-z][a-z0-9_-]*", m.group(1).lower()) if w not in stop]
        found += [w for w in words if w not in found]
    return [w.replace("_", "-") for w in found if w not in existing and len(w) <= 63]


def _wait_seconds(lowered: str) -> int:
    m = re.search(r"\b(?:delay|wait|sleep|pause|gap|deloy|dealy)\w*\b[^0-9]{0,20}(\d+)\s*(s|sec\w*|m|min\w*|h|hours?)?\b",
                  lowered) or re.search(r"\b(\d+)\s*(s|sec\w*|m|min\w*|h|hours?)\b[^.]{0,20}\b(?:delay|wait|sleep|"
                                        r"pause|gap|deloy|dealy)", lowered)
    if not m:
        return 0
    n, unit = int(m.group(1)), (m.group(2) or "s")
    return n * 3600 if unit.startswith("h") else n * 60 if unit.startswith("m") else n


def _workflow_intent(text: str, lowered: str, root: Path, asks_create: bool, howto: bool) -> Optional[Dict[str, Any]]:
    from .edits import names as item_names
    from .edits import raw_config

    raw = raw_config(root)
    if not raw:
        return None
    functions = item_names(raw, "function")
    workflows = item_names(raw, "workflow")
    if re.search(r"\b(run|start|execute|trigger|test)\b", lowered) and not asks_create:
        wf = next((w for w in workflows if _mentions(w, lowered)), workflows[0] if workflows else "")
        if not wf:
            return {"reply": "This project has no workflows yet. Ask me \"create a workflow\" to make one.",
                    "card": None, "direct": True}
        return {"reply": f"To run **{wf}**:\n\n**In studio**\n1. Open **Test**.\n2. Pick the workflow **{wf}**, enter "
                         "the input JSON and click **Run**.\n\n**In the terminal**\n```bash\n"
                         f"pskit workflow run {wf} -i '{{}}' --history      # here, on the embedded engine\n"
                         f"pskit workflow start {wf} -i '{{}}' --wait       # the deployed workflow\n```",
                "card": None, "direct": True}
    if not asks_create or howto:
        return None
    from .edits import handler_module, py_name

    new = _new_function_names(text, functions + workflows)
    wait = _wait_seconds(lowered)
    if not functions and not new:
        return {"reply": "A workflow runs this project's functions one after another, and the project has no "
                         "functions yet. Tell me which to create, e.g. \"create step-1 and step-2 functions and a "
                         "workflow that runs them\".", "card": None, "direct": True}
    # every function named in the message (new or existing), in the order it is written ("a then b")
    everything = functions + new
    positions = sorted((m.start(), f) for f in everything
                       for m in re.finditer(rf"(?<![\w-]){re.escape(f.lower())}(?![\w-])", lowered))
    steps = list(dict.fromkeys(f for _p, f in positions))
    # the workflow's own name: "a workflow called pipe" (not "functions named alpha")
    wf_named = re.search(r"\bwork\s*flow\w*\s+(?:named|called)\s+[\"'`]?([a-z][\w-]*)", text, re.I)
    others = [m.group("name") for m in _KEY_NAME.finditer(text) if m.group("name").lower() not in everything]
    name = (wf_named.group(1) if wf_named else (others[-1] if others else "")).lower()
    if not name or name in workflows or name in everything:
        n = 1
        while f"workflow-{n}" in workflows:
            n += 1
        name = f"workflow-{n}"
    card = {"kind": "workflow", "name": name, "steps": steps, "functions": everything, "create": new, "wait": wait}
    flow = (" → wait " + _human_seconds(wait) + " → ").join(steps) if wait else " → ".join(steps)
    plan = ["Here is what I understood:", ""]
    n = 1
    if new:
        module = handler_module(edits_raw(root))
        plan.append(f"{n}. Create the function{'s' if len(new) > 1 else ''} " + ", ".join(f"**{f}**" for f in new)
                    + f" (no trigger; a handler stub each, `{module}.{py_name(new[0])}`"
                    + (" and so on" if len(new) > 1 else "") + ").")
        n += 1
    if steps:
        plan.append(f"{n}. Create the workflow **{name}**: {flow}. Each step gets the previous step's result.")
    else:
        plan.append(f"{n}. Create the workflow **{name}**: pick its steps on the card.")
    plan += ["", "Check the card (you can rename, reorder or change the wait) and click **Create**: pskit.yml is backed "
             "up first, then validated. Branches, retries and parallel steps can be added on the **Workflows** page."]
    return _many("\n".join(plan), [card])


def _human_seconds(seconds: int) -> str:
    if seconds and seconds % 3600 == 0:
        return f"{seconds // 3600} h"
    if seconds and seconds % 60 == 0:
        return f"{seconds // 60} min"
    return f"{seconds} s"


def edits_raw(root: Path) -> Dict[str, Any]:
    from .edits import raw_config

    return raw_config(root)


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", word.lower())


def _mentions(name: str, lowered: str) -> bool:
    return bool(re.search(rf"(?<![\w.-]){re.escape(name.lower())}(?![\w.-])", lowered))


def server_details(text: str) -> Dict[str, Any]:
    """Host, user, port and key file from free text: ``ssh -i k.pem ubuntu@1.2.3.4``, ``public_ip = "..."``,
    ``ssh_user = "ubuntu"``, a ``.pem`` path (an absolute path wins over a relative one)."""
    out: Dict[str, Any] = {}
    m = _SSH_CMD.search(text)
    if m:
        out["user"], out["host"] = m.group("user"), m.group("host")
        port = re.search(r"-p\s+(\d+)", m.group("opts") or "")
        if port:
            out["port"] = int(port.group(1))
    for kv in _KV.finditer(text):
        key, value = kv.group("key").lower(), kv.group("value")
        if "user" in key and re.fullmatch(r"[A-Za-z_][\w.-]*", value):
            out.setdefault("user", value)
        elif ("ip" in key or "host" in key) and (_IP.fullmatch(value) or re.fullmatch(r"[\w.-]+\.[a-z]{2,}", value)):
            if "private" not in key:
                out["host"] = value
        elif key.endswith("port") and value.isdigit() and "ssh" in key:
            out["port"] = int(value)
    if "host" not in out:
        ips = _IP.findall(text)
        if ips:
            out["host"] = ips[0]
    pems = _PEM_ABS.findall(text) or [p.group("path") for p in _PEM.finditer(text)]
    if pems:
        out["identity_file"] = pems[-1]
    return out


# the words that introduce a secret (a pattern, not a password)
_SECRET_WORD = (r"\b(?:ssh[ _-]?|db[ _-]?|admin[ _-]?|root[ _-]?)?"  # noqa: S105
                r"(?:password|passwd|pwd|pass|passcode|secret|token|api[ _-]?key)\b")
# "password is / as / to / should be / = / : X" -> X is the secret, whatever it looks like
_PASSWORD_VALUE = re.compile(rf"({_SECRET_WORD}\s*(?:(?:is|as|to|be|should\s+be|will\s+be|of)\b|[=:])\s*)([^\s,;]+)",
                             re.I)
# "password Test@1234" (no linking word) -> hidden when the next word looks like a secret (a digit or a symbol)
_PASSWORD_BARE = re.compile(rf"({_SECRET_WORD}\s+)(?!<hidden>)([^\s,;]*[\d@#$%^&*!?+~][^\s,;]*)", re.I)


def redact_password(text: str) -> str:
    """``password as Test@1234`` -> ``password as <hidden>``: a password typed in the chat, a plan note or an answer
    is never stored or sent to the model."""
    return _PASSWORD_BARE.sub(r"\1<hidden>", _PASSWORD_VALUE.sub(r"\1<hidden>", text))


def server_options(text: str) -> Dict[str, Any]:
    """The optional server fields from free text: login method, sudo, SSH port, user, bind address,
    description (the folders come from ``_folders``)."""
    out: Dict[str, Any] = {}
    low = text.lower()
    if re.search(r"\b(no|without|don'?t use|disable)\s+sudo\b", low):
        out["sudo"] = False
    elif re.search(r"\bsudo\b", low):
        out["sudo"] = True
    if re.search(r"\b(password|passwd)\b", low) and not re.search(r"\b(no|without)\s+password", low):
        out["auth"] = "password"
    elif re.search(r"\bssh[- ]agent\b|\bdefault key\b|\bagent\b", low):
        out["auth"] = "agent"
    m = re.search(r"\b(?:ssh\s+)?port\s*(?:is|=|:|to|of)?\s*(\d{2,5})\b", low)
    if m and 0 < int(m.group(1)) < 65536:
        out["port"] = int(m.group(1))
    m = re.search(r"\buser(?:name)?\s*(?:is|=|:|to|as)\s*[\"'`]?([A-Za-z_][\w.-]{0,31})", text, re.I)
    if m:
        out["user"] = m.group(1)
    m = re.search(r"\b(?:bind|listen)(?:\s+(?:address|addr|ip|on))*\s*(?:is|=|:|to|on)?\s*"
                  r"((?:\d{1,3}\.){3}\d{1,3})", low)
    if m:
        out["bind"] = m.group(1)
    # a value only after "is / = / : / to / as" (or in quotes): "add a description" alone leaves it to the user
    m = re.search(r"\b(?:description|desc|note|label)\s*(?:is|=|:|to|as)?\s*[\"'`]([^\"'`\n]{1,200})[\"'`]", text, re.I)
    if not m:
        m = re.search(r"\b(?:description|desc|note|label)\s*(?:is|=|:|to|as)\s*([^,\n]{1,200}?)\s*(?:,|\band\b|$)",
                      text, re.I | re.M)
    if m and m.group(1).strip():
        out["description"] = m.group(1).strip()
    return out


def _folders(text: str) -> Dict[str, str]:
    """``home /opt/pskit and data /data/pskit`` -> ``{"home": ..., "data_dir": ...}`` (a path after its word)."""
    out: Dict[str, str] = {}
    # The field's word must not be part of a path ("/home/azureuser" is a path, not the word "home"), and the path
    # is taken whole (a trailing "/" dropped): "make root to /home/azureuser/" -> home "/home/azureuser".
    words = (("home", r"home(?:\s+(?:path|folder|dir\w*))?|root(?:\s+(?:path|folder|dir\w*))?|base\s+(?:path|dir\w*)"),
             ("data_dir", r"data(?:\s+(?:path|folder|dir\w*))?"))
    for field, word in words:
        m = re.search(rf"(?<![/\w])(?:{word})\b(?![/\w])[^/\n]{{0,40}}?(/[\w.-]+(?:/[\w.-]+)*/?|/)(?![\w.-])", text, re.I)
        if m:
            path = m.group(1)
            out[field] = path.rstrip("/") or "/"
    if not out:
        paths = _POSIX_PATH.findall(text)
        if len(paths) == 1 and re.search(r"(?<![/\w])home\b(?!/)", text, re.I) and not re.search(r"\bdata\b", text, re.I):
            out["home"] = paths[0].rstrip("/") or "/"
    return out


def _user_from_paths(folders: Dict[str, str]) -> str:
    """``/home/azureuser`` -> ``azureuser``: the SSH user when the message gave none."""
    for path in folders.values():
        m = re.match(r"^/home/([A-Za-z_][\w.-]{0,31})(/|$)", path)
        if m:
            return m.group(1)
    return ""


def _service(text: str, catalog: List[Dict[str, Any]]) -> Optional[str]:
    words = {_norm(w) for w in re.findall(r"[\w.-]+", text)}
    for word in list(words):
        if word in _ALIASES:
            words.add(_ALIASES[word])
    for item in catalog:
        if _norm(item["id"]) in words:
            return str(item["id"])
    for item in catalog:
        first = _norm(str(item["label"]).split(" ")[0])
        if first and first not in _GENERIC_LABEL_WORDS and first in words:
            return str(item["id"])
    return None


# first words of catalog labels that are not the service's name ("AWS Secrets Manager compatible", "Apache Kafka")
_GENERIC_LABEL_WORDS = {"aws", "amazon", "apache", "eclipse", "uptime", "fakegcsserver"}


_KIND_RX = [
    ("service", r"services?|databases?|dbs?|caches?|brokers?|containers?"),
    ("cluster", r"clusters?|clust\w*"),
    ("balancer", r"load[ -]?bal\w*|lbs?"),
    ("function", r"fun[ct]\w*|handlers?|endpoints?|routes?"),
    ("workflow", r"work\s*flows?"),
    ("resource", r"reso\w*|resou\w*|resorces?|queues?|buckets?|topics?"),
    ("server", r"servers?|severs?|servs?|machines?|vms?|hosts?|instances?"),
]


def object_and_place(lowered: str, catalog: Optional[List[Dict[str, Any]]] = None,
                     servers: Optional[List[str]] = None) -> Tuple[Optional[str], Optional[str]]:
    """What the request is about, and where it goes: "add a service to a server" -> ("service", "server");
    "add app-3 to cluster-1" -> ("server", "cluster"). A noun after to / on / in / onto / into / for is the place,
    not the thing; the thing is the first other noun. A catalog service (redis ...) counts as a service."""
    found: List[Tuple[int, str, bool]] = []
    for kind, rx in _KIND_RX:
        for m in re.finditer(rf"\b(?:{rx})\b", lowered):
            before = lowered[max(0, m.start() - 24):m.start()]
            is_place = bool(re.search(r"\b(to|on|in|onto|into|inside|at|for|of|from)\s+(?:(?:a|an|the|my|our|this|that|"
                                      r"every|each|all|one)\s+)?(?:[\w-]+\s+)?$", before))
            found.append((m.start(), kind, is_place))
    if catalog:
        for m in re.finditer(r"[\w.-]+", lowered):
            if _service(m.group(0), catalog):
                found.append((m.start(), "service", False))
    for name in servers or []:  # a saved server's name ("add app-1 to a cluster") is a server too
        for m in re.finditer(rf"(?<![\w.-]){re.escape(name.lower())}(?![\w.-])", lowered):
            before = lowered[max(0, m.start() - 24):m.start()]
            found.append((m.start(), "server", bool(re.search(r"\b(to|on|in|onto|into|at|for|of|from)\s+(?:the\s+)?$",
                                                              before))))
    found.sort()
    thing = next((k for _p, k, place in found if not place), None)
    place = next((k for _p, k, is_place in found if is_place and k != thing), None)
    return thing, place


_STEPS_Q = re.compile(
    r"^\s*(?:no,?\s+)?(?:i\s+mean\s+)?(?:pl(?:ea)?se?\s+|pls\s+|can\s+(?:you|u)\s+)?"
    r"(how(?!\s+(?:many|much|long|often|old|big))|steps?|step[- ]by[- ]step|guide|walk me through|explain how|"
    r"show me how|tell me how|procedure|"
    r"what are the steps|(?:provide|give|share|send|list|write)(?:\s+me)?\s+(?:the\s+)?(?:steps?|guide|procedure|"
    r"instructions?))\b|\b(steps?\s+(?:to|for)|how\s+(?:to|do\s+i|can\s+i|i\s+can|should\s+i)|instructions?\s+"
    r"(?:to|for))\b", re.I)


def how_to(kind: str, root: Path, names: List[str], service: Optional[Dict[str, Any]] = None,
           role: str = "") -> Dict[str, Any]:
    """Step-by-step answers (studio, terminal, code) for "how do I / steps to" requests. Only steps: nothing is
    created, and the reply says which request would do it."""
    from ...core import onprem_cluster

    try:
        clusters = [str(c["name"]) for c in onprem_cluster.list_clusters(root)]
    except Exception:  # noqa: BLE001
        clusters = []
    server = names[0] if names else "app-1"
    servers_line = f"Your saved servers: {', '.join(f'**{n}**' for n in names)}." if names else \
        "You have no saved servers yet."
    if kind == "service":
        database = role == "database" or bool(service and "database" in (service.get("roles") or []))
        if service:
            label = service["label"]
        elif database:
            label = "a database (PostgreSQL, MySQL, MariaDB, MongoDB ...)"
        else:
            label = "a service (Redis, PostgreSQL, RabbitMQ, MinIO ...)"
        sid = service["id"] if service else "postgres" if database else "redis"
        key = f"{sid.split('-')[0]}-1"
        replicated = bool(service.get("replication")) if service else database
        scaling = ("4. **Scaling** (databases): **Single server**, or **Primary + read replicas**: the primary takes "
                   "every write, replicas on other servers serve reads, with "
                   + ("a load balancer in front (pgpool-II for PostgreSQL, ProxySQL for MySQL / MariaDB) and "
                      if replicated else "")
                   + "async or sync replication. It needs at least two saved servers.\n") if database else ""
        n = 5 if database else 4
        text = (f"Steps to create **{label}**:\n\n**In studio**\n"
                "1. Open **Resources** > **On-prem services** and click **+ Create service**.\n"
                f"2. Pick **{label if service else 'the ' + ('database' if database else 'service')}**"
                + (" (PostgreSQL, MySQL, MariaDB or MongoDB)" if database and not service else "") + ".\n"
                "3. In **Where**, choose **This machine**, an SSH server (then pick it under **Server**) or a "
                "**scaling cluster** (pick the cluster; studio places it on its server with the most free memory).\n"
                + scaling
                + f"{n}. Set the name, then click **Create**. Docker is installed on the server when missing; the log "
                "shows the progress, and the password is saved in the project's env file, not in pskit.yml.\n"
                f"{n + 1}. On its row, click **Add to pskit.yml** so your functions get its connection.\n\n"
                "**In the terminal**\n```bash\n"
                f"pskit resources onprem create {key} --service {sid} --server {server}\n"
                f"pskit resources onprem create {key} --service {sid} --cluster {clusters[0] if clusters else 'cluster-1'}"
                + (f"\n# primary + read replicas (scaling):\npskit resources onprem create {key} --service {sid} "
                   f"--primary {server} --replica {names[1] if len(names) > 1 else 'app-2'}"
                   + (f" --balancer {server}" if sid != "mongodb" else "") + " --sync async" if database else "")
                + "\n```\n\n" + servers_line
                + (f" Clusters: {', '.join(f'**{c}**' for c in clusters)}." if clusters else "")
                + f"\n\nWant me to prepare it? Say for example \"create {sid} on {server}\".")
    elif kind == "server":
        text = ("Steps to add a server:\n\n**In studio**\n"
                "1. Open **Resources** > **On-prem services**, then **Servers** > **+ Add server** (or **Scaling "
                "cluster** > **+ Add a server**).\n"
                "2. Enter a name, the host (IP or DNS name), the SSH user and port.\n"
                "3. **Log in with**: a key file (.pem), the SSH agent, or a password.\n"
                "4. Optional: **Use sudo**, the home path, bind address and data directory.\n"
                "5. Click **Save and test**: studio logs in once and shows the OS, CPU, memory and Docker.\n\n"
                "**In the terminal**\n```bash\npskit resources onprem servers add app-1 --ssh ubuntu@203.0.113.10 "
                "--pem ~/.ssh/app-1.pem\npskit resources onprem servers test app-1\n```\n\n"
                "Want me to add it? Paste its IP, user and `.pem` path (or the Terraform outputs).")
    elif kind == "cluster":
        text = ("Steps to create a scaling cluster:\n\n**In studio**\n"
                "1. Open **Scaling cluster** and click **+ New cluster**.\n"
                "2. Enter the name, pick the orchestrator (Docker Swarm, Kubernetes k3s or Nomad) and the **master** "
                "server.\n3. Click create; studio installs the orchestrator over SSH.\n"
                "4. Click **+ Join server** for each other server.\n"
                "5. Deploy to it: **Deploy** > **Run on** > the cluster.\n\n"
                "**In the terminal**\n```bash\n"
                f"pskit cluster create cluster-1 -o swarm --master {server}\n"
                f"pskit cluster join cluster-1 {names[1] if len(names) > 1 else 'app-2'}\n"
                "pskit deploy --cluster cluster-1\n```\n\n" + servers_line
                + "\n\nWant me to prepare it? Say for example \"create a cluster with 2 servers\".")
    elif kind == "balancer":
        text = ("Steps to create a load balancer:\n\n**In studio**\n"
                "1. Open **Load balancers** and click **+ Create load balancer**.\n"
                "2. Pick the server it runs on, the port and the algorithm.\n"
                "3. Attach the cluster(s) it sends requests to.\n"
                "4. In pskit.yml set `provider.options.balancer: <name>`; the next deploy adds the route "
                "`http://<load balancer>/<service>/`.\n\n**In the terminal**\n```bash\n"
                f"pskit lb create lb-1 --server {server} --algorithm least_connections\n"
                f"pskit lb attach lb-1 --cluster {clusters[0] if clusters else 'cluster-1'}\npskit lb algorithms\n```\n\n"
                + servers_line + "\n\nWant me to prepare it? Say for example \"create a load balancer\".")
    elif kind == "function":
        text = ("Steps to create a function:\n\n**In studio**\n"
                "1. Open **Functions** and click **+ Create function**.\n"
                "2. Enter the name and the handler (e.g. `app.handlers.orders`), pick the trigger (HTTP, schedule, "
                "queue, storage, topic) and click **Create function**: studio writes a handler stub.\n"
                "3. Write the code on the **Code** page, then **Test** it.\n\n**In code**\n```yaml\nfunctions:\n"
                "  orders:\n    handler: app.handlers.orders\n    events:\n      - http: GET /orders\n```\n"
                "```python\ndef orders(event, ctx):\n    return {\"orders\": []}\n```\n\n"
                "Want me to do it? Say for example \"create an orders function as an http endpoint\".")
    elif kind == "workflow":
        text = ("Steps to create a workflow:\n\n**In studio**\n"
                "1. Open **Workflows** and click **+ Create workflow**.\n"
                "2. Add the steps (tasks that run your functions, waits, choices, parallel branches).\n"
                "3. Save, then run it on the **Test** page.\n\n**In code**\n```yaml\nworkflows:\n  orders:\n"
                "    start_at: Validate\n    states:\n      Validate: {type: task, function: validate, next: Wait}\n"
                "      Wait: {type: wait, seconds: 10, next: Charge}\n      Charge: {type: task, function: charge, "
                "end: true}\n```\n\n**In the terminal**\n```bash\npskit workflow run orders -i '{}' --history\n```\n\n"
                "Want me to do it? Say for example \"create a workflow with validate then charge\".")
    else:  # resource
        text = ("Steps to add a resource (queue, bucket, topic, database, cache):\n\n**In studio**\n"
                "1. Open **Resources** and click **+ Add resource**.\n"
                "2. Pick the type. Queues, buckets and topics are created by pskit; a database or cache that already "
                "exists is added with its host, port and the NAME of the env variable holding its password.\n"
                "3. Save; functions read it with `resource(\"name\")`.\n\n**In code**\n```yaml\nresources:\n"
                "  jobs:\n    type: queue\n  orders-db:\n    type: database\n    external: true\n    connection:\n"
                "      host: ${env:ORDERS_DB_HOST, localhost}\n      port: 5432\n      password_env: ORDERS_DB_PASSWORD\n```"
                "\n\nWant me to do it? Say for example \"add a jobs queue\".")
    return {"reply": text, "card": None, "direct": True}


def _how_service_on_server(names: List[str]) -> Dict[str, Any]:
    example = names[0] if names else "server-1"
    saved = (", ".join(f"**{n}**" for n in names) if names else "none yet (add one first: paste its IP, user and "
             "`.pem` path)")
    return {"reply": "To run a service (Redis, PostgreSQL, RabbitMQ, MinIO ...) on one of your servers:\n\n"
                     "**In studio**\n"
                     "1. Open **Resources** > **On-prem services** and click **+ Create service**.\n"
                     "2. Pick the service.\n"
                     "3. In **Where**, choose the SSH server and pick it under **Server** (Docker is installed there "
                     "when missing).\n"
                     "4. Click **Create**; the log shows the progress.\n\n"
                     "**In the terminal**\n```bash\n"
                     f"pskit resources onprem create cache-1 --service redis --server {example}\n```\n\n"
                     f"Your saved servers: {saved}.\n\n"
                     f"Or tell me which one and where, e.g. \"create redis on {example}\", and I'll prepare it.",
            "card": None, "direct": True}


def _how_join_cluster(root: Path, names: List[str]) -> Dict[str, Any]:
    from ...core import onprem_cluster

    try:
        clusters = [str(c["name"]) for c in onprem_cluster.list_clusters(root)]
    except Exception:  # noqa: BLE001
        clusters = []
    cluster = clusters[0] if clusters else "cluster-1"
    server = names[0] if names else "server-1"
    return {"reply": "To add a saved server to a scaling cluster:\n\n**In studio**\n"
                     "1. Open **Scaling cluster** and pick the cluster.\n"
                     "2. Click **+ Join server** and choose the server; studio installs the agent and copies the "
                     "deployed images.\n\n**In the terminal**\n```bash\n"
                     f"pskit cluster join {cluster} {server}\n```\n\n"
                     f"Clusters: {', '.join(f'**{c}**' for c in clusters) or 'none yet'}. Saved servers: "
                     f"{', '.join(f'**{n}**' for n in names) or 'none yet'}.",
            "card": None, "direct": True}


def _count_before(lowered: str, pos: int) -> int:
    """"2 redis" / "two queues" / "a cache": the number written right before position ``pos`` (default 1)."""
    m = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:more\s+|new\s+|\w+\s+)?$",
                  lowered[:pos][-30:])
    if not m:
        return 1
    word = m.group(1)
    n = int(word) if word.isdigit() else _NUMBER_WORDS[word]
    return n if 0 < n <= 20 else 1


def _service_requests(text: str, lowered: str, catalog: List[Dict[str, Any]],
                      servers: List[str]) -> List[Any]:
    """Every catalog service named, in order, with how many and where: "2 redis on app-1 and postgres on app-2"
    -> [("redis", 2, "app-1"), ("postgres", 1, "app-2")]. The server is the first saved server named after the
    service and before the next one."""
    hits: List[Any] = []
    for m in re.finditer(r"[\w.-]+", lowered):
        one = _service(m.group(0), catalog)
        if one and all(one != h[1] for h in hits):
            hits.append((m.start(), one))
    out = []
    for i, (pos, service) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(lowered)
        segment = lowered[pos:end]
        server = next((s for s in sorted(servers, key=lambda s: segment.find(s.lower()) if s.lower() in segment else 9e9)
                       if _mentions(s, segment)), "")
        out.append((service, _count_before(lowered, pos), server))
    return out


def _services(text: str, catalog: List[Dict[str, Any]]) -> List[str]:
    """Every catalog service named in the text, in the order they appear ("redis and postgres" -> both)."""
    found: List[str] = []
    for word in re.findall(r"[\w.-]+", text):
        one = _service(word, catalog)
        if one and one not in found:
            found.append(one)
    return found


def _next_name(taken: List[str]) -> str:
    n = 1
    while f"server-{n}" in taken:
        n += 1
    return f"server-{n}"


def _recent_card(history: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for item in reversed(history):
        card = item.get("card") if item.get("role") == "action" else None
        if isinstance(card, dict) and card.get("kind") == "server":
            return card
    return None


def _recent_server(history: List[Dict[str, Any]], names: List[str]) -> Optional[str]:
    """The server the chat was last about: the newest card or note naming a saved server."""
    for item in reversed(history):
        if item.get("role") == "action" and isinstance(item.get("card"), dict):
            name = item["card"].get("name")
            if name in names:
                return str(name)
        text = str(item.get("text") or "")
        for name in names:
            if f"**{name}**" in text or _mentions(name, text.lower()):
                return name
    return None


def detect(text: str, root: Path, history: List[Dict[str, Any]], provider: str = "",
           stage: str = "dev") -> Optional[Dict[str, Any]]:
    from ...core.onprem_servers import list_servers
    from ...core.onprem_services import catalog as service_catalog
    from ...core.onprem_services import list_services

    lowered = text.lower()
    if _TOOLS_Q.search(lowered):
        return {"reply": CAPABILITIES, "card": None, "direct": True, "first": True}
    # an answer to the question studio just asked ("Which function should I remove?" -> "step01, step02"): read
    # together with that question, and answered by studio (the model didn't see the question's context)
    pending = pending_followup(history)
    if pending is not None and not history_depth_exceeded(history) and len(lowered.split()) <= 15:
        fits = any(_mentions(str(n), lowered) for n in pending.get("names") or []) or (
            pending.get("answers") in ("placement", "decision")
            and bool(placement_in(text, [])[0] or decision_in(text)))
        if fits:
            redo = detect(f"{pending['prefix']} {text}", root, history + [{"role": "_redo"}], provider, stage)
            if redo is not None:
                return {**redo, "first": True}
    # "i mean servers": a correction of the previous request -> do that request again with the correction
    correction = re.match(r"\s*(?:no[,.]?\s+)?(?:i\s+mean[t]?|i\s+meant|actually|sorry,?)\s+(.+)", lowered)
    prev_text = next((str(d.get("text") or "") for d in reversed(history) if d.get("role") == "user"), "")
    if correction and prev_text and len(correction.group(1).split()) <= 4 and not history_depth_exceeded(history):
        redo = detect(f"{prev_text} {correction.group(1)}", root, history + [{"role": "_redo"}], provider, stage)
        if redo is not None:
            return redo
    # one saved server named in a question: its saved settings ("what is root path in AZ_VM_01_2cpu")
    asked_server = _server_question(lowered, root)
    if asked_server is not None:
        return asked_server
    hinglish = len(_HINGLISH.findall(lowered)) >= 2
    if _IDENTITY.search(lowered):
        return {"reply": IDENTITY + (" (I answer in English.)" if hinglish else ""), "card": None, "direct": True,
                "first": True}
    if lowered.strip(" ?!.") in _VAGUE or not re.search(r"[a-z0-9]", lowered):
        return {"reply": VAGUE, "card": None, "direct": True}
    if _PROJECT_Q.search(lowered) and not (_DO.search(lowered) and not re.search(
            r"\b(what|explain|describe|tell me|summar\w*|overview|purpose)\b", lowered)):
        summary = project_summary(root)
        if summary:
            return {"reply": summary, "card": None, "direct": True, "first": True}
    if hinglish and not re.search(r"\b(server|function|deploy|cluster|redis|postgres|yml|error)\b", lowered):
        return {"reply": "I answer best in English. Could you ask in English? For example: \"what is this project "
                         "for?\", \"add a GET /health endpoint\", \"how many servers do we have?\" or \"who are you?\"",
                "card": None, "direct": True}
    try:
        servers = list_servers(root)
    except Exception:  # noqa: BLE001 - a broken servers file must not break the chat
        servers = []
    try:
        services = list_services(root)
    except Exception:  # noqa: BLE001
        services = []
    names = [str(s["name"]) for s in servers]
    keys = [str(s.get("key")) for s in services]
    catalog = [c for c in service_catalog() if c.get("kind") == "service"]
    howto = bool(_HOWTO.match(text)) and "for me" not in lowered
    # "servers", "lst ser": the saved servers
    if lowered.strip(" ?!.") in ("servers", "server", "ser", "sers", "severs", "vms", "machines") or re.fullmatch(
            r"\s*(?:list|lst|lis|show)\s+(?:all\s+)?(?:the\s+)?(?:ser|sers|srv|srvs|servers?)\s*[?!.]*\s*", lowered):
        return {"reply": _server_list(servers), "card": None, "direct": True, "first": True}
    # commands studio runs for the user (they click Run first; the model then answers from the output)
    if not howto and not _STEPS_Q.search(lowered):
        runtimes = [str(c["id"]) for c in service_catalog() if c.get("kind") == "runtime"]
        run = _terminal_intent(text, lowered, names, runtimes, history)
        if run is not None:
            return run
    named = next((n for n in names if _mentions(n, lowered)), None)
    named_key = next((k for k in keys if _mentions(k, lowered)), None)
    about_server = bool(_SERVER_WORD.search(lowered)) or named is not None
    about_service = bool(_SERVICE_WORD.search(lowered)) or named_key is not None or (
        _service(text, catalog) is not None and _ONPREM_WORDS.search(lowered) is not None)
    remove = bool(_REMOVE.search(lowered)) and not howto
    definition = bool(re.match(r"\s*(what|what's|whats)\s+(is|are)\s+(a|an|the)?\s*\w+", lowered)) and not re.search(
        r"\b(my|our|this project'?s?|saved|existing)\b", lowered)  # "what is a queue trigger?" asks about pskit
    listing = bool(_LIST.search(lowered)) and not remove and not definition and not _DO.search(
        lowered.replace("do i have", "").replace("do we have", ""))

    # ---- first: what is this message about, and where does it go? ("a service TO a server" is about a service)
    thing, place = object_and_place(lowered, catalog, names)
    asks_how = howto or bool(re.match(r"\s*(?:no,?\s+)?(?:i\s+mean\s+)?(how(?!\s+(?:many|much|long|often|old|big))|"
                                      r"can i|can we|could i|is it possible|"
                                      r"what is the way|where do i)\b", lowered))
    if thing == "server" and place == "cluster" and asks_how:
        return _how_join_cluster(root, names)
    # "provide steps to create a postgresql", "how do I add a load balancer": steps only, nothing is created
    if (asks_how or _STEPS_Q.search(lowered)) and not remove and thing in (
            "service", "server", "cluster", "balancer", "function", "workflow", "resource"):
        named_service = _services(text, catalog)
        spec = next((c for c in catalog if named_service and c["id"] == named_service[0]), None)
        role_hint = "database" if re.search(r"\b(databases?|dbs?|sql)\b", lowered) else ""
        return how_to(thing, root, names, spec, role_hint)
    server_is_object = thing in (None, "server")  # else the server words below are only the place

    # ---- names that no longer exist (removed earlier in the chat, or on another page): say so, don't act on them
    gone = _gone_names(lowered, history, names, keys)
    if gone and not _DO.search(lowered.replace(gone, "")):
        what = "saved server" if gone in _seen(history, "server") else "on-prem service"
        current = names if what == "saved server" else keys
        listing_text = ", ".join(f"**{n}**" for n in current) if current else "none"
        return {"reply": f"**{gone}** isn't a {what} anymore (it was removed). Current {what}s: {listing_text}.",
                "card": None, "direct": True}

    # ---- lists, from the real state
    if listing and about_server and not about_service and not named:
        return {"reply": _server_list(servers), "card": None, "direct": True, "first": True}
    if listing and about_service and not named_key:
        return {"reply": _service_list(services), "card": None, "direct": True, "first": True}

    # ---- the project's functions / workflows / resources, listed from pskit.yml
    asks_create = bool(re.search(r"\b(crea\w*|creat\w*|cerate|add|make|new|build|set ?up|want|need)\b", lowered))
    if _LIST_ITEMS.search(lowered) and not remove and not asks_create:
        for kind in ("function", "workflow", "resource"):
            if _ITEM_WORDS[kind].search(lowered) and not (kind == "function" and _ITEM_WORDS["workflow"].search(lowered)):
                listed = items_list(root, kind)
                if listed:
                    return {"reply": listed, "card": None, "direct": True, "first": True}

    # ---- existing functions into their own apps ("make step01 and step02 separate apps", "remove app/steps and
    # create a different app for each function"); new names are a create (below), with that placement
    if not howto and _SEPARATE.search(lowered):
        from .edits import names as item_names
        from .edits import raw_config

        raw = raw_config(root)
        if raw and not [n for n in _new_function_names(text, item_names(raw, "function") + item_names(raw, "workflow"))
                        if n not in _NOT_FUNCTION_NAMES]:
            moved = _separate_intent(text, lowered, root)
            if moved is not None:
                return moved

    # ---- a workflow: the project's functions run one after the other
    workflow_word =re.search(r"\bwork\s*flows?\b|\bwrok\s*flows?\b|\bstate machines?\b|\bpipelines?\b", lowered)
    if workflow_word and not remove:
        found = _workflow_intent(text, lowered, root, asks_create, howto)
        if found is not None:
            return found

    # ---- new functions: pskit.yml entry AND handler code, never one without the other
    if asks_create and not howto and not remove and _ITEM_WORDS["function"].search(lowered):
        made = _functions_intent(text, lowered, root)
        if made is not None:
            return made

    # ---- handler code that is missing ("just add boilerplate code", "write the code for step02")
    if not remove and re.search(r"\b(code|boiler\w*|boilder\w*|boil\w*plate|stubs?|implement\w*|handlers?)\b", lowered) \
            and re.search(r"\b(write|add|create|generate|make|give|put|missing|what about|where is|need)\b", lowered):
        code = _code_intent(lowered, root)
        if code is not None:
            return code

    # ---- resources in pskit.yml (queues, buckets, topics, databases, caches): one card each
    if asks_create and not howto and not remove and not _services(text, catalog) and not about_server \
            and not _CLUSTER_WORD.search(lowered) and not _LB_WORD.search(lowered):
        res = _resources_intent(text, lowered, root, provider)
        if res is not None:
            return res

    # ---- "create a service": a function here, an on-prem service (Redis ...), or a new project?
    if asks_create and not howto and re.search(r"\bservices?\b", lowered) and not _services(text, catalog) \
            and not about_server and not _CLUSTER_WORD.search(lowered) and not _LB_WORD.search(lowered):
        return {"reply": "Which one do you mean?\n\n"
                         "1. **A function in this service** (pskit calls the whole project a service): say for example "
                         "\"add a GET /orders endpoint\" or \"add a function that runs every hour\".\n"
                         "2. **An on-prem service** (a database, cache or queue in Docker): say for example \"create "
                         "redis on server-1\" or \"create a postgres database\".\n"
                         "3. **A new project**: open studio in an empty folder (**New project**), or run "
                         "`pskit init my-api -p onprem`.", "card": None, "direct": True}

    # ---- clusters, load balancers, algorithms, deploy (studio pages; never invented pskit.yml keys)
    infra = _infra(text, lowered, root, servers, provider, stage, bool(_DO.search(lowered)) or "for me" in lowered,
                   bool(_LIST.search(lowered)), howto, remove)
    if infra is not None:
        return infra

    # ---- functions, workflows and resources in pskit.yml: remove completely (entry + handler code)
    item = _project_item(text, lowered, root) if remove else None
    if item is not None:
        return item

    # ---- remove (one card per server / service named; "all" = every one)
    every = bool(re.search(r"\b(all|every|each)\b", lowered))
    if remove and (named_key or (every and about_service and keys)):
        targets = [k for k in keys if _mentions(k, lowered)] or (keys if every else [])
        cards: List[Dict[str, Any]] = []
        for key in targets:
            entry = next(s for s in services if s.get("key") == key)
            cards.append({"kind": "service-remove", "key": key, "service": entry.get("service"),
                          "where": entry.get("target_label") or ""})
        what = f"**{targets[0]}**" if len(targets) == 1 else f"these {len(targets)} services ({', '.join(targets)})"
        return _many(f"Remove the on-prem service{'s' if len(targets) > 1 else ''} {what}? Each card stops and "
                     "deletes its container; data is kept unless you tick the box. Confirm each below.", cards)
    kinds_named = _services(text, catalog)
    if remove and thing == "service" and kinds_named and not named_key:
        # "remove redis from app-1": the Redis services (on that server), never the server itself
        on = next((n for n in names if _mentions(n, lowered)), None)
        hits = [s for s in services if s.get("service") in kinds_named and (
            on is None or (s.get("target") or {}).get("server") == on or on in str(s.get("target_label") or ""))]
        label = " / ".join(kinds_named)
        if not hits:
            listed = ", ".join(f"**{s.get('key')}** ({s.get('service')})" for s in services) or "none"
            return {"reply": f"There is no {label} service" + (f" on **{on}**" if on else "") + f" to remove. "
                             f"On-prem services: {listed}.", "card": None, "direct": True}
        cards = [{"kind": "service-remove", "key": s.get("key"), "service": s.get("service"),
                  "where": s.get("target_label") or ""} for s in hits]
        return _many(f"Remove {'these' if len(cards) > 1 else 'this'} {label} service{'s' if len(cards) > 1 else ''}"
                     + (f" on **{on}**" if on else "") + ": " + ", ".join(f"**{c['key']}**" for c in cards)
                     + "? The server itself stays. Each card stops and deletes its container; data is kept unless you "
                       "tick the box.", cards)
    if remove and about_server and names and server_is_object:
        targets = [n for n in names if _mentions(n, lowered)] or (names if every else [])
        if len(targets) > 1:
            cards = [{"kind": "server-remove", "name": n, "label": next(s for s in servers if s["name"] == n).get("label")}
                     for n in targets]
            return _many(f"Remove these {len(targets)} saved servers ({', '.join(targets)})? Studio only forgets them "
                         "here; nothing on the machines is touched. Each card has its own **Remove** button.", cards)
    if remove and about_server and server_is_object:
        target = named or (_recent_server(history, names) if _THIS.search(lowered) else None)
        if not target and len(names) == 1:
            target = names[0]
        if not target:
            if not names:
                return {"reply": "There are no saved servers in this project, so there is nothing to remove.",
                        "card": None, "direct": True}
            return {"reply": "Which server should I remove? Saved servers: "
                             + ", ".join(f"**{n}**" for n in names) + ". Say for example \"remove " + names[0] + "\".",
                    "card": None, "direct": True, "followup": {"prefix": "remove server", "names": names}}
        entry = next(s for s in servers if s["name"] == target)
        card = {"kind": "server-remove", "name": target, "label": entry.get("label") or entry.get("host")}
        return {"reply": f"Remove the saved server **{target}** ({card['label']})? Studio only forgets it here: nothing "
                         "on the machine is touched, and it refuses while a cluster still uses the server. Confirm "
                         "below.", "card": card, "direct": True}

    # ---- several servers in one message: one card each, in the same order
    blocks = server_blocks(text) if not remove and not listing else []
    if blocks:
        cards = []
        lines: List[str] = []
        taken = list(names)
        for block in blocks:
            d = block["details"]
            existing = next((s for s in servers if s.get("host") == d["host"]), None)
            if existing is not None:
                cards.append(_server_card(existing, d, block["folders"], names, mode="edit"))
                lines.append(f"- **{existing['name']}** ({d['host']}) is already saved: its card updates it")
                continue
            wanted = block["name"]
            name = wanted if wanted and wanted not in taken else _next_name(taken)
            taken.append(name)
            card = _server_card({}, d, block["folders"], taken, name=name)
            missing = [label for key, label in (("user", "the SSH user"), ("identity_file", "the .pem key file"))
                       if not card.get(key)]
            cards.append(card)
            lines.append(f"- **{name}**: {card['user']}@{card['host']}:{card['port']}"
                         + (f" (still needs {' and '.join(missing)})" if missing else ""))
        reply = (f"I found **{len(cards)} servers** in your message and made one card for each, in the same order. "
                 "Check each card and click its **Save & test** (studio saves it and tests the SSH login):\n\n"
                 + "\n".join(lines))
        common = [f"{label} `{cards[0][key]}`" for key, label in
                  (("home", "home folder"), ("data_dir", "data folder"), ("bind", "listen address"))
                  if cards[0].get(key) and all(c.get(key) == cards[0][key] for c in cards)]
        if cards[0].get("sudo") and all(c.get("sudo") for c in cards):
            common.append("sudo on")
        if common:
            reply += "\n\nOn every server: " + ", ".join(common) + "."
        return _many(reply, cards)

    # ---- change a saved server (home / data folder, user, key, port, address)
    details = {**server_details(text), **server_options(text)}
    fields = [f for f, pattern in _FIELDS.items() if re.search(pattern, lowered)]
    this = bool(_THIS.search(lowered))
    if (about_server or this) and not howto and server_is_object:
        by_host = next((s for s in servers if details.get("host") and s.get("host") == details["host"]), None)
        target = named or (str(by_host["name"]) if by_host else None) or (_recent_server(history, names) if this else None)
        asks_change = bool(_EDIT.search(lowered)) and bool(fields) and (named is not None or this)
        if target is None and asks_change:
            previous = _recent_card(history)  # "this server" = the card above, not saved yet: add it with the folders
            if previous is not None:
                card = _server_card({}, {**previous, **details}, _folders(text), names, name=str(previous["name"]),
                                    focus=fields)
                return {"reply": f"**{card['name']}** isn't saved yet, so I put everything in one card; the fields you "
                                 "asked for are highlighted. " + _missing_text(card, fields)
                                 + "Then click **Save & test**.",
                        "card": card, "direct": True}
        if target and (asks_change or (by_host is not None and not named)):
            entry = next(s for s in servers if s["name"] == target)
            card = _server_card(entry, details, _folders(text), names, mode="edit", focus=fields)
            missing = [label for f, label in _FIELD_LABELS.items() if f in fields and not card.get(f)]
            reply = f"Here is **{target}**: change what you need and click **Save & test**."
            if by_host is not None and not named:
                reply = f"This machine is already saved as **{target}**. Update it below if something changed."
            if missing or (card["auth"] == "password" and not card["has_password"]):
                folders = "Folders are paths on the server, e.g. `/opt/pskit`." if {"home", "data_dir"} & set(fields) else ""
                reply = " ".join(p for p in (f"Here is **{target}** with the fields you asked for highlighted.",
                                             _missing_text(card, fields).strip(), folders,
                                             "Then click **Save & test**.") if p)
            return {"reply": reply, "card": card, "direct": True}

    wants = bool(_DO.search(lowered)) or "for me" in lowered
    # ---- create an on-prem service
    requests = _service_requests(text, lowered, catalog, names) if wants and not howto and not remove else []
    if requests:  # a named service is created directly, for any provider (it runs in Docker here or on a server)
        from ...core import onprem_cluster

        try:
            cluster_names = [str(c["name"]) for c in onprem_cluster.list_clusters(root)]
        except Exception:  # noqa: BLE001
            cluster_names = []
        on_cluster = next((c for c in cluster_names if _mentions(c, lowered)), "")
        mentioned = [n for n in names if _mentions(n, lowered)]
        # one server named in the message ("redis and postgres on app-1") is where every service goes
        default = mentioned[0] if len(mentioned) == 1 else ""
        default = default or _recent_server(history, names) or (names[0] if len(names) == 1 else "")
        role_words = {"cache": "cache", "queue": "queue", "database": "database", "db": "database",
                      "storage": "storage", "stream": "stream", "secrets": "secrets"}
        key_match = _KEY_NAME.search(text)  # "as cache" is a role, not a name: only "named x" / "called x"
        taken_keys = list(keys)
        cards = []
        plan = ["Here is what I understood:", ""]
        total = sum(c for _s, c, _srv in requests)
        for service, count, server in requests:
            spec = next(c for c in catalog if c["id"] == service)
            role = next((r for w, r in role_words.items() if re.search(rf"\b{w}\b", lowered) and r in spec["roles"]),
                        "cache" if "cache" in spec["roles"] else spec["roles"][0])
            base = service.split("-")[0]
            where = server or default
            for _i in range(count):
                key = key_match.group("name") if key_match and total == 1 else ""
                wanted_key = key
                if not key or key in taken_keys:
                    n = 1
                    while f"{base}-{n}" in taken_keys:
                        n += 1
                    key = f"{base}-{n}"
                taken_keys.append(key)
                in_cluster = on_cluster if on_cluster and not server else ""
                svc_card: Dict[str, Any] = {"kind": "service", "service": service, "role": role, "key": key,
                                        "server": "" if in_cluster else where, "servers": names, "cluster": in_cluster}
                if wanted_key and wanted_key != key:  # the name asked for is taken: say so, never replace a service
                    was = next((s for s in services if s.get("key") == wanted_key), {})
                    svc_card["conflict"] = (f"{wanted_key} is already an on-prem service ({was.get('service') or '?'} "
                                            f"on {was.get('target_label') or 'this machine'}), so this card uses {key}. "
                                            f"To replace it, remove {wanted_key} first (\"remove {wanted_key}\"), then "
                                            "create it again; to change it, use Resources > On-prem services.")
                    plan.append(f"(**{wanted_key}** is already an on-prem service, so I named this one **{key}**: "
                                f"rename it on the card, or say \"remove {wanted_key}\" first to replace it.)")
                # a database asked to scale: primary + read replicas on the servers named (the first is the primary)
                if role == "database" and spec.get("replication") and re.search(
                        r"\b(replica\w*|replicat\w*|scal\w*|high availability|ha|read replicas?)\b", lowered):
                    members = list(mentioned) or ([where] if where else [])
                    members += [n for n in names if n not in members]
                    svc_card.update({"scaling": "replicated", "primary": members[0] if members else "",
                                 "replicas": members[1:2] if len(mentioned) < 2 else mentioned[1:],
                                 "sync": "sync" if re.search(r"\bsync(hronous)?\b", lowered) and "async"
                                 not in lowered else "async"})
                cards.append(svc_card)
                if svc_card.get("scaling") == "replicated":
                    plan.append(f"{len(cards)}. **{spec['label']}** as **{key}**, scaled: primary **{svc_card['primary']}**, "
                                f"read replica(s) {', '.join(f'**{r}**' for r in svc_card['replicas']) or '(pick on the card)'}"
                                f", {svc_card['sync']} replication"
                                + (f", load balancer {spec['replication']['balancer']}" if spec["replication"].get(
                                    "balancer") else ""))
                else:
                    plan.append(f"{len(cards)}. **{spec['label']}** as **{key}** ({role}), on "
                                + (f"the scaling cluster **{in_cluster}** (its server with the most free memory)"
                                   if in_cluster else f"**{where}**" if where
                                   else "this machine (or pick a server or cluster on the card)")
                                + (". For a database you can also pick **Scaling: primary + read replicas** on the card"
                                   if role == "database" and spec.get("replication") else ""))
        plan += ["", "One card each: check it and click its **Create** (studio starts it with Docker and shows the log)."]
        if provider and provider not in ("onprem", "none"):
            plan.append(f"These run in Docker on this machine or a saved server. For a managed {provider} resource in "
                        "pskit.yml instead, say for example \"add a database resource\".")
        return _many("\n".join(plan), cards)
    # ---- add a server
    if (about_server and server_is_object) or "ssh" in lowered or ".pem" in lowered:
        if howto and not details.get("host"):
            reply = ("To add a server in studio: **Overview & provider** (on-premises) or **Scaling cluster** > "
                     "**Servers** > **+ Add server**, then enter its address, SSH user and key file and click "
                     "**Test**. I can also do it for you: fill in the card below.")
            return {"reply": reply, "card": _server_card({}, details, _folders(text), names), "direct": True}
        cloud = re.search(r"\b(aws|azure|gcp|google cloud|ec2|vm|virtual machine)\b", lowered)
        if wants and cloud and not details.get("host"):
            reply = ("pskit doesn't create virtual machines in a cloud: create the VM in the cloud (console, CLI or "
                     "Terraform), then paste its public IP, SSH user and `.pem` path (or the Terraform outputs) and I "
                     "add it here. The card below is ready for those details.")
            return {"reply": reply, "card": _server_card({}, details, _folders(text), names), "direct": True}
        if (wants or details.get("host")) and not listing:
            card = _server_card({}, details, _folders(text), names, name=_name_in(text, names))
            missing = [label for key, label in (("host", "the IP or host name"), ("user", "the SSH user"),
                                                ("identity_file", "the .pem key file")) if not card.get(key)]
            reply = "I can add this server to studio. "
            reply += (f"I still need {', '.join(missing)}: fill it in below, then click **Save & test**."
                      if missing else "Check the details and click **Save & test**: studio saves it and logs in "
                                      "once over SSH to check it.")
            return {"reply": reply, "card": card, "direct": True}

    return None


_ITEM_WORDS = {
    "function": re.compile(r"\b(fun[ct]\w*|fucntions?|fns?|handlers?|endpoints?|routes?|lambdas?)\b", re.I),
    "workflow": re.compile(r"\b(workflows?|step ?functions?|state machines?)\b", re.I),
    "resource": re.compile(r"\b(reso\w*|resou\w*|resorces?|buckets?|tables?|queues?|topics?)\b", re.I),
}


def _seen(history: List[Dict[str, Any]], kind: str) -> List[str]:
    """Names the chat has shown cards for: saved servers (``server``) or services (``service``)."""
    out = []
    for item in history:
        card = item.get("card") if item.get("role") == "action" else None
        if isinstance(card, dict):
            if kind == "server" and card.get("kind") in ("server", "server-remove"):
                out.append(str(card.get("name")))
            if kind == "service" and card.get("kind") in ("service", "service-remove"):
                out.append(str(card.get("key")))
        text = str(item.get("text") or "")
        if kind == "server":
            out += re.findall(r"(?:server|Saved server|Updated server) \*\*([\w.-]+)\*\*", text)
        else:
            out += re.findall(r"on-prem service \*\*([\w.-]+)\*\*", text)
    return out


def _gone_names(lowered: str, history: List[Dict[str, Any]], names: List[str], keys: List[str]) -> Optional[str]:
    """A server / service the chat knew that no longer exists, named in this message."""
    for kind, current in (("server", names), ("service", keys)):
        for name in dict.fromkeys(_seen(history, kind)):
            if name and name not in current and _mentions(name, lowered):
                return name
    return None


def _project_item(text: str, lowered: str, root: Path) -> Optional[Dict[str, Any]]:
    """"remove the hello function" -> a remove card with everything that goes (pskit.yml entry + handler code)."""
    from .edits import names as item_names
    from .edits import plan_removal, raw_config

    raw = raw_config(root)
    if not raw:
        return None
    hits = []
    for kind in ("function", "workflow", "resource"):
        for name in item_names(raw, kind):
            if _mentions(name, lowered):
                hits.append((kind, name))
    typed = [k for k, rx in _ITEM_WORDS.items() if rx.search(lowered)]
    if typed:
        hits = [h for h in hits if h[0] in typed] or hits
    if typed and re.search(r"\b(all|every)\b", lowered) and len(hits) <= 1:  # "remove all functions"
        hits = [(typed[0], n) for n in item_names(raw, typed[0])]
    if not hits:
        if not typed:
            return None
        kind = typed[0]
        existing = item_names(raw, kind)
        word = re.search(r"\b(?:function|funtion|fn|handler|workflow|resource)\s+[\"'`]?([A-Za-z][\w-]*)", text, re.I)
        missing = f" **{word.group(1)}**" if word and word.group(1).lower() not in ("the", "a", "this", "that") else ""
        listed = ", ".join(f"**{n}**" for n in existing) if existing else "none"
        if missing:
            return {"reply": f"There is no {kind}{missing} in pskit.yml (it may be removed already). "
                             f"{kind.capitalize()}s: {listed}.", "card": None, "direct": True}
        if len(existing) == 1:
            hits = [(kind, existing[0])]
        else:  # the answer ("step01, step02") is read as "remove <kind> step01, step02"
            return {"reply": f"Which {kind} should I remove? {kind.capitalize()}s in pskit.yml: {listed}.",
                    "card": None, "direct": True, "followup": {"prefix": f"remove {kind}", "names": existing}}
    cards: List[Dict[str, Any]] = []
    lines: List[str] = []
    for kind, name in hits:
        plan = plan_removal(root, kind, name)
        if plan["blocked"]:
            lines.append(f"- **{name}**: not removed, {plan['blocked']}")
            continue
        parts = [f"`{plan['yml']}` from pskit.yml"]
        code = plan.get("code") or {}
        if code.get("action") == "delete-file":
            parts.append(f"the file `{code['file']}`")
        elif code.get("action") == "delete-function":
            parts.append(f"`{code['handler'].rsplit('.', 1)[1]}()` from `{code['file']}`")
        elif code.get("action") == "keep":
            parts.append(f"(the code in `{code['file']}` stays: {code['why']})")
        line = f"- the {kind} **{name}**: " + " and ".join(parts)
        if plan["warnings"]:
            line += " (note: " + "; ".join(plan["warnings"]) + ")"
        lines.append(line)
        cards.append({**{k: v for k, v in plan.items() if k != "kind"}, "kind": "item-remove", "item_kind": kind})
    if not cards:
        return {"reply": "I can't remove that yet:\n\n" + "\n".join(lines), "card": None, "direct": True}
    head = ("Removing it takes out (pskit.yml is backed up first):" if len(hits) == 1
            else f"One card per item, {len(cards)} to confirm (pskit.yml is backed up first):")
    return _many(head + "\n\n" + "\n".join(lines) + "\n\nConfirm below.", cards)


_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                 "ten": 10, "a": 1, "an": 1, "single": 1}
_SPELLED = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
_ORCHESTRATOR_WORDS = {"swarm": "swarm", "kubernetes": "kubernetes", "k3s": "kubernetes", "k8s": "kubernetes",
                       "nomad": "nomad"}
_CLUSTER_WORD = re.compile(r"\bclusters?\b", re.I)
# "load balancer", typos ("load balncer"), "lb", nginx, and a bare "create load" at the end of a message
_LB_WORD = re.compile(r"\bload[ -]?bal\w*|\blbs?\b|\bnginx\b|\bload\s*[?.!]*\s*$", re.I)
_ALGO_Q = re.compile(r"\b(algo\w*|algorithms?|strateg\w*)\b", re.I)
_DEPLOY = re.compile(r"\b(deploy\w*|go live|publish|ship it)\b", re.I)


def spelled(n: int) -> str:
    return _SPELLED[n] if 0 <= n < len(_SPELLED) else str(n)


def _cluster_sizes(lowered: str) -> List[int]:
    """"a cluster with 2 servers and another cluster with 1 server" -> [2, 1] (in order)."""
    sizes = []
    for m in re.finditer(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an|single)\s+"
                         r"(?:more\s+)?(?:servers?|nodes?|machines?|vms?)\b", lowered):
        word = m.group(1)
        sizes.append(int(word) if word.isdigit() else _NUMBER_WORDS[word])
    return [s for s in sizes if 0 < s <= 20]


def _infra(text: str, lowered: str, root: Path, servers: List[Dict[str, Any]], provider: str, stage: str,
           wants: bool, listing: bool, howto: bool, remove: bool) -> Optional[Dict[str, Any]]:
    """Clusters, load balancers, their algorithms and deploying: studio's own pages, never invented config."""
    from ...core import onprem_balancers, onprem_cluster, onprem_lb

    names = [str(s["name"]) for s in servers]
    try:
        clusters = onprem_cluster.list_clusters(root)
    except Exception:  # noqa: BLE001
        clusters = []
    try:
        balancers = onprem_balancers.list_balancers(root)
    except Exception:  # noqa: BLE001
        balancers = []
    algorithms = onprem_lb.catalog()

    if _ALGO_Q.search(lowered) and (_LB_WORD.search(lowered) or listing or "?" in text):
        lines = [f"- **{a['label']}** (`{a['name']}`): {a['summary']} Best for: {a['best_for']}" for a in algorithms]
        return {"reply": "Load balancer algorithms you can pick (Load balancers page > the balancer > Algorithm, or "
                         f"`--algorithm` on the command line); the default is `{onprem_lb.DEFAULT_ALGORITHM}`:\n\n"
                         + "\n".join(lines), "card": None, "direct": True}
    if listing and _CLUSTER_WORD.search(lowered) and not wants:
        if not clusters:
            return {"reply": "There are no scaling clusters yet. Ask me, for example \"create a cluster with 2 servers\".",
                    "card": None, "direct": True}
        lines = [f"- **{c['name']}** ({c.get('orchestrator')}): " + ", ".join(n.get("server", "?") for n in c.get("nodes") or [])
                 for c in clusters]
        return {"reply": f"**{len(clusters)}** ({spelled(len(clusters))}) scaling cluster{'s' if len(clusters) != 1 else ''}:\n\n"
                         + "\n".join(lines) + "\n\nDetails: the **Scaling cluster** page.", "card": None, "direct": True,
                "first": True}
    if listing and _LB_WORD.search(lowered) and not wants:
        if not balancers:
            return {"reply": "There are no load balancers yet. Ask me, for example \"create a load balancer on app-1 "
                             "for cluster-1\".", "card": None, "direct": True}
        lines = [f"- **{b['name']}** on {b.get('server')}:{b.get('port')} ({b.get('algorithm')})" for b in balancers]
        return {"reply": f"**{len(balancers)}** ({spelled(len(balancers))}) load balancer{'s' if len(balancers) != 1 else ''}:"
                         "\n\n" + "\n".join(lines) + "\n\nDetails: the **Load balancers** page.", "card": None, "direct": True,
                "first": True}

    if _DEPLOY.search(lowered) and not remove and not _CLUSTER_WORD.search(lowered) and not _LB_WORD.search(lowered):
        p = provider if provider and provider != "none" else "<provider>"
        asked = re.search(r"\b(?:to|on|for|stage)\s+(prod\w*|staging|dev\w*|test\w*|qa|uat)\b|\b(prod\w*|staging)\b",
                          lowered)
        if asked:
            stage = asked.group(1) or asked.group(2)
        lines = ["I don't deploy myself: a deploy changes real servers or a cloud account, so studio does it after you "
                 "confirm.", "", "**In studio**", "1. Open **Deploy** (left menu).",
                 f"2. Check the provider (**{p}**) and stage (**{stage}**) in the top bar."]
        cmd = f"pskit deploy -p {p} -s {stage}"
        if p == "onprem":
            lines.append("3. In **Run on**, pick the **Machine** (a saved server or this machine) or a **Scaling "
                         "cluster**.")
            lines.append("4. Click **Deploy** and confirm.")
            extra = f" --server {names[0]}" if names else ""
            ccmd = f"\n{cmd} --cluster {clusters[0]['name']}" if clusters else ""
            lines += ["", "**In the terminal**", "```bash", f"pskit validate -p {p} -s {stage}", cmd + extra + ccmd,
                      "```", "`--server NAME` deploys to a saved server, `--cluster NAME` to a scaling cluster."]
        else:
            lines.append("3. Click **Deploy** and confirm.")
            lines += ["", "**In the terminal**", "```bash", f"pskit validate -p {p} -s {stage}", cmd, "```",
                      "Add `--confirm` to review the Terraform plan first."]
        lines.append("\nI can run `validate` for you first, or fix problems it finds.")
        asks_to_do = not howto and (wants or re.search(r"\b(deploy|ship|publish)\b(?!\w)", lowered)) and not \
            re.search(r"\b(how|what|why|where|explain)\b", lowered)
        if not asks_to_do:
            return {"reply": "\n".join(lines), "card": None, "direct": True}
        # "deploy the code to server-1": a card that runs studio's own deploy job after you confirm
        to_server = next((n for n in names if _mentions(n, lowered)), "")
        named_cluster = next((str(c["name"]) for c in clusters if _mentions(str(c["name"]), lowered)), "")
        last = ""
        if p == "onprem" and not (to_server or named_cluster):
            try:
                from ...core.onprem_control import deployed_host

                last = str((deployed_host(root, stage) or {}).get("server") or "")
            except Exception:  # noqa: BLE001
                last = ""
        deploy_card: Dict[str, Any] = {
            "kind": "deploy", "provider": p if p != "<provider>" else "", "stage": stage,
            "server": to_server or (last if last in names else "")
            or (names[0] if names and not named_cluster and p == "onprem" else ""),
            "cluster": named_cluster, "servers": names if p == "onprem" else [],
            "clusters": [str(c["name"]) for c in clusters] if p == "onprem" else []}
        where = (f" to the cluster **{named_cluster}**" if named_cluster else
                 f" to **{deploy_card['server']}**" if deploy_card["server"] else "")
        reply = (f"Here is the deploy of this project ({deploy_card['provider'] or 'pick the provider in the top bar'}, "
                 f"stage **{stage}**){where}. Check it and click **Deploy**: studio asks you to confirm"
                 + (", and for a production stage you type its name" if stage.startswith("prod") else "")
                 + ", then shows the log here. I don't start a deploy without your click.")
        return _many(reply, [deploy_card])

    if not (wants and not howto and not remove):
        return None
    in_clusters = {n.get("server") for c in clusters for n in c.get("nodes") or []}
    free = [n for n in names if n not in in_clusters]
    if _CLUSTER_WORD.search(lowered) and not _LB_WORD.search(lowered):
        orch = next((v for k, v in _ORCHESTRATOR_WORDS.items() if re.search(rf"\b{k}\b", lowered)), "swarm")
        named = [n for n in names if _mentions(n, lowered)]
        sizes = _cluster_sizes(lowered) or ([len(named)] if named else [min(2, len(free)) or 1])
        many = re.search(r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten)\s+(?:\w+\s+)?clusters\b", lowered)
        if many:  # "3 clusters with 1 server each" / "two clusters" -> the same size for each
            count = int(many.group(1)) if many.group(1).isdigit() else _NUMBER_WORDS[many.group(1)]
            if 1 < count <= 10 and len(sizes) == 1:
                sizes = sizes * count
        pool = named + [n for n in free if n not in named]
        cards, lines, taken = [], [], [str(c["name"]) for c in clusters]
        wanted = _wanted_name(text, names) if len(sizes) == 1 else ""
        short = 0
        for size in sizes:
            n = 1
            while f"cluster-{n}" in taken:
                n += 1
            name = wanted if wanted and wanted not in taken else f"cluster-{n}"
            taken.append(name)
            members, pool = pool[:size], pool[size:]
            short += size - len(members)
            cards.append({"kind": "cluster", "name": name, "orchestrator": orch, "master": members[0] if members else "",
                          "workers": members[1:], "size": size, "servers": names})
            if wanted and wanted != name:
                cards[-1]["conflict"] = (f"{wanted} is already a cluster, so this card uses {name}. To change "
                                         f"{wanted}, use the Scaling cluster page (+ Join server / remove a node).")
                lines.append(f"- (**{wanted}** already exists: I named the new one **{name}**; rename it on the card. "
                             f"To add servers to {wanted} instead, say \"add app-2 to {wanted}\".)")
            lines.append(f"- **{name}** ({size} server{'s' if size != 1 else ''}): "
                         + (", ".join(members) if members else "pick the servers on the card")
                         + (f" (master **{members[0]}**)" if members else ""))
        head = (f"One card per cluster, {len(cards)} in all ({orch}). The first server is the master; the others join it:"
                if len(cards) > 1 else f"Here is the cluster ({orch}); the first server is the master, the others join it:")
        tail = ""
        if short:
            tail = (f"\n\nYou need **{short}** more saved server{'s' if short != 1 else ''} than you have free. Paste "
                    "their IP, user and `.pem` (or the Terraform outputs) and I'll add them, then pick them on the card.")
        return _many(head + "\n\n" + "\n".join(lines) + tail + "\n\nCheck each card and click **Create**.", cards)
    if _LB_WORD.search(lowered):
        if not names:
            return {"reply": "A load balancer runs on one of your saved servers, and there are none yet. Paste a "
                             "server's IP, user and `.pem` path and I'll add it first.", "card": None, "direct": True}
        named = [n for n in names if _mentions(n, lowered)]
        attach = [str(c["name"]) for c in clusters if _mentions(str(c["name"]), lowered)] or (
            [str(clusters[0]["name"])] if len(clusters) == 1 else [])
        algo = next((a["name"] for a in algorithms if a["name"].replace("_", " ") in lowered or a["name"] in lowered),
                    onprem_lb.DEFAULT_ALGORITHM)
        taken = [str(b["name"]) for b in balancers]
        port = re.search(r"\bport\s*(\d{2,5})\b", lowered)
        many = re.search(r"\b(\d+|two|three|four|five|six)\s+(?:\w+\s+)?(?:load[ -]?bal\w*|lbs)\b", lowered)
        count = (int(many.group(1)) if many.group(1).isdigit() else _NUMBER_WORDS[many.group(1)]) if many else 1
        # one per server named ("on app-1 and app-2"), else N on different servers (named first, then the rest)
        hosts = named if len(named) > 1 else (named + [n for n in names if n not in named])[:max(count, 1)]
        if len(hosts) < count:
            hosts += [names[0]] * (count - len(hosts))
        cards = []
        lines = ["Here is what I understood:", ""]
        chosen = hosts[:max(count, len(named) if len(named) > 1 else 1)]
        wanted = _wanted_name(text, names + [str(c["name"]) for c in clusters]) if len(chosen) == 1 else ""
        for server in chosen:
            n = 1
            while f"lb-{n}" in taken:
                n += 1
            name = wanted if wanted and wanted not in taken else f"lb-{n}"
            taken.append(name)
            cards.append({"kind": "balancer", "name": name, "server": server,
                          "port": int(port.group(1)) if port else 80, "algorithm": algo, "clusters": attach,
                          "cluster_names": [str(c["name"]) for c in clusters], "servers": names,
                          "algorithms": [{"name": a["name"], "label": a["label"], "summary": a["summary"]}
                                         for a in algorithms]})
            lines.append(f"{len(cards)}. **{name}** on **{server}**, port {cards[-1]['port']}, algorithm `{algo}`"
                         + (f", for cluster **{', '.join(attach)}**" if attach else ", no cluster attached yet"))
            if wanted and wanted != name:
                cards[-1]["conflict"] = (f"{wanted} is already a load balancer, so this card uses {name}. To change "
                                         f"{wanted} (algorithm, clusters, port), use the Load balancers page or "
                                         f"`pskit lb update {wanted}`.")
                lines.append(f"   (**{wanted}** already exists: rename this one on the card, or change {wanted} on "
                             "the **Load balancers** page.)")
        lines += ["", "A load balancer is nginx on a server that spreads requests over a cluster's servers. One card "
                  "each: check it and click its **Create**.", "",
                  f"To send this project's requests through one, set `provider.options.balancer: {cards[0]['name']}` "
                  "in pskit.yml (I can do that with a plan); `pskit deploy` then adds the route "
                  "`http://<load balancer>/<service>/`."]
        return _many("\n".join(lines), cards)
    return None


_HEADING = re.compile(r"^\s*[#*>\-\s]*([A-Za-z][\w.-]{0,62})\s*:?\s*\**\s*$")
_NOT_NAMES = {"add", "create", "servers", "server", "these", "this", "them", "ok", "thanks", "hi", "hello", "please"}


def server_blocks(text: str) -> List[Dict[str, Any]]:
    """Several servers in one message -> ``[{"name": heading or "", "details": {...}}]`` in order.

    Splits on a name line (``AZ_VM_01_4cpu`` above its Terraform outputs), else on a repeated first key
    (``app_url = ...`` again), else one block per ``ssh user@host`` command. Fewer than two hosts -> ``[]``."""
    lines = text.replace("\r\n", "\n").split("\n")
    titles: Dict[int, str] = {}
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if m and m.group(1).lower() not in _NOT_NAMES and "=" not in line:
            titles[i] = m.group(1)
    chunks: List[Any] = []
    if titles:
        bounds = list(titles) + [len(lines)]
        chunks = [(titles[a], "\n".join(lines[a + 1:b])) for a, b in zip(bounds, bounds[1:])]
    if sum(1 for _n, body in chunks if server_details(body).get("host")) < 2:
        keys = re.findall(r"^\s*([A-Za-z_][\w]*)\s*=", text, re.M)
        first = keys[0] if keys else ""
        if first and keys.count(first) >= 2:
            starts = [i for i, line in enumerate(lines) if re.match(rf"^\s*{re.escape(first)}\s*=", line)] + [len(lines)]
            chunks = [("", "\n".join(lines[a:b])) for a, b in zip(starts, starts[1:])]
        else:
            commands = [m.group(0) for m in _SSH_CMD.finditer(text)]
            chunks = [("", c) for c in commands] if len(commands) >= 2 else []
    # A block is only its data lines (key = value, ssh commands). Everything else in the message is an instruction
    # for every server ("add home path ... in all servers", "listen on 0.0.0.0"), even when it is written after
    # the last block, so it is read once and given to every card.
    data_lines = set()
    for i, line in enumerate(lines):
        if re.match(r"^\s*[A-Za-z_][\w]*\s*=", line) or _SSH_CMD.search(line) or i in titles:
            data_lines.add(i)
    shared_text = "\n".join(line for i, line in enumerate(lines) if i not in data_lines)
    shared_options = {k: v for k, v in server_options(shared_text).items() if k in ("sudo", "bind", "auth", "port")}
    shared_folders = _folders(shared_text)
    out = []
    seen_hosts = set()
    for name, body in chunks:
        own = "\n".join(line for line in body.split("\n")
                        if re.match(r"^\s*[A-Za-z_][\w]*\s*=", line) or _SSH_CMD.search(line))
        details = {**shared_options, **server_details(own), **server_options(own)}
        host = details.get("host")
        if host and host not in seen_hosts:
            seen_hosts.add(host)
            out.append({"name": name, "details": details, "folders": {**shared_folders, **_folders(own)}})
    return out if len(out) >= 2 else []


def _many(reply: str, cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"reply": reply, "card": cards[0] if cards else None, "cards": cards, "direct": True}


def match_server(text: str, names: List[str]) -> str:
    """The saved server a message names: exactly ("AZ_VM_01_2cpu"), else by a distinctive part of its name
    ("VM_01_2cpu", "01_2cpu") when only one server has it. "" when none."""
    low = text.lower()
    exact = [n for n in names if _mentions(n, low)]
    if exact:
        return exact[0]
    for token in re.findall(r"[a-z0-9][\w.-]{2,}", low):
        if not re.search(r"[\d_-]", token):  # "server", "docker": not a name
            continue
        hits = [n for n in names if token in n.lower()]
        if len(hits) == 1:
            return hits[0]
    return ""


# the start of a shell command: a program studio users run (a command in backticks is taken whatever it is)
_PROGRAMS = ("pskit", "docker", "git", "ls", "cat", "df", "du", "free", "uname", "systemctl", "journalctl", "kubectl",
             "k3s", "nomad", "pip", "pip3", "python", "python3", "npm", "node", "curl", "wget", "uptime", "ps", "tail",
             "head", "whoami", "hostname", "ip", "ss", "netstat", "nginx", "sudo", "apt", "apt-get", "dnf", "yum",
             "lsblk", "top", "env", "echo", "pwd", "terraform", "tofu", "redis-cli", "psql", "mysql", "dir", "type")
_RUN_VERB = re.compile(r"\b(?:run|execute|exec)\s+(?:the\s+)?(?:command\s+)?", re.I)
_RUN_IT = re.compile(r"^\s*(?:ok\s*,?\s*)?(?:(?:can|could|will)\s+(?:you|u)\s+|(?:please|pls|plz)\s+)?(?:run|execute|exec|do)"
                     r"\s+(?:it|this|that|the command|this command|that command|them)\b", re.I)
_ON_SERVER = re.compile(r"\s+(?:on|in|at)\s+(?:the\s+)?(?:server\s+|vm\s+|machine\s+)?([\w.-]+)\s*[.?!]*\s*$", re.I)


def _last_command(history: List[Dict[str, Any]]) -> str:
    """The first command in a code block of Hana's previous answer ("can u execute it")."""
    users = 0
    for item in reversed(history):
        if item.get("role") == "user":
            users += 1
            if users > 1:
                break
            continue
        if item.get("role") == "assistant":
            block = re.search(r"```(?:bash|sh|shell|console)?\s*\n(.*?)```", str(item.get("text") or ""), re.S)
            if block:
                line = next((ln.strip().lstrip("$").strip() for ln in block.group(1).splitlines()
                             if ln.strip() and not ln.strip().startswith("#")), "")
                if line and not re.search(r"<[^>]+>|\.\.\.", line):
                    return line
    return ""


def _terminal_intent(text: str, lowered: str, names: List[str], runtimes: List[str],
                     history: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Requests studio answers with a command (``run_command``: the user clicks Run, then the model answers from the
    output): install a runtime on a server, an explicit command, or "execute it" (the command of the last answer)."""
    server = match_server(text, names)
    # "access the VM_01_2cpu and install docker to it"
    runtime = next((r for r in runtimes if re.search(rf"(?<![\w-]){re.escape(r)}(?![\w-])", lowered)), "")
    if runtime and re.search(r"\b(install|instal|set ?up|setup|add|put|enable)\b", lowered):
        if not server:
            if len(names) != 1:
                listed = ", ".join(f"**{n}**" for n in names) or "none yet (add one first: paste its IP, user and .pem)"
                return {"reply": f"On which server should I install **{runtime}**? Saved servers: {listed}.",
                        "card": None, "direct": True, "first": True,
                        "followup": {"prefix": f"install {runtime} on", "names": names}}
            server = names[0]
        command = f"pskit resources onprem create {runtime} --service {runtime} --server {server}"
        return {"reply": f"I'll install **{runtime}** on **{server}** with studio's installer (it logs in over SSH "
                         f"from this machine). Click **Run** to start it.", "run": {"command": command},
                "card": None, "direct": True}
    # "run `docker ps` on app-1", "execute pskit validate"
    command = ""
    ticks = re.search(r"`{1,3}(?:bash|sh)?\s*([^`\n]+?)\s*`{1,3}", text)
    if ticks and (_RUN_VERB.search(text) or re.search(r"\b(terminal|shell)\b", lowered)):
        command = ticks.group(1).strip()
    elif _RUN_VERB.search(text):
        rest = text[_RUN_VERB.search(text).end():].strip()  # type: ignore[union-attr]
        first = rest.split(" ", 1)[0].lower() if rest else ""
        if first in _PROGRAMS:
            command = rest
    if command:
        # where: "... on AZ_VM_01_2cpu" at the end of the command, or a server named after the backticks
        where = ""
        on = _ON_SERVER.search(command)
        if on and match_server(on.group(1), names):
            where = match_server(on.group(1), names)
            command = command[:on.start()].strip()
        elif ticks:
            where = match_server(text[ticks.end():], names)
        return {"reply": f"I'll run `{command}`" + (f" on **{where}**" if where else " in the project folder")
                         + ". Click **Run** to start it.",
                "run": {"command": command, **({"server": where} if where else {})}, "card": None, "direct": True}
    # "can u execute it": the command of the previous answer
    if _RUN_IT.search(lowered):
        last = _last_command(history)
        if last:
            return {"reply": f"I'll run the command from my last answer: `{last}`"
                             + (f" on **{server}**" if server else "") + ". Click **Run** to start it.",
                    "run": {"command": last, **({"server": server} if server else {})}, "card": None, "direct": True}
    return None


def _wanted_name(text: str, not_names: List[str]) -> str:
    """The name the user gave a new cluster / load balancer: "named prod-lb", "called web" ("" when none)."""
    m = _KEY_NAME.search(text)
    name = m.group("name").lower() if m else ""
    return name if name and name not in {n.lower() for n in not_names} else ""


def _name_in(text: str, names: List[str]) -> str:
    m = _SERVER_NAME.search(text)
    return m.group("name") if m and m.group("name") not in names else ""


def _server_card(entry: Dict[str, Any], details: Dict[str, Any], folders: Dict[str, str], names: List[str],
                 mode: str = "add", name: str = "", focus: Optional[List[str]] = None) -> Dict[str, Any]:
    merged = {**{k: v for k, v in entry.items() if v not in (None, "")}, **details, **folders}
    card: Dict[str, Any] = {
        "kind": "server",
        "mode": mode,
        "name": str(entry.get("name") or name or _next_name(names)),
        "host": str(merged.get("host") or ""),
        "user": str(merged.get("user") or _user_from_paths(folders) or ("ubuntu" if merged.get("host") else "")),
        "port": int(merged.get("port") or 22),
        "identity_file": str(merged.get("identity_file") or ""),
        "home": str(merged.get("home") or ""),
        "data_dir": str(merged.get("data_dir") or ""),
        "bind": str(merged.get("bind") or ""),
        "auth": str(merged.get("auth") or ("password" if merged.get("password_file") else "key")),
        "sudo": bool(merged.get("sudo")),
        "description": str(merged.get("description") or ""),
        "has_password": bool(entry.get("password_file")),
        "focus": list(focus or []),
    }
    return card


def _missing_text(card: Dict[str, Any], fields: List[str]) -> str:
    missing = [label for f, label in _FIELD_LABELS.items() if f in fields and not card.get(f)]
    out = f"Fill in {' and '.join(missing)}. " if missing else ""
    if card.get("auth") == "password" and not card.get("has_password"):
        out += "Type the SSH password in the card (not in the chat). "
    return out


def _server_list(servers: List[Dict[str, Any]]) -> str:
    if not servers:
        return ("There are no saved servers in this project yet. Paste a server's IP, SSH user and `.pem` path (or "
                "its `ssh` command) and I'll add it.")
    lines = [f"This project has **{len(servers)}** ({spelled(len(servers))}) saved server"
             f"{'s' if len(servers) != 1 else ''}:", ""]
    for s in servers:
        extra = [f"home `{s['home']}`" if s.get("home") else "", f"data `{s['data_dir']}`" if s.get("data_dir") else ""]
        extra_text = ", ".join(e for e in extra if e)
        lines.append(f"- **{s['name']}**: {s.get('label') or s.get('host')}" + (f" ({extra_text})" if extra_text else ""))
    lines += ["", "They are on the **Overview & provider** page (on-premises) under **Servers**."]
    return "\n".join(lines)


def _service_list(services: List[Dict[str, Any]]) -> str:
    if not services:
        return ("There are no on-prem services in this project yet. Ask me to create one, for example \"create redis "
                "on server-1 as cache\".")
    lines = [f"This project has **{len(services)}** ({spelled(len(services))}) on-prem service"
             f"{'s' if len(services) != 1 else ''}:", ""]
    for s in services:
        where = s.get("target_label") or "this machine"
        port = f":{s['port']}" if s.get("port") else ""
        lines.append(f"- **{s.get('key')}**: {s.get('service')} ({s.get('role') or s.get('kind')}) on {where}"
                     + (f", {s.get('address')}{port}" if s.get("address") else ""))
    lines += ["", "Details, logs and backups: **Resources** > **On-prem services**."]
    return "\n".join(lines)
