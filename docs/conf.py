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

# A single-backtick span is otherwise the `title reference` role, rendered as
# italic text with no link even when it names a real object. As `py:obj` it
# links where the name resolves, and falls back to ordinary code styling
# everywhere else.
default_role = "py:obj"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
]

# The API reference is generated from the docstrings (#424): autosummary walks
# the public modules of vsdxkit and writes one page per module under api/. A
# module or name with a leading underscore is private and is left out; nothing
# is listed by hand. `inherited-members` (set in the module template) shows
# `GeometryRow.inherited` and `make_local`, which the row takes from
# `vsdxkit._inheritance.InheritedRow`, on the class a reader looks them up on.
autosummary_generate = True


def skip_builtin_members(app, what, name, obj, skip, options):
    """Leave out members that `inherited-members` takes from a builtin base.

    An exception deriving from OSError would otherwise list `errno` and
    `with_traceback`, which the reference never carried.
    """
    if name == "msg":  # PartParseError documents its own `msg`, which shadows SyntaxError's
        return None
    owner = getattr(obj, "__objclass__", None)
    return True if getattr(owner, "__module__", None) == "builtins" else None


def setup(app):
    """Register the member filter."""
    app.connect("autodoc-skip-member", skip_builtin_members)


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

# The firmfooting brand. The stylesheet, mark and favicon are copied from
# firmfooting/branding, whose generate.py owns the palette; copy them again
# from there rather than editing them here.
html_static_path = ["_static"]
html_css_files = ["sphinx-rtd.css"]
html_logo = "_static/mark_white.svg"
html_favicon = "_static/favicon.ico"

# The theme's "Edit on GitHub" link, pointing at the source of each page on main.
html_context = {
    "display_github": True,
    "github_user": "firmfooting",
    "github_repo": "vsdxkit",
    "github_version": "main",
    "conf_py_path": "/docs/",
}

html_theme_options = {
    # mark links that leave the site, such as the GitHub and PyPI links
    "style_external_links": True,
    # show every section heading of a guide in the sidebar
    "navigation_depth": 3,
    "collapse_navigation": False,
    "prev_next_buttons_location": "both",
}
