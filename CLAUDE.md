# ToolHub — CLAUDE.md

## What this is
Static site generator that builds a personal tools portfolio from GitHub repos and gists.
Two scripts, both run with `uv run` (PEP 723 inline deps — no venv setup needed):
- `uv run bootstrap.py` — seed/refresh `projects.yaml` from the GitHub API (run manually)
- `uv run build.py` — fetch READMEs, render Jinja2 templates, write `output/`

## Repository layout
```
toolhub/
├── bootstrap.py              # Seed script: GitHub API → projects.yaml
├── build.py                  # Main generator: projects.yaml + READMEs → HTML
├── lib/
│   ├── __init__.py
│   └── github.py             # Shared GitHub API helpers (pagination, REST, GraphQL)
├── templates/
│   ├── base.html             # Base layout (header, footer, stylesheet block)
│   ├── index.html            # Portfolio index with JS filter bar and TOC
│   ├── project.html          # Individual project detail page
│   └── feed.xml              # Atom 1.0 feed template
├── static/
│   └── style.css             # Portfolio styling (light theme)
├── tests/
│   ├── conftest.py           # Sets GITHUB_TOKEN / GH_USERNAME env vars for import
│   ├── test_backlink.py      # Tests for _derive_parent_url() and load_site_config()
│   └── test_feed.py          # Tests for Atom feed generation
├── .github/workflows/
│   └── build.yml             # CI: test → bootstrap → build → deploy gh-pages
├── pyproject.toml            # Project metadata + pytest config
├── site.toml.example         # All site.toml options (committed; actual file gitignored)
├── portfolio.toml.example    # Convention for per-project portfolio.toml files
└── exclude.txt.example       # Template for the optional exclusion list
```

Gitignored at runtime: `.env`, `projects.yaml`, `exclude.txt`, `.cache/`, `output/`

## Key files
| File | Role |
|---|---|
| `bootstrap.py` | Fetches repos+gists, writes `projects.yaml` |
| `build.py` | Reads `projects.yaml`, fetches READMEs, renders site |
| `lib/github.py` | Shared GitHub API helpers (pagination, fetching, GraphQL) |
| `projects.yaml` | Gitignored — user-local project list |
| `exclude.txt` | Gitignored — optional, one repo name or gist ID per line to skip |
| `.cache/` | Gitignored — cached READMEs (`.md`) and portfolio data (`.portfolio.json`) |
| `output/` | Gitignored — generated site, deployed to gh-pages |

## Environment variables
Set in `.env` (copy from `.env.example`):

| Variable | Required | Description |
|---|---|---|
| `GITHUB_TOKEN` | Yes | Personal access token (needs `Contents: Read`, `Metadata: Read`, GraphQL) |
| `GH_USERNAME` | Yes | GitHub username to fetch repos/gists for |
| `CACHE_TTL_HOURS` | No | How long to cache READMEs and portfolio data (default: 24) |
| `CUSTOM_DOMAIN` | No | Used by build.py to derive canonical site URL and parent back-link |
| `GITHUB_REPOSITORY` | No | Fallback for deriving site URL if CUSTOM_DOMAIN not set (set automatically in CI) |

## Entry points
1. **Bootstrap (one-time or to refresh):** `uv run bootstrap.py`
   - Reads `.env`, calls GitHub REST API, writes `projects.yaml`
2. **Build (recurring):** `uv run build.py`
   - Reads `projects.yaml` + optional `site.toml`, fetches/caches READMEs, writes `output/`
3. **Tests:** `uv run --group test pytest`

## Instance configuration (site.toml)
Optional `site.toml` in repo root (gitignored). Loaded by `build.py` via `tomllib`,
deep-merged with `_SITE_DEFAULTS`. Controls:
- `title`, `description`, `footer`, `url`, `author` — passed to Jinja2 as `{{ site.* }}`
- `[navigation]` — `back_link_url`, `back_link_label` for the header back-link
- `[sections]` — `active`, `archived`, `back_link` section labels, as `{{ sections.* }}`
- `[feed]` — `max_entries` (caps Atom feed length)
- `[theme]` — `templates_dir`, `static_dir` — override which dirs are used for templates/CSS

See `site.toml.example` for all options. `site.toml` is gitignored; `site.toml.example` is committed.

The back-link URL is auto-derived from `CUSTOM_DOMAIN` or `GITHUB_REPOSITORY` via
`_derive_parent_url()` (strips subdomain or repo path segment), but can be overridden in
`site.toml` under `[navigation]`.

