import math

import pytest
from cadbuildr.foundation.dag_utils import show_dag
from cadbuildr.frames import (
    Angle,
    Arc3D,
    Channel,
    EndCap,
    Frame,
    Gusset,
    IBeam,
    Line3D,
    Lumber,
    RectTube,
    RoundTube,
    SquareTube,
    box_edges,
    polyline,
    rectangle,
)


def rows_by_length(frame):
    return {r.length: r for r in frame.cut_list()}


# --------------------------------------------------------------- cut lists


def test_rectangle_miter_cut_lengths_and_angles():
    frame = Frame(rectangle(600, 400), SquareTube(40, 3), corner="miter")
    rows = rows_by_length(frame)
    assert set(rows) == {640.0, 440.0}  # long point = centreline + 2 * 20
    for r in rows.values():
        assert r.count == 2
        assert r.end_angles == (45.0, 45.0)
        assert r.end_cuts == ("miter", "miter")
        assert r.profile == "SHS 40x40x3"


def test_rectangle_butt_longer_member_runs_through():
    frame = Frame(rectangle(600, 400), SquareTube(40, 3), corner="butt")
    rows = rows_by_length(frame)
    assert set(rows) == {640.0, 360.0}
    assert rows[640.0].end_cuts == ("through", "through")
    assert rows[360.0].end_cuts == ("butt", "butt")
    assert rows[360.0].end_angles == (0.0, 0.0)
    assert all(r.count == 2 for r in rows.values())


def test_rect_tube_miter_uses_in_plane_width():
    # 60 wide in the frame plane (u), 30 tall (v = up): miters extend by 30
    frame = Frame(rectangle(500, 300), RectTube(60, 30, 3))
    assert set(rows_by_length(frame)) == {560.0, 360.0}


def test_non_right_angle_miter():
    # 120-degree corner (60-degree turn): each end cut 30 degrees from square,
    # long point extends by h/2 * tan(30)
    pts = [
        (0, 0, 0),
        (100, 0, 0),
        (100 + 100 * math.cos(math.radians(60)), 100 * math.sin(math.radians(60)), 0),
    ]
    frame = Frame(polyline(pts), SquareTube(20, 2))
    m1, m2 = frame.layout.members
    assert m1.end.angle_deg == pytest.approx(30.0)
    assert m2.start.angle_deg == pytest.approx(30.0)
    assert m1.end.extension == pytest.approx(10 * math.tan(math.radians(30)))
    assert m1.start.kind == "free" and m2.end.kind == "free"


def test_member_and_part_counts():
    frame = Frame(
        rectangle(600, 400),
        SquareTube(40, 3),
        gussets=[Gusset(at=(-300, -200, 0)), Gusset(at=(300, 200, 0))],
    )
    assert len(frame.members) == 4
    assert len(frame.gussets) == 2
    assert len(frame.components) == 6
    assert [m.name.value for m in frame.members] == [f"member_{i}" for i in range(1, 5)]
    assert sum(r.count for r in frame.cut_list()) == 4


def test_box_frame_three_member_nodes_are_butted():
    frame = Frame(box_edges(800, 500, 700), SquareTube(40, 3))
    rows = rows_by_length(frame)
    # 800 rails run through (+20 each end), 500 rails and 700 posts butt (-20)
    assert {(k, r.count) for k, r in rows.items()} == {
        (840.0, 4),
        (460.0, 4),
        (660.0, 4),
    }


def test_t_junction_butts_onto_member_face():
    frame = Frame(
        [Line3D((0, 0, 0), (500, 0, 0)), Line3D((250, 0, 0), (250, 300, 0))],
        SquareTube(40, 3),
    )
    host, brace = frame.layout.members
    assert host.cut_length == pytest.approx(500)
    assert brace.start.kind == "butt"
    assert brace.cut_length == pytest.approx(280)


def test_coped_round_tube_runs_to_the_host_axis():
    frame = Frame(
        [Line3D((0, 0, 0), (500, 0, 0)), Line3D((250, 0, 0), (250, 300, 0))],
        RoundTube(30, 2),
        corner="coped",
    )
    _, post = frame.layout.members
    assert post.start.kind == "coped"
    assert post.start.cope_member == 0
    assert post.cut_length == pytest.approx(300)  # long point at the host centreline
    show_dag(frame)


