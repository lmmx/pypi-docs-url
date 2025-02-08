import re

import requests
import yaml


def get_intersphinx_url(package_name: str, debug: bool = False) -> str | None:
    """
    Attempt to discover a Python package's intersphinx `objects.inv` URL by:
      1) Checking PyPI metadata for doc link.
         -> If doc link is found, try forming `<doc_link>/objects.inv`. If that 200s, done.
      2) If that fails, parse GitHub repo from PyPI and fetch `.github/workflows/docs-python.yml`
      3) Parse 'api/python/stable' or similar, build final URL, HEAD check
      4) Return the first success or None if we can't find a valid objects.inv anywhere.

    Returns:
        The final `objects.inv` URL (str) if it exists (HTTP 200),
        or None if not found or not parseable.

    Use `debug=True` to print step-by-step logic.
    """

    with requests.Session() as session:
        # 1) PyPI JSON
        data = _fetch_pypi_json(session, package_name, debug)
        if not data:
            return None

        # 1a) doc link from project_urls
        doc_link = _find_doc_link_in_project_urls(data, debug)
        # If doc_link is found, attempt an immediate objects.inv check
        if doc_link:
            inv_url = _try_objects_inv_in_doc_url(session, doc_link, debug)
            if inv_url:
                return inv_url

        # 1b) If that fails or doc_link not found, see if there's a GitHub repo:
        gh_repo_link = _find_github_repo_in_project_urls(data, debug)
        if not gh_repo_link:
            if debug:
                print(
                    "[DEBUG] No GitHub repo link found; can't do fallback GH workflow logic."
                )
            return None

        orgrepo = _parse_github_repo_url(gh_repo_link)
        if not orgrepo:
            if debug:
                print("[DEBUG] Could not parse org/repo from GitHub link.")
            return None
        org, repo = orgrepo

        if debug:
            print(f"[DEBUG] Attempting fallback GH workflow approach with {org}/{repo}")

        # 2) fetch docs-python.yml
        workflow_text = _fetch_docs_python_yml(
            session, org, repo, branch="main", debug=debug
        )
        if not workflow_text:
            return None

        # 3) parse stable subfolder
        stable_tf = _parse_stable_subfolder(workflow_text, debug)
        if not stable_tf:
            return None

        # 4) guess domain from doc_link if we have it, else fallback
        domain = None
        if doc_link:
            m = re.match(r"https?://([^/]+)/", doc_link)
            if m:
                domain = m.group(1)

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


### Helper Functions ###


def _try_objects_inv_in_doc_url(
    session: requests.Session, doc_link: str, debug: bool
) -> str | None:
    """
    Attempt to guess a direct objects.inv from the doc_link. For example:
      - If doc_link ends with 'index.html', we remove 'index.html' and add 'objects.inv'
      - Else if doc_link does not end with '/', we add '/'
      - Then we do a HEAD check. If 200, return that URL.

    Return None if not found or fails.
    """
    # Some typical transformations:
    # doc_link = "https://pandas.pydata.org/docs/index.html" -> "https://pandas.pydata.org/docs/objects.inv"
    # doc_link = "https://pandas.pydata.org/docs" -> "https://pandas.pydata.org/docs/objects.inv"
    # doc_link = "https://pandas.pydata.org/docs/" -> "https://pandas.pydata.org/docs/objects.inv"
    original_doc_link = doc_link
    doc_link = doc_link.strip()

    # if it ends with something like 'index.html', remove that
    if doc_link.endswith("index.html"):
        doc_link = doc_link[: -len("index.html")]

    # if it doesn't end with '/', add one
    if not doc_link.endswith("/"):
        doc_link += "/"

    inv_candidate = doc_link + "objects.inv"

    if debug:
        print(f"[DEBUG] Checking doc_link => {original_doc_link}")
        print(f"[DEBUG] Trying objects.inv => {inv_candidate}")

    try:
        r = session.head(inv_candidate, allow_redirects=True, timeout=10)
        if r.status_code == 200:
            if debug:
                print("[DEBUG] Found a valid objects.inv at doc_link-based guess!")
            return inv_candidate
        if debug:
            print(f"[DEBUG] doc_link-based guess => {r.status_code}")
    except requests.RequestException as exc:
        if debug:
            print(f"[DEBUG] doc_link-based guess => request error: {exc}")

    return None


def _fetch_pypi_json(session: requests.Session, pkg: str, debug: bool) -> dict | None:
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


def _find_doc_link_in_project_urls(data: dict, debug: bool) -> str | None:
    info = data.get("info", {})
    purls = info.get("project_urls", {})
    for label, link in purls.items():
        if "doc" in label.lower():
            if debug:
                print(f"[DEBUG] Found doc link in project_urls: {link}")
            return link
    # No doc-like label? Possibly "Documentation" or something else
    # Attempt a fallback for "Documentation" exactly:
    if "Documentation" in purls:
        link = purls["Documentation"]
        if debug:
            print(f"[DEBUG] Found doc link 'Documentation': {link}")
        return link

    if debug:
        print("[DEBUG] No doc link found in project_urls.")
    return None


def _find_github_repo_in_project_urls(data: dict, debug: bool) -> str | None:
    info = data.get("info", {})
    purls = info.get("project_urls", {})
    candidates = list(purls.values())
    if info.get("home_page"):
        candidates.append(info["home_page"])

    for link in candidates:
        if isinstance(link, str) and "github.com" in link.lower():
            if debug:
                print(f"[DEBUG] Found GitHub link: {link}")
            return link
    if debug:
        print("[DEBUG] No GitHub link found.")
    return None


def _parse_github_repo_url(link: str) -> tuple[str, str] | None:
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)", link)
    if not m:
        return None
    org = m.group(1)
    repo = m.group(2).removesuffix(".git")
    return (org, repo)


def _fetch_docs_python_yml(
    session: requests.Session, org: str, repo: str, branch="main", debug: bool = False
) -> str | None:
    url = f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/.github/workflows/docs-python.yml"
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
                f"[DEBUG] Failed to fetch docs-python.yml from {url}: {r.status_code}"
            )
        return None
    except requests.RequestException as e:
        if debug:
            print(f"[DEBUG] Error fetching docs-python.yml: {e}")
    return None


def _parse_stable_subfolder(workflow_text: str, debug: bool) -> str | None:
    try:
        config = yaml.safe_load(workflow_text)
    except yaml.YAMLError as exc:
        if debug:
            print(f"[DEBUG] YAML parse error: {exc}")
        return None

    jobs = config.get("jobs", {})
    build_job = jobs.get("build-python-docs", {})
    steps = build_job.get("steps", [])
    for step in steps:
        if isinstance(step.get("with"), dict):
            tf = step["with"].get("target-folder")
            if tf and "stable" in tf:
                if debug:
                    print(f"[DEBUG] Found stable target-folder: {tf}")
                return tf
    if debug:
        print("[DEBUG] No stable target-folder found.")
    return None
