from __future__ import annotations

import threading

_scrape_lock = threading.Lock()
_generation_lock = threading.Lock()
_current_generation = 0


def begin_scrape() -> int:
    """Acquire the global scrape lock and return a generation token."""
    _scrape_lock.acquire()
    with _generation_lock:
        global _current_generation
        _current_generation += 1
        return _current_generation


def end_scrape() -> None:
    _scrape_lock.release()


def cancel_current_scrape() -> None:
    """Invalidate any in-progress scrape so it stops after the current source."""
    with _generation_lock:
        global _current_generation
        _current_generation += 1


def is_cancelled(generation: int) -> bool:
    with _generation_lock:
        return generation != _current_generation
