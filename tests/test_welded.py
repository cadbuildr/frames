"""Welded and fabricated frames: section geometry against the catalogues,
cope / mitre / bevel geometry against hand-computed values, welds, the
load check and the fabrication configurables."""

import math

import numpy as np
import pytest
from cadbuildr.foundation import estimate_part_extents
from cadbuildr.foundation.dag_utils import show_dag
from cadbuildr.foundation.library import get_manifest
from cadbuildr.foundation.library.registry import call_configurable, find_item
from cadbuildr.foundation.math_utils import quaternion_to_axes
from cadbuildr.frames import (
    BEVEL_ASME_B16_25,
    AnchorBasePlate,
    Angle,
    BasePlateError,
    Bevel,
    BevelError,
    Cope,
    CopeError,
    CornerGusset,
    EndPrepError,
    Frame,
    FrameMember,
    Line3D,
    LoadCheckError,
    PreparedTube,
    RectTube,
    RoundBar,
    RoundTube,
    SectionGeometryError,
    SimplySupportedBeam,
    SquareTube,
    TubeEndCap,
    WeldSymbol,
    anchor_hole_diameter,
    bevel_volume,
    cope_extent,
    cope_perimeter,
    cope_template,
    cope_template_svg,
    coped_volume,
    default_throat,
    en10219_corner_radius,
    load_table,
    plane_cut_perimeter,
    profile_from_designation,
    rectangle,
    rounded_polygon,
    saddle_curve,
    simple_span_udl,
    standard_profile,
    weld_summary,
)

ITEMS = {i["id"]: i for i in get_manifest("cadbuildr.frames")["items"]}

# --------------------------------------------------------------------------- #
# Sections: drawn outline (radii) vs published catalogue values
# --------------------------------------------------------------------------- #

# (designation, area cm2, I about the axis parallel to u (x-x / y-y) cm4,
#  W_el cm3) — published:
# - L 120/150/200: British Steel "Equal angles (EA)" datasheet (EN 10056-1)
# - PFC: British Steel "Parallel flange channels" datasheet (BS EN 10365)
# - L50x50x5, L40x40x4, UPN, IPE, HEA, SHS: EN 10056-1 / DIN 1026-1 /
#   EN 10365 / EN 10219-2 catalogue tables (ArcelorMittal sections
#   catalogue values)
CATALOGUE = [
    ("L120x120x10", 23.2, 313, 36.0),
    ("L150x150x12", 34.8, 737, 67.8),
    ("L200x200x20", 76.3, 2851, 199),
    ("L50x50x5", 4.80, 11.0, 3.05),
    ("L40x40x4", 3.08, 4.47, 1.55),
    ("PFC150x75x18", 22.8, 861, 115),
    ("PFC200x90x30", 37.9, 2523, 252),
    ("PFC300x100x46", 58.0, 8229, 549),
    ("UPN80", 11.0, 106, 26.5),
    ("UPN100", 13.5, 206, 41.2),
    ("UPN200", 32.2, 1910, 191),
    ("IPE100", 10.3, 171, 34.2),
    ("IPE200", 28.5, 1943, 194),
    ("HEA160", 38.8, 1673, 220),
    ("SHS 40x40x3", 4.21, 9.32, 4.66),
    ("SHS 100x100x5", 18.4, 271, 54.2),
]


@pytest.mark.parametrize("designation, area, i_u, w_u", CATALOGUE)
def test_section_properties_match_catalogue(designation, area, i_u, w_u):
    props = profile_from_designation(designation).section_properties()
    assert props.area_cm2 == pytest.approx(area, rel=0.005)
    assert props.i_u_cm4 == pytest.approx(i_u, rel=0.005)
    assert props.w_u_cm3 == pytest.approx(w_u, rel=0.006)


def test_angle_area_closed_form():
    # A = t (2a - t) + (1 - pi/4) (r1^2 - 2 r2^2): root fillet adds, toe
    # radii remove material.
    a, t, r1, r2 = 50.0, 5.0, 7.0, 3.5
    expected = t * (2 * a - t) + (1 - math.pi / 4) * (r1**2 - 2 * r2**2)
    assert Angle(a, a, t, r1, r2).area == pytest.approx(expected, rel=1e-4)


