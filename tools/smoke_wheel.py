"""Distribution smoke test: exercise the installed wheel, not the source tree.

Run by the CI build job from outside the repository checkout against a clean
virtual environment, so every assertion lands on the installed distribution:

    python /path/to/smoke_wheel.py /path/to/dist/*.whl

Raises on any of:
- vsdxkit not importable, or importable only via the checkout (source shadowing)
- py.typed or the bundled media .vsdx files missing from the installation
- loading the bundled donors, create_shape(), connector creation, save or reopen failing
- the wheel's top-level modules differing from the checkout's src/vsdxkit/*.py,
  as a wheel built over a stale build/lib does
"""

import glob
import importlib.util
import os
import sys
import tempfile
import zipfile
from pathlib import Path

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)
    print(f"FAIL: {message}")


def ok(message: str) -> None:
    print(f"ok: {message}")


# The checkout this script sits in. CI runs it from outside the checkout, so
# the path comes from the script, not from the working directory.
SOURCE_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "vsdxkit"


def module_set_mismatch(wheel_names: list[str], source_package: Path) -> str | None:
    """How the wheel's top-level modules differ from `source_package`'s, or None if they match.

    setuptools' build_py copies into build/lib and never deletes from it, so a
    wheel built from a working tree that once held a module still ships it
    after the module is deleted.
    """
    in_wheel = {
        name.removeprefix("vsdxkit/")
        for name in wheel_names
        if name.startswith("vsdxkit/") and name.count("/") == 1 and name.endswith(".py")
    }
    in_source = {path.name for path in source_package.glob("*.py")}
    if in_wheel == in_source:
        return None
    return f"extra in the wheel: {sorted(in_wheel - in_source)}; missing from the wheel: {sorted(in_source - in_wheel)}"


def main() -> int:
    wheel_paths = glob.glob(sys.argv[1] if len(sys.argv) > 1 else "dist/*.whl")
    if not wheel_paths:
        fail("no wheel found")
        return 1
    wheel_path = wheel_paths[0]

    # 1. wheel contents include package data: inspected from the archive itself
    with zipfile.ZipFile(wheel_path) as wheel:
        names = wheel.namelist()
    media_members = sorted(name for name in names if name.startswith("vsdxkit/media/") and name.endswith(".vsdx"))
    if len(media_members) < 2:
        fail(f"wheel carries {len(media_members)} media .vsdx members, expected at least 2: {media_members}")
    else:
        ok(f"wheel media members: {', '.join(media_members)}")
    if "vsdxkit/py.typed" not in names:
        fail("py.typed missing from wheel")
    else:
        ok("py.typed present in wheel")

    if not SOURCE_PACKAGE.is_dir():
        fail(f"no {SOURCE_PACKAGE} beside this script to compare the wheel's modules with")
    elif (mismatch := module_set_mismatch(names, SOURCE_PACKAGE)) is not None:
        fail(f"wheel modules differ from src/vsdxkit: {mismatch}")
    else:
        ok("wheel modules match src/vsdxkit")

    # 2. the import must resolve inside site-packages, not a source checkout
    spec = importlib.util.find_spec("vsdxkit")
    if spec is None or spec.origin is None:
        fail("vsdxkit is not importable")
        return 1
    package_dir = os.path.dirname(os.path.abspath(spec.origin))
    if "site-packages" not in package_dir:
        fail(f"vsdxkit resolves to {package_dir}, which is not an installed location; source tree is shadowing the wheel")
        return 1
    ok(f"vsdxkit installed at {package_dir}")

    # 3. both bundled media files exist in the installed distribution
    for member_name in ("media.vsdx", "palette_extended.vsdx"):
        installed = os.path.join(package_dir, "media", member_name)
        if not os.path.exists(installed):
            fail(f"installed distribution is missing media/{member_name}")
        else:
            ok(f"installed media/{member_name} present")

    import vsdxkit
    from vsdxkit import media
    from vsdxkit.document import Document
    from vsdxkit.shape_kind import ShapeKind

    ok(f"vsdxkit {vsdxkit.__version__} imports cleanly")

    # 4. load the bundled donors, then exercise the creation APIs against a sample document
    try:
        media._sentinel(media.PALETTE, "PALETTE_PROCESS", Document.open)
        media._sentinel(media.MEDIA, media.STRAIGHT_CONNECTOR, Document.open)
    except Exception as error:  # smoke harness reports every failure mode
        fail(f"loading the bundled donors failed from the installed wheel: {error}")
        return 1
    ok("the bundled donors load from the installed wheel")

    source = glob.glob(os.path.join(package_dir, "media", "*.vsdx"))[0]
    with tempfile.TemporaryDirectory() as workdir:
        document = os.path.join(workdir, "smoke.vsdx")
        with open(source, "rb") as handle:
            payload = handle.read()
        with open(document, "wb") as handle:
            handle.write(payload)

        try:
            vis = Document.open(document)
            page = vis.pages[0]
            shape = page.create_shape(ShapeKind.DECISION, x=4.0, y=6.0, width=1.5, height=1.0, text="smoke")
            if shape is None:
                fail("create_shape returned None")
            else:
                ok("create_shape from installed palette")
            other = page.create_shape(ShapeKind.PROCESS, x=8.0, y=6.0, width=1.5, height=1.0, text="smoke-to")
            connector = page.connect(shape, other)
            if connector is None:
                fail("create_connect returned None")
            else:
                ok("create_connect between created shapes")
            vis.save(document)

            reloaded = Document.open(document)
            found = reloaded.pages[0].shapes.by_text("smoke")
            if found is None:
                fail("saved document lost the created shape")
            else:
                ok("save and reopen preserve created shapes")
        except Exception as error:  # smoke harness reports every failure mode
            fail(f"creation API exercise failed: {error}")
            return 1

    if failures:
        print(f"{len(failures)} smoke failure(s)")
        return 1
    print("distribution smoke: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
