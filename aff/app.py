"""Entry point for the window version:  python -m aff.app"""
from __future__ import annotations

import logging

from .logging_setup import setup_logging


def main() -> int:
    setup_logging(logging.INFO)
    from .ui.wizard import Wizard                  # imported late so logging is ready first
    Wizard().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
