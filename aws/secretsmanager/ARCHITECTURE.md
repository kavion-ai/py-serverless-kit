# aws/secretsmanager: code layout and contracts

Two interchangeable servers (Python, Node.js) that speak the AWS Secrets Manager API and serve one web console. They
read and write the same data file (`secretsmanager.json`, see README), expose the same console API, and must behave the
same: the test suite (`tests/core/test_onprem_secretsmanager.py`) runs every server test against both.

## Layout

```
aws/secretsmanager/
  python/
    server.py                 entry point only (python server.py [--check | --rewrap]); runs smserver.main
    smserver/                 standard library only, Python 3.9+
      __init__.py             VERSION and the module map
      config.py               environment settings (SM_*), limits, credentials, log()
      errors.py               ApiError, not_found(), invalid(), bad_request()
      util.py                 now(), today()
      ciphers.py              AES-256, GCM, ChaCha20-Poly1305, AES-CBC-HMAC, HKDF (loads on its own: no package imports)
      keyring.py              master keys, envelope encryption (seal / open / rewrap), aad_of()
      store.py                Store (memory + atomic JSON file), db() / set_store()
      values.py               versions, staging labels, tags, paging, ListSecrets filters, response shapes
      operations.py           the API operations (OPERATIONS), READS, run()
      sigv4.py                verify_sigv4()
      console.py              console sign-in, throttling, sessions, static files (index.html, assets/)
      handler.py              the HTTP handler (API, /health, /ui/...)
      main.py                 main(), check()
  nodejs/
    server.js                 entry point only (node server.js [--check | --rewrap]); require("./lib/main").main(__dirname)
    package.json
    lib/                      no npm packages, Node.js 18+; the same split as smserver (*.js; crypto.js = ciphers)
  ui/
    index.html                the console shell: loads assets/css/*.css and assets/js/app.js (ES module)
    assets/
      css/                    theme.css (color tokens, light + dark), layout.css (shell), components.css
      js/
        app.js                bootstrap: session check, shell, router
        core/                 api.js (fetch + CSRF + errors), dom.js (h() builder), router.js (hash routes),
                              state.js (session + events), format.js (dates), icons.js (inline SVG), snippets.js
        components/           reusable widgets, one per file (table, modal, flash, tabs, wizard, editors, ...)
        views/                one file per page (login, secrets list, store-secret wizard, secret detail, ...)
```

Modules depend in one direction: `config` / `errors` / `util` -> `ciphers` -> `keyring` -> `store` -> `values` ->
`operations` -> `sigv4` / `console` -> `handler` -> `main`. The store is reached through `store.db()` (Python) or the
`store` module (Node), never copied into another module's globals.

In the UI, `components/` never import `views/`, and views talk to the server only through `core/api.js`. Every string
from the server is rendered with `textContent` (the `h()` builder); secret values never go into URLs, logs or browser
storage, and are masked until the user retrieves them.

## Deployment

pskit (`src/py_serverless_kit/core/onprem_secretsmanager.py`) copies the server's folder (without the Dockerfile and
caches) and `ui/` into `/app` of a stock `python:3.12-alpine` / `node:22-alpine` container:

```
/app/server.py  /app/smserver/...  /app/ui/index.html  /app/ui/assets/...      (Python)
/app/server.js  /app/package.json  /app/lib/...  /app/ui/...                    (Node.js)
```

The Dockerfiles build the same layout (build from `aws/secretsmanager`).

## Console HTTP routes

| Route | Auth | |
|---|---|---|
| `GET /ui`, `GET /` | none | 302 to `/ui/` |
| `GET /ui/` | none | `ui/index.html` with the page headers below |
| `GET /ui/assets/<path>` | none | a file under `ui/assets/`; 404 for anything else (no `..`, no backslash, no NUL, no empty segment, no segment starting with `.`, must resolve inside `assets/`) |
| `GET /ui/session` | cookie | `{authenticated, user, auth, csrf, password_login}` |
| `POST /ui/login` | none | `{user, password}` -> sets the `sm_session` cookie, returns `{csrf}`; 10 failures in 5 minutes lock an address out (429) |
| `POST /ui/logout` | cookie | ends the session |
| `POST /ui/api/<Operation>` | cookie + `X-SM-CSRF` | the Secrets Manager operation, same JSON in and out; errors `{__type, message}` |

The UI folder is `SM_UI_DIR` when set, else `ui` next to the server's entry point, else `../ui` (the repository).

Page headers: `Cache-Control: no-store`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer` and
`Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'`
(no inline scripts: everything is in `assets/js`).

Static files: `Content-Type` from the extension (`.js` `text/javascript; charset=utf-8`, `.css` `text/css; charset=utf-8`,
`.svg`, `.png`, `.ico`, `.woff2`, `.json`, `.html`, otherwise `application/octet-stream`), `Cache-Control: no-cache`,
`X-Content-Type-Options: nosniff`.

## Changing things

- A new API operation: `operations.py` and `lib/operations.js` (plus `READS` if it changes nothing), a test in
  `tests/core/test_onprem_secretsmanager.py` that runs on both servers, and the README's operations table.
- A new setting: `config.py` and `lib/config.js`, the README's settings table and
  `docs/onprem/aws-compatible/secretsmanager.md`.
- A new console widget: a file in `ui/assets/js/components/`, styles in `components.css` using the tokens of
  `theme.css` (never raw colors), so light and dark mode keep working.
