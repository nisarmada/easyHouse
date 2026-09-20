from __future__ import annotations

import os
import signal
import socket
import threading
from dataclasses import dataclass
from threading import Event

import uvicorn

from config.paths import ensure_user_data
from services.autostart import autostart_status
from services.watcher import WatcherConfig, run_watcher
from web.app import app


@dataclass
class AgentConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    watcher: WatcherConfig | None = None


WATCHER_JOIN_SEC = 3


def _log_agent_message(message: str) -> None:
    print(message, flush=True)


def _log_agent_error(message: str) -> None:
    print(message, flush=True)


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _ensure_port_available(host: str, port: int) -> None:
    if not _port_in_use(host, port):
        return

    status = autostart_status()
    lines = [
        f"Port {port} is already in use on {host}.",
        f"Check what is listening: lsof -i :{port}",
    ]
    if status.installed:
        lines.extend(
            [
                "",
                "easyHouse autostart is installed — launchd keeps restarting the agent when killed.",
                "Stop the background copy first:",
                "  .venv/bin/python scripts/agent.py --uninstall-autostart",
                "Then kill any leftover process:",
                f"  lsof -ti :{port} | xargs kill",
            ]
        )
    raise RuntimeError("\n".join(lines))


def _run_web_server(
    host: str,
    port: int,
    stop_event: Event,
    shutdown_count: list[int],
) -> None:
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    def _request_shutdown(*_args) -> None:
        shutdown_count[0] += 1
        stop_event.set()
        server.should_exit = True
        if shutdown_count[0] == 1:
            _log_agent_message("Shutting down — press Ctrl+C again to force quit.")
        else:
            _log_agent_message("Force quit.")
            os._exit(130)

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    server.run()


def _run_watcher_thread(config: WatcherConfig, stop_event: Event) -> None:
    try:
        run_watcher(config, stop_event=stop_event)
    except Exception as exc:
        _log_agent_error(f"Watcher stopped: {exc}")
        _log_agent_message("Dashboard remains available — fix settings and restart the agent.")


def run_agent(config: AgentConfig) -> None:
    """
    Run the easyHouse agent: local web dashboard and background watcher in one process.

    The web server runs on the main thread. The watcher runs in a background thread.
    Ctrl+C stops both; press Ctrl+C twice to force quit during a scrape.
    """
    ensure_user_data()
    watcher_config = config.watcher or WatcherConfig()
    stop_event = Event()
    shutdown_count = [0]

    dashboard_url = f"http://{config.host}:{config.port}"
    _log_agent_message("easyHouse agent starting")
    _ensure_port_available(config.host, config.port)
    _log_agent_message(f"Dashboard: {dashboard_url}")

    watcher_thread = threading.Thread(
        target=_run_watcher_thread,
        args=(watcher_config, stop_event),
        name="easyhouse-watcher",
        daemon=True,
    )
    watcher_thread.start()

    def _force_shutdown(*_args) -> None:
        shutdown_count[0] += 1
        stop_event.set()
        if shutdown_count[0] >= 2:
            _log_agent_message("Force quit.")
            os._exit(130)
        _log_agent_message("Shutting down — press Ctrl+C again to force quit.")

    try:
        _run_web_server(config.host, config.port, stop_event, shutdown_count)
    finally:
        stop_event.set()
        signal.signal(signal.SIGINT, _force_shutdown)
        signal.signal(signal.SIGTERM, _force_shutdown)
        watcher_thread.join(timeout=WATCHER_JOIN_SEC)
        _log_agent_message("easyHouse agent stopped.")
