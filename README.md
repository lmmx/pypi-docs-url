# pypi-docs-url

**Proof of concept** for a tool that locates a project’s [Intersphinx inventory](https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html) (`objects.inv`) by combining **PyPI** metadata and (if necessary) **GitHub** actions/workflows analysis.

Most packages use a direct `docs/` URL, but many run extra steps—**mkdocs**, **Sphinx**, GitHub Pages, multi-step publishing—so the final `objects.inv` location can be non-trivial. **pypi-docs-url** tries to guess it automatically.

## Basic Overview

1. **Check PyPI** (via [PyPI JSON](https://pypi.org/pypi/<package>/json)) for a doc link (`project_urls` or `home_page`).
2. **If missing**, parse the GitHub repo from PyPI (if present).
3. **Fetch** the `.github/workflows/docs-python.yml` to see how docs are deployed (e.g. “`target-folder: api/python/stable`”).
4. **Build** a guessed final docs domain (e.g. `docs.pola.rs`) plus that subfolder + `/objects.inv`.
5. **Check** if that file returns HTTP 200, and if so, print the final URL.

## Installation

```bash
pip install pypi-docs-url
```

*(Or however you prefer to install from your local copy, e.g. `pip install .`.)*

## Usage

### CLI

The primary entry point is a CLI tool, **`pypi-docs-url`**, which accepts a single argument: the **package name** you want to inspect. It simply prints the discovered `objects.inv` URL if successful, or reports failure:

```bash
$ pypi-docs-url polars
https://docs.pola.rs/api/python/stable/objects.inv
```

If it can’t find the `objects.inv`, it prints:
```
No objects.inv discovered or parse failed.
```

**That’s it—**by default, it’s short and sweet.

#### CLI Help

```bash
$ pypi-docs-url --help
Usage: pypi-docs-url [OPTIONS] PACKAGE_NAME

  CLI entry point to get the 'objects.inv' URL for PACKAGE_NAME, if any.

Options:
  --help  Show this message and exit.
```

### Python API

If you want to **reuse** the logic in your own code (not just the CLI), simply import from the package:

```python
from pypi_docs_url import get_intersphinx_url

def example():
    inv_url = get_intersphinx_url("polars")
    if inv_url:
        print(f"Found objects.inv => {inv_url}")
    else:
        print("No objects.inv discovered.")
```

*(This means you can embed the logic in your library or script, rather than invoking the CLI.)*

## Walkthrough / Verbose Explanation

If you want to see the **internal** steps—like how we parse PyPI’s JSON, find `docs-python.yml`, guess the subfolder, etc.—**the package contains commented code** illustrating each step in detail. Look in [`examples/demo_verbose.py`](./examples/demo_verbose.py) for a fully “instrumented” version:

```python
# demo_verbose.py (example, not installed by default)
#
# This script shows a step-by-step chain, printing out partial PyPI JSON,
# partial GitHub workflow lines, how we locate "api/python/stable",
# and the final HEAD request on objects.inv.
#
# EXAMPLE USAGE:
#   python demo_verbose.py polars
#
# (Output lines are commented out to avoid spamming the console by default.)

import re
import requests
import yaml

def main(package_name: str):
    # 1) PyPI JSON fetch
    # print(f"Fetching PyPI JSON at: https://pypi.org/pypi/{package_name}/json")
    # ...
    # print("Relevant fields: { ... }")

    # 2) Doc link in project_urls
    # print(f"Found doc link => https://docs.pola.rs/api/python/stable/reference/index.html")

    # 3) GitHub link => parse org/repo => fetch docs-python.yml
    # print("Key lines from docs-python.yml containing 'deploy' or 'target-folder': ...")

    # 4) Identify 'api/python/stable' => build guess => HEAD request => final URL
    # print("HEAD => 200 => success!")

    pass

if __name__ == "__main__":
    import sys
    pkg = sys.argv[1] if len(sys.argv) > 1 else "polars"
    main(pkg)
```

You can uncomment lines in that **demo** to see each step’s output. This is purely an example—**the main installed `pypi-docs-url` script** does not do this verbose printing.

---

## Example

Below is how Polars’ doc resolution might look if you were to **uncomment** the verbose lines:

```text
** Attempting to discover polars's objects.inv via PyPI → GH workflow logic **

[1] Fetching PyPI JSON at: https://pypi.org/pypi/polars/json

[1a] Relevant PyPI fields:
  project_urls: {
    "Changelog": "...",
    "Documentation": "https://docs.pola.rs/api/python/stable/reference/index.html",
    "Repository": "https://github.com/pola-rs/polars"
  }

[1b] Found doc link => https://docs.pola.rs/api/python/stable/reference/index.html

[1c] GitHub => https://github.com/pola-rs/polars
[1d] org=pola-rs, repo=polars

[2] Attempting to fetch workflow at: https://raw.githubusercontent.com/pola-rs/polars/main/.github/workflows/docs-python.yml

[2a] Key lines (containing 'deploy' or 'target-folder'):
  ... "target-folder: api/python/dev"
  ... "target-folder: api/python/stable"

[2c] stable => api/python/stable

[3] Final guess => https://docs.pola.rs/api/python/stable/objects.inv
Performing HEAD => status 200 => success!
```

*(That’s the deeper logic under the hood, while the actual CLI usage is a single line printing out the final URL.)*

---

## Contributing

Feel free to open issues/PRs:

- **Expand** to handle multiple subdomains or dev vs stable docs.
- **Add** a fallback if the doc link is missing but the project uses Sphinx.
- **Improve** logic for *mkdocs* vs *Sphinx* detection.

## License

MIT.
