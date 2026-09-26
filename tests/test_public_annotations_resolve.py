"""Every public signature's annotations resolve at runtime.

The 1.0 design (amended 2026-09-23) turns each upward dependency into a
`Protocol` declared by the lower module, so every public signature names only
types its own module can import, and `typing.get_type_hints` resolves them all:
introspection, documentation and runtime validators all go through it.
"""

import importlib
import inspect
import pkgutil
import typing
from collections.abc import Callable, Iterator

import vsdxkit


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


# signatures the walk must reach, so a walk that finds nothing cannot pass:
# the ones that named an upward type before the seams, and the public entries
# the seams were built for
FLOOR = {
    "vsdxkit.pages.Page.__init__",
    "vsdxkit.pages.Page.connect",
    "vsdxkit.pages.Page.vis",
    "vsdxkit.shapes.Shape.__init__",
    "vsdxkit.shapes.Shape.copy",
    "vsdxkit.shapes.Shape.master_page",
    "vsdxkit.shapes.Shape.page",
    "vsdxkit.templating.render_document",
}


def test_public_annotations_resolve_at_runtime():
    """Fails if a public annotation names a type its module cannot import, or the walk misses a signature it must see."""
    signatures = dict(_public_signatures())
    assert set(signatures) >= FLOOR, "the walk no longer reaches every public signature"
    unresolved = set()
    for qualified_name, function in signatures.items():
        try:
            typing.get_type_hints(function)
        except (NameError, TypeError, AttributeError):
            unresolved.add(qualified_name)
    assert unresolved == set(), "public annotations that do not resolve at runtime"
