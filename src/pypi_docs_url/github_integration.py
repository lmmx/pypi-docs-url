# pypi_docs_url/github_integration.py
from __future__ import annotations

import re
import requests
import yaml


def parse_github_repo_url(link: str) -> tuple[str, str] | None:
    """
    Extract (org, repo) from a GitHub URL, e.g.:
    'https://github.com/org/repo' => ('org', 'repo')
    """
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)", link)
    if not m:
        return None
    org = m.group(1)
    repo = m.group(2).removesuffix(".git")
    return (org, repo)


def fetch_docs_python_yml(
    session: requests.Session,
    org: str,
    repo: str,
    debug: bool,
) -> str | None:
    """
    Fetch the 'docs-python.yml' workflow file from GitHub if it exists.
    """
    url = f"https://raw.githubusercontent.com/{org}/{repo}/main/.github/workflows/docs-python.yml"
    if debug:
        print(f"[DEBUG] Attempting to fetch workflow at: {url}")
    try:
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            if debug:
                print(f"[DEBUG] Successfully fetched docs-python.yml from {url}")
            return r.text
        if debug:
            print(
                f"[DEBUG] Failed to fetch docs-python.yml from {url}: {r.status_code}",
            )
    except requests.RequestException as exc:
        if debug:
            print(f"[DEBUG] Error fetching docs-python.yml => {exc}")
    return None


def parse_stable_subfolder(workflow_text: str, debug: bool) -> str | None:
    """
    Parse the YAML contents of docs-python.yml to find a 'target-folder' containing 'stable'.
    """
    try:
        config = yaml.safe_load(workflow_text)
    except yaml.YAMLError as exc:
        if debug:
            print(f"[DEBUG] YAML parse error => {exc}")
        return None

    jobs = config.get("jobs", {})
    build_job = jobs.get("build-python-docs", {})
    steps = build_job.get("steps", [])
    for step in steps:
        w = step.get("with")
        if isinstance(w, dict):
            tf = w.get("target-folder")
            if tf and "stable" in tf:
                if debug:
                    print(f"[DEBUG] Found stable target-folder => {tf}")
                return tf

    if debug:
        print("[DEBUG] No stable target-folder found in GH workflow.")
    return None
