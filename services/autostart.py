from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AutostartStatus:
    platform: str
    supported: bool
    installed: bool
    target: str | None = None


def _agent_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]

    agent_script = Path(__file__).resolve().parents[1] / "scripts" / "agent.py"
    return [sys.executable, str(agent_script)]


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.easyhouse.agent.plist"


def _linux_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "easyhouse-agent.service"


def _windows_bat_path() -> Path:
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / "easyhouse-agent.bat"


def autostart_status() -> AutostartStatus:
    platform = sys.platform
    if platform == "darwin":
        target = str(_macos_plist_path())
        return AutostartStatus(platform=platform, supported=True, installed=_macos_plist_path().exists(), target=target)
    if platform.startswith("linux"):
        target = str(_linux_unit_path())
        return AutostartStatus(platform=platform, supported=True, installed=_linux_unit_path().exists(), target=target)
    if platform == "win32":
        target = str(_windows_bat_path())
        return AutostartStatus(platform=platform, supported=True, installed=_windows_bat_path().exists(), target=target)
    return AutostartStatus(platform=platform, supported=False, installed=False)


def install_autostart() -> AutostartStatus:
    command = _agent_command()
    status = autostart_status()
    if not status.supported:
        raise RuntimeError(f"Autostart is not supported on {status.platform}")

    if status.platform == "darwin":
        plist_path = _macos_plist_path()
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "Label": "com.easyhouse.agent",
            "ProgramArguments": command,
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": str(Path.home() / ".easyhouse" / "agent.log"),
            "StandardErrorPath": str(Path.home() / ".easyhouse" / "agent.error.log"),
        }
        plist_path.write_bytes(plistlib.dumps(payload))
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist_path)], check=False, capture_output=True)
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)], check=True)
        return autostart_status()

    if status.platform.startswith("linux"):
        unit_path = _linux_unit_path()
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        exec_start = " ".join(_shell_quote(part) for part in command)
        unit_path.write_text(
            f"""[Unit]
Description=easyHouse rental watcher agent
After=network-online.target

[Service]
Type=simple
ExecStart={exec_start}
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
""",
            encoding="utf-8",
        )
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "easyhouse-agent.service"], check=True)
        return autostart_status()

    bat_path = _windows_bat_path()
    bat_path.parent.mkdir(parents=True, exist_ok=True)
    bat_path.write_text(
        "@echo off\r\n"
        f'start "" {" ".join(_shell_quote(part) for part in command)}\r\n',
        encoding="utf-8",
    )
    return autostart_status()


def uninstall_autostart() -> AutostartStatus:
    status = autostart_status()
    if not status.supported:
        raise RuntimeError(f"Autostart is not supported on {status.platform}")

    if status.platform == "darwin":
        plist_path = _macos_plist_path()
        if plist_path.exists():
            subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist_path)], check=False, capture_output=True)
            plist_path.unlink(missing_ok=True)
        return autostart_status()

    if status.platform.startswith("linux"):
        unit_path = _linux_unit_path()
        subprocess.run(["systemctl", "--user", "disable", "--now", "easyhouse-agent.service"], check=False)
        unit_path.unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        return autostart_status()

    _windows_bat_path().unlink(missing_ok=True)
    return autostart_status()


def _shell_quote(value: str) -> str:
    if sys.platform == "win32":
        if " " in value or '"' in value:
            return f'"{value.replace(chr(34), chr(92) + chr(34))}"'
        return value
    if not value:
        return "''"
    if all(ch not in " \t\r\n'\"\\$&|;<>()" for ch in value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"
