# Music Works Catalogue Portal

A modern, catalogue-agnostic web portal for exploring classical composers' works encoded in MEI XML (Music Encoding Initiative). This project transforms legacy MerMEId catalogue data into a clean, queryable system with a REST API, interactive web interface, and a Works Discovery Engine.

Built as a Computer Science Final Year Project, 2025–2026.

---

## The problem

Thematic catalogues — systematic lists of everything a composer wrote, including manuscripts, performances, and musical themes — are essential scholarly resources that have existed for centuries. In 2014, the Danish Royal Library built **MerMEId**, a Java-based XML system to digitise these catalogues using the MEI standard. It successfully published catalogues for Carl Nielsen, Frederick Delius, and others.

When the Danish library stopped development, the publication pipeline broke. The data still exists in MEI XML — but users can no longer access it through a working, modern interface.

This project addresses six documented problems identified from academic literature (Stadler & Jettka 2023; Krabbe & Geertinger 2012):

| # | Problem | Source |
|---|---------|--------|
| P1 | Broken publication pipeline | Stadler & Jettka 2023 |
| P2 | Technical debt & obsolete stack (Java/XForms) | Stadler & Jettka 2023 |
| P3 | No machine-readable API | Krabbe & Geertinger 2012 |
| P4 | Access limited to XML specialists | Dreyfus et al. 2025 |
| P5 | Catalogues are siloed — no cross-composer exploration | Krabbe & Geertinger 2012 |
| P6 | No documentation or automated testing | Stadler & Jettka 2023 |

---

## The solution

### Catalogue-agnostic architecture

The pipeline is designed to work with **any MEI XML catalogue produced by MerMEId** — not just one composer. Adding a new catalogue requires no code changes, only a new XML source file.

**Catalogues used in this project:**
- **Carl Nielsen Works (CNW)** — ~750 works, Danish Royal Library / DCM — primary dataset
- **Frederick Delius (DCW)** — ~150 works, University of Oxford / BL Labs — secondary dataset

**Other compatible MEI catalogues (extensible without code changes):**
- J.P.E. Hartmann — Danish Royal Library
- Niels W. Gade — Danish Royal Library
- Johann Adolph Scheibe — Danish Royal Library
- Giuseppe Tartini — Discover Tartini project

### Data model decision

Four data models were evaluated before selecting the approach:

| Model | Decision | Reason |
|-------|----------|--------|
| Keep as MEI XML | ❌ Rejected | Recreates the original eXist-db dependency problem |
| Linked Data (RDF) | ⚠️ Stretch goal | Best long-term solution but too complex for project scope |
| Graph database (Neo4j) | ❌ Declined | Overkill for 2–3 catalogues; hosting constraints |
| **JSON + SQLite** | **✅ Selected** | Queryable via SQL, clean REST API, portable, zero-config, reversible |

The original MEI XML is preserved as the source of truth — the transformation is fully reversible.

---

## Features

| Feature | Solves | User group |
|---------|--------|------------|
| Full-text search | P3, P4 | All users |
| Works Discovery Engine | P5 | Students, scholars |
| REST API (JSON, OpenAPI) | P3, P6 | Developers |
| Multi-catalogue browser | P5 | All users |
| Linked data (Wikidata / MusicBrainz) | P3, P5 | Researchers, devs |
| Manuscript & source viewer | P4 | Scholars, librarians |
| MEI model evaluation report | P2, P6 | Librarians |

### Works Discovery Engine (original contribution)

MEI catalogues include **incipits** — the opening notes of each work. By analysing these computationally, the system clusters works by melodic character, surfacing connections that no human cataloguer has explicitly mapped. Because multiple catalogues are loaded together, structural similarities between composers (e.g. Nielsen and Delius) can also be surfaced — something no existing tool does.

> **Important:** melodic similarity groupings are computational suggestions, not scholarly claims. The interface labels these clearly to avoid misrepresentation.

---

## User needs

| Persona | Role | Key needs |
|---------|------|-----------|
| Dr. Sarah M. | Musicologist | Search by key/instrumentation, access manuscript provenance, export data |
| James K. | Music Librarian | Sustainable open infrastructure, MEI/JSON/CSV import-export, multilingual support |
| Anna T. | Music Student | Browse without XML knowledge, discover lesser-known works |
| Dev / Researcher | API Consumer | RESTful documented API, JSON responses, linked data IDs, stable endpoints |

---

## Project structure

