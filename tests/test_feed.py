"""Tests for Atom feed generation.

Coverage:
- feed.xml template: produces valid Atom 1.0 XML
- _build_feed: max_entries from site_config["feed"] is respected
- _build_feed: archived projects excluded from feed entries
- base.html: autodiscovery <link> points to feed.xml

Run from the repo root:
    uv run --group test pytest
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
ATOM_NS = "http://www.w3.org/2005/Atom"


def _project(name: str, *, archived: bool = False, month: int = 1) -> dict:
    """Minimal project dict suitable for feed rendering."""
    return {
        "name": name,
        "type": "repo",
        "repo_url": f"https://github.com/user/{name}",
        "description": f"Description of {name}",
        "tags": [],
        "created_at": f"2026-{month:02d}-01T00:00:00Z",
        "archived": archived,
    }


def _make_env() -> Environment:
    import build
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals["site"] = build._SITE_DEFAULTS
    env.globals["sections"] = build._SITE_DEFAULTS["sections"]
    return env


# --- feed.xml template ------------------------------------------------------ #

def test_feed_template_produces_valid_xml():
    """feed.xml must render as well-formed Atom 1.0 XML."""
    import build
    env = _make_env()
    env.filters["atom_date"] = build._to_atom_date
    project = {**_project("myrepo"), "feed_updated": "2026-03-25T10:00:00Z"}
    rendered = env.get_template("feed.xml").render(
        projects=[project],
        feed_updated="2026-03-25T10:00:00Z",
        site_url="https://example.com",
        feed_url="https://example.com/feed.xml",
        author="testuser",
    )
    root = ET.fromstring(rendered)
    assert root.tag == f"{{{ATOM_NS}}}feed"


# --- _build_feed behaviour -------------------------------------------------- #

def test_max_entries_respected(tmp_path):
    """feed entries must be capped to site_config["feed"]["max_entries"]."""
    import build
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    env = _make_env()

    projects = [_project(f"proj{i}", month=i + 1) for i in range(5)]

    with patch("build.OUTPUT_DIR", output_dir):
        build._build_feed(env, projects, {**build._SITE_DEFAULTS, "feed": {"max_entries": 2}})

    root = ET.parse(output_dir / "feed.xml").getroot()
    assert len(root.findall(f"{{{ATOM_NS}}}entry")) == 2


def test_archived_projects_excluded(tmp_path):
    """Archived projects must not appear as feed entries."""
    import build
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    env = _make_env()

    projects = [
        _project("active-repo", archived=False, month=1),
        _project("archived-repo", archived=True, month=2),
    ]

    with patch("build.OUTPUT_DIR", output_dir):
        build._build_feed(env, projects, build._SITE_DEFAULTS)

    root = ET.parse(output_dir / "feed.xml").getroot()
    entry_titles = [
        e.find(f"{{{ATOM_NS}}}title").text
        for e in root.findall(f"{{{ATOM_NS}}}entry")
    ]
    assert "active-repo" in entry_titles
    assert "archived-repo" not in entry_titles


# --- base.html autodiscovery ------------------------------------------------ #

def test_autodiscovery_link_points_to_feed_xml():
    """base.html must include an Atom feed autodiscovery link referencing feed.xml."""
    env = _make_env()
    rendered = env.get_template("base.html").render()
    assert 'type="application/atom+xml"' in rendered
    assert 'href="feed.xml"' in rendered
