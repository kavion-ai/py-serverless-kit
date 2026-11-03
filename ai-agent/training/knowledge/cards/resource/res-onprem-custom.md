# Other on-premises services (`type: custom`)

`custom` covers anything else functions talk to: an SMTP server, LDAP / Active Directory, an internal REST API, an
Elasticsearch cluster, a file share. pskit only hands `connection` values to handlers (`external: true` is required).

Not to be confused with the **custom driver** (`options.driver: custom`), which plugs your own class into a `queue` or
`storage` resource so it can trigger functions: see queue.md.

## The recipe

1. Find the service's address and a service account in its admin console.
2. Keep secrets in the host's environment (see README).
3. Put everything else, plus the secret's variable **name**, in `connection`.

## Example: SMTP server

Collect from the mail server's admin (Postfix, Exchange, Microsoft 365, SendGrid, ...): host, port (587 for STARTTLS,
465 for TLS), a user and its password or app password.

## Test

A resource key follows function-name rules. connection values are scalars. A key ending in _env names a variable, and the handler reads that variable from the environment. database, cache, and custom must set external to true. The Fields table in the resources page lists storage, queue, topic, database, cache, and custom. The schema also allows smtp.

Open the form on its own line:

Resources > + Add resource

Then open the generated guide:

Resources > How to use

```
pskit validate
pskit resources usage orders -p onprem -s dev
```

pskit resources send sends a test message or object for a queue, bucket, or topic. pskit resources send --list shows every resource. pskit invoke and pskit dev inject the same PSKIT_RESOURCE_* variables locally.
