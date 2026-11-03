## In studio
1. Open this path:
Resources > + SMTP server

2. Open this path:
Resources > DNS guide

## In the terminal
1. Run:

```
pskit resources onprem create inbound-mail --service smtp --domains inbound.example.com --attach on-mail
```

## In code

Domains are required. Port 25 receives mail. Add an A record for the mail host and an MX record for the domain. Use a subdomain when the root MX is already in use.

## Create it In the studio: **Resources → + SMTP server .

| Field | | |---|---| | Resource key | e.g. `inbound-mail`; the trigger refers to it | | Domains | e.g. `inbound.example.com`. Mail to any address there (and at its subdomains) runs the functions | | Where | an SSH server (usually the functions' server) or this machine | | Port | `25` (other mail servers always connect to

## DNS records at your domain provider

After creating it, open **DNS guide** on the service (also under *How to use*). It lists the records with your values: | Type | Name (host) | Value | Why | |---|---|---|---| | A | `mail.inbound.example.com` | the server's **public** IP | the mail server's address | | MX | `inbound.example.com` | `10 mail.inbound.example.com` | mail for `*@inbound.example.com` goes there | - Most
