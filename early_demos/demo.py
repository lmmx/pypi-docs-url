#!/usr/bin/env python3
"""
Fetch a package's documentation URL from PyPI, then guess the intersphinx
inventory (objects.inv) URL by appending "objects.inv". If that 200s,
we assume it's the correct location.
"""

import httpx


def get_pypi_docs_url(client: httpx.Client, package_name: str) -> str | None:
    """
    Query PyPI's JSON API for `package_name` to find a docs link in info.project_urls.
    Return None if no doc link is found.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    resp = client.get(url)
    resp.raise_for_status()
    data = resp.json()

    project_urls = data["info"].get("project_urls", {})
    if not project_urls:
        return None

    # Check if there's a key containing "doc"
    for label, link in project_urls.items():
        if "doc" in label.lower():
            return link

    # Alternatively, you could specifically do:
    # return project_urls.get("Documentation")
    return None


def guess_intersphinx_url(client: httpx.Client, docs_url: str) -> str | None:
    """
    Heuristically guess the location of `objects.inv` for intersphinx.
    We do the simplest approach: if docs_url doesn't end with "/", add it,
    then append "objects.inv" and test whether it returns 200.
    """
    if not docs_url.endswith("/"):
        docs_url += "/"
    guess = docs_url + "objects.inv"

    try:
        resp = client.head(guess, follow_redirects=True, timeout=5)
        if resp.status_code == 200:
            return guess
    except httpx.HTTPError:
        pass

    return None


def main():
    package_name = "polars"

    with httpx.Client() as client:
        doc_url = get_pypi_docs_url(client, package_name)
        if not doc_url:
            print(f"No documentation URL found for {package_name}")
            return

        print(f"Documentation URL for {package_name}: {doc_url}")

        # Now guess the intersphinx inventory URL
        inv_url = guess_intersphinx_url(client, doc_url)
        if inv_url:
            print(f"Guessed intersphinx inventory: {inv_url}")
        else:
            print("Could not guess an intersphinx objects.inv URL.")


if __name__ == "__main__":
    main()
