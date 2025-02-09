import re

import requests
import yaml


def get_intersphinx_url(package_name: str, debug: bool = False) -> str | None:
    """
    Attempt to discover a Python package's intersphinx `objects.inv` URL by:

      1) Checking PyPI metadata for:
         - A doc-labeled link (existing approach),
         - Any link with "stable" or "latest" in path (new approach).
         If expansions succeed (HEAD => 200), return.
      2) If that fails, parse the GitHub workflow `.github/workflows/docs-python.yml`
         fallback logic.

    Example:
        scikit-learn => 'https://scikit-learn.org/stable/objects.inv'
        pytest => 'https://docs.pytest.org/en/stable/objects.inv'
        polars => fallback GH approach (like before)
    """

    with requests.Session() as session:
        # Step A: Fetch PyPI JSON
        data = _fetch_pypi_json(session, package_name, debug)
        if not data:
            return None

        # Step B: doc-labeled link expansions
        doc_candidate = _find_doc_url_candidate(data, debug)
        if doc_candidate:
            inv_url = _try_intersphinx_expansions(session, doc_candidate, debug)
            if inv_url:
                return inv_url

        # Step C: stable/latest approach
        stable_candidate = _find_stable_latest_link(data, debug)
        if stable_candidate:
            inv_url = _try_intersphinx_expansions(session, stable_candidate, debug)
            if inv_url:
                return inv_url

        # Step D: If above expansions all fail, do fallback GH approach
        gh_repo_link = _find_github_repo_in_project_urls(data, debug)
        if not gh_repo_link:
            if debug:
                print(
                    "[DEBUG] No GitHub link found; can't do fallback GH workflow logic."
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

        # fetch docs-python.yml
        workflow_text = _fetch_docs_python_yml(session, org, repo, debug)
        if not workflow_text:
            return None

        # parse stable subfolder
        stable_tf = _parse_stable_subfolder(workflow_text, debug)
        if not stable_tf:
            return None

        # guess domain from doc_candidate or stable_candidate if we have it
        domain = None
        for candidate in (doc_candidate, stable_candidate):
            if candidate:
                d = _parse_domain_from_url(candidate, debug)
                if d:
                    domain = d
                    break
        if not domain:
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
      3) URLs containing 'stable' or 'latest'
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

    # d) Check for URLs containing 'stable' or 'latest'
    for link in purls.values():
        if "stable" in link or "latest" in link:
            if debug:
                print(f"[DEBUG] Found URL containing 'stable' or 'latest' => {link}")
            return link

    if debug:
        print("[DEBUG] No doc-like candidate found in project_urls or home_page.")
    return None


def _find_stable_latest_link(data: dict, debug: bool) -> str | None:
    """
    Scan project_urls + home_page for a link containing 'stable' or 'latest' in the path.
    If found, attempt to trim after 'stable' or 'latest', e.g.:
      "https://scikit-learn.org/stable/whats_new" => "https://scikit-learn.org/stable"
      "https://docs.pytest.org/en/stable/changelog.html" => "https://docs.pytest.org/en/stable"

    Return that trimmed base. If none found, return None.
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
        # search for "/stable" or "/latest" in the path
        match = re.search(r"(.*?)/(stable|latest)(?:/|$)", link)
        if match:
            # group(1) => everything before /stable, group(2) => stable
            # we want => ".../stable"
            base = match.group(1) + "/" + match.group(2)
            if debug:
                print(f"[DEBUG] Found stable/latest link => {link}")
                print(f"[DEBUG] Trimmed base => {base}")
            return base

    if debug:
        print(
            "[DEBUG] No link containing 'stable' or 'latest' found in project_urls/home_page."
        )
    return None


def _try_intersphinx_expansions(
    session: requests.Session, base_url: str, debug: bool
) -> str | None:
    """
    Attempt multiple expansions on `base_url`:
      - if ends with .html or .htm, remove it
      - ensure trailing slash
      Then HEAD check:
        objects.inv
        stable/objects.inv
        en/stable/objects.inv
        latest/objects.inv
        en/latest/objects.inv
    Return first 200 success, or None.
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


def _fetch_docs_python_yml(
    session: requests.Session, org: str, repo: str, debug: bool
) -> str | None:
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
                f"[DEBUG] Failed to fetch docs-python.yml from {url}: {r.status_code}"
            )
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
    Extract domain from e.g. 'https://docs.pytest.org/en/stable/changelog.html' => 'docs.pytest.org'
    """
    m = re.match(r"https?://([^/]+)/", url.strip())
    if m:
        dom = m.group(1)
        if debug:
            print(f"[DEBUG] Extracted domain => {dom}")
        return dom
    return None
