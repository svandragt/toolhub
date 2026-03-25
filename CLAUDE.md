# ToolHub — CLAUDE.md

## What this is
Static site generator that builds a personal tools portfolio from GitHub repos and gists.
Two scripts, both run with `uv run` (PEP 723 inline deps — no venv setup needed):
- `uv run bootstrap.py` — seed/refresh `projects.yaml` from the GitHub API (run manually)
- `uv run build.py` — fetch READMEs, render Jinja2 templates, write `output/`

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

## GitHub API notes
- REST: `/user/repos` for repos, `/users/{username}/gists` for public gists only
- GraphQL: `POST /graphql` used to fetch pinned items (up to 6)
- Token needs: `Contents: Read`, `Metadata: Read`, plus GraphQL access
- Pagination uses `seen_urls` guard to prevent infinite loops
- Portfolio data and READMEs are both cached under `.cache/`, respecting `CACHE_TTL_HOURS`

## projects.yaml fields
Repos: `name`, `type=repo`, `repo_url`, `description`, `tags` (from GitHub Topics), `updated_at`, `archived`, optionally `homepage`
Gists: `name`, `type=gist`, `gist_id`, `gist_url`, `md_file`, `description`, `tags` (from portfolio.toml), `updated_at`

## Build enrichment
`build.py` merges `portfolio.toml` fields on top of each entry at build time:
- `live_url`, `docs_url` — override/supplement what's in projects.yaml
- `pinned` — added at build time via GraphQL query, not stored in projects.yaml

Sort order: pinned (0) → active (1) → archived (2), then `updated_at` desc within each group.

## Templates
Jinja2 templates in `templates/`. Base path for CSS differs between index (`static/`) and project pages (`../static/`), handled via `{% block stylesheets %}` override in `project.html`.

Index sections: Pinned / Active projects / Archived. Filter bar (JS) and TOC (shown when 2+ sections and >15 projects) are inline in `index.html`.

## CI
`.github/workflows/build.yml` — triggers on push to main and `workflow_dispatch`.
Requires repo variable `GITHUB_USERNAME` (Settings → Secrets and variables → Actions → Variables).
Uses built-in `GITHUB_TOKEN`. Deploys `output/` to `gh-pages` via `peaceiris/actions-gh-pages@v4`.
