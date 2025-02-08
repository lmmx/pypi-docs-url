import re
import json
import yaml
import requests

def get_intersphinx_url(package_name: str) -> str | None:
    """
    Attempt to discover a Python package's intersphinx `objects.inv` URL by:
      1) Checking PyPI metadata for doc link / GitHub repo
      2) If GitHub repo found, fetch `.github/workflows/docs-python.yml`
      3) Parse the final stable subfolder e.g. `api/python/stable`
      4) Guess domain from the doc link, or fallback to a known domain if needed
      5) HEAD request `<domain>/<subfolder>/objects.inv`

    Returns:
        The final `objects.inv` URL (str) if it exists (HTTP 200),
        or None if not found or not parseable.

    Dependencies:
        - PyYAML for parsing YAML
        - requests

    Example:
        >>> url = get_intersphinx_url("polars")
        >>> print(url)
        https://docs.pola.rs/api/python/stable/objects.inv
    """
    with requests.Session() as session:
        # 1) PyPI JSON
        data = _fetch_pypi_json(session, package_name)
        if not data:
            return None

        # 1a) doc link from project_urls
        doc_link = _find_doc_link_in_project_urls(data)
        # 1b) GitHub repo link from project_urls or home_page
        gh_repo_link = _find_github_repo_in_project_urls(data)

        if not gh_repo_link:
            # No GitHub link found => can't parse docs-python.yml => no guess
            return None

        orgrepo = _parse_github_repo_url(gh_repo_link)
        if not orgrepo:
            return None

        org, repo = orgrepo

        # 2) fetch docs-python.yml
        workflow_text = _fetch_docs_python_yml(session, org, repo, branch="main")
        if not workflow_text:
            return None

        # 3) parse stable subfolder
        stable_tf = _parse_stable_subfolder(workflow_text)
        if not stable_tf:
            return None

        # 4) guess domain from doc_link if we have it, else fallback
        domain = "docs.pola.rs"
        if doc_link:
            m = re.match(r"https?://([^/]+)/", doc_link)
            if m:
                domain = m.group(1)

        # 5) build final objects.inv path
        stable_tf = stable_tf.strip("/")
        guess = f"https://{domain}/{stable_tf}/objects.inv"

        # 6) HEAD request to see if 200
        resp = session.head(guess, allow_redirects=True, timeout=10)
        if resp.status_code == 200:
            return guess
        return None

def _fetch_pypi_json(session: requests.Session, pkg: str) -> dict | None:
    """Retrieve minimal PyPI JSON for `pkg`. Return dict or None."""
    url = f"https://pypi.org/pypi/{pkg}/json"
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None

def _find_doc_link_in_project_urls(data: dict) -> str | None:
    """Look for a link containing 'doc' in data["info"]["project_urls"]."""
    info = data.get("info", {})
    purls = info.get("project_urls", {})
    for label, link in purls.items():
        if "doc" in label.lower():
            return link
    return None

def _find_github_repo_in_project_urls(data: dict) -> str | None:
    """
    Return the first link referencing github.com from project_urls or home_page.
    """
    info = data.get("info", {})
    purls = info.get("project_urls", {})
    candidates = list(purls.values())

    home_page = info.get("home_page")
    if home_page:
        candidates.append(home_page)

    for link in candidates:
        if isinstance(link, str) and "github.com" in link.lower():
            return link
    return None

def _parse_github_repo_url(link: str) -> tuple[str, str] | None:
    """Parse https://github.com/ORG/REPO => (ORG, REPO)."""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)", link)
    if not m:
        return None
    org = m.group(1)
    repo = m.group(2).removesuffix(".git")
    return (org, repo)

def _fetch_docs_python_yml(
    session: requests.Session, org: str, repo: str, branch="main"
) -> str | None:
    """
    Retrieve .github/workflows/docs-python.yml from GitHub if it exists.
    Return the raw text or None.
    """
    url = f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/.github/workflows/docs-python.yml"
    try:
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            return r.text
        return None
    except requests.RequestException:
        return None

def _parse_stable_subfolder(workflow_text: str) -> str | None:
    """
    In docs-python.yml, look for step -> with -> target-folder that
    includes 'stable'. Return that subfolder if found, else None.
    """
    try:
        data = yaml.safe_load(workflow_text)
    except yaml.YAMLError:
        return None

    jobs = data.get("jobs", {})
    build_job = jobs.get("build-python-docs", {})
    steps = build_job.get("steps", [])
    for step in steps:
        w = step.get("with")
        if isinstance(w, dict):
            tf = w.get("target-folder")
            if tf and "stable" in tf:
                return tf
    return None
