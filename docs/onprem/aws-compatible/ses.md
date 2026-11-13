# Amazon SES compatible server reference

Search terms: SES compatible server, sesv2 endpoint_url, SendEmail, SendRawEmail, SES SMTP password, DKIM signing,
mailbox simulator, suppression list, configuration set, relay, direct MX delivery, ses-cpp

`aws/ses` is an Amazon SES compatible server in two interchangeable implementations: **Python** (standard library
only) and **C++** (C++17 + OpenSSL). Both read and write the same data files and pass the same contract tests
(`tests/core/test_onprem_ses.py`). Creating it as a pskit service: [../services/ses.md](../services/ses.md). Running
it on its own and every setting: [aws/ses/README.md](../../../aws/ses/README.md).

## API coverage

| SES v2 (`sesv2`, REST JSON) | SES v1 (`ses`, Query XML) |
|---|---|
| SendEmail (Simple with attachments and headers, Raw, Template), SendBulkEmail | SendEmail, SendRawEmail, SendTemplatedEmail, SendBulkTemplatedEmail |
| CreateEmailIdentity (with BYODKIM), GetEmailIdentity, ListEmailIdentities, DeleteEmailIdentity | VerifyEmailIdentity, VerifyEmailAddress, VerifyDomainIdentity, VerifyDomainDkim, ListIdentities, ListVerifiedEmailAddresses, DeleteIdentity, DeleteVerifiedEmailAddress |
| PutEmailIdentityDkimAttributes, PutEmailIdentityDkimSigningAttributes, PutEmailIdentityMailFromAttributes, PutEmailIdentityFeedbackAttributes, PutEmailIdentityConfigurationSetAttributes | GetIdentityVerificationAttributes, GetIdentityDkimAttributes, SetIdentityDkimEnabled, GetIdentityMailFromDomainAttributes, SetIdentityMailFromDomain, SetIdentityFeedbackForwardingEnabled |
| Create / Get / Update / Delete / ListEmailTemplate(s), TestRenderEmailTemplate | CreateTemplate, GetTemplate, UpdateTemplate, DeleteTemplate, ListTemplates, TestRenderTemplate |
| Create / Get / Delete / ListConfigurationSet(s), Put…SendingOptions, …SuppressionOptions, …DeliveryOptions, …ReputationOptions, …TrackingOptions, event destinations | CreateConfigurationSet, DeleteConfigurationSet, ListConfigurationSets, DescribeConfigurationSet |
| GetAccount, PutAccountSendingAttributes, PutAccountSuppressionAttributes | GetSendQuota, GetSendStatistics, GetAccountSendingEnabled, UpdateAccountSendingEnabled |
| Put / Get / Delete / ListSuppressedDestination(s), TagResource, UntagResource, ListTagsForResource | |

Errors use the SES codes and HTTP statuses (`MessageRejected`, `NotFoundException`, `AlreadyExistsException`,
`TemplateDoesNotExist`, `ConfigurationSetDoesNotExist`, `LimitExceededException` / `Throttling`,
`SendingPausedException`, `SignatureDoesNotMatch`, `InvalidClientTokenId`, ...), so SDK error handling written for
SES works.

## How a message is handled

1. **Checks**, as SES makes them: account and configuration set sending enabled; the From address is a verified
   identity (the address, its domain or a parent domain); 1 to 50 recipients (verified ones only with
   `SES_SANDBOX=on`); size; the 24-hour quota and the sending rate.
2. **Build and sign**: simple content becomes a MIME message (text + HTML alternative, attachments); raw messages get
   CRLF line endings, lose their `Bcc` header, and get `Date` / `Message-ID` when missing. The message is DKIM-signed
   (`rsa-sha256`, `relaxed/relaxed`) with the From domain's key once its DKIM record is verified.
3. **Suppression**: recipients on the suppression list (for the reasons the account or the configuration set
   suppresses) are dropped with a `Bounce` event of subtype `OnAccountSuppressionList`.
