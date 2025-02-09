import re
import requests
import yaml

def get_intersphinx_url(package_name: str, debug: bool = False) -> str | None:
    """
    Attempt to discover a Python package's intersphinx `objects.inv` URL by:

      1) Checking PyPI metadata for a doc-like link (from 'project_urls' or 'home_page').
         a) Try multiple expansions:
            - `objects.inv`
            - `stable/objects.inv`
            - `latest/objects.inv`
            - `en/stable/objects.inv`
            - `en/latest/objects.inv`
         b) If any HEAD => 200, return that immediately.

      2) If that fails, parse the GitHub repo from PyPI, fetch `.github/workflows/docs-python.yml`,
         parse the final stable subfolder e.g. `api/python/stable`, and guess domain from doc link.

      3) Return whichever is discovered first or None if none succeed.

    Example:
        >>> url = get_intersphinx_url("numpy", debug=True)
        # 1) doc link is https://numpy.org/doc/
        # Try expansions => stable/objects.inv => 200 => done

    Returns:
        The final `objects.inv` URL if discovered, else None.
    """

    with requests.Session() as session:
        data = _fetch_pypi_json(session, package_name, debug)
        if not data:
            return None

        # 1) Attempt doc-based expansions first
        doc_candidate = _find_doc_url_candidate(data, debug)
        if doc_candidate:
            # Try expansions
            inv_url = _try_intersphinx_expansions(session, doc_candidate, debug)
            if inv_url:
                return inv_url

        # 2) Fallback to GH approach if doc expansions fail
        gh_repo_link = _find_github_repo_in_project_urls(data, debug)
        if not gh_repo_link:
            if debug:
                print("[DEBUG] No GitHub link found; can't do fallback GH workflow logic.")
            return None

        orgrepo = _parse_github_repo_url(gh_repo_link)
        if not orgrepo:
            if debug:
                print("[DEBUG] Could not parse org/repo from GitHub link.")
            return None
        org, repo = orgrepo

        if debug:
            print(f"[DEBUG] Attempting fallback GH workflow approach with {org}/{repo}")

        # fetch docs-python.yml
        workflow_text = _fetch_docs_python_yml(session, org, repo, debug=debug)
        if not workflow_text:
            return None

        # parse stable subfolder
        stable_tf = _parse_stable_subfolder(workflow_text, debug)
        if not stable_tf:
            return None

        # guess domain from doc_candidate if we have it
        domain = None
        if doc_candidate:
            # parse the domain from doc_candidate
            domain = _parse_domain_from_url(doc_candidate, debug)

        if not domain:
            # fallback domain for GH approach
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


### Helper Functions ###

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

def _find_doc_url_candidate(data: dict, debug: bool) -> str | None:
    """
    From PyPI metadata, attempt to find a doc-like link.
    Priority:
      1) 'project_urls' containing 'doc' or 'Documentation'
      2) 'home_page' if it looks readthedocs or something doc-ish
    Return the best guess or None.
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

    # c) if home_page has readthedocs or docs, we might treat it as doc link
    homepage = info.get("home_page")
    if homepage and any(hint in homepage.lower() for hint in ["readthedocs", "docs"]):
        if debug:
            print(f"[DEBUG] Using home_page as doc link => {homepage}")
        return homepage

    if debug:
        print("[DEBUG] No doc-like candidate found in project_urls or home_page.")
    return None

def _try_intersphinx_expansions(session: requests.Session, base_url: str, debug: bool) -> str | None:
    """
    Attempt multiple expansions on `base_url`:
      - if ends with .html or .htm, remove it
      - ensure trailing slash
      Then HEAD check for each:
        objects.inv
        stable/objects.inv
        en/stable/objects.inv
        latest/objects.inv
        en/latest/objects.inv
    Return the first 200 success, or None.

    e.g. base_url = 'https://numpy.org/doc/'
         => https://numpy.org/doc/stable/objects.inv
    e.g. base_url = 'https://docs.pytest.org/en/stable/changelog.html'
         => trimmed to https://docs.pytest.org/en/stable/
         => stable/objects.inv => 200
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
    ]

    # We'll do HEAD requests in a loop
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

def _find_github_repo_in_project_urls(data: dict, debug: bool) -> str | None:
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

def _parse_github_repo_url(link: str) -> tuple[str, str] | None:
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)", link)
    if not m:
        return None
    org = m.group(1)
    repo = m.group(2).removesuffix(".git")
    return (org, repo)

def _fetch_docs_python_yml(session: requests.Session, org: str, repo: str, debug: bool) -> str | None:
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
            print(f"[DEBUG] Failed to fetch docs-python.yml from {url}: {r.status_code}")
    except requests.RequestException as exc:
        if debug:
            print(f"[DEBUG] Error fetching docs-python.yml => {exc}")
    return None

def _parse_stable_subfolder(workflow_text: str, debug: bool) -> str | None:
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

def _parse_domain_from_url(url: str, debug: bool) -> str | None:
    """
    Extract domain from e.g. 'https://docs.pytest.org/en/stable/' => 'docs.pytest.org'
    """
    m = re.match(r"https?://([^/]+)/", url.strip())
    if m:
        dom = m.group(1)
        if debug:
            print(f"[DEBUG] Extracted domain => {dom}")
        return dom
    return None
