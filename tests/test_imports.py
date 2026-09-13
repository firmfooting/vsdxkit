import pkgutil
from importlib import import_module

import vsdxkit


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
