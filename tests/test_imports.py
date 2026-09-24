import inspect
import pkgutil
import subprocess
import sys
from importlib import import_module

import pytest

import vsdxkit

MODULES = [module.name for module in pkgutil.walk_packages(vsdxkit.__path__, f"{vsdxkit.__name__}.")]


def test_all_package_modules_import():
    discovery_errors: list[str] = []
    modules = list(
        pkgutil.walk_packages(
            vsdxkit.__path__,
            f"{vsdxkit.__name__}.",
            onerror=discovery_errors.append,
        )
    )

    assert discovery_errors == []
    for module in modules:
        import_module(module.name)


@pytest.mark.parametrize("module", MODULES)
def test_each_module_imports_first_in_a_fresh_interpreter(module):
    """Fails if a module can only be imported after some other module has loaded.

    Nothing imports the whole package up front any more, so whichever module a
    caller names first is the one that starts the load. A `from x import Name`
    inside an import cycle breaks for one of the two entry points and not the
    other, so each module gets its own interpreter.
    """
    result = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_the_package_root_re_exports_nothing():
    """Fails if `vsdxkit` binds a class or function that another module defines.

    Each name is imported from the module that defines it
    (`from vsdxkit.document import Document`), so the root holds only its own
    namespace constants and helpers.
    """
    borrowed = [
        name
        for name, value in vars(vsdxkit).items()
        if not name.startswith("_")
        and (inspect.isclass(value) or inspect.isfunction(value))
        and value.__module__ != vsdxkit.__name__
    ]
    assert borrowed == []
