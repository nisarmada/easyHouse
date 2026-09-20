#!/usr/bin/env python3
"""Run easyHouse as a single process: background watcher + local web dashboard."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.env import load_dotenv

load_dotenv(ROOT / ".env")

from config.paths import ensure_user_data, get_sources_path
from services.agent import AgentConfig, run_agent
from services.autostart import install_autostart, uninstall_autostart
from services.watcher import DEFAULT_DEEP_INTERVAL_SEC, WatcherConfig


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run easyHouse agent (watcher + web dashboard in one process)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Web dashboard host")
    parser.add_argument("--port", type=int, default=8080, help="Web dashboard port")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to sources JSON (default: ~/.easyhouse/config/sources.json)",
    )
    parser.add_argument(
        "--deep-interval",
        type=int,
        default=DEFAULT_DEEP_INTERVAL_SEC,
        help=f"Seconds between full sync scans (default: {DEFAULT_DEEP_INTERVAL_SEC}, 0=disable)",
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="Skip the initial full scrape (not recommended on first run)",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the dashboard in your default browser on startup",
    )
    parser.add_argument(
        "--install-autostart",
        action="store_true",
        help="Install easyHouse to start automatically at login, then exit",
    )
    parser.add_argument(
        "--uninstall-autostart",
        action="store_true",
        help="Remove easyHouse autostart entry, then exit",
    )
    args = parser.parse_args()

    ensure_user_data()

    if args.install_autostart:
        status = install_autostart()
        print(f"Autostart installed: {status.target}")
        return

    if args.uninstall_autostart:
        status = uninstall_autostart()
        print(f"Autostart removed (installed={status.installed})")
        return

    watcher = WatcherConfig(
        config_path=args.config or get_sources_path(),
        deep_interval_sec=args.deep_interval,
        skip_bootstrap=args.skip_bootstrap,
    )

    if args.open_browser:
        webbrowser.open(f"http://{args.host}:{args.port}")

    try:
        run_agent(AgentConfig(host=args.host, port=args.port, watcher=watcher))
    except ValueError as exc:
        parser.error(str(exc))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
