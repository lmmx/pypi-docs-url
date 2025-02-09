# pypi_docs_url/core.py
from __future__ import annotations

import requests

# Import helpers from the other modules
from .pypi_api import (
    fetch_pypi_json,
    find_doc_url_candidate,
    find_stable_latest_link,
    find_github_repo_in_project_urls,
)
from .github_integration import (
    parse_github_repo_url,
    fetch_docs_python_yml,
    parse_stable_subfolder,
)
from .docs_intersphinx import (
    try_intersphinx_expansions,
    parse_domain_from_url,
)


def get_intersphinx_url(package_name: str, debug: bool = False) -> str | None:
    """
    Attempt to discover a Python package's intersphinx `objects.inv` URL by:

      1) Checking PyPI metadata for doc-labeled links or stable/latest.
      2) If not found, parse the fallback GitHub workflow `.github/workflows/docs-python.yml`.
    """
    with requests.Session() as session:
        # Step A: Fetch PyPI JSON
        data = fetch_pypi_json(session, package_name, debug)
        if not data:
            return None

        # Step B: doc-labeled link expansions
        doc_candidate = find_doc_url_candidate(data, debug)
        if doc_candidate:
            inv_url = try_intersphinx_expansions(session, doc_candidate, debug)
            if inv_url:
                return inv_url

        # Step C: stable/latest approach
        stable_candidate = find_stable_latest_link(data, debug)
        if stable_candidate:
            inv_url = try_intersphinx_expansions(session, stable_candidate, debug)
            if inv_url:
                return inv_url

        # Step D: Fallback GH approach
        gh_repo_link = find_github_repo_in_project_urls(data, debug)
        if not gh_repo_link:
            if debug:
                print("[DEBUG] No GitHub link found; can't do fallback GH workflow logic.")
            return None

        orgrepo = parse_github_repo_url(gh_repo_link)
        if not orgrepo:
            if debug:
                print("[DEBUG] Could not parse org/repo from GitHub link.")
            return None
        org, repo = orgrepo

        if debug:
            print(f"[DEBUG] Attempting fallback GH workflow approach with {org}/{repo}")

        # fetch docs-python.yml
        workflow_text = fetch_docs_python_yml(session, org, repo, debug)
        if not workflow_text:
            return None

        # parse stable subfolder
        stable_tf = parse_stable_subfolder(workflow_text, debug)
        if not stable_tf:
            return None

        # guess domain from doc_candidate or stable_candidate
        domain = None
        for candidate in (doc_candidate, stable_candidate):
            if candidate:
                d = parse_domain_from_url(candidate, debug)
                if d:
                    domain = d
                    break
        if not domain:
            # Fallback domain if none
            domain = "docs.pola.rs"

        stable_tf = stable_tf.strip("/")
        guess = f"https://{domain}/{stable_tf}/objects.inv"

        if debug:
            print(f"[DEBUG] Attempting HEAD request for fallback guess => {guess}")

        resp = session.head(guess, allow_redirects=True, timeout=10)
        if resp.status_code == 200:
            if debug:
                print("[DEBUG] Fallback GH approach found a valid objects.inv!")
            return guess

        if debug:
            print("[DEBUG] All approaches failed.")
        return None
