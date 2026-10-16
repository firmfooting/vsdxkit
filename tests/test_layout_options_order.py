"""LayoutOptions keeps 0.11.0's positional order; fields added since come after it."""

from dataclasses import fields

from vsdxkit.layout import LayoutOptions


def test_fields_added_after_0_11_follow_the_0_11_fields():
    names = [f.name for f in fields(LayoutOptions)]
    assert names[: names.index("channel_pitch") + 1] == [
        "direction",
        "layer_gap",
        "node_gap",
        "margin",
        "group_padding",
        "lane_padding",
        "lane_heading",
        "sweeps",
        "page",
        "parents",
        "headings",
        "edge_labels",
        "port_pitch",
        "channel_pitch",
    ]
