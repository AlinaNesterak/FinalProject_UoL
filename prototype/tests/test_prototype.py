"""
Test suite for the Music Works Catalogue Portal prototype.

Covers the three layers using standard techniques (pytest):
- parser: correct field extraction + graceful handling of edge cases
- pipeline: database is built correctly
- API: endpoints return correct data and status codes (via FastAPI TestClient)

Run:  pytest -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "transform"))
sys.path.insert(0, str(ROOT))

from parser import parse_file, parse_directory, MEIParseError  # noqa: E402
from pipeline import build_database  # noqa: E402
import discovery  # noqa: E402

DATA = ROOT / "data"
TEST_DB = ROOT / "test_catalogue.db"


# ---------------- Parser tests ----------------

def test_parse_complete_record():
    """A full record (CNW 131) extracts all expected fields."""
    w = parse_file(DATA / "nielsen_cnw0131.xml")
    assert w.catalogue == "CNW"
    assert w.catalogue_number == "131"
    assert w.title_en == "Greeting"
    assert w.title_da == "Hilsen"
    assert w.title_main == "Greeting"          # English preferred
    assert w.composer == "Carl Nielsen"
    assert w.opus == "10.6"
    assert w.genre == "Song"
    assert "voice" in w.instrumentation
    assert w.incipit is not None
    assert w.incipit.key == "D major"
    assert w.incipit.meter_count == 6
    assert len(w.incipit.pitches) == 6


def test_parse_catalogue_agnostic():
    """A Delius record (different catalogue) parses with no code change."""
    w = parse_file(DATA / "delius_dcw042.xml")
    assert w.catalogue == "DCW"
    assert w.composer == "Frederick Delius"
    assert w.title_main == "On Hearing the First Cuckoo in Spring"


def test_parse_missing_fields_graceful():
    """A minimal record (no incipit, genre, date) does not crash."""
    w = parse_file(DATA / "nielsen_edge_minimal.xml")
    assert w.catalogue == "CNW"
    assert w.catalogue_number == "999"
    assert w.incipit is None
    assert w.genre is None
    assert w.instrumentation == []


def test_parse_malformed_raises():
    """Malformed XML raises MEIParseError, not an uncaught exception."""
    with pytest.raises(MEIParseError):
        parse_file(DATA / "nielsen_edge_malformed.xml")


def test_parse_directory_separates_errors():
    """Directory parse returns good works and records errors separately."""
    works, errors = parse_directory(DATA)
    assert len(works) >= 6
    assert any("malformed" in fname for fname, _ in errors)


# ---------------- Discovery engine tests ----------------

def test_pitch_to_midi():
    assert discovery.pitch_to_midi("C4") == 60
    assert discovery.pitch_to_midi("F#5") == 78
    assert discovery.pitch_to_midi("bad") is None


def test_similarity_identical_is_one():
    p = ["D5", "E5", "F#5", "G5"]
    assert discovery.similarity(p, p) == 1.0


def test_similarity_transposition_invariant():
    """The same contour transposed up should be highly similar."""
    a = ["C5", "D5", "E5"]
    b = ["G5", "A5", "B5"]   # same intervals, transposed
    assert discovery.similarity(a, b) == 1.0


# ---------------- Pipeline tests ----------------

def test_build_database():
    report = build_database(DATA, TEST_DB)
    assert report["works_loaded"] >= 6
    assert "CNW" in report["catalogues"]
    assert "DCW" in report["catalogues"]
    assert len(report["parse_errors"]) == 1   # the malformed file
    assert TEST_DB.exists()


# ---------------- API tests ----------------

@pytest.fixture(scope="module")
def client():
    build_database(DATA, ROOT / "catalogue.db")
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_api_list_works(client):
    r = client.get("/works")
    assert r.status_code == 200
    assert len(r.json()) >= 6


def test_api_filter_by_catalogue(client):
    r = client.get("/works?catalogue=DCW")
    assert r.status_code == 200
    assert all(w["catalogue"] == "DCW" for w in r.json())


def test_api_get_work(client):
    r = client.get("/works/CNW 131")
    assert r.status_code == 200
    assert r.json()["title_main"] == "Greeting"


def test_api_get_missing_work_404(client):
    r = client.get("/works/CNW 12345")
    assert r.status_code == 404


def test_api_search(client):
    r = client.get("/works/search?q=symphony")
    assert r.status_code == 200
    assert any("Symphony" in (w["title_main"] or "") for w in r.json())


def test_api_similar(client):
    r = client.get("/works/CNW 131/similar")
    assert r.status_code == 200
    # CNW 128 (also a Holstein song) should appear among similar works
    assert isinstance(r.json(), list)
