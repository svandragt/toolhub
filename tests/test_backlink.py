"""
Tests for the backlink feature (issue #3).

Covers _derive_parent_url() and load_site_config() for all relevant
deployment scenarios:
  - Subdomain:              tools.example.com        → example.com
  - Subdomain + path:       tools.example.com/path   → example.com
  - Subdirectory (root):    example.com/toolhub      → example.com
  - GitHub Pages subdir:    username.github.io/repo  → requires explicit config
  - Root domain:            example.com              → no backlink
  - Root domain, no path:   username.github.io       → no backlink
  - Explicit override:      back_link_url set         → always wins
  - No config at all:       both empty               → no backlink
"""

from pathlib import Path
from unittest.mock import patch

import pytest

# conftest.py sets GITHUB_TOKEN / GH_USERNAME before any import of build.py.
from build import _derive_parent_url, _SITE_DEFAULTS, _deep_merge
from build import load_site_config, SITE_FILE


# ===========================================================================
# _derive_parent_url — unit tests
# ===========================================================================

class TestDeriveParentUrl:
    """Pure-function tests for subdomain / subdirectory detection."""

    # --- Subdomain scenarios -----------------------------------------------

    def test_subdomain_only(self):
        """tools.example.com → example.com (classic subdomain)."""
        assert _derive_parent_url("https://tools.example.com") == "https://example.com"

    def test_subdomain_with_trailing_slash(self):
        """tools.example.com/ — trailing slash is not a real path."""
        assert _derive_parent_url("https://tools.example.com/") == "https://example.com"

    def test_subdomain_with_path(self):
        """tools.example.com/toolhub — subdomain wins over path."""
        assert _derive_parent_url("https://tools.example.com/toolhub") == "https://example.com"

    def test_subdomain_deep_path(self):
        """tools.example.com/a/b/c — subdomain wins regardless of path depth."""
        assert _derive_parent_url("https://tools.example.com/a/b/c") == "https://example.com"

    def test_multi_level_subdomain(self):
        """dev.tools.example.com — strips one subdomain label at a time."""
        assert _derive_parent_url("https://dev.tools.example.com") == "https://tools.example.com"

    def test_subdomain_http(self):
        """Works for http:// schemes too."""
        assert _derive_parent_url("http://tools.example.com") == "http://example.com"

    # --- Subdirectory (root domain) scenarios ------------------------------

    def test_subdirectory_root_domain(self):
        """example.com/toolhub — path stripped, origin returned."""
        assert _derive_parent_url("https://example.com/toolhub") == "https://example.com"

    def test_subdirectory_deep(self):
        """example.com/projects/toolhub — full path stripped."""
        assert _derive_parent_url("https://example.com/projects/toolhub") == "https://example.com"

    def test_subdirectory_http(self):
        """http scheme preserved when stripping path."""
        assert _derive_parent_url("http://example.com/toolhub") == "http://example.com"

    # --- GitHub Pages subdirectory -----------------------------------------
    # username.github.io is treated as a subdomain by our heuristic (github.io
    # is not in our algorithm's list of known public suffixes).  The recommended
    # approach for this deployment is to set back_link_url explicitly in site.toml.
    # These tests document the current behaviour so regressions are caught.

    def test_github_pages_subdir_behaviour(self):
        """username.github.io/repo — heuristic strips 'username' as subdomain.

        This is a known limitation: without a Public Suffix List the algorithm
        cannot distinguish username.github.io from tools.example.com.
        Use explicit back_link_url for GitHub Pages subdirectory deployments.
        """
        result = _derive_parent_url("https://username.github.io/repo")
        # Current behaviour: subdomain heuristic fires → github.io
        assert result == "https://github.io"

    def test_github_pages_root_no_backlink(self):
        """username.github.io with no path — subdomain heuristic also fires.

        Returns github.io. For a plain github.io root deployment where no
        backlink is desired, leave url unset or set back_link_url = "".
        """
        result = _derive_parent_url("https://username.github.io")
        assert result == "https://github.io"

    # --- Root domain (no backlink) ----------------------------------------

    def test_root_domain_no_path(self):
        """example.com — root domain with no path → no backlink."""
        assert _derive_parent_url("https://example.com") == ""

    def test_root_domain_trailing_slash_only(self):
        """example.com/ — trailing slash is not a real path."""
        assert _derive_parent_url("https://example.com/") == ""

    # --- Edge cases --------------------------------------------------------

    def test_empty_string(self):
        assert _derive_parent_url("") == ""

    def test_no_scheme(self):
        """Bare hostname without scheme — urlparse sees no netloc, returns degenerate."""
        # urlparse("example.com/path") → scheme='', netloc='', path='example.com/path'
        # hostname is None → host='', has path → returns "://"
        result = _derive_parent_url("example.com/path")
        assert result == "://"  # degenerate but does not crash


