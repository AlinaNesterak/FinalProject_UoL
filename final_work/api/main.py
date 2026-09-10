"""
REST API for the Music Works Catalogue Portal prototype.

Exposes the transformed catalogue data over HTTP as JSON, with endpoints for
listing, retrieving, searching, and filtering works, plus a discovery endpoint
that returns melodically similar works. FastAPI auto-generates OpenAPI docs at
/docs — directly addressing the "no API / no documentation" problems from the
literature.

Run:  uvicorn api.main:app --reload
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3

# Allow importing the discovery black box from the transform package
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "transform"))
from discovery import find_similar  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "catalogue.db"

app = FastAPI(
    title="Music Works Catalogue Portal API",
    description="Prototype REST API serving MEI thematic-catalogue data as JSON.",
    version="0.1.0",
)


# ---- Response models (Pydantic gives validation + schema for free) ----

class WorkSummary(BaseModel):
    work_id: str
    catalogue: str
    title_main: Optional[str]
    composer: Optional[str]
    genre: Optional[str]


class WorkDetail(WorkSummary):
    title_da: Optional[str]
    title_en: Optional[str]
    opus: Optional[str]
    composer_uri: Optional[str]
    date_text: Optional[str]
    instrumentation: list[str]
    incipit_tempo: Optional[str]
    incipit_key: Optional[str]
    incipit_meter: Optional[str]
    incipit_pitches: list[str]
    incipit_durations: list[int]
    sources: list[dict[str, object]]
    performances: list[dict[str, object]]
    history_note: Optional[str]
    composer_wikidata: Optional[str]
    composer_musicbrainz: Optional[str]
    work_wikidata: Optional[str]
    work_musicbrainz: Optional[str]
    imslp_url: Optional[str]


class SimilarWork(BaseModel):
    work_id: str
    title: Optional[str]
    composer: Optional[str]
    score: float


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(503, "Database not built. Run the transformation pipeline first.")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_detail(row: sqlite3.Row) -> WorkDetail:
    return WorkDetail(
        work_id=row["work_id"],
        catalogue=row["catalogue"],
        title_main=row["title_main"],
        title_da=row["title_da"],
        title_en=row["title_en"],
        composer=row["composer"],
        composer_uri=row["composer_uri"],
        opus=row["opus"],
        genre=row["genre"],
        date_text=row["date_text"],
        instrumentation=json.loads(row["instrumentation"] or "[]"),
        incipit_tempo=row["incipit_tempo"],
        incipit_key=row["incipit_key"],
        incipit_meter=row["incipit_meter"],
        incipit_pitches=json.loads(row["incipit_pitches"] or "[]"),
        incipit_durations=json.loads(row["incipit_durations"] or "[]"),
        sources=json.loads(row["sources"] or "[]"),
        performances=json.loads(row["performances"] or "[]"),
        history_note=row["history_note"],
        composer_wikidata=row["composer_wikidata"],
        composer_musicbrainz=row["composer_musicbrainz"],
        work_wikidata=row["work_wikidata"],
        work_musicbrainz=row["work_musicbrainz"],
        imslp_url=row["imslp_url"],
    )


FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


@app.get("/", response_model=None)
def root() -> FileResponse | dict[str, str]:
    """Serve the web interface if present, else basic API info."""
    if FRONTEND.exists():
        return FileResponse(str(FRONTEND))
    return {"name": "Music Works Catalogue Portal API", "version": "0.1.0", "docs": "/docs"}


@app.get("/api")
def api_info() -> dict[str, str]:
    return {"name": "Music Works Catalogue Portal API", "version": "0.1.0", "docs": "/docs"}


@app.get("/works", response_model=list[WorkSummary])
def list_works(
    catalogue: Optional[str] = Query(None, description="Filter by catalogue, e.g. CNW"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    composer: Optional[str] = Query(None, description="Filter by composer (substring)"),
    key: Optional[str] = Query(None, description="Filter by musical key, e.g. 'D major'"),
    instrument: Optional[str] = Query(None, description="Filter by instrumentation (substring)"),
    year_from: Optional[int] = Query(None, description="Earliest composition year (inclusive)"),
    year_to: Optional[int] = Query(None, description="Latest composition year (inclusive)"),
    sort: str = Query("catalogue", description="Sort order: catalogue, title, date, or composer"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[WorkSummary]:
    """
    List works with optional faceted filtering, sorting, and pagination.

    Filtering by genre, key, instrumentation and date range provides the
    dynamic querying that printed thematic catalogues cannot support and
    that Krabbe and Geertinger (2012) identify as the central advantage of
    digitising them.
    """
    conn = _connect()
    sql = "SELECT work_id, catalogue, title_main, composer, genre FROM works WHERE 1=1"
    params: list[object] = []
    if catalogue:
        sql += " AND catalogue = ?"
        params.append(catalogue.upper())
    if genre:
        sql += " AND genre = ?"
        params.append(genre)
    if composer:
        sql += " AND composer LIKE ?"
        params.append(f"%{composer}%")
    if key:
        sql += " AND incipit_key = ?"
        params.append(key)
    if instrument:
        sql += " AND instrumentation LIKE ?"
        params.append(f"%{instrument}%")
    # Dates are stored as text but the structured MEI attributes are
    # 4-digit years, so a numeric cast is safe and allows range queries.
    if year_from is not None:
        sql += " AND date_notbefore IS NOT NULL AND CAST(date_notbefore AS INTEGER) >= ?"
        params.append(year_from)
    if year_to is not None:
        sql += " AND date_notafter IS NOT NULL AND CAST(date_notafter AS INTEGER) <= ?"
        params.append(year_to)

    # Whitelist sort columns — never interpolate user input into SQL.
    # For date sorting, works with no recorded date sort last rather than
    # first, so an incomplete record doesn't head a chronological listing.
    sort_columns = {
        "catalogue": "catalogue, CAST(catalogue_number AS INTEGER)",
        "title": "title_main COLLATE NOCASE",
        "date": "date_notbefore IS NULL, CAST(date_notbefore AS INTEGER)",
        "composer": "composer COLLATE NOCASE, CAST(catalogue_number AS INTEGER)",
    }
    order_by = sort_columns.get(sort, sort_columns["catalogue"])
    sql += f" ORDER BY {order_by} LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [WorkSummary(**dict(r)) for r in rows]


@app.get("/works/search", response_model=list[WorkSummary])
def search_works(q: str = Query(..., min_length=1, description="Free-text search")) -> list[WorkSummary]:
    """Full-text search across title, composer, and incipit text."""
    conn = _connect()
    like = f"%{q}%"
    rows = conn.execute(
        """
        SELECT work_id, catalogue, title_main, composer, genre FROM works
        WHERE title_main LIKE ? OR title_da LIKE ? OR title_en LIKE ?
           OR composer LIKE ? OR genre LIKE ?
        ORDER BY catalogue, CAST(catalogue_number AS INTEGER)
        """,
        (like, like, like, like, like),
    ).fetchall()
    conn.close()
    return [WorkSummary(**dict(r)) for r in rows]


@app.get("/works/{work_id:path}/similar", response_model=list[SimilarWork])
def similar_works(work_id: str, top_n: int = Query(3, ge=1, le=10)) -> list[SimilarWork]:
    """
    Return works melodically similar to the given work, via the Works
    Discovery Engine (incipit interval comparison).
    """
    results = find_similar(DB_PATH, work_id, top_n=top_n)
    return [SimilarWork(**r) for r in results]


@app.get("/works/{work_id:path}", response_model=WorkDetail)
def get_work(work_id: str) -> WorkDetail:
    """Retrieve full detail for a single work by its ID (e.g. 'CNW 131')."""
    conn = _connect()
    row = conn.execute("SELECT * FROM works WHERE work_id = ?", (work_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, f"Work '{work_id}' not found")
    return _row_to_detail(row)


@app.get("/catalogues")
def list_catalogues() -> list[dict[str, str | int]]:
    """List available catalogues and their work counts."""
    conn = _connect()
    rows = conn.execute(
        "SELECT catalogue, COUNT(*) AS n FROM works GROUP BY catalogue ORDER BY catalogue"
    ).fetchall()
    conn.close()
    return [{"catalogue": r["catalogue"], "works": r["n"]} for r in rows]


class FindingsResponse(BaseModel):
    """Computed research findings about the transformed catalogue data."""
    total_works: int
    catalogues: dict[str, int]
    genres: dict[str, int]
    field_coverage: dict[str, dict[str, int | float]]
    incipit_lengths: dict[str, int]
    total_sources: int
    total_performances: int


@app.get("/findings", response_model=FindingsResponse)
def findings() -> FindingsResponse:
    """
    Computed research findings about the catalogue data.

    These figures are calculated live from the transformed database rather
    than hard-coded, so the research page always reflects the data actually
    loaded. They provide the empirical basis for this project's assessment
    of the MEI catalogue model (see docs/MEI evaluation).
    """
    conn = _connect()
    rows = conn.execute("SELECT * FROM works").fetchall()
    conn.close()

    total = len(rows)

    catalogues: dict[str, int] = {}
    genres: dict[str, int] = {}
    incipit_lengths: dict[str, int] = {}
    total_sources = 0
    total_performances = 0

    # Fields whose optionality in MEI is the subject of the evaluation.
    tracked = ["title_main", "composer", "opus", "title_da", "date_text",
               "genre", "incipit_pitches", "sources", "performances"]
    present: dict[str, int] = {f: 0 for f in tracked}

    for r in rows:
        catalogues[r["catalogue"]] = catalogues.get(r["catalogue"], 0) + 1
        if r["genre"]:
            genres[r["genre"]] = genres.get(r["genre"], 0) + 1

        srcs = json.loads(r["sources"] or "[]")
        perfs = json.loads(r["performances"] or "[]")
        total_sources += len(srcs)
        total_performances += len(perfs)

        pitches = json.loads(r["incipit_pitches"] or "[]")
        if pitches:
            key = str(len(pitches))
            incipit_lengths[key] = incipit_lengths.get(key, 0) + 1

        for f in tracked:
            if f == "sources":
                if srcs:
                    present[f] += 1
            elif f == "performances":
                if perfs:
                    present[f] += 1
            elif f == "incipit_pitches":
                if pitches:
                    present[f] += 1
            elif r[f]:
                present[f] += 1

    coverage: dict[str, dict[str, int | float]] = {
        f: {
            "present": present[f],
            "total": total,
            "percent": round(100 * present[f] / total, 1) if total else 0.0,
        }
        for f in tracked
    }

    return FindingsResponse(
        total_works=total,
        catalogues=catalogues,
        genres=genres,
        field_coverage=coverage,
        incipit_lengths=incipit_lengths,
        total_sources=total_sources,
        total_performances=total_performances,
    )


class FacetsResponse(BaseModel):
    """Available filter values, with counts, for building browse controls."""
    genres: list[dict[str, str | int]]
    keys: list[dict[str, str | int]]
    instruments: list[dict[str, str | int]]
    year_min: Optional[int]
    year_max: Optional[int]


@app.get("/facets", response_model=FacetsResponse)
def facets() -> FacetsResponse:
    """
    Available filter values and their counts.

    Computed from the loaded data rather than hard-coded, so the browse
    controls always match what is actually in the catalogue.
    """
    conn = _connect()
    rows = conn.execute(
        "SELECT genre, incipit_key, instrumentation, date_notbefore, date_notafter FROM works"
    ).fetchall()
    conn.close()

    genre_counts: dict[str, int] = {}
    key_counts: dict[str, int] = {}
    instrument_counts: dict[str, int] = {}
    years: list[int] = []

    for r in rows:
        if r["genre"]:
            genre_counts[r["genre"]] = genre_counts.get(r["genre"], 0) + 1
        if r["incipit_key"]:
            key_counts[r["incipit_key"]] = key_counts.get(r["incipit_key"], 0) + 1
        for inst in json.loads(r["instrumentation"] or "[]"):
            instrument_counts[inst] = instrument_counts.get(inst, 0) + 1
        for field in ("date_notbefore", "date_notafter"):
            val = r[field]
            if val and str(val).isdigit():
                years.append(int(val))

    def as_list(counts: dict[str, int]) -> list[dict[str, str | int]]:
        return [
            {"value": v, "count": n}
            for v, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    return FacetsResponse(
        genres=as_list(genre_counts),
        keys=as_list(key_counts),
        instruments=as_list(instrument_counts),
        year_min=min(years) if years else None,
        year_max=max(years) if years else None,
    )


@app.get("/export/works.json")
def export_json() -> Response:
    """
    Export the full catalogue as JSON.

    Data export directly serves the librarian and researcher user groups
    identified in the project's design, who need to take catalogue data
    into their own tools rather than only reading it in a browser.
    """
    conn = _connect()
    rows = conn.execute("SELECT * FROM works ORDER BY catalogue, CAST(catalogue_number AS INTEGER)").fetchall()
    conn.close()

    works = []
    for r in rows:
        d = dict(r)
        # Re-inflate the JSON-encoded columns so the export is properly
        # structured rather than containing embedded JSON strings.
        for field in ("instrumentation", "incipit_pitches", "incipit_durations",
                      "sources", "performances"):
            d[field] = json.loads(d.get(field) or "[]")
        works.append(d)

    payload = json.dumps({"works": works, "count": len(works)}, indent=2, ensure_ascii=False)
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="music-works-catalogue.json"'},
    )


@app.get("/export/works.csv")
def export_csv() -> Response:
    """
    Export the catalogue as CSV for use in spreadsheets and analysis tools.

    Nested data (sources, performances, incipit) is flattened into readable
    columns, since CSV cannot represent nesting; the JSON export preserves
    the full structure for callers that need it.
    """
    conn = _connect()
    rows = conn.execute("SELECT * FROM works ORDER BY catalogue, CAST(catalogue_number AS INTEGER)").fetchall()
    conn.close()

    buffer = io.StringIO()
    columns = [
        "work_id", "catalogue", "catalogue_number", "title_main", "title_da",
        "title_en", "composer", "opus", "genre", "date_text",
        "date_notbefore", "date_notafter", "instrumentation",
        "incipit_tempo", "incipit_key", "incipit_meter", "incipit_pitches",
        "source_count", "performance_count", "composer_wikidata", "composer_musicbrainz",
    ]
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        d = dict(r)
        d["instrumentation"] = "; ".join(json.loads(d.get("instrumentation") or "[]"))
        d["incipit_pitches"] = " ".join(json.loads(d.get("incipit_pitches") or "[]"))
        d["source_count"] = len(json.loads(d.get("sources") or "[]"))
        d["performance_count"] = len(json.loads(d.get("performances") or "[]"))
        writer.writerow(d)

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="music-works-catalogue.csv"'},
    )
