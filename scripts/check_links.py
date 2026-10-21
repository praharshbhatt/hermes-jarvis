#!/usr/bin/env python3
"""Check that relative links and #anchors in the Markdown files resolve. Run from anywhere: scripts/check_links.py"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def slug(heading: str) -> str:
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return re.sub(r" ", "-", s)


def anchors(path: Path) -> set[str]:
    out = set()
    in_code = False
    for line in path.read_text().splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and (m := re.match(r"#{1,6}\s+(.*)", line)):
            out.add(slug(m.group(1)))
    return out


bad = 0
for md in sorted(ROOT.rglob("*.md")):
    if any(part in (".venv", ".venv-fw", "upstream", "site", ".git", ".esphome", "node_modules", ".next", "out") for part in md.parts):
        continue
    for target in LINK.findall(md.read_text()):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path, _, frag = target.partition("#")
        dest = (md.parent / path).resolve() if path else md
        if not dest.exists():
            print(f"{md.relative_to(ROOT)}: broken link {target}")
            bad += 1
        elif frag and dest.suffix == ".md" and frag not in anchors(dest):
            print(f"{md.relative_to(ROOT)}: no heading for #{frag} in {dest.relative_to(ROOT)}")
            bad += 1
print("links ok" if not bad else f"{bad} broken")
sys.exit(1 if bad else 0)
