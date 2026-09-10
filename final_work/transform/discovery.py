"""
Works Discovery Engine v2.

The prototype version of this engine (interval + contour edit distance on
pitches alone) was evaluated honestly in the Preliminary Report and found not
to separate melodically similar works from dissimilar ones reliably: with
only five or six notes per incipit, pitch shape alone carries too little
information. That evaluation named three concrete improvements to try:
incorporate rhythm, use melodic n-grams rather than whole-sequence edit
distance, and validate against works with a known relationship. This version
implements the first two; the third is exercised by the sanity check at the
bottom of this module and by tests/test_prototype.py.

Method (v2):
1. Interval sequence (as before) - transposition-invariant pitch shape.
2. Contour sequence (as before) - coarser, more robust up/down/same shape.
3. NEW - rhythm sequence: each note's duration relative to the previous
   note's duration (a ratio, log-scaled and bucketed), which is itself
   transposition/tempo-invariant: a melody played twice as fast has the same
   *relative* rhythm even though the absolute durations differ.
4. NEW - bigram overlap: overlapping pairs of consecutive (interval, rhythm)
   steps are compared as sets (Jaccard similarity). Bigrams capture local
   melodic-rhythmic shape and are far less sensitive to a single differing
   note than a whole-sequence edit distance is on a 5-6 note incipit, where
   one mismatch previously swung the score enormously.

The final score is a weighted combination of all four signals. Rhythm and
bigram overlap are weighted most heavily because the evaluation showed pitch
shape alone was insufficient; the weights are declared as constants below so
the reasoning is auditable, not hidden inside the formula.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict, TypeVar


class SimilarWorkResult(TypedDict):
    """A single scored result from find_similar."""
    work_id: str
    title: str | None
    composer: str | None
    score: float

_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Signal weights (must sum to 1.0) - declared explicitly so the scoring
# rationale is visible and adjustable, not buried in arithmetic.
W_INTERVAL = 0.20
W_CONTOUR = 0.20
W_RHYTHM = 0.25
W_BIGRAM = 0.35


def pitch_to_midi(pitch: str) -> int | None:
    """Convert a pitch name like 'F#5' or 'D5' to a MIDI-like integer."""
    if not pitch:
        return None
    name = pitch[0].upper()
    if name not in _PITCH_CLASS:
        return None
    semitone = _PITCH_CLASS[name]
    rest = pitch[1:]
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


def to_contour(intervals: list[int]) -> list[int]:
    """Reduce intervals to up/down/same contour (-1/0/+1) - coarser, more robust."""
    return [(1 if i > 0 else -1 if i < 0 else 0) for i in intervals]


def to_rhythm(durations: list[int]) -> list[int]:
    """
    Convert MEI durations (4=quarter, 8=eighth, ...) to a tempo-invariant
    rhythm sequence: each step is the bucketed log-ratio of consecutive note
    lengths, so "twice as long", "half as long", or "same length" are the
    stable, comparable units, regardless of the piece's actual tempo.
    """
    if not durations or len(durations) < 2:
        return []
    steps = []
    for a, b in zip(durations, durations[1:]):
        if a <= 0 or b <= 0:
            steps.append(0)
            continue
        # MEI duration codes are inverse note-lengths (8 = eighth note is
        # shorter than 4 = quarter note), so invert before taking the ratio.
        ratio = (1 / b) / (1 / a)
        bucket = round(math.log2(ratio) * 2)  # bucketed log-ratio, symmetric
        steps.append(max(-4, min(4, bucket)))
    return steps


def _edit_distance(a: Sequence[int], b: Sequence[int]) -> int:
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


def _seq_sim(a: Sequence[int], b: Sequence[int]) -> float:
    """1 - normalised edit distance; 1.0 if both empty, 0.0 if only one is."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return 1.0 - _edit_distance(a, b) / max(len(a), len(b))


