"""Emit the authoring workflow. The script only points agents at slot files."""
from pathlib import Path

slots = sorted(Path("ai-agent/training/data/slots").glob("shard_*.json"))
pairs = []
for i in range(0, len(slots), 2):
    group = slots[i : i + 2]
    pairs.append(group)
lines = [
    "let meta = #{",
    '    name: "write-knowledge",',
    '    description: "Write Hana knowledge conversations from card slots",',
    "    phases: [ #{ title: \"Write\", detail: \"authors write JSONL from slots\" } ],",
    "};",
    'phase("Write");',
    "let jobs = [];",
]
for index, group in enumerate(pairs):
    inputs = " and ".join(p.as_posix() for p in group)
    outs = " and ".join(
        "ai-agent/training/data/authored/" + p.name.replace(".json", ".jsonl") for p in group
    )
    prompt = (
        "Read ai-agent/training/tools/_authoring_rules.md and follow every rule. "
        f"Read the slot files {inputs}. "
        f"Write one JSONL file per slot file, at {outs}. "
        "The output names match the slot names. "
        "Write every conversation yourself from its card. "
        "Do not write or run a generator. Do not modify cards or check_knowledge.py."
    )
    # Rhai double-quoted string. Escape backslashes and quotes. Prompt has none.
    escaped = prompt.replace("\\", "\\\\").replace('"', '\\"')
    label = f"write-{index:03d}"
    lines.append(f'jobs.push(#{{ prompt: "{escaped}", label: "{label}", capability_mode: "read-write" }});')
lines.append("let results = parallel(jobs);")
lines.append('let wrote = 0;')
lines.append("for r in results {")
lines.append("    if r != () && r.success { wrote += 1; }")
lines.append("}")
lines.append('complete(#{ summary: wrote.to_string() + " authors finished" });')
path = Path(".grok/workflows/write-knowledge.rhai")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("jobs", len(pairs), "bytes", path.stat().st_size)
