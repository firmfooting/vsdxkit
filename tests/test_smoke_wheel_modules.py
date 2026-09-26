"""The wheel smoke test compares the wheel's modules with `src/vsdxkit` (Phase 7).

setuptools' `build_py` copies into `build/lib` and never deletes from it, so a
wheel built from a working tree that once held a module still ships it after
`src/` deletes it. CI builds from a fresh checkout; a local release build
does not.
"""

import importlib.util
import os
from pathlib import Path

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "tools")
SOURCE = Path(__file__).resolve().parents[1] / "src" / "vsdxkit"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke_wheel = _load("smoke_wheel")


def _wheel_names(*extra: str, without: str | None = None) -> list[str]:
    modules = [f"vsdxkit/{path.name}" for path in SOURCE.glob("*.py") if path.name != without]
    return [*modules, "vsdxkit/py.typed", "vsdxkit/media/media.vsdx", "vsdxkit-1.0.0.dist-info/METADATA", *extra]


def test_the_script_finds_the_checkout_it_sits_in():
    assert smoke_wheel.SOURCE_PACKAGE == SOURCE


def test_a_wheel_with_exactly_the_source_modules_passes():
    assert smoke_wheel.module_set_mismatch(_wheel_names(), SOURCE) is None


def test_a_wheel_built_over_a_stale_build_lib_is_caught():
    """Fails if a module `src/` deleted can ship unnoticed: a stale `build/lib` can carry deleted modules into a wheel."""
    mismatch = smoke_wheel.module_set_mismatch(_wheel_names("vsdxkit/vsdxfile.py", "vsdxkit/containers.py"), SOURCE)
    assert mismatch is not None
    assert "containers.py" in mismatch and "vsdxfile.py" in mismatch


def test_a_wheel_missing_a_module_is_caught():
    mismatch = smoke_wheel.module_set_mismatch(_wheel_names(without="pages.py"), SOURCE)
    assert mismatch is not None and "pages.py" in mismatch
