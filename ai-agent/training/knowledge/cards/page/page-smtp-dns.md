# Studio: SMTP DNS guide

How to open: Resources > DNS guide

Use it on an smtp resource row whose key matches an on-prem service. The button title is "DNS records to add at your domain provider (A, MX), the port, and the mail fields handlers get". On the On-prem services list, an smtp service's guide button is also labeled DNS guide. Both open `ServiceUsageDrawer` for that key. The drawer title is "How to use <key>".

What it is for: Show the DNS records that let other mail servers find this SMTP server. docs/smtp/README.md says you add two records, an A and an MX, at the domain provider, and that the DNS guide lists them with your values. The drawer body is markdown from `api.onpremUsage`. Copy guide copies that markdown. Show passwords and URLs is the same toggle as the other service usage drawer.

What you see: The doc's example table, for the domain inbound.example.com, is an A record whose name is mail.inbound.example.com and whose value is the server's public IP, and an MX record whose name is inbound.example.com and whose value is `10 mail.inbound.example.com`. The doc says the A record is the mail server's address, and the MX sends mail for addresses at that domain to it. Most providers want only the part before the root domain in the name field. The priority in the example is 10. Cloudflare should set the A record to DNS only, because the proxy does not carry mail. An optional TXT record in the doc is `v=spf1 -all` on a subdomain that only receives mail.

What you can do: Create the server first with
Resources > + SMTP server

The doc's create table lists Resource key, Domains, Where, Port 25, Trigger functions, and Advanced (pskit host URL and Largest mail in MB, default 25). The domains field help in the create drawer says mail for any other domain is refused, so the server is never an open relay. After DNS is published, the doc says to check with nslookup for the MX and for the mail host. Changes can take minutes or hours.

```
pskit resources onprem usage inbound-mail
```

Tips and limits: The doc says to use a subdomain such as inbound.example.com when the root domain already receives mail (Microsoft 365 or Google Workspace). Changing the root domain's MX would stop existing mailboxes receiving mail. Port 25 is what other mail servers connect to. The create form says to keep 25 unless something else uses it, and then to forward 25 to the port you chose.

Sources: `dashboard-ui/src/studio/views/Resources.tsx`, `dashboard-ui/src/studio/components/OnPremServices.tsx`, `docs/smtp/README.md#dns-records-at-your-domain-provider`, `docs/smtp/README.md#create-it`
