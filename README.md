# dev-portfolio-hub

A static site generator that turns a curated list of GitHub repos and gists into a personal tools portfolio — no CMS, no framework, no manual copy-pasting.

Each project page is built from its README, rendered to HTML at build time. Live URLs and docs links are extracted automatically from a `portfolio.toml` convention file you add to each project. Tags come from GitHub Topics (repos) or `portfolio.toml` (gists).

The site deploys automatically to GitHub Pages on every push to `main`.

---

## How it works

```
portfolio.toml         ← add to each repo/gist (live_url, docs_url)
GitHub Topics          ← set on each repo for tags
        ↓
bootstrap.py           ← seeds projects.yaml from the GitHub API (run once)
        ↓
projects.yaml          ← your curated project list (edit to remove unwanted entries)
        ↓
build.py               ← fetches READMEs, renders HTML, writes output/
        ↓
output/                ← deployed to GitHub Pages via CI
```

---

## Project structure

```
.
├── .cache/                        # gitignored — cached README files
├── .env                           # gitignored — secrets and config
├── .env.example                   # committed — safe config template
├── .github/
│   └── workflows/
│       └── build.yml              # CI: build and deploy on push to main
├── .gitignore
├── bootstrap.py                   # one-time seed script
├── build.py                       # site generator
├── lib/
│   └── github.py                  # shared GitHub API helpers
├── output/                        # gitignored locally — generated site
├── portfolio.toml.example         # convention template for your projects
├── projects.yaml                  # your curated project list
├── static/
│   └── style.css
└── templates/
    ├── base.html
    ├── index.html
    └── project.html
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/dev-portfolio-hub
cd dev-portfolio-hub
```

### 2. Create a GitHub personal access token

Go to [github.com/settings/tokens](https://github.com/settings/tokens) and create a **fine-grained token** with:

- **Repository access:** All public repositories (read-only)
- **Permissions:** `Contents: Read`, `Metadata: Read`

### 3. Configure your environment

```bash
cp .env.example .env
```

Edit `.env`:

```ini
GITHUB_TOKEN=ghp_yourtoken
GITHUB_USERNAME=yourusername
CACHE_TTL_HOURS=1.0
```

### 4. Seed your project list

```bash
uv run bootstrap.py
```

This generates `projects.yaml` from your public repos and gists. Open it and remove any entries you don't want in the portfolio.

### 5. Add `portfolio.toml` to your projects

For any project that has a live URL or docs site, add a `portfolio.toml` to its root:

```toml
live_url = "https://mytool.example.com"
docs_url = "https://docs.example.com/mytool"
```

For gists, you can also add tags (repos use GitHub Topics instead):

```toml
tags = ["python", "cli"]
```

See `portfolio.toml.example` for a full reference.

### 6. Build the site locally

```bash
uv run build.py
```

Open `output/index.html` in your browser to preview.

### 7. Deploy to GitHub Pages

**First-time setup:**

1. Push this repo to GitHub.
2. Go to your repo **Settings → Secrets and variables → Actions → Variables** and add:
   - `GITHUB_USERNAME` = your GitHub username
3. Go to **Settings → Pages** and set the source to the `gh-pages` branch.

From then on, every push to `main` triggers a rebuild and deploy automatically. You can also trigger it manually from the **Actions** tab.

---

## Keeping the portfolio up to date

| Task | What to do |
|---|---|
| Add a new project | Re-run `uv run bootstrap.py`, review `projects.yaml` |
| Add a live URL | Add `portfolio.toml` to that repo/gist |
| Update tags (repo) | Set GitHub Topics on the repo |
| Update tags (gist) | Edit `portfolio.toml` in the gist |
| Refresh README content | Cache expires per `CACHE_TTL_HOURS`, or push to trigger CI |

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `GITHUB_TOKEN` | — | GitHub personal access token |
| `GITHUB_USERNAME` | — | Your GitHub username |
| `CACHE_TTL_HOURS` | `1.0` | Hours before a cached README is re-fetched. Set to `0` to always re-fetch. |

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

Dependencies are declared inline in each script via [PEP 723](https://peps.python.org/pep-0723/) and installed automatically by `uv run`.
