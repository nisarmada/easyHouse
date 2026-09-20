# easyHouse

Watch Dutch rental listing sites for new apartments, deduplicate listings across platforms, and get alerts for homes within your search area.

Supported platforms:

- [Pararius](https://www.pararius.com)
- [Kamernet](https://kamernet.nl)
- [Funda](https://www.funda.nl)
- [Huurwoningen](https://www.huurwoningen.nl)
- [HousingAnywhere](https://housinganywhere.com)

## Features

- **Multi-platform scraping** — one config enables/disables platforms; URLs are built from your city
- **City + radius search** — geocode listings and filter by distance from city center
- **Cross-site dedup** — the same flat on Pararius and Funda is stored once, with one alert
- **Web control panel** — set search area, browse listings, trigger scrapes, manage platforms
- **Notifications** — optional email alerts (respecting the radius filter)
- **Fast watcher** — bootstrap full scrape, then randomized page-1 polls with periodic full sync

## Project layout

```
config/          search.json (city + radius), sources.json (enabled platforms)
geo/             geocoding (Nominatim) and haversine distance
scrapers/        per-platform parsers
db/              SQLite schema, upsert/dedup, query helpers
notify/          email notifications
services/        shared scrape runner (used by CLI and web UI)
web/             FastAPI API + static dashboard
scripts/         CLI: agent, scrape_once, watch, serve, test_scrapers
tests/           unit tests (pytest)
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On first run, easyHouse creates a local data directory at `~/.easyhouse/` with default config, SQLite database, and notification settings. Configure everything from the dashboard — no manual JSON editing required.

Override the data directory with `EASYHOUSE_HOME=/path/to/data`.

## Usage

### One-off scrape

```bash
python scripts/scrape_once.py
python scripts/scrape_once.py --source pararius
python scripts/scrape_once.py --source pararius --max-pages 1 --no-sync
```

Parse saved HTML offline (Pararius only):

```bash
python scripts/scrape_once.py --file pararius.html
```

### Agent (recommended)

One process: background watcher + web dashboard. Scraping runs from your machine; open the dashboard to configure and browse listings.

```bash
.venv/bin/python scripts/agent.py --open-browser
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080) for the landing page. **Get started** takes you to the search area picker at `/app?view=search`.

If the browser did not open automatically, visit that URL manually.

| Flag | Purpose |
|------|---------|
| `--open-browser` | Open the dashboard on startup |
| `--skip-bootstrap` | Skip the initial full scrape |
| `--deep-interval SECS` | Full sync interval (default: 1800, `0` disables) |
| `--install-autostart` | Start easyHouse automatically at login |
| `--uninstall-autostart` | Remove autostart entry |

On first run the agent bootstraps a full scrape, then fast page-1 polls every 45–90 s with a full sync every 30 min. Press Ctrl+C to stop.

**Start at login:** run `--install-autostart` once, or use **Settings → Start at login** in the dashboard.

### Standalone build (no Python install)

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/build.py
./dist/easyhouse --open-browser
```

### Continuous watcher (CLI only)

Watcher without the web UI:

```bash
python scripts/watch.py
python scripts/watch.py --skip-bootstrap
```

### Web control panel (UI only)

Dashboard without the background watcher:

```bash
.venv/bin/python scripts/serve.py
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080) to:

- Set city and radius (listings outside the radius are hidden)
- Browse and search stored listings with distance from center
- Enable/disable platforms
- Trigger manual or full-sync scrapes
- Check notification channel status

Optional flags: `--host`, `--port`, `--reload`.

### Tests

```bash
pytest
```

Live scraper smoke test (hits real sites):

```bash
python scripts/test_scrapers.py
```

## Search area

- Set **city** (e.g. Amsterdam, Rotterdam, Utrecht, Den Haag) and **radius** in km
- Listings are geocoded via [Nominatim](https://nominatim.org/) on upsert (cached in SQLite, ~1 req/s)
- The web UI, stats, and notifications only include listings within the radius
- Listings without coordinates are excluded when a radius filter is active

## Notifications

1. Open **Settings** in the dashboard
2. **Create an account** with your email and a password
3. Enter the **6-digit verification code** sent to your inbox
4. Toggle **Email alerts** on

Alerts only go to verified accounts — you cannot register someone else's email without access to their inbox.

### Cloud auth (recommended)

Scraping stays local. Signup, verification codes, and alert emails go through a small **Cloudflare Worker** (free tier) so users never configure SMTP.

**One-time deploy (maintainer):**

```bash
cd cloudflare/auth-worker
npm install
npx wrangler login
npx wrangler d1 create easyhouse-auth
# Paste database_id into cloudflare/auth-worker/wrangler.jsonc
export SMTP_USER=you@gmail.com
export SMTP_PASSWORD=your-gmail-app-password
export SMTP_FROM="easyHouse <you@gmail.com>"
./scripts/deploy_auth_worker.sh
```

This saves the worker URL to `~/.easyhouse/auth.json`. Users can also set:

```bash
python scripts/set_auth_url.py https://easyhouse-auth.YOUR.workers.dev
# or
export EASYHOUSE_AUTH_URL=https://easyhouse-auth.YOUR.workers.dev
```

**GitHub Pages** hosts the public landing site from `docs/` (see `.github/workflows/pages.yml`).

### Local-only fallback

If no auth URL is configured, the agent falls back to local SQLite auth. You can still configure SMTP under **Settings → Email delivery** or via:

| Variable | Purpose |
|----------|---------|
| `EASYHOUSE_SMTP_HOST` | SMTP server hostname |
| `EASYHOUSE_SMTP_PORT` | Port (default: `587`) |
| `EASYHOUSE_SMTP_FROM` | From address |
| `EASYHOUSE_SMTP_USER` | Login username (optional) |
| `EASYHOUSE_SMTP_PASSWORD` | Login password (optional) |
| `EASYHOUSE_SMTP_USE_TLS` | Use STARTTLS (default: `true`) |

If no account is signed in or email is not verified, new listings are logged to stdout only.

## How it works

1. **Scrape** — each enabled platform is fetched; listings get a `search_id` from the configured city
2. **Geocode** — address fields are sent to Nominatim (with cache) to attach lat/lon
3. **Dedup** — canonical listings match on postcode + house number when available, otherwise street + city + price
4. **Filter** — new listings outside the radius are stored but not shown or notified
5. **Sync** — full scrapes remove source rows no longer on the site; fast polls only upsert page 1

## Notes

- **Funda** only exposes ~15 listings in static HTML. Results beyond that are mostly JS-rendered, so full coverage is limited without a browser.
- **Sync safety** — full sync deletes listings missing from a complete scrape. Fast polls (`watch.py`) only upsert page 1 and never delete.
- User data lives in `~/.easyhouse/` (database, config, email settings).
