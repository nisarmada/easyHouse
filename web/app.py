from __future__ import annotations

import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auth.service import (
    auth_status,
    get_current_account,
    login,
    logout,
    resend_verification,
    signup,
    update_alerts,
    verify_email,
)
from config.load import ensure_sources_config, get_sources_path, load_sources, save_platforms
from config.neighborhoods import SUPPORTED_CITIES, neighborhoods_for_city
from config.paths import ensure_user_data, get_auth_url, get_db_path, remote_auth_enabled, user_data_dir
from config.search import load_search, save_search
from config.search_service import get_active_search, search_city_changed
from db.db import get_connection, init_db
from db.queries import get_dashboard_stats, get_listing, list_listings
from geo.geocode import geocode_search_area
from notify.email import send_service_email
from notify.smtp_config import (
    load_service_smtp_config,
    load_service_smtp_public,
    parse_from_address,
    save_service_smtp,
)
from services.autostart import autostart_status, install_autostart, uninstall_autostart
from web.jobs import JobManager

STATIC_DIR = Path(__file__).resolve().parent / "static"
job_manager = JobManager()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_user_data()
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
    neighborhood: Optional[str] = None
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None


class SearchGeocodePayload(BaseModel):
    city: str = Field(min_length=1)
    neighborhood: Optional[str] = None


class ScrapePayload(BaseModel):
    source_id: Optional[str] = None
    max_pages: Optional[int] = 1
    full_sync: bool = False


class AuthSignupPayload(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)


