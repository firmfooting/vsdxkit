# Configuration for the Sphinx documentation builder.

import os
import sys

sys.path.insert(0, os.path.abspath(".."))

import vsdxkit

project = "vsdxkit"
copyright = "2020–2026, Dave Howard and Firm Footing"  # noqa: RUF001  # holders as in LICENSE
author = "Dave Howard and Firm Footing"
release = vsdxkit.__version__
version = vsdxkit.__version__

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

# Canonical URL, so search engines credit the published site rather than a
# mirror or a local build.
html_baseurl = "https://firmfooting.github.io/vsdxkit/"
