"""One-off validator for authored shards. Not a generator."""
import json
import sys
from collections import Counter
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
import check_knowledge as ck  # noqa: E402
import check_quality as cq  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
AUTHORED = Path(__file__).resolve().parent
SLOTS = AUTHORED.parent / "slots"

errors: list[str] = []
warnings: list[str] = []
known = ck.cli_index()
headings = ck.heading_index()
keys = ck.schema_keys()
blob = ck.studio_blob()

rows = []
for name in ("shard_010.jsonl", "shard_011.jsonl"):
    path = AUTHORED / name
    slot_rows = json.loads((SLOTS / name.replace(".jsonl", ".json")).read_text(encoding="utf-8"))
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != len(slot_rows):
        errors.append(f"{name}: {len(lines)} lines vs {len(slot_rows)} slots")
    for i, (line, slot) in enumerate(zip(lines, slot_rows), 1):
        where = f"{name}:{i}"
        if not line.strip():
            errors.append(f"{where}: blank")
            continue
        obj = json.loads(line)
        rows.append(obj)
        if obj.get("id") != slot["id"]:
            errors.append(f"{where}: id {obj.get('id')} != {slot['id']}")
        meta = obj.get("meta") or {}
        if set(meta) != {"category", "card_ids", "grounding", "persona", "sources"}:
            errors.append(f"{where}: meta keys {sorted(meta)}")
        for field in ("category", "card_ids", "grounding", "persona", "sources"):
            if meta.get(field) != slot[field]:
                errors.append(f"{where}: meta {field} {meta.get(field)!r} != {slot[field]!r}")
        messages = obj.get("messages") or []
        ck.check_messages(messages, where, errors)
        blob_text = "\n".join(m.get("content") or "" for m in messages)
        ck.check_pskit_lines(blob_text, known, where, errors)
        ck.check_sources(meta.get("sources") or [], headings, where, errors)
        ck.check_ips(blob_text, where, errors)
        ck.check_yaml(blob_text, keys, where, warnings)
        ck.check_python(blob_text, where, errors)
        ck.check_studio_paths(blob_text, blob, where, warnings)
        env = f"provider={slot['provider']} stage={slot['stage']} mode={slot['mode']} page={slot['page']}"
        system = messages[0]["content"]
        if env not in system:
            errors.append(f"{where}: missing {env}")
        user = next(m["content"] for m in messages if m["role"] == "user")
        five = " ".join(user.split()[:5])
        low = user.lower()
        for banned in ("can you explain", "how do i", "what does the", "i just opened", "on call for"):
            if low.startswith(banned):
                errors.append(f"{where}: banned opening")
        if slot.get("multi_turn"):
            errors.append(f"{where}: unexpected multi")
        if any(m.get("role") == "tool" or m.get("tool_calls") for m in messages):
            errors.append(f"{where}: unexpected tool")

ck.check_training_shape(rows, errors)

# quality gates on these rows only
answers = Counter()
openings = Counter()
user5 = Counter()
for row in rows:
    cid = row["id"]
    messages = row["messages"]
    for message in messages:
        if message.get("role") == "assistant" and (message.get("content") or "").strip():
            answers[message["content"].strip()] += 1
        if message.get("role") != "user":
            continue
        text = message.get("content") or ""
        openings[" ".join(text.lower().split()[:4])] += 1
        user5[" ".join(text.lower().split()[:5])] += 1
        leaked = cq.TITLE_LEAK.search(text)
        if leaked:
            errors.append(f"Q3 {cid}")
    for message in messages:
        if message.get("role") != "assistant":
            continue
        text = message.get("content") or ""
        low = text.lower()
        for phrase in cq.FILLER:
            if phrase in low:
                errors.append(f"Q2 {cid}: {phrase}")
                break
        part = cq.in_code_part(text)
        if part is not None and "```" not in part:
            errors.append(f"Q4 {cid}")
        first = text.strip().splitlines()[0] if text.strip() else ""
        word = first.split()[0] if first.split() else ""
        mid = word[:1].islower() and word.isalpha() and word not in ("pskit", "hi", "hello")
        if first and (mid or __import__("re").search(r"\|\s*\|---", first)):
            errors.append(f"Q5 {cid}: {first[:60]!r}")
    answer = cq.final_answer(messages)
    if "**In studio**" in answer or "**In the terminal**" in answer:
        if any(p in answer for p in ("does not list a studio button", "does not include a sample command")):
            errors.append(f"Q8 {cid}")
        if "**In the terminal**" in answer and "```" not in ck._section(answer, "In the terminal"):
            errors.append(f"{cid}: terminal section has no fence")
        if "**In studio**" in answer and "Load balancers >" not in ck._section(answer, "In studio"):
            # routes/status/list should not have studio; if they do, path required
            if "Load balancers >" not in answer:
                errors.append(f"{cid}: studio section without path")

for text, n in answers.items():
    if n > 2:
        errors.append(f"Q1 duplicate answer x{n}: {text[:50]!r}")
for opening, n in openings.items():
    if n > 1:
        errors.append(f"Q6 opening x{n}: {opening!r}")
for opening, n in user5.items():
    if n > 1:
        errors.append(f"five x{n}: {opening!r}")

howto = 0
for obj in rows:
    text = "\n".join((m.get("content") or "") for m in obj["messages"] if m.get("role") == "assistant")
    if "In studio" in text or "In the terminal" in text:
        howto += 1
print(f"rows={len(rows)} howto={howto}/{len(rows)} = {howto/len(rows):.1%}")
print(f"errors={len(errors)} warnings={len(warnings)}")
for msg in errors:
    print("ERROR", msg)
for msg in warnings:
    print("WARN", msg)
