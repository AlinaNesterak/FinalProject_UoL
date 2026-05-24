# FinalProject_UoL

# Music Works Catalogue Portal

A modern web portal for exploring classical music catalogues encoded in MEI XML (Music Encoding Initiative). This project transforms legacy MerMEId catalogue data into a flexible, queryable system with a REST API and an interactive web interface.

Built as a final year university project in Computer Science.

---

## The problem

Digital catalogues of classical composers' works (e.g. Carl Nielsen) were originally built using a Java-based XML system (MerMEId) developed by the Danish Royal Library in 2014. This system is difficult to maintain, no longer actively supported, and its publication pipeline has broken down. The underlying data — encoded in MEI XML — remains valuable but is inaccessible to most users.

## The solution

This project:
- Parses and transforms MEI XML catalogue data into a modern, lightweight format (JSON / SQLite)
- Exposes the data through a clean REST API
- Provides an interactive web interface for exploring works, manuscripts, performances, and themes

---

## Features

- XML to JSON/SQLite transformation pipeline
- REST API for querying works, composers, genres, and dates
- Web interface for browsing and searching the catalogue
- Full-text search across work titles, descriptions, and metadata
- Evaluation of the MEI catalogue model with recommendations

---

## Project structure

```
/
├── data/               # Source MEI XML files
├── transform/          # XML parsing and transformation scripts
├── api/                # REST API (Python / FastAPI)
├── frontend/           # Web interface
├── docs/               # Project documentation and MEI evaluation
└── README.md
```

---

## Tech stack

> To be confirmed based on university requirements.

Likely stack:
- Python (transformation scripts + API)
- FastAPI or Flask (REST API)
- SQLite or JSON (data storage)
- HTML / CSS / JavaScript (web frontend)

---

## Data source

This project uses MEI XML catalogues from the MerMEId system, primarily the **Carl Nielsen Works Catalogue** maintained by the Royal Danish Library.

- MEI standard: https://music-encoding.org
- MerMEId project: https://github.com/Det-Kongelige-Bibliotek/MerMEId

---

## Status

- [ ] Data source located and downloaded
- [ ] MEI XML structure analysed
- [ ] Data model designed
- [ ] Transformation script complete
- [ ] REST API built
- [ ] Web frontend complete
- [ ] MEI evaluation written

---

## License

For academic use. Data sourced from publicly available MEI catalogues.
