"""
Works Discovery Engine (prototype "black box").

This is the technical barrier feature, implemented here as a simple but real
black box, exactly as recommended for a first prototype: pitch sequences go in,
similarity scores come out. The internals are deliberately simple for now and
can be replaced with a more sophisticated melodic-similarity algorithm later
without changing the interface.

Method (prototype version):
- Convert each incipit's pitch names to a sequence of MIDI-like integers.
- Represent each melody as its sequence of intervals (pitch differences),
  which makes the comparison transposition-invariant.
- Compute similarity between two melodies using a normalised edit distance
  on their interval sequences.

This is a standard, defensible approach (interval-based melodic comparison is
well established in music information retrieval). It is not claimed to be
state of the art — that honesty is part of the evaluation.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

# Semitone offsets within an octave for natural pitch classes
_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pitch_to_midi(pitch: str) -> int | None:
    """Convert a pitch name like 'F#5' or 'D5' to a MIDI-like integer."""
    if not pitch:
        return None
    name = pitch[0].upper()
    if name not in _PITCH_CLASS:
        return None
    semitone = _PITCH_CLASS[name]
    rest = pitch[1:]
    # accidentals
    while rest and rest[0] in "#b":
        semitone += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    try:
        octave = int(rest)
    except ValueError:
        return None
    return semitone + (octave + 1) * 12


def to_intervals(pitches: list[str]) -> list[int]:
    """Convert a pitch sequence to an interval sequence (transposition-invariant)."""
    midi = [m for p in pitches if (m := pitch_to_midi(p)) is not None]
    return [b - a for a, b in zip(midi, midi[1:])]


def _edit_distance(a: list[int], b: list[int]) -> int:
    """Standard Levenshtein edit distance between two integer sequences."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def _contour(intervals: list[int]) -> list[int]:
    """Reduce intervals to up/down/same contour (-1/0/+1) — coarser, more robust."""
    return [(1 if i > 0 else -1 if i < 0 else 0) for i in intervals]


def similarity(pitches_a: list[str], pitches_b: list[str]) -> float:
    """
    Return a similarity score in [0, 1] between two incipits.
    1.0 = identical melodic contour; 0.0 = maximally different.

    The prototype combines two standard MIR ideas: exact interval matching
    and melodic-contour matching (Parsons-style up/down/same). Contour is
    more forgiving of small differences, which suits short, noisy incipits.
    The two are averaged. This is intentionally simple — a placeholder black
    box that can be upgraded later.
    """
    ia, ib = to_intervals(pitches_a), to_intervals(pitches_b)
    if not ia and not ib:
        return 1.0
    if not ia or not ib:
        return 0.0
    # Exact interval similarity
    interval_sim = 1.0 - _edit_distance(ia, ib) / max(len(ia), len(ib))
    # Contour similarity (coarser, more robust to small variation)
    ca, cb = _contour(ia), _contour(ib)
    contour_sim = 1.0 - _edit_distance(ca, cb) / max(len(ca), len(cb))
    return round((interval_sim + contour_sim) / 2, 4)


def find_similar(db_path: str | Path, work_id: str, top_n: int = 3) -> list[dict]:
    """
    Find the works most melodically similar to the given work.

    Returns a list of {work_id, title, composer, score}, highest score first.
    This is the "numbers in, numbers out" black box the API will call.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT work_id, title_main, composer, incipit_pitches FROM works"
    ).fetchall()
    conn.close()

    target = next((r for r in rows if r["work_id"] == work_id), None)
    if target is None:
        return []
    target_pitches = json.loads(target["incipit_pitches"] or "[]")
    if not target_pitches:
        return []

    scored = []
    for r in rows:
        if r["work_id"] == work_id:
            continue
        pitches = json.loads(r["incipit_pitches"] or "[]")
        if not pitches:
            continue
        scored.append({
            "work_id": r["work_id"],
            "title": r["title_main"],
            "composer": r["composer"],
            "score": round(similarity(target_pitches, pitches), 3),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


if __name__ == "__main__":
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else "catalogue.db"
    wid = sys.argv[2] if len(sys.argv) > 2 else "CNW 131"
    print(f"Works most similar to {wid}:")
    for s in find_similar(db, wid):
        print(f"  {s['score']:.3f}  {s['work_id']}: {s['title']} ({s['composer']})")
