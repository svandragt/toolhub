"""Tests for Atom feed generation (issue #1).

Coverage:
- atom.xml template: valid XML, entry structure, base_url in links
- build.py: feed skipped without base_url, written with base_url
- build.py: archived projects excluded from feed entries
- base.html: autodiscovery link absent/present based on base_url
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
ATOM_NS = "http://www.w3.org/2005/Atom"

ACTIVE_PROJECT = {
    "name": "myrepo",
    "slug": "myrepo",
    "type": "repo",
    "updated_at": "2026-03-25T10:00:00Z",
    "description": "A handy tool",
    "tags": ["python", "cli"],
    "archived": False,
    "pinned": False,
}

ARCHIVED_PROJECT = {
    "name": "oldthing",
    "slug": "oldthing",
    "type": "repo",
    "updated_at": "2024-01-01T00:00:00Z",
    "description": "Ancient",
    "tags": [],
    "archived": True,
    "pinned": False,
}


def _make_jinja_env(base_url: str = "") -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["site"] = {
        "title": "Test Tools",
        "description": "Test portfolio",
        "base_url": base_url,
        "footer": "",
        "sections": {"active": "Active", "archived": "Archived", "back_link": "back"},
        "navigation": {"back_link_url": "", "back_link_label": "Home"},
    }
    env.globals["sections"] = env.globals["site"]["sections"]
    return env


# ---------------------------------------------------------------------------
# atom.xml template unit tests
# ---------------------------------------------------------------------------

def test_atom_template_produces_valid_xml():
    env = _make_jinja_env("https://example.com")
    rendered = env.get_template("atom.xml").render(projects=[ACTIVE_PROJECT])
    ET.fromstring(rendered)  # raises ParseError if invalid


def test_atom_template_entry_contains_required_elements():
    env = _make_jinja_env("https://example.com")
    rendered = env.get_template("atom.xml").render(projects=[ACTIVE_PROJECT])
    root = ET.fromstring(rendered)
    entry = root.find(f"{{{ATOM_NS}}}entry")
    assert entry is not None, "feed must have at least one entry"
    assert entry.find(f"{{{ATOM_NS}}}title") is not None
    assert entry.find(f"{{{ATOM_NS}}}id") is not None
    assert entry.find(f"{{{ATOM_NS}}}updated") is not None
    assert entry.find(f"{{{ATOM_NS}}}link") is not None


def test_atom_template_entry_links_use_base_url():
    env = _make_jinja_env("https://example.com")
    rendered = env.get_template("atom.xml").render(projects=[ACTIVE_PROJECT])
    root = ET.fromstring(rendered)
    entry = root.find(f"{{{ATOM_NS}}}entry")
    link_href = entry.find(f"{{{ATOM_NS}}}link").get("href")
    assert link_href.startswith("https://example.com"), "entry link must use base_url"
    assert "myrepo" in link_href


# ---------------------------------------------------------------------------
# build.py integration tests (feed conditional on base_url)
# ---------------------------------------------------------------------------

def test_feed_not_written_when_base_url_absent(tmp_path):
    import build

    with (
        patch("build.OUTPUT_DIR", tmp_path / "output"),
        patch("build.get_portfolio", return_value={}),
        patch("build.get_readme", return_value="# Test"),
    ):
        build.build(
            projects=[ACTIVE_PROJECT],
            client=MagicMock(),
            site_config={**build._SITE_DEFAULTS, "base_url": ""},
        )

    assert not (tmp_path / "output" / "atom.xml").exists()


def test_feed_written_when_base_url_set(tmp_path):
    import build

    with (
        patch("build.OUTPUT_DIR", tmp_path / "output"),
        patch("build.get_portfolio", return_value={}),
        patch("build.get_readme", return_value="# Test"),
    ):
        build.build(
            projects=[ACTIVE_PROJECT],
            client=MagicMock(),
            site_config={**build._SITE_DEFAULTS, "base_url": "https://example.com"},
        )

    feed_path = tmp_path / "output" / "atom.xml"
    assert feed_path.exists(), "atom.xml must be written when base_url is configured"
    ET.parse(feed_path)  # valid XML


def test_feed_excludes_archived_projects(tmp_path):
    import build

    with (
        patch("build.OUTPUT_DIR", tmp_path / "output"),
        patch("build.get_portfolio", return_value={}),
        patch("build.get_readme", return_value="# Test"),
    ):
        build.build(
            projects=[ACTIVE_PROJECT, ARCHIVED_PROJECT],
            client=MagicMock(),
            site_config={**build._SITE_DEFAULTS, "base_url": "https://example.com"},
        )

    root = ET.parse(tmp_path / "output" / "atom.xml").getroot()
    entry_titles = [
        e.find(f"{{{ATOM_NS}}}title").text
        for e in root.findall(f"{{{ATOM_NS}}}entry")
    ]
    assert "myrepo" in entry_titles, "active project must appear in feed"
    assert "oldthing" not in entry_titles, "archived project must not appear in feed"


# ---------------------------------------------------------------------------
# base.html autodiscovery link tests
# ---------------------------------------------------------------------------

def test_autodiscovery_link_absent_without_base_url():
    env = _make_jinja_env("")
    rendered = env.get_template("base.html").render()
    assert "application/atom+xml" not in rendered


def test_autodiscovery_link_present_with_base_url():
    env = _make_jinja_env("https://example.com")
    rendered = env.get_template("base.html").render()
    assert 'rel="alternate"' in rendered
    assert "application/atom+xml" in rendered
    assert "atom.xml" in rendered