def test_en10219_corner_radii_and_tube_area():
    assert [en10219_corner_radius(t) for t in (3, 6, 8, 12)] == [6, 12, 20, 36]
    tube = standard_profile("SHS", "40x40x3")
    assert tube.corner_radius == 6 and tube.inner_corner_radius == 3
    # 40^2 - 34^2 - (4 - pi)(ro^2 - ri^2)
    assert tube.area == pytest.approx(1600 - 1156 - (4 - math.pi) * (36 - 9), rel=1e-4)
    assert tube.size == pytest.approx((40.0, 40.0))  # bounding box unchanged


def test_rolled_sections_are_one_compact_polygon_with_arcs():
    member = standard_profile("L", "L50x50x5")
    loop = member.outer_loop()
    assert sum(1 for *_, b in loop if b > 0) == 2  # two toe radii (convex)
    assert sum(1 for *_, b in loop if b < 0) == 1  # the root radius (concave)
    from cadbuildr.frames import AngleMember

    part = AngleMember("L50x50x5", 500)
    shapes = part.operations[0].shape
    assert type(shapes[0]).__name__ == "CompactPolygon"
    assert any(abs(b) > 0 for b in shapes[0].bulges)
    show_dag(part)


def test_upn_taper_thickens_flanges_towards_the_web():
    upn = standard_profile("UPN", "UPN100")
    pts = upn.outer_points()
    toe, root = pts[2][1] - pts[1][1], pts[3][1] - pts[0][1]
    assert root - toe == pytest.approx(0.08 * (50 - 6))  # 8 % over the free flange


def test_rounded_polygon_rejects_radii_that_do_not_fit():
    with pytest.raises(SectionGeometryError, match="need"):
        rounded_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [6, 6, 0, 0])
    with pytest.raises(ValueError, match="corner_radius"):
        RectTube(40, 40, 3, 25)
    with pytest.raises(ValueError, match="toe_radius"):
        Angle(40, 40, 4, 6, 5)


# --------------------------------------------------------------------------- #
# Copes: the analytic saddle against closed forms
# --------------------------------------------------------------------------- #


def test_equal_round_cope_removes_half_a_steinmetz_solid():
    # solid bar R onto a host of the same radius, square: the material lost
    # from a bar ending at the host axis is half the bicylinder 16 R^3 / 3.
    r, x_end = 20.0, 100.0
    v = coped_volume(RoundBar(2 * r), Cope(RoundBar(2 * r)), x_end)
    assert v == pytest.approx(math.pi * r * r * x_end - 8 * r**3 / 3, rel=2e-4)


def test_equal_round_cope_weld_is_one_ellipse():
    # the saddle of two equal cylinders is two half-ellipses (semi-axes
    # R sqrt 2 and R): one full ellipse perimeter (Ramanujan).
    r = 20.0
    a, b = math.sqrt(2) * r, r
    ellipse = math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))
    assert cope_perimeter(RoundBar(2 * r), Cope(RoundBar(2 * r))) == pytest.approx(
        ellipse, rel=1e-4
    )


def test_saddle_curve_perpendicular_and_oblique():
    curve = saddle_curve(33.7, 48.3)
    R, r = 24.15, 16.85
    for phi, x in curve[::9]:
        p = math.radians(phi)
        assert x == pytest.approx(math.sqrt(R * R - (r * math.sin(p)) ** 2))
    # 45 deg: x = (r cos phi cos a + sqrt(R^2 - (r sin phi)^2)) / sin a
    oblique = dict(saddle_curve(33.7, 48.3, 45))
    assert oblique[0.0] == pytest.approx((r * math.cos(math.pi / 4) + R) / math.sin(math.pi / 4))
    # template: depth from 0 at the long point to R - sqrt(R^2 - r^2) at the side
    tpl = cope_template(33.7, 48.3)
    assert min(d for _, d in tpl) == pytest.approx(0.0)
    assert max(d for _, d in tpl) == pytest.approx(R - math.sqrt(R * R - r * r))
    assert tpl[-1][0] == pytest.approx(math.pi * 33.7)
    svg = cope_template_svg(33.7, 48.3)
    assert svg.startswith("<svg") and "<path" in svg and "mm" in svg


