# tests/test_intersphinx_known_packages.py

import pytest
import requests

from pypi_docs_url import get_intersphinx_url


@pytest.mark.online
@pytest.mark.parametrize(
    "package",
    [
        "polars",
        "pandas",
        "numpy",
        "matplotlib",
        "flask",
        "django",
        "requests",
        "sqlalchemy",
        "fastapi",
    ],
)
def test_intersphinx_for_known_packages(package):
    """
    For each package in the list, verify that `get_intersphinx_url(package)`
    returns a URL containing 'objects.inv' and resolves to 2xx over HTTP.
    If any fail, it likely means our code or the package's doc structure changed.
    """
    url = get_intersphinx_url(package, debug=True)
    assert url is not None, f"Expected to find objects.inv for {package}, got None"
    assert (
        "objects.inv" in url
    ), f"For {package}, returned URL doesn't look like objects.inv: {url}"

    resp = requests.head(url, allow_redirects=True, timeout=10)
    resp.raise_for_status()  # ensures we got a 2xx
    print()
