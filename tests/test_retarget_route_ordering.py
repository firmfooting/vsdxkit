"""PR #3 review finding: retarget must validate routes before deleting records.

A caught ValueError from an invalid route must leave the connector's original
Connect records in place — the caller may save afterwards.
"""

import os

import pytest

from vsdxkit import VisioFile

FIXTURES = os.path.dirname(os.path.realpath(__file__))


def test_reanchor_with_invalid_route_keeps_connect_records(vsdx_copy, tmp_path):
    path = vsdx_copy("test4_connectors.vsdx")
    output = os.path.join(str(tmp_path), "after-rejected-retarget.vsdx")
    with VisioFile(path) as vis:
        page = vis.pages[0]
        connectors = [s for s in page.all_shapes if "BeginX" in s.cells]
        assert connectors
        connector = connectors[0]
        other = next(s for s in page.all_shapes if "BeginX" not in s.cells)
        records_before = sorted((c.from_id, c.to_id, c.from_rel) for c in page.connects)
        with pytest.raises(ValueError, match="route"):
            page.reanchor_connector(connector, to_shape=other, route="diagonal")
        records_after = sorted((c.from_id, c.to_id, c.from_rel) for c in page.connects)
        assert records_after == records_before, "rejected retarget removed the connector's records"
        vis.save_vsdx(output)

    with VisioFile(output) as reloaded:
        records_reloaded = sorted((c.from_id, c.to_id, c.from_rel) for c in reloaded.pages[0].connects)
        assert records_reloaded == records_before, "rejected retarget corrupted saved connectivity"