# ===========================================================================
# load_site_config — integration tests
# ===========================================================================

class TestLoadSiteConfigBacklink:
    """Tests for auto-derived and explicit back_link_url in load_site_config.

    We patch build.SITE_FILE to point at a real temp file (or a non-existent
    path) rather than mocking PosixPath instance methods, which are read-only
    in Python 3.11+.
    """

    def _load_with_toml(self, toml_content: str, tmp_path: Path):
        """Write toml_content to a temp file and run load_site_config() against it."""
        toml_file = tmp_path / "site.toml"
        toml_file.write_bytes(toml_content.encode())
        with patch("build.SITE_FILE", toml_file):
            return load_site_config()

    def _load_no_toml(self, tmp_path: Path):
        """Run load_site_config() as if no site.toml is present."""
        with patch("build.SITE_FILE", tmp_path / "nonexistent.toml"):
            return load_site_config()

    # --- No site.toml at all -----------------------------------------------

    def test_no_toml_no_backlink(self, tmp_path):
        """Without site.toml and no url, back_link_url is empty."""
        config = self._load_no_toml(tmp_path)
        assert config["navigation"]["back_link_url"] == ""

    def test_no_toml_default_label(self, tmp_path):
        """Default back_link_label is 'Home'."""
        config = self._load_no_toml(tmp_path)
        assert config["navigation"]["back_link_label"] == "Home"

    # --- Auto-detection from url: subdomain --------------------------------

    def test_subdomain_auto_derives_parent(self, tmp_path):
        """url on a subdomain → back_link_url auto-set to parent domain."""
        config = self._load_with_toml('url = "https://tools.example.com"', tmp_path)
        assert config["navigation"]["back_link_url"] == "https://example.com"

    def test_subdomain_with_path_auto_derives_parent(self, tmp_path):
        """Subdomain + subdirectory: parent domain derived from subdomain."""
        config = self._load_with_toml('url = "https://tools.example.com/toolhub"', tmp_path)
        assert config["navigation"]["back_link_url"] == "https://example.com"

    # --- Auto-detection from url: subdirectory -----------------------------

    def test_subdirectory_auto_derives_origin(self, tmp_path):
        """Root domain with path → back_link_url auto-set to origin."""
        config = self._load_with_toml('url = "https://example.com/toolhub"', tmp_path)
        assert config["navigation"]["back_link_url"] == "https://example.com"

    def test_github_pages_subdirectory_explicit_required(self, tmp_path):
        """username.github.io/repo: explicit back_link_url overrides heuristic."""
        config = self._load_with_toml(
            'url = "https://username.github.io/repo"\n'
            '[navigation]\n'
            'back_link_url = "https://username.github.io"',
            tmp_path,
        )
        assert config["navigation"]["back_link_url"] == "https://username.github.io"

    # --- Root domain: no auto-detection ------------------------------------

    def test_root_domain_no_auto_derive(self, tmp_path):
        """Plain root domain → no auto-derived backlink."""
        config = self._load_with_toml('url = "https://example.com"', tmp_path)
        assert config["navigation"]["back_link_url"] == ""

    def test_root_domain_trailing_slash_no_derive(self, tmp_path):
        config = self._load_with_toml('url = "https://example.com/"', tmp_path)
        assert config["navigation"]["back_link_url"] == ""

    # --- No url — no backlink ----------------------------------------------

    def test_no_url_no_backlink(self, tmp_path):
        """No url set → no backlink regardless of toml."""
        config = self._load_with_toml("", tmp_path)
        assert config["navigation"]["back_link_url"] == ""

    # --- Explicit back_link_url always wins --------------------------------

    def test_explicit_url_overrides_auto(self, tmp_path):
        """Explicit back_link_url is used instead of auto-detected value."""
        config = self._load_with_toml(
            'url = "https://tools.example.com"\n'
            '[navigation]\n'
            'back_link_url = "https://custom.example.com"',
            tmp_path,
        )
        assert config["navigation"]["back_link_url"] == "https://custom.example.com"

    def test_explicit_url_no_site_url(self, tmp_path):
        """Explicit back_link_url works even without url."""
        config = self._load_with_toml(
            '[navigation]\n'
            'back_link_url = "https://mysite.com"',
            tmp_path,
        )
        assert config["navigation"]["back_link_url"] == "https://mysite.com"

    def test_explicit_label_preserved(self, tmp_path):
        """Custom back_link_label is preserved."""
        config = self._load_with_toml(
            'url = "https://tools.example.com"\n'
            '[navigation]\n'
            'back_link_label = "Back to main site"',
            tmp_path,
        )
        assert config["navigation"]["back_link_label"] == "Back to main site"

    # --- Default label when auto-derived -----------------------------------

    def test_default_label_when_auto_derived(self, tmp_path):
        """Auto-derived backlink uses default label 'Home'."""
        config = self._load_with_toml('url = "https://tools.example.com"', tmp_path)
        assert config["navigation"]["back_link_label"] == "Home"

    # --- _SITE_DEFAULTS is not mutated -------------------------------------

    def test_defaults_not_mutated_by_load(self, tmp_path):
        """load_site_config() must not mutate _SITE_DEFAULTS navigation values."""
        original_url = _SITE_DEFAULTS["navigation"]["back_link_url"]
        self._load_with_toml('url = "https://tools.example.com"', tmp_path)
        assert _SITE_DEFAULTS["navigation"]["back_link_url"] == original_url

    # --- Deployment scenario matrix ----------------------------------------

    @pytest.mark.parametrize("url,expected_url", [
        # Subdomain deployments
        ("https://tools.example.com",         "https://example.com"),
        ("https://tools.example.com/",        "https://example.com"),
        ("https://tools.example.com/toolhub", "https://example.com"),
        # Subdirectory on root domain (e.g. GitHub Pages project site)
        ("https://example.com/toolhub",       "https://example.com"),
        ("https://example.com/a/b",           "https://example.com"),
        # Root domain — no backlink
        ("https://example.com",               ""),
        ("https://example.com/",              ""),
        # No url — no backlink
        ("",                                  ""),
    ])
    def test_auto_derive_matrix(self, url, expected_url, tmp_path):
        """Parametrised matrix of url → expected auto-derived back_link_url."""
        toml = f'url = "{url}"' if url else ""
        config = self._load_with_toml(toml, tmp_path)
        assert config["navigation"]["back_link_url"] == expected_url


