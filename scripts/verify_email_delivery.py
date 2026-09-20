#!/usr/bin/env python3
"""Verify signup/resend email delivery against a local SMTP sink."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db.db as dbmod
from auth.service import resend_verification, signup, verify_email
from db.db import get_connection, init_db
from notify.smtp_config import save_service_smtp
from tests.local_smtp_sink import LocalSmtpSink


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default="test@example.com", help="Recipient for the verification email")
    args = parser.parse_args()

    sink = LocalSmtpSink()
    sink.start()
    print(f"Local SMTP sink listening on 127.0.0.1:{sink.port}")

    with tempfile.TemporaryDirectory() as tmp:
        import os

        home = Path(tmp) / "home"
        home.mkdir()
        db_path = Path(tmp) / "verify-email.db"
        os.environ["EASYHOUSE_HOME"] = str(home)
        dbmod.DB_PATH = db_path

        save_service_smtp(
            host="127.0.0.1",
            port=sink.port,
            from_address="easyHouse <alerts@easyhouse.test>",
            username="",
            password="",
            use_tls=False,
        )

        conn = get_connection()
        init_db(conn)

        print(f"Signing up {args.email} …")
        signup_result = signup(conn, email=args.email, password="secretpass")
        if not signup_result["email_sent"]:
            print("FAIL: signup reported email_sent=false")
            return 1

        message = sink.wait_for_message(to_address=args.email, subject_contains="verification code")
        code = sink.extract_verification_code(message)
        print(f"Received verification email with code {code}")

        token = conn.execute("SELECT token FROM sessions").fetchone()["token"]
        delivered = len(sink._store.messages)
        resend_result = resend_verification(conn, token)
        if not resend_result["email_sent"]:
            print("FAIL: resend reported email_sent=false")
            return 1

        resent = sink.wait_for_message(
            to_address=args.email,
            subject_contains="verification code",
            timeout=5,
            after_count=delivered,
        )
        resent_code = sink.extract_verification_code(resent)
        print(f"Resend delivered a new code {resent_code}")

        verified = verify_email(conn, resent_code)
        if not verified["verified"]:
            print("FAIL: verification did not mark account as verified")
            return 1

    sink.stop()
    print("OK: verification email delivery works end-to-end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
