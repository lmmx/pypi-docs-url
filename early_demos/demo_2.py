#!/usr/bin/env python3

import json
import httpx


def print_full_json(data: dict):
    """
    Pretty-print the entire JSON response for debugging.
    """
    print("\n----- Full PyPI JSON Response -----")
    print(json.dumps(data, indent=2))
    print("----- End of PyPI JSON Response -----\n")


def get_pypi_docs_url(client: httpx.Client, package_name: str) -> str | None:
    """
    Use PyPI's JSON API to find the documentation URL for `package_name`.
    Return None if no doc link is found.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    print(f"Fetching PyPI JSON from: {url}")
    resp = client.get(url)
    resp.raise_for_status()
    data = resp.json()

    # Print the entire JSON for debugging:
    print_full_json(data)

    project_urls = data["info"].get("project_urls", {})
    if not project_urls:
        return None

    # Look for a key that includes "doc" in its label:
    for label, link in project_urls.items():
        if "doc" in label.lower():
            return link

    return None


def guess_intersphinx_url(client: httpx.Client, docs_url: str) -> str | None:
    """
    Heuristically guess the location of `objects.inv`.
    Append '/objects.inv' to docs_url (adding a slash if needed)
    and do a HEAD request, printing all intermediate steps.
    """
    if not docs_url.endswith("/"):
        docs_url += "/"
    guess = docs_url + "objects.inv"

    print(f"\nDebug: Attempting HEAD request to guess objects.inv:\n  {guess}")
    try:
        resp = client.head(guess, follow_redirects=True, timeout=5)

        if resp.history:
            print("  Redirect chain:")
            for i, r in enumerate(resp.history, start=1):
                print(f"    {i}. {r.status_code} {r.url}")
        print(f"  Final response: {resp.status_code} {resp.url}")

        if resp.status_code == 200:
            return guess

    except httpx.HTTPError as exc:
        print(f"  HEAD request failed with an exception:\n  {exc}")

    return None


def main():
    package_name = "polars"

    with httpx.Client() as client:
        doc_url = get_pypi_docs_url(client, package_name)
        if not doc_url:
            print(f"No documentation URL found for {package_name} in PyPI metadata.")
            return

        print(f"PyPI metadata docs URL => {doc_url}")

        inv_url = guess_intersphinx_url(client, doc_url)
        if inv_url:
            print(f"\nSuccess! Found intersphinx inventory at: {inv_url}")
        else:
            print("\nNo luck guessing an intersphinx objects.inv URL.")


if __name__ == "__main__":
    main()
