from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file without overriding existing env vars."""
    if path is None:
        path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        cleaned_key = key.strip()
        cleaned_value = value.strip().strip('"').strip("'")
        if cleaned_key.endswith("PASSWORD"):
            cleaned_value = cleaned_value.replace(" ", "")
        if cleaned_key and cleaned_key not in os.environ:
            os.environ[cleaned_key] = cleaned_value
