# Concept: workflow states

State types are task, choice, wait, pass, parallel, map, succeed, and fail. A task calls `function` and may set `input_path`, `result_path`, `retry`, `catch`, and `timeout_seconds`. A choice has `choices` and an optional `default`. With no match and no default the run fails with `States.NoChoiceMatched`. A wait sleeps for `seconds` or `seconds_path`. A pass injects `result` or passes the input through. Parallel runs `branches` at the same time and the result is a list, one item per branch. Map runs `iterator` for each item from `items_path`, with optional `max_concurrency`, and the result is a list. Succeed finishes with the current data. Fail finishes with `error` and `cause`.

A task, wait, pass, parallel, or map without `next` is treated as `end: true`. The schema sets `end` in that case. Every state can have a `comment`.

JSON paths are `$`, `$.a.b`, `$.items[0]`, and `$['key']`. `input_path` selects what the task receives. The default is `$`. `result_path` of `$` replaces the state data with the result. `$.payment` stores the result under that key. `null` discards the result. The schema default for `result_path` is `$`.

Retry `errors` are exception class names. `"*"` or `States.ALL` means any. Defaults in the schema and the doc are `max_attempts` 3, `interval_seconds` 1, and `backoff_rate` 2.0. `max_delay_seconds` is optional. The first matching retrier is used. When retries are exhausted, the first matching catcher routes to `next`. A catch `result_path` defaults to `$.error` and stores `error` and `cause`. With no match the run fails. A rule whose variable is missing or the wrong type is false, not a failure.

Sources: `docs/workflows.md#state-types`, `docs/workflows.md#data-flow`, `docs/workflows.md#retry-and-catch`, `src/py_serverless_kit/config/schema.py`

```text
choices:
  - {variable: "$.status", equals: "paid", next: Ship}
  - {variable: "$.amount", gte: 100, next: Review}
  - and:
      - {variable: "$.country", in: [IN, US]}
      - not: {variable: "$.vip", equals: true}
    next: Standard
  - or: [{variable: "$.email", is_present: false}, {variable: "$.email", is_null: true}]
    next: AskEmail
```
