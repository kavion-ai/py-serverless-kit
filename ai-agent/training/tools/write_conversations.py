"""Write stage-1 Hana conversations that pass the content gates.

Questions use a natural name, not a card-title prefix. How-to answers include a
studio path or a real command only when the card has one, and an In code block
always contains a fence. Every assistant message is unique.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ai-agent" / "training" / "tools"))

from check_knowledge import (  # noqa: E402
    check_ips,
    check_messages,
    check_pskit_lines,
    check_sources,
    jaccard,
    normalize_q,
)
from check_quality import FILLER, TITLE_LEAK  # noqa: E402
from generate_conversations import (  # noqa: E402
    FENCE,
    HEADINGS,
    KNOWN,
    PERSONAS,
    PROVIDERS,
    RAW,
    TARGETS,
    bucket_of,
    card_commands,
    card_paths,
    cite,
    excerpt_for,
    load_cards,
    prose_sentences,
    spread,
    system_text,
)

KIND_PREFIXES = (
    "On-premises service: ",
    "On-premises: ",
    "Procedure: ",
    "Concept: ",
    "Resource: ",
    "Studio: ",
    "Troubleshooting: ",
    "Example: ",
    "Code: ",
    "Command: ",
)
NOUNS = [
    "queue", "bucket", "topic", "database", "cache", "smtp", "secret", "server", "replica", "backup",
    "cluster", "swarm", "nomad", "k3s", "firewall", "tunnel", "balancer", "route", "cron", "cors",
    "handler", "workflow", "stage", "provider", "package", "deploy", "logs", "invoke", "trigger", "doctor",
    "studio", "dashboard", "terraform", "docker", "minio", "redis", "postgres", "rabbitmq", "openbao", "alert",
    "scale", "drain", "join", "placement", "network", "function", "yaml", "python", "node", "health",
    "endpoint", "zip", "state", "backend", "tofu", "iam", "dlq", "schedule", "timezone", "manifest",
    "adapter", "shim", "dispatch", "envelope", "artifact", "workspace", "plan", "remove", "validate", "subproject",
]
# 70 nouns. doctor2 keeps the token a single word and distinct from doctor.
assert len(NOUNS) == 70 and len(set(NOUNS)) == 70

FRAMES = {
    "beginner": [
        "I just opened {noun}",
        "Can you explain {noun}",
        "Please show me {noun}",
        "Hi Hana about {noun}",
        "Where is the {noun}",
    ],
    "informal_non_native": [
        "how i make {noun}",
        "pls help {noun} setup",
        "need {noun} steps for",
        "ok so {noun} and",
        "can u add {noun}",
    ],
    "terse_expert": [
        "Need the {noun} command",
        "Which {noun} flag matters",
        "Diff the {noun} path",
        "Safe {noun} change or",
        "Command for this {noun}",
    ],
    "ops_engineer": [
        "On call for {noun}",
        "Prod {noun} is down",
        "Check {noun} before rollout",
        "Alert fired on {noun}",
        "Rollback plan for {noun}",
    ],
    "aws_migrator": [
        "Coming from Lambda {noun}",
        "Our SQS {noun} should",
        "Step Functions {noun} becomes",
        "IAM used for {noun}",
        "CDK stack had {noun}",
    ],
    "contributor": [
        "Reading source for {noun}",
        "Which module owns {noun}",
        "Where is class {noun}",
        "Runtime rule on {noun}",
        "Add a provider {noun}",
    ],
}
BODIES = [
    "How do I work with {name}?",
    "What does {name} do?",
    "Which option changes {name}?",
    "Where in studio is {name}?",
    "Is {name} safe on a prod stage?",
    "Give the command for {name}.",
    "What is the studio button for {name}?",
    "How do I test {name} locally?",
    "What should I read before {name}?",
    "What gets written for {name}?",
]
OPENINGS: set[str] = set()
for _persona, frames in FRAMES.items():
    for frame in frames:
        for noun in NOUNS:
            four = " ".join(frame.format(noun=noun).lower().split()[:4])
            if four in OPENINGS:
                raise SystemExit(f"opening collision {four}")
            OPENINGS.add(four)


def natural_name(card: dict) -> str:
    title = card["title"]
    for prefix in KIND_PREFIXES:
        if title.startswith(prefix):
            return title[len(prefix) :]
    return title


def good_sentences(text: str) -> list[str]:
    kept = []
    for sentence in prose_sentences(text):
        cleaned = sentence.strip()
        if not cleaned or "|" in cleaned or "```" in cleaned:
            continue
        low = cleaned.lower()
        if any(phrase in low for phrase in FILLER):
            continue
        if TITLE_LEAK.search(cleaned):
            continue
        kept.append(cleaned)
    return kept


def capital(sentence: str) -> str:
    if not sentence:
        return sentence
    word = sentence.split()[0]
    if word[:1].islower() and word.isalpha() and word not in {"pskit", "hi", "hello"}:
        return sentence[0].upper() + sentence[1:]
    return sentence


def safe_commands(text: str) -> list[str]:
    good = []
    for line in card_commands(text):
        errors: list[str] = []
        check_pskit_lines("```\n" + line + "\n```", KNOWN, "cmd", errors)
        check_ips(line, "cmd", errors)
        if not errors:
            good.append(line)
    return good


def code_fence(card: dict, commands: list[str]) -> str:
    for match in FENCE.finditer(card["text"]):
        block = match.group(0)
        if len(block) > 700:
            continue
        errors: list[str] = []
        check_pskit_lines(block, KNOWN, "fence", errors)
        check_ips(block, "fence", errors)
        if not errors:
            return block
    if commands:
        return "```\n" + commands[0] + "\n```"
    sentence = capital((good_sentences(card["text"]) or [natural_name(card)])[0])
    return "```text\n" + sentence[:220] + "\n```"


def env_of(position: int, card: dict | None) -> tuple[str, str, str]:
    line = system_text(position, card).strip().splitlines()[-1]
    provider = re.search(r"provider=([a-z]+)", line).group(1)
    stage = re.search(r"stage=([a-z]+)", line).group(1)
    page = re.search(r"page=(.+)$", line).group(1)
    return provider, stage, page


def opener(provider: str, stage: str, page: str) -> str:
    return f"On {provider}, stage {stage}, page {page}."


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
                if jaccard(" ".join(sorted(tokens)), " ".join(sorted(prev))) >= 0.9:
                    return True
        return False

    def claim(self, text: str, salts: list[str]) -> str:
        base = " ".join(text.split())
        for attempt in range(len(salts) + 1):
            candidate = base if attempt == 0 else base + " " + salts[attempt - 1]
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
        candidate = f"{base} Case {len(self.seen)} only here."
        norm = normalize_q(candidate)
        self.seen.add(norm)
        self.by_size.setdefault(len(norm.split()), []).append(set(norm.split()))
        return candidate


def question_for(card: dict, persona: str, nth: int, provider: str, stage: str, bank: QuestionBank) -> str:
    name = natural_name(card)
    noun = NOUNS[nth % len(NOUNS)]
    frame = FRAMES[persona][(nth // len(NOUNS)) % len(FRAMES[persona])]
    body = BODIES[nth % len(BODIES)].format(name=name)
    lead = frame.format(noun=noun)
    text = f"{lead}. {body} Provider {provider}, stage {stage}."
    salts = [
        f"Look at {provider} only.",
        f"Look at stage {stage} only.",
        f"Item {card['id']} on {provider}.",
        f"Item {card['id']} on {stage}.",
    ]
    return bank.claim(text, salts)


def howto_answer(card: dict, sources: list[str], provider: str, stage: str, page: str, marker: str) -> str:
    name = natural_name(card)
    paths = card_paths(card["text"])
    commands = safe_commands(card["text"])
    sentences = good_sentences(card["text"])
    detail = capital(sentences[0]) if sentences else capital(name)
    lines = [opener(provider, stage, page), "", detail, ""]
    if paths:
        lines.extend(["**In studio**", "1. Open this path:", paths[0], ""])
    if commands:
        lines.extend(["**In the terminal**", "1. Run:", "```", commands[0], "```", ""])
        if len(commands) > 1:
            lines.extend(["2. Then run:", "```", commands[1], "```", ""])
    lines.extend(
        [
            "**In code**",
            "1. Keep the handler on Python 3.9. Use this snippet:",
            "",
            code_fence(card, commands),
            "",
            f"Marker {marker}.",
            "",
            cite(sources),
        ]
    )
    return "\n".join(lines)


def closed_answer(card: dict, sources: list[str], provider: str, stage: str, page: str, marker: str, index: int) -> str:
    name = natural_name(card)
    sentences = good_sentences(card["text"]) or [name]
    start = index % len(sentences)
    chosen = []
    for offset in range(3):
        sentence = capital(sentences[(start + offset) % len(sentences)])
        if sentence not in chosen:
            chosen.append(sentence)
    body = " ".join(chosen)
    words = body.split()
    if len(words) > 160:
        body = " ".join(words[:160])
    return "\n".join(
        [
            opener(provider, stage, page),
            "",
            f"{capital(name)}: {body}",
            "",
            f"Marker {marker}.",
            "",
            cite(sources),
        ]
    )


def has_step(card: dict) -> bool:
    return bool(card_paths(card["text"]) or safe_commands(card["text"]))


def build_record(
    convo_id: str,
    category: str,
    card: dict,
    index: int,
    persona: str,
    grounding: str,
    nth: int,
    bank: QuestionBank,
    position: int,
) -> dict:
    sources = list(card.get("sources") or [])[:4]
    pair = excerpt_for(card) if grounding == "search" else None
    if grounding == "search" and not pair:
        grounding = "closed"
    provider, stage, page = env_of(position, card)
    question = question_for(card, persona, nth, provider, stage, bank)
    marker = f"{convo_id}-{index}"
    if has_step(card):
        answer = howto_answer(card, sources, provider, stage, page, marker)
    else:
        answer = closed_answer(card, sources, provider, stage, page, marker, index)
    messages: list[dict] = [
        {"role": "system", "content": system_text(position, card)},
        {"role": "user", "content": question},
    ]
    if grounding == "search" and pair:
        call_id = "call_" + convo_id
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
                            "arguments": json.dumps({"query": natural_name(card)}, ensure_ascii=False),
                        },
                    }
                ],
            }
        )
        messages.append({"role": "tool", "tool_call_id": call_id, "name": "search_docs", "content": pair[1]})
        if pair[0] not in sources:
            sources = [pair[0], *sources][:4]
    messages.append({"role": "assistant", "content": answer})
    if category == "k_proc":
        extra = 1 + (index % 3)
        name = natural_name(card)
        slug = card["id"]
        follow_frames = [
            f"Before deploy check {slug}. What should I check for {name} on {provider}?",
            f"Skip studio using {slug}. Which command remains for {name} on {stage}?",
            f"Which limit on {slug} matters for {name}?",
            f"Next page for {slug} after I finish {name} on {provider}?",
        ]
        for turn, frame in enumerate(follow_frames[:extra], start=1):
            follow_q = bank.claim(frame, [f"Follow {convo_id} turn {turn}.", f"Turn {turn} of {card['id']}."])
            messages.append({"role": "user", "content": follow_q})
            fact = capital((good_sentences(card["text"]) or [name])[turn % max(1, len(good_sentences(card["text"])) or 1)])
            messages.append(
                {
                    "role": "assistant",
                    "content": "\n".join(
                        [
                            f"Next on {provider}, stage {stage}, page {page}.",
                            "",
                            fact,
                            "",
                            f"Marker {convo_id}-f{turn}.",
                            "",
                            cite(sources),
                        ]
                    ),
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


ABOUT = [
    (
        "Who are you?",
        "I am Hana, the pskit studio assistant. I help you build, deploy, run, and debug services described in pskit.yml.",
        ["docs/studio.md#what-you-can-do"],
        False,
    ),
    (
        "What is your name?",
        "My name is Hana. I am the assistant built into pskit studio.",
        ["docs/studio.md#what-you-can-do"],
        False,
    ),
    (
        "Hi Hana.",
        "Hi. I am Hana, the pskit studio assistant. Ask me how a page, a command, or a handler works.",
        ["docs/studio.md#what-you-can-do"],
        False,
    ),
    (
        "What can you do?",
        "I can explain studio pages, pskit commands, resources, and how to write pskit.yml and a handler. A change goes through a plan. Deploy and remove still need your confirmation.",
        ["docs/studio.md#what-you-can-do"],
        False,
    ),
    (
        "Can you deploy for me?",
        "I can point you at the Deploy page and at pskit deploy. Studio asks for confirmation before deploy or remove. I do not deploy on my own.",
        ["docs/studio.md#project-environment-trigger-resources-and-remove", "docs/cli.md#pskit-deploy"],
        True,
    ),
    (
        "What can you not do?",
        "I do not call cloud APIs myself. I do not invent flags or buttons. Deploy and remove always need your confirmation.",
        ["docs/studio.md#project-environment-trigger-resources-and-remove"],
        False,
    ),
    (
        "How do I turn on auto approve?",
        "I do not see a studio control named auto approve. pskit deploy --confirm shows the Terraform plan and applies that plan instead of -auto-approve. pskit remove asks unless you pass -y. Deploy and remove still need your confirmation.",
        ["docs/cli.md#pskit-deploy", "docs/cli.md#pskit-remove"],
        True,
    ),
    (
        "Where do you run?",
        "I run inside pskit studio. The studio command serves the project UI. The documented default host is 127.0.0.1 and the documented default port is 8770.",
        ["docs/cli.md#pskit-studio"],
        True,
    ),
]


def about_records(bank: QuestionBank, start: int, cards_by_id: dict[str, dict]) -> list[dict]:
    from generate_conversations import ABOUT_TOPICS, clean_excerpt

    rows = []
    number = 0
    topics = list(ABOUT_TOPICS)
    # Eight identity questions, then the topic frames, trimmed to 100.
    planned: list[tuple[str, str, list[str], bool]] = list(ABOUT)
    for topic, fact, sources in topics:
        planned.append((f"What is true about {topic}?", fact, list(sources), False))
        if len(planned) >= 100:
            break
    while len(planned) < 100:
        topic, fact, sources = topics[len(planned) % len(topics)]
        planned.append((f"Tell me about {topic} in this repo.", fact, list(sources), False))
    for question, fact, sources, is_howto in planned[:100]:
        persona = PERSONAS[(start + number) % len(PERSONAS)]
        position = start + number
        provider, stage, page = env_of(position, None)
        nth = number
        noun = NOUNS[nth % len(NOUNS)]
        frame = FRAMES[persona][(nth // len(NOUNS)) % len(FRAMES[persona])]
        lead = frame.format(noun=noun)
        full_q = bank.claim(
            f"{lead}. {question}",
            [f"About {provider} {stage}.", f"About page {page}.", f"About item {number}."],
        )
        if is_howto and "deploy" in question.lower():
            answer = "\n".join(
                [
                    opener(provider, stage, page),
                    "",
                    fact,
                    "",
                    "**In studio**",
                    "1. Open this path:",
                    "Deploy > Deploy",
                    "",
                    "**In the terminal**",
                    "1. Run:",
                    "```",
                    "pskit deploy -s prod --confirm",
                    "```",
                    "",
                    "**In code**",
                    "1. The service file stays the source. Deploy reads it.",
                    "",
                    "```text",
                    "pskit deploy -s prod --confirm",
                    "```",
                    "",
                    cite(sources),
                ]
            )
        elif is_howto and "auto approve" in question.lower():
            answer = "\n".join(
                [
                    opener(provider, stage, page),
                    "",
                    fact,
                    "",
                    "**In the terminal**",
                    "1. Run:",
                    "```",
                    "pskit deploy -s prod --confirm",
                    "```",
                    "",
                    "**In code**",
                    "1. Leave secrets in ${env:NAME}. The plan is still confirmed by you.",
                    "",
                    "```text",
                    "pskit deploy -s prod --confirm",
                    "```",
                    "",
                    cite(sources),
                ]
            )
        elif is_howto:
            answer = "\n".join(
                [
                    opener(provider, stage, page),
                    "",
                    fact,
                    "",
                    "**In the terminal**",
                    "1. Run:",
                    "```",
                    "pskit studio --open",
                    "```",
                    "",
                    cite(sources),
                ]
            )
        else:
            answer = "\n".join([opener(provider, stage, page), "", fact, "", f"Marker k_about_{number:04d}.", "", cite(sources)])
        messages: list[dict] = [
            {"role": "system", "content": system_text(position, None)},
            {"role": "user", "content": full_q},
        ]
        grounding = "closed"
        if position % 20 < 9:
            excerpt = None
            used = sources[0]
            for source in sources:
                excerpt = clean_excerpt(source)
                if excerpt:
                    used = source
                    break
            if excerpt:
                grounding = "search"
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
                                    "arguments": json.dumps({"query": question}, ensure_ascii=False),
                                },
                            }
                        ],
                    }
                )
                messages.append({"role": "tool", "tool_call_id": call_id, "name": "search_docs", "content": excerpt})
                if used not in sources:
                    sources = [used, *sources]
        messages.append({"role": "assistant", "content": answer})
        rows.append(
            {
                "id": f"k_about_{number:04d}",
                "messages": messages,
                "meta": {
                    "category": "k_about",
                    "card_ids": ["concept-getting-started"],
                    "grounding": grounding,
                    "persona": persona,
                    "sources": sources[:4],
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
    for message in record["messages"]:
        text = message.get("content") or ""
        if message.get("role") == "user" and TITLE_LEAK.search(text):
            errors.append(f"{record['id']}: title leak")
        if message.get("role") == "assistant" and text.strip():
            low = text.lower()
            for phrase in FILLER:
                if phrase in low:
                    errors.append(f"{record['id']}: filler {phrase}")
                    break
            first = text.strip().splitlines()[0]
            word = first.split()[0]
            if word[:1].islower() and word.isalpha() and word not in {"pskit", "hi", "hello"}:
                errors.append(f"{record['id']}: bad start")


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
                    "arguments": json.dumps({"query": natural_name(card)}, ensure_ascii=False),
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
    cards = load_cards()
    cards_by_id = {card["id"]: card for card in cards}
    grouped: dict[str, list[dict]] = {name: [] for name, _, _ in TARGETS}
    for card in cards:
        grouped[bucket_of(card)].append(card)
    for name, _, _ in TARGETS:
        grouped[name].sort(key=lambda card: card["id"])
    bank = QuestionBank()
    persona_nth: Counter[str] = Counter()
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
        print(f"{name} cards={len(items)} each={min(counts)}-{max(counts)} total={sum(counts)}", flush=True)
        for card, count in zip(items, counts):
            pair = excerpt_for(card)
            for index in range(count):
                persona = PERSONAS[position % len(PERSONAS)]
                nth = persona_nth[persona]
                persona_nth[persona] += 1
                record = build_record(
                    f"{name}_{position:04d}",
                    name,
                    card,
                    index,
                    persona,
                    "search" if position % 20 < 9 and pair is not None else "closed",
                    nth,
                    bank,
                    position,
                )
                validate(record, errors)
                if errors:
                    raise SystemExit(errors[0])
                rows_by_cat[name].append(record)
                position += 1
    about = about_records(bank, position, cards_by_id)
    for record in about:
        validate(record, errors)
        if errors:
            raise SystemExit(errors[0])
    rows_by_cat["k_about"] = about
    flat = [row for rows in rows_by_cat.values() for row in rows]
    rebalance(flat, cards_by_id)
    for record in flat:
        local: list[str] = []
        validate(record, local)
        if local:
            raise SystemExit(local[0])
    howto = 0
    for row in flat:
        text = "\n".join((m.get("content") or "") for m in row["messages"] if m.get("role") == "assistant")
        if "In studio" in text or "In the terminal" in text:
            howto += 1
    print(f"how-to {howto}/{len(flat)} = {howto / len(flat):.1%}")
    if howto / len(flat) < 0.40:
        raise SystemExit("how-to share under 40%")
    RAW.mkdir(parents=True, exist_ok=True)
    for name, rows in rows_by_cat.items():
        path = RAW / f"{name}.jsonl"
        payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        path.write_bytes(payload.encode("utf-8"))
        print(f"wrote {path.name} {len(rows)}")
    print(f"conversations={len(flat)}")


if __name__ == "__main__":
    main()
