"""pskit's Amazon SES compatible server (Python, standard library only; Python 3.9+).

Modules, in dependency order (a module imports only modules above it):

``config``      settings from the environment (``SES_*``), limits, credentials, ``log``
``errors``      ``ApiError`` and the error helpers
``util``        time, ids, address parsing
``rsa``         RSA keys (generate, DER / PEM, PKCS#1 v1.5 SHA-256 signatures) for DKIM
``dkim``        DKIM-Signature (relaxed/relaxed, rsa-sha256)
``dns``         a small DNS client (MX, TXT) for direct delivery and identity checks
``templates``   the template language (a Handlebars subset, as SES uses)
``mime``        builds messages (simple content, templates, attachments) and reads raw ones
``store``       identities, templates, configuration sets, suppression list, messages; ``db()``
``events``      message events (SES event publishing format) and the events webhook
``sender``      accepts a message: checks, quotas, suppression, simulator, DKIM, queue
``delivery``    the delivery worker: relay, direct MX or capture, retries, bounces
``identities``  identity verification and DKIM status checks (DNS)
``operations``  the API operations in the SES v2 shape (``OPERATIONS``, ``run()``), console extras
``query``       the SES v1 Query API (``Action=...``, XML answers) on top of ``operations``
``rest``        the SES v2 REST routes (``/v2/email/...``) on top of ``operations``
``sigv4``       AWS Signature Version 4 verification, SES SMTP passwords
``console``     the web console: sessions, sign-in throttling, static files under ``ui/``
``smtp``        the SMTP endpoint (AUTH PLAIN / LOGIN, STARTTLS) that sends like SendRawEmail
``handler``     the HTTP handler
``main``        ``main()`` (serve, ``--check``, ``--smtp-password``)
"""

VERSION = "1.0.0"
