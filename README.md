# pypi-docs-url

Proof of concept for a tool that will do its best to find `objects.inv` by reading mkdocs config.

The path to the Intersphinx inventory is supposed to be trivial to find but in reality because of
the diversity of deployment methods, the info can be a few hops to find. We can do this and
hopefully make guesses fast enough that nobody has to notice!

For Polars, it uses mkdocs, but there is some URL redirection behind the scenes (Polars serves 3
sets of docs, one for Python, one for Rust, and one "global" one for the entire project). Other
projects are likely simpler, but we want to try to capture this in as much generality as we can.

Here is a demo (script `demo_5.py`), potentially to be incorporated into a proper package,
essentially using heuristics based on the typical approach to deploying open source package docs
with mkdocs and GitHub Actions/Pages.

**Note**: We could also find as many of these as we can and store them in a HuggingFace dataset
to have this be our first port of call! It is very important we can access these inventories for a
given package name though, as it potentially also gives us versioning on the namespace.

## Current status

This is just a demo for now, to run it:

```sh
pypi-docs-url
```

```
** Attempting to discover polars's objects.inv via PyPI → GH workflow logic **

[1] Fetching PyPI JSON at: https://pypi.org/pypi/polars/json

[1a] Relevant PyPI fields:
  project_urls: {
  "Changelog": "https://github.com/pola-rs/polars/releases",
  "Documentation": "https://docs.pola.rs/api/python/stable/reference/index.html",
  "Homepage": "https://www.pola.rs/",
  "Repository": "https://github.com/pola-rs/polars"
}

[1b] Found doc link in project_urls => https://docs.pola.rs/api/python/stable/reference/index.html

[1c] Found GitHub link => https://github.com/pola-rs/polars/releases

[1d] Parsed org=pola-rs, repo=polars

[2] Attempting to fetch workflow at: https://raw.githubusercontent.com/pola-rs/polars/main/.github/workflows/docs-python.yml

[2a] Key lines from docs-python.yml (containing 'deploy' or 'target-folder'):
        - name: Deploy Python docs for latest development version
          uses: JamesIves/github-pages-deploy-action@v4
            target-folder: api/python/dev
        - name: Deploy Python docs for latest release version - versioned
          uses: JamesIves/github-pages-deploy-action@v4
            target-folder: api/python/version/${{ steps.version.outputs.version }}
        - name: Deploy Python docs for latest release version - stable
          uses: JamesIves/github-pages-deploy-action@v4
            target-folder: api/python/stable

[2c] Stable subfolder => api/python/stable

[3] Final guess => https://docs.pola.rs/api/python/stable/objects.inv
Performing HEAD request...
Response status: 200, final URL => https://docs.pola.rs/api/python/stable/objects.inv
Looks like we found objects.inv!
```
