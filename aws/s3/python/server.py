"""An Amazon S3 compatible server (Python, standard library only): ``python server.py [--check]``.

The code is the ``s3server`` package next to this file; see its docstring for the settings.
"""

import sys

from s3server.main import main

if __name__ == "__main__":
    sys.exit(main())
