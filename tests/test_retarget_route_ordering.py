"""PR #3 review finding: retarget must validate before deleting records.

A caught refusal must leave the connector's original Connect records in
place: the caller may save afterwards. The 0.x refusal was an invalid route
string; routes are enums now, so the refusal here is a connection point the
target lacks.
"""

import os

import pytest

from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.glue import ConnectorOptions, Glue

FIXTURES = os.path.dirname(os.path.realpath(__file__))


def test_a_refused_retarget_keeps_connect_records(vsdx_copy, tmp_path):
    path = vsdx_copy("test4_connectors.vsdx")
    output = os.path.join(str(tmp_path), "after-rejected-retarget.vsdx")
    vis = Document.open(path)
    page = vis.pages[0]
    connectors = [s for s in page.shapes if "BeginX" in s.cells]
    assert connectors
    connector = connectors[0]
    other = next(s for s in page.shapes if "BeginX" not in s.cells)
    records_before = sorted((c.from_id, c.to_id, c.from_rel) for c in page.connects)
    with pytest.raises(InvalidOperationError, match="connection point"):
        connector.retarget(target=other, options=ConnectorOptions(glue=Glue.POINT, to_point=99))
    records_after = sorted((c.from_id, c.to_id, c.from_rel) for c in page.connects)
    assert records_after == records_before, "rejected retarget removed the connector's records"
    vis.save(output)

    reloaded = Document.open(output)
    records_reloaded = sorted((c.from_id, c.to_id, c.from_rel) for c in reloaded.pages[0].connects)
    assert records_reloaded == records_before, "rejected retarget corrupted saved connectivity"
