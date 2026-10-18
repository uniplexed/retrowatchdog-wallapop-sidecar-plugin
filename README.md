# Wallapop sidecar

A source plugin for [RetroWatchdog](https://github.com/uniplexed/retrowatchdog),
the manager of your retro game collection and your price hunts. It fetches
Wallapop listings so the app can show private sellers' asking prices in
Spain, Italy and Portugal, speaking protocol version 3 as set out in the
protocol document, `docs/sidecar-protocol.md` in the `retrowatchdog`
repository. It is a small Python service on the standard library alone: one
process serves three `live` sources, `wallapop_es`, `wallapop_it` and
`wallapop_pt`. In a RetroWatchdog deployment it runs as the compose service
`wallapop-sidecar-plugin` behind the `wallapop` profile; the app offers it as a
pending plugin row on first boot, you approve its role in Settings → Plugins
and switch on the countries you want in Settings → Markets. Nothing about it
is compiled into the app.

The general rules (what a plugin is, the fetch/interpret split, the manifest
and its approval, the isolation, the pacing) are in the protocol document;
this file covers only what this sidecar does within them.

## Terms of use: you need Wallapop's authorization

Wallapop's [terms of use](https://about.wallapop.com/condiciones-de-uso/) require Wallapop's **express
authorization** to access its service this way. Get it before you run this
plugin; running it without that authorization is your decision and your
responsibility. The plugin's manifest repeats this under every Wallapop price
in the app.

Wallapop publishes no API for this. The plugin reads the JSON its own website
uses, which may change or close without warning. It is a personal-use,
best-effort integration: do not build a business on it.

## What it serves

| endpoint | answer |
|---|---|
| `GET /health` | `{status, protocol, configured, sources}`. `configured` is always `true`: a public site needs no credential. |
| `GET /manifest` | one source per served site, each with its label, country, currency, reach, role and caveat; `requiredSecrets` is empty |
| `GET /search?source=<id>&q=<text>[&platform=<id>]` | a JSON array of raw listings |

`/health` and `/manifest` never call Wallapop. Status codes: `400` for a
missing `source` or `q`; `404` for a source this process does not serve or an
unknown path; `502` when the search fails or Wallapop answers in a shape the
plugin does not know, so the app's breaker counts it; `500` from `/manifest`
when `WALLAPOP_SITES` names an unknown site. Unknown query parameters are
ignored.

## What it declares

`kind: live`, `family: wallapop`, `reach: global` (a marketplace of private
sellers), `defaultRegion: null`, one expected currency per source, `kindRoles`
`active_listing → buy_listing` and nothing else, `kindLabels` "<site> asking
price", and a caveat saying the source is read through an unofficial API.
Every Wallapop number is a private seller's asking price, never a reference.

| key | source | listings at | country | currency | label | searches from |
|---|---|---|---|---|---|---|
| `es` | `wallapop_es` | `es.wallapop.com` | ES | EUR | Wallapop España | Madrid |
| `it` | `wallapop_it` | `it.wallapop.com` | IT | EUR | Wallapop Italia | Rome |
| `pt` | `wallapop_pt` | `pt.wallapop.com` | PT | EUR | Wallapop Portugal | Lisbon |

## How a search runs

One `GET https://api.wallapop.com/api/v3/search` per request, with the
game's title as `keywords`, the site's point as `latitude` and `longitude`,
and `subcategory_ids` narrowing it to video games (`10093`) and PC games
(`24129`). Wallapop ranks by distance from that point, and the point decides
the country: a search from Lisbon returns mostly Spanish listings, because
that is what is near. The platform hint is ignored; the app reads the
platform from each title.

Reserved items are skipped: they are promised to a buyer. An item without an
id, a title, a numeric price or an ISO currency is dropped and logged, and
the rest of the answer stands. A missing or odd `web_slug` keeps the listing
without a link.

Each row carries `sourceProductId` (Wallapop's item id), `title` (verbatim),
one `active_listing` price as quoted, and `url`
(`https://<site>/item/<web_slug>`). The listing's description, seller and
location are not read.

## Configuration

`app/config.py` reads these variables, all optional. In a RetroWatchdog
deployment the plugin's own env file is `.env.wallapop` beside the app's
`.env`.

| variable | default | meaning |
|---|---|---|
| `WALLAPOP_SITES` | `es,it,pt` | comma-separated site keys to serve |
| `WALLAPOP_LOCATION_ES`, `_IT`, `_PT` | the capital | where that site's searches start, as `latitude,longitude` |
| `WALLAPOP_SUBCATEGORY_IDS` | `10093,24129` | Wallapop subcategories every search is narrowed to |
| `PORT` | `8000` | the port inside the container; blank counts as unset |

A location that is not two numbers inside the globe stops the container at
start with the variable named in the log.

### Search from your city

Goal: rank listings near you rather than near the capital.

1. In Google Maps, right-click your town and click the coordinates at the top
   of the menu; they are copied as `40.4168, -3.7038`.
2. In `.env.wallapop`, add `WALLAPOP_LOCATION_ES=40.4168,-3.7038` (or `_IT`,
   `_PT`).
3. Run `docker compose up -d wallapop-sidecar-plugin`.

## What is not verified

No test calls Wallapop; each item below could change without the suite
noticing.

1. The `X-DeviceOS: 0` header: without it Wallapop answers 403 (checked
   2026-10-18). With it, Wallapop accepts this plugin's own user agent, so
   the plugin says who it is.
2. The subcategory ids, read from Wallapop's category tree on 2026-10-18.
3. One page per search: the plugin reads the first answer (about 40 items)
   and does not follow `next_page`.

## How to build and run it

1. From this repository's root, run
   `docker build -t retrowatchdog-wallapop-sidecar-plugin:latest .`, or use
   the published image `ghcr.io/uniplexed/retrowatchdog-wallapop-sidecar-plugin`.
2. From the app's directory, add `wallapop` to `COMPOSE_PROFILES` and run
   `docker compose up -d`.
3. In the app, open Settings → Plugins, approve the Wallapop row, and switch
   on its markets in Settings → Markets.
4. Check: open a game; a Wallapop block shows asking prices.

The image is `python:3.12-slim` with nothing installed; the process runs as an
unprivileged user and publishes no host port.

## How to run the tests

`pip install pytest`, then `pytest` from the repository root. The suite uses
no network: searches are answered by a stub fed
`fixtures/search-ocarina-2026-10-18.json`, a real answer cut to the fields the
plugin reads.

## How to regenerate the manifest fixture

```bash
python -c "import json; from app.config import load_settings; from app.manifest import manifest_payload; print(json.dumps(manifest_payload(load_settings({})), indent=2))" > manifest.fixture.json
```

Copy it into the app repository as
`apps/api/src/adapters/sidecar/fixtures/wallapop-manifest.json`; the app's
`wallapopManifest` test checks it validates.

## Legal

[LEGAL.md](LEGAL.md): the source's terms as last read, what they mean for
whoever runs this plugin, no warranty, not financial advice, no affiliation.
The names of the shops and marketplaces are their owners' trademarks, used
only to say where a price came from.

## License

Free software under the [GNU Affero General Public License v3.0](LICENSE),
and only that. Contributions are accepted under the terms in
[CONTRIBUTING.md](CONTRIBUTING.md).
