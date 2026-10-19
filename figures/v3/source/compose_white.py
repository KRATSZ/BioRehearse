#!/usr/bin/env python3
"""Composite v3 transparent renders on white for manuscript previews.

The transparent PNGs remain authoritative.  This script only creates a white
background derivative and a small hash manifest for figure assembly.
"""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()

source = Path(args.input)
target = Path(args.output)
target.mkdir(parents=True, exist_ok=True)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


records = []
for path in sorted(source.glob("*.png")):
    image = Image.open(path).convert("RGBA")
    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
    background.alpha_composite(image)
    output = target / path.name
    background.convert("RGB").save(output, format="PNG", optimize=True)
    records.append({"source": path.name, "source_sha256": digest(path), "white_png": output.name, "white_sha256": digest(output), "size_px": list(image.size)})

(target / "white-composites.json").write_text(json.dumps({"schema": "biorehearse.v3.white-composites/1", "records": records}, indent=2) + "\n")
