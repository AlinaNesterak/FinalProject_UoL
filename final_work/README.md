# Music Works Catalogue Portal

A working system that transforms real MEI XML thematic-catalogue data into a
queryable database, a documented REST API, and an accessible web interface,
with a Works Discovery Engine for melodic similarity, real musical notation
rendering, audio playback of incipits, and a dedicated composition-history
page for each work.

This project tackles the domain's hardest technical challenge — parsing the
MEI XML data model, including its manuscripts, performance history, and
musical incipits, and computing melodic similarity across works — following
the principle of wiring up the full pipeline end-to-end early, even where
individual components started out simple and were then iterated on.

## Pipeline

```
MEI XML files  ->  parser.py  ->  SQLite  ->  FastAPI REST API  ->  Web UI
                                     |
                                     +->  discovery.py (incipit similarity, v2)
```

## What works

- **MEI 4.0 parser** (`transform/parser.py`) — extracts titles (multilingual),
  composer, catalogue number, opus, genre, date, instrumentation, incipit
  (tempo, key, meter, pitch sequence, and durations), manuscript/print
  sources, performance history, and a narrative composition-history essay.
  Catalogue-agnostic: handles both Carl Nielsen (CNW) and Frederick Delius
  (DCW) with no code changes.
- **Transformation pipeline** (`transform/pipeline.py`) — builds a normalised
  SQLite database over 24 real works; reports parse errors separately rather
  than crashing.
- **REST API** (`api/main.py`) — FastAPI with endpoints for listing, faceted
  filtering (genre, key, instrument, date range), sorting, search,
  single-work retrieval, similar-work discovery, computed research findings,
  and CSV/JSON export. Auto-generated OpenAPI docs at `/docs`.
- **Web interface** (`frontend/index.html`) — an accessible (WCAG-aligned),
  keyboard-navigable single-page app: browse and search the catalogue, view
  manuscripts and performance history, see the incipit rendered as real
  musical notation, hear it played back, and read each work's full
  composition history on its own page (`#/history/<work id>`), and view
  computed research findings about the catalogue data (`#/research`).
  Works can be browsed by genre, musical key, instrumentation and date range,
  sorted several ways, and exported as CSV or JSON. Records link out to
  Wikidata, MusicBrainz, and — where a verified page exists — to free
  downloadable scores on IMSLP.
- **Works Discovery Engine v2** (`transform/discovery.py`) — combines pitch
  interval shape, melodic contour, tempo-invariant rhythm, and local
  (interval, rhythm) bigram overlap. v1 (pitch-only) failed its own sanity
  check; v2 fixes it with a concrete, evidenced improvement — see
  `evaluation/evaluate.py`.
- **Test suite** (`tests/`) — 80 tests: 52 backend (pytest) covering the
  parser, pipeline, and every API endpoint, plus 28 end-to-end (Playwright)
  covering the browser behaviour — search, filtering, notation rendering,
  the play button, the history page and its hash-based routing, and
  accessibility (keyboard focus, skip link, reduced-motion support).
- **Evaluation** (`evaluation/evaluate.py`) — measures parse robustness,
  data integrity (duplicate identifiers), processing time with a projection
  to full catalogue scale, transformation completeness, and discovery
  quality, with honest limitations throughout.

## Deployment

The `deploy/` folder contains everything needed to run this on a Linux server:
a `systemd` unit, an `nginx` site configuration, and a `setup.sh` script that
performs the whole installation. See `deploy/README.md` for step-by-step
instructions, including the Azure firewall rule that must be added separately.

```bash
bash deploy/setup.sh
```

## Running the tests

```bash
python3 -m pytest tests/test_prototype.py -v   # 52 backend tests
python3 -m pytest tests/test_frontend.py -v    # 28 end-to-end tests (Playwright)
python3 -m pytest tests/ -v                    # all 80 together
```

The end-to-end tests start a real server in a background thread and drive a
real headless Chromium browser — no mocking. First-time setup needs the
Chromium binary: `playwright install chromium` (already listed as a
dependency; the browser itself is a one-time separate download).

## Data

`data/` contains real Carl Nielsen works (CNW 60, 102, 128, 131) and a Delius
work (DCW 42), reconstructed in MEI 4.0 from the public MerMEId demo catalogue,
plus two deliberate edge cases (a minimal record and a malformed file) for
robustness testing.

## Running

```bash
pip install -r requirements.txt
./run.sh                       # build DB + start API at localhost:8000
# or individually:
python3 transform/pipeline.py data catalogue.db
python3 evaluation/evaluate.py
python3 -m pytest tests/ -v
uvicorn api.main:app --reload
```

## Known limitations (see evaluation output)

- Tiny sample (6 works) — metrics are indicative only.
- Incipit similarity is coarse on short melodies; the discovery sanity check
  currently does **not** cleanly separate songs from the symphony, a documented
  finding that motivates a richer metric in the next iteration.
- No frontend yet (backend-focused prototype).
