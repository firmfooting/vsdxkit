"""The oracles in `tests/helpers/` must not import `vsdxkit`.

`tests/helpers/__init__.py` states the rule and every module in there repeats
it. This is what enforces it.

The check is transitive by construction: the finder below refuses `vsdxkit` for the
whole duration of the import, so a helper reaching it through a third module is
refused just the same. It is an import-time check, so a `vsdxkit` import inside a
function would still get through - but nothing in these modules imports that
way, and a helper that started to would be reaching for the library at the point
where it matters most.
"""

import ast
import contextlib
import importlib
import os
import pathlib
import pkgutil
import sys

import pytest

TESTS = os.path.dirname(os.path.realpath(__file__))
HELPERS = os.path.join(TESTS, "helpers")


def _helper_modules() -> list[str]:
    """Every module and subpackage under `tests/helpers/`, found rather than listed.

    A hand-written list is a list someone forgets to add to, and the module
    nobody added is the one that gets to import `vsdxkit`. `pkgutil` finds
    subpackages too, which a scan for `*.py` would walk past.
    """
    return sorted(f"helpers.{found.name}" for found in pkgutil.iter_modules([HELPERS]))


class _RefuseVsdx:
    """Refuses `vsdxkit`, and defers on every other name.

    Returning None from `find_spec` hands the request on to the finders after
    it, which is every normal one, so this intervenes for the one name only.
    """

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "vsdxkit" or fullname.startswith("vsdxkit."):
            raise AssertionError(
                f"{fullname!r} was imported. Modules under tests/helpers/ are the oracle the library "
                "is measured against; one that shares the library's parser shares its blind spots "
                "and would go on passing while checking nothing."
            )
        return None


@contextlib.contextmanager
def _refusing_vsdx(module: str):
    """Import `module` from scratch, with `vsdxkit` unavailable.

    The module has to leave `sys.modules` first: an import of a name already
    there returns it without consulting a finder at all, so the check would pass
    on every helper the suite has already loaded - which is all of them.
    `vsdxkit` goes too, or the same shortcut answers the import this is watching for.
    """
    saved = dict(sys.modules)
    for name in list(sys.modules):
        if name == module or name.startswith(("helpers.", "vsdxkit.")) or name in ("helpers", "vsdxkit"):
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
    with _refusing_vsdx("vsdxkit"), pytest.raises(AssertionError, match="oracle"):
        importlib.import_module("vsdxkit")


def test_no_test_module_shadows_a_conftest_fixture():
    """A module global named after a fixture wins, silently, for the whole file.

    Eighteen modules defined `basedir = os.path.dirname(...)` next to the
    session fixture of that name, whose docstring asks them not to. The values
    agreed, so nothing broke - but a test in one of those files asking for
    `basedir` got the global, and the fixture's guarantee stopped applying to it
    with nothing said.

    Module-level assignment only. A name bound by an import or a `for` target
    shadows a fixture just as thoroughly, and is not looked for here, because
    neither has ever been written in this suite and a check nobody can trip is
    one nobody maintains.
    """
    fixtures = _conftest_fixture_names()
    assert "basedir" in fixtures, "the fixture this was written for is gone; check the list is still right"

    paths = sorted(pathlib.Path(TESTS).rglob("test_*.py"))
    assert paths, "no test modules were found, so this checked nothing"

    offenders = []
    for path in paths:
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets = [node.target]
            else:
                continue
            for name in (t.id for t in _flattened(targets) if isinstance(t, ast.Name)):
                if name in fixtures:
                    offenders.append(f"{path.name}:{node.lineno} {name}")

    assert offenders == [], (
        "these module globals shadow a fixture defined in conftest.py, for every test in their "
        "file: " + ", ".join(offenders) + ". Rename the global, or take the fixture."
    )


def _flattened(targets: list[ast.expr]) -> list[ast.expr]:
    """Assignment targets, with `a, b = ...` broken into its parts."""
    flat: list[ast.expr] = []
    for target in targets:
        flat.extend(target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target])
    return flat


def _conftest_fixture_names() -> set[str]:
    """The top-level functions in `tests/conftest.py` carrying a `fixture` decorator.

    Matched on the decorator's source, because `pytest.fixture`,
    `pytest.fixture(scope="session")` and a bare `fixture` are three different
    node shapes for the same thing.
    """
    tree = ast.parse((pathlib.Path(TESTS) / "conftest.py").read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and any("fixture" in ast.dump(decorator) for decorator in node.decorator_list)
    }
