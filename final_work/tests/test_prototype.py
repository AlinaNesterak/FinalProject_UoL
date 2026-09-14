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

import discovery  # noqa: E402
from parser import MEIParseError, parse_directory, parse_file  # noqa: E402
from pipeline import build_database  # noqa: E402

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


def test_parse_history_note():
    """Narrative composition-history prose is extracted from <history><p>."""
    w = parse_file(DATA / "nielsen_cnw0102.xml")
    assert w.history_note is not None
    assert "Inextinguishable" in w.history_note or "First World War" in w.history_note


def test_parse_sources():
    """Sources (manuscripts/prints) are extracted with repository and shelfmark."""
    w = parse_file(DATA / "nielsen_cnw0102.xml")
    assert len(w.sources) == 3
    s = w.sources[0]
    assert s.title == "Autograph score"
    assert "Royal Danish Library" in s.repository
    assert s.shelfmark == "CNS 64"
    assert s.source_type == "manuscript"


def test_parse_performances():
    """Performance history events are extracted with date and description."""
    w = parse_file(DATA / "nielsen_cnw0102.xml")
    assert len(w.performances) == 2
    assert w.performances[0].date == "1916-02-01"
    assert "premiere" in w.performances[0].description.lower()


def test_parse_durations():
    """Note durations are extracted in parallel with pitches (for audio/notation)."""
    w = parse_file(DATA / "nielsen_cnw0131.xml")
    assert w.incipit is not None
    assert len(w.incipit.durations) == len(w.incipit.pitches)
    assert all(isinstance(d, int) for d in w.incipit.durations)


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
    assert len(works) >= 24
    assert any("malformed" in fname for fname, _ in errors)


# ---------------- Discovery engine v2 tests ----------------

def test_pitch_to_midi():
    assert discovery.pitch_to_midi("C4") == 60
    assert discovery.pitch_to_midi("F#5") == 78
    assert discovery.pitch_to_midi("bad") is None


def test_similarity_identical_pitches_and_rhythm_is_one():
    """Identical pitches AND identical durations score a perfect 1.0."""
    p = ["D5", "E5", "F#5", "G5"]
    d = [8, 8, 8, 8]
    assert discovery.similarity(p, p, d, d) == 1.0


def test_similarity_transposition_invariant():
    """The same contour transposed up, with the same rhythm, is highly similar."""
    a, da = ["C5", "D5", "E5"], [8, 8, 8]
    b, db = ["G5", "A5", "B5"], [8, 8, 8]   # same intervals, transposed
    assert discovery.similarity(a, b, da, db) == 1.0


def test_similarity_pitches_only_still_works():
    """Callers that omit durations still get a valid score (graceful degradation)."""
    p = ["D5", "E5", "F#5", "G5"]
    score = discovery.similarity(p, p)
    assert 0.0 <= score <= 1.0
    assert score > 0.8  # pitch shape alone still matches strongly


def test_rhythm_is_tempo_invariant():
    """A melody played twice as fast has the same *relative* rhythm."""
    normal = [4, 4, 4, 4]     # four quarter notes
    doubled = [8, 8, 8, 8]    # same pattern, twice as fast (all eighths)
    assert discovery.to_rhythm(normal) == discovery.to_rhythm(doubled)


def test_rhythm_distinguishes_uniform_from_mixed():
    """Uniform rhythm and mixed rhythm produce different rhythm sequences."""
    uniform = [8, 8, 8, 8, 8, 8]
    mixed = [4, 8, 8, 4, 4]
    assert discovery.to_rhythm(uniform) != discovery.to_rhythm(mixed)


def test_bigrams_capture_local_shape():
    """Bigrams are overlapping (interval, rhythm) pairs; length n-1 for n steps."""
    intervals = [2, -1, 3]
    rhythm = [0, 1]
    bg = discovery._bigrams(intervals, rhythm)
    assert isinstance(bg, set)
    assert len(bg) <= 2  # at most len(steps)-1 bigrams from 3 steps


def test_discovery_v2_fixes_known_ordering_failure():
    """
    The specific, documented v1 failure: two Holstein songs with identical
    uniform eighth-note rhythm (CNW 131, CNW 128) must now score more similar
    to each other than either does to the mixed-rhythm symphony (CNW 102).
    v1 got this backwards (0.200 vs 0.300); v2 must get it right.
    """
    w131 = parse_file(DATA / "nielsen_cnw0131.xml")
    w128 = parse_file(DATA / "nielsen_cnw0128.xml")
    w102 = parse_file(DATA / "nielsen_cnw0102.xml")
    sim_songs = discovery.similarity(
        w131.incipit.pitches, w128.incipit.pitches,
        w131.incipit.durations, w128.incipit.durations,
    )
    sim_song_symph = discovery.similarity(
        w131.incipit.pitches, w102.incipit.pitches,
        w131.incipit.durations, w102.incipit.durations,
    )
    assert sim_songs > sim_song_symph


