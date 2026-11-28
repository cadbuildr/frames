"""Library configurables: the manifest, every configuration builds a DAG,
standard tables, weight and stock planning."""

import pytest
from cadbuildr.foundation.dag_utils import show_dag
from cadbuildr.foundation.library import get_manifest
from cadbuildr.foundation.library.registry import call_configurable, find_item
from cadbuildr.frames import (
    EN10219_SHS,
    IPE,
    BasePlate,
    Frame,
    IPEMember,
    LadderFrame,
    Line3D,
    Piece,
    PieceTooLongError,
    RectangularFrame,
    RoundTubeMember,
    SquareTube,
    SquareTubeMember,
    TableFrame,
    UnknownSectionError,
    profile_from_designation,
    rectangle,
    standard_member,
    standard_profile,
    stock_plan,
)

MANIFEST = get_manifest("cadbuildr.frames")
ITEMS = {i["id"]: i for i in MANIFEST["items"]}


def test_manifest_lists_members_plates_and_frames():
    assert "errors" not in MANIFEST
    assert MANIFEST["library"]["id"] == "frames"
    expected = {
        "frames:SquareTubeMember",
        "frames:RectTubeMember",
        "frames:RoundTubeMember",
        "frames:HSSMember",
        "frames:AngleMember",
        "frames:ChannelMember",
        "frames:IPEMember",
        "frames:HEAMember",
        "frames:WideFlangeMember",
        "frames:FlatBarMember",
        "frames:RoundBarMember",
        "frames:LumberMember",
        "frames:BasePlate",
        "frames:TriangularGusset",
        "frames:RectangularFrame",
        "frames:TableFrame",
        "frames:ShelvingFrame",
        "frames:LadderFrame",
        "frames:GateFrame",
    }
    assert expected <= set(ITEMS)
    toolbar_ids = {i for s in MANIFEST["toolbar"]["sections"] for i in s["items"]}
    assert toolbar_ids == set(ITEMS)


def test_member_sizes_are_configurations_with_anchors_and_interfaces():
    shs = ITEMS["frames:SquareTubeMember"]
    assert shs["standard"] == "EN 10219-2"
    assert [c["name"] for c in shs["configurations"]] == list(EN10219_SHS)
    size = next(i for i in shs["inputs"] if i["name"] == "size")
    assert size["widget"]["kind"] == "enum"
    assert size["widget"]["default"] == "40x40x3"
    assert "description" in size
    assert {"end_a", "end_b", "axis", "face_top"} <= set(shs["anchors"])
    types = {i["name"]: i["type"] for i in shs["interfaces"]}
    assert types["end_a"] == "PlaneFace"
    tube = ITEMS["frames:RoundTubeMember"]
    assert {i["name"]: i["type"] for i in tube["interfaces"]}["axis"] == "Shaft"


def _all_configurations():
    for item_id, item in ITEMS.items():
        yield item_id, None, {}
        for config in item["configurations"]:
            if item["kind"] == "part" and len(item["configurations"]) > 3:
                continue  # every size row is checked by test_every_size_builds
            yield item_id, config["name"], config["values"]


@pytest.mark.parametrize("item_id, config, values", list(_all_configurations()))
def test_every_item_and_configuration_builds_a_dag(item_id, config, values):
    component = call_configurable(find_item(item_id), values)
    show_dag(component)


@pytest.mark.parametrize("family, table", [("SHS", EN10219_SHS), ("IPE", IPE)])
def test_every_size_builds(family, table):
    for size in table:
        member = standard_member(family, size, 300)
        assert member.length == 300
        assert member.profile.area > 0


def test_member_hole_row_has_screw_holes():
    m = SquareTubeMember("50x50x3", 1200, hole_count=5, hole_size="M10")
    assert len(m.holes) == 5
    holes = [i for i in m.interfaces if i.type.value == "ScrewHole"]
    assert len(holes) == 5
    show_dag(m)


def test_member_names_and_designations():
    assert IPEMember("IPE200", 3000).name.value == "IPE200 x 3000"
    assert RoundTubeMember().profile.designation == "CHS 48.3x3.2"


def test_base_plate_mates_onto_a_leg():
    frame = TableFrame(feet="base_plate")
    assert len(frame.feet) == 4
    for plate, leg in zip(frame.feet, frame.members[4:8]):
        assert isinstance(plate, BasePlate)
    lo_z = min(r.frame.position[2] for r in frame.components)
    assert lo_z == pytest.approx(0.0)  # plates' bottom faces on the floor
    show_dag(frame)


