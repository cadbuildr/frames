"""Anchors, interfaces and joint placement of frame members, plates, holes."""

import math

import numpy as np
import pytest
from cadbuildr.foundation import Assembly, Part, make_anchor
from cadbuildr.foundation.dag_utils import show_dag
from cadbuildr.foundation.interfaces import PlaneFace
from cadbuildr.foundation.math_utils import rotation_matrix_to_quaternion
from cadbuildr.frames import (
    Arc3D,
    EndCap,
    Frame,
    Gusset,
    HolePattern,
    Line3D,
    RoundTube,
    SquareTube,
    box_edges,
    polyline,
    rectangle,
)
from cadbuildr.frames.frame import euler_deg


def _same_rotation(q1, q2):
    return min(
        np.linalg.norm(np.array(q1) - np.array(q2)),
        np.linalg.norm(np.array(q1) + np.array(q2)),
    )


def _root(frame, part):
    for root in frame.components:
        if root.name.value == part.name.value:
            return root
    raise KeyError(part.name.value)


def _table():
    corners = [(-300, -200), (300, -200), (300, 200), (-300, 200)]
    top = polyline([(x, y, 700) for x, y in corners], closed=True)
    legs = [Line3D((x, y, 700), (x, y, 0)) for x, y in corners]
    return Frame(top + legs, SquareTube(40, 3), corner="butt", end_caps=EndCap(3))


# ------------------------------------------------------------ placement


@pytest.mark.parametrize(
    "basis",
    [
        ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        ((0, 0, -1), (0, 1, 0), (1, 0, 0)),  # a post (gimbal lock)
        ((0, 0, 1), (0, -1, 0), (1, 0, 0)),
        ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
        (
            (math.cos(0.3), math.sin(0.3), 0),
            (-math.sin(0.3), math.cos(0.3), 0),
            (0, 0, 1),
        ),
    ],
)
def test_euler_deg_round_trips(basis):
    from cadbuildr.foundation.placement import rotation_from_deg

    q = rotation_from_deg(euler_deg(basis))
    expected = rotation_matrix_to_quaternion(np.array(basis, dtype=float).T)
    assert _same_rotation(q, expected) < 1e-9


def test_members_are_placed_by_joints_at_their_skeleton_pose():
    frame = _table()
    assert len(frame.joints) == len(frame.members) + len(frame.end_caps)
    for part in frame.members:
        m = part.member_layout
        root = _root(frame, part)
        assert np.allclose(root.frame.position, m.origin)
        expected = rotation_matrix_to_quaternion(np.array(m.basis, dtype=float).T)
        assert _same_rotation(root.frame.quaternion, expected) < 1e-9


def test_end_caps_connect_onto_member_ends():
    frame = _table()
    assert len(frame.end_caps) == 4
    for cap in frame.end_caps:
        host = frame.members[cap.member_layout.index]
        cap_root, host_root = _root(frame, cap), _root(frame, host)
        # the cap is built in its member's coordinates: same pose
        assert np.allclose(cap_root.frame.position, host_root.frame.position)
        assert (
            _same_rotation(cap_root.frame.quaternion, host_root.frame.quaternion) < 1e-9
        )


def test_frame_check_has_no_coordinate_placements():
    frame = Frame(
        rectangle(600, 400),
        SquareTube(40, 3),
        gussets=[Gusset(at=(-300, -200, 0))],
    )
    codes = {issue["code"] for issue in frame.check()}
    assert "coordinates" not in codes
    assert "loop" not in codes


def test_gusset_is_jointed_to_its_first_member():
    frame = Frame(
        rectangle(600, 400), SquareTube(40, 3), gussets=[Gusset(at=(300, 200, 0))]
    )
    plate = frame.gussets[0]
    root = _root(frame, plate)
    # same world pose as the legacy transform placement
    tf = np.array(plate.placement)
    assert np.allclose(root.frame.position, tf[:3, 3])
    q = rotation_matrix_to_quaternion(tf[:3, :3])
    assert _same_rotation(root.frame.quaternion, q) < 1e-9
    host = frame.members[plate.gusset_layout.member_a]
    assert host.has_anchor("gusset_1")
    show_dag(frame)


# -------------------------------------------------------------- anchors


def test_straight_member_anchors_and_interfaces():
    frame = Frame(rectangle(600, 400), SquareTube(40, 3), corner="miter")
    part = frame.members[0]
    names = {a.name.value for a in part.anchors}
    for n in (
        "node_a",
        "node_b",
        "end_a",
        "end_b",
        "axis",
        "face_top",
        "face_bottom",
        "face_left",
        "face_right",
    ):
        assert n in names
    kinds = {i.anchor.name.value: i.type.value for i in part.interfaces}
    assert kinds["end_a"] == "PlaneFace"
    assert kinds["face_top"] == "PlaneFace"
    x0, x1 = part.length_range
    assert part.anchor("end_a").frame.position == pytest.approx([x0, 0, 0])
    assert part.anchor("end_b").frame.position == pytest.approx([x1, 0, 0])
    assert part.anchor("face_top").frame.position == pytest.approx([x0, 0, 20])
    assert part.anchor("face_left").frame.position == pytest.approx([x0, 20, 0])
    assert part.anchor("node_b").frame.position == pytest.approx([600, 0, 0])


