from types import SimpleNamespace as NS

from helpers import route_metrics as rm


def box(x, y, w=2.0, h=1.0):
    return NS(x=x, y=y, width=w, height=h)


def layout(nodes, routes, labels=None, width=10.0, height=6.0):
    return NS(nodes=nodes, routes=routes, labels=labels or {}, width=width, height=height)


def test_bends_ignore_collinear_points_and_duplicates():
    assert rm.bends(((0, 0), (1, 0), (1, 0), (2, 0), (2, 1))) == 1


def test_a_degenerate_route_has_no_bends():
    assert rm.bends(((0, 0),)) == 0
    assert rm.bends(((0, 0), (0, 0))) == 0


def test_a_proper_crossing_is_counted_and_a_shared_end_is_not():
    cross = layout({}, {("a", "b", 0): ((0, 1), (4, 1)), ("c", "d", 0): ((2, 0), (2, 3))})
    touch = layout({}, {("a", "b", 0): ((0, 1), (4, 1)), ("a", "c", 0): ((0, 1), (0, 3))})
    assert rm.crossings(cross) == 1
    assert rm.crossings(touch) == 0


def test_a_collinear_overlap_is_a_shared_run_unless_both_are_together():
    routes = {("a", "b", 0): ((0, 1), (4, 1)), ("c", "d", 0): ((2, 1), (6, 1))}
    assert rm.shared_runs(layout({}, routes)) == [(("a", "b", 0), ("c", "d", 0))]
    assert rm.shared_runs(layout({}, routes), together=frozenset(routes)) == []


def test_ports_on_a_side_are_checked_against_the_pitch():
    nodes = {"a": box(0, 0, 2, 3), "b": box(5, 1), "c": box(5, -1)}
    close = {("a", "b", 0): ((1, 0.05), (4, 1)), ("a", "c", 0): ((1, -0.05), (4, -1))}
    wide = {("a", "b", 0): ((1, 0.4), (4, 1)), ("a", "c", 0): ((1, -0.4), (4, -1))}
    assert rm.port_gap_violations(layout(nodes, close))
    assert rm.port_gap_violations(layout(nodes, wide)) == []


def test_ports_ordered_against_their_far_ends_are_a_violation():
    nodes = {"a": box(0, 0, 2, 3), "b": box(5, 1), "c": box(5, -1)}
    swapped = {("a", "b", 0): ((1, -0.4), (4, 1)), ("a", "c", 0): ((1, 0.4), (4, -1))}
    assert rm.port_order_violations(layout(nodes, swapped))


def test_a_corner_end_belongs_to_one_side():
    nodes = {"a": box(0, 0, 2, 1), "b": box(5, 3)}
    corner = {("a", "b", 0): ((1, 0.5), (4, 3))}
    assert len(rm.side_ends(layout(nodes, corner))) == 2  # one side of a, one of b


def test_metrics_of_an_empty_layout_are_zero():
    empty = layout({}, {})
    assert rm.crossings(empty) == 0 and rm.shared_runs(empty) == []
    assert rm.port_gap_violations(empty) == [] and rm.aspect(layout({}, {}, width=8, height=4)) == 2.0


def test_the_digest_is_a_stable_64_hex_string():
    first = rm.layout_digest({"empty": layout({}, {})})
    assert len(first) == 64 and int(first, 16) >= 0
    assert first == rm.layout_digest({"empty": layout({}, {})})


def test_ports_in_the_same_order_as_their_far_ends_pass():
    nodes = {"a": box(0, 0, 2, 3), "b": box(5, 1), "c": box(5, -1)}
    ordered = {("a", "b", 0): ((1, 0.4), (4, 1)), ("a", "c", 0): ((1, -0.4), (4, -1))}
    assert rm.port_order_violations(layout(nodes, ordered)) == []


def test_a_vertical_collinear_overlap_is_a_shared_run():
    routes = {("a", "b", 0): ((1, 0), (1, 4)), ("c", "d", 0): ((1, 2), (1, 6))}
    assert rm.shared_runs(layout({}, routes)) == [(("a", "b", 0), ("c", "d", 0))]


def test_route_keys_with_the_old_delimiter_in_an_id_do_not_collide():
    pts = ((0.0, 0.0), (1.0, 0.0))
    a = layout({}, {("a|b", "c", 0): pts})
    b = layout({}, {("a", "b|c", 0): pts})
    assert rm.layout_digest({"x": a}) != rm.layout_digest({"x": b})


def test_the_drawn_paths_are_part_of_the_digest():
    lay = layout({}, {})
    one, two = {"x": {("a", "b", 0): ((0.0, 0.0), (1.0, 0.0))}}, {"x": {("a", "b", 0): ((0.0, 0.0), (2.0, 0.0))}}
    assert rm.layout_digest({"x": lay}, one) != rm.layout_digest({"x": lay}, two)
