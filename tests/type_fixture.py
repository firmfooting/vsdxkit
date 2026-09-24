"""Consumer-side type fixture: representative API calls, fully typed.

Checked by mypy with ``--disallow-untyped-calls`` in the lint job. If a public
vsdx definition loses its return annotation, Mypy consumers receive ``Any`` and
this fixture fails with ``no-untyped-call`` — reproducing issue #15's evidence
against the installed distribution.
"""

from pathlib import Path

from vsdxkit.connectors import Connect
from vsdxkit.document import Document
from vsdxkit.package import PackageLimits
from vsdxkit.pages import Page
from vsdxkit.shapes import Shape


def open_document(path: str) -> Document:
    return Document.open(path)


def page_names(visio_file: Document) -> list[str]:
    return visio_file.get_page_names()


def find_page(visio_file: Document, name: str) -> Page | None:
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


def save_copy(visio_file: Document, destination: Path) -> None:
    visio_file.save(str(destination))


def start_shape(page: Page) -> Shape:
    return page.shapes.require_text("Start")


def open_items(page: Page) -> tuple[Shape, ...]:
    return page.shapes.matching_property("Status", "Open")


def group_members(shape: Shape) -> list[Shape]:
    return [*shape.children, *shape.descendants]


def maybe_shape(page: Page, shape_id: str) -> Shape | None:
    return page.children.by_id(shape_id)


def current_state(visio_file: Document) -> Page:
    return visio_file.pages.require_name("Current state")


def review_page(visio_file: Document) -> Page:
    return visio_file.pages.create("Review", index=0)
