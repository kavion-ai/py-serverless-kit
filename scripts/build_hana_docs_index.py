"""Rebuild Hana's docs index (``src/py_serverless_kit/studio/hana/docs.jsonl.gz``) from ``docs/**/*.md``.

Run from anywhere after changing the docs:

    python scripts/build_hana_docs_index.py          # write the index
    python scripts/build_hana_docs_index.py --check  # exit 1 if it is out of date (CI / pre-commit)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from py_serverless_kit.studio.hana import docs_index  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only check that the index is up to date")
    args = parser.parse_args()
    cards = docs_index.build(REPO)
    data = docs_index.encode(cards)
    current = docs_index.INDEX.read_bytes() if docs_index.INDEX.is_file() else b""
    if args.check:
        if current != data:
            print("Hana's docs index is out of date: run python scripts/build_hana_docs_index.py")
            return 1
        print(f"Hana's docs index is up to date ({len(cards)} cards).")
        return 0
    docs_index.INDEX.write_bytes(data)
    pages = len({c["sources"][0].split("#")[0] for c in cards})
    print(f"Wrote {docs_index.INDEX.relative_to(REPO).as_posix()}: {len(cards)} cards from {pages} pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
