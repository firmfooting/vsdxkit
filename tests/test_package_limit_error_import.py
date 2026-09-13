"""The import paths #355 moved, and the one it was documented at.

`PackageLimitError` moved from `vsdxkit.vsdxfile` to `vsdxkit.package`. The
old path was named in `docs/classes.rst` at the time, so it was a published
location, not an implementation detail someone happened to find.
"""


def test_package_limit_error_is_importable_from_its_documented_module():
    from vsdxkit.vsdxfile import PackageLimitError

    assert PackageLimitError.__module__ == "vsdxkit.package"


def test_the_two_paths_are_the_same_class_not_a_lookalike():
    from vsdxkit.package import PackageLimitError as moved
    from vsdxkit.vsdxfile import PackageLimitError as documented

    assert documented is moved
