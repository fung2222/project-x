#!/usr/bin/env python3
"""Compatibility entry point. Prefer ``python run.py pullback`` or master ``tick``."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from run import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["pullback", *sys.argv[1:]]))
