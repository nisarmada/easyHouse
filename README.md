# easyHouse

Watch Dutch rental listing sites for new apartments and sync them to a local SQLite database.

Supported sources:

- [Pararius](https://www.pararius.com)
- [Kamernet](https://kamernet.nl)
- [Funda](https://www.funda.nl)
- [Huurwoningen](https://www.huurwoningen.nl)
- [HousingAnywhere](https://housinganywhere.com)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure searches in [`config/sources.json`](config/sources.json). Each entry needs a `name`, `url`, and optional `enabled` flag.

## Usage

One-off scrape:

```bash
python scripts/scrape_once.py
python scripts/scrape_once.py --source pararius --max-pages 1 --no-sync
```

Continuous watcher (bootstrap full scrape, then fast page-1 polls):

```bash
python scripts/watch.py
python scripts/watch.py --skip-bootstrap
```

Live scraper smoke test:

```bash
python scripts/test_scrapers.py
```

Offline unit tests:

```bash
pytest
```

## Notifications

When new listings are found, optional notifications can be sent via environment variables:

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID |
| `NOTIFY_WEBHOOK_URL` | POST JSON payload to a custom webhook |

If none are set, output stays on stdout only.

## Notes

- **Funda** only exposes about 15 listings in static HTML. The scraper paginates when new IDs appear, but Funda's search results are mostly JS-rendered, so full coverage is limited without a browser.
- **Sync safety**: full sync deletes listings missing from a complete scrape. Fast polls (`watch.py`) only upsert page 1 and never delete.
- Database file: `easyhouse.db` (gitignored).
