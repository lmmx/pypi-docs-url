# tests/test_polars_intersphinx.py

import requests
import pytest

from pypi_docs_url import get_intersphinx_url


@pytest.mark.online
def test_polars_intersphinx():
    """
    Test that we can discover Polars' objects.inv URL by calling
    our library function. We check that the returned URL includes
    'objects.inv' and that HEAD request => 200 status.
    """
    url = get_intersphinx_url("polars")
    assert url is not None, "Expected to find objects.inv for Polars, got None"
    assert (
        "objects.inv" in url
    ), f"Returned URL doesn't look like an objects.inv link: {url}"

    # Optionally confirm we can do a HEAD request and get 200
    resp = requests.head(url, allow_redirects=True, timeout=10)
    resp.raise_for_status()  # will raise if not 2xx
    # If we reach here, it means 2xx => success

    # We could do additional checks like verifying `resp.url` ends with 'objects.inv'
    # or that we get a content-type, etc. but this is enough for a basic test.
