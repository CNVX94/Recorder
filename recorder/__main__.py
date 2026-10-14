"""`python -m recorder`: lo mismo que `daily` o `python recorder.py` (ver recorder/cli/app.py)."""
import sys

from .cli.app import arrancar


def main() -> int:
    return arrancar()


if __name__ == "__main__":
    sys.exit(main())
