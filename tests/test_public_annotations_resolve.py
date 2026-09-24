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


def test_public_annotations_resolve_at_runtime():
    unresolved = set()
    for qualified_name, function in _public_signatures():
        try:
            typing.get_type_hints(function)
        except (NameError, TypeError, AttributeError):
            unresolved.add(qualified_name)
    assert unresolved == set(), "public annotations that do not resolve at runtime"
