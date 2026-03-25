# ToolHub

A static site generator that turns a curated list of GitHub repos and gists into a personal tools portfolio — no CMS, no framework, no manual copy-pasting.

Each project page is built from its README, rendered to HTML at build time. Live URLs and docs links are extracted automatically from a `portfolio.toml` convention file you add to each project. Tags come from GitHub Topics (repos) or `portfolio.toml` (gists).

The site deploys automatically to GitHub Pages on every push to `main`.

---
## Screenshots

<img width="1478" height="1014" alt="index" src="https://github.com/user-attachments/assets/2cb81233-96a9-4a6a-a69b-e98d71f84758" />
<img width="1478" height="1014" alt="detail" src="https://github.com/user-attachments/assets/a3492bca-6c9c-4ca7-94f1-d9e16e221e35" />


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

This generates `projects.yaml` from your public repos and gists.

To permanently exclude repos or gists, create an `exclude.txt` (one repo name or gist ID per line, `#` for comments) before running bootstrap. See `exclude.txt.example`.

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

### 6. Customise branding (optional)

By default the site uses the built-in branding (`~/tools`, `Tools & Projects`, etc.).
To change it, copy `site.toml.example` to `site.toml` and edit:

```bash
cp site.toml.example site.toml
```

`site.toml` is gitignored — it's your instance config. CI builds without it and
falls back to the defaults, so **you only need this file if you want to change the
branding or use a custom theme**.

To use a custom theme, point `theme.templates_dir` and `theme.static_dir` at your
own directories:

```toml
[theme]
templates_dir = "my-theme/templates"
static_dir    = "my-theme/static"
```

### 7. Build the site locally

```bash
uv run build.py
```

Open `output/index.html` in your browser to preview.

### 8. Deploy to GitHub Pages

**First-time setup:**

1. Push this repo to GitHub.
2. Go to your repo **Settings → Secrets and variables → Actions → Variables** and add:
   - `GITHUB_USERNAME` = your GitHub username
3. Go to **Settings → Pages** and set the source to the `gh-pages` branch.

From then on, every push to `main` triggers a rebuild and deploy automatically. You can also trigger it manually from the **Actions** tab.

> **Note:** CI builds without `site.toml` and uses the default branding. If you want
> your customised branding on the deployed site, commit your `site.toml` to the repo.

### 9. Deploy to a server via SCP (alternative to GitHub Pages)

After building locally, copy the `output/` directory to any web server:

```bash
scp -r output/ user@yourserver.example.com:/var/www/html/portfolio/
```

Or with `rsync` (faster for incremental updates — only changed files are transferred):

```bash
rsync -az --delete output/ user@yourserver.example.com:/var/www/html/portfolio/
```

The `--delete` flag removes files on the server that no longer exist locally, keeping
the remote in sync with your build.

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

## Constraints & known limitations

| Constraint | Detail |
|---|---|
| Personal GitHub accounts only | The pinned items query uses the GraphQL `user` type, which doesn't apply to organisations |
| Public repos and gists only | Private content is intentionally excluded — this is a public portfolio tool |
| Gists must contain a `.md` file | Gists without markdown are skipped by bootstrap |
| Maximum 6 pinned items | GitHub's own limit on pinned profile items |

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

Dependencies are declared inline in each script via [PEP 723](https://peps.python.org/pep-0723/) and installed automatically by `uv run`.
