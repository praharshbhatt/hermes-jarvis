#!/usr/bin/env python3
"""Assemble the web flasher (ESP Web Tools) from a firmware build.

  scripts/make_flash_site.py --version 0.1.0 --factory path/to/firmware.factory.bin --out site/

Writes site/index.html, site/manifest.json and site/hermes-jarvis.factory.bin. Publish the folder (GitHub Pages in
CI). Flashing needs https, which Pages provides.
"""
import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

p = argparse.ArgumentParser()
p.add_argument("--version", required=True)
p.add_argument("--factory", required=True, type=Path, help="firmware.factory.bin from `esphome compile`")
p.add_argument("--out", required=True, type=Path)
a = p.parse_args()

a.out.mkdir(parents=True, exist_ok=True)
shutil.copy(a.factory, a.out / "hermes-jarvis.factory.bin")
manifest = {
    "name": "Hermes JARVIS",
    "version": a.version,
    "new_install_prompt_erase": True,  # lets people wipe a device that already holds a key (or old Wi-Fi settings)
    "builds": [{
        "chipFamily": "ESP32-S3",
        "parts": [{"path": "hermes-jarvis.factory.bin", "offset": 0}],
    }],
}
(a.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
html = (ROOT / "firmware" / "flash" / "index.html").read_text().replace("__VERSION__", a.version)
(a.out / "index.html").write_text(html)
print(f"wrote {a.out}/ ({(a.out / 'hermes-jarvis.factory.bin').stat().st_size // 1024} KiB firmware)")
