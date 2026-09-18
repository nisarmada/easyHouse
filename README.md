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
- **Notifications** — optional email, Telegram, or webhook alerts (respecting the radius filter)
- **Fast watcher** — bootstrap full scrape, then randomized page-1 polls with periodic full sync

## Project layout

```
config/          search.json (city + radius), sources.json (enabled platforms)
geo/             geocoding (Nominatim) and haversine distance
scrapers/        per-platform parsers
db/              SQLite schema, upsert/dedup, query helpers
notify/          email, Telegram, webhook notifications
services/        shared scrape runner (used by CLI and web UI)
web/             FastAPI API + static dashboard
scripts/         CLI: scrape_once, watch, serve, test_scrapers
tests/           unit tests (pytest)
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure your search area in [`config/search.json`](config/search.json):

```json
{
  "city": "Amsterdam",
  "radius_km": 10
}
```

Enable platforms in [`config/sources.json`](config/sources.json). You only pick platform names and on/off — URLs are generated from the city:

```json
{
  "platforms": [
    { "name": "Pararius", "type": "pararius", "enabled": true },
    { "name": "Funda", "type": "funda", "enabled": true }
  ]
}
```

Legacy configs with a `sources` array (manual URLs) are migrated automatically on first load.

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

### Continuous watcher

Bootstrap (full scrape + sync), then fast page-1 polls every 45–90 s with a full sync every 30 min:

```bash
python scripts/watch.py
python scripts/watch.py --skip-bootstrap
```

### Web control panel

Use the project venv — system Python won't have the dependencies:

```bash
.venv/bin/pip install -r requirements.txt
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

When new listings are found, optional notifications can be sent via environment variables. All channels respect the radius filter.

### Email (SMTP)

| Variable | Required | Purpose |
|----------|----------|---------|
| `NOTIFY_EMAIL` | yes | Recipient address |
| `SMTP_HOST` | yes | SMTP server hostname |
| `SMTP_PORT` | no | Port (default: `587`) |
| `SMTP_USER` | no | Login username |
| `SMTP_PASSWORD` | no | Login password or app password |
| `SMTP_FROM` | no | From address (defaults to `SMTP_USER`) |
| `SMTP_USE_TLS` | no | Use STARTTLS (default: `true`) |

Example (Gmail app password):

```bash
export NOTIFY_EMAIL="you@gmail.com"
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USER="you@gmail.com"
export SMTP_PASSWORD="your-app-password"
export SMTP_FROM="easyHouse <you@gmail.com>"
python scripts/watch.py
```

### Other channels

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID |
| `NOTIFY_WEBHOOK_URL` | POST JSON payload to a custom webhook |

If none are set, output stays on stdout only.

## How it works

1. **Scrape** — each enabled platform is fetched; listings get a `search_id` from the configured city
2. **Geocode** — address fields are sent to Nominatim (with cache) to attach lat/lon
3. **Dedup** — canonical listings match on postcode + house number when available, otherwise street + city + price
4. **Filter** — new listings outside the radius are stored but not shown or notified
5. **Sync** — full scrapes remove source rows no longer on the site; fast polls only upsert page 1

## Notes

- **Funda** only exposes ~15 listings in static HTML. Results beyond that are mostly JS-rendered, so full coverage is limited without a browser.
- **Sync safety** — full sync deletes listings missing from a complete scrape. Fast polls (`watch.py`) only upsert page 1 and never delete.
- Database file: `easyhouse.db` (gitignored).
