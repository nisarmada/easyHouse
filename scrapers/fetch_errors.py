from __future__ import annotations


class FetchError(Exception):
    """Base class for HTTP fetch failures."""


class FetchNotFound(FetchError):
    """Resource not found (HTTP 404). Do not retry with alternate clients."""


class FetchRateLimited(FetchError):
    def __init__(self, message: str, *, retry_after_seconds: float) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class FetchUnavailable(FetchError):
    def __init__(self, message: str, *, retry_after_seconds: float) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class FetchCloudflareChallenge(FetchError):
    """Cloudflare interstitial or bot check page."""


class FetchHttpStatus(FetchError):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code