class AuthLoginPayload(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class AlertsPayload(BaseModel):
    enabled: bool = True


class VerifyCodePayload(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class EmailServicePayload(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=587, ge=1, le=65535)
    from_address: str = Field(min_length=1)
    username: str = ""
    password: Optional[str] = None
    use_tls: bool = True


def _session_token(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        return token or None
    return None


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
def landing() -> FileResponse:
    return FileResponse(STATIC_DIR / "landing.html")


@app.get("/app")
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.html")


@app.get("/api/search")
def api_get_search() -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    return _search_response(conn)


@app.get("/api/cities")
def api_cities() -> dict[str, Any]:
    return {
        "cities": [
            {"name": city, "neighborhoods": neighborhoods_for_city(city)}
            for city in SUPPORTED_CITIES
        ]
    }


@app.post("/api/search/geocode")
def api_geocode_search(payload: SearchGeocodePayload) -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    city = payload.city.strip()
    neighborhood = (payload.neighborhood or "").strip() or None
    coords = geocode_search_area(conn, city, neighborhood=neighborhood)
    if coords is None:
        label = f"{neighborhood}, {city}" if neighborhood else city
        raise HTTPException(status_code=400, detail=f"Could not geocode: {label}")

    return {
        "city": city,
        "neighborhood": neighborhood,
        "center_lat": coords[0],
        "center_lon": coords[1],
        "label": f"{neighborhood}, {city}" if neighborhood else city,
    }


@app.put("/api/search")
def api_update_search(payload: SearchUpdatePayload) -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    previous = load_search()
    city = payload.city.strip()
    neighborhood = (payload.neighborhood or "").strip() or None

    if payload.center_lat is not None and payload.center_lon is not None:
        center_lat, center_lon = payload.center_lat, payload.center_lon
    else:
        coords = geocode_search_area(conn, city, neighborhood=neighborhood)
        if coords is None:
            label = f"{neighborhood}, {city}" if neighborhood else city
            raise HTTPException(status_code=400, detail=f"Could not geocode: {label}")
        center_lat, center_lon = coords

    updated = save_search(
        city,
        payload.radius_km,
        center_lat=center_lat,
        center_lon=center_lon,
        neighborhood=neighborhood,
    )
    response = updated.to_dict()
    if search_city_changed(previous, updated):
        job = job_manager.start_scrape(max_pages=None, full_sync=True)
        response["scrape_job"] = _job_to_dict(job)
    return response


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


@app.get("/api/auth/config")
def api_auth_config() -> dict[str, Any]:
    return {
        "remote_auth": remote_auth_enabled(),
        "auth_url": get_auth_url(),
    }


@app.get("/api/auth/status")
def api_auth_status(token: Optional[str] = Depends(_session_token)) -> dict[str, Any]:
    return auth_status(token)


@app.post("/api/auth/signup")
def api_signup(payload: AuthSignupPayload) -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    try:
        return signup(conn, email=payload.email, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/login")
def api_login(payload: AuthLoginPayload) -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    try:
        return login(conn, email=payload.email, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/logout")
def api_logout(token: Optional[str] = Depends(_session_token)) -> dict[str, str]:
    conn = get_connection()
    init_db(conn)
    logout(conn, token)
    return {"status": "signed_out"}


@app.post("/api/auth/verify")
def api_verify_email(payload: VerifyCodePayload) -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    try:
        return verify_email(conn, payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/resend-verification")
def api_resend_verification(token: Optional[str] = Depends(_session_token)) -> dict[str, str]:
    conn = get_connection()
    init_db(conn)
    try:
        return resend_verification(conn, token or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/auth/alerts")
def api_update_alerts(
    payload: AlertsPayload,
    token: Optional[str] = Depends(_session_token),
) -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    try:
        return update_alerts(conn, token or "", enabled=payload.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/email-service")
def api_get_email_service() -> dict[str, Any]:
    return load_service_smtp_public()


@app.put("/api/email-service")
def api_save_email_service(payload: EmailServicePayload) -> dict[str, Any]:
    try:
        save_service_smtp(
            host=payload.host,
            port=payload.port,
            from_address=payload.from_address,
            username=payload.username,
            password=payload.password,
            use_tls=payload.use_tls,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return load_service_smtp_public()


@app.post("/api/email-service/test")
def api_test_email_service() -> dict[str, str]:
    config = load_service_smtp_config()
    if config is None:
        raise HTTPException(status_code=400, detail="Configure SMTP settings first")
    to_address = config.username or parse_from_address(config.from_address)
    if not to_address:
        raise HTTPException(
            status_code=400,
            detail="Set a username or a from address with an email to receive the test message",
        )
    try:
        send_service_email(
            to_address=to_address,
            subject="easyHouse: test email",
            plain_body="This is a test email from easyHouse. SMTP is configured correctly.",
            html_body="<p>This is a test email from easyHouse. SMTP is configured correctly.</p>",
            config=config,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not send test email: {exc}") from exc
    return {"status": "sent", "to": to_address}


@app.get("/api/notifications")
def api_notifications(token: Optional[str] = Depends(_session_token)) -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    account = get_current_account(conn, token)
    status = auth_status(token)
    return {
        "account": account,
        "signed_in": account is not None,
        "can_send_mail": status["can_send_mail"],
        "remote_auth": status.get("remote_auth", False),
    }


@app.get("/api/agent/autostart")
def api_autostart_status() -> dict[str, Any]:
    status = autostart_status()
    return {
        "platform": status.platform,
        "supported": status.supported,
        "installed": status.installed,
        "target": status.target,
    }


@app.post("/api/agent/autostart/install")
def api_install_autostart() -> dict[str, Any]:
    try:
        status = install_autostart()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "platform": status.platform,
        "supported": status.supported,
        "installed": status.installed,
        "target": status.target,
    }


@app.post("/api/agent/autostart/uninstall")
def api_uninstall_autostart() -> dict[str, Any]:
    try:
        status = uninstall_autostart()
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "platform": status.platform,
        "supported": status.supported,
        "installed": status.installed,
        "target": status.target,
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
        "data_dir": str(user_data_dir()),
        "database": str(get_db_path()),
        "sources": str(get_sources_path()),
        "remote_auth": str(remote_auth_enabled()).lower(),
        "auth_url": get_auth_url() or "",
    }
