"""vsdxkit - create, edit and analyse Microsoft Visio .vsdx files.

Import each name from the module that defines it, for example
``from vsdxkit.document import Document``. This module holds only the XML
namespace constants the other modules share, and the version.
"""

namespace = "{http://schemas.microsoft.com/office/visio/2012/main}"
"""Visio's own XML namespace, in the ``{uri}`` form ElementTree tags use: ``shape.xml.find(f"{namespace}Cell")``."""
ext_prop_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
"""The namespace of ``docProps/app.xml``, the package's extended properties, whose ``HeadingPairs`` and ``TitlesOfParts`` list the pages and masters by name."""
vt_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes}"
"""The namespace of the typed values inside ``app.xml``'s properties: the ``vector``, ``variant``, ``lpstr`` and ``i4`` elements."""
r_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
"""The namespace of the ``r:id`` attribute, by which an element in a part names one of that part's relationships: a page's ``Rel`` in ``pages.xml``, or an image's ``Rel`` on its page."""
document_rels_namespace = "{http://schemas.openxmlformats.org/package/2006/relationships}"
"""The namespace of every ``.rels`` part: its ``Relationships`` root and each ``Relationship`` in it."""
cont_types_namespace = "{http://schemas.openxmlformats.org/package/2006/content-types}"
"""The namespace of ``[Content_Types].xml``: its ``Default`` and ``Override`` elements, which give each part its content type."""

# Ref: https://docs.microsoft.com/en-us/office/client-developer/visio/visio-file-format-reference


# The one place the version lives. pyproject.toml reads it through
# tool.setuptools.dynamic, so a static [project].version would go stale in
# uv.lock on every bump and fail the `uv sync --locked` gate. release-please
# rewrites the line below; the annotation is how it finds it.
__version__ = "0.8.0"  # x-release-please-version
"""This release's version string; the distribution's metadata takes its version from here."""
