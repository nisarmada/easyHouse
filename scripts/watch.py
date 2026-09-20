from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.paths import ensure_user_data, get_sources_path
from services.watcher import DEFAULT_DEEP_INTERVAL_SEC, WatcherConfig, run_watcher


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Watch configured sources for new listings (bootstrap + fast polls)"
    )
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
    args = parser.parse_args()
    ensure_user_data()

    config = WatcherConfig(
        config_path=args.config or get_sources_path(),
        deep_interval_sec=args.deep_interval,
        skip_bootstrap=args.skip_bootstrap,
    )

    try:
        run_watcher(config)
    except ValueError as exc:
        parser.error(str(exc))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
