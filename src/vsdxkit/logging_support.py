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
from typing import TYPE_CHECKING, TextIO

_PACKAGE_ROOT = "vsdxkit"

if TYPE_CHECKING:
    _StreamHandler = logging.StreamHandler[TextIO]
else:
    _StreamHandler = logging.StreamHandler


class _DebugStreamHandler(_StreamHandler):
    """Package-owned handler used by the legacy ``debug=True`` bridge."""

    _vsdx_debug_handler = True


_root = logging.getLogger(_PACKAGE_ROOT)
if not _root.handlers:
    _root.addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    """Return a logger in the vsdx hierarchy (pass ``__name__``)."""
    return logging.getLogger(name)


def attach_debug_stream_handler() -> None:
    """Legacy ``debug=True`` bridge: attach a stderr handler at DEBUG level.

    Mirrors the old ``debug=True`` print-to-stdout behaviour on the standard
    logging machinery. Idempotent; applications wanting different behaviour
    should configure the ``vsdx`` logger themselves and leave ``debug=False``.
    """
    if any(isinstance(handler, _DebugStreamHandler) for handler in _root.handlers):
        return
    handler = _DebugStreamHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    _root.addHandler(handler)
    if _root.level == logging.NOTSET or _root.level > logging.DEBUG:
        _root.setLevel(logging.DEBUG)
