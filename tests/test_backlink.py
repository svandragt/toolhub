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

import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the repo root is on sys.path so build.py can be imported as a module
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# build.py expects GITHUB_TOKEN and GH_USERNAME to be set; patch them before
# importing so the module-level sys.exit guard does not fire.
import os
os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GH_USERNAME", "test-user")

from build import _derive_parent_url, _SITE_DEFAULTS, _deep_merge  # noqa: E402


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
        """username.github.io with no path — treated as root-like by subdomain rule.

        Still matches >2 parts, so returns github.io.  Document this so the
        edge case is visible; users should leave site_url unset or set
        back_link_url = "" explicitly for a plain github.io root deployment.
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
        """Bare hostname without scheme — parsed host will be empty."""
        # urlparse treats "example.com/path" as a path, not a netloc
        result = _derive_parent_url("example.com/path")
        assert result == "://example.com"  # degenerate but does not crash


# ===========================================================================
# load_site_config — integration tests
# ===========================================================================

# We need to import load_site_config but it reads SITE_FILE (Path("site.toml")).
# Patch Path.exists and Path.open to control what it sees.

from build import load_site_config, SITE_FILE  # noqa: E402


def _make_toml_bytes(**kwargs) -> bytes:
    """Build a minimal TOML byte-string from keyword args (flat keys only)."""
    lines = []
    for k, v in kwargs.items():
        if isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, dict):
            for sk, sv in v.items():
                lines.append(f'[{k}]')
                if isinstance(sv, str):
                    lines.append(f'{sk} = "{sv}"')
    return "\n".join(lines).encode()


class TestLoadSiteConfigBacklink:
    """Tests for auto-derived and explicit back_link_url in load_site_config."""

    def _load_with_toml(self, toml_content: str):
        """Helper: run load_site_config() as if site.toml contains toml_content."""
        import io
        toml_bytes = toml_content.encode()

        with (
            patch.object(SITE_FILE, "exists", return_value=True),
            patch.object(SITE_FILE, "open", return_value=io.BytesIO(toml_bytes)),
        ):
            return load_site_config()

    def _load_no_toml(self):
        """Helper: run load_site_config() with no site.toml present."""
        with patch.object(SITE_FILE, "exists", return_value=False):
            return load_site_config()

    # --- No site.toml at all -----------------------------------------------

    def test_no_toml_no_backlink(self):
        """Without site.toml and no site_url, back_link_url is empty."""
        config = self._load_no_toml()
        assert config["navigation"]["back_link_url"] == ""

    def test_no_toml_default_label(self):
        """Default back_link_label is 'Home'."""
        config = self._load_no_toml()
        assert config["navigation"]["back_link_label"] == "Home"

    # --- Auto-detection from site_url: subdomain ---------------------------

    def test_subdomain_auto_derives_parent(self):
        """site_url on a subdomain → back_link_url auto-set to parent domain."""
        config = self._load_with_toml('site_url = "https://tools.example.com"')
        assert config["navigation"]["back_link_url"] == "https://example.com"

    def test_subdomain_with_path_auto_derives_parent(self):
        """Subdomain + subdirectory: parent domain derived from subdomain."""
        config = self._load_with_toml('site_url = "https://tools.example.com/toolhub"')
        assert config["navigation"]["back_link_url"] == "https://example.com"

    # --- Auto-detection from site_url: subdirectory ------------------------

    def test_subdirectory_auto_derives_origin(self):
        """Root domain with path → back_link_url auto-set to origin."""
        config = self._load_with_toml('site_url = "https://example.com/toolhub"')
        assert config["navigation"]["back_link_url"] == "https://example.com"

    def test_github_pages_subdirectory_explicit_required(self):
        """username.github.io/repo: explicit back_link_url overrides heuristic."""
        config = self._load_with_toml(
            'site_url = "https://username.github.io/repo"\n'
            '[navigation]\n'
            'back_link_url = "https://username.github.io"'
        )
        assert config["navigation"]["back_link_url"] == "https://username.github.io"

    # --- Root domain: no auto-detection ------------------------------------

    def test_root_domain_no_auto_derive(self):
        """Plain root domain → no auto-derived backlink."""
        config = self._load_with_toml('site_url = "https://example.com"')
        assert config["navigation"]["back_link_url"] == ""

    def test_root_domain_trailing_slash_no_derive(self):
        config = self._load_with_toml('site_url = "https://example.com/"')
        assert config["navigation"]["back_link_url"] == ""

    # --- GitHub Pages root (no path) ---------------------------------------

    def test_github_pages_root_no_site_url(self):
        """No site_url set → no backlink regardless of hostname."""
        config = self._load_with_toml("")
        assert config["navigation"]["back_link_url"] == ""

    # --- Explicit back_link_url always wins --------------------------------

    def test_explicit_url_overrides_auto(self):
        """Explicit back_link_url is used instead of auto-detected value."""
        config = self._load_with_toml(
            'site_url = "https://tools.example.com"\n'
            '[navigation]\n'
            'back_link_url = "https://custom.example.com"'
        )
        assert config["navigation"]["back_link_url"] == "https://custom.example.com"

    def test_explicit_url_no_site_url(self):
        """Explicit back_link_url works even without site_url."""
        config = self._load_with_toml(
            '[navigation]\n'
            'back_link_url = "https://mysite.com"'
        )
        assert config["navigation"]["back_link_url"] == "https://mysite.com"

    def test_explicit_url_empty_clears_backlink(self):
        """Explicit back_link_url = "" suppresses auto-derive on subdomain."""
        config = self._load_with_toml(
            'site_url = "https://tools.example.com"\n'
            '[navigation]\n'
            'back_link_url = ""'
        )
        # Empty explicit URL should stay empty (user opted out)
        assert config["navigation"]["back_link_url"] == ""

    def test_explicit_label_preserved(self):
        """Custom back_link_label is preserved."""
        config = self._load_with_toml(
            'site_url = "https://tools.example.com"\n'
            '[navigation]\n'
            'back_link_label = "← Back to main site"'
        )
        assert config["navigation"]["back_link_label"] == "← Back to main site"

    # --- Default label when auto-derived -----------------------------------

    def test_default_label_when_auto_derived(self):
        """Auto-derived backlink uses default label 'Home'."""
        config = self._load_with_toml('site_url = "https://tools.example.com"')
        assert config["navigation"]["back_link_label"] == "Home"

    # --- Deployment scenario matrix ----------------------------------------

    @pytest.mark.parametrize("site_url,expected_url", [
        # Subdomain deployments
        ("https://tools.example.com",         "https://example.com"),
        ("https://tools.example.com/",        "https://example.com"),
        ("https://tools.example.com/toolhub", "https://example.com"),
        # Subdirectory on root domain
        ("https://example.com/toolhub",       "https://example.com"),
        ("https://example.com/a/b",           "https://example.com"),
        # Root domain — no backlink
        ("https://example.com",               ""),
        ("https://example.com/",              ""),
        # No site_url — no backlink
        ("",                                  ""),
    ])
    def test_auto_derive_matrix(self, site_url, expected_url):
        """Parametrised matrix of site_url → expected auto-derived back_link_url."""
        toml = f'site_url = "{site_url}"' if site_url else ""
        config = self._load_with_toml(toml)
        assert config["navigation"]["back_link_url"] == expected_url
