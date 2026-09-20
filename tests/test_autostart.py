from __future__ import annotations

from services import autostart


def test_autostart_status_reports_platform() -> None:
    status = autostart.autostart_status()
    assert status.platform
    assert isinstance(status.supported, bool)
    assert isinstance(status.installed, bool)
