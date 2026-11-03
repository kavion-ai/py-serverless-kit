# Write these conversations yourself

Read each slot. Read that slot's card file. Write one conversation. Do not write a Python generator, and do not run generate_conversations.py or write_conversations.py.

## Record

One JSON object per line, UTF-8. Fields: id, messages, meta.

meta: category, card_ids, grounding, persona, sources. Copy these from the slot. Add nothing else.

messages:

1. system. Read `SYSTEM_BEFORE_ENV` in `ai-agent/training/tools/check_knowledge.py` and copy it unchanged, then one line:
   `Environment: provider=<slot.provider> stage=<slot.stage> mode=<slot.mode> page=<slot.page>`
   Page is one of: Overview, Setup, Functions, Workflows, Resources, Cluster, Load balancers, Network map, Code, Test, Deploy, Logs, YAML, none.
2. user. One natural question in the slot's persona. Mention provider or stage only when the question needs them. On-prem questions stay on-prem: never ask about provider tencent for an on-prem service. The first five words must be unique in your file and must include a concrete flag, button, file, or resource name from the card. Do not start with "Can you explain", "How do I", "What does the", "I just opened", or "On call for".
3. If grounding is search: an assistant message with content "" and tool_calls:
   `[{"id":"call_N","type":"function","function":{"name":"search_docs","arguments":"{\"query\":\"short topic\"}"}}]`
   Use a call id like call_01, not the record id. Then a tool message: `{"role":"tool","tool_call_id":"call_N","name":"search_docs","content": <the slot excerpt, verbatim>}`. The excerpt is already 300-1500 characters and starts with [path#anchor]. Then the assistant answer. The answer may use only facts that are in that excerpt or in the card. Do not add facts from memory.
4. If grounding is closed: the assistant answer follows the user message. No tool call.
5. If multi_turn is true: 2 to 4 user turns. Each user turn is a real follow-up. Answer each one. A search call happens once, before the first answer.

The last message is an assistant answer with no tool_calls.

## Answers

Answer the question that was asked.

- A "where in studio" question starts with "In studio".
- A "which flag" question names the flag in the first sentence.
- A command question gives the purpose, the command with real flags, and one real example.
- Do not start with "On aws, stage dev" or any "On <provider>, stage".
- No "Marker", no record id, no card id, no "the catalog id is".
- Secrets only as `${env:NAME}` or `--password-env NAME`. No literal passwords.
- Vary the shape. Some answers are one sentence. Some are numbered steps. Some are a short table. Do not give every answer the same outline.

**In studio**, **In the terminal**, and **In code** appear only when that way exists. At least half of your conversations are how-tos and use the headings that apply, numbered.

- In studio: real navigation such as `Deploy > Deploy`. One path per line.
- In the terminal: a fenced command with real flags.
- In code: a ```yaml pskit.yml snippet and/or a ```python or ```javascript handler. Never put the CLI command in In code. Leave the heading out if it would only repeat the terminal.

k_about (empty card_path): you are Hana, the pskit studio assistant. Changes go through a plan and approval. Deploy and remove need confirmation. There is no studio control named "auto approve". Do not claim to be another product. Keep these answers short.

## Persona voice

- beginner: plain, one question, no jargon piled up
- informal_non_native: short words, a small grammar slip is fine, still clear
- terse_expert: few words, wants the flag or the command
- ops_engineer: production, rollback, what breaks
- aws_migrator: coming from Lambda, SQS, Step Functions, or IAM
- contributor: asks where the code lives or what a change must keep true

Write the file with the Write tool. One JSON object per line. No commentary in the file.
