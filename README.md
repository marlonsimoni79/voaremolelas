# Voaremolelas

Paragliding weather analyzer for **Almargem, Portugal**. Fetches live wind,
temperature and pressure from Windguru, tephigram soundings from IPMA and rain
data from Open-Meteo, then plots today's findings and shows a simple
**GOOD / BAD** flying indicator.

Flying criteria (per spec):

| Criterion | Threshold |
|---|---|
| Wind speed (avg) | 15 – 22 km/h |
| Wind speed (max) | 15 – 25 km/h (when available) |
| Wind direction | 271° – 337° |
| Rain | none (probability < 40%) |

## Architecture

```
app/
  config.py          # all settings: endpoints, thresholds, timeouts
  main.py            # Flask app factory + entry point
  api/routes.py      # HTTP layer: /, /api/weather, in-memory cache
  data/windguru.py   # Windguru station client (scraped third-party API)
  data/ipma.py       # IPMA tephigram page parser
  data/openmeteo.py  # Open-Meteo rain client
  logic/analysis.py  # GOOD/BAD business logic
templates/index.html # Jinja dashboard
static/              # CSS + JS (AJAX polling of /api/weather)
tests/               # pytest suite (analysis + mocked API)
quadlet/             # Podman quadlet units
```

Data sources are scraped third-party pages; their markup/JSON can change at
any time, so all parsing is centralized in `app/data/` and selectors are
treated as fragile.

- **Windguru** — station `3843` (XPTO, Algueirão/Sintra, 6.3 km from Almargem)
  via `https://www.windguru.cz/int/iapi.php` (session + token refresh).
- **IPMA** — `https://www.ipma.pt/pt/otempo/obs.sondagens/`, tephigram PNGs
  under `https://www.ipma.pt/resources.www/transf/sondagem/`.
- **Open-Meteo** — `https://api.open-meteo.com/v1/forecast` for Almargem
  coordinates (current rain + hourly rain forecast).

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main            # serves on http://localhost:5555
```

Production-style:

```bash
gunicorn -b 0.0.0.0:5555 --workers 2 --timeout 60 app.main:app
```

## Tests

```bash
pip install -r requirements.txt
pytest
```

API tests mock all external sources, so no network is needed.

## Docker / Podman

```bash
podman build -t voaremolelas:latest .
podman run --rm -p 127.0.0.1:5555:5555 voaremolelas:latest
```

The container runs gunicorn on port 5555.

## Podman Quadlet (systemd-managed container)

Quadlet units live in `quadlet/`. The `.container` file generates
`voaremolelas.service`, and the `.network` file generates
`voaremolelas-network.service`. To install:

```bash
podman build -t voaremolelas:latest .
cp quadlet/voaremolelas.network quadlet/voaremolelas.container \
   ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start voaremolelas.service
```

The generated units are wired into the user session automatically after
`daemon-reload`; do not try to enable `voaremolelas.container` directly.

Check status and logs:

```bash
systemctl --user status voaremolelas.service
journalctl --user -u voaremolelas.service -f
```

Stop/remove:

```bash
systemctl --user stop voaremolelas.service
rm ~/.config/containers/systemd/voaremolelas.{container,network}
systemctl --user daemon-reload
```

The container is bound to `127.0.0.1:5555` (localhost only) and restarts
automatically on failure.

## Endpoints

| Route | Description |
|---|---|
| `GET /` | Dashboard (Jinja + JS) |
| `GET /api/weather` | JSON: station, current, series, rain now/forecast, tephigrams, assessment |

`/api/weather` responses are cached in memory for 300 s. If a data source
fails, the error is reported in `assessment.errors` and the affected field is
`null` — the app degrades gracefully instead of failing.
