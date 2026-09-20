from __future__ import annotations

import re
import smtpd
import asyncore
import threading
import time
from email import message_from_bytes
from email.policy import default


class _CaptureServer(smtpd.SMTPServer):
    def __init__(self, localaddr, remoteaddr, handler) -> None:
        super().__init__(localaddr, remoteaddr)
        self._handler = handler

    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        self._handler.store(data, rcpttos)


class _MessageStore:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []
        self._lock = threading.Lock()

    def store(self, data: bytes, rcpttos: list[str]) -> None:
        parsed = message_from_bytes(data, policy=default)
        plain_part = parsed.get_body(preferencelist=("plain",))
        html_part = parsed.get_body(preferencelist=("html",))
        with self._lock:
            self.messages.append(
                {
                    "subject": str(parsed.get("Subject", "")),
                    "to": ", ".join(rcpttos),
                    "plain": plain_part.get_content() if plain_part else "",
                    "html": html_part.get_content() if html_part else "",
                }
            )


class LocalSmtpSink:
    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self._store = _MessageStore()
        self._server = _CaptureServer((host, port), None, self._store)
        self.port = int(self._server.socket.getsockname()[1])
        self._thread = threading.Thread(
            target=asyncore.loop,
            kwargs={"map": self._server._map, "timeout": 0.5},
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()
        time.sleep(0.1)

    def stop(self) -> None:
        try:
            asyncore.close_all(map=self._server._map, ignore_all=True)
        except OSError:
            pass

    def wait_for_message(
        self,
        *,
        to_address: str | None = None,
        subject_contains: str = "",
        timeout: float = 5.0,
        after_count: int = 0,
    ) -> dict[str, str]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self._store.messages) > after_count:
                for message in self._store.messages[after_count:]:
                    if to_address and to_address not in message["to"]:
                        continue
                    if subject_contains and subject_contains not in message["subject"]:
                        continue
                    return message
            time.sleep(0.05)
        raise TimeoutError("Timed out waiting for email delivery")

    @staticmethod
    def extract_verification_code(message: dict[str, str]) -> str:
        for body in (message.get("plain", ""), message.get("html", "")):
            match = re.search(r"\b(\d{6})\b", body)
            if match:
                return match.group(1)
        raise ValueError("No 6-digit verification code found in email body")
