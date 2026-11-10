"""Reject release tags that disagree with source and installed metadata."""
import argparse
from importlib.metadata import version
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recharge_ai_task import __version__

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    args = parser.parse_args()
    declared = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    assert declared == __version__ == version("recharge-ai-task"), "Package versions disagree"
    if args.tag:
        assert args.tag == f"v{__version__}", f"Expected tag v{__version__}, got {args.tag}"
    print(f"Version verified: {__version__}")
