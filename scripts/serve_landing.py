#!/usr/bin/env python3
"""Deprecated: landing page is served by the agent at http://127.0.0.1:8080/."""

from __future__ import annotations

import sys


def main() -> None:
    print("The landing page is now served by the agent at http://127.0.0.1:8080/")
    print("Run: python scripts/agent.py --open-browser")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
