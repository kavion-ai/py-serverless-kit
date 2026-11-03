# Conflicts

When two repository files disagree, the code wins. Cards must follow the code and cite both files.

## Fields table omits `smtp` (2026-10-31)

- `docs/resources.md` section "Fields" says `type` is required and lists `storage`, `queue`, `topic`, `database`, `cache` or `custom`.
- The same file later says a resource of `type: smtp` (on premises) is the SMTP server one-click service.
- `src/py_serverless_kit/config/schema.py` sets `RESOURCE_TYPES = ("storage", "queue", "topic", "database", "cache", "custom", "smtp")`.

Code wins: `smtp` is a resource type. The Fields table is incomplete.

`docs/configuration.md` section `resources` lists `type` as `storage`, `queue`, `topic`, `database`, `cache`, `custom` and does not list `smtp`. The same `RESOURCE_TYPES` tuple includes `smtp`. Code wins.

## Handler `Event.type` table omits `smtp` (2026-10-31)

- `docs/handlers.md` section `Event` lists `type` as `http`, `schedule`, `queue`, `storage`, `topic`, `invoke`, `workflow`.
- `src/py_serverless_kit/runtime/event.py` `EventType.ALL` is those values plus `smtp`. The comment says `data` is the parsed mail.
- `docs/events.md` documents an `smtp` trigger. `EVENT_TYPES` in `config/schema.py` includes `smtp`.

Code wins: a handler can see `event.type == "smtp"`. The handlers table is incomplete. `invoke` and `workflow` are runtime event types. They are not keys in `EVENT_TYPES`.

## `docs/cli.md` does not document three command groups

Not a contradictory sentence. `docs/cli.md` has no mention of `pskit lb`, `pskit firewall`, or `pskit function`. Those commands exist on the Click group in `src/py_serverless_kit/cli/main.py` (see `ai-agent/training/knowledge/cli.json`). Cards for them cite the CLI and the feature docs (`docs/load-balancers.md`, `docs/onprem-network.md`, `docs/placement.md`), not `docs/cli.md`.
