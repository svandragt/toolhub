# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx",
#   "python-dotenv",
#   "ruamel.yaml",
#   "markdown-it-py",
#   "jinja2",
# ]
# ///
"""
build.py — generate the static portfolio site from projects.yaml.

Usage (run from repo root):
    uv run build.py

Reads from .env:
    GITHUB_TOKEN      — personal access token (read-only contents scope)
    GH_USERNAME   — your GitHub username
    CACHE_TTL_HOURS   — float, how old a cached README can be before re-fetching
                        (default: 1.0 — set to 0 on CI to always re-fetch)

Output:
    output/           — ready to deploy to GitHub Pages
"""

import json
import os
import shutil
import sys
import time
import tomllib
from pathlib import Path

import httpx
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from ruamel.yaml import YAML

# Guard: must be run from the repo root so lib/ is importable
if not Path("lib/github.py").exists():
    sys.exit("ERROR: Run this script from the repo root directory.")

from lib.github import (
    BOOTSTRAP_VERSION,
    fetch_gist_portfolio,
    fetch_gist_readme,
    fetch_pinned_names,
    fetch_repo_portfolio,
    fetch_repo_readme,
    make_client,
)

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN")
USERNAME = os.getenv("GH_USERNAME")
CACHE_TTL_HOURS = float(os.getenv("CACHE_TTL_HOURS", "1.0"))

if not TOKEN or not USERNAME:
    sys.exit(
        "ERROR: GITHUB_TOKEN and GH_USERNAME must be set in .env\n"
        "See .env.example for reference."
    )

CACHE_DIR = Path(".cache")
OUTPUT_DIR = Path("output")
PROJECTS_FILE = Path("projects.yaml")
SITE_FILE = Path("site.toml")