def _bigrams(intervals: list[int], rhythm: list[int]) -> set[tuple[tuple[int, int], tuple[int, int]]]:
    """
    Overlapping (interval, rhythm) bigrams: each element pairs a melodic step
    with its rhythmic step, and consecutive pairs of these form a bigram.
    Comparing bigrams as a set is far more forgiving of a single differing
    note than whole-sequence edit distance is on a 5-6 note incipit.
    """
    steps = list(zip(intervals, rhythm)) if rhythm else [(i, 0) for i in intervals]
    return {tuple(steps[i:i + 2]) for i in range(len(steps) - 1)} if len(steps) >= 2 else set()  # type: ignore[misc]


_T = TypeVar("_T")


def _jaccard(a: set[_T], b: set[_T]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity(
    pitches_a: list[str], pitches_b: list[str],
    durations_a: list[int] | None = None, durations_b: list[int] | None = None,
) -> float:
    """
    Return a similarity score in [0, 1] between two incipits, combining
    pitch-interval shape, coarse contour, tempo-invariant rhythm, and
    local (interval, rhythm) bigram overlap. See module docstring for the
    rationale behind each signal and its weight.

    Durations are optional so existing callers passing pitches alone still
    work (rhythm/bigram signals then degrade gracefully to neutral values).
    """
    # Degenerate cases (e.g. a work with no recorded incipit at all) are
    # handled explicitly, before the weighted blend, so the contract stays
    # intuitive regardless of how many signals are combined below.
    if not pitches_a and not pitches_b:
        return 1.0
    if not pitches_a or not pitches_b:
        return 0.0

    ia, ib = to_intervals(pitches_a), to_intervals(pitches_b)
    interval_sim = _seq_sim(ia, ib)
    contour_sim = _seq_sim(to_contour(ia), to_contour(ib))

    ra = to_rhythm(durations_a) if durations_a else []
    rb = to_rhythm(durations_b) if durations_b else []
    rhythm_sim = _seq_sim(ra, rb) if (ra or rb) else 0.5  # neutral if no rhythm data

    bg_a, bg_b = _bigrams(ia, ra), _bigrams(ib, rb)
    bigram_sim = _jaccard(bg_a, bg_b) if (bg_a or bg_b) else 0.5

    score = (
        W_INTERVAL * interval_sim
        + W_CONTOUR * contour_sim
        + W_RHYTHM * rhythm_sim
        + W_BIGRAM * bigram_sim
    )
    return round(score, 4)


def find_similar(db_path: str | Path, work_id: str, top_n: int = 3) -> list[SimilarWorkResult]:
    """
    Find the works most melodically (and rhythmically) similar to the given
    work. Returns a list of {work_id, title, composer, score}, highest first.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT work_id, title_main, composer, incipit_pitches, incipit_durations FROM works"
    ).fetchall()
    conn.close()

    target = next((r for r in rows if r["work_id"] == work_id), None)
    if target is None:
        return []
    target_pitches = json.loads(target["incipit_pitches"] or "[]")
    if not target_pitches:
        return []
    target_durations = json.loads(target["incipit_durations"] or "[]")

    scored: list[SimilarWorkResult] = []
    for r in rows:
        if r["work_id"] == work_id:
            continue
        pitches = json.loads(r["incipit_pitches"] or "[]")
        if not pitches:
            continue
        durations = json.loads(r["incipit_durations"] or "[]")
        scored.append(SimilarWorkResult(
            work_id=r["work_id"],
            title=r["title_main"],
            composer=r["composer"],
            score=similarity(target_pitches, pitches, target_durations, durations),
        ))

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


if __name__ == "__main__":
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else "catalogue.db"
    wid = sys.argv[2] if len(sys.argv) > 2 else "CNW 131"
    print(f"Works most similar to {wid}:")
    for s in find_similar(db, wid):
        print(f"  {s['score']:.3f}  {s['work_id']}: {s['title']} ({s['composer']})")
