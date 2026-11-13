#!/bin/sh
# pskit's Amazon SES compatible server, C++, on a stock alpine image: /app holds this file, Makefile, src/ and ui/.
# Installs the compiler once, builds into the data volume (again only when the sources change) and runs the server.
#   sh /app/start.sh            build if needed, then serve
#   sh /app/start.sh --check    the container health check (exit 0 when /health answers)
set -e

APP="$(cd "$(dirname "$0")" && pwd)"
BUILD="${SES_BUILD_DIR:-${SES_DATA_DIR:-/data}/.build}"
BIN="$BUILD/ses-server"

if [ "$1" = "--check" ]; then
  [ -x "$BIN" ] || exit 1
  exec "$BIN" --check
fi

# What the build depends on: the sources, the Makefile and the system it is built on.
HASH="$( (cat "$APP/Makefile"; find "$APP/src" -type f | sort | xargs cat; cat /etc/alpine-release 2>/dev/null; uname -m) \
  | sha256sum | cut -d' ' -f1)"

if [ ! -x "$BIN" ] || [ "$(cat "$BUILD/.hash" 2>/dev/null)" != "$HASH" ]; then
  if ! command -v g++ >/dev/null 2>&1 || ! command -v make >/dev/null 2>&1     || ! echo '#include <openssl/ssl.h>' | g++ $CPPFLAGS -E -x c++ - >/dev/null 2>&1; then
    echo "ses: installing the compiler (g++ make openssl-dev)"
    apk add --no-cache g++ make openssl-dev
  fi
  echo "ses: building the server into $BUILD"
  mkdir -p "$BUILD"
  rm -rf "$BUILD/obj" "$BIN"
  make -C "$APP" BUILD="$BUILD" -j"$(nproc 2>/dev/null || echo 2)"
  echo "$HASH" > "$BUILD/.hash"
fi

# A container recreated from the stock image keeps the binary (in the volume) but not the libraries it links.
if command -v apk >/dev/null 2>&1 && ldd "$BIN" 2>&1 | grep -q -e "not found" -e "Error loading"; then
  echo "ses: installing the runtime libraries (libstdc++ openssl)"
  apk add --no-cache libstdc++ openssl
fi

if [ -z "$SES_UI_DIR" ] && [ -f "$APP/ui/index.html" ]; then
  export SES_UI_DIR="$APP/ui"
fi
exec "$BIN" "$@"
