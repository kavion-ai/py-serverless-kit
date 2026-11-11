"use strict";
// An AWS Secrets Manager compatible server (Node.js 18+, no dependencies). This file is the entry point only; the
// code is in ./lib (see ../ARCHITECTURE.md).
//
// boto3, the AWS SDKs (JavaScript v3, Java, Go, ...), the AWS CLI and pskit's getSecret() talk to it unchanged:
// point their endpoint at this server and sign with an access key / secret key it knows. Requests are checked with
// AWS Signature Version 4, exactly as AWS does, so a wrong secret key is refused.
//
// Settings (environment), the same as the Python server (../python/server.py):
//   SM_ACCESS_KEY_ID / SM_SECRET_ACCESS_KEY   the credentials clients sign with
//   SM_CREDENTIALS                            more credentials: id1:secret1,id2:secret2
//   SM_AUTH                                   sigv4 (default) or off (development only)
//   SM_PORT (4584), SM_BIND (0.0.0.0), SM_DATA_DIR (./data), SM_REGION (us-east-1), SM_ACCOUNT_ID (000000000000)
//   SM_UI (on), SM_UI_PASSWORD, SM_UI_DIR     the web console, an optional console password, and its files
//                                             (default <this dir>/ui, else <this dir>/../ui)
//   SM_MASTER_KEY                             encrypts values at rest: 32 random bytes in base64, key id "default"
//   SM_MASTER_KEYS, SM_MASTER_KEY_ID          more master keys (id1:key,id2:key; KmsKeyId picks one) and the id
//                                             used for secrets without a KmsKeyId (changing it rewraps on start)
//   SM_ENCRYPTION                             aes-256-gcm (default with a key), chacha20-poly1305, aes-256-cbc-hmac, off
//
// `node server.js --check` exits 0 when the server answers on /health (a container health check);
// `node server.js --rewrap` encrypts, decrypts or rewraps the file for the current settings and exits.

require("./lib/main").main(__dirname);