_SITE_DEFAULTS: dict = {
    "title": "~/tools",
    "description": "Tools & Projects",
    "footer": "Built with GitHub + uv",
    "sections": {
        "active": "Active projects",
        "archived": "Archived",
        "back_link": "all projects",
    },
    "theme": {
        "templates_dir": "templates",
        "static_dir": "static",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = {**base}
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_site_config() -> dict:
    """Load site.toml if present, merging with defaults."""
    if not SITE_FILE.exists():
        return _deep_merge({}, _SITE_DEFAULTS)
    with SITE_FILE.open("rb") as f:
        return _deep_merge(_deep_merge({}, _SITE_DEFAULTS), tomllib.load(f))


# --------------------------------------------------------------------------- #
# Cache helpers
# --------------------------------------------------------------------------- #

def is_stale(cache_file: Path, ttl_hours: float) -> bool:
    """Return True if the cache file is missing or older than ttl_hours."""
    if not cache_file.exists():
        return True
    if ttl_hours == 0:
        return True
    age_seconds = time.time() - cache_file.stat().st_mtime
    return age_seconds > ttl_hours * 3600


def get_readme(client: httpx.Client, project: dict) -> str:
    """Return README markdown, using cache if fresh enough."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{project['name']}.md"

    if not is_stale(cache_file, CACHE_TTL_HOURS):
        print(f"  [cache] {project['name']}")
        return cache_file.read_text(encoding="utf-8")

    print(f"  [fetch] {project['name']}")
    try:
        if project["type"] == "repo":
            content = fetch_repo_readme(client, USERNAME, project["name"])
        else:
            # Pass a minimal gist-like dict — only files + id needed
            content = fetch_gist_readme(client, {
                "id": project["gist_id"],
                "files": {project["md_file"]: {"raw_url": _gist_raw_url(client, project)}},
            })
    except httpx.HTTPStatusError as e:
        print(f"  [warn]  Could not fetch README for {project['name']}: {e}")
        if cache_file.exists():
            print(f"  [warn]  Using stale cache for {project['name']}")
            return cache_file.read_text(encoding="utf-8")
        return f"_README not available for {project['name']}._"

    cache_file.write_text(content, encoding="utf-8")
    return content


def _gist_raw_url(client: httpx.Client, project: dict) -> str:
    """Resolve the raw_url for a gist's .md file via the API."""
    from lib.github import BASE_URL
    response = client.get(f"{BASE_URL}/gists/{project['gist_id']}")
    response.raise_for_status()
    return response.json()["files"][project["md_file"]]["raw_url"]


def get_portfolio(client: httpx.Client, project: dict) -> dict:
    """Fetch portfolio.toml for a project, using cache if fresh enough."""
    import json
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{project['name']}.portfolio.json"

    if not is_stale(cache_file, CACHE_TTL_HOURS):
        return json.loads(cache_file.read_text(encoding="utf-8"))

    if project["type"] == "repo":
        data = fetch_repo_portfolio(client, USERNAME, project["name"])
    else:
        from lib.github import BASE_URL
        response = client.get(f"{BASE_URL}/gists/{project['gist_id']}")
        response.raise_for_status()
        data = fetch_gist_portfolio(client, response.json())

    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #

def render_markdown(md_text: str) -> str:
    """Convert markdown to HTML using CommonMark spec."""
    md = MarkdownIt("commonmark")
    return md.render(md_text)


# --------------------------------------------------------------------------- #
# Load projects
# --------------------------------------------------------------------------- #

def load_projects() -> list[dict]:
    """Read and return the list of projects from projects.yaml."""
    yaml = YAML()
    data = yaml.load(PROJECTS_FILE)
    file_version = data.get("version", 0)
    if file_version < BOOTSTRAP_VERSION:
        sys.exit(
            f"ERROR: projects.yaml is at version {file_version}, "
            f"but version {BOOTSTRAP_VERSION} is required.\n"
            "Re-run: uv run bootstrap.py"
        )
    return data["projects"]


# --------------------------------------------------------------------------- #
# Build site
# --------------------------------------------------------------------------- #

def build(
    projects: list[dict],
    client: httpx.Client,
    pinned: set[str] | None = None,
    site_config: dict | None = None,
) -> None:
    """Render the full static site into output/."""
    site_config = site_config or _deep_merge({}, _SITE_DEFAULTS)
    static_dir = Path(site_config["theme"]["static_dir"])
    templates_dir = Path(site_config["theme"]["templates_dir"])

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()

    if static_dir.exists():
        shutil.copytree(static_dir, OUTPUT_DIR / "static")

    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["site"] = site_config
    env.globals["sections"] = site_config["sections"]

    pinned = pinned or set()
    used_slugs: set[str] = set()
    enriched_projects = []

    project_template = env.get_template("project.html")
    for project in projects:
        # Merge portfolio.toml fields into the project dict
        portfolio = get_portfolio(client, project)
        # A project is pinned by repo name or gist ID
        pin_key = project["name"] if project["type"] == "repo" else project.get("gist_id", "")
        # Deduplicate output slugs (repo and gist can share the same name)
        slug = project["name"]
        if slug in used_slugs:
            slug = f"{slug}-{project.get('gist_id', project['name'])[:7]}"
        used_slugs.add(slug)
        enriched = {**project, **portfolio, "pinned": pin_key in pinned, "slug": slug}
        enriched_projects.append(enriched)

        readme_md = get_readme(client, project)
        readme_html = render_markdown(readme_md)

        page_dir = OUTPUT_DIR / slug
        page_dir.mkdir(parents=True, exist_ok=True)

        rendered = project_template.render(
            project=enriched,
            readme_html=readme_html,
        )
        (page_dir / "index.html").write_text(rendered, encoding="utf-8")

    def section_order(p: dict) -> int:
        if p.get("pinned"):
            return 0
        if p.get("archived"):
            return 2
        return 1

    # Sort by recency descending first (stable), then by section (stable)
    enriched_projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
    enriched_projects.sort(key=section_order)

    index_template = env.get_template("index.html")
    rendered_index = index_template.render(projects=enriched_projects)
    (OUTPUT_DIR / "index.html").write_text(rendered_index, encoding="utf-8")

    print(f"\nBuilt {len(projects)} project pages → {OUTPUT_DIR}/")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    if not PROJECTS_FILE.exists():
        sys.exit(
            "ERROR: projects.yaml not found.\n"
            "Run bootstrap.py first to generate it."
        )

    site_config = load_site_config()
    print(f"Site: {site_config['title']}")

    print(f"Loading projects from {PROJECTS_FILE}...")
    projects = load_projects()
    print(f"  Found {len(projects)} projects")
    print(f"  Cache TTL: {CACHE_TTL_HOURS}h")

    print("\nFetching pinned items...")
    with make_client(TOKEN) as client:
        pinned = fetch_pinned_names(client, USERNAME)
        print(f"  Pinned: {', '.join(sorted(pinned)) or 'none'}")

        print("\nFetching READMEs and portfolio metadata...")
        build(projects, client, pinned, site_config)


if __name__ == "__main__":
    main()
