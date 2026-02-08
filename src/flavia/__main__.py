"""Allow running as python -m flavia."""

import sys

from flavia.cli import main

if __name__ == "__main__":
    sys.exit(main())
