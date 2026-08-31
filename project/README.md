# Music Works Catalogue Portal — Prototype

A working backend prototype that transforms real MEI XML thematic-catalogue data
into a queryable REST API, with a Works Discovery Engine for melodic similarity.

This prototype deliberately tackles the project's hardest technical challenge —
parsing the MEI XML data model and computing melodic similarity from incipits —
following the principle of wiring up the full pipeline end-to-end early, even
where individual components are still simple.

## Pipeline

```
MEI XML files  ->  parser.py  ->  SQLite  ->  FastAPI REST API
                                     |
                                     +->  discovery.py (incipit similarity)
```

## What works

- **MEI 4.0 parser** (`transform/parser.py`) — extracts titles (multilingual),
  composer, catalogue number, opus, genre, date, instrumentation, and incipit
  (tempo, key, meter, and the pitch sequence). Catalogue-agnostic: handles both
  Carl Nielsen (CNW) and Frederick Delius (DCW) with no code changes.
- **Transformation pipeline** (`transform/pipeline.py`) — builds a normalised
  SQLite database; reports parse errors separately rather than crashing.
- **REST API** (`api/main.py`) — FastAPI with endpoints for listing, filtering,
  search, single-work retrieval, and similar-work discovery. Auto-generated
  OpenAPI docs at `/docs`.
- **Works Discovery Engine** (`transform/discovery.py`) — a "black box" that
  takes incipit pitch sequences and returns similarity scores (interval +
  contour comparison). Simple by design; upgradeable later.
- **Test suite** (`tests/`) — 15 pytest tests across parser, pipeline, and API.
- **Evaluation** (`evaluation/evaluate.py`) — measures parse robustness,
  transformation completeness, and discovery quality, with honest limitations.

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
