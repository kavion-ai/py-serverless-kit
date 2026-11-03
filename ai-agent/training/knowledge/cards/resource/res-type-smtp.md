# Resource: smtp

An smtp resource is the on-premises SMTP server that receives mail for your domains and runs functions. Use it when a message to `inbox@inbound.example.com` should start a handler. The events table marks smtp on on premises only.

`RESOURCE_TYPES` includes `smtp`, and `EVENT_RESOURCE_TYPES` includes it, so the schema allows the resource with `external` false or true. The Fields table in `docs/resources.md#fields` lists six types and omits smtp. The code wins. The create guide's example sets `external: true` and stores `host`, `port`, `domains`, and `hostname` in `connection`.

The server is a Node.js container from the on-prem catalog (`smtp`, port 25). It accepts mail for the domains you list and their subdomains, and it posts each message to the pskit host. It is receive-only. It is not an open relay.

In the studio, open:

Resources > + SMTP server

The form asks for a resource key, domains such as `inbound.example.com`, where it runs, port 25, and the functions to trigger. The same server is:

```
pskit resources onprem create inbound-mail --service smtp --domains inbound.example.com --attach on-mail --ssh deploy@203.0.113.10
```

The guide prints that command with a different SSH login. This card uses `deploy`. `203.0.113.10` is a documentation address. `--attach` adds the smtp trigger on that function. Deploy so the host learns the trigger.

The event is `smtp: {resource: inbound-mail}`, or the shorthand `smtp: inbound-mail`. `event.type` is `smtp`. `event.data` holds from, to, cc, subject, text, html, headers, and attachments. The same mail is also an Amazon SES-shaped object at `Records[0].ses`.

DNS is an A record for the mail host and an MX record for the domain. Open:

Resources > DNS guide

Keep the root MX when Microsoft 365 or Google Workspace already receives company mail, and use a subdomain. Allow inbound TCP 25. The largest mail defaults to 25 MB.

```
pskit resources onprem usage inbound-mail
pskit invoke -f on-mail -t smtp
```

Sources: `docs/smtp/README.md#create-it`, `docs/events.md#events-triggers`, `docs/resources.md#on-premises-drivers`, `src/py_serverless_kit/config/schema.py`
