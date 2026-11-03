# Hana knowledge dataset

Package version `2.10.0` from `src/py_serverless_kit/_version.py`.

These files are the stage-1 knowledge set. The conversations teach py-serverless-kit from this repository.

Conversations: 4600.
Train: 4370 in `knowledge_train.jsonl` (95%).
Validation: 230 in `knowledge_val.jsonl` (5%), stratified by category.
Shuffle seed: 2100.
Card explanations: 426 in `cards_train.jsonl`. That file is separate from the 4600 conversations.

## Category

- k_about: 100
- k_arch: 450
- k_cmd: 1100
- k_nav: 600
- k_onprem: 700
- k_proc: 350
- k_res: 700
- k_scale: 450
- k_trouble: 150

## Persona

- aws_migrator: 461 (10.0%)
- beginner: 920 (20.0%)
- contributor: 690 (15.0%)
- informal_non_native: 1150 (25.0%)
- ops_engineer: 689 (15.0%)
- terse_expert: 690 (15.0%)

## Grounding

- closed: 2530 (55.0%)
- search: 2070 (45.0%)

## How-to share

2511/4600 = 54.6% of conversations have an assistant reply containing "In studio" or "In the terminal".

## Files

- `ai-agent/training/data/raw/k_*.jsonl` is the source split by category.
- `ai-agent/training/data/final/knowledge_train.jsonl` and `knowledge_val.jsonl` add the `search_docs` tool definition.
- `ai-agent/training/knowledge/index_source.jsonl` is a copy of `knowledge/cards.jsonl`.
- `ai-agent/training/knowledge/cards/` holds the same card text as the JSONL.

Cards for deploy, remove, and server changes come from `--help`, docs, and code.