def test_coped_wider_member_is_rejected():
    with pytest.raises(ValueError, match="cannot be coped"):
        Frame(
            [Line3D((0, 0, 0), (500, 0, 0)), Line3D((250, 0, 0), (250, 300, 0))],
            [RoundTube(20, 2), RoundTube(40, 2)],
            corner="coped",
        )


def test_arc_member_length_and_tangent_continuity():
    frame = Frame(
        [
            Line3D((0, 0, 0), (500, 0, 0)),
            Arc3D((500, 0, 0), (600, 100, 0), (500, 200, 0)),
            Line3D((500, 200, 0), (0, 200, 0)),
        ],
        RoundTube(30, 2),
    )
    arc = frame.layout.members[1]
    assert arc.centerline_length == pytest.approx(math.pi * 100)
    assert (arc.start.kind, arc.end.kind) == ("continuous", "continuous")
    bent = [r for r in frame.cut_list() if r.bend_radius]
    assert bent[0].bend_radius == 100.0
    show_dag(frame)


# ----------------------------------------------------------- gussets / caps


def test_gusset_sits_in_the_inner_corner():
    frame = Frame(
        rectangle(600, 400),
        SquareTube(40, 3),
        gussets=[Gusset(at=(300, -200, 0), size=60, thickness=5)],
    )
    g = frame.layout.gusset((300, -200, 0))
    assert g.corner == pytest.approx((280, -180, 0))  # node inset by half the tube
    legs = {tuple(round(c, 9) for c in g.leg_a), tuple(round(c, 9) for c in g.leg_b)}
    assert legs == {(-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)}
    assert g.normal == pytest.approx((0, 0, 1))
    assert g.offset == 0.0


def test_gusset_flush_with_top_face():
    frame = Frame(rectangle(600, 400), SquareTube(40, 3))
    g = frame.layout.gusset((300, -200, 0), position="top", thickness=5)
    assert g.offset == pytest.approx(20 - 2.5)


def test_gusset_needs_a_two_member_corner():
    frame = Frame(rectangle(600, 400), SquareTube(40, 3))
    with pytest.raises(ValueError, match="no two-member corner"):
        frame.layout.gusset((0, -200, 0))


def test_end_caps_on_free_ends_only():
    frame = Frame(
        polyline([(0, 0, 0), (300, 0, 0), (300, 200, 0)]),
        SquareTube(40, 3),
        end_caps=EndCap(thickness=3),
    )
    assert len(frame.end_caps) == 2
    assert (
        len(Frame(rectangle(300, 200), SquareTube(40, 3), end_caps=EndCap()).end_caps)
        == 0
    )


# ---------------------------------------------------------------- profiles


@pytest.mark.parametrize(
    "profile, designation, size",
    [
        (SquareTube(40, 3), "SHS 40x40x3", (40, 40)),
        (RectTube(60, 40, 3), "RHS 60x40x3", (60, 40)),
        (RoundTube(33.7, 2.6), "CHS 33.7x2.6", (33.7, 33.7)),
        (Angle(50, 40, 5), "L 50x40x5", (50, 40)),
        (Channel(100, 50, 5, 8), "C 100x50x5/8", (50, 100)),
        (IBeam(200, 100, 5.6, 8.5), "I 200x100x5.6/8.5", (100, 200)),
        (Lumber("2x4"), "Lumber 2x4", (38.1, 88.9)),
    ],
)
def test_profiles(profile, designation, size):
    assert profile.designation == designation
    assert profile.size == pytest.approx(size)
    frame = Frame(rectangle(400, 300), profile)
    show_dag(frame)


def test_unknown_lumber_size():
    with pytest.raises(ValueError, match="unknown lumber size"):
        Lumber("3x7")


def test_profile_count_must_match_skeleton():
    with pytest.raises(ValueError, match="profiles for"):
        Frame(rectangle(400, 300), [SquareTube(40, 3)] * 3)


def test_bad_corner_type():
    with pytest.raises(ValueError, match="corner must be"):
        Frame(rectangle(400, 300), SquareTube(40, 3), corner="weld")


def test_cut_list_table_text():
    table = Frame(rectangle(600, 400), SquareTube(40, 3)).cut_list_table()
    assert "SHS 40x40x3" in table and "640.0" in table and "miter/miter" in table
