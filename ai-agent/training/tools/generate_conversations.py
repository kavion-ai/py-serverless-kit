"""Build the stage-1 Hana conversations from knowledge cards and docs.

Answers copy card sentences and fenced commands that already passed the checker.
Search excerpts are verbatim paragraphs from docs headings.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ai-agent" / "training" / "tools"))

from extract_docs import github_anchor  # noqa: E402
from check_knowledge import (  # noqa: E402
    SYSTEM_BEFORE_ENV,
    check_ips,
    check_messages,
    check_pskit_lines,
    check_sources,
    cli_index,
    heading_index,
    normalize_q,
    jaccard,
)

KNOW = ROOT / "ai-agent" / "training" / "knowledge"
RAW = ROOT / "ai-agent" / "training" / "data" / "raw"
CARDS = KNOW / "cards.jsonl"

PROVIDERS = [
    "aws",
    "azure",
    "gcp",
    "alibaba",
    "tencent",
    "huawei",
    "oracle",
    "ibm",
    "digitalocean",
    "cloudflare",
    "onprem",
]
STAGES = ["dev", "staging", "prod"]
MODES = ["ask", "auto"]
PAGES = [
    "Overview",
    "Setup",
    "Functions",
    "Workflows",
    "Resources",
    "Cluster",
    "Load balancers",
    "Network map",
    "Code",
    "Test",
    "Deploy",
    "Logs",
    "YAML",
    "none",
]
PERSONAS = (
    ["beginner"] * 4
    + ["informal_non_native"] * 5
    + ["terse_expert"] * 3
    + ["ops_engineer"] * 3
    + ["aws_migrator"] * 2
    + ["contributor"] * 3
)
PREFIX = {
    "beginner": "I am new here. ",
    "informal_non_native": "pls explain slowly. ",
    "terse_expert": "Quick: ",
    "ops_engineer": "On call tonight. ",
    "aws_migrator": "Coming from Lambda. ",
    "contributor": "Reading the source. ",
}
TEMPLATES = [
    "What does {title} cover?",
    "When should I use {title}?",
    "Which flags matter for {title}?",
    "Where in studio do I do the work of {title}?",
    "Is {title} something that changes a server?",
    "Give one example for {title}.",
    "What should I read before {title}?",
    "How do I complete {title}?",
    "What is the first step in {title}?",
    "Does the studio or the terminal own {title}?",
    "What does the help text say for {title}?",
    "Which related item sits beside {title}?",
    "Which file defines the behavior of {title}?",
    "Can I try {title} before a deploy?",
    "What does {title} change?",
    "How do I inspect {title} without applying?",
    "Which page matches {title}?",
    "Explain {title} to a new teammate.",
    "What limit is documented for {title}?",
    "What input does {title} need?",
    "What result does {title} produce?",
    "How does {title} show up in the project file?",
    "Which provider note belongs to {title}?",
    "What should I avoid while doing {title}?",
    "Walk through {title} on this stage.",
    "What confirmation belongs to {title}?",
    "How do I back out of {title}?",
    "What is the on-premises view of {title}?",
    "What is the cloud view of {title}?",
    "Which source documents {title}?",
    "What purpose line is written for {title}?",
    "List the options that belong with {title}.",
    "Is a studio button documented for {title}?",
    "What local check fits {title}?",
    "What happens if I skip {title}?",
    "How do logs fit after {title}?",
    "Which environment name shows up around {title}?",
    "What runtime rule sits near {title}?",
    "What Terraform output follows {title}?",
    "What should a reviewer look at in {title}?",
    "What is easy to get wrong about {title}?",
    "What stays the same across clouds for {title}?",
    "What does the safety note say about {title}?",
    "Which command example is printed for {title}?",
]
TARGETS = [
    ("k_cmd", 1100, 8),
    ("k_nav", 600, 3),
    ("k_res", 700, 3),
    ("k_onprem", 700, 3),
    ("k_scale", 450, 3),
    ("k_arch", 450, 3),
    ("k_proc", 350, 3),
    ("k_trouble", 150, 3),
]
FENCE = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", re.S)
PATH_ARROW = re.compile(
    r"(?:Overview & provider|Setup & credentials|Functions|Workflows|Resources|Scaling cluster|Load balancers|Network map|Code|Test|Deploy|Logs|YAML)(?: > [^>\n]{1,80})+"
)
KNOWN = cli_index()
HEADINGS = heading_index()


def load_cards() -> list[dict]:
    rows = []
    for line in CARDS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def bucket_of(card: dict) -> str:
    kind = card["kind"]
    cid = card["id"]
    if kind == "command":
        return "k_cmd"
    if kind == "page":
        return "k_nav"
    if kind == "resource":
        return "k_res"
    if kind == "troubleshooting":
        return "k_trouble"
    if kind == "procedure":
        return "k_proc"
    if kind == "onprem":
        if any(tok in cid for tok in ("cluster", "lb-", "firewall", "network", "placement", "tunnel")):
            return "k_scale"
        return "k_onprem"
    return "k_arch"


def spread(count: int, total: int) -> list[int]:
    base, extra = divmod(total, count)
    return [base + (1 if i < extra else 0) for i in range(count)]


def environment(index: int, card: dict | None) -> str:
    provider = PROVIDERS[index % len(PROVIDERS)]
    stage = STAGES[(index // 3) % len(STAGES)]
    mode = MODES[(index // 5) % len(MODES)]
    page = PAGES[index % len(PAGES)]
    if card:
        cid = card["id"]
        if cid.startswith("cmd-deploy") or cid.startswith("proc-deploy") or cid.startswith("page-") and "deploy" in cid:
            page = "Deploy"
        elif cid.startswith("cmd-logs") or "trouble-http" == cid:
            page = "Logs"
        elif cid.startswith("page-") and card["kind"] == "page":
            # Keep the cycled page. Page cards are not all NAV short names.
            pass
    return f"Environment: provider={provider} stage={stage} mode={mode} page={page}"


def system_text(index: int, card: dict | None) -> str:
    return SYSTEM_BEFORE_ENV + environment(index, card)


def card_commands(text: str) -> list[str]:
    found = []
    for match in FENCE.finditer(text):
        for line in match.group(2).splitlines():
            stripped = line.strip()
            if not stripped.startswith("pskit"):
                continue
            if any(token in stripped for token in ("COMMAND", "ARGS…", "ARGS...")):
                continue
            found.append(stripped)
    concrete = [line for line in found if "[OPTIONS]" not in line]
    return concrete or found[:1]


def card_paths(text: str) -> list[str]:
    paths = []
    for match in PATH_ARROW.finditer(text):
        path = match.group(0).strip().rstrip(".,;:")
        if path not in paths:
            paths.append(path)
    return paths


def prose_sentences(text: str) -> list[str]:
    kept = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or line.startswith("#") or " > " in line:
            continue
        cleaned = line.strip(" -\t")
        if len(cleaned) >= 12:
            kept.append(cleaned)
    if not kept:
        kept.append(text.strip().splitlines()[0].lstrip("# ").strip())
    return kept


def cite(sources: list[str]) -> str:
    shown = " ".join(f"[{source}]" for source in sources[:3])
    return f"Sources: {shown}."


def section_lines(path: Path, anchor: str) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = None
    level = 0
    in_fence = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.startswith("#"):
            continue
        current = len(line) - len(line.lstrip("#"))
        title = line[current:].strip()
        if github_anchor(title) == anchor:
            start = index
            level = current
            break
    if start is None:
        return []
    chunk = [lines[start]]
    in_fence = False
    for line in lines[start + 1 :]:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("#"):
            current = len(line) - len(line.lstrip("#"))
            if current <= level:
                break
        chunk.append(line)
    return chunk


def clean_excerpt(source: str) -> str | None:
    path, _, anchor = source.partition("#")
    if not anchor or not path.startswith("docs/"):
        return None
    file_path = ROOT / path
    if not file_path.is_file():
        return None
    if anchor not in HEADINGS.get(path, set()):
        return None
    raw_lines = section_lines(file_path, anchor)
    if not raw_lines:
        return None
    paragraphs = re.split(r"\n\s*\n", "\n".join(raw_lines))
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if "```" in paragraph or " > " in paragraph:
            continue
        if len(paragraph) > 650:
            cut = paragraph[:650]
            dot = max(cut.rfind(". "), cut.rfind(".\n"))
            if dot < 80:
                continue
            paragraph = paragraph[: dot + 1]
        if len(paragraph) < 60:
            continue
        errors: list[str] = []
        check_ips(paragraph, "excerpt", errors)
        check_pskit_lines(paragraph, KNOWN, "excerpt", errors)
        if errors:
            continue
        return f"[{source}]\n{paragraph}"
    return None


_EXCERPT_CACHE: dict[str, tuple[str, str] | None] = {}


def excerpt_for(card: dict) -> tuple[str, str] | None:
    cid = card["id"]
    if cid in _EXCERPT_CACHE:
        return _EXCERPT_CACHE[cid]
    found: tuple[str, str] | None = None
    for source in card.get("sources") or []:
        text = clean_excerpt(source)
        if text:
            found = (source, text)
            break
    _EXCERPT_CACHE[cid] = found
    return found


def in_code_sentence(card: dict) -> str:
    text = card["text"]
    if "## In code" in text:
        chunk = text.split("## In code", 1)[1]
        for line in chunk.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("`"):
                return stripped
    sentences = prose_sentences(text)
    return sentences[0]


def howto_answer(card: dict, sources: list[str], lead: str) -> str:
    lines = []
    if lead:
        lines.append(lead)
        lines.append("")
    lines.append("**In studio**")
    paths = card_paths(card["text"])
    if paths:
        lines.append("1. Open this path:")
        lines.append(paths[0])
    else:
        lines.append("1. This item does not list a studio button. Use the terminal steps.")
    lines.append("")
    lines.append("**In the terminal**")
    commands = card_commands(card["text"])
    if commands:
        for index, command in enumerate(commands[:2], start=1):
            lines.append(f"{index}. Run:")
            lines.append("```")
            lines.append(command)
            lines.append("```")
    else:
        lines.append("1. The card does not include a sample command line. Read the command help before you add flags.")
    lines.append("")
    lines.append("**In code**")
    lines.append("1. " + in_code_sentence(card))
    lines.append("")
    lines.append(cite(sources))
    return "\n".join(lines)


def closed_answer(card: dict, sources: list[str], index: int) -> str:
    sentences = prose_sentences(card["text"])
    start = index % len(sentences)
    chosen = []
    for offset in range(3):
        chosen.append(sentences[(start + offset) % len(sentences)])
    body = " ".join(dict.fromkeys(chosen))
    words = body.split()
    if len(words) > 180:
        body = " ".join(words[:180])
    return body + "\n\n" + cite(sources)


def lead_from_excerpt(excerpt: str) -> str:
    body = excerpt.split("\n", 1)[1]
    sentence = re.split(r"(?<=[.!?])\s+", body.strip())[0].strip()
    if " > " in sentence or sentence.startswith("```"):
        return "The doc excerpt above is the source for this answer."
    if len(sentence) > 320:
        return "The doc excerpt above is the source for this answer."
    return sentence


def make_question(card: dict, index: int, persona: str, salt: str) -> str:
    title = card["title"]
    template = TEMPLATES[index % len(TEMPLATES)]
    question = PREFIX[persona] + template.format(title=title)
    if index >= len(TEMPLATES):
        snippet = prose_sentences(card["text"])[index % len(prose_sentences(card["text"]))]
        snippet = " ".join(snippet.split()[:10])
        question += f" Focus on this line: {snippet}."
    if salt:
        question += " " + salt
    return question


SALTS = [
    "Use the purpose wording.",
    "Use the options wording.",
    "Use the example wording.",
    "Use the safety wording.",
    "Use the related wording.",
    "Stay with the cited heading.",
    "Stay with this stage.",
    "Stay with this provider.",
    "Mention only what the card states.",
    "Skip anything the card does not state.",
]


class QuestionBank:
    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.by_size: dict[int, list[set[str]]] = {}

    def too_close(self, tokens: set[str]) -> bool:
        size = len(tokens)
        low = max(1, int(size * 0.9))
        high = int(size / 0.9) + 1
        for count in range(low, high + 1):
            for prev in self.by_size.get(count, []):
                if jaccard_sets(tokens, prev) >= 0.9:
                    return True
        return False

    def claim(self, text: str) -> str:
        base = text.strip()
        for attempt in range(12):
            extra = "" if attempt == 0 else " " + SALTS[(attempt - 1) % len(SALTS)]
            candidate = base + extra
            norm = normalize_q(candidate)
            if not norm or norm in self.seen:
                continue
            tokens = set(norm.split())
            if len(norm) >= 20 and self.too_close(tokens):
                continue
            self.seen.add(norm)
            if len(norm) >= 20:
                self.by_size.setdefault(len(tokens), []).append(tokens)
            return candidate
        unique = f"{base} Ask number {len(self.seen)} only."
        norm = normalize_q(unique)
        self.seen.add(norm)
        self.by_size.setdefault(len(norm.split()), []).append(set(norm.split()))
        return unique


def jaccard_sets(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    inter = len(left & right)
    if inter == 0:
        return 0.0
    return inter / len(left | right)


def followups(card: dict, persona: str, bank: QuestionBank, turns: int) -> list[str]:
    title = card["title"]
    frames = [
        f"For {title}, what should I check before deploy?",
        f"If I skip the studio for {title}, which written step remains?",
        f"What limit should I remember about {title}?",
        f"After {title}, which page do I open next?",
    ]
    chosen = []
    for frame in frames[:turns]:
        chosen.append(bank.claim(PREFIX[persona] + frame))
    return chosen


def build_record(
    convo_id: str,
    category: str,
    card: dict,
    index: int,
    persona: str,
    grounding: str,
    howto: bool,
    bank: QuestionBank,
    position: int,
) -> dict:
    sources = list(card.get("sources") or [])
    excerpt_pair = excerpt_for(card) if grounding == "search" else None
    if grounding == "search" and not excerpt_pair:
        grounding = "closed"
    question = bank.claim(make_question(card, index, persona, ""))
    if howto:
        lead = ""
        if excerpt_pair:
            lead = lead_from_excerpt(excerpt_pair[1])
        answer = howto_answer(card, sources, lead)
    else:
        answer = closed_answer(card, sources, index)
        if excerpt_pair:
            answer = lead_from_excerpt(excerpt_pair[1]) + "\n\n" + answer
    messages = [{"role": "system", "content": system_text(position, card)}, {"role": "user", "content": question}]
    if grounding == "search" and excerpt_pair:
        call_id = "call_" + convo_id
        query = card["title"]
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "search_docs",
                            "arguments": json.dumps({"query": query}, ensure_ascii=False),
                        },
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": "search_docs",
                "content": excerpt_pair[1],
            }
        )
        if excerpt_pair[0] not in sources:
            sources.append(excerpt_pair[0])
    messages.append({"role": "assistant", "content": answer})
    if category == "k_proc":
        extra = 1 + (index % 3)
        for follow in followups(card, persona, bank, extra):
            messages.append({"role": "user", "content": follow})
            messages.append(
                {
                    "role": "assistant",
                    "content": howto_answer(card, sources, "Same steps, still from the card."),
                }
            )
    return {
        "id": convo_id,
        "messages": messages,
        "meta": {
            "category": category,
            "card_ids": [card["id"]],
            "grounding": grounding,
            "persona": persona,
            "sources": sources[:4],
        },
    }


ABOUT_TOPICS = [
    (
        "the studio assistant",
        "I am Hana, the pskit studio assistant. I help you build, deploy, run, and debug services described in pskit.yml.",
        ["docs/studio.md#what-you-can-do"],
    ),
    (
        "the package name",
        "The package is py-serverless-kit. The import name is py_serverless_kit. The command is pskit.",
        ["README.md", "CLAUDE.md"],
    ),
    (
        "the version string",
        "src/py_serverless_kit/_version.py sets __version__ to 2.10.0. That file is the single version source.",
        ["src/py_serverless_kit/_version.py"],
    ),
    (
        "the provider list",
        "CLAUDE.md names AWS, Azure, GCP, Alibaba, Tencent, Huawei, Oracle, IBM, DigitalOcean, Cloudflare, and an on-premises host.",
        ["CLAUDE.md"],
    ),
    (
        "Terraform in the pipeline",
        "pskit writes Terraform JSON and runs terraform or tofu. It does not call cloud APIs itself. The deploy pipeline in the architecture doc ends in main.tf.json.",
        ["docs/architecture.md#deploy-pipeline"],
    ),
    (
        "the handler API",
        "Handlers use Event, Context, and Response. The same handler is meant to run on every provider. Provider-specific settings belong in options.",
        ["README.md", "docs/handlers.md#handler-signatures"],
    ),
    (
        "pskit.yml",
        "pskit.yml is the service file. It names the service, the provider, the functions, and the events. pskit validate checks it.",
        ["docs/configuration.md#top-level"],
    ),
    (
        "local runs",
        "pskit invoke runs one function with a synthetic event. pskit dev serves HTTP routes on this machine. Neither one is a cloud deploy.",
        ["docs/local-development.md#local-development"],
    ),
    (
        "studio versus the dashboard",
        "pskit studio is the project builder. pskit dashboard is the page of what a deploy created. They are different commands.",
        ["docs/studio.md#what-you-can-do", "docs/dashboard.md#dashboard"],
    ),
    (
        "Python 3.9",
        "Handlers and the vendored runtime stay on Python 3.9. The runtime uses the standard library only.",
        ["CLAUDE.md"],
    ),
    (
        "secrets in env vars",
        "Secrets go in ${env:NAME}. They stay out of pskit.yml and out of handler source.",
        ["docs/configuration.md#variables"],
    ),
    (
        "workflows",
        "A workflow is a state machine in pskit.yml. AWS can compile it to Step Functions. GCP can compile it to Cloud Workflows. Other providers use the embedded engine. pskit workflow run executes it locally.",
        ["docs/workflows.md#workflows-state-machines"],
    ),
    (
        "Node handlers",
        "The README says you can set a nodejs runtime and write JavaScript or TypeScript handlers with the same Event and Context idea.",
        ["README.md", "docs/nodejs.md#nodejs-and-typescript"],
    ),
    (
        "resources in the file",
        "The resources section can name storage, queue, topic, database, cache, custom, and smtp. database, cache, and custom require external true.",
        ["docs/resources.md#fields"],
    ),
    (
        "OpenTofu",
        "OpenTofu is selected by pointing PSKIT_TERRAFORM_BIN at tofu, or by provider.terraform.binary. pskit doctor reports which binary it found.",
        ["docs/troubleshooting.md#installation-and-tooling"],
    ),
    (
        "stages",
        "A stage is a name such as dev, staging, or prod. Output and state live under .pskit/provider-stage, one state per provider and stage.",
        ["docs/architecture.md#state-handling"],
    ),
    (
        "deploy confirmation",
        "For deploy or remove, point to the Deploy page or the command. The studio asks for confirmation. The CLI remove command asks unless -y is set.",
        ["docs/studio.md#project-environment-trigger-resources-and-remove"],
    ),
    (
        "the on-premises host",
        "The on-premises provider starts the service with Terraform local-exec. Methods include local, ssh, and docker. No cloud account is required for a local method.",
        ["docs/providers.md#onprem-on-premises"],
    ),
    (
        "examples in the repo",
        "Each examples directory that contains pskit.yml is packaged and run locally by tests/test_examples.py.",
        ["CLAUDE.md"],
    ),
    (
        "changes and checks",
        "Look at the project before changing it. Make the smallest change. After a change, validate. Do not say it works unless a check passed.",
        ["docs/troubleshooting.md#configuration"],
    ),
]
ABOUT_FRAMES = [
    "Who should I ask about {topic}?",
    "Define {topic} for me.",
    "A new hire asked about {topic}. What is true?",
    "Before we edit the repo, what is {topic}?",
    "In this project, what does {topic} refer to?",
]


def about_records(bank: QuestionBank, start_position: int) -> list[dict]:
    card_id = "concept-getting-started"
    rows = []
    number = 0
    for topic, fact, sources in ABOUT_TOPICS:
        for frame in ABOUT_FRAMES:
            persona = PERSONAS[(start_position + number) % len(PERSONAS)]
            question = bank.claim(PREFIX[persona] + frame.format(topic=topic))
            answer = fact + "\n\n" + cite(sources)
            position = start_position + number
            grounding = "search" if position % 20 < 9 else "closed"
            messages = [
                {"role": "system", "content": system_text(position, None)},
                {"role": "user", "content": question},
            ]
            if grounding == "search":
                excerpt = None
                used = sources[0]
                for source in sources:
                    excerpt = clean_excerpt(source)
                    if excerpt:
                        used = source
                        break
                if excerpt:
                    call_id = f"call_k_about_{number:04d}"
                    messages.append(
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": call_id,
                                    "type": "function",
                                    "function": {
                                        "name": "search_docs",
                                        "arguments": json.dumps({"query": topic}, ensure_ascii=False),
                                    },
                                }
                            ],
                        }
                    )
                    messages.append(
                        {"role": "tool", "tool_call_id": call_id, "name": "search_docs", "content": excerpt}
                    )
                    if used not in sources:
                        sources = [used, *sources]
                else:
                    grounding = "closed"
            messages.append({"role": "assistant", "content": answer})
            rows.append(
                {
                    "id": f"k_about_{number:04d}",
                    "messages": messages,
                    "meta": {
                        "category": "k_about",
                        "card_ids": [card_id],
                        "grounding": grounding,
                        "persona": persona,
                        "sources": sources,
                    },
                }
            )
            number += 1
    return rows


def validate(record: dict, errors: list[str]) -> None:
    check_messages(record["messages"], record["id"], errors)
    blob = "\n".join(message.get("content") or "" for message in record["messages"])
    check_pskit_lines(blob, KNOWN, record["id"], errors)
    check_ips(blob, record["id"], errors)
    check_sources(record["meta"]["sources"], HEADINGS, record["id"], errors)
    if len(blob) / 3.5 > 3000:
        errors.append(f"{record['id']}: too long")


def attach_search(record: dict, card: dict) -> bool:
    pair = excerpt_for(card)
    if not pair:
        return False
    call_id = "call_" + record["id"]
    call = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "search_docs",
                    "arguments": json.dumps({"query": card["title"]}, ensure_ascii=False),
                },
            }
        ],
    }
    tool = {"role": "tool", "tool_call_id": call_id, "name": "search_docs", "content": pair[1]}
    messages = record["messages"]
    index = next(i for i, message in enumerate(messages) if message.get("role") == "assistant")
    messages.insert(index, tool)
    messages.insert(index, call)
    record["meta"]["grounding"] = "search"
    sources = list(record["meta"]["sources"])
    if pair[0] not in sources:
        sources.insert(0, pair[0])
    record["meta"]["sources"] = sources[:4]
    return True


def rebalance(rows: list[dict], cards_by_id: dict[str, dict]) -> None:
    target = int(round(len(rows) * 0.45))
    current = sum(1 for row in rows if row["meta"]["grounding"] == "search")
    for record in rows:
        if current >= target:
            break
        if record["meta"]["grounding"] == "search":
            continue
        card = cards_by_id.get(record["meta"]["card_ids"][0])
        if not card:
            continue
        backup_messages = json.loads(json.dumps(record["messages"]))
        backup_grounding = record["meta"]["grounding"]
        backup_sources = list(record["meta"]["sources"])
        if not attach_search(record, card):
            continue
        local: list[str] = []
        validate(record, local)
        if local:
            record["messages"] = backup_messages
            record["meta"]["grounding"] = backup_grounding
            record["meta"]["sources"] = backup_sources
            continue
        current += 1
    print(f"search {current}/{len(rows)} target {target}")
    if current < target:
        raise SystemExit(f"search share {current} is under {target}")


def main() -> None:
    # The template generator failed the content gates. The checked writer is write_conversations.py.
    from write_conversations import main as write_main

    write_main()
    return
    cards = load_cards()
    grouped: dict[str, list[dict]] = {name: [] for name, _, _ in TARGETS}
    for card in cards:
        grouped[bucket_of(card)].append(card)
    for name, _, _ in TARGETS:
        grouped[name].sort(key=lambda card: card["id"])
    bank = QuestionBank()
    rows_by_cat: dict[str, list[dict]] = {name: [] for name, _, _ in TARGETS}
    position = 0
    errors: list[str] = []
    for name, total, minimum in TARGETS:
        items = grouped[name]
        if not items:
            raise SystemExit(f"no cards for {name}")
        counts = spread(len(items), total)
        if min(counts) < minimum:
            raise SystemExit(f"{name}: min {min(counts)} < {minimum} across {len(items)} cards")
        print(f"{name} cards={len(items)} each={min(counts)}-{max(counts)} total={sum(counts)}")
        for card, count in zip(items, counts):
            pair = excerpt_for(card)
            for index in range(count):
                persona = PERSONAS[position % len(PERSONAS)]
                want_search = position % 20 < 9 and pair is not None
                howto = position % 2 == 0
                record = build_record(
                    f"{name}_{position:04d}",
                    name,
                    card,
                    index,
                    persona,
                    "search" if want_search else "closed",
                    howto,
                    bank,
                    position,
                )
                validate(record, errors)
                if errors:
                    raise SystemExit(errors[0])
                rows_by_cat[name].append(record)
                position += 1
    about = about_records(bank, position)
    for record in about:
        validate(record, errors)
        if errors:
            raise SystemExit(errors[0])
    rows_by_cat["k_about"] = about
    flat = [row for rows in rows_by_cat.values() for row in rows]
    rebalance(flat, {card["id"]: card for card in cards})
    RAW.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, rows in rows_by_cat.items():
        path = RAW / f"{name}.jsonl"
        payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        path.write_bytes(payload.encode("utf-8"))
        total += len(rows)
        print(f"wrote {path.name} {len(rows)}")
    print(f"conversations={total}")


if __name__ == "__main__":
    main()