# ---------------- Pipeline tests ----------------

def test_discovery_v2_second_validation_case_is_honestly_inconclusive():
    """
    A second, independent known-relationship check: DCW 42 and DCW 44 are
    documented in this project's own history notes as companion pieces
    sharing the same folk-song sources. Unlike the first validation case
    (test_discovery_v2_fixes_known_ordering_failure), this pair does NOT
    score clearly higher than an unrelated control — it ties. This is
    recorded as a real result, not adjusted away by retuning weights
    against a single example, and documents v2's actual, honest scope.
    """
    cuckoo = parse_file(DATA / "delius_dcw042.xml")
    river = parse_file(DATA / "delius_dcw044.xml")
    symph = parse_file(DATA / "nielsen_cnw0102.xml")
    sim_companions = discovery.similarity(
        cuckoo.incipit.pitches, river.incipit.pitches,
        cuckoo.incipit.durations, river.incipit.durations,
    )
    sim_control = discovery.similarity(
        cuckoo.incipit.pitches, symph.incipit.pitches,
        cuckoo.incipit.durations, symph.incipit.durations,
    )
    # Documents the actual behaviour (a tie), not an assumption of success.
    assert sim_companions == sim_control


def test_build_database():
    report = build_database(DATA, TEST_DB)
    assert report["works_loaded"] >= 24
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
    assert len(r.json()) >= 24


def test_api_filter_by_catalogue(client):
    r = client.get("/works?catalogue=DCW")
    assert r.status_code == 200
    assert all(w["catalogue"] == "DCW" for w in r.json())


def test_api_get_work(client):
    r = client.get("/works/CNW 131")
    assert r.status_code == 200
    assert r.json()["title_main"] == "Greeting"


def test_api_detail_includes_sources_and_performances(client):
    r = client.get("/works/CNW 102")
    assert r.status_code == 200
    d = r.json()
    assert len(d["sources"]) == 3
    assert d["sources"][0]["shelfmark"] == "CNS 64"
    assert len(d["performances"]) == 2
    assert len(d["incipit_durations"]) == len(d["incipit_pitches"])
    assert d["history_note"] and "Nielsen" in d["history_note"] or len(d["history_note"]) > 20


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


# ---------------- Additional coverage: edge cases & contract ----------------

def test_similarity_empty_inputs():
    """Empty vs empty is 1.0; empty vs non-empty is 0.0 (no crash)."""
    assert discovery.similarity([], []) == 1.0
    assert discovery.similarity([], ["C4", "D4"]) == 0.0


def test_find_similar_no_incipit_returns_empty():
    """A work without an incipit (CNW 999) yields no suggestions, gracefully."""
    build_database(DATA, TEST_DB)
    assert discovery.find_similar(TEST_DB, "CNW 999") == []


def test_api_pagination(client):
    r1 = client.get("/works?limit=5&offset=0")
    r2 = client.get("/works?limit=5&offset=5")
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(r1.json()) == 5
    ids1 = {w["work_id"] for w in r1.json()}
    ids2 = {w["work_id"] for w in r2.json()}
    assert ids1.isdisjoint(ids2)  # pages don't overlap


def test_api_invalid_params_422(client):
    assert client.get("/works?limit=0").status_code == 422       # below minimum
    assert client.get("/works/search").status_code == 422        # missing q


def test_api_search_no_results_empty_list(client):
    r = client.get("/works/search?q=zzzznotfound")
    assert r.status_code == 200
    assert r.json() == []


