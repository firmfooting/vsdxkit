"""Consumer-side type fixture: representative API calls, fully typed.

Checked by mypy with ``--disallow-untyped-calls`` in the lint job. If a public
vsdx definition loses its return annotation, Mypy consumers receive ``Any`` and
this fixture fails with ``no-untyped-call`` — reproducing issue #15's evidence
against the installed distribution.
"""

from pathlib import Path

from vsdxkit import Connect, PackageLimits, Page, Shape, VisioFile


def open_document(path: str) -> VisioFile:
    return VisioFile(path)


def page_names(visio_file: VisioFile) -> list[str]:
    return visio_file.get_page_names()


def find_page(visio_file: VisioFile, name: str) -> Page | None:
    return visio_file.get_page_by_name(name)


def coordinate(shape: Shape) -> float | None:
    return shape.x


def connector_endpoint(connect: Connect) -> str | None:
    return connect.shape_id


def shape_connects(shape: Shape) -> list[Connect]:
    # the quoted 'Connect' annotation must resolve for Mypy consumers too
    return shape.connects


def relaxed_limits() -> PackageLimits:
    return PackageLimits(max_members=16, max_member_size=1_048_576)


def save_copy(visio_file: VisioFile, destination: Path) -> None:
    visio_file.save_vsdx(str(destination))
