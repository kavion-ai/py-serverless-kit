## Configuration

**`unresolved variables: env:FOO`**
: Set the variable, or give a default: `${env:FOO, fallback}`.

**`each event must be a single-key mapping`**
: Write `- http: {path: /x}` and `- queue: jobs` as separate list items, not two keys in one item.

**`route GET /x is used by both 'a' and 'b'`**
: Each `METHOD /path` may belong to one function only (`/x` and `/x/` count as the same path).

**`<provider> does not support python3.12`**
: You pinned `runtime:`. Remove it so pskit picks a supported version, or choose one the provider supports (`pskit providers --json`).

**Values from a parent file win over my child file**
: Child values beat a parent's `providers.<cloud>` block. Check the precedence order. Lists replace rather than merge.

Add -v to the command when you need the traceback. Start with pskit validate and pskit doctor. The studio Problems list and Setup & credentials show the same class of setup errors.

Setup & credentials > Check again

```
pskit doctor
pskit validate
```
