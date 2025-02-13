# pypi_docs_url/docs_intersphinx.py
from __future__ import annotations

import re
import requests


def try_intersphinx_expansions(
    session: requests.Session,
    base_url: str,
    debug: bool,
) -> str | None:
    """
    Attempt multiple expansions on `base_url` to find a valid `objects.inv`.
    Return the first 200 success, or None.
    """
    trimmed = base_url.strip()
    # remove trailing .html or .htm
    if trimmed.endswith(".html"):
        trimmed = trimmed[: -len(".html")]
    elif trimmed.endswith(".htm"):
        trimmed = trimmed[: -len(".htm")]

    trimmed = trimmed.rstrip("/")
    expansions = [
        "objects.inv",
        "stable/objects.inv",
        "en/stable/objects.inv",
        "latest/objects.inv",
        "en/latest/objects.inv",
        "doc/objects.inv",
        "docs/objects.inv",
    ]

    for path in expansions:
        test_url = trimmed + "/" + path
        if debug:
            print(f"[DEBUG] Trying doc expansions => {test_url}")
        try:
            r = session.head(test_url, allow_redirects=True, timeout=10)
            if r.status_code == 200:
                if debug:
                    print(f"[DEBUG] Found a valid objects.inv => {test_url}")
                return test_url
        except requests.RequestException as exc:
            if debug:
                print(f"[DEBUG] Request error => {exc}")

    return None


def parse_domain_from_url(url: str, debug: bool) -> str | None:
    """
    Extract domain from e.g. 'https://docs.pytest.org/en/stable/changelog.html' => 'docs.pytest.org'
    """
    m = re.match(r"https?://([^/]+)/", url.strip())
    if m:
        dom = m.group(1)
        if debug:
            print(f"[DEBUG] Extracted domain => {dom}")
        return dom
    return None
