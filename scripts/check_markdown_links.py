"""Check local Markdown links without network access.

Usage:
    python scripts/check_markdown_links.py README.md docs/README.md docs/final

HTTP(S), mailto, data URLs, and anchor-only links are intentionally skipped.
Directories are scanned recursively. The command exits non-zero if a local
target is missing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote


LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+[\"'][^\"']*[\"'])?\)")
SKIPPED_SCHEMES = ("http://", "https://", "mailto:", "data:")


def markdown_files(paths: list[str]) -> list[Path]:
    files: set[Path] = set()
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.update(path.rglob("*.md"))
        elif path.suffix.lower() == ".md":
            files.add(path)
        else:
            raise FileNotFoundError(f"not a Markdown file or directory: {path}")
    return sorted(files)


def local_target(source: Path, raw_target: str) -> Path | None:
    target = unquote(raw_target.strip())
    if not target or target.startswith("#") or target.lower().startswith(SKIPPED_SCHEMES):
        return None
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None
    return (source.parent / target).resolve()


def check(files: list[Path]) -> list[tuple[Path, int, str, Path]]:
    broken: list[tuple[Path, int, str, Path]] = []
    for source in files:
        text = source.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in LINK_PATTERN.finditer(line):
                raw_target = match.group(1) or match.group(2)
                target = local_target(source, raw_target)
                if target is not None and not target.exists():
                    broken.append((source, line_number, raw_target, target))
    return broken


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Markdown files or directories")
    args = parser.parse_args()

    try:
        files = markdown_files(args.paths)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    broken = check(files)
    if broken:
        for source, line_number, raw_target, resolved in broken:
            print(f"{source}:{line_number}: {raw_target} -> MISSING {resolved}")
        print(f"FAILED: {len(broken)} broken local link(s) in {len(files)} Markdown file(s)")
        return 1

    print(f"OK: {len(files)} Markdown file(s), all local targets exist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
