"""vsdxkit - create, edit and analyse Microsoft Visio .vsdx files.

Import each name from the module that defines it, for example
``from vsdxkit.document import Document``. This module holds only the XML
namespace constants the other modules share, and the version.
"""

namespace = "{http://schemas.microsoft.com/office/visio/2012/main}"  # visio file name space
ext_prop_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
vt_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes}"
r_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
document_rels_namespace = "{http://schemas.openxmlformats.org/package/2006/relationships}"
cont_types_namespace = "{http://schemas.openxmlformats.org/package/2006/content-types}"

# Ref: https://docs.microsoft.com/en-us/office/client-developer/visio/visio-file-format-reference


# The one place the version lives. pyproject.toml reads it through
# tool.setuptools.dynamic, so a static [project].version would go stale in
# uv.lock on every bump and fail the `uv sync --locked` gate. release-please
# rewrites the line below; the annotation is how it finds it.
__version__ = "0.8.0"  # x-release-please-version
