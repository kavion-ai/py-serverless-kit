import json
from pathlib import Path

shown = 0
for path in sorted(Path("ai-agent/training/data/slots").glob("shard_*.json")):
    for slot in json.loads(path.read_text(encoding="utf-8")):
        if slot["grounding"] != "search":
            continue
        text = slot["excerpt"]
        body = text.split("\n", 1)[1]
        print(slot["id"], slot["card_ids"], len(body), body[:180].replace("\n", " "))
        print("---")
        shown += 1
        if shown >= 4:
            raise SystemExit