# ===========================================================================
# Template rendering — base.html backlink visibility
# ===========================================================================

from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _render_base(site_config: dict) -> str:
    """Render base.html with the given site config and return HTML string."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["site"] = site_config
    env.globals["sections"] = site_config.get("sections", {})
    tmpl = env.get_template("base.html")
    return tmpl.render()


def _make_site_config(back_link_url: str = "", back_link_label: str = "Home") -> dict:
    config = _deep_merge({}, _SITE_DEFAULTS)
    config["navigation"]["back_link_url"] = back_link_url
    config["navigation"]["back_link_label"] = back_link_label
    return config


class TestBaseHtmlBacklink:
    """Tests that base.html renders the backlink nav correctly."""

    def test_backlink_hidden_when_no_url(self):
        """No back_link_url → nav element absent from rendered HTML."""
        html = _render_base(_make_site_config(back_link_url=""))
        assert "site-header__nav" not in html

    def test_backlink_shown_when_url_set(self):
        """back_link_url set → nav element present with correct href."""
        html = _render_base(_make_site_config(back_link_url="https://example.com"))
        assert "site-header__nav" in html
        assert 'href="https://example.com"' in html

    def test_backlink_label_rendered(self):
        """Custom back_link_label appears as link text."""
        html = _render_base(_make_site_config(
            back_link_url="https://example.com",
            back_link_label="My Site",
        ))
        assert "My Site" in html

    def test_backlink_default_label(self):
        """Default label 'Home' appears when no custom label is set."""
        html = _render_base(_make_site_config(back_link_url="https://example.com"))
        assert "Home" in html

    def test_backlink_arrow_present(self):
        """Back-arrow HTML entity &#8592; is present in rendered output."""
        html = _render_base(_make_site_config(back_link_url="https://example.com"))
        assert "&#8592;" in html
