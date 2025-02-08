#!/usr/bin/env python3

import json
import re
import sys
import yaml  # pip install pyyaml
import httpx

"""
Fully instrumented script to trace the entire logic from:

  1. PyPI JSON => doc link / GH repo link
  2. GH docs-python.yml => stable subfolder
  3. Final objects.inv guess

along with printing all intermediate data so you can confirm
the result isn't hard-coded.

Usage:
  python pypi_to_objects_inv_debug.py [package_name]

If no package_name is given, defaults to "polars".
"""


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"** {title}")
    print("=" * 70 + "\n")


def fetch_pypi_json(client: httpx.Client, package: str) -> dict:
    url = f"https://pypi.org/pypi/{package}/json"
    print(f"Fetching PyPI JSON at: {url}")
    resp = client.get(url)
    resp.raise_for_status()
    data = resp.json()

    # Print the entire JSON for transparency
    print_header(f"PyPI JSON for {package}")
    print(json.dumps(data, indent=2))

    return data


def find_doc_link_in_project_urls(data: dict) -> str | None:
    """
    Look for a link containing "doc" in data["info"]["project_urls"].
    Return it if found; else None.
    """
    info = data.get("info", {})
    purls = info.get("project_urls", {})
    for label, link in purls.items():
        if "doc" in label.lower():
            return link
    # Optionally also check "Documentation" key or home_page, etc.
    return None


def find_github_repo_in_project_urls(data: dict) -> str | None:
    """
    Return the first link that references github.com from project_urls or home_page.
    """
    info = data.get("info", {})
    purls = info.get("project_urls", {})

    # Gather them all, including home_page
    links = list(purls.values())
    if info.get("home_page"):
        links.append(info["home_page"])

    for link in links:
        if isinstance(link, str) and "github.com" in link.lower():
            return link
    return None


def parse_github_repo_url(link: str) -> tuple[str, str] | None:
    """
    Given something like https://github.com/pola-rs/polars,
    parse out (org, repo). Return None if not matched.
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
    Retrieve the docs-python.yml from:
      https://raw.githubusercontent.com/<org>/<repo>/<branch>/.github/workflows/docs-python.yml
    Return the raw text if found (status 200), else None.
    """
    url = f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/.github/workflows/docs-python.yml"
    print(f"Trying to fetch workflow at: {url}")
    r = client.get(url)
    if r.status_code == 200:
        # Print the entire file so we can see there's no cheating
        print_header(f".github/workflows/docs-python.yml from {org}/{repo}")
        print(r.text)
        return r.text

    print(f"Status {r.status_code}; no docs-python.yml at {url}.")
    return None


def parse_stable_subfolder(yml_text: str) -> str | None:
    """
    Parse docs-python.yml as YAML, look for step(s) with
      with:
        target-folder: ...
    containing 'stable'.
    Return that 'target-folder' string if found, else None.
    """
    try:
        config = yaml.safe_load(yml_text)
    except yaml.YAMLError as exc:
        print(f"YAML parse error: {exc}")
        return None

    # The job name is likely "build-python-docs"
    jobs = config.get("jobs", {})
    build_job = jobs.get("build-python-docs", {})
    steps = build_job.get("steps", [])

    for step in steps:
        w = step.get("with")
        if isinstance(w, dict):
            tf = w.get("target-folder")
            if tf and "stable" in tf:
                return tf
    return None


def main():
    # If user passes a package name, use it; else default polars
    pkg = sys.argv[1] if len(sys.argv) > 1 else "polars"
    print_header(f"Attempting docs/objects.inv discovery for package '{pkg}'")

    with httpx.Client() as client:
        # 1. PyPI JSON
        try:
            data = fetch_pypi_json(client, pkg)
        except httpx.HTTPError as exc:
            print(f"Error fetching PyPI JSON: {exc}")
            return

        # 2. See if there's a doc link in project_urls
        doc_link = find_doc_link_in_project_urls(data)
        print_header("Doc link found in PyPI project_urls")
        if doc_link:
            print(f"Doc link from PyPI => {doc_link}")
        else:
            print("No direct 'doc'-labeled link in project_urls.")

        # 3. Attempt to parse a GitHub repo from pypi
        repo_link = find_github_repo_in_project_urls(data)
        print_header("Potential GitHub repo link from PyPI")
        if repo_link:
            print(f"GitHub link => {repo_link}")
        else:
            print("No GitHub link found. Stopping here.")
            return

        orgrepo = parse_github_repo_url(repo_link)
        if not orgrepo:
            print("Could not parse org/repo from that link.")
            return

        org, repo = orgrepo
        print(f"Parsed org={org}, repo={repo}")

        # 4. Fetch docs-python.yml
        yml_text = fetch_docs_python_yml(client, org, repo, branch="main")
        if not yml_text:
            print("No docs-python.yml found or we can't parse it.")
            return

        # 5. From docs-python.yml, parse stable subfolder
        stable_tf = parse_stable_subfolder(yml_text)
        print_header("Parsing target-folder: stable from docs-python.yml")
        if stable_tf:
            print(f"Found stable subfolder => {stable_tf}")
        else:
            print(
                "No stable subfolder found. Possibly dev only, or a different naming.",
            )
            return

        # 6. Construct a guess for the domain + stable folder + objects.inv
        # The snippet for polars uses 'docs.pola.rs' as final domain, but let's do a naive guess:
        # We see in the doc link: e.g. "https://docs.pola.rs/api/python/stable/reference/index.html"
        # We'll try to unify that domain + stable subfolder => "https://docs.pola.rs/api/python/stable/objects.inv"
        # But let's parse the domain from doc_link if we have it, else fallback to "docs.pola.rs"
        domain = "docs.pola.rs"
        if doc_link:
            # Extract the domain from e.g. https://docs.pola.rs/api/python/stable/reference/index.html
            # This is naive:
            m = re.match(r"https?://([^/]+)/", doc_link)
            if m:
                domain = m.group(1)
        # Now build final guess:
        # remove leading/trailing slashes from stable_tf
        stable_tf = stable_tf.strip("/")
        guess = f"https://{domain}/{stable_tf}/objects.inv"

        print_header("Final guess for objects.inv location")
        print(f"Guess => {guess}")

        # 7. HEAD request
        print("\nPerforming HEAD request to see if it yields a 200...\n")
        try:
            r = client.head(guess, follow_redirects=True, timeout=10)
            print(f"Response => {r.status_code}, final URL => {r.url}")
            if r.status_code == 200:
                print("Looks like we found a valid objects.inv!")
            else:
                print("Hmm, not 200. Possibly not found or we need a different path.")
        except httpx.HTTPError as exc:
            print(f"HEAD request failed: {exc}")


if __name__ == "__main__":
    main()
