#!/usr/bin/env python3
"""Point the local agent at a deployed easyHouse auth worker."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.paths import ensure_user_data, get_auth_config_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Auth worker base URL, e.g. https://easyhouse-auth.example.workers.dev")
    args = parser.parse_args()

    url = args.url.strip().rstrip("/")
    if not url.startswith("https://"):
        print("URL must start with https://", file=sys.stderr)
        return 1

    ensure_user_data()
    path = get_auth_config_path()
    path.write_text(json.dumps({"auth_url": url}, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass

    print(f"Saved auth URL to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
