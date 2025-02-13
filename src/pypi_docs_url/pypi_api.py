# pypi_docs_url/pypi_api.py
from __future__ import annotations

import re
import requests


def fetch_pypi_json(session: requests.Session, pkg: str, debug: bool) -> dict | None:
    """Fetch JSON metadata for a package from PyPI."""
    url = f"https://pypi.org/pypi/{pkg}/json"
    if debug:
        print(f"[DEBUG] Fetching PyPI JSON at: {url}")
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        if debug:
            print(f"[DEBUG] Successfully fetched PyPI JSON for {pkg}")
        return r.json()
    except requests.RequestException as e:
        if debug:
            print(f"[DEBUG] Failed to fetch PyPI JSON for {pkg}: {e}")
    return None


def find_doc_url_candidate(data: dict, debug: bool) -> str | None:
    """
    From PyPI metadata, attempt to find a doc-like link.
    Priority:
      1) 'project_urls' containing 'doc' or 'Documentation'
      2) 'home_page' if it looks doc-ish
      3) URLs containing 'stable' or 'latest'
      4) Homepage as a fallback
    """
    info = data.get("info", {})
    purls = info.get("project_urls", {})

    # a) doc-labeled in project_urls
    for label, link in purls.items():
        lower_label = label.lower()
        if "doc" in lower_label or "documentation" in lower_label:
            if debug:
                print(f"[DEBUG] Found doc-labeled link in project_urls => {link}")
            return link

    # b) If there's 'Documentation' key exactly
    if "Documentation" in purls:
        link = purls["Documentation"]
        if debug:
            print(f"[DEBUG] Found 'Documentation' key => {link}")
        return link

    # c) if home_page has readthedocs or docs, treat it as doc link
    homepage = info.get("home_page")
    if homepage and any(hint in homepage.lower() for hint in ["readthedocs", "docs"]):
        if debug:
            print(f"[DEBUG] Using home_page as doc link => {homepage}")
        return homepage

    # d) Check for URLs containing 'stable' or 'latest'
    for link in purls.values():
        if isinstance(link, str) and ("stable" in link or "latest" in link):
            if debug:
                print(f"[DEBUG] Found URL containing 'stable' or 'latest' => {link}")
            return link

    # e) Use homepage as a fallback
    if homepage:
        if debug:
            print(f"[DEBUG] Using home_page as a fallback => {homepage}")
        return homepage

    if debug:
        print("[DEBUG] No doc-like candidate found in project_urls or home_page.")
    return None


def find_stable_latest_link(data: dict, debug: bool) -> str | None:
    """
    Scan project_urls + home_page for a link containing 'stable' or 'latest' in the path.
    Return that trimmed base if found.
    E.g. "https://scikit-learn.org/stable/whats_new" => "https://scikit-learn.org/stable"
    """
    info = data.get("info", {})
    purls = info.get("project_urls", {})
    candidates = list(purls.values())
    homepage = info.get("home_page")
    if homepage:
        candidates.append(homepage)

    for link in candidates:
        if not isinstance(link, str):
            continue
        match = re.search(r"(.*?)/(stable|latest)(?:/|$)", link)
        if match:
            base = match.group(1) + "/" + match.group(2)
            if debug:
                print(f"[DEBUG] Found stable/latest link => {link}")
                print(f"[DEBUG] Trimmed base => {base}")
            return base

    if debug:
        print(
            "[DEBUG] No link containing 'stable' or 'latest' found in project_urls/home_page.",
        )
    return None


def find_github_repo_in_project_urls(data: dict, debug: bool) -> str | None:
    """
    Look for a GitHub link in the project_urls or home_page fields from PyPI data.
    """
    info = data.get("info", {})
    purls = info.get("project_urls", {})
    candidates = list(purls.values())
    homepage = info.get("home_page")
    if homepage:
        candidates.append(homepage)

    for link in candidates:
        if isinstance(link, str) and "github.com" in link.lower():
            if debug:
                print(f"[DEBUG] Found GitHub link: {link}")
            return link

    if debug:
        print("[DEBUG] No GitHub link found.")
    return None
