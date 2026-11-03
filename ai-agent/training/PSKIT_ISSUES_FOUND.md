# pskit issues found while generating the stage-2 dataset

The dataset agents ran `pskit validate` / `pskit invoke` (v2.10.0) on scratch projects. These looked wrong. None of
them is used in training samples, and no code or docs were changed. Check each one before fixing.

## Crashes (traceback instead of a config error)

- `extends: base.yml` with a missing file: `FileNotFoundError` (`config/loader.py` `_read_layers`).
- `${file(x.json)}` pointing at invalid JSON: `JSONDecodeError`.
- `environment` written as a list (function or provider level): `AttributeError: 'list' object has no attribute 'items'`.
  The same with a string (`environment: "LOG_LEVEL=debug"`): `AttributeError: 'str' object has no attribute 'items'`
  (`config/schema.py` `_env`).
- onprem `options.balancer: true`: `TypeError: 'bool' object is not iterable`.

## Unhelpful messages

- onprem `options.placement` as a list, with an unknown key (`group:`), or `groups: {}`: prints only
  `Error: function_group`.

## Accepted without an error or warning

- Choice rule with an unknown operator (`eq:`), wait `seconds: -10`, map `max_concurrency: -1`.
- HTTP path without a leading `/`; Express-style `/users/:id`.
- `${self:}` references that point at each other in a circle; unknown `${ssm:...}` variable source.
- Cron with hour 25; rate `0 minutes`; `allow_credentials: true` with origin `*`.
- onprem `balancer: {name: edge}` when no balancer named edge exists.
- onprem `concurrency` (not documented for onprem); onprem `iam.statements` (docs say ignored "with a warning").
- onprem `provider.log_retention_days` is silently ignored (under `options` it warns "unknown option").
- http event without `path` (`- http: {method: GET}`); queue `max_receive: 0`, `visibility_timeout: -1`;
  retry `max_attempts: 0`, `interval_seconds: 0`; `architecture: arm64` on azure; a missing
  `package.requirements` file; leftover GCP `options.project` on aws.
- An smtp resource on aws still errors ("AWS Lambda does not support smtp resources") after the function using it
  is disabled on aws.
- GCP queue `batch_size` / `batch_window` (docs say they warn).

## Runtime / local invoke

- `ctx.remaining_time_ms()` returns `None` under `pskit invoke` and on Azure (adapter sets no deadline), so
  `ctx.remaining_time_ms() < 5000` raises TypeError.
- Nested variables `${self:custom.x.${opt:stage}}` are not resolved.
- `invoke()` of an unknown function recurses locally (RecursionError).

- Node.js: an ESM `import { NotFound } from "pskit"` in a `.js` handler fails on Node 24 ("does not provide an export
  named 'NotFound'"), while docs/nodejs.md shows that import in TypeScript.

## Docs that don't match the code

- `docs/load-balancers.md:39`: `servers add lb1 --host ... --user ... --key ...`; the real flags are
  `--ssh user@host[:port]` and `--pem`.
- `docs/events.md` says Azure ignores queue `batch_size`; `docs/resource-guides/azure/queue.md` uses `batch_size: 16`.
- `docs/local-development.md`: the `http_event` / `build_event` table and the `WorkflowEngine` note sit under
  "On-premises is a deploy, not pskit dev" instead of "Testing with pytest".
- Azure `schedule: 7 minutes` becomes `0 */7 * * * *` (last gap of each hour is 4 minutes); worth a docs note.
- GCP schedule-only functions accept `timeout: 900` (540 s applies to event triggers only); worth a docs note.
