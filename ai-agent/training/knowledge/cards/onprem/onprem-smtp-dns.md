## DNS records at your domain provider

After creating it, open **DNS guide** on the service (also under *How to use*). It lists the records with your values:

| Type | Name (host) | Value | Why |
|---|---|---|---|
| A | `mail.inbound.example.com` | the server's **public** IP | the mail server's address |
| MX | `inbound.example.com` | `10 mail.inbound.example.com` | mail for `*@inbound.example.com` goes there |

- Most providers want only the part before your root domain in *Name*: `mail.inbound` and `inbound` for
  `example.com`, or `@` for the root domain itself. `10` is the MX priority; some providers have a separate field for it.
- **Cloudflare**: set the A record to *DNS only* (grey cloud). The proxy does not carry mail.
- Optional, for a subdomain that only receives mail: `TXT inbound "v=spf1 -all"`. This says the subdomain never sends
  mail, so nobody can send spoofed mail from it.
- Check the records with `nslookup -type=mx inbound.example.com` and `nslookup mail.inbound.example.com`. Changes show
  up after a few minutes, sometimes hours.
