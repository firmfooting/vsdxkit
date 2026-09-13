"""The oracles in `tests/helpers/` must not import `vsdx`.

`tests/helpers/__init__.py` states the rule and every module in there repeats
it. This is what enforces it.

The check is transitive by construction: the finder below refuses `vsdx` for the
whole duration of the import, so a helper reaching it through a third module is
refused just the same. It is an import-time check, so a `vsdx` import inside a
function would still get through - but nothing in these modules imports that
way, and a helper that started to would be reaching for the library at the point
where it matters most.
"""

import contextlib
import importlib
import os
import pkgutil
import sys

import pytest

HELPERS = os.path.join(os.path.dirname(os.path.realpath(__file__)), "helpers")


def _helper_modules() -> list[str]:
    """Every module and subpackage under `tests/helpers/`, found rather than listed.

    A hand-written list is a list someone forgets to add to, and the module
    nobody added is the one that gets to import `vsdx`. `pkgutil` finds
    subpackages too, which a scan for `*.py` would walk past.
    """
    return sorted(f"helpers.{found.name}" for found in pkgutil.iter_modules([HELPERS]))


class _RefuseVsdx:
    """Refuses `vsdx`, and defers on every other name.

    Returning None from `find_spec` hands the request on to the finders after
    it, which is every normal one, so this intervenes for the one name only.
    """

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "vsdx" or fullname.startswith("vsdx."):
            raise AssertionError(
                f"{fullname!r} was imported. Modules under tests/helpers/ are the oracle the library "
                "is measured against; one that shares the library's parser shares its blind spots "
                "and would go on passing while checking nothing."
            )
        return None


@contextlib.contextmanager
def _refusing_vsdx(module: str):
    """Import `module` from scratch, with `vsdx` unavailable.

    The module has to leave `sys.modules` first: an import of a name already
    there returns it without consulting a finder at all, so the check would pass
    on every helper the suite has already loaded - which is all of them.
    `vsdx` goes too, or the same shortcut answers the import this is watching for.
    """
    saved = dict(sys.modules)
    for name in list(sys.modules):
        if name == module or name.startswith(("helpers.", "vsdx.")) or name in ("helpers", "vsdx"):
            del sys.modules[name]
    finder = _RefuseVsdx()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        # by identity, not by position: the import may have installed a finder
        # of its own in front of this one, and popping would then leave this one
        # in place for the rest of the session
        sys.meta_path.remove(finder)
        # Anything the import left behind is discarded along with it, so the
        # rest of the session goes on using the module objects it already holds.
        sys.modules.clear()
        sys.modules.update(saved)


@pytest.mark.parametrize("module", _helper_modules())
def test_a_helper_imports_without_vsdx(module):
    with _refusing_vsdx(module):
        importlib.import_module(module)


def test_the_refusal_is_reachable():
    """Without this, a finder that never fired would make every case above vacuous."""
    with _refusing_vsdx("vsdx"), pytest.raises(AssertionError, match="oracle"):
        importlib.import_module("vsdx")
