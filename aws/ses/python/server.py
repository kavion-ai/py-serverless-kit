"""An Amazon SES compatible server (Python 3.9+, standard library only).

boto3 (``ses`` and ``sesv2``), the AWS SDKs, the AWS CLI, nodemailer's SES transport and any SMTP client talk to it
unchanged: point their endpoint at this server and sign with an access key / secret key it knows. Requests are
checked with AWS Signature Version 4, exactly as AWS does. Mail is queued, DKIM-signed and delivered through a relay
(smarthost), straight to the recipients' MX hosts, or kept for inspection (capture). A web console is served at
``/ui/``.

This file is the entry point only; the code is in the ``sesserver`` package next to it (see
``sesserver/__init__.py`` for the module map and ``sesserver/config.py`` for the settings). The Node.js server
(``../nodejs/server.js``) reads and writes the same data files, so you can switch between them.

``python server.py``            serve (HTTP API + console, and the SMTP endpoint)
``python server.py --check``    exit 0 when the server answers on ``/health`` (a container health check)
``python server.py --smtp-password``  print the SES SMTP password of ``SES_SECRET_ACCESS_KEY`` and exit
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sesserver.main import main  # noqa: E402 - after the path is set

if __name__ == "__main__":
    sys.exit(main())
