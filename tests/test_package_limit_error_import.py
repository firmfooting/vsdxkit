"""The import paths #355 moved, and the one it was documented at.

`PackageLimitError` moved from `vsdxkit.vsdxfile` to `vsdxkit.package`, and
then, with the error hierarchy (#365), to `vsdxkit.errors`, which is where
`docs/classes.rst` documents it now. The old path was named in
`docs/classes.rst` at the time, so it was a published location, not an
implementation detail someone happened to find.
"""


def test_package_limit_error_is_importable_from_its_documented_module():
    """Fails if `vsdxkit.vsdxfile.PackageLimitError` stops resolving to the class `docs/classes.rst` documents."""
    from vsdxkit.vsdxfile import PackageLimitError

    assert PackageLimitError.__module__ == "vsdxkit.errors"


def test_the_two_paths_are_the_same_class_not_a_lookalike():
    from vsdxkit.errors import PackageLimitError as defined
    from vsdxkit.package import PackageLimitError as moved
    from vsdxkit.vsdxfile import PackageLimitError as documented

    assert documented is moved is defined
