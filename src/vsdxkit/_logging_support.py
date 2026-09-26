"""Central logging support for the vsdx package.

Standards (Python logging HOWTO, library authorship):
- one module logger per module via ``logging.getLogger(__name__)``; the
  hierarchy sits under the package root so applications configure ``vsdx``
  (or any submodule) in one place
- the package root logger carries only a ``NullHandler``: a library never
  configures handlers or ``basicConfig()``, and never emits to a bare stdout
- lazy %-style message formatting (args passed to the logger, interpolated
  only when the level is enabled)

Usage in a vsdx module:

    from .logging_support import get_logger
    logger = get_logger(__name__)
"""

import logging

_PACKAGE_ROOT = "vsdxkit"

_root = logging.getLogger(_PACKAGE_ROOT)
if not _root.handlers:
    _root.addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    """Return a logger in the vsdx hierarchy (pass ``__name__``)."""
    return logging.getLogger(name)
