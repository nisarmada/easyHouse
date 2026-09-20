#!/usr/bin/env python3
"""Save SMTP settings and verify that easyHouse can send email."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from notify.email import send_service_email
from notify.smtp_config import load_service_smtp_config, save_service_smtp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("EASYHOUSE_SMTP_HOST", "smtp.gmail.com"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("EASYHOUSE_SMTP_PORT", "587")))
    parser.add_argument("--from-address", default=os.environ.get("EASYHOUSE_SMTP_FROM"))
    parser.add_argument("--username", default=os.environ.get("EASYHOUSE_SMTP_USER"))
    parser.add_argument("--password", default=os.environ.get("EASYHOUSE_SMTP_PASSWORD"))
    parser.add_argument("--to", help="Address to send the test email to (defaults to username)")
    parser.add_argument("--no-tls", action="store_true")
    args = parser.parse_args()

    if not args.from_address or not args.username or not args.password:
        print(
            "Usage:\n"
            "  configure_email.py \\\n"
            "    --from-address 'easyHouse <you@gmail.com>' \\\n"
            "    --username you@gmail.com \\\n"
            "    --password YOUR_GMAIL_APP_PASSWORD\n\n"
            "Or set EASYHOUSE_SMTP_FROM, EASYHOUSE_SMTP_USER, and EASYHOUSE_SMTP_PASSWORD.",
            file=sys.stderr,
        )
        return 2

    if not args.from_address:
        args.from_address = f"easyHouse <{args.username}>"

    save_service_smtp(
        host=args.host,
        port=args.port,
        from_address=args.from_address,
        username=args.username,
        password=args.password,
        use_tls=not args.no_tls,
    )
    config = load_service_smtp_config()
    if config is None:
        print("FAIL: SMTP settings were not saved correctly", file=sys.stderr)
        return 1

    to_address = args.to or args.username
    print(f"Sending test email to {to_address} …")
    send_service_email(
        to_address=to_address,
        subject="easyHouse: test email",
        plain_body="easyHouse email delivery is configured.",
        html_body="<p>easyHouse email delivery is configured.</p>",
        config=config,
    )
    print("OK: test email sent — check your inbox")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