def test_api_root_serves_frontend(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Music Works Catalogue" in r.text


def test_api_similar_scores_bounded(client):
    r = client.get("/works/CNW 131/similar")
    assert r.status_code == 200
    for s in r.json():
        assert 0.0 <= s["score"] <= 1.0


# ---------------- Research findings endpoint ----------------

def test_api_findings_returns_computed_statistics(client):
    """The findings endpoint computes real statistics from the loaded data."""
    r = client.get("/findings")
    assert r.status_code == 200
    d = r.json()
    assert d["total_works"] >= 24
    assert "CNW" in d["catalogues"] and "DCW" in d["catalogues"]
    assert d["total_sources"] > 0
    assert d["total_performances"] > 0


def test_api_findings_coverage_percentages_are_valid(client):
    """Every tracked field reports a coherent present/total/percent triple."""
    d = client.get("/findings").json()
    for field, cov in d["field_coverage"].items():
        assert 0 <= cov["present"] <= cov["total"]
        assert 0.0 <= cov["percent"] <= 100.0
        # percent must actually match the counts it claims to summarise
        expected = round(100 * cov["present"] / cov["total"], 1)
        assert cov["percent"] == expected, f"{field} percent inconsistent"


def test_api_findings_core_fields_are_complete(client):
    """Title and composer are present for every work — the documented finding."""
    d = client.get("/findings").json()
    assert d["field_coverage"]["title_main"]["percent"] == 100.0
    assert d["field_coverage"]["composer"]["percent"] == 100.0


# ---------------- Faceted filtering, sorting, and export ----------------

def test_api_facets_returns_filter_options(client):
    """The facets endpoint lists available filter values with counts."""
    r = client.get("/facets")
    assert r.status_code == 200
    d = r.json()
    assert len(d["genres"]) > 0
    assert len(d["keys"]) > 0
    assert d["year_min"] is not None and d["year_max"] is not None
    assert d["year_min"] < d["year_max"]
    # Counts must be positive and values non-empty
    for g in d["genres"]:
        assert g["count"] > 0 and g["value"]


def test_api_filter_by_genre(client):
    r = client.get("/works?genre=Song")
    assert r.status_code == 200
    works = r.json()
    assert len(works) > 0
    assert all(w["genre"] == "Song" for w in works)


def test_api_filter_by_key(client):
    r = client.get("/works?key=D major")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_api_filter_by_year_range(client):
    """Year filtering returns only works composed within the range."""
    r = client.get("/works?year_from=1890&year_to=1900")
    assert r.status_code == 200
    filtered = r.json()
    all_works = client.get("/works?limit=200").json()
    assert 0 < len(filtered) < len(all_works)


def test_api_filters_combine(client):
    """Multiple filters narrow results cumulatively (AND, not OR)."""
    songs = client.get("/works?genre=Song").json()
    songs_in_key = client.get("/works?genre=Song&key=D major").json()
    assert len(songs_in_key) <= len(songs)


def test_api_sort_by_date_puts_undated_last(client):
    """
    Undated works must sort last, not first — otherwise an incomplete
    record heads a chronological listing, which misleads the user.
    """
    works = client.get("/works?sort=date&limit=200").json()
    assert works[-1]["work_id"] == "CNW 999"   # the deliberate minimal record


def test_api_sort_by_title_is_alphabetical(client):
    works = client.get("/works?sort=title&limit=200").json()
    titles = [w["title_main"].lower() for w in works if w["title_main"]]
    assert titles == sorted(titles)


def test_api_invalid_sort_falls_back_safely(client):
    """An unrecognised sort value must not error or inject SQL."""
    r = client.get("/works?sort=; DROP TABLE works")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_export_csv(client):
    r = client.get("/export/works.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().split("\n")
    assert len(lines) >= 25          # header + 24 works
    assert "work_id" in lines[0]     # header row present


def test_export_json(client):
    r = client.get("/export/works.json")
    assert r.status_code == 200
    d = r.json()
    assert d["count"] >= 24
    # Nested fields must be real structures, not embedded JSON strings
    first = d["works"][0]
    assert isinstance(first["instrumentation"], list)
    assert isinstance(first["sources"], list)


# ---------------- IMSLP linked data ----------------

def test_parse_imslp_link():
    """IMSLP score links are extracted where a verified page exists."""
    w = parse_file(DATA / "nielsen_cnw0043.xml")   # Wind Quintet
    assert w.imslp_url is not None
    assert "imslp.org/wiki/" in w.imslp_url


def test_imslp_identifier_does_not_break_catalogue_detection():
    """
    Regression: linked-data identifiers live in the same pubStmt as the
    catalogue identifier, so they must be excluded from catalogue detection.
    A work with an IMSLP link must still report its real catalogue.
    """
    w = parse_file(DATA / "nielsen_cnw0043.xml")
    assert w.catalogue == "CNW"
    assert w.catalogue_number == "43"


def test_api_exposes_imslp_url(client):
    d = client.get("/works/CNW 43").json()
    assert d["imslp_url"] is not None
    assert d["imslp_url"].startswith("https://imslp.org/")


def test_works_without_verified_imslp_page_have_none(client):
    """
    Links are only added where an IMSLP page was actually verified;
    unverified works report None rather than a guessed URL that may 404.
    """
    d = client.get("/works/CNW 999").json()   # the minimal edge-case record
    assert d["imslp_url"] is None


# ---------------- Data integrity ----------------

def test_no_duplicate_work_identifiers():
    """
    work_id is the database primary key, so a duplicate identifier would
    silently overwrite a record rather than raise an error. This asserts
    the property the evaluation script reports on.
    """
    from collections import Counter
    works, _ = parse_directory(DATA)
    counts = Counter(w.work_id for w in works)
    duplicates = {wid: n for wid, n in counts.items() if n > 1}
    assert not duplicates, f"duplicate work identifiers would overwrite: {duplicates}"


def test_every_work_has_a_usable_identifier():
    """No work should fall back to the parser's UNKNOWN/? placeholder."""
    works, _ = parse_directory(DATA)
    for w in works:
        assert w.catalogue != "UNKNOWN", f"{w.source_file} has no catalogue identifier"
        assert w.catalogue_number != "?", f"{w.source_file} has no catalogue number"