```
/
├── data/                   # Source MEI XML catalogue files
│   ├── nielsen/            # Carl Nielsen Works (CNW)
│   └── delius/             # Frederick Delius Works (DCW)
├── transform/              # MEI XML → JSON + SQLite pipeline
│   ├── parser.py           # MEI XML parser
│   ├── schema.sql          # SQLite schema
│   └── tests/              # Pytest unit tests for parser
├── api/                    # REST API
│   ├── main.py             # FastAPI application
│   ├── routes/             # Endpoint definitions
│   └── tests/              # Pytest API tests
├── frontend/               # Web interface
│   ├── index.html
│   ├── css/
│   └── js/
├── docs/                   # Project documentation
│   ├── mei-evaluation.md   # Critical assessment of MEI data model
│   └── api-reference.md    # API endpoint documentation
└── README.md
```

---

## Tech stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Data source | MEI XML (MerMEId) | Existing standard — preserved as source of truth |
| Transformation | Python + lxml | Robust XML parsing, well-documented |
| Storage | SQLite | Portable, zero-config, ideal for project scale |
| API | FastAPI + OpenAPI | Auto-generated docs, fast, modern Python |
| Frontend | HTML / CSS / JavaScript | Lightweight, no framework lock-in |
| Testing | pytest | Industry standard, clear coverage reporting |
| Deployment | Docker | Reproducible, avoids the institutional dependency problem |

---

## Evaluation & testing

Three datasets are used to evaluate the system:

### Carl Nielsen Works (CNW) — primary
- XML parsing completeness (% of fields successfully extracted)
- API response accuracy vs. source XML
- Search recall on known work titles

### Frederick Delius (DCW) — secondary
- Schema compatibility across two catalogues
- Cross-composer search precision
- Linked data ID match rate (Wikidata / MusicBrainz)

### Synthetic edge-case set — unit testing
- Parser robustness on missing / null fields
- API error handling (4xx responses)
- Graceful UI fallback for incomplete records

> Note: evaluation focuses on transformation accuracy, data coverage, and interface usability — not classification accuracy scores.

---

## Ethics & limitations

### Ethical responsibilities
- **Data attribution** — MEI catalogue data was produced by named scholars. The system prominently credits original authors and institutions.
- **Copyright on editorial content** — musical works may be public domain, but editorial annotations and descriptions may be separately copyrighted. No protected text is reproduced verbatim.
- **Algorithmic transparency** — melodic similarity groupings are labelled as computational suggestions, not musicological claims.
- **Accessibility** — the portal targets WCAG 2.1 AA compliance and screen-reader compatibility.

### Honest limitations
- **Data completeness varies** — some MEI records have missing incipits or incomplete manuscript data. The interface surfaces this uncertainty rather than hiding it.
- **Incipit analysis is shallow** — opening notes are a limited proxy for musical similarity. The system does not overstate what this means.
- **Scope is 2–3 composers** — scaling to dozens requires infrastructure beyond this project's scope, though the architecture is designed to be extensible.
- **Multilingual metadata** — MEI catalogues mix Danish, German, and English inconsistently. Full normalisation is documented as a known limitation.

---

## Grading criteria alignment

| Grade | Criteria | This project |
|-------|----------|-------------|
| Pass (3rd) | Live website with catalogue data | ✅ Core deliverable |
| Good (2:1) | Significant data model coverage, most data transformed | ✅ Full MEI model implemented |
| Outstanding (1st) | MEI evaluation, multi-composer, linked data, new insights | ✅ Targeted via Discovery Engine + linked data + evaluation report |

---

## Data sources

- MEI standard: https://music-encoding.org
- MerMEId project: https://github.com/Edirom/MerMEId
- Carl Nielsen Works Catalogue: https://www.kb.dk/dcm/cnw/navigation.xq
- Frederick Delius Catalogue: https://delius.music.ox.ac.uk/catalogue/navigation.html
- Wikidata: https://www.wikidata.org
- MusicBrainz: https://musicbrainz.org

## References

- Krabbe, N. & Geertinger, A.T. (2012). *MEI as a Basis for Thematic Catalogues*. RISM Conference.
- Stadler, P. & Jettka, D. (2023). *Sustainability of MerMEId*. DLfM '23, Milano.
- Dreyfus, L., Lewis, D. & Page, K. (2025). *Digital Companions for Music Scholarship*. Journal of New Music Research.

---

## Status

- [ ] MEI XML source files located and downloaded
- [ ] XML structure analysed and documented
- [ ] SQLite schema designed
- [ ] Transformation pipeline complete
- [ ] Transformation tests passing
- [ ] REST API built and documented
- [ ] API tests passing
- [ ] Web frontend complete
- [ ] Works Discovery Engine implemented
- [ ] Linked data connections added
- [ ] MEI model evaluation written
- [ ] Accessibility audit complete

---

## License

For academic use. Data sourced from publicly available MEI catalogues. All original catalogue data remains the property of the respective institutions.
