"""
Transformation pipeline: MEI XML -> SQLite.

Reads all MEI files in a directory (via parser.py), creates a normalised SQLite
database, and loads the works. This is the "transform" stage of the pipeline:
source XML in, queryable database out.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from parser import parse_directory, Work

SCHEMA = """
CREATE TABLE IF NOT EXISTS works (
    work_id           TEXT PRIMARY KEY,
    catalogue         TEXT NOT NULL,
    catalogue_number  TEXT NOT NULL,
    title_main        TEXT,
    title_da          TEXT,
    title_en          TEXT,
    composer          TEXT,
    composer_uri      TEXT,
    opus              TEXT,
    genre             TEXT,
    date_text         TEXT,
    date_notbefore    TEXT,
    date_notafter     TEXT,
    instrumentation   TEXT,   -- JSON array
    incipit_tempo     TEXT,
    incipit_key       TEXT,
    incipit_meter     TEXT,
    incipit_pitches   TEXT,   -- JSON array of pitch names
    source_file       TEXT
);

CREATE INDEX IF NOT EXISTS idx_catalogue ON works (catalogue);
CREATE INDEX IF NOT EXISTS idx_composer  ON works (composer);
CREATE INDEX IF NOT EXISTS idx_genre     ON works (genre);
"""


def build_database(data_dir: str | Path, db_path: str | Path) -> dict:
    """
    Build the SQLite database from MEI files.

    Returns a report dict with counts and any parse errors — used by the
    evaluation script to measure transformation completeness.
    """
    data_dir = Path(data_dir)
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()

    works, errors = parse_directory(data_dir)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)

    for w in works:
        meter = None
        pitches = "[]"
        tempo = key = None
        if w.incipit:
            tempo = w.incipit.tempo
            key = w.incipit.key
            if w.incipit.meter_count and w.incipit.meter_unit:
                meter = f"{w.incipit.meter_count}/{w.incipit.meter_unit}"
            pitches = json.dumps(w.incipit.pitches)

        conn.execute(
            """
            INSERT OR REPLACE INTO works VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                w.work_id, w.catalogue, w.catalogue_number,
                w.title_main, w.title_da, w.title_en,
                w.composer, w.composer_uri, w.opus, w.genre,
                w.date_text, w.date_notbefore, w.date_notafter,
                json.dumps(w.instrumentation),
                tempo, key, meter, pitches, w.source_file,
            ),
        )

    conn.commit()
    conn.close()

    return {
        "works_loaded": len(works),
        "parse_errors": errors,
        "catalogues": sorted({w.catalogue for w in works}),
    }


if __name__ == "__main__":
    import sys
    data = sys.argv[1] if len(sys.argv) > 1 else "data"
    db = sys.argv[2] if len(sys.argv) > 2 else "catalogue.db"
    report = build_database(data, db)
    print(f"Database built: {db}")
    print(f"  Works loaded: {report['works_loaded']}")
    print(f"  Catalogues:   {', '.join(report['catalogues'])}")
    print(f"  Parse errors: {len(report['parse_errors'])}")
    for fname, msg in report["parse_errors"]:
        print(f"    - {fname}")
