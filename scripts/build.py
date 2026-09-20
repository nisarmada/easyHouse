#!/usr/bin/env python3
"""Build a standalone easyHouse executable with PyInstaller."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    spec_path = PROJECT_ROOT / "easyhouse.spec"
    subprocess.check_call(
        [sys.executable, "-m", "PyInstaller", str(spec_path), "--noconfirm"],
        cwd=PROJECT_ROOT,
    )
    dist_path = PROJECT_ROOT / "dist" / "easyhouse"
    print(f"\nBuilt standalone agent: {dist_path}")
    print("Run it with:")
    print(f"  {dist_path} --open-browser")


if __name__ == "__main__":
    main()
