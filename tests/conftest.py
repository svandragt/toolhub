import os

# Set before any test module imports build.py (which reads env at import time).
os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GH_USERNAME", "test-user")