def test_cope_onto_a_flat_face_is_a_plane():
    x0, x1 = cope_extent(RoundTube(33.7, 2.6), Cope(standard_profile("SHS", "50x50x3"), 60))
    a = math.radians(60)
    assert x0 == pytest.approx((-16.85 * math.cos(a) + 25) / math.sin(a))
    assert x1 == pytest.approx((16.85 * math.cos(a) + 25) / math.sin(a))


def test_cope_errors():
    with pytest.raises(CopeError, match="wider"):
        cope_extent(RoundTube(60.3, 3.2), Cope(RoundTube(48.3, 3.2)))
    with pytest.raises(CopeError, match="wider"):
        cope_extent(RoundTube(33.7, 2.6), Cope(RoundTube(48.3, 3.2), offset=10))
    with pytest.raises(CopeError, match="between"):
        Cope(RoundTube(48.3, 3.2), angle=10)
    with pytest.raises(CopeError, match="not supported"):
        cope_extent(RoundTube(20, 2), Cope(Angle(50, 50, 5)))


# --------------------------------------------------------------------------- #
# PreparedTube geometry
# --------------------------------------------------------------------------- #


def _plane_axes(op):
    frame = op.shape[0].center.sketch.plane.frame if hasattr(op.shape[0], "center") else op.shape[0].sketch.plane.frame
    x, y, z = quaternion_to_axes(list(frame.quaternion))
    return np.asarray(frame.position, float), np.asarray(x), np.asarray(z)


def test_prepared_tube_square_cope_cut_length_and_saddle_cut():
    tube = PreparedTube(section="CHS 33.7x2.6", length=500, end_a="cope", cope_host="CHS 48.3x3.2")
    long_point = math.sqrt(24.15**2 - 16.85**2)  # x of the saddle's lowest point
    assert tube.cut_length == pytest.approx(500 - long_point, abs=1e-3)
    # the last operation subtracts the host's OD (r 24.15) extruded along
    # the host axis (local Y), its sketch u along Z
    cut = tube.operations[-1]
    assert cut.cut.value is True
    assert cut.shape[0].radius.value == pytest.approx(24.15)
    origin, x_axis, normal = _plane_axes(cut)
    assert np.allclose(origin, 0.0)
    assert np.allclose(np.abs(normal), [0, 1, 0], atol=1e-9)
    assert np.allclose(x_axis, [0, 0, 1], atol=1e-9)
    assert tube.saw_angle("start") is None  # a cope, not a saw cut
    ext = estimate_part_extents(tube).boxes[0]
    assert sorted(2 * ext.half) == pytest.approx(sorted([33.7, 33.7, 500 - long_point]))
    show_dag(tube)


def test_prepared_tube_offset_and_oblique_cope():
    tube = PreparedTube(
        section="CHS 33.7x2.6", length=400, end_a="cope", cope_host="CHS 60.3x3.2",
        cope_angle=60, cope_offset=8,
    )
    origin, _, normal = _plane_axes(tube.operations[-1])
    assert origin == pytest.approx([0, 0, -8])
    assert np.allclose(np.abs(normal), [0.5, math.sqrt(3) / 2, 0], atol=1e-9)
    assert tube.welds[0].length == pytest.approx(
        cope_perimeter(RoundTube(33.7, 2.6), Cope(RoundTube(60.3, 3.2), 60, 8))
    )
    assert tube.welds[0].length > math.pi * 33.7  # a saddle is longer than the circle


def test_prepared_tube_mitres_and_saw_angles():
    rail = PreparedTube(section="SHS 40x40x3", length=600, end_a="miter", end_b="miter")
    assert rail.cut_length == pytest.approx(640.0)  # 600 + 2 x 20 tan 45
    assert str(rail.saw_angle("start")) == "45.0"
    bevel = PreparedTube(
        section="SHS 40x40x3", length=600, end_a="miter", end_b="square",
        miter_a=30, miter_axis="u",
    )
    saw = bevel.saw_angle("start")
    assert saw.miter == pytest.approx(0.0) and saw.bevel == pytest.approx(30.0)
    assert bevel.cut_length == pytest.approx(600 + 20 * math.tan(math.radians(30)))
    onto_flat = PreparedTube(section="CHS 33.7x2.6", end_a="cope", cope_host="SHS 50x50x3", cope_angle=60)
    assert onto_flat.saw_angle("start").miter == pytest.approx(30.0)


