# Configuration for the Sphinx documentation builder.

import os
import sys

sys.path.insert(0, os.path.abspath(".."))

import vsdx

project = "vsdxkit"
copyright = "2021–2026, Dave Howard and Shaun Eccles"  # noqa: RUF001  # update when preparing each release
author = "Dave Howard and Shaun Eccles"
release = vsdx.__version__
version = vsdx.__version__

extensions = [
    "sphinx.ext.autodoc",
]

templates_path = ["_templates"]
# docs/maintainers/ holds Markdown notes for this project's maintainers. They
# live here to sit beside the docs they concern, not to be published: there is
# no Markdown parser configured, and they are not in any toctree. Excluding
# them says so, rather than relying on Sphinx ignoring an unreadable suffix.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "maintainers"]

html_theme = "sphinx_rtd_theme"
html_title = f"vsdxkit {release}"
