#!/usr/bin/env python3

import json
import re
import sys
import yaml  # pip install pyyaml
import httpx

"""
Traces a causal chain from a package name on PyPI to a final guess
for the 'objects.inv' location, logging each step but without dumping
the entire PyPI JSON or entire workflow file. Instead, we show only
the relevant bits.

Usage:
  python pypi_to_objects_inv_trace.py [package_name]

If no package_name is given, defaults to "polars".
"""


def safe_print_dict(title: str, d: dict, keys: list[str]):
    """
    Nicely print only selected `keys` from dict `d` under a given title.
    If a key doesn't exist, skip it.
    """
    print(f"\n=== {title} ===")
    for k in keys:
        if k in d:
            print(f"{k}: {d[k]}")


def fetch_pypi_json(client: httpx.Client, package: str) -> dict:
    """Fetch minimal PyPI JSON for the given package."""
    url = f"https://pypi.org/pypi/{package}/json"
    print(f"\n[1] Fetching PyPI JSON at: {url}")
    resp = client.get(url)
    resp.raise_for_status()
    return resp.json()


def log_relevant_pypi_info(data: dict):
    """Print only the fields from PyPI JSON we rely on: project_urls, home_page."""
    info = data.get("info", {})
    purls = info.get("project_urls", {})
    homepage = info.get("home_page")
    print("\n[1a] Relevant PyPI fields:")
    print(f"  project_urls: {json.dumps(purls, indent=2)}")
    if homepage:
        print(f"  home_page: {homepage}")


def find_doc_link_in_project_urls(data: dict) -> str | None:
    """Look for a link containing 'doc' in data["info"]["project_urls"]."""
    info = data.get("info", {})
    purls = info.get("project_urls", {})
    for label, link in purls.items():
        if "doc" in label.lower():
            return link
    return None


def find_github_repo_in_project_urls(data: dict) -> str | None:
    """
    Return the first link referencing github.com from project_urls or home_page.
    """
    info = data.get("info", {})
    purls = info.get("project_urls", {})
    candidates = list(purls.values())
    if info.get("home_page"):
        candidates.append(info["home_page"])

    for c in candidates:
        if isinstance(c, str) and "github.com" in c.lower():
            return c
    return None


def parse_github_repo_url(link: str) -> tuple[str, str] | None:
    """
    Parse https://github.com/ORG/REPO => (ORG, REPO).
    """
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)", link)
    if not m:
        return None
    org = m.group(1)
    repo = m.group(2).removesuffix(".git")
    return (org, repo)


def fetch_docs_python_yml(
    client: httpx.Client,
    org: str,
    repo: str,
    branch="main",
) -> str | None:
    """
    Retrieve docs-python.yml from:
      https://raw.githubusercontent.com/<org>/<repo>/<branch>/.github/workflows/docs-python.yml
    Return raw text if found.
    """
    url = f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/.github/workflows/docs-python.yml"
    print(f"\n[2] Attempting to fetch workflow at: {url}")
    r = client.get(url)
    if r.status_code == 200:
        return r.text
    return None


def log_selected_lines(workflow_text: str):
    """
    Print only lines containing 'deploy' or 'target-folder' to illustrate how docs are published
    without dumping everything.
    """
    print(
        "\n[2a] Key lines from docs-python.yml (containing 'deploy' or 'target-folder'):",
    )
    lines = workflow_text.splitlines()
    for ln in lines:
        lower = ln.lower()
        if "deploy" in lower or "target-folder" in lower:
            print("  " + ln)


def parse_stable_subfolder(yml_text: str) -> str | None:
    """
    Parse docs-python.yml as YAML, look for a step with 'target-folder' containing 'stable'.
    Return that string if found.
    """
    config = yaml.safe_load(yml_text)  # assume it parses
    jobs = config.get("jobs", {})
    build_job = jobs.get("build-python-docs", {})
    steps = build_job.get("steps", [])
    for step in steps:
        if isinstance(step.get("with"), dict):
            tf = step["with"].get("target-folder")
            if tf and "stable" in tf:
                return tf
    return None


def main():
    pkg = sys.argv[1] if len(sys.argv) > 1 else "polars"
    print(
        f"** Attempting to discover {pkg}'s objects.inv via PyPI → GH workflow logic **",
    )

    with httpx.Client() as client:
        # [1] PyPI JSON
        data = fetch_pypi_json(client, pkg)
        log_relevant_pypi_info(data)

        # a) see if doc link
        doc_link = find_doc_link_in_project_urls(data)
        if doc_link:
            print(f"\n[1b] Found doc link in project_urls => {doc_link}")
        else:
            print("\n[1b] No doc link found in project_urls")

        # b) see if we can find GH repo
        gh_repo_link = find_github_repo_in_project_urls(data)
        if gh_repo_link:
            print(f"\n[1c] Found GitHub link => {gh_repo_link}")
        else:
            print("\n[1c] No GitHub link found, can't parse workflows. Stopping.")
            return

        orgrepo = parse_github_repo_url(gh_repo_link)
        if not orgrepo:
            print("\n[1d] Could not parse org/repo from GitHub link.")
            return
        org, repo = orgrepo
        print(f"\n[1d] Parsed org={org}, repo={repo}")

        # [2] fetch docs-python.yml
        workflow_text = fetch_docs_python_yml(client, org, repo, branch="main")
        if not workflow_text:
            print("\n[2b] docs-python.yml not found. Stopping.")
            return

        # Print only lines referencing deploy or target-folder
        log_selected_lines(workflow_text)

        stable_tf = parse_stable_subfolder(workflow_text)
        if not stable_tf:
            print(
                "\n[2c] No stable subfolder found in that workflow. Possibly dev only.",
            )
            return
        print(f"\n[2c] Stable subfolder => {stable_tf}")

        # [3] Build final guess for objects.inv
        # We see that polars actually uses domain "docs.pola.rs"
        # But we can guess it from doc_link domain if we want:
        domain = "docs.pola.rs"
        if doc_link:
            # Try to parse domain from doc_link, e.g. https://docs.pola.rs/api/python/stable/...
            m = re.match(r"https?://([^/]+)/", doc_link)
            if m:
                domain = m.group(1)
        stable_tf = stable_tf.strip("/")
        guess_url = f"https://{domain}/{stable_tf}/objects.inv"

        print(f"\n[3] Final guess => {guess_url}")
        print("Performing HEAD request...")

        r = client.head(guess_url, follow_redirects=True, timeout=10)
        print(f"Response status: {r.status_code}, final URL => {r.url}")
        if r.status_code == 200:
            print("Looks like we found objects.inv!")
        else:
            print("Not 200. Possibly missing or hosted elsewhere.")


if __name__ == "__main__":
    main()
