# aws/ses: code layout and contracts

Two interchangeable servers (Python, C++) that speak the Amazon SES v1 and v2 APIs, run an SES-style SMTP endpoint
and serve one web console. They read and write the same data files and must behave the same: the test suite
(`tests/core/test_onprem_ses.py`) runs every server test against both, and `test_data_survives_a_restart_and_is_shared`
runs them one after the other on one data folder.

## Layout

```
aws/ses/
  python/
    server.py                 entry point only (python server.py [--check | --smtp-password]); runs sesserver.main
    sesserver/                standard library only, Python 3.9+ (module map in __init__.py)
      config.py               environment settings (SES_*), limits, credentials, log()
      errors.py               ApiError: one error, with its v2 code and its v1 (Query) code
      util.py                 time, message ids, address parsing
      rsa.py                  RSA keys in pure Python: generate, DER (PKCS#1 / PKCS#8 / SPKI), PKCS#1 v1.5 SHA-256
      dkim.py                 DKIM-Signature (relaxed/relaxed, rsa-sha256), and verify() for the tests
      dns.py                  a small DNS client (MX, TXT over UDP, TCP when truncated)
      templates.py            the Handlebars subset of SES templates
      mime.py                 builds messages (simple content, attachments) and reads raw ones
      store.py                ses.json + messages/<id>.json / .eml; db()
      events.py               message events, the SES event publishing format, the SES_EVENTS_URL webhook
      sender.py               accept(): every check before a MessageId, DKIM, suppression, the queue
      delivery.py             the worker: relay / direct (MX) / capture, simulator, retries, bounces
      identities.py           verification modes, DKIM keys and DNS checks, the records to publish
      operations.py           every operation in the SES v2 shape (OPERATIONS), plus the console-only ones
      query.py                SES v1 Query API (Action=..., XML) on top of operations
      rest.py                 SES v2 REST routes (/v2/email/...) on top of operations
      sigv4.py                SigV4 verification (path encoded twice, as for every service but S3), SMTP passwords
      console.py              console sign-in, throttling, sessions, static files
      smtp.py                 the SMTP endpoint (AUTH PLAIN / LOGIN, STARTTLS)
      handler.py              the HTTP handler
      main.py                 main(): HTTP server, SMTP server, delivery worker, DNS re-checks
  cpp/
    Makefile                  build/ses-server (BUILD=, CXX=, CPPFLAGS=, LDFLAGS= can be set); -lssl -lcrypto
    start.sh                  pskit's entry point in a stock alpine image: apk add the compiler once, build into
                              $SES_DATA_DIR/.build (again only when src/ or the Makefile change), exec the server
    Dockerfile                multi-stage: build on alpine, run on alpine with libstdc++ and openssl only
    src/                      C++17; the same modules as sesserver (*.cpp / *.hpp), plus json (parser and writer),
                              http (the HTTP/1.1 server) and net (sockets and OpenSSL TLS, client and server)
  ui/
    index.html                the console shell: assets/css/*.css and assets/js/app.js (ES module)
    assets/
      css/                    theme.css (tokens, light + dark), layout.css, components.css, ses.css
      js/
        app.js                bootstrap: session check, shell, routes
        core/                 api.js (fetch + X-SES-CSRF + errors), dom.js (h()), router.js, state.js, format.js,
                              icons.js, theme.js, mime.js (reads RenderedTemplate)
        components/           reusable widgets, one per file (table, modal, tabs, charts, html-preview, ...)
        views/                one file per page: account, identities, identity-detail, send, messages,
                              message-detail, templates, config-sets, suppression, smtp, login
```

Python modules depend in one direction, top to bottom in the list above. The store is reached through `store.db()`.
In the UI, `components/` never import `views/`, views reach the server only through `core/api.js`, every server string
is rendered with `textContent`, and message / template HTML is shown only in an `<iframe sandbox="">` made from a
`blob:` URL (no scripts, no same origin).

## Contracts both servers keep

