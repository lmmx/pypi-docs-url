#!/usr/bin/env python3

import re
import yaml  # pip install pyyaml
import httpx

"""
End-to-end example:

- Query PyPI for the docs link of a package.
- If that doc link doesn't straightforwardly yield objects.inv,
  parse the GitHub repo's `.github/workflows/docs-python.yml` to see how docs are deployed.
- Construct final objects.inv URL, do a HEAD check, and print the debug chain.
"""

# 1) Basic PyPI fetch
def get_pypi_json(client: httpx.Client, package_name: str) -> dict:
    url = f"https://pypi.org/pypi/{package_name}/json"
    resp = client.get(url)
    resp.raise_for_status()
    return resp.json()

def parse_docs_url_from_pypi(data: dict) -> str | None:
    """Return a doc-related link from project_urls or None if not found."""
    info = data.get("info", {})
    project_urls = info.get("project_urls", {})
    # Look for a label containing 'doc'
    for label, link in project_urls.items():
        if "doc" in label.lower():
            return link
    # Fallback: we might also check 'Documentation' specifically, or 'home_page'.
    return None

def parse_github_repo_from_pypi(data: dict) -> tuple[str, str] | None:
    """Look in project_urls or home_page for a GitHub repo, return (org, repo) if found."""
    info = data.get("info", {})
    project_urls = info.get("project_urls", {})
    # Check each link for github
    possible_links = list(project_urls.values())
    if info.get("home_page"):
        possible_links.append(info["home_page"])

    for link in possible_links:
        if isinstance(link, str) and "github.com" in link.lower():
            # Extract org/repo
            # E.g. https://github.com/pola-rs/polars
            m = re.match(r"https://github\.com/([^/]+)/([^/]+)", link)
            if m:
                org = m.group(1)
                repo = m.group(2).removesuffix(".git")
                return (org, repo)
    return None

# 2) Fetch docs-python.yml
def fetch_docs_python_workflow(client: httpx.Client, org: str, repo: str, branch="main") -> str | None:
    """
    Attempt to retrieve .github/workflows/docs-python.yml from e.g.
    https://raw.githubusercontent.com/org/repo/main/.github/workflows/docs-python.yml
    Return the file contents as a string or None if not found.
    """
    url = f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/.github/workflows/docs-python.yml"
    r = client.get(url)
    if r.status_code == 200:
        return r.text
    return None

def parse_stable_deployment_subfolder(yml_text: str) -> str | None:
    """
    In docs-python.yml, we look for the lines specifying:
      folder: py-polars/docs/build/html
      target-folder: api/python/stable
    Then we return 'api/python/stable'.
    This is a naive approach, scanning for 'stable' block in the file.
    """
    try:
        config = yaml.safe_load(yml_text)
    except yaml.YAMLError:
        return None

    # The config is a typical GitHub workflow dict.
    # We want to find a job step with 'Deploy Python docs for latest release version - stable'
    # That is likely in config['jobs']['build-python-docs']['steps'] etc.
    jobs = config.get("jobs", {})
    build_job = jobs.get("build-python-docs", {})
    steps = build_job.get("steps", [])

    # Look for a step that references 'stable' in 'target-folder'
    for step in steps:
        if "with" in step and isinstance(step["with"], dict):
            tf = step["with"].get("target-folder")
            if tf and "stable" in tf:
                return tf  # e.g. "api/python/stable"

    return None

# 3) Putting it all together in main
def main():
    package_name = "polars"

    with httpx.Client() as client:
        # A) Get PyPI JSON
        try:
            pypi_data = get_pypi_json(client, package_name)
        except httpx.HTTPError as exc:
            print(f"Error fetching PyPI JSON: {exc}")
            return

        # B) Parse docs link from project_urls
        docs_url = parse_docs_url_from_pypi(pypi_data)
        print(f"PyPI docs_url => {docs_url}")

        # If we do not see a direct 'objects.inv' in docs_url,
        # or if the user wants to do the "causal chain" approach,
        # we proceed:
        # (In Polars's case, we do see a doc link, but let's keep going.)

        # C) Attempt to parse the GH repo from PyPI
        gh = parse_github_repo_from_pypi(pypi_data)
        if not gh:
            print("No GitHub link found in PyPI. Can't parse workflow. Stopping.")
            return
        org, repo = gh
        print(f"Identified GitHub repository => {org}/{repo}")

        # D) Fetch docs-python.yml
        workflow_text = fetch_docs_python_workflow(client, org, repo, branch="main")
        if not workflow_text:
            print("Couldn't fetch .github/workflows/docs-python.yml from main branch.")
            return
        # E) Parse the stable subfolder, e.g. "api/python/stable"
        stable_subfolder = parse_stable_deployment_subfolder(workflow_text)
        if not stable_subfolder:
            print("No stable subfolder found in the docs workflow steps. Possibly dev only.")
            return

        # F) Construct the final objects.inv path
        # We know from the docs: site is served at docs.pola.rs => / + stable_subfolder
        # Typically from that workflow we know the final domain is docs.pola.rs
        # So let's guess https://docs.pola.rs/<stable_subfolder>/objects.inv
        final_url = f"https://docs.pola.rs/{stable_subfolder.strip('/')}/objects.inv"

        print(f"Guessing objects.inv => {final_url}")

        # G) HEAD request to confirm existence
        try:
            r = client.head(final_url, follow_redirects=True, timeout=5)
            print(f"HEAD {final_url} => status {r.status_code}, final URL: {r.url}")
            if r.status_code == 200:
                print("Success! We found a 200 for objects.inv.")
            else:
                print("Not a 200 - might not exist, or might be hidden somewhere else.")
        except httpx.HTTPError as exc:
            print(f"Failed to HEAD {final_url}: {exc}")


if __name__ == "__main__":
    main()
