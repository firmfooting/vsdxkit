"""Every public signature's annotations resolve at runtime, apart from a shrinking list.

The 1.0 design (amended 2026-09-23) turns each upward dependency into a
`Protocol` declared by the lower module, so `typing.get_type_hints` can resolve
every public signature: introspection, documentation and runtime validators
all go through it. The entries in `UNRESOLVED` still name an owner the lower
module cannot import without a cycle. Each comment names the phase that
retires the owner reference.

The check fails both ways. A new unresolved annotation fails it, and so does a
listed one that has started resolving, so the list only shrinks.
"""

import importlib
import inspect
import pkgutil
import typing
from collections.abc import Callable, Iterator

import vsdxkit

UNRESOLVED = {
    # Phase 4B and 5: `Connect` becomes the data-only `ConnectionRecord` and the
    # public `Connector(Shape)`, so the record stops reaching up to a Page.
    "vsdxkit.connectors.Connect.__init__",
    "vsdxkit.connectors.Connect.connector_shape",
    "vsdxkit.connectors.Connect.shape",
    # Phase 5: `Container` becomes `SwimlaneDiagram`, reached as `page.swimlanes`.
    "vsdxkit.containers.Container.__init__",
    "vsdxkit.containers.Container.find",
    # Phase 3: a page holds a document token rather than its `Document`.
    "vsdxkit.pages.Page.__init__",
    # Phase 2 moves master lookup to `MasterCatalog`; Phase 3 replaces the
    # page back-reference with a document token.
    "vsdxkit.shapes.Shape.__init__",
    "vsdxkit.shapes.Shape.copy",
    "vsdxkit.shapes.Shape.master_page",
}


def _public_signatures() -> Iterator[tuple[str, Callable[..., object]]]:
    """Every public function, and every public method, property and `__init__` of a public class."""
    for info in pkgutil.walk_packages(vsdxkit.__path__, f"{vsdxkit.__name__}."):
        module = importlib.import_module(info.name)
        for name, value in vars(module).items():
            if name.startswith("_") or getattr(value, "__module__", None) != module.__name__:
                continue
            if inspect.isfunction(value):
                yield f"{module.__name__}.{name}", value
            if not inspect.isclass(value):
                continue
            for attribute, member in vars(value).items():
                if attribute.startswith("_") and attribute != "__init__":
                    continue
                if isinstance(member, property):
                    member = member.fget
                if isinstance(member, (staticmethod, classmethod)):
                    member = member.__func__
                if inspect.isfunction(member):
                    yield f"{module.__name__}.{name}.{attribute}", member


def test_public_annotations_resolve_at_runtime():
    unresolved = set()
    for qualified_name, function in _public_signatures():
        try:
            typing.get_type_hints(function)
        except (NameError, TypeError, AttributeError):
            unresolved.add(qualified_name)
    assert unresolved - UNRESOLVED == set(), "new annotations that do not resolve at runtime"
    assert UNRESOLVED - unresolved == set(), "these resolve now: remove them from UNRESOLVED"
