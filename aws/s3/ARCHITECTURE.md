# aws/s3: code layout and contracts

Two interchangeable servers (Python, Node.js) that speak the Amazon S3 API and serve one web console. They read and
write the same data layout (see README), expose the same console API, and must behave the same: the test suite
(`tests/core/test_onprem_s3.py`) runs every test against both.

## Layout

```
aws/s3/
  python/
    server.py                 entry point only (python server.py [--check]); imports s3server.main
    s3server/                 standard library only, Python 3.9+
      __init__.py
      config.py               environment settings (S3_*), constants, credentials
      errors.py               S3Error and the error helpers (_denied, _invalid, ...)
      util.py                 time, XML, escaping, URI encoding helpers
      checksums.py            CRC32 / CRC32C / CRC64NVME / SHA checksums
      store.py                Bucket, Store (disk layout, atomic writes), create/delete bucket, get_store()/set_store()
      cors.py, lifecycle.py, objectlock.py, versions.py
      sigv4.py                Auth, SigV4 / SigV2 verification, presign(), streaming chunk signing
      payload.py              request bodies: Content-Length / chunked, aws-chunked decoding, receive(), copy_file()
      policy.py               the bucket policy engine (see "Bucket policies"): Context, evaluate_policy(), is_public_policy()
      access.py               ACLs, block public access, ownership controls, allowed() (the access decision), access summary
      objects.py              object fields from headers, response headers, conditions, ranges, tags, copy sources
      listing.py              key listings (prefix / delimiter paging), continuation tokens, <Contents>
      request.py              Request (incl. its policy Context), Response, authenticate(), need_auth()
      routes/                 service.py, bucket.py (incl. CORS preflight), config.py, objects.py, multipart.py, post.py,
                              website.py
      console/                session.py (login, cookie, CSRF), api.py (the /ui/api operations), static.py (/ui/ and
                              /ui/assets/ files), router.py (the /ui routes)
      http.py                 Handler and route(): the routing entry
      main.py                 main(), check()
  nodejs/
    server.js                 entry point only (node server.js [--check]); requires ./lib/main
    package.json
    lib/                      no npm packages, Node.js 18+; same module split as python/s3server (*.js)
  ui/
    index.html                the console shell: loads assets/css/*.css and assets/js/app.js (ES module)
    assets/
      css/                    theme.css (color tokens, light + dark), layout.css, components.css
      js/
        app.js                bootstraps: session check, router start
        core/                 api.js (fetch wrapper, CSRF), router.js (hash routes), state.js, dom.js (h()),
                              format.js (sizes, dates), s3.js (ARNs, URIs, XML <-> JSON for CORS/lifecycle/website)
        components/           reusable widgets: button, table (selectable, sortable, paged, filter), modal, toast,
                              tabs, breadcrumbs, page header, container/card, key-value list, form fields, alert,
                              dropdown menu, toggle, json editor, tag editor, copy button, status badge
        views/                one file per page (buckets, create-bucket, bucket, objects, upload, object, properties,
                              permissions, management, policy editor, ...)
        data/                 policy-examples.js, cors-examples.js
```

Shared modules must not import route or console code (one direction: config/errors/util -> store/sigv4 ->
access/policy -> routes/console -> http -> main; in Python: config/errors/util/checksums -> store -> objectlock/versions/
cors/lifecycle -> sigv4 -> payload -> policy -> access -> objects/listing -> request -> routes -> console -> http -> main,
with request.py importing http.Handler for type checking only). The store is reached through an accessor (`store.get_store()` /
`store.STORE` set by main), never copied into another module's globals.

## Console HTTP routes

| Route | Auth | |
|---|---|---|
| `GET /ui` | none | 302 to `/ui/` |
| `GET /ui/` | none | `ui/index.html` with `UI_HEADERS` |
| `GET /ui/assets/<path>` | none | static file under `ui/assets/`; 404 for anything else (no `..`, no backslash, no NUL, no path segment starting with `.`) |
| `GET /ui/session`, `POST /ui/login`, `POST /ui/logout` | | unchanged |
| `GET /ui/download` | session cookie | unchanged (in-page text previews only) |
| `PUT /ui/upload` | session + `X-S3-CSRF` | unchanged |
| `POST /ui/api/<Operation>` | session + `X-S3-CSRF` | JSON in, JSON out; errors are `{code, message}` with the S3 status |

The UI directory is `S3_UI_DIR` when set, else `<server dir>/ui`, else `<server dir>/../ui` (the repository layout).

Static files: `Content-Type` from the extension (`.js` `text/javascript; charset=utf-8`, `.css` `text/css; charset=utf-8`,
`.svg` `image/svg+xml`, `.png`, `.ico` `image/x-icon`, `.woff2` `font/woff2`, `.json` `application/json`, otherwise
`application/octet-stream`), `Cache-Control: no-cache`, `X-Content-Type-Options: nosniff`.

`UI_HEADERS` Content-Security-Policy:
`default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; frame-src 'self' blob:; frame-ancestors 'none'; form-action 'self'; base-uri 'none'`
(no inline scripts: everything is in `assets/js`).

## Console API changes (beyond the existing operations)