def test_table_frame_legs_run_through_and_shelf_tees():
    frame = TableFrame(width=1200, depth=600, height=750, shelf_height=200)
    kinds = [j.kind for j in frame.junctions]
    assert kinds.count("tee") == 4
    for leg in frame.layout.members[4:8]:
        assert leg.start.kind == "through"
    with pytest.raises(ValueError, match="shelf_height"):
        TableFrame(height=750, shelf_height=740)


def test_ladder_frame_rungs():
    frame = LadderFrame(length=2400, width=1200, rungs=5, section="RHS 80x40x3")
    assert len(frame.members) == 7
    kinds = [j.kind for j in frame.junctions]
    assert kinds.count("tee") == 6  # 3 inner rungs x 2 rails
    with pytest.raises(ValueError, match="at least 2 rungs"):
        LadderFrame(rungs=1)


# ------------------------------------------------------------ standards


def test_standard_profiles_and_designations():
    assert standard_profile("SHS", "40x40x3").designation == "SHS 40x40x3"
    assert standard_profile("IPE", "IPE200").designation == "IPE200"
    assert profile_from_designation("IPE200").size == (100, 200)
    assert profile_from_designation("W8x18").designation == "W8x18"
    assert profile_from_designation("Lumber 2x4").designation == "Lumber 2x4"
    assert profile_from_designation("CHS 48.3x3.2").size == (48.3, 48.3)
    with pytest.raises(UnknownSectionError, match="known"):
        standard_profile("SHS", "41x41x3")
    with pytest.raises(UnknownSectionError, match="cannot read"):
        profile_from_designation("tube 40")


@pytest.mark.parametrize(
    "designation, kg_per_m, tol",
    [
        # catalogue masses (EN 10219-2, EN 10365, EN 10056-1, DIN 1026-1,
        # BS EN 10365 PFC); sections carry their corner / root / toe radii
        ("SHS 40x40x3", 3.30, 0.01),
        ("CHS 48.3x3.2", 3.56, 0.01),
        ("IPE200", 22.4, 0.01),
        ("HEA160", 30.4, 0.01),
        ("L50x50x5", 3.77, 0.01),
        ("UPN100", 10.6, 0.01),
        ("PFC200x90x30", 29.7, 0.01),
    ],
)
def test_mass_per_metre_close_to_catalogue(designation, kg_per_m, tol):
    got = profile_from_designation(designation).mass_per_m()
    assert got == pytest.approx(kg_per_m, rel=tol)


def test_frame_weight_and_total_length():
    frame = Frame(rectangle(600, 400), SquareTube(40, 3), corner="miter")
    assert frame.total_length() == {"SHS 40x40x3": pytest.approx(2160.0)}
    per_m = SquareTube(40, 3).mass_per_m()
    assert frame.weight() == pytest.approx(2.16 * per_m)
    assert frame.weight(density=2700) < frame.weight()


# ---------------------------------------------------------------- stock


def test_stock_plan_first_fit_decreasing():
    pieces = [Piece("SHS 40x40x3", 2500, f"m{i}") for i in range(4)] + [
        Piece("SHS 40x40x3", 900, "short")
    ]
    plan = stock_plan(pieces, stock_length=6000, kerf=3)
    assert plan.count() == 2
    assert plan.bars[0].pieces[0].length == 2500
    assert 0 < plan.utilisation < 1
    assert "2 bars" in plan.table()


def test_stock_plan_separates_profiles_and_rejects_long_pieces():
    plan = stock_plan([Piece("A", 100, "a"), Piece("B", 100, "b")], 6000)
    assert plan.count("A") == 1 and plan.count("B") == 1
    with pytest.raises(PieceTooLongError, match="longer than"):
        stock_plan([Piece("A", 7000, "a")], 6000)


def test_frame_stock_plan():
    frame = RectangularFrame(width=2000, depth=1000)
    plan = frame.stock_plan(stock_length=6000, kerf=3)
    assert plan.count() == 2  # 2 x 2040 + 2 x 1040 = 6160 > 6000
    assert sum(len(b.pieces) for b in plan.bars) == 4


def test_line_member_frame_weight_for_timber():
    from cadbuildr.frames import Lumber, SOFTWOOD_DENSITY

    frame = Frame([Line3D((0, 0, 0), (1000, 0, 0))], Lumber("2x4"))
    assert frame.weight(SOFTWOOD_DENSITY) == pytest.approx(
        1.0 * 38.1 * 88.9 * 1e-6 * 500
    )
