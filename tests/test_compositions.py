"""Cross-library compositions: stdlib fasteners on frame holes and plates.

``cadbuildr-stdlib`` is not a dependency of frames (publish-first: foundation
only), so these tests skip when it is not installed.
"""

import pytest
from cadbuildr.foundation.dag_utils import show_dag
from cadbuildr.frames import BasePlate, Frame, Line3D, SquareTube, TableFrame

stdlib_screws = pytest.importorskip(
    "cadbuildr.stdlib.fasteners.screws_and_bolts.din912_part"
)
DIN912Screw = stdlib_screws.DIN912Screw


def test_screws_connect_into_drilled_member_holes():
    frame = Frame([Line3D((0, 0, 0), (600, 0, 0))], SquareTube(40, 3))
    holes = frame.members[0].drill("top", size="M6", count=3, margin=100)
    screws = []
    for hole in holes:
        screw = DIN912Screw(size="M6", length=12)
        frame.connect(
            screw.interface("head_seat"), frame.members[0].interface(hole.name.value)
        )
        screws.append(screw)
    assert len(screws) == 3
    assert not [i for i in frame.check() if i["code"] in ("coordinates", "loop")]
    show_dag(frame)


def test_anchor_bolts_in_workbench_base_plates():
    bench = TableFrame(feet="base_plate")
    for plate in bench.feet:
        assert isinstance(plate, BasePlate)
        for i in range(4):
            bolt = DIN912Screw(size="M10", length=20)
            bench.connect(bolt.interface("head_seat"), plate.interface(f"hole_{i}"))
    assert not [i for i in bench.check() if i["code"] == "coordinates"]
    show_dag(bench)