def test_prepared_tube_bevels():
    pipe = PreparedTube(section="CHS 114.3x4", end_a="bevel", end_b="square",
                        bevel_angle=37.5, root_face=1.6)
    lathe = [o for o in pipe.operations if type(o).__name__ == "Lathe"]
    assert len(lathe) == 1 and lathe[0].cut.value is True
    assert pipe.welds[0].kind == "single_v_butt"
    shs = PreparedTube(section="SHS 60x60x4", end_a="bevel")
    wedges = [o for o in shs.operations if type(o).__name__ == "Extrusion" and o.cut.value]
    assert len(wedges) == 1 + 4  # the bore + one wedge per wall
    with pytest.raises(BevelError, match="root face"):
        PreparedTube(section="CHS 33.7x2.6", end_a="bevel", root_face=3)
    with pytest.raises(BevelError, match="square"):
        PreparedTube(section="SHS 40x40x3", end_a="miter").bevel("start", Bevel())


def test_bevel_volume_closed_form_vs_integral():
    tube, bevel = RoundTube(114.3, 4.0), BEVEL_ASME_B16_25
    ro = 57.15
    a = ro - 4.0 + 1.6
    k = math.tan(math.radians(37.5))
    n = 2000
    numeric = sum(
        2 * math.pi * rho * (rho - a) * k * (ro - a) / n
        for rho in (a + (i + 0.5) * (ro - a) / n for i in range(n))
    )
    assert bevel_volume(tube, bevel) == pytest.approx(numeric, rel=1e-5)


def test_prepared_tube_rejects_bad_inputs():
    with pytest.raises(EndPrepError, match="too short"):
        PreparedTube(length=20, end_a="cope", end_b="cope", cope_angle=20)
    with pytest.raises(EndPrepError, match="hollow"):
        PreparedTube(section="RD 20")


def _configs(item_id):
    item = ITEMS[item_id]
    yield None, {}
    for c in item["configurations"]:
        yield c["name"], c["values"]


NEW_ITEMS = [
    "frames:PreparedTube",
    "frames:AnchorBasePlate",
    "frames:CornerGusset",
    "frames:TubeEndCap",
    "frames:SimplySupportedBeam",
    "frames:PFCMember",
]


@pytest.mark.parametrize(
    "item_id, config, values",
    [(i, n, v) for i in NEW_ITEMS for n, v in _configs(i)],
)
def test_new_items_every_configuration_builds(item_id, config, values):
    component = call_configurable(find_item(item_id), values)
    show_dag(component)


# --------------------------------------------------------------------------- #
# Frames: saw angles, welds, BOM
# --------------------------------------------------------------------------- #


def _trailer():
    rails = [Line3D((-1200, -600, 0), (1200, -600, 0)), Line3D((-1200, 600, 0), (1200, 600, 0))]
    cross = [Line3D((x, -600, 0), (x, 600, 0)) for x in (-1200, 0, 1200)]
    arms = [Line3D((-2300, 0, 0), (-1200, -600, 0)), Line3D((-2300, 0, 0), (-1200, 600, 0))]
    rhs = standard_profile("RHS", "100x50x4")
    return Frame(rails + cross + arms, [rhs] * 7, corner="butt")


def test_cut_list_saw_angles_per_end():
    frame = _trailer()
    rows = {r.members: r for r in frame.cut_list()}
    arm = next(r for m, r in rows.items() if "member_6" in m)
    arm_angle = 90 - math.degrees(math.atan2(600, 1100))  # cut on the rail's face
    assert any(s and s.miter == pytest.approx(arm_angle, abs=0.05) for s in arm.saw_angles)
    assert "Saw 1" in frame.cut_list_table()
    mitred = Frame(rectangle(600, 400), SquareTube(40, 3)).cut_list()
    assert all(str(s) == "45.0" for r in mitred for s in r.saw_angles)


