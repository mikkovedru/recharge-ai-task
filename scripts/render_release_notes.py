"""Render repository-relative notes for the separate GitHub Release body."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def render(source: Path, *, repository: str, ref: str) -> str:
    source = source.resolve()
    def absolute(target, *, image=False):
        parts = urlsplit(target)
        if parts.scheme or parts.netloc or target.startswith("#"):
            return target
        path = (source.parent / parts.path).resolve()
        relative = path.relative_to(ROOT)
        if not path.is_file():
            raise FileNotFoundError(path)
        prefix = (f"https://raw.githubusercontent.com/{repository}/{quote(ref, safe='')}" if image
                  else f"https://github.com/{repository}/blob/{quote(ref, safe='')}")
        result = prefix + "/" + quote(relative.as_posix(), safe="/")
        if parts.fragment:
            result += "#" + parts.fragment
        return result
    text = source.read_text(encoding="utf-8")
    text = re.sub(r'(<img\b[^>]*\bsrc=")([^"]+)(")',
                  lambda m: m[1] + absolute(m[2], image=True) + m[3], text)
    text = re.sub(r'(!?\[[^\]]*\]\()([^)]+)(\))',
                  lambda m: m[1] + absolute(m[2], image=m[1].startswith("!")) + m[3], text)
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "docs/2026-11-09_release-notes-1.0.md")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(args.source, repository=args.repository, ref=args.ref), encoding="utf-8")
