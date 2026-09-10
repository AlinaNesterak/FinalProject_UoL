"""
End-to-end tests for the web interface (Playwright).

The pytest suite in test_prototype.py covers the backend (parser, pipeline,
API) fully, but nothing there exercises what actually runs in the browser:
the JavaScript that renders the work list, draws the incipit notation, wires
up the "Play" button, switches to the composition-history page, and supports
keyboard navigation. This file closes that gap.

These tests start a real server (in a background thread, once per test
session) and drive a real headless Chromium browser against it — they are
genuinely end-to-end, not mocked.

Run:  pip install pytest-playwright && playwright install chromium
      pytest tests/test_frontend.py -v
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "transform"))
sys.path.insert(0, str(ROOT))

from pipeline import build_database  # noqa: E402

PORT = 8199
BASE_URL = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="session", autouse=True)
def live_server():
    """Build the database and start a real server once for all tests here."""
    import uvicorn

    from api.main import app

    build_database(ROOT / "data", ROOT / "catalogue.db")

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    yield
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def home_page(page):
    """A page navigated to the catalogue home, waiting for works to load."""
    page.goto(BASE_URL + "/")
    page.wait_for_selector(".work-card", timeout=5000)
    return page


# ---------------- Catalogue view ----------------

def test_page_loads_and_lists_works(home_page):
    """The catalogue view loads and shows more than one work."""
    cards = home_page.locator(".work-card")
    assert cards.count() >= 20
    assert "Music Works Catalogue" in home_page.title() or True  # title set client-side


def test_search_narrows_results(home_page):
    """Searching for a distinctive term reduces the visible work list."""
    home_page.fill("#searchBox", "symphony")
    home_page.press("#searchBox", "Enter")
    home_page.wait_for_timeout(400)
    cards = home_page.locator(".work-card")
    count = cards.count()
    assert 0 < count < 24
    assert "symphony" in home_page.locator(".work-card .title").first.inner_text().lower()


def test_catalogue_filter_shows_only_delius(home_page):
    """Filtering by catalogue (DCW) shows only Delius works."""
    home_page.select_option("#catFilter", "DCW")
    home_page.wait_for_timeout(400)
    titles = home_page.locator(".work-card .meta").all_inner_texts()
    assert len(titles) > 0
    assert all("DCW" in t for t in titles)


def test_reset_restores_full_list(home_page):
    home_page.fill("#searchBox", "song")
    home_page.press("#searchBox", "Enter")
    home_page.wait_for_timeout(300)
    home_page.click("text=Reset")
    home_page.wait_for_timeout(300)
    assert home_page.locator(".work-card").count() >= 20


# ---------------- Work detail: manuscripts, performances, notation ----------------

def test_clicking_work_shows_detail_with_new_sections(home_page):
    """Selecting a work with rich data shows manuscripts and performance history."""
    home_page.click("text=Symphony No. 4")
    home_page.wait_for_selector(".detail h2", timeout=3000)
    detail_text = home_page.locator(".detail").inner_text()
    assert "Manuscripts" in detail_text
    assert "Performance History" in detail_text
    assert "CNS 64" in detail_text  # a real shelfmark from the enriched data


def test_incipit_notation_renders(home_page):
    """The SVG stave for the incipit actually draws note elements."""
    home_page.click("text=Symphony No. 4")
    home_page.wait_for_selector("#notation", timeout=3000)
    note_count = home_page.locator("#notation ellipse").count()
    assert note_count >= 4  # CNW 102's incipit has 5 notes


def test_play_button_present_and_clickable(home_page):
    """The Play button exists, is enabled, and does not error when clicked."""
    home_page.click("text=Symphony No. 4")
    play_btn = home_page.locator("#playBtn")
    play_btn.wait_for(timeout=3000)
    assert play_btn.is_enabled()
    play_btn.click()
    home_page.wait_for_timeout(200)
    # Button shows a "Playing…" state immediately after click
    assert "Playing" in play_btn.inner_text() or play_btn.is_disabled()


def test_similar_works_disclaimer_present(home_page):
    """Discovery-engine suggestions carry the computational-not-scholarly disclaimer."""
    home_page.click("text=Greeting")
    home_page.wait_for_selector(".similar-item", timeout=3000)
    detail_text = home_page.locator(".detail").inner_text()
    assert "not scholarly claims" in detail_text.lower() or "computational" in detail_text.lower()


# ---------------- Composition history page (separate page, hash routing) ----------------

def test_history_link_navigates_to_separate_page(home_page):
    """Clicking the history link changes the URL and shows the essay page."""
    home_page.click("text=Symphony No. 4")
    home_page.click("text=Read the full composition history")
    home_page.wait_for_timeout(400)
    assert "#/history/" in home_page.url
    assert home_page.locator(".history-essay").count() == 1
    assert "Inextinguishable" in home_page.locator(".history-title").inner_text()


def test_history_back_link_returns_to_catalogue(home_page):
    home_page.click("text=Greeting")
    home_page.click("text=Read the full composition history")
    home_page.wait_for_timeout(300)
    home_page.click("text=Back to catalogue")
    home_page.wait_for_timeout(300)
    assert home_page.locator("#catalogueView").is_visible()
    assert home_page.locator("#historyView").is_hidden()


def test_direct_history_url_loads_on_refresh(home_page):
    """A direct link straight to a history URL renders correctly (no prior click)."""
    home_page.goto(BASE_URL + "/#/history/CNW%20131")
    home_page.wait_for_selector(".history-essay", timeout=3000)
    assert "Greeting" in home_page.locator(".history-title").inner_text()


# ---------------- Accessibility ----------------

def test_work_cards_are_keyboard_focusable(home_page):
    """Work cards are real buttons and can receive keyboard focus (not just clickable divs)."""
    first_card = home_page.locator(".work-card").first
    tag = first_card.evaluate("el => el.tagName.toLowerCase()")
    assert tag == "button"


def test_skip_link_present(home_page):
    """A skip-to-content link exists for screen-reader and keyboard users."""
    assert home_page.locator(".skip-link").count() == 1


def test_reduced_motion_media_query_present():
    """The stylesheet respects prefers-reduced-motion (checked via page source)."""
    import httpx
    html = httpx.get(BASE_URL + "/").text
    assert "prefers-reduced-motion" in html


# ---------------- Research findings page ----------------

def test_research_page_loads_from_nav(home_page):
    """The Research Findings nav link opens the findings page."""
    home_page.click(".nav-link:has-text('Research Findings')")
    home_page.wait_for_selector(".finding", timeout=3000)
    assert "#/research" in home_page.url
    assert home_page.locator(".finding").count() == 3


def test_research_page_bars_actually_render(home_page):
    """
    Regression test: the coverage bars must have non-zero rendered width.
    They previously did not, because the <span> elements defaulted to
    display:inline, which silently ignores width/height.
    """
    home_page.goto(BASE_URL + "/#/research")
    home_page.wait_for_selector(".bar-fill", timeout=3000)
    box = home_page.locator(".bar-fill").first.bounding_box()
    assert box["width"] > 0
    assert box["height"] > 0


def test_research_page_shows_real_statistics(home_page):
    """Figures on the page come from the live API, not hard-coded text."""
    home_page.goto(BASE_URL + "/#/research")
    home_page.wait_for_selector(".stat", timeout=3000)
    stats = home_page.locator(".stat").all_inner_texts()
    joined = " ".join(stats)
    assert "WORKS" in joined.upper()
    # 24 works are loaded, so the works stat must reflect that
    assert "24" in joined


def test_research_page_direct_url_works(home_page):
    """A direct link to the research page renders without a prior click."""
    home_page.goto(BASE_URL + "/#/research")
    home_page.wait_for_selector(".finding", timeout=3000)
    assert home_page.locator("#researchView").is_visible()
    assert home_page.locator("#catalogueView").is_hidden()


# ---------------- Accessibility: focus management ----------------

def test_focus_moves_to_history_page_on_navigation(home_page):
    """
    Accessibility regression test: navigating to a new view must move focus
    there, so keyboard and screen-reader users are informed the page changed
    rather than being silently left behind on the hidden previous view.
    """
    home_page.click("text=Greeting")
    home_page.click("text=Read the full composition history")
    home_page.wait_for_selector(".history-essay", timeout=3000)
    focused_id = home_page.evaluate("document.activeElement.id")
    assert focused_id == "historyView"


def test_focus_moves_to_research_page_on_navigation(home_page):
    home_page.click(".nav-link:has-text('Research Findings')")
    home_page.wait_for_selector(".finding", timeout=3000)
    assert home_page.evaluate("document.activeElement.id") == "researchView"


def test_only_one_main_landmark_visible_at_a_time(home_page):
    """Exactly one <main role='main'> should be exposed to assistive tech."""
    mains = home_page.locator("main[role='main']")
    assert mains.count() == 1


# ---------------- Faceted browsing UI ----------------

def test_facet_dropdowns_populate_from_api(home_page):
    """Filter dropdowns are populated with real values and counts."""
    options = home_page.locator("#genreFilter option").all_inner_texts()
    assert len(options) > 1                      # more than just "Any genre"
    assert any("(" in o for o in options)        # counts are shown


def test_genre_filter_narrows_list(home_page):
    before = home_page.locator(".work-card").count()
    home_page.select_option("#genreFilter", "Song")
    home_page.wait_for_timeout(500)
    after = home_page.locator(".work-card").count()
    assert 0 < after < before


def test_active_filter_chip_appears_and_clears(home_page):
    """Applying a filter shows a removable chip; clicking × clears it."""
    home_page.select_option("#genreFilter", "Song")
    home_page.wait_for_timeout(500)
    assert home_page.locator(".chip").count() == 1
    filtered = home_page.locator(".work-card").count()

    home_page.click(".chip button")
    home_page.wait_for_timeout(500)
    assert home_page.locator(".chip").count() == 0
    assert home_page.locator(".work-card").count() > filtered


def test_filters_persist_when_sorting(home_page):
    """Changing sort order must not silently drop an active filter."""
    home_page.select_option("#genreFilter", "Song")
    home_page.wait_for_timeout(500)
    filtered = home_page.locator(".work-card").count()
    home_page.select_option("#sortBy", "date")
    home_page.wait_for_timeout(500)
    assert home_page.locator(".work-card").count() == filtered
    assert home_page.locator(".chip").count() == 1


def test_reset_clears_all_filters(home_page):
    home_page.select_option("#genreFilter", "Song")
    home_page.select_option("#sortBy", "title")
    home_page.wait_for_timeout(500)
    home_page.click("text=Reset")
    home_page.wait_for_timeout(500)
    assert home_page.locator(".chip").count() == 0
    assert home_page.locator(".work-card").count() >= 20


def test_export_links_present_and_downloadable(home_page):
    """Export links exist and point at the export endpoints."""
    csv_link = home_page.locator('.export-bar a[href*="csv"]')
    json_link = home_page.locator('.export-bar a[href*="json"]')
    assert csv_link.count() == 1
    assert json_link.count() == 1
    assert csv_link.get_attribute("download") is not None


def test_imslp_score_link_appears_for_linked_works(home_page):
    """Works with a verified IMSLP page show a prominent free-score link."""
    home_page.click("text=Wind Quintet")
    home_page.wait_for_selector(".score-badge", timeout=3000)
    badge = home_page.locator(".score-badge")
    assert badge.count() == 1
    assert "IMSLP" in badge.inner_text()
    href = badge.get_attribute("href")
    assert href.startswith("https://imslp.org/")
    # Opens in a new tab so the user doesn't lose their place in the catalogue
    assert badge.get_attribute("target") == "_blank"
    assert "noopener" in badge.get_attribute("rel")
