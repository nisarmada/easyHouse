from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from services.scrape_runner import ScrapeResult, run_scrape


@dataclass
class Job:
    id: str
    status: str = "pending"
    created_at: str = field(default_factory=lambda: _now())
    finished_at: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start_scrape(
        self,
        *,
        source_id: str | None = None,
        max_pages: int | None = 1,
        full_sync: bool = False,
    ) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            params={
                "source_id": source_id,
                "max_pages": max_pages,
                "full_sync": full_sync,
            },
        )
        with self._lock:
            self._jobs[job.id] = job

        thread = threading.Thread(target=self._run, args=(job.id,), daemon=True)
        thread.start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def latest(self) -> Job | None:
        with self._lock:
            if not self._jobs:
                return None
            return max(self._jobs.values(), key=lambda job: job.created_at)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"

        try:
            results = run_scrape(
                source_id=job.params.get("source_id"),
                max_pages=job.params.get("max_pages"),
                full_sync=bool(job.params.get("full_sync")),
            )
            with self._lock:
                job.results = [_result_to_dict(result) for result in results]
                job.status = "completed"
                job.finished_at = _now()
        except Exception as exc:
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = _now()


def _result_to_dict(result: ScrapeResult) -> dict[str, Any]:
    return {
        "source_name": result.source_name,
        "parsed": result.parsed,
        "new_count": result.new_count,
        "removed_count": result.removed_count,
        "error": result.error,
    }
