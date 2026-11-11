"""An AWS Secrets Manager compatible server (Python 3.9+, standard library only).

boto3, the AWS SDKs (JavaScript v3, Java, Go, ...), the AWS CLI and pskit's ``get_secret()`` talk to it unchanged:
point their ``endpoint_url`` at this server and sign with an access key / secret key it knows. Requests are checked
with AWS Signature Version 4, exactly as AWS does, so a wrong secret key is refused. A web console is served at
``/ui/``.

This file is the entry point only; the code is in the ``smserver`` package next to it (see ``smserver/__init__.py``
for the module map and ``smserver/config.py`` for the settings). The Node.js server (``../nodejs/server.js``) reads
and writes the same data file, so you can switch between them.

``python server.py``            serve
``python server.py --check``    exit 0 when the server answers on ``/health`` (a container health check)
``python server.py --rewrap``   encrypt, decrypt or rewrap the data file for the current settings and exit
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smserver.main import main  # noqa: E402 - after the path is set

if __name__ == "__main__":
    sys.exit(main())