- **Presign** `{bucket, key, versionId?, expires, method: GET|PUT, host, scheme, disposition?: "inline"|"attachment", filename?}`
  When `disposition` is given for a GET, the URL carries `response-content-disposition` (`inline`, or
  `attachment; filename*=UTF-8''<percent-encoded filename>`, the filename defaulting to the key's last segment),
  included in the signed canonical query. The console's **Open** uses `disposition: "inline"` and `expires: 300`;
  **Download** uses `disposition: "attachment"` and `expires: 300`, exactly like the AWS console. These are normal
  presigned S3 URLs, so a bucket policy `Deny` stops them too.
- **EmptyBucket** `{bucket}` -> `{deleted: <number of versions and delete markers removed>, errors: [{key, versionId, code, message}]}`:
  removes every version and delete marker and aborts every unfinished multipart upload. Versions under object lock
  retention or legal hold are skipped and reported in `errors`.
- **ListBuckets** entries gain `access` and `publicBlock` (the four flags).
- **BucketInfo** gains `access`, `arn` (`arn:aws:s3:::<name>`), `ownership` (`BucketOwnerEnforced`,
  `BucketOwnerPreferred`, `ObjectWriter` or `""`), `websiteHosts` (`<bucket>.s3-website.<domain>` for each `S3_DOMAIN`),
  `account` (`S3_ACCOUNT_ID`).
- **ListVersions** accepts `delimiter` (`"/"`): then it returns `folders` (common prefixes) and only the versions of keys
  directly under `prefix`; the response is `{versions, folders, truncated}` (`folders` is `[]` without a delimiter).

`access` is `"public"` when an Allow statement of the policy is public and `RestrictPublicBuckets` is off, or the bucket
ACL grants AllUsers/AuthenticatedUsers READ and neither `IgnorePublicAcls` nor `BucketOwnerEnforced` applies;
otherwise `"not-public"` when all four block-public-access flags are on; otherwise `"objects-can-be-public"`.

## Object responses on the console's origin

The console and path-style object URLs share one origin. A path-style `GET` of an object (not virtual-hosted, not the
website endpoint) whose final `Content-Type` is HTML, XHTML, XML or SVG gets
`Content-Security-Policy: sandbox allow-scripts allow-forms allow-popups allow-modals allow-downloads`, so a page opened
from a bucket runs in an opaque origin and cannot use the console's session. Other types (images, PDF, video, text)
are served unchanged so browsers can show them inline.

## Bucket policies

Evaluated for every S3 API request on a bucket or object that names an action (both anonymous and signed requests,
presigned URLs included). Console `/ui/api` operations act as the account owner and are not evaluated.

1. Statements are matched on principal, action, resource and condition. Any matching `Deny` refuses the request
   (`403 AccessDenied`), for signed requests too. Exception: `s3:GetBucketPolicy`, `s3:PutBucketPolicy` and
   `s3:DeleteBucketPolicy` by a signed request are never denied (the owner can always repair the policy, like the
   AWS root user).
2. A signed request that no `Deny` matched is allowed (every key belongs to the bucket owner's account).
3. An anonymous request is allowed when an `Allow` matches (ignored when `RestrictPublicBuckets` is on), otherwise
   the ACL rules decide as before.

Principal: `"*"`, `{"AWS": "*"}`, or `{"AWS": [...]}` whose entries may be `*`, the account id, `arn:aws:iam::<account>:root`
(any signed request), an access key id, or `arn:aws:iam::<account>:user/<access key id>`. `NotPrincipal` matches every
requester not listed. Anonymous requests only match `*`.
Action / `NotAction` and Resource / `NotResource` support `*` and `?` wildcards (actions case-insensitive).

Condition operators: `StringEquals`, `StringNotEquals`, `StringEqualsIgnoreCase`, `StringNotEqualsIgnoreCase`,
`StringLike`, `StringNotLike`, `NumericEquals`, `NumericNotEquals`, `NumericLessThan`, `NumericLessThanEquals`,
`NumericGreaterThan`, `NumericGreaterThanEquals`, `DateEquals`, `DateNotEquals`, `DateLessThan`, `DateLessThanEquals`,
`DateGreaterThan`, `DateGreaterThanEquals`, `Bool`, `IpAddress`, `NotIpAddress` (IPv4 and IPv6 CIDR), `Null`, each with
an optional `IfExists` suffix and an optional `ForAnyValue:` / `ForAllValues:` prefix. Keys are case-insensitive.
All operators of a statement must hold (AND); a key's values are ORed. A missing key makes a positive operator false
and a negated operator (`...Not...`, `NotIpAddress`) true; `IfExists` makes a missing key true. Unknown operators make
the condition false.

Condition keys: `aws:SourceIp` (the TCP peer; `X-Forwarded-For`'s first address only when the peer is loopback),
`aws:SecureTransport` (`true` only when the peer is loopback and `X-Forwarded-Proto: https`), `aws:Referer`,
`aws:UserAgent`, `aws:CurrentTime`, `aws:EpochTime`, `aws:PrincipalType` (`Anonymous` / `Account`),
`aws:username` and `aws:userid` (the access key id, signed only), `aws:PrincipalAccount` (signed only),
`s3:authType` (`REST-HEADER`, `REST-QUERY-STRING`, `POST`), `s3:signatureversion` (`AWS4-HMAC-SHA256` / `AWS`),
`s3:prefix`, `s3:delimiter`, `s3:max-keys` (list requests), `s3:VersionId`, `s3:x-amz-acl`,
`s3:x-amz-server-side-encryption`, `s3:x-amz-storage-class`, `s3:x-amz-content-sha256`, `s3:ExistingObjectTag/<key>`.

`policyStatus.IsPublic` (and `access`) treat an Allow for anyone as public unless it is restricted by an `aws:SourceIp`,
`aws:SourceVpc`, `aws:SourceVpce`, `aws:SourceAccount`, `aws:SourceArn`, `aws:PrincipalAccount` or `aws:PrincipalOrgID`
condition.