def test_round_tube_axis_is_a_shaft():
    frame = Frame([Line3D((0, 0, 0), (500, 0, 0))], RoundTube(33.7, 2.6))
    part = frame.members[0]
    shaft = [i for i in part.interfaces if i.anchor.name.value == "axis"][0]
    assert shaft.type.value == "Shaft"


def test_bent_member_has_end_anchors_but_no_faces():
    frame = Frame([Arc3D((0, 0, 0), (100, 100, 0), (200, 0, 0))], RoundTube(20, 2))
    names = {a.name.value for a in frame.members[0].anchors}
    assert {"end_a", "end_b", "node_b"} <= names
    assert "face_top" not in names


def test_a_part_mates_onto_a_member_face():
    """Something else (a plate) connects onto a frame face by interfaces."""

    class Pad(Part):
        def __init__(self):
            from cadbuildr.foundation import Extrusion, Point, Rectangle, Sketch

            super().__init__()
            sk = Sketch(self.xy())
            self.add_operation(
                Extrusion(Rectangle.from_center_and_sides(Point(sk, 0, 0), 30, 30), 5)
            )
            seat = self.add_anchor(make_anchor("seat", (0, 0, 0), z_down=True))
            self.add_interface(PlaneFace(name="pad"), seat)

    frame = Frame([Line3D((0, 0, 0), (500, 0, 0))], SquareTube(40, 3))
    scene = Assembly()
    scene.ground(frame)
    pad = Pad()
    scene.connect(pad.interface("seat"), frame.members[0].interface("face_top"))
    show_dag(scene)


# --------------------------------------------------------------- holes


def test_hole_pattern_by_count_and_margin():
    frame = Frame(
        [Line3D((0, 0, 0), (1000, 0, 0))],
        SquareTube(40, 3),
        holes=[HolePattern(0, face="top", size="M8", count=4, margin=100)],
    )
    holes = frame.holes[0]
    assert [h.name.value for h in holes] == [f"hole_{i}" for i in range(4)]
    xs = [h.frame.position[0] for h in holes]
    assert xs == pytest.approx([100, 366.667, 633.333, 900], abs=1e-3)
    assert all(h.frame.position[2] == pytest.approx(20) for h in holes)
    screw_holes = [
        i for i in frame.members[0].interfaces if i.type.value == "ScrewHole"
    ]
    assert len(screw_holes) == 4
    show_dag(frame)


def test_hole_pattern_by_pitch_is_centred():
    frame = Frame([Line3D((0, 0, 0), (600, 0, 0))], SquareTube(40, 3))
    holes = frame.members[0].drill("left", size="M6", count=3, pitch=100)
    assert [h.frame.position[0] for h in holes] == pytest.approx([200, 300, 400])
    assert holes[0].frame.position[1] == pytest.approx(20)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        (dict(face="front", at=[10]), "face must be"),
        (dict(count=3), "pitch= or margin="),
        (dict(at=[3]), "runs off the member"),
        (dict(diameter=50, at=[100]), "does not fit"),
        (dict(), "no hole positions"),
    ],
)
def test_bad_holes_fail_loudly(kwargs, match):
    frame = Frame([Line3D((0, 0, 0), (600, 0, 0))], SquareTube(40, 3))
    with pytest.raises(ValueError, match=match):
        frame.members[0].drill(**kwargs)


def test_hole_pattern_bad_member_index():
    with pytest.raises(ValueError, match="not a member index"):
        Frame(
            [Line3D((0, 0, 0), (600, 0, 0))],
            SquareTube(40, 3),
            holes=[HolePattern(3, at=[100])],
        )


def test_box_frame_builds_with_all_anchors():
    frame = Frame(box_edges(600, 400, 300), SquareTube(30, 2), corner="butt")
    show_dag(frame)
    assert all(p.has_anchor("face_top") for p in frame.members)


def test_drilling_after_placement_reaches_the_dag():
    import json

    frame = Frame([Line3D((0, 0, 0), (600, 0, 0))], SquareTube(40, 3))
    before = json.dumps(show_dag(frame), default=str)
    frame.members[0].drill("top", at=[100, 200])
    after = json.dumps(show_dag(frame), default=str)
    assert len(after) > len(before)
