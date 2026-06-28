"""
MEI XML parser for the Music Works Catalogue Portal prototype.

This module tackles the central technical challenge of the project: extracting
structured catalogue data from MEI (Music Encoding Initiative) XML files produced
by MerMEId. It handles the MEI 4.0 metadata model, including multilingual titles,
catalogue identifiers, instrumentation, and musical incipits.

Design notes:
- Parsing is defensive: missing fields return None rather than raising, so that
  incomplete real-world records (which are common) are handled gracefully.
- Malformed XML is caught and reported, not allowed to crash the pipeline.
- The parser is catalogue-agnostic: it reads the identifier @type to determine
  the catalogue (CNW, DCW, etc.), so new catalogues need no code changes.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lxml import etree

# MEI 4.0 namespace
MEI_NS = "http://www.music-encoding.org/ns/mei"
NS = {"mei": MEI_NS}


@dataclass
class Incipit:
    """A musical incipit: the opening notes of a work."""
    tempo: Optional[str] = None
    meter_count: Optional[int] = None
    meter_unit: Optional[int] = None
    key: Optional[str] = None
    text_da: Optional[str] = None
    text_en: Optional[str] = None
    # Pitch sequence as scientific pitch names, e.g. ["D5", "D5", "F#5", ...]
    pitches: list[str] = field(default_factory=list)


@dataclass
class Work:
    """A single catalogued musical work."""
    catalogue: str                       # e.g. "CNW", "DCW"
    catalogue_number: str                # e.g. "131"
    work_id: str                         # e.g. "CNW 131"
    title_main: Optional[str] = None     # primary title (English preferred, else any)
    title_da: Optional[str] = None
    title_en: Optional[str] = None
    composer: Optional[str] = None
    composer_uri: Optional[str] = None
    opus: Optional[str] = None
    genre: Optional[str] = None
    date_text: Optional[str] = None
    date_notbefore: Optional[str] = None
    date_notafter: Optional[str] = None
    instrumentation: list[str] = field(default_factory=list)
    incipit: Optional[Incipit] = None
    source_file: Optional[str] = None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        return d


class MEIParseError(Exception):
    """Raised when an MEI file cannot be parsed at all (malformed XML)."""


def _text(el) -> Optional[str]:
    """Safely extract stripped text from an element, or None."""
    if el is None:
        return None
    txt = el.text
    return txt.strip() if txt and txt.strip() else None


def _find(root, xpath: str):
    return root.find(xpath, namespaces=NS)


def _findall(root, xpath: str):
    return root.findall(xpath, namespaces=NS)


# Map MEI accidental codes to symbols
_ACCID = {"s": "#", "f": "b", "ss": "##", "ff": "bb", "n": ""}


def _parse_incipit(work_el) -> Optional[Incipit]:
    """Extract the incipit (tempo, meter, key, text, and pitch sequence)."""
    incip_el = _find(work_el, "mei:incip")
    if incip_el is None:
        return None

    inc = Incipit()
    inc.tempo = _text(_find(incip_el, "mei:tempo"))

    meter_el = _find(incip_el, "mei:meter")
    if meter_el is not None:
        count = meter_el.get("count")
        unit = meter_el.get("unit")
        inc.meter_count = int(count) if count and count.isdigit() else None
        inc.meter_unit = int(unit) if unit and unit.isdigit() else None

    inc.key = _text(_find(incip_el, "mei:key"))

    for it in _findall(incip_el, "mei:incipText"):
        lang = it.get("{http://www.w3.org/XML/1998/namespace}lang")
        if lang == "da":
            inc.text_da = _text(it)
        elif lang == "en":
            inc.text_en = _text(it)

    # Extract the pitch sequence from the encoded score (this is what the
    # Works Discovery Engine will later use for melodic similarity).
    for note in _findall(incip_el, ".//mei:note"):
        pname = note.get("pname")
        octave = note.get("oct")
        accid = note.get("accid", "")
        if pname and octave:
            symbol = _ACCID.get(accid, "")
            inc.pitches.append(f"{pname.upper()}{symbol}{octave}")

    return inc


def parse_file(path: str | Path) -> Work:
    """
    Parse a single MEI XML file into a Work object.

    Raises MEIParseError if the file is not well-formed XML.
    Missing individual fields are tolerated (returned as None / empty).
    """
    path = Path(path)
    try:
        tree = etree.parse(str(path))
    except etree.XMLSyntaxError as exc:
        raise MEIParseError(f"Malformed XML in {path.name}: {exc}") from exc

    root = tree.getroot()

    # --- Identifier / catalogue (catalogue-agnostic) ---
    catalogue = "UNKNOWN"
    cat_number = "?"
    opus = None
    for ident in _findall(root, ".//mei:pubStmt/mei:identifier"):
        itype = (ident.get("type") or "").upper()
        val = _text(ident)
        if itype == "OPUS":
            opus = val
        elif itype and val:
            catalogue = itype
            cat_number = val

    work_id = f"{catalogue} {cat_number}"

    work = Work(
        catalogue=catalogue,
        catalogue_number=cat_number,
        work_id=work_id,
        opus=opus,
        source_file=path.name,
    )

    # --- Work element ---
    work_el = _find(root, ".//mei:workList/mei:work")
    if work_el is None:
        # No work data at all; return the skeleton with just the identifier.
        return work

    # Titles (multilingual)
    for title in _findall(work_el, "mei:title"):
        lang = title.get("{http://www.w3.org/XML/1998/namespace}lang")
        ttype = title.get("type")
        if ttype and ttype != "main":
            continue
        if lang == "da":
            work.title_da = _text(title)
        elif lang == "en":
            work.title_en = _text(title)
    # Prefer English as the main display title, else Danish
    work.title_main = work.title_en or work.title_da

    # Composer
    comp = _find(work_el, "mei:composer")
    if comp is not None:
        work.composer = _text(comp)
        work.composer_uri = comp.get("auth.uri")

    # Genre
    genre = _find(work_el, ".//mei:classification//mei:term[@type='genre']")
    if genre is None:
        genre = _find(work_el, ".//mei:term")
    work.genre = _text(genre)

    # Creation date
    date_el = _find(work_el, ".//mei:creation/mei:date")
    if date_el is not None:
        work.date_text = _text(date_el)
        work.date_notbefore = date_el.get("notbefore") or date_el.get("isodate")
        work.date_notafter = date_el.get("notafter") or date_el.get("isodate")

    # Instrumentation
    for pr in _findall(work_el, ".//mei:perfMedium//mei:perfRes"):
        name = _text(pr)
        if name:
            work.instrumentation.append(name)

    # Incipit (the hard part — feeds the discovery engine)
    work.incipit = _parse_incipit(work_el)

    return work


def parse_directory(data_dir: str | Path) -> tuple[list[Work], list[tuple[str, str]]]:
    """
    Parse all .xml files in a directory.

    Returns (works, errors) where errors is a list of (filename, message)
    for files that could not be parsed. This separation lets the pipeline
    report robustly on partial failures rather than crashing.
    """
    data_dir = Path(data_dir)
    works: list[Work] = []
    errors: list[tuple[str, str]] = []

    for xml_file in sorted(data_dir.glob("*.xml")):
        try:
            works.append(parse_file(xml_file))
        except MEIParseError as exc:
            errors.append((xml_file.name, str(exc)))

    return works, errors


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "data"
    works, errors = parse_directory(target)
    print(f"Parsed {len(works)} works, {len(errors)} errors\n")
    for w in works:
        inc = f", incipit: {len(w.incipit.pitches)} notes" if w.incipit else ", no incipit"
        print(f"  {w.work_id}: {w.title_main or '(untitled)'} [{w.genre or '?'}]{inc}")
    for fname, msg in errors:
        print(f"  ERROR {fname}: {msg}")
