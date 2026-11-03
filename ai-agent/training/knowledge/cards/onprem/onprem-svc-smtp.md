# On-premises service: SMTP server (receive mail, Node.js)

The catalog id is `smtp`. Kind is service. Group is Mail. Image is node:22-alpine. Published port is 25. Extra ports are none. Roles are smtp. Backup is no. Persistent data is yes. Auth is no. Default user is pskit. Companion UI is none. Web UI names are none. GUI login choices are none.

Catalog notes: Receives mail for your domains and runs the functions attached to it with the mail: from, to, cc, subject, text, html, headers and attachments (also in the Amazon SES event shape). Never relays. After creating it, How to use lists the DNS records (A, MX) to add at your domain provider.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-smtp --service smtp
pskit resources onprem status sample-smtp
```

pskit resources onprem usage sample-smtp prints how to connect. pskit resources onprem logs sample-smtp shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
