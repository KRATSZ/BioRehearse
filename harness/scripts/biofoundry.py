#!/usr/bin/env python3
"""Reproducible local entry: python3 scripts/biofoundry.py [--accept]."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labscriptai.biofoundry.app import main

if __name__ == "__main__":
    main()
