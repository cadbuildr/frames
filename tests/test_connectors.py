"""The connector hook: junction records, through override, components and
machining."""

import pytest
from cadbuildr.foundation import Circle, Extrusion, Part, Point, Sketch
from cadbuildr.foundation.dag_utils import show_dag
from cadbuildr.frames import (
    Connection,
    ConnectorRule,
    Frame,
    Line3D,
    Placed,
    SquareTube,
    basis_transform,
    box_edges,
    rectangle,
)


class Block(Part):
    def __init__(self, name="block"):
        super().__init__()
        self.add_operation(
            Extrusion(Circle(Point(Sketch(self.xy()), 0.0, 0.0), 3.0), 5.0)
        )


def test_no_connector_keeps_the_frame_unchanged():
    plain = Frame(rectangle(600, 400), SquareTube(40, 3), corner="butt")
    assert plain.connectors == [] and plain.connections == []
    assert len(plain.components) == 4


def test_junction_kinds_of_a_box():
    frame = Frame(box_edges(600, 400, 300), SquareTube(40, 3), corner="butt")
    kinds = [j.kind for j in frame.junctions]
    assert kinds == ["multi"] * 8
    for j in frame.junctions:
        assert j.through is not None and len(j.butting) == 2
        assert len(j.ends) == 3
        # the longest member (600 rail) runs through by default
        assert j.through.member.centerline_length == 600


def test_junction_kinds_free_tee_corner_continuous():
    skeleton = [
        Line3D((0, 0, 0), (500, 0, 0)),
        Line3D((500, 0, 0), (1000, 0, 0)),  # continuous with the first
        Line3D((1000, 0, 0), (1000, 300, 0)),  # corner, free end at the top
        Line3D((250, 0, 0), (250, 200, 0)),  # tee onto the first member
    ]
    frame = Frame(skeleton, SquareTube(40, 3), corner="butt")
    kinds = sorted(j.kind for j in frame.junctions)
    assert kinds == ["continuous", "corner", "free", "free", "free", "tee"]
    tee = next(j for j in frame.junctions if j.kind == "tee")
    assert tee.through.which is None and tee.through.member.index == 0
    assert tee.butting[0].member.index == 3
    assert tee.butting[0].into == pytest.approx((0.0, 1.0, 0.0))


def test_mitered_corner_has_no_through_member():
    frame = Frame(rectangle(600, 400), SquareTube(40, 3), corner="miter")
    for j in frame.junctions:
        assert j.kind == "corner" and j.through is None and len(j.butting) == 2


class PostsThrough(ConnectorRule):
    """Vertical members run through every node."""

    def choose_through(self, node, ends):
        for i, e in enumerate(ends):
            if abs(e.into[2]) > 0.99:
                return i
        return None


def test_choose_through_overrides_the_longest_rule():
    frame = Frame(
        box_edges(600, 400, 300),
        SquareTube(40, 3),
        corner="butt",
        connector=PostsThrough(),
    )
    lengths = sorted(r.length for r in frame.cut_list() for _ in range(r.count))
    # posts run through: 300 + 2 * 20; rails trimmed to the post faces
    assert lengths == [340.0] * 4 + [360.0] * 4 + [560.0] * 4
    for j in frame.junctions:
        assert abs(j.through.into[2]) > 0.99


def test_bad_choose_through_index():
    class Bad(ConnectorRule):
        def choose_through(self, node, ends):
            return 7

    with pytest.raises(ValueError, match="choose_through"):
        Frame(
            box_edges(600, 400, 300), SquareTube(40, 3), corner="butt", connector=Bad()
        )


def test_callable_connector_adds_placed_components():
    calls = []

    def at_corners(junction):
        calls.append(junction.kind)
        if junction.kind != "corner":
            return None
        e = junction.butting[0]
        return Connection(
            components=[Placed(Block(), basis_transform(junction.node, e.basis))]
        )

    frame = Frame(
        rectangle(600, 400), SquareTube(40, 3), corner="butt", connector=at_corners
    )
    assert calls == ["corner"] * 4
    assert len(frame.connectors) == 4
    assert len(frame.components) == 8
    show_dag(frame)  # serialises


def test_machining_lands_on_the_member_and_prepare_member_runs():
    seen = []

    class Drill(ConnectorRule):
        def prepare_member(self, part):
            seen.append(part.member_name)

        def connect(self, junction, layout):
            if junction.kind != "corner":
                return None
            butt = junction.butting[0]

            def drill(part):
                x = (
                    15.0
                    if butt.which == "start"
                    else part.member_layout.centerline_length - 15.0
                )
                plane = part.plane((x, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
                part.add_operation(
                    Extrusion(
                        Circle(Point(Sketch(plane), 0.0, 0.0), 4.0),
                        30.0,
                        start=-30.0,
                        cut=True,
                    )
                )

            return Connection(machining=[(butt, drill)])

    plain = Frame(rectangle(600, 400), SquareTube(40, 3), corner="butt")
    drilled = Frame(
        rectangle(600, 400), SquareTube(40, 3), corner="butt", connector=Drill()
    )
    assert sorted(seen) == [f"member_{i}" for i in range(1, 5)]
    ops = lambda f: [len(m.operations) for m in f.members]  # noqa: E731
    # each butting (short) member got one hole per end
    assert sum(ops(drilled)) == sum(ops(plain)) + 4
    assert drilled.members[0].length_range == pytest.approx((-20.0, 620.0))


def test_bad_connector_type():
    with pytest.raises(TypeError, match="ConnectorRule"):
        Frame(rectangle(600, 400), SquareTube(40, 3), connector=42)


def test_two_ends_on_a_members_interior_butt_onto_it():
    # a shelf rectangle at mid-height of four posts: each shelf corner is two
    # rail ends lying inside a post — both rails butt onto the post (they
    # used to be joined to each other with the post running through them)
    posts = [Line3D((x, y, 0), (x, y, 600)) for x in (-300, 300) for y in (-200, 200)]
    frame = Frame(
        posts + rectangle(600, 400, (0, 0, 300)), SquareTube(40, 3), corner="butt"
    )
    tees = [j for j in frame.junctions if j.kind == "tee"]
    assert len(tees) == 4
    for j in tees:
        assert j.through.which is None and len(j.butting) == 2
        assert abs(j.through.into[2]) == 1.0
    lengths = sorted(r.length for r in frame.cut_list() for _ in range(r.count))
    assert lengths == [360.0] * 2 + [560.0] * 2 + [600.0] * 4
