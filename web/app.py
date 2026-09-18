from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config.load import DEFAULT_SOURCES_PATH, ensure_sources_config, load_sources, save_platforms
from config.search import load_search, save_search
from config.search_service import get_active_search
from db.db import get_connection, init_db
from db.queries import get_dashboard_stats, get_listing, list_listings
from geo.geocode import geocode_city
from notify.email import load_email_config
from web.jobs import JobManager

STATIC_DIR = Path(__file__).resolve().parent / "static"
job_manager = JobManager()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_sources_config()
    yield


app = FastAPI(title="easyHouse", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class PlatformPayload(BaseModel):
    name: str
    type: str
    enabled: bool = True


class SourcesUpdatePayload(BaseModel):
    sources: list[PlatformPayload]


class SearchUpdatePayload(BaseModel):
    city: str = Field(min_length=1)
    radius_km: float = Field(ge=0.5, le=100)


class ScrapePayload(BaseModel):
    source_id: Optional[str] = None
    max_pages: Optional[int] = 1
    full_sync: bool = False


def _job_to_dict(job) -> dict[str, Any]:
    return {
        "id": job.id,
        "status": job.status,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "params": job.params,
        "results": job.results,
        "error": job.error,
    }


def _search_response(conn) -> dict[str, Any]:
    return get_active_search(conn).to_dict()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/search")
def api_get_search() -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    return _search_response(conn)


@app.put("/api/search")
def api_update_search(payload: SearchUpdatePayload) -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    coords = geocode_city(conn, payload.city.strip())
    if coords is None:
        raise HTTPException(status_code=400, detail=f"Could not geocode city: {payload.city}")

    save_search(
        payload.city.strip(),
        payload.radius_km,
        center_lat=coords[0],
        center_lon=coords[1],
    )
    return _search_response(conn)


@app.get("/api/stats")
def api_stats() -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    return get_dashboard_stats(conn)


@app.get("/api/listings")
def api_listings(
    limit: int = 50,
    offset: int = 0,
    source: Optional[str] = None,
    search: Optional[str] = None,
) -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    listings, total = list_listings(
        conn,
        limit=min(limit, 200),
        offset=offset,
        source=source,
        search=search,
        apply_radius=True,
    )
    return {
        "listings": listings,
        "total": total,
        "limit": limit,
        "offset": offset,
        "search": _search_response(conn),
    }


@app.get("/api/listings/{canonical_id}")
def api_listing_detail(canonical_id: str) -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    listing = get_listing(conn, canonical_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@app.get("/api/sources")
def api_sources() -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    sources = load_sources()
    return {
        "search": _search_response(conn),
        "sources": [
            {
                "id": source.id,
                "name": source.name,
                "url": source.url,
                "enabled": source.enabled,
                "type": source.type,
            }
            for source in sources
        ],
    }


@app.put("/api/sources")
def api_update_sources(payload: SourcesUpdatePayload) -> dict[str, Any]:
    try:
        sources = save_platforms([source.model_dump() for source in payload.sources])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    conn = get_connection()
    init_db(conn)
    return {
        "search": _search_response(conn),
        "sources": [
            {
                "id": source.id,
                "name": source.name,
                "url": source.url,
                "enabled": source.enabled,
                "type": source.type,
            }
            for source in sources
        ],
    }


@app.get("/api/notifications")
def api_notifications() -> dict[str, Any]:
    email = load_email_config()
    return {
        "email": {
            "configured": email is not None,
            "to": email.to_address if email else None,
            "host": email.host if email else None,
        },
        "telegram": {
            "configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")),
        },
        "webhook": {
            "configured": bool(os.environ.get("NOTIFY_WEBHOOK_URL")),
        },
    }


@app.post("/api/scrape")
def api_scrape(payload: ScrapePayload) -> dict[str, Any]:
    if payload.full_sync and payload.max_pages is not None:
        raise HTTPException(
            status_code=400,
            detail="Full sync requires a complete scrape. Omit max_pages or disable full_sync.",
        )

    job = job_manager.start_scrape(
        source_id=payload.source_id,
        max_pages=None if payload.full_sync else payload.max_pages,
        full_sync=payload.full_sync,
    )
    return _job_to_dict(job)


@app.get("/api/jobs/latest")
def api_latest_job() -> dict[str, Any]:
    job = job_manager.latest()
    if job is None:
        return {"job": None}
    return {"job": _job_to_dict(job)}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> dict[str, Any]:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)


@app.get("/api/health")
def api_health() -> dict[str, str]:
    search = load_search()
    return {
        "status": "ok",
        "city": search.city,
        "config": str(DEFAULT_SOURCES_PATH),
    }
