# SES compatible server, C++

A drop-in replacement for the Python server (`../python/server.py`): the same `SES_*` settings, the SES v1 Query
API and v2 REST API, the SMTP endpoint, the web console (`../ui`) and the same data files under `SES_DATA_DIR`, so
the two can take turns on one data directory. C++17, the standard library, POSIX and OpenSSL; nothing else.

```sh
make                          # build/ses-server (g++ and the OpenSSL headers: apk add g++ make openssl-dev)
SES_SECRET_ACCESS_KEY=... build/ses-server
build/ses-server --check      # exit 0 when /health answers
build/ses-server --smtp-password
make clean
```

`make CXX=... CPPFLAGS=-I... LDFLAGS="-L... -Wl,-rpath,..."` builds with a compiler or OpenSSL outside the system
paths. The console files are found in `SES_UI_DIR`, else `ui` next to the binary or in the folders above it.

- `start.sh`: what pskit runs on a stock `alpine:3.20` (`/app` = this folder's `start.sh`, `Makefile`, `src/` and
  `../ui`): installs `g++ make openssl-dev` once, builds into `/data/.build` (again only when the sources change) and
  runs the server; `start.sh --check` is the health check.
- `Dockerfile`: a two-stage image (build from `aws/ses`: `docker build -f cpp/Dockerfile .`).

`src/` mirrors the Python modules (`config`, `util`, `json`, `rsa`, `dkim`, `dns`, `templates`, `mime`, `store`,
`events`, `sender`, `delivery`, `identities`, `operations`, `query`, `rest`, `sigv4`, `console`, `smtp`, `http`,
`main`, plus `net` for sockets and TLS). The contract tests are `tests/core/test_onprem_ses.py` (the `cpp` cases).