- **Settings**: the `SES_*` variables in `python/sesserver/config.py` (and the README table), same defaults.
- **Data files** under `SES_DATA_DIR`, written atomically (temp file + rename) with mode 600:
  - `ses.json`: `{format: 1, account, identities, templates, configuration_sets, suppressed}`. DKIM private keys are
    base64 DER PKCS#1, public keys base64 SubjectPublicKeyInfo.
  - `messages/<id>.json`: `MessageId`, `Timestamp`, `Source`, `From`, `MailFrom`, `Destinations`, `Recipients`
    (`{address: {Status, Attempts, NextAttempt, Response, ...}}`), `Events`, `Status`, ... ; `messages/<id>.eml`:
    the message as sent (CRLF, DKIM-signed).
  - Timestamps are epoch seconds with milliseconds.
- **APIs**: the v2 REST routes in `rest.py`, the v1 actions in `query.py`, the console routes below, the same error
  codes and statuses. Responses carry epoch-second timestamps (v2, console) or ISO 8601 (v1 XML).
- **Templates** render byte-identically (escaping, JavaScript-style number text, scope lookup, truthiness).
- **MIME** need not be byte-identical, but both send 7-bit safe bodies (quoted-printable or base64), RFC 2047
  subjects, `multipart/alternative` for text + HTML and `multipart/mixed` with attachments.
- **SMTP replies**: `250 Ok <MessageId>`, `535 5.7.8` for a bad login, `554 Transaction failed: ...`,
  `454 Throttling failure: ...`.

## Console HTTP routes

| Route | Auth | |
|---|---|---|
| `GET /ui`, `GET /` | none | 302 to `/ui/` |
| `GET /ui/` | none | `ui/index.html` with the page headers below |
| `GET /ui/assets/<path>` | none | a file under `ui/assets/`; 404 for anything else (no `..`, backslash, NUL, empty or hidden segment) |
| `GET /ui/session` | cookie | `{authenticated, user, auth, csrf, password_login}` |
| `POST /ui/login` | none | `{user, password}` -> `ses_session` cookie and `{csrf}`; 10 failures in 5 minutes lock an address out (429) |
| `POST /ui/logout` | cookie | ends the session |
| `POST /ui/api/<Operation>` | cookie + `X-SES-CSRF` | an operation of `operations.py` (v2 JSON shapes), errors `{__type, message}` |

Console-only operations: `ListMessages`, `GetMessage`, `DeleteMessage`, `RetryMessage`, `CheckEmailIdentity`,
`SetEmailIdentityVerified`, `GetEmailIdentityDnsRecords`, `GetServerInfo`, `GetStatistics`, `GetSmtpCredentials`.

The page's Content-Security-Policy: `default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline';
connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; frame-src blob:; frame-ancestors 'none';
form-action 'self'; base-uri 'none'`.

## Deployment by pskit

`src/py_serverless_kit/core/onprem_ses.py` copies the server (Python: `server.py` + `sesserver/`; C++: `start.sh`,
`Makefile`, `src/`) and `ui/` into `/app` of a stock `python:3.12-alpine` / `alpine:3.20` container, publishes 4579
(API, console) and 2587 (SMTP), and keeps `/data` in a volume. Never name a folder `data` in this tree: the copy, the
`.gitignore` and the `.dockerignore` skip it.

## Changing things

- A new operation: `operations.py` and `cpp/src/operations.cpp` (plus a route in `rest.py` / `rest.cpp` or an action
  in `query.py` / `query.cpp`), a test in `tests/core/test_onprem_ses.py`, and the API table in
  `docs/onprem/aws-compatible/ses.md`.
- A new setting: `config.py` and `cpp/src/config.cpp`, the README's settings table, and `core/onprem_ses.py` if pskit
  should set it.
- Run the suite on Linux (or WSL) so the C++ cases run: `make -C aws/ses/cpp && pytest tests/core/test_onprem_ses.py`.