def test_frame_welds_lengths_and_symbols():
    frame = Frame(rectangle(600, 400), standard_profile("SHS", "40x40x3"), corner="butt")
    welds = frame.welds()
    assert len(welds) == 4 and {w.kind for w in welds} == {"fillet"}
    perimeter = 4 * (40 - 2 * 6) + 2 * math.pi * 6  # rounded SHS outline
    assert welds[0].length == pytest.approx(perimeter, rel=1e-3)
    assert welds[0].throat == 3.0
    assert welds[0].symbol.text().startswith("a3 ◺ (all round)")
    assert frame.weld_length() == pytest.approx(4 * perimeter, rel=1e-3)
    mitred = Frame(rectangle(600, 400), SquareTube(40, 3), corner="miter").welds()
    assert {w.kind for w in mitred} == {"square_butt"}
    # a 45-degree mitre outline: two faces stretched by 1/cos(45)
    assert mitred[0].length == pytest.approx(2 * 40 + 2 * 40 * math.sqrt(2))


def test_frame_bom_has_total_weld_length():
    from cadbuildr.frames import EndCap, Gusset

    frame = Frame(
        rectangle(600, 400), SquareTube(40, 3), corner="butt",
        gussets=[Gusset(at=(300, 200, 0), size=60, thickness=5)],
    )
    rows = frame.bom()
    total = rows[-1]
    assert total["kind"] == "total"
    assert total["weld_length_mm"] == pytest.approx(frame.weld_length())
    gusset_welds = [w for w in frame.welds() if w.joint == "gusset_1"]
    assert [w.total_length for w in gusset_welds] == [120.0, 120.0]  # 2 legs x 2 faces
    weld_rows = [r for r in rows if r["kind"] == "weld"]
    assert sum(r["length_mm"] for r in weld_rows) == pytest.approx(total["weld_length_mm"])
    capped = Frame([Line3D((0, 0, 0), (500, 0, 0))], RoundTube(48.3, 3.2), end_caps=EndCap(3))
    assert [round(w.length, 1) for w in capped.welds()] == [round(math.pi * 48.3, 1)] * 2
    assert "weld length" in frame.bom_table()


def test_weld_lines_reach_cadbuildr_bom():
    bom = pytest.importorskip("cadbuildr.bom")
    frame = Frame(rectangle(600, 400), standard_profile("SHS", "40x40x3"), corner="butt")
    result = bom.build_bom(frame)
    text = result.to_markdown()
    assert "Weld fillet a3" in text
    assert "SHS 40x40x3" in text


def test_weld_defaults_and_symbols():
    assert [default_throat(t) for t in (2, 3, 4, 5, 10)] == [2.0, 3.0, 3.0, 3.5, 7.0]
    sym = WeldSymbol("fillet", 4, length=120, side="both", process=135, quality="B")
    assert sym.text() == "a4 ◺ 120 (both sides) < 135 / ISO 5817-B"
    assert sym.to_dict()["standard"] == "ISO 2553"
    with pytest.raises(ValueError, match="elementary"):
        WeldSymbol("blob")
    welds = Frame(rectangle(600, 400), SquareTube(40, 2), corner="butt").welds()
    assert "3 mm minimum" in welds[0].notes[0]
    summary = weld_summary(welds)
    assert summary["fillet a2"]["count"] == 4


# --------------------------------------------------------------------------- #
# Load check
# --------------------------------------------------------------------------- #


def test_simple_span_udl_hand_calculation():
    ipe = standard_profile("IPE", "IPE200")
    r = simple_span_udl(ipe, 4000, 10.0, self_weight=False)
    i = ipe.section_properties().i_u
    w_el = ipe.section_properties().w_u
    assert r.deflection == pytest.approx(5 * 10 * 4000**4 / (384 * 210000 * i))
    assert r.deflection == pytest.approx(8.17, abs=0.02)  # with I = 1943 cm4
    assert r.stress == pytest.approx(10 * 4000**2 / 8 / w_el)
    assert r.deflection_limit == 16.0 and r.ok
    heavy = simple_span_udl(ipe, 4000, 25.0, grade="S355")
    assert not heavy.ok and heavy.governs == "deflection"


def test_load_table_is_the_inverse_of_the_check():
    shs = standard_profile("SHS", "50x50x3")
    for row in load_table(shs, [1000, 2000, 3000], grade="S275"):
        r = simple_span_udl(shs, row.span, row.allowable, grade="S275")
        assert r.utilisation == pytest.approx(1.0, rel=1e-9)
    with pytest.raises(LoadCheckError, match="grade"):
        load_table(shs, [1000], grade="S999")
    with pytest.raises(LoadCheckError, match="span"):
        simple_span_udl(shs, 0, 1)


