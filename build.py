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
    GITHUB_USERNAME   — your GitHub username
    CACHE_TTL_HOURS   — float, how old a cached README can be before re-fetching
                        (default: 1.0 — set to 0 on CI to always re-fetch)

Output:
    output/           — ready to deploy to GitHub Pages
"""

import os
import shutil
import sys
import time
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
    fetch_gist_portfolio,
    fetch_gist_readme,
    fetch_repo_portfolio,
    fetch_repo_readme,
    make_client,
)

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN")
USERNAME = os.getenv("GITHUB_USERNAME")
CACHE_TTL_HOURS = float(os.getenv("CACHE_TTL_HOURS", "1.0"))

if not TOKEN or not USERNAME:
    sys.exit(
        "ERROR: GITHUB_TOKEN and GITHUB_USERNAME must be set in .env\n"
        "See .env.example for reference."
    )

CACHE_DIR = Path(".cache")
OUTPUT_DIR = Path("output")
STATIC_DIR = Path("static")
TEMPLATES_DIR = Path("templates")
PROJECTS_FILE = Path("projects.yaml")


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
    """Fetch portfolio.toml for a project, returning {} if not present."""
    if project["type"] == "repo":
        return fetch_repo_portfolio(client, USERNAME, project["name"])
    else:
        # Fetch the full gist object to pass to fetch_gist_portfolio
        from lib.github import BASE_URL
        response = client.get(f"{BASE_URL}/gists/{project['gist_id']}")
        response.raise_for_status()
        return fetch_gist_portfolio(client, response.json())


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
    return data["projects"]


# --------------------------------------------------------------------------- #
# Build site
# --------------------------------------------------------------------------- #

def build(projects: list[dict], client: httpx.Client) -> None:
    """Render the full static site into output/."""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()

    if STATIC_DIR.exists():
        shutil.copytree(STATIC_DIR, OUTPUT_DIR / "static")

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )

    enriched_projects = []

    project_template = env.get_template("project.html")
    for project in projects:
        # Merge portfolio.toml fields into the project dict
        portfolio = get_portfolio(client, project)
        enriched = {**project, **portfolio}
        enriched_projects.append(enriched)

        readme_md = get_readme(client, project)
        readme_html = render_markdown(readme_md)

        page_dir = OUTPUT_DIR / project["name"]
        page_dir.mkdir(parents=True, exist_ok=True)

        rendered = project_template.render(
            project=enriched,
            readme_html=readme_html,
        )
        (page_dir / "index.html").write_text(rendered, encoding="utf-8")

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

    print(f"Loading projects from {PROJECTS_FILE}...")
    projects = load_projects()
    print(f"  Found {len(projects)} projects")
    print(f"  Cache TTL: {CACHE_TTL_HOURS}h")

    print("\nFetching READMEs and portfolio metadata...")
    with make_client(TOKEN) as client:
        build(projects, client)


if __name__ == "__main__":
    main()