## Cache versioning
`BOOTSTRAP_VERSION` in `lib/github.py` gates `projects.yaml` compatibility.
Bump it whenever bootstrap produces new required fields. `build.py` will exit with
a "re-run bootstrap" message if the file's version is behind.
Current version: **2** (added `created_at`, `latest_release_at` for repos).

## GitHub API notes
- REST: `/user/repos` for repos, `/users/{username}/gists` for public gists only
- GraphQL: `POST /graphql` used to fetch pinned items (up to 6)
- Token needs: `Contents: Read`, `Metadata: Read`, plus GraphQL access
- Pagination uses `seen_urls` guard to prevent infinite loops
- Portfolio data and READMEs are both cached under `.cache/`, respecting `CACHE_TTL_HOURS`
- README fetch failures fall back to stale cache; portfolio.toml errors return `{}`

## projects.yaml fields
Repos: `name`, `type=repo`, `repo_url`, `description`, `tags` (from GitHub Topics),
`created_at`, `updated_at`, `archived`, optionally `homepage`, optionally `latest_release_at`

Gists: `name`, `type=gist`, `gist_id`, `gist_url`, `md_file`, `description`,
`tags` (from portfolio.toml), `created_at`, `updated_at`

## Build enrichment
`build.py` merges `portfolio.toml` fields on top of each entry at build time:
- `live_url`, `docs_url` — override/supplement what's in projects.yaml
- `pinned` — added at build time via GraphQL query, not stored in projects.yaml

Sort order: pinned (0) → active (1) → archived (2), then `updated_at` desc within each group.

## Templates
Jinja2 templates in `templates/`. Base path for CSS differs between index (`static/`) and
project pages (`../static/`), handled via `{% block stylesheets %}` override in `project.html`.

Index sections: Pinned / Active projects / Archived. Filter bar (JS) and TOC (shown when
2+ sections and >15 projects) are inline in `index.html`.

The `feed.xml` template produces Atom 1.0. Archived projects and projects without a date are
excluded. The `<updated>` for each entry uses `latest_release_at` if present, else `created_at`.

## portfolio.toml convention
Each individual project can have a `portfolio.toml` at its root (repos) or as a gist file.
Recognised fields:
- `live_url` — where the project runs (web apps)
- `docs_url` — documentation site
- `tags` — for gists only (repos use GitHub Topics instead)

## Testing
Tests live in `tests/` and use pytest. Run with:
```
uv run --group test pytest
```

- `tests/conftest.py` — sets dummy env vars so build.py can be imported without a real `.env`
- `tests/test_backlink.py` — unit tests for `_derive_parent_url()` (subdomain/path stripping)
  and integration tests for `load_site_config()` merging
- `tests/test_feed.py` — tests that `feed.xml` renders valid Atom 1.0 XML and respects
  `feed.max_entries`

## CI
`.github/workflows/build.yml` — triggers on push to main, `workflow_dispatch`, and daily cron
(06:00 UTC). Pipeline: run tests → bootstrap → build (with `CACHE_TTL_HOURS=0`) → deploy.

CI secrets/variables:
| Name | Type | Description |
|---|---|---|
| `GH_TOKEN` | Secret | Personal access token (used instead of built-in GITHUB_TOKEN for API access) |
| `GH_USERNAME` | Variable | GitHub username |
| `CUSTOM_DOMAIN` | Variable | Optional — written as CNAME file and used for canonical URL |

Deploys `output/` to `gh-pages` via `peaceiris/actions-gh-pages@v4`.

## Key design patterns

**Version gating:** Bump `BOOTSTRAP_VERSION` in `lib/github.py` whenever bootstrap adds a new
required field. `build.py` checks this on load and exits with a message if stale.

**Deep merge:** `_deep_merge()` recursively merges `site.toml` over `_SITE_DEFAULTS`, so
partial configs don't erase unspecified keys.

**Caching:** READMEs cached as `.cache/{slug}.md`; portfolio metadata as
`.cache/{slug}.portfolio.json`. TTL controlled by `CACHE_TTL_HOURS`. On network errors,
stale cache is used as fallback. CI always sets `CACHE_TTL_HOURS=0`.

**Graceful degradation:** README fetch errors → stale cache or placeholder. portfolio.toml
parse errors → logged warning, empty dict returned. GraphQL pinned query failure → empty set.

**No venv:** All scripts use PEP 723 inline dependency metadata; `uv run` handles everything.
Don't add a `requirements.txt` or `setup.py` — keep using the inline `# /// script` headers.
