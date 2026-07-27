#!/usr/bin/env python3
"""Run the Northern Expedition playtest web app."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.server import run


if __name__ == "__main__":
    run()