4. **Queue and deliver**: `relay`, `direct` (MX hosts in preference order, STARTTLS when offered, required with the
   configuration set's `TlsPolicy: REQUIRE`) or `capture`. A 5xx answer bounces the recipient and adds it to the
   suppression list; a 4xx answer or a connection failure retries after 1, 5, 15, 30 and then every 60 minutes until
   `SES_RETRY_HOURS` (or the configuration set's `MaxDeliverySeconds`).
5. **Events**: `Send`, `Delivery`, `Bounce`, `Complaint`, `DeliveryDelay` in the message record, and to
   `SES_EVENTS_URL` in the SES event publishing format (filtered by the configuration set's enabled event
   destinations when it has some).

The **mailbox simulator** answers without sending: `success@`, `ooto@` (delivered), `bounce@` (hard bounce, not added
to the suppression list), `complaint@` (delivered and a complaint), `suppressionlist@` (bounce as if suppressed), all
`@simulator.amazonses.com`.

## SMTP endpoint

Port 2587 (`SES_SMTP_PORT`). `AUTH PLAIN` or `AUTH LOGIN` with the access key ID and the **SES SMTP password**:
`base64(0x04 + HMAC chain("AWS4"+secret, "11111111", region, "ses", "aws4_request", "SendRawEmail"))`, exactly as AWS
derives it, so `aws`-style credential scripts and SMTP settings pages work. The secret key itself is also accepted.
Each message goes through the same checks as SendRawEmail; the reply is `250 Ok <MessageId>`, or `554 Transaction
failed: ...` / `454 Throttling failure: ...` as on SES. Set `SES_TLS_CERT` / `SES_TLS_KEY` for STARTTLS and
`SES_SMTP_REQUIRE_TLS=on` to refuse AUTH before it.

## Identities, verification and DNS

A domain identity gets a 2048-bit RSA DKIM key (or yours, via `DkimSigningAttributes`), shown as one token: the
selector. Publish, at the domain's DNS provider:

| Record | Name | Value |
|---|---|---|
| DKIM (TXT) | `<selector>._domainkey.<domain>` | `v=DKIM1; k=rsa; p=<public key>` |
| Verification (TXT) | `_amazonses.<domain>` | the verification token (needed with `SES_VERIFY=dns` only, or use DKIM) |
| SPF (TXT) | `<domain>` | `v=spf1 a:<HELO name> ~all` (direct), or your relay's `include:` |
| DMARC (TXT) | `_dmarc.<domain>` | `v=DMARC1; p=none; rua=mailto:postmaster@<domain>` |

Unlike Amazon SES, DKIM is a TXT record with the key itself (pskit has no `dkim.amazonses.com` to point CNAMEs at).
The console lists the exact records and *Check DNS now*; pending records are looked up every 10 minutes for 72 hours.
`SES_VERIFY` decides when an identity may send: `auto` (at once), `dns` (when its records are found), `manual` (the
console's *Mark as verified*), `off` (any From address).

## Templates

The Handlebars subset SES templates use: `{{name}}`, `{{a.b}}`, `{{this}}`, `{{@index}}` / `@first` / `@last` /
`@key`, `{{{raw}}}`, `{{#if}}` / `{{else}}`, `{{#unless}}`, `{{#each}}` (arrays and objects), `{{#with}}`, comments.
`{{...}}` is HTML-escaped in the HTML part only; a missing value renders as nothing; a name not found on the current
object is looked up in the enclosing ones. Both implementations render byte-identically.

## Python or C++

Same API, settings, files and console. The Python server needs nothing but Python 3.9+. The C++ server uses less
memory and CPU under load (one native binary, a thread per connection); pskit compiles it inside a stock Alpine
container on the first start (`start.sh`, kept in the volume and rebuilt only when the sources change), or build the
multi-stage `cpp/Dockerfile` once and push it to your registry.