def test_load_check_runs_in_the_checks_hook():
    assert "check" not in FrameMember.__dict__  # the hook, never check()
    beam = SimplySupportedBeam(section="SHS 40x40x3", span=2000, udl=5.0)
    codes = {i["code"] for i in beam.check()}
    assert "frames.load.deflection" in codes
    ok = SimplySupportedBeam(section="IPE200", span=4000, udl=8.0)
    assert [i["code"] for i in ok.check()] == ["frames.load.ok"]
    frame = Frame(rectangle(1500, 700), standard_profile("SHS", "50x50x3"), corner="butt")
    frame.apply_udl("member_1", 30.0)
    issues = frame.check()
    assert any(i["code"] == "frames.load.yield" for i in issues)
    dag = show_dag(frame)
    assert any(c["code"].startswith("frames.load") for c in dag["checks"])


# --------------------------------------------------------------------------- #
# Plates
# --------------------------------------------------------------------------- #


def test_anchor_base_plate_holes_checks_and_errors():
    assert anchor_hole_diameter("M16") == 18 and anchor_hole_diameter("M24", "oversize") == 30
    plate = AnchorBasePlate(column="SHS 100x100x5", width=250, depth=250, thickness=15, anchor="M16", edge=35)
    holes = [i for i in plate.interfaces if i.type.value == "ScrewHole"]
    assert len(holes) == 4 and plate.check() == []
    assert plate.welds[0].length == pytest.approx(
        plane_cut_perimeter(standard_profile("SHS", "100x100x5"), (1, 0, 0))
    )
    ext = estimate_part_extents(plate).boxes[0]
    assert sorted(2 * ext.half) == pytest.approx([15, 250, 250])
    tight = AnchorBasePlate(column="SHS 100x100x5", width=160, depth=160, anchor="M16", edge=12)
    codes = {i["code"] for i in tight.check()}
    assert {"frames.baseplate.edge", "frames.baseplate.washer"} <= codes
    assert len(AnchorBasePlate(pattern="8", width=400, depth=300, edge=40).holes) == 8
    with pytest.raises(BasePlateError, match="larger"):
        AnchorBasePlate(column="SHS 100x100x5", width=90, depth=90, edge=20, anchor="M12")
    with pytest.raises(BasePlateError, match="do not fit"):
        AnchorBasePlate(anchor="M30", edge=10)


def test_corner_gusset_area_with_true_radii():
    g = CornerGusset(leg=80, width=25, thickness=5, inner_radius=10, corner_radius=5)
    expected = 2 * 80 * 25 - 25 * 25 + (1 - math.pi / 4) * 10**2 - (1 - math.pi / 4) * 5**2
    assert g.area == pytest.approx(expected, rel=1e-4)
    assert type(g.operations[0].shape[0]).__name__ == "CompactPolygon"
    with pytest.raises(ValueError, match="inner_radius"):
        CornerGusset(leg=60, width=40, inner_radius=30)


def test_tube_end_caps():
    shs = standard_profile("SHS", "50x50x3")
    plate = TubeEndCap(section="SHS 50x50x3", style="plate", thickness=3)
    assert plate.area == pytest.approx(shs.outer_area)
    inset = TubeEndCap(section="CHS 48.3x3.2", style="inset", thickness=4, clearance=0.5)
    assert inset.area == pytest.approx(math.pi * (24.15 - 3.2 - 0.5) ** 2)
    assert inset.welds[0].length == pytest.approx(2 * math.pi * (24.15 - 3.2))
    tube = PreparedTube(section="SHS 50x50x3", end_a="square", length=300)
    from cadbuildr.foundation import Assembly

    asm = Assembly()
    asm.add_component(tube)
    asm.connect(plate.interface("seat"), tube.interface("end_b"))
    show_dag(asm)


def test_bolted_frames_report_no_welds():
    frame = Frame(rectangle(600, 400), SquareTube(40, 3), corner="butt", welded=False)
    assert frame.welds() == [] and frame.weld_length() == 0
