"""Library configurables: standard members, plates and parametric frames.

Everything here is declared with ``cadbuildr.foundation.library``
(``@part`` / ``@assembly`` + type hints), so it is listed in the library
manifest and a viewer edits it with widgets::

    python -m cadbuildr.foundation.library manifest cadbuildr.frames

- **Members** — one straight cut length of a standard section (the size
  tables of :mod:`cadbuildr.frames.standards`, one configuration per row),
  along +X from ``end_a`` (x = 0) to ``end_b``, with the member anchors and
  interfaces of :meth:`FrameMember.add_standard_anchors` and an optional row
  of bolt holes (``ScrewHole`` interfaces).
- **Plates** — ``BasePlate`` (a foot with four bolt holes, mates onto a
  member end) and ``TriangularGusset``.
- **Frames** — ``RectangularFrame``, ``TableFrame`` (workbench / table base,
  optional shelf and base-plate feet), ``ShelvingFrame``, ``LadderFrame``
  (ladder / trailer chassis) and ``GateFrame``: each is a ``Frame`` built
  from a few dimensions and a section, so ``cut_list()``, ``weight()`` and
  ``stock_plan()`` work on them.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from cadbuildr.foundation import (
    Circle,
    Extrusion,
    Part,
    Point,
    Rectangle,
    Sketch,
    StringParameter,
    make_anchor,
)
from cadbuildr.foundation.holes import clearance_diameter
from cadbuildr.foundation.interfaces import PlaneFace, ScrewHole
from cadbuildr.foundation.library import Num, OneOf, assembly, part

from .connectors import ConnectorRule
from .frame import PLATE_COLOR, STEEL_COLOR, EndCap, Frame, FrameMember, Gusset
from .geometry import Line3D, polyline, rectangle
from .layout import solve_layout
from .profiles import Profile
from .standards import (
    AISC_W,
    ASTM_A500_SQUARE,
    EN10056_ANGLE,
    EN10058_FLAT,
    EN10060_ROUND,
    EN10219_CHS,
    EN10219_RHS,
    EN10219_SHS,
    HEA,
    IPE,
    LUMBER,
    UPN,
    profile_from_designation,
    standard_profile,
)

__all__ = [
    "AngleMember",
    "BasePlate",
    "ChannelMember",
    "FlatBarMember",
    "GateFrame",
    "HEAMember",
    "HSSMember",
    "IPEMember",
    "LadderFrame",
    "LumberMember",
    "RectangularFrame",
    "RectTubeMember",
    "RoundBarMember",
    "RoundTubeMember",
    "SECTIONS",
    "ShelvingFrame",
    "SquareTubeMember",
    "TableFrame",
    "TriangularGusset",
    "WideFlangeMember",
    "standard_member",
]

WOOD_COLOR = "#c8a27a"

HoleSize = Literal["M5", "M6", "M8", "M10", "M12", "M16"]
Face = Literal["top", "bottom", "left", "right"]

# --------------------------------------------------------------------------- #
# Members
# --------------------------------------------------------------------------- #


class _StandardMember(FrameMember):
    """A straight cut length of a standard section along +X (a one-member
    frame layout), with member anchors and an optional hole row."""

    FAMILY: ClassVar[str] = ""
    COLOR: ClassVar[str | None] = STEEL_COLOR

    def _build(
        self,
        size: str,
        length: float,
        hole_count: int = 0,
        hole_size: str = "M8",
        hole_face: str = "top",
        hole_margin: float = 50.0,
    ) -> None:
        if not length > 0:
            raise ValueError(f"length must be > 0 mm, got {length}")
        profile = standard_profile(self.FAMILY, size)
        layout = solve_layout(
            [Line3D((0.0, 0.0, 0.0), (float(length), 0.0, 0.0))],
            [profile],
            "miter",
            None,
        )
        FrameMember.__init__(self, layout.members[0], layout, self.COLOR)
        self.name = StringParameter(value=f"{profile.designation} x {length:g}")
        self.profile = profile
        self.length = float(length)
        self.holes = []
        hole_count = int(hole_count)
        if hole_count > 0:
            if hole_count == 1:
                at = [self.length / 2]
                self.holes = self.drill(hole_face, size=hole_size, at=at)
            else:
                self.holes = self.drill(
                    hole_face, size=hole_size, count=hole_count, margin=hole_margin
                )
        self.add_standard_anchors()


_HOLE_ARGS = """
        hole_count: bolt holes drilled in a row along the member (0 = none).
        hole_size: metric bolt the holes clear (ISO 273 normal fit).
        hole_face: the face the holes are drilled into (top = +Z).
        hole_margin: distance of the first / last hole from the ends."""


def _documented(summary: str, size_doc: str, holes: bool = True):
    """Class decorator (applied before ``@part``): the shared member
    docstring, so the manifest gets a description and per-input help."""

    def wrap(cls):
        cls.__doc__ = (
            f"{summary}\n\n    Args:\n        size: {size_doc}\n"
            "        length: cut length along +X (end_a at x = 0)."
            + (_HOLE_ARGS if holes else "")
        )
        return cls

    return wrap


_LEN = Num(min=10, max=12000, step=10)
_HC = Num(min=0, max=40, step=1, integer=True, unit=None)
_HM = Num(min=5, max=1000, step=5)


@part(category="Members/Tubes", name="Square tube (SHS)", standard="EN 10219-2")
@_documented("A cut length of square hollow section.", "outside size x wall (mm).")
class SquareTubeMember(_StandardMember):
    FAMILY = "SHS"
    TABLE: ClassVar[dict] = EN10219_SHS

    def __init__(
        self,
        size: OneOf[EN10219_SHS] = "40x40x3",
        length: _LEN = 1000,
        hole_count: _HC = 0,
        hole_size: HoleSize = "M8",
        hole_face: Face = "top",
        hole_margin: _HM = 50,
    ):
        self._build(size, length, hole_count, hole_size, hole_face, hole_margin)


@part(category="Members/Tubes", name="Rectangular tube (RHS)", standard="EN 10219-2")
@_documented(
    "A cut length of rectangular hollow section (height along +Z).",
    "height x width x wall (mm).",
)
class RectTubeMember(_StandardMember):
    FAMILY = "RHS"
    TABLE: ClassVar[dict] = EN10219_RHS

    def __init__(
        self,
        size: OneOf[EN10219_RHS] = "80x40x3",
        length: _LEN = 1000,
        hole_count: _HC = 0,
        hole_size: HoleSize = "M8",
        hole_face: Face = "top",
        hole_margin: _HM = 50,
    ):
        self._build(size, length, hole_count, hole_size, hole_face, hole_margin)


@part(category="Members/Tubes", name="Round tube (CHS)", standard="EN 10219-2")
@_documented(
    "A cut length of circular hollow section (its axis is a Shaft interface).",
    "outside diameter x wall (mm).",
)
class RoundTubeMember(_StandardMember):
    FAMILY = "CHS"
    TABLE: ClassVar[dict] = EN10219_CHS

    def __init__(
        self,
        size: OneOf[EN10219_CHS] = "48.3x3.2",
        length: _LEN = 1000,
        hole_count: _HC = 0,
        hole_size: HoleSize = "M8",
        hole_face: Face = "top",
        hole_margin: _HM = 50,
    ):
        self._build(size, length, hole_count, hole_size, hole_face, hole_margin)


@part(category="Members/Tubes", name="Square HSS (inch)", standard="ASTM A500")
@_documented(
    "A cut length of square HSS (AISC design wall = 0.93 x nominal).",
    "HSS designation in inches.",
)
class HSSMember(_StandardMember):
    FAMILY = "HSS"
    TABLE: ClassVar[dict] = ASTM_A500_SQUARE

    def __init__(
        self,
        size: OneOf[ASTM_A500_SQUARE] = "HSS2x2x1/8",
        length: _LEN = 1000,
        hole_count: _HC = 0,
        hole_size: HoleSize = "M8",
        hole_face: Face = "top",
        hole_margin: _HM = 50,
    ):
        self._build(size, length, hole_count, hole_size, hole_face, hole_margin)


@part(category="Members/Sections", name="Equal angle", standard="EN 10056-1")
@_documented(
    "A cut length of equal angle (heel at -Y / -Z).", "leg x leg x thickness (mm)."
)
class AngleMember(_StandardMember):
    FAMILY = "L"
    TABLE: ClassVar[dict] = EN10056_ANGLE

    def __init__(
        self,
        size: OneOf[EN10056_ANGLE] = "L40x40x4",
        length: _LEN = 1000,
        hole_count: _HC = 0,
        hole_size: HoleSize = "M8",
        hole_face: Face = "bottom",
        hole_margin: _HM = 50,
    ):
        self._build(size, length, hole_count, hole_size, hole_face, hole_margin)


@part(category="Members/Sections", name="Channel (UPN)", standard="DIN 1026-1")
@_documented(
    "A cut length of UPN channel (web at -Y, flanges open towards +Y).",
    "UPN designation (web height in mm).",
)
class ChannelMember(_StandardMember):
    FAMILY = "UPN"
    TABLE: ClassVar[dict] = UPN

    def __init__(
        self,
        size: OneOf[UPN] = "UPN100",
        length: _LEN = 1000,
        hole_count: _HC = 0,
        hole_size: HoleSize = "M10",
        hole_face: Face = "right",
        hole_margin: _HM = 50,
    ):
        self._build(size, length, hole_count, hole_size, hole_face, hole_margin)


@part(category="Members/Sections", name="I beam (IPE)", standard="EN 10365")
@_documented("A cut length of IPE beam (web vertical, along +Z).", "IPE designation.")
class IPEMember(_StandardMember):
    FAMILY = "IPE"
    TABLE: ClassVar[dict] = IPE

    def __init__(
        self,
        size: OneOf[IPE] = "IPE200",
        length: _LEN = 2000,
        hole_count: _HC = 0,
        hole_size: HoleSize = "M12",
        hole_face: Face = "top",
        hole_margin: _HM = 50,
    ):
        self._build(size, length, hole_count, hole_size, hole_face, hole_margin)


@part(category="Members/Sections", name="H beam (HEA)", standard="EN 10365")
@_documented("A cut length of HEA wide-flange beam.", "HEA designation.")
class HEAMember(_StandardMember):
    FAMILY = "HEA"
    TABLE: ClassVar[dict] = HEA

    def __init__(
        self,
        size: OneOf[HEA] = "HEA160",
        length: _LEN = 2000,
        hole_count: _HC = 0,
        hole_size: HoleSize = "M12",
        hole_face: Face = "top",
        hole_margin: _HM = 50,
    ):
        self._build(size, length, hole_count, hole_size, hole_face, hole_margin)


@part(category="Members/Sections", name="W shape (inch)", standard="ASTM A6 / AISC")
@_documented("A cut length of AISC W shape.", "W designation (nominal depth x lb/ft).")
class WideFlangeMember(_StandardMember):
    FAMILY = "W"
    TABLE: ClassVar[dict] = AISC_W

    def __init__(
        self,
        size: OneOf[AISC_W] = "W8x18",
        length: _LEN = 2000,
        hole_count: _HC = 0,
        hole_size: HoleSize = "M16",
        hole_face: Face = "top",
        hole_margin: _HM = 50,
    ):
        self._build(size, length, hole_count, hole_size, hole_face, hole_margin)


@part(category="Members/Bars", name="Flat bar", standard="EN 10058")
@_documented(
    "A cut length of flat bar (width along Y, thickness along Z).",
    "width x thickness (mm).",
)
class FlatBarMember(_StandardMember):
    FAMILY = "FL"
    TABLE: ClassVar[dict] = EN10058_FLAT

    def __init__(
        self,
        size: OneOf[EN10058_FLAT] = "50x10",
        length: _LEN = 500,
        hole_count: _HC = 0,
        hole_size: HoleSize = "M8",
        hole_face: Face = "top",
        hole_margin: _HM = 25,
    ):
        self._build(size, length, hole_count, hole_size, hole_face, hole_margin)


@part(category="Members/Bars", name="Round bar", standard="EN 10060")
@_documented(
    "A cut length of round bar (its axis is a Shaft interface).",
    "diameter (mm).",
    holes=False,
)
class RoundBarMember(_StandardMember):
    FAMILY = "RD"
    TABLE: ClassVar[dict] = EN10060_ROUND

    def __init__(
        self,
        size: OneOf[EN10060_ROUND] = "20",
        length: _LEN = 500,
    ):
        self._build(size, length)


@part(category="Members/Bars", name="Dimensional lumber")
@_documented(
    "A cut length of dimensional lumber (actual dressed size, on edge).",
    "nominal size (2x4 is 1.5 x 3.5 in).",
)
class LumberMember(_StandardMember):
    FAMILY = "LUMBER"
    COLOR = WOOD_COLOR
    TABLE: ClassVar[dict] = LUMBER

    def __init__(
        self,
        size: OneOf[LUMBER] = "2x4",
        length: _LEN = 2438,
        hole_count: _HC = 0,
        hole_size: HoleSize = "M10",
        hole_face: Face = "left",
        hole_margin: _HM = 50,
    ):
        self._build(size, length, hole_count, hole_size, hole_face, hole_margin)


_MEMBER_CLASSES = {
    "SHS": SquareTubeMember,
    "RHS": RectTubeMember,
    "CHS": RoundTubeMember,
    "HSS": HSSMember,
    "L": AngleMember,
    "UPN": ChannelMember,
    "IPE": IPEMember,
    "HEA": HEAMember,
    "W": WideFlangeMember,
    "FL": FlatBarMember,
    "RD": RoundBarMember,
    "LUMBER": LumberMember,
}


def standard_member(family: str, size: str, length: float, **holes) -> FrameMember:
    """A standard member by family: ``standard_member("IPE", "IPE200",
    3000)`` -> ``IPEMember``."""
    cls = _MEMBER_CLASSES.get(family.upper())
    if cls is None:
        raise ValueError(
            f"unknown member family {family!r}; known: {', '.join(_MEMBER_CLASSES)}"
        )
    return cls(size=size, length=length, **holes)


# --------------------------------------------------------------------------- #
# Plates
# --------------------------------------------------------------------------- #


@part(
    category="Plates",
    name="Base plate",
    configurations={
        "100x100x8 M10": dict(width=100, depth=100, thickness=8, hole_size="M10"),
        "150x150x10 M12": dict(
            width=150, depth=150, thickness=10, hole_size="M12", hole_inset=20
        ),
    },
)
class BasePlate(Part):
    """A square foot plate with a bolt hole near each corner.

    Anchors: ``top`` (centre of the top face, +Z, a ``PlaneFace``: mate a
    member's ``end_a`` / ``end_b`` here), ``bottom`` (-Z, on the floor) and
    ``hole_0..3`` (``ScrewHole`` interfaces on the top face, group
    ``anchor``). The plate spans z = 0 (floor) to z = thickness.

    Args:
        width: size along X.
        depth: size along Y.
        thickness: plate thickness.
        hole_size: anchor bolt the holes clear (ISO 273 normal fit).
        hole_inset: hole centre distance from the plate edges.
    """

    def __init__(
        self,
        width: Num(min=30, max=600, step=5) = 100,
        depth: Num(min=30, max=600, step=5) = 100,
        thickness: Num(min=2, max=40, step=1) = 8,
        hole_size: HoleSize = "M10",
        hole_inset: Num(min=5, max=200, step=1) = 15,
    ):
        d = clearance_diameter(float(hole_size.lstrip("M")))
        if 2 * hole_inset >= min(width, depth) or hole_inset < d / 2 + 1:
            raise ValueError(
                f"hole_inset {hole_inset:g} mm does not fit {hole_size} holes on a "
                f"{width:g} x {depth:g} mm plate"
            )
        sk = Sketch(self.xy())
        self.add_operation(
            Extrusion(
                Rectangle.from_center_and_sides(Point(sk, 0, 0), width, depth),
                thickness,
            )
        )
        top = self.add_anchor(make_anchor("top", (0.0, 0.0, float(thickness))))
        self.add_interface(PlaneFace(name="base"), top)
        bottom = self.add_anchor(make_anchor("bottom", (0.0, 0.0, 0.0), z_down=True))
        self.add_interface(PlaneFace(name="floor"), bottom)
        hx, hy = width / 2 - hole_inset, depth / 2 - hole_inset
        for i, (x, y) in enumerate(((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))):
            hole_sk = Sketch(self.xy())
            self.add_operation(
                Extrusion(
                    Circle(Point(hole_sk, x, y), d / 2),
                    thickness + 1,
                    start=-1,
                    cut=True,
                )
            )
            a = self.add_anchor(make_anchor(f"hole_{i}", (x, y, float(thickness))))
            self.add_interface(
                ScrewHole(size=hole_size, depth=float(thickness)), a, group="anchor"
            )
        self.width, self.depth, self.thickness = width, depth, thickness
        self.hole_size = hole_size
        self.paint(PLATE_COLOR)


@part(category="Plates", name="Triangular gusset")
class TriangularGusset(Part):
    """A right-angle triangular gusset plate (free-standing; ``Frame``
    places its own gussets in corners with ``Gusset(at=...)``).

    Anchors: ``corner`` (the right-angle corner, legs along +X / +Y, plate
    on z = 0..thickness) and ``face`` (+Z, a ``PlaneFace``).

    Args:
        size: leg length along X and Y.
        thickness: plate thickness.
        chamfer: corner clip at the right angle (weld clearance); 0 = none.
    """

    def __init__(
        self,
        size: Num(min=20, max=500, step=5) = 80,
        thickness: Num(min=2, max=30, step=1) = 6,
        chamfer: Num(min=0, max=100, step=1) = 10,
    ):
        if chamfer >= size / 2:
            raise ValueError(f"chamfer {chamfer:g} is too big for a {size:g} gusset")
        pencil = Sketch(self.xy()).pencil
        if chamfer > 0:
            pencil.move_to(chamfer, 0.0)
            pencil.line_to(size, 0.0)
            pencil.line_to(0.0, size)
            pencil.line_to(0.0, chamfer)
        else:
            pencil.move_to(0.0, 0.0)
            pencil.line_to(size, 0.0)
            pencil.line_to(0.0, size)
        self.add_operation(Extrusion(pencil.close(), thickness))
        self.add_anchor(make_anchor("corner", (0.0, 0.0, 0.0)))
        face = self.add_anchor(make_anchor("face", (0.0, 0.0, float(thickness))))
        self.add_interface(PlaneFace(name="gusset"), face)
        self.size, self.thickness = size, thickness
        self.paint(PLATE_COLOR)


# --------------------------------------------------------------------------- #
# Parametric frames
# --------------------------------------------------------------------------- #

# Sections offered by the parametric frames (any designation
# ``profile_from_designation`` reads works from code).
SECTIONS = [
    "SHS 20x20x2",
    "SHS 25x25x2",
    "SHS 30x30x3",
    "SHS 40x40x3",
    "SHS 50x50x3",
    "SHS 60x60x4",
    "RHS 50x30x3",
    "RHS 60x40x3",
    "RHS 80x40x3",
    "RHS 100x50x4",
    "CHS 26.9x2",
    "CHS 33.7x2.6",
    "CHS 42.4x3.2",
    "CHS 48.3x3.2",
    "L40x40x4",
    "L50x50x5",
    "UPN100",
    "IPE100",
    "HSS1-1/2x1-1/2x1/8",
    "HSS2x2x1/8",
    "Lumber 2x4",
    "Lumber 4x4",
]
Corner = Literal["miter", "butt"]


def _section(designation: str) -> Profile:
    return profile_from_designation(designation)


def _color(designation: str) -> str:
    return WOOD_COLOR if designation.lower().startswith("lumber") else STEEL_COLOR


@assembly(
    category="Frames",
    name="Rectangular frame",
    configurations={
        "Picture-rail 600x400": dict(width=600, depth=400, section="SHS 25x25x2"),
        "Machine base 1200x800": dict(
            width=1200, depth=800, section="RHS 80x40x3", gussets=True
        ),
    },
)
class RectangularFrame(Frame):
    """A flat rectangular frame in the XY plane, centred on the origin
    (dimensions are the members' centre lines).

    Args:
        width: centre-line size along X.
        depth: centre-line size along Y.
        section: the profile of every member.
        corner: miter (picture-frame) or butt (the long sides run through).
        gussets: a triangular gusset in every corner.
        gusset_size: gusset leg length from the inner corner.
    """

    def __init__(
        self,
        width: Num(min=50, max=12000, step=10) = 600,
        depth: Num(min=50, max=12000, step=10) = 400,
        section: OneOf[SECTIONS] = "SHS 40x40x3",
        corner: Corner = "miter",
        gussets: bool = False,
        gusset_size: Num(min=10, max=500, step=5) = 60,
    ):
        prof = _section(section)
        plates = []
        if gussets:
            plates = [
                Gusset(at=(x, y, 0), size=gusset_size, thickness=5)
                for x in (-width / 2, width / 2)
                for y in (-depth / 2, depth / 2)
            ]
        super().__init__(
            rectangle(width, depth),
            prof,
            corner=corner,
            gussets=plates,
            color=_color(section),
        )


Feet = Literal["none", "end_cap", "base_plate"]


def _attach_feet(frame: Frame, feet: str, leg_indices, plate_size: float) -> None:
    """End caps or ``BasePlate`` feet on the bottom ends of the legs."""
    frame.feet = []
    if feet != "base_plate":
        return
    for i in leg_indices:
        leg = frame.members[i]
        plate = BasePlate(
            width=plate_size, depth=plate_size, thickness=8, hole_size="M10"
        )
        plate.name = StringParameter(value=f"foot_{len(frame.feet) + 1}")
        frame.connect(plate.interface("top"), leg.interface("end_b"))
        frame.feet.append(plate)


@assembly(
    category="Frames",
    name="Table / workbench frame",
    configurations={
        "Workbench 1500x700": dict(
            width=1500,
            depth=700,
            height=900,
            section="SHS 40x40x3",
            shelf_height=150,
            feet="base_plate",
        ),
        "Coffee table 1000x500": dict(
            width=1000, depth=500, height=420, section="SHS 25x25x2"
        ),
        "Timber bench 1200x400": dict(
            width=1200, depth=400, height=450, section="Lumber 4x4", feet="none"
        ),
    },
)
class TableFrame(Frame):
    """A table or workbench base: a top rectangle on four legs, an optional
    shelf rectangle between the legs, capped or base-plated feet.

    The frame sits on z = 0 (the floor, under the feet) and its top face is
    at ``height``; width / depth are the leg centre lines.

    Args:
        width: leg centre-to-centre along X.
        depth: leg centre-to-centre along Y.
        height: floor to the top face of the top rails.
        section: the profile of every member.
        shelf_height: height of a lower shelf rectangle (centre line); 0 = none.
        corner: how the top rails meet the legs (the legs run through).
        feet: end caps, ``BasePlate`` feet (bolt-down) or open tube ends.
    """

    def __init__(
        self,
        width: Num(min=200, max=6000, step=10) = 1200,
        depth: Num(min=200, max=3000, step=10) = 600,
        height: Num(min=200, max=2000, step=10) = 750,
        section: OneOf[SECTIONS] = "SHS 40x40x3",
        shelf_height: Num(min=0, max=1500, step=10) = 0,
        feet: Feet = "end_cap",
        plate_size: Num(min=40, max=300, step=5) = 100,
    ):
        prof = _section(section)
        _, v = prof.size
        foot = 8.0 if feet == "base_plate" else (3.0 if feet == "end_cap" else 0.0)
        top_z = height - v / 2
        bottom_z = foot
        if shelf_height and not bottom_z + v < shelf_height < top_z - v:
            raise ValueError(
                f"shelf_height {shelf_height:g} must lie between the feet and the "
                f"top rails ({bottom_z + v:g} .. {top_z - v:g} mm)"
            )
        corners = [
            (-width / 2, -depth / 2),
            (width / 2, -depth / 2),
            (width / 2, depth / 2),
            (-width / 2, depth / 2),
        ]
        top = polyline([(x, y, top_z) for x, y in corners], closed=True)
        legs = [Line3D((x, y, top_z), (x, y, bottom_z)) for x, y in corners]
        skeleton = top + legs
        if shelf_height:
            skeleton += polyline([(x, y, shelf_height) for x, y in corners], True)
        legs_through = _LegsThrough()
        super().__init__(
            skeleton,
            prof,
            corner="butt",
            end_caps=EndCap(3.0) if feet == "end_cap" else None,
            color=_color(section),
            connector=legs_through,
        )
        self.height = height
        _attach_feet(self, feet, range(4, 8), plate_size)


class _LegsThrough(ConnectorRule):
    """Connector rule adding no hardware: vertical members (legs / posts)
    run through the corners, so rails are cut to fit between them."""

    def choose_through(self, node, ends):
        for i, e in enumerate(ends):
            if abs(abs(e.into[2]) - 1.0) < 1e-9:
                return i
        return None


@assembly(
    category="Frames",
    name="Shelving frame",
    configurations={
        "Garage shelf 1000x400x1800": dict(
            width=1000, depth=400, height=1800, levels=5, section="L40x40x4"
        ),
    },
)
class ShelvingFrame(Frame):
    """A shelving unit: four posts and a rail rectangle per level (rails butt
    onto the posts; the top level sits on the post tops).

    Args:
        width: post centre-to-centre along X.
        depth: post centre-to-centre along Y.
        height: floor to the top level (centre line).
        levels: number of shelf levels, evenly spaced from ``bottom`` up.
        bottom: height of the lowest level (centre line).
        section: the profile of every member.
    """

    def __init__(
        self,
        width: Num(min=200, max=4000, step=10) = 900,
        depth: Num(min=150, max=1500, step=10) = 400,
        height: Num(min=300, max=3000, step=10) = 1800,
        levels: Num(min=2, max=12, step=1, integer=True, unit=None) = 4,
        bottom: Num(min=50, max=1000, step=10) = 150,
        section: OneOf[SECTIONS] = "SHS 30x30x3",
    ):
        levels = int(levels)
        if not 0 < bottom < height:
            raise ValueError("bottom must be between 0 and height")
        prof = _section(section)
        corners = [
            (-width / 2, -depth / 2),
            (width / 2, -depth / 2),
            (width / 2, depth / 2),
            (-width / 2, depth / 2),
        ]
        posts = [Line3D((x, y, height), (x, y, 0.0)) for x, y in corners]
        step = (height - bottom) / (levels - 1)
        skeleton = list(posts)
        for k in range(levels):
            z = bottom + k * step
            skeleton += polyline([(x, y, z) for x, y in corners], closed=True)
        super().__init__(
            skeleton,
            prof,
            corner="butt",
            end_caps=EndCap(3.0),
            color=_color(section),
            connector=_LegsThrough(),
        )
        self.level_heights = [bottom + k * step for k in range(levels)]


@assembly(
    category="Frames",
    name="Ladder frame / chassis",
    configurations={
        "Utility trailer 2400x1200": dict(
            length=2400, width=1200, rungs=5, section="RHS 100x50x4"
        ),
        "Go-kart base 1400x700": dict(
            length=1400, width=700, rungs=4, section="CHS 33.7x2.6"
        ),
    },
)
class LadderFrame(Frame):
    """Two long rails along X with cross members between them — a ladder, a
    trailer chassis or a cart base. The rails run through, cross members
    are butted between them (end rungs at the rail ends).

    Args:
        length: rail length along X (centre line).
        width: rail centre-to-centre along Y.
        rungs: cross members, evenly spaced, including both ends.
        section: rail profile.
        rung_section: cross member profile ("same" = the rail section).
    """

    def __init__(
        self,
        length: Num(min=200, max=12000, step=10) = 2400,
        width: Num(min=100, max=3000, step=10) = 1200,
        rungs: Num(min=2, max=40, step=1, integer=True, unit=None) = 5,
        section: OneOf[SECTIONS] = "RHS 80x40x3",
        rung_section: OneOf[["same"] + SECTIONS] = "same",
    ):
        rungs = int(rungs)
        if rungs < 2:
            raise ValueError("a ladder frame needs at least 2 rungs")
        rail = _section(section)
        rung = rail if rung_section == "same" else _section(rung_section)
        x0, y0 = -length / 2, width / 2
        rails = [
            Line3D((x0, -y0, 0.0), (-x0, -y0, 0.0)),
            Line3D((x0, y0, 0.0), (-x0, y0, 0.0)),
        ]
        step = length / (rungs - 1)
        cross = [
            Line3D((x0 + k * step, -y0, 0.0), (x0 + k * step, y0, 0.0))
            for k in range(rungs)
        ]
        if width <= max(rail.size):
            raise ValueError(f"width {width:g} is narrower than the rails")
        super().__init__(
            rails + cross,
            [rail, rail] + [rung] * rungs,
            corner="butt",
            end_caps=EndCap(3.0),
            color=_color(section),
        )


GateInfill = Literal["none", "pickets", "brace"]


@assembly(
    category="Frames",
    name="Gate frame",
    configurations={
        "Garden gate 1000x1200": dict(
            width=1000, height=1200, infill="pickets", pickets=9
        ),
        "Braced gate 1200x1000": dict(width=1200, height=1000, infill="brace"),
    },
)
class GateFrame(Frame):
    """A gate leaf in the XZ plane: a mitered rectangle (centre lines,
    bottom-left at the origin) with vertical pickets or a diagonal brace.

    Args:
        width: centre-line width along X.
        height: centre-line height along Z.
        section: perimeter profile.
        infill: vertical pickets, a diagonal brace (hinge side bottom to latch
            side top) or nothing.
        pickets: number of pickets (``infill="pickets"``).
        picket_section: picket / brace profile.
    """

    def __init__(
        self,
        width: Num(min=300, max=6000, step=10) = 1000,
        height: Num(min=300, max=3000, step=10) = 1200,
        section: OneOf[SECTIONS] = "SHS 40x40x3",
        infill: GateInfill = "pickets",
        pickets: Num(min=1, max=60, step=1, integer=True, unit=None) = 9,
        picket_section: OneOf[SECTIONS] = "SHS 20x20x2",
    ):
        frame_p = _section(section)
        infill_p = _section(picket_section)
        pts = [
            (0.0, 0.0, 0.0),
            (width, 0.0, 0.0),
            (width, 0.0, height),
            (0.0, 0.0, height),
        ]
        skeleton = polyline(pts, closed=True)
        profiles = [frame_p] * 4
        if infill == "pickets":
            n = int(pickets)
            gap = width / (n + 1)
            skeleton += [
                Line3D((gap * (k + 1), 0.0, 0.0), (gap * (k + 1), 0.0, height))
                for k in range(n)
            ]
            profiles += [infill_p] * n
        elif infill == "brace":
            a = max(frame_p.size)
            skeleton.append(Line3D((a, 0.0, 0.0), (width - a, 0.0, height)))
            profiles.append(infill_p)
        super().__init__(
            skeleton,
            profiles,
            corner="miter",
            up=(0.0, -1.0, 0.0),
            color=_color(section),
        )
