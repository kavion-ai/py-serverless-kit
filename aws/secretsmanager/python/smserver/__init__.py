"""pskit's AWS Secrets Manager compatible server (Python, standard library only; Python 3.9+).

Modules, in dependency order (a module imports only modules above it):

``config``      settings from the environment (``SM_*``), constants, credentials, ``log``
``errors``      ``ApiError`` and the error helpers
``util``        time helpers
``ciphers``     AES-256, GCM, ChaCha20-Poly1305, AES-CBC-HMAC (standalone: loads without the package)
``keyring``     master keys and envelope encryption
``store``       the secrets in memory and on disk; ``db()`` returns the running store
``values``      helpers of the operations (versions, stages, tags, paging, filters)
``operations``  the Secrets Manager API operations and ``run()``
``sigv4``       AWS Signature Version 4 verification
``console``     the web console: sessions, sign-in throttling, static files under ``ui/``
``handler``     the HTTP handler
``main``        ``main()`` (serve, ``--check``, ``--rewrap``)
"""

VERSION = "1.0.0"
