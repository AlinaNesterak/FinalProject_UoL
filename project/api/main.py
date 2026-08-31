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

import json
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Allow importing the discovery black box from the transform package
import sys
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
    sources: list[dict]
    performances: list[dict]


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
    )


FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


@app.get("/")
def root():
    """Serve the web interface if present, else basic API info."""
    if FRONTEND.exists():
        return FileResponse(str(FRONTEND))
    return {"name": "Music Works Catalogue Portal API", "version": "0.1.0", "docs": "/docs"}


@app.get("/api")
def api_info():
    return {"name": "Music Works Catalogue Portal API", "version": "0.1.0", "docs": "/docs"}


@app.get("/works", response_model=list[WorkSummary])
def list_works(
    catalogue: Optional[str] = Query(None, description="Filter by catalogue, e.g. CNW"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    composer: Optional[str] = Query(None, description="Filter by composer (substring)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List works with optional filtering and pagination."""
    conn = _connect()
    sql = "SELECT work_id, catalogue, title_main, composer, genre FROM works WHERE 1=1"
    params: list = []
    if catalogue:
        sql += " AND catalogue = ?"
        params.append(catalogue.upper())
    if genre:
        sql += " AND genre = ?"
        params.append(genre)
    if composer:
        sql += " AND composer LIKE ?"
        params.append(f"%{composer}%")
    sql += " ORDER BY catalogue, CAST(catalogue_number AS INTEGER) LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [WorkSummary(**dict(r)) for r in rows]


@app.get("/works/search", response_model=list[WorkSummary])
def search_works(q: str = Query(..., min_length=1, description="Free-text search")):
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
def similar_works(work_id: str, top_n: int = Query(3, ge=1, le=10)):
    """
    Return works melodically similar to the given work, via the Works
    Discovery Engine (incipit interval comparison).
    """
    results = find_similar(DB_PATH, work_id, top_n=top_n)
    return [SimilarWork(**r) for r in results]


@app.get("/works/{work_id:path}", response_model=WorkDetail)
def get_work(work_id: str):
    """Retrieve full detail for a single work by its ID (e.g. 'CNW 131')."""
    conn = _connect()
    row = conn.execute("SELECT * FROM works WHERE work_id = ?", (work_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, f"Work '{work_id}' not found")
    return _row_to_detail(row)


@app.get("/catalogues")
def list_catalogues():
    """List available catalogues and their work counts."""
    conn = _connect()
    rows = conn.execute(
        "SELECT catalogue, COUNT(*) AS n FROM works GROUP BY catalogue ORDER BY catalogue"
    ).fetchall()
    conn.close()
    return [{"catalogue": r["catalogue"], "works": r["n"]} for r in rows]
