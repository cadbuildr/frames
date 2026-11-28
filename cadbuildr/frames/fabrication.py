"""Fabrication configurables: prepared tube ends, anchor-bolt base plates,
corner gussets, tube end caps and a load-checked beam.

- :class:`PreparedTube` — a hollow-section member whose ends are square,
  mitred, coped (true saddle) or bevelled for a butt weld
  (:mod:`cadbuildr.frames.end_prep`).
- :class:`AnchorBasePlate` — a column base plate with a 2 / 4 / 6 / 8 anchor
  bolt pattern, EN 1090-2 hole clearances, EN 1993-1-8 edge / spacing
  checks and the column-to-plate weld.
- :class:`CornerGusset` — an L-shaped corner (knee) plate with a true inner
  radius.
- :class:`TubeEndCap` — a welded cap for SHS / RHS / CHS ends: an overlapping
  plate or an inset plug flush with the end.
- :class:`SimplySupportedBeam` — a member with a UDL, checked against
  L / 250 and yield in its ``__checks__`` hook (:mod:`cadbuildr.frames.loads`).
"""

from __future__ import annotations

import math
from typing import Literal

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
from cadbuildr.foundation.interfaces import PlaneFace, ScrewHole
from cadbuildr.foundation.library import Num, OneOf, part

from .end_prep import (
    Bevel,
    Cope,
    CopeError,
    EndPrepError,
    Miter,
    cope_extent,
    cope_perimeter,
    cope_template,
    plane_cut_perimeter,
    profile_wall,
)
from .frame import PLATE_COLOR, STEEL_COLOR, FrameMember
from .geometry import Line3D
from .layout import solve_layout
from .profiles import RectTube, RoundBar, RoundTube
from .sections import densify, draw_loop, polygon_properties, rounded_polygon
from .standards import profile_from_designation
from .welds import Weld, butt, fillet

__all__ = [
    "ANCHOR_HOLE_CLEARANCE",
    "AnchorBasePlate",
    "BasePlateError",
    "CornerGusset",
    "HOLLOW_SECTIONS",
    "PreparedTube",
    "SimplySupportedBeam",
    "TubeEndCap",
    "anchor_hole_diameter",
]

HOLLOW_SECTIONS = [
    "CHS 21.3x2",
    "CHS 26.9x2.6",
    "CHS 33.7x2.6",
    "CHS 42.4x3.2",
    "CHS 48.3x3.2",
    "CHS 60.3x3.2",
    "CHS 76.1x3.2",
    "CHS 88.9x4",
    "CHS 114.3x4",
    "SHS 25x25x2",
    "SHS 30x30x3",
    "SHS 40x40x3",
    "SHS 50x50x3",
    "SHS 60x60x4",
    "SHS 80x80x4",
    "SHS 100x100x5",
    "RHS 60x40x3",
    "RHS 80x40x3",
    "RHS 100x50x4",
    "RHS 120x60x4",
]
COPE_HOSTS = HOLLOW_SECTIONS + ["RD 20", "RD 25", "RD 30", "RD 40"]

EndKind = Literal["square", "miter", "cope", "bevel"]
MiterAxis = Literal["v", "u"]

# --------------------------------------------------------------------------- #
# Prepared tube
# --------------------------------------------------------------------------- #


def _miter_cut(cut, which: str, profile, miter: Miter, node) -> None:
    a = math.radians(miter.angle)
    c, s = math.cos(a), math.sin(a)
    sign = -1.0 if which == "start" else 1.0
    n = (sign * c, s, 0.0) if miter.about == "v" else (sign * c, 0.0, s)
    outer = profile.outline()[0]
    ext = max(-(n[1] * y + n[2] * z) / c for y, z in outer)
    cut.kind = "miter" if miter.angle > 0 else "free"
    cut.extension = ext
    cut.angle_deg = miter.angle
    cut.trim_normal = n
    cut.trim_point = node


@part(
    category="Members/End prep",
    name="Prepared tube (cope / mitre / bevel)",
    standard="ISO 9692-1 / ASME B16.25",
    configurations={
        "Handrail post coped onto CHS 48.3": dict(
            section="CHS 42.4x3.2",
            length=900,
            end_a="cope",
            end_b="square",
            cope_host="CHS 48.3x3.2",
        ),
        "45 deg brace coped onto CHS 60.3": dict(
            section="CHS 33.7x2.6",
            length=600,
            end_a="cope",
            end_b="cope",
            cope_host="CHS 60.3x3.2",
            cope_angle=45,
        ),
        "Round tube onto SHS face": dict(
            section="CHS 33.7x2.6",
            length=500,
            end_a="cope",
            end_b="square",
            cope_host="SHS 50x50x3",
        ),
        "Picture-frame rail 45/45": dict(
            section="SHS 40x40x3",
            length=600,
            end_a="miter",
            end_b="miter",
        ),
        "Pipe spool end (ASME B16.25)": dict(
            section="CHS 114.3x4",
            length=1000,
            end_a="bevel",
            end_b="bevel",
            bevel_angle=37.5,
            root_face=1.6,
        ),
    },
)
class PreparedTube(FrameMember):
    """A straight hollow-section member with prepared ends, along +X.

    ``length`` is node to node: from where the end_a cut meets the axis
    (the host axis for a cope, the mitre plane, or the square / bevelled
    end) to the same point at end_b. The stock to cut is
    ``self.cut_length`` (long point to long point, in the cut list).

    - ``square``: plain saw cut.
    - ``miter``: the cut plane turned ``miter_a`` / ``miter_b`` degrees
      about the profile's v (``miter_axis="v"``, picture-frame) or u axis.
    - ``cope``: a true saddle onto ``cope_host`` (round tube / bar) or a
      flat notch onto a square / rectangular host; the host axis crosses the
      node at ``cope_angle`` to the member (90 = square), offset
      ``cope_offset`` along -Z. The host's outer profile extruded along its
      axis is subtracted (exact intersection curve on both walls).
    - ``bevel``: single-V weld prep on a square end, ``bevel_angle`` from
      the end plane, ``root_face`` left square (ISO 9692-1 ref. 1.3: 30
      deg, c <= 2 mm; ASME B16.25: 37.5 deg, 1.6 mm land).

    Bad inputs raise ``CopeError`` (branch wider than the host, a cope that
    would leave a stub), ``BevelError`` (root face >= wall) or
    ``EndPrepError``. ``welds`` lists the joint welds (a fillet all round
    each cope, a butt weld on each bevel). ``cope_template("start")`` is
    the unrolled template of a round-on-round cope.

    Args:
        section: the tube.
        length: node-to-node length along +X.
        end_a: preparation of the start end.
        end_b: preparation of the far end.
        miter_a: mitre angle from square at end_a (degrees).
        miter_b: mitre angle from square at end_b.
        miter_axis: v = picture-frame mitre, u = through the depth.
        cope_host: the section the cope fits onto.
        cope_angle: angle between this tube and the host (90 = square).
        cope_offset: offset of this tube's axis from the host axis.
        bevel_angle: weld-prep bevel angle from the end plane.
        root_face: wall thickness left square at the bevel root.
    """

    def __init__(
        self,
        section: OneOf[HOLLOW_SECTIONS] = "CHS 33.7x2.6",
        length: Num(min=20, max=12000, step=10) = 500,
        end_a: EndKind = "cope",
        end_b: EndKind = "square",
        miter_a: Num(min=0, max=60, step=0.5) = 45,
        miter_b: Num(min=0, max=60, step=0.5) = 45,
        miter_axis: MiterAxis = "v",
        cope_host: OneOf[COPE_HOSTS] = "CHS 48.3x3.2",
        cope_angle: Num(min=15, max=90, step=0.5) = 90,
        cope_offset: Num(min=-100, max=100, step=0.5) = 0,
        bevel_angle: Num(min=10, max=60, step=0.5) = 30,
        root_face: Num(min=0, max=5, step=0.1) = 1.5,
    ):
        profile = profile_from_designation(section)
        if not isinstance(profile, (RoundTube, RectTube)):
            raise EndPrepError(f"PreparedTube needs a hollow section, got {section!r}")
        if not length > 0:
            raise EndPrepError(f"length must be > 0 mm, got {length}")
        layout = solve_layout(
            [Line3D((0.0, 0.0, 0.0), (float(length), 0.0, 0.0))], [profile], "miter", None
        )
        m = layout.members[0]
        host = profile_from_designation(cope_host)
        cope = Cope(host, float(cope_angle), float(cope_offset))
        bevel = Bevel(float(bevel_angle), float(root_face), "ISO 9692-1 / ASME B16.25")
        kinds = {"start": end_a, "end": end_b}
        for which, kind in kinds.items():
            cut = m.cut(which)
            if kind == "miter":
                angle = miter_a if which == "start" else miter_b
                _miter_cut(cut, which, profile, Miter(float(angle), miter_axis), m.node(which))
            elif kind == "cope":
                x0, _ = cope_extent(profile, cope)
                cut.kind = "coped"
                cut.extension = -x0
            elif kind not in ("square", "bevel"):
                raise EndPrepError(f"unknown end preparation {kind!r}")
        if m.cut_length <= 0:
            raise EndPrepError(
                f"length {length:g} mm is too short for these end preparations "
                f"(cut length {m.cut_length:.1f} mm)"
            )
        FrameMember.__init__(self, m, layout, STEEL_COLOR)
        self.profile = profile
        self.length = float(length)
        self.welds: list[Weld] = []
        wall = profile_wall(profile)
        for which, kind in kinds.items():
            if kind == "cope":
                self.cope(which, cope)
                length_w = cope_perimeter(profile, cope)
                t_min = min(wall, profile_wall(host))
                self.welds.append(
                    fillet(f"cope {which}", (self.member_name, host.designation), length_w, t_min, all_around=True)
                )
            elif kind == "bevel":
                self.bevel(which, bevel)
                self.welds.append(
                    butt(
                        f"bevel {which}",
                        (self.member_name,),
                        plane_cut_perimeter(profile, (1.0, 0.0, 0.0)),
                        wall,
                        bevel,
                    )
                )
        self._cope = cope
        self.add_standard_anchors()
        self.name = StringParameter(value=f"{profile.designation} x {m.cut_length:.0f}")

    def cope_template(self, which: str = "start", n: int = 72):
        """Unrolled cope template ``(s, depth)`` of a round tube coped onto a
        round host (see :func:`cadbuildr.frames.end_prep.cope_template`)."""
        cut = self.member_layout.cut(which)
        if cut.cope is None:
            raise CopeError(f"the {which} end is not coped")
        if not isinstance(self.profile, RoundTube) or not isinstance(
            cut.cope.host, (RoundTube, RoundBar)
        ):
            raise CopeError("cope templates are for round tube onto a round host")
        return cope_template(
            self.profile.diameter, cut.cope.host.diameter, cut.cope.angle, cut.cope.offset, n
        )


# --------------------------------------------------------------------------- #
# Anchor-bolt base plate
# --------------------------------------------------------------------------- #

# EN 1090-2:2018 Table 11, nominal clearance (mm) of normal round and
# oversize holes by bolt / anchor diameter.
ANCHOR_HOLE_CLEARANCE: dict[str, dict[int, float]] = {
    "normal": {12: 1, 14: 1, 16: 2, 20: 2, 22: 2, 24: 2, 27: 3, 30: 3, 36: 3},
    "oversize": {12: 3, 14: 4, 16: 4, 20: 4, 22: 4, 24: 6, 27: 8, 30: 8, 36: 8},
}
# ISO 7089 plain washer outside diameters (spanner / washer clearance).
WASHER_OD = {12: 24.0, 16: 30.0, 20: 37.0, 24: 44.0, 30: 56.0}

AnchorSize = Literal["M12", "M16", "M20", "M24", "M30"]
HoleClass = Literal["normal", "oversize"]
BoltPattern = Literal["2", "4", "6", "8"]
COLUMN_SECTIONS = ["none"] + HOLLOW_SECTIONS + ["IPE100", "IPE140", "IPE200", "HEA100", "HEA160", "HEA200"]


class BasePlateError(ValueError):
    """A base plate whose holes or column do not fit it."""


def anchor_hole_diameter(size: str, hole: str = "normal") -> float:
    """Hole diameter ``d0`` for an anchor ``size`` (``"M20"``) and hole class
    (EN 1090-2 Table 11)."""
    d = int(str(size).upper().lstrip("M"))
    try:
        return d + ANCHOR_HOLE_CLEARANCE[hole][d]
    except KeyError:
        raise BasePlateError(f"no EN 1090-2 clearance for {size} {hole} holes") from None


def _bolt_positions(pattern: str, hx: float, hy: float) -> list[tuple[float, float]]:
    if pattern == "2":
        return [(-hx, 0.0), (hx, 0.0)]
    if pattern == "4":
        return [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
    rows = [(x, y) for y in (-hy, hy) for x in (-hx, 0.0, hx)]
    if pattern == "6":
        return rows
    if pattern == "8":
        return rows + [(-hx, 0.0), (hx, 0.0)]
    raise BasePlateError(f"pattern must be 2, 4, 6 or 8, got {pattern!r}")


@part(
    category="Plates",
    name="Anchor-bolt base plate",
    standard="EN 1090-2 / EN 1993-1-8",
    configurations={
        "SHS 100 column, 4 x M16": dict(
            column="SHS 100x100x5", width=250, depth=250, thickness=15, anchor="M16"
        ),
        "HEA 160 column, 4 x M20": dict(
            column="HEA160", width=300, depth=300, thickness=20, anchor="M20", edge=40
        ),
        "Machine foot, 2 x M12": dict(
            column="SHS 60x60x4", width=200, depth=100, thickness=10, anchor="M12",
            pattern="2", edge=30,
        ),
        "Heavy column, 8 x M24 oversize": dict(
            column="HEA200", width=450, depth=400, thickness=25, anchor="M24",
            pattern="8", hole="oversize", edge=55,
        ),
    },
)
class AnchorBasePlate(Part):
    """A column base plate with an anchor-bolt pattern.

    The plate spans z = 0 (grout / floor) to z = ``thickness``, centred on
    the origin. Holes: ``d0`` = anchor + the EN 1090-2:2018 Table 11
    clearance (normal or oversize). Patterns: 2 (on the X centre line), 4
    (corners), 6 (three per long side), 8 (perimeter), each ``edge`` from
    the plate edges.

    ``__checks__`` (warnings): edge distance ``e >= 1.2 d0`` and spacing
    ``p >= 2.2 d0`` (EN 1993-1-8:2005 Table 3.3 minimums), and washer
    clearance from the column (ISO 7089 washer OD / 2 + the fillet leg from
    the column outline). Raises ``BasePlateError`` when a hole runs off the
    plate or the column does not fit.

    Anchors: ``top`` (+Z, ``PlaneFace``: mate a column's ``end_a`` /
    ``end_b``), ``bottom`` (-Z, on the floor), ``hole_0..`` (``ScrewHole``
    group ``anchor``). ``welds``: the column-to-plate fillet all round.

    Args:
        column: the column section it carries ("none" = plate only).
        width: size along X.
        depth: size along Y.
        thickness: plate thickness.
        anchor: anchor bolt size.
        hole: EN 1090-2 hole class.
        pattern: number of anchor bolts.
        edge: hole centre distance from the plate edges.
    """

    def __init__(
        self,
        column: OneOf[COLUMN_SECTIONS] = "SHS 100x100x5",
        width: Num(min=60, max=1000, step=5) = 250,
        depth: Num(min=60, max=1000, step=5) = 250,
        thickness: Num(min=6, max=60, step=1) = 15,
        anchor: AnchorSize = "M16",
        hole: HoleClass = "normal",
        pattern: BoltPattern = "4",
        edge: Num(min=10, max=200, step=1) = 35,
    ):
        d0 = anchor_hole_diameter(anchor, hole)
        hx, hy = width / 2 - edge, depth / 2 - edge
        if edge < d0 / 2 + 1 or hx <= 0 or hy <= 0:
            raise BasePlateError(
                f"{anchor} holes (d0 {d0:g}) at edge {edge:g} mm do not fit a "
                f"{width:g} x {depth:g} plate"
            )
        self.column = None if column == "none" else profile_from_designation(column)
        if self.column is not None:
            cw, ch = self.column.size
            if cw > width or ch > depth:
                raise BasePlateError(
                    f"column {column} ({cw:g} x {ch:g}) is larger than the "
                    f"{width:g} x {depth:g} plate"
                )
        sk = Sketch(self.xy())
        self.add_operation(
            Extrusion(Rectangle.from_center_and_sides(Point(sk, 0, 0), width, depth), thickness)
        )
        top = self.add_anchor(make_anchor("top", (0.0, 0.0, float(thickness))))
        self.add_interface(PlaneFace(name="base"), top)
        bottom = self.add_anchor(make_anchor("bottom", (0.0, 0.0, 0.0), z_down=True))
        self.add_interface(PlaneFace(name="floor"), bottom)
        self.holes = _bolt_positions(pattern, hx, hy)
        for i, (x, y) in enumerate(self.holes):
            hole_sk = Sketch(self.xy())
            self.add_operation(
                Extrusion(Circle(Point(hole_sk, x, y), d0 / 2), thickness + 1, start=-1, cut=True)
            )
            a = self.add_anchor(make_anchor(f"hole_{i}", (x, y, float(thickness))))
            self.add_interface(ScrewHole(size=anchor, depth=float(thickness)), a, group="anchor")
        self.width, self.depth, self.thickness = float(width), float(depth), float(thickness)
        self.anchor_size, self.hole_class, self.d0, self.edge = anchor, hole, d0, float(edge)
        self.pattern = pattern
        self.designation = (
            f"Base plate {width:g}x{depth:g}x{thickness:g}, {pattern} x {anchor} ({hole})"
        )
        self.mass_kg = (width * depth - len(self.holes) * math.pi * d0**2 / 4) * thickness * 7850e-9
        self.welds: list[Weld] = []
        if self.column is not None:
            t_min = min(float(thickness), profile_wall(self.column))
            self.welds.append(
                fillet(
                    "column to base plate",
                    (column, "base plate"),
                    plane_cut_perimeter(self.column, (1.0, 0.0, 0.0)),
                    t_min,
                    all_around=True,
                )
            )
        self.paint(PLATE_COLOR)

    def __checks__(self) -> list:
        from cadbuildr.foundation import issue

        out = []
        d0 = self.d0
        if self.edge < 1.2 * d0:
            out.append(
                issue(
                    "warning",
                    "frames.baseplate.edge",
                    f"edge distance {self.edge:g} mm < 1.2 d0 = {1.2 * d0:.1f} mm "
                    "(EN 1993-1-8 Table 3.3)",
                    fix="increase edge or the plate size",
                )
            )
        xs = sorted({round(x, 6) for x, _ in self.holes})
        ys = sorted({round(y, 6) for _, y in self.holes})
        gaps = [b - a for v in (xs, ys) for a, b in zip(v, v[1:])]
        if gaps and min(gaps) < 2.2 * d0:
            out.append(
                issue(
                    "warning",
                    "frames.baseplate.spacing",
                    f"bolt spacing {min(gaps):.1f} mm < 2.2 d0 = {2.2 * d0:.1f} mm "
                    "(EN 1993-1-8 Table 3.3)",
                    fix="use a larger plate or fewer bolts",
                )
            )
        if self.column is not None:
            size = int(self.anchor_size.lstrip("M"))
            leg = self.welds[0].leg or 0.0
            need = WASHER_OD.get(size, 2 * size) / 2 + leg
            cw, ch = self.column.size
            for x, y in self.holes:
                dx, dy = abs(x) - cw / 2, abs(y) - ch / 2
                clear = max(dx, dy)
                if clear < need:
                    out.append(
                        issue(
                            "warning",
                            "frames.baseplate.washer",
                            f"anchor at ({x:g}, {y:g}) is {clear:.1f} mm from the "
                            f"column; the washer + weld need {need:.1f} mm",
                            fix="move the anchors out (smaller edge, larger plate)",
                        )
                    )
                    break
        return out


# --------------------------------------------------------------------------- #
# Corner gusset and end caps
# --------------------------------------------------------------------------- #


@part(
    category="Plates",
    name="Corner gusset (knee plate)",
    configurations={
        "60 x 60 x 20, t5": dict(leg=60, width=20, thickness=5, inner_radius=8),
        "120 x 120 x 40, t8": dict(leg=120, width=40, thickness=8, inner_radius=15),
    },
)
class CornerGusset(Part):
    """An L-shaped corner plate for a 90-degree frame corner: two strips of
    ``width`` and ``leg`` length along +X and +Y from the outer corner at the
    origin, with a true ``inner_radius`` (no stress-raising sharp inner
    corner) and an optional outer ``corner_radius``. Plate on z = 0 ..
    ``thickness``.

    Anchors: ``corner`` (outer corner, legs along +X / +Y) and ``face``
    (+Z, ``PlaneFace``). ``welds``: a fillet along each leg's outer edge.

    Args:
        leg: leg length from the outer corner.
        width: strip width.
        thickness: plate thickness.
        inner_radius: radius of the inner (concave) corner.
        corner_radius: radius of the outer corner (0 = square).
    """

    def __init__(
        self,
        leg: Num(min=20, max=600, step=5) = 80,
        width: Num(min=8, max=200, step=1) = 25,
        thickness: Num(min=2, max=30, step=1) = 5,
        inner_radius: Num(min=0, max=100, step=0.5) = 10,
        corner_radius: Num(min=0, max=100, step=0.5) = 0,
    ):
        if width >= leg:
            raise ValueError(f"width {width:g} must be smaller than leg {leg:g}")
        if inner_radius > leg - width:
            raise ValueError(f"inner_radius {inner_radius:g} > leg - width = {leg - width:g}")
        if corner_radius > width:
            raise ValueError(f"corner_radius {corner_radius:g} > width {width:g}")
        pts = [(0.0, 0.0), (leg, 0.0), (leg, width), (width, width), (width, leg), (0.0, leg)]
        radii = [corner_radius, 0.0, 0.0, inner_radius, 0.0, 0.0]
        self.loop = rounded_polygon(pts, radii)
        self.add_operation(Extrusion(draw_loop(Sketch(self.xy()), self.loop), thickness))
        self.add_anchor(make_anchor("corner", (0.0, 0.0, 0.0)))
        face = self.add_anchor(make_anchor("face", (0.0, 0.0, float(thickness))))
        self.add_interface(PlaneFace(name="gusset"), face)
        self.leg, self.width, self.thickness = float(leg), float(width), float(thickness)
        self.area = polygon_properties(densify(self.loop)).area
        self.mass_kg = self.area * thickness * 7850e-9
        self.welds = [
            fillet(f"leg {axis}", ("corner gusset",), float(leg), float(thickness), all_around=False)
            for axis in ("x", "y")
        ]
        self.paint(PLATE_COLOR)


CapStyle = Literal["plate", "inset"]


@part(
    category="Plates",
    name="Tube end cap",
    configurations={
        "SHS 40 plate cap": dict(section="SHS 40x40x3", style="plate", thickness=3),
        "SHS 50 inset cap": dict(section="SHS 50x50x3", style="inset", thickness=3),
        "CHS 48.3 inset cap": dict(section="CHS 48.3x3.2", style="inset", thickness=4),
    },
)
class TubeEndCap(Part):
    """A welded cap closing an SHS / RHS / CHS end.

    - ``plate``: the tube's outer outline (with its EN 10219 corner radii),
      ``thickness`` thick, welded on the end with a fillet all round the
      tube's outside. Occupies z = 0 .. thickness.
    - ``inset``: a plug cut to the bore (inner outline less ``clearance``
      all round), welded flush inside the end with a fillet round the bore.
      Occupies z = -thickness .. 0.

    The ``seat`` anchor (z = 0, +Z pointing into the tube, ``PlaneFace``) is
    the face that meets the tube end: ``connect(cap.interface("seat"),
    member.interface("end_b"))`` closes a member end.

    Args:
        section: the tube it closes.
        style: plate on the end, or inset flush in the bore.
        thickness: cap thickness.
        clearance: gap to the bore all round (inset caps).
    """

    def __init__(
        self,
        section: OneOf[HOLLOW_SECTIONS] = "SHS 40x40x3",
        style: CapStyle = "plate",
        thickness: Num(min=1, max=20, step=0.5) = 3,
        clearance: Num(min=0, max=2, step=0.1) = 0.5,
    ):
        prof = profile_from_designation(section)
        if not isinstance(prof, (RoundTube, RectTube)):
            raise ValueError(f"TubeEndCap needs a hollow section, got {section!r}")
        sk = Sketch(self.xy())
        wall = profile_wall(prof)
        if style == "plate":
            shape = prof.outer(sk)
            self.area = prof.outer_area
            weld_len = plane_cut_perimeter(prof, (1.0, 0.0, 0.0))
            self.add_operation(Extrusion(shape, thickness))
        elif style == "inset":
            if isinstance(prof, RoundTube):
                r = prof.diameter / 2 - prof.wall - clearance
                if r <= 0:
                    raise ValueError("clearance leaves no inset cap")
                shape = Circle(Point(sk, 0.0, 0.0), r)
                self.area = math.pi * r * r
                weld_len = 2 * math.pi * (r + clearance)
            else:
                w = prof.width - 2 * prof.wall - 2 * clearance
                h = prof.height - 2 * prof.wall - 2 * clearance
                if min(w, h) <= 0:
                    raise ValueError("clearance leaves no inset cap")
                ri = max(prof.inner_corner_radius - clearance, 0.0)
                pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
                loop = rounded_polygon(pts, [ri] * 4)
                shape = draw_loop(sk, loop)
                self.area = polygon_properties(densify(loop)).area
                bore = prof.outline()[1]
                weld_len = sum(
                    math.dist(bore[i], bore[(i + 1) % len(bore)]) for i in range(len(bore))
                )
            self.add_operation(Extrusion(shape, 0.0, start=-float(thickness)))
        else:
            raise ValueError(f"style must be plate or inset, got {style!r}")
        seat = self.add_anchor(make_anchor("seat", (0.0, 0.0, 0.0), z_down=True))
        self.add_interface(PlaneFace(name="end"), seat)
        self.section, self.style, self.thickness = prof, style, float(thickness)
        self.designation = f"End cap {prof.designation} {style} t{thickness:g}"
        self.mass_kg = self.area * thickness * 7850e-9
        self.welds = [
            fillet("end cap", (self.designation, prof.designation), weld_len,
                   min(float(thickness), wall), all_around=True)
        ]
        self.paint(PLATE_COLOR)


# --------------------------------------------------------------------------- #
# Load-checked beam
# --------------------------------------------------------------------------- #

BEAM_SECTIONS = [
    "SHS 40x40x3",
    "SHS 50x50x3",
    "SHS 60x60x4",
    "SHS 80x80x4",
    "SHS 100x100x5",
    "RHS 80x40x3",
    "RHS 100x50x4",
    "RHS 120x60x4",
    "RHS 160x80x5",
    "CHS 48.3x3.2",
    "CHS 60.3x3.2",
    "L50x50x5",
    "L60x60x6",
    "UPN100",
    "UPN140",
    "PFC150x75x18",
    "PFC200x90x30",
    "IPE100",
    "IPE160",
    "IPE200",
    "HEA160",
]
Grade = Literal["S235", "S275", "S355"]


@part(
    category="Members/Checked",
    name="Simply supported beam (UDL check)",
    standard="EN 1993-1-1",
    configurations={
        "Workbench rail 1500, 2 kN/m": dict(section="SHS 40x40x3", span=1500, udl=2.0),
        "Trailer rail 2400, 3 kN/m": dict(section="RHS 100x50x4", span=2400, udl=3.0),
        "Mezzanine joist 4000, 8 kN/m": dict(section="IPE200", span=4000, udl=8.0),
    },
)
class SimplySupportedBeam(FrameMember):
    """A straight member along +X carrying a uniformly distributed load as
    a simply supported span. Its ``__checks__`` reports mid-span deflection
    ``5 w L^4 / (384 E I)`` against ``span / limit_ratio`` and the bending
    stress ``w L^2 / (8 W_el)`` against ``f_y`` (EN 1993-1-1 6.2.5, gamma_M0
    = 1.0) — an error per failed limit, else an info line with the numbers.
    The load bends the section about its u axis (load along +Z / v).

    Args:
        section: the member's section.
        span: support-to-support span (the member length).
        udl: imposed load in kN/m (self-weight is added).
        grade: steel grade (f_y for t <= 40 mm).
        limit_ratio: deflection limit span / ratio.
    """

    def __init__(
        self,
        section: OneOf[BEAM_SECTIONS] = "SHS 40x40x3",
        span: Num(min=100, max=12000, step=10) = 1500,
        udl: Num(min=0, max=200, step=0.1, unit="kN/m") = 2.0,
        grade: Grade = "S235",
        limit_ratio: Num(min=100, max=1000, step=10, unit=None) = 250,
    ):
        prof = profile_from_designation(section)
        layout = solve_layout(
            [Line3D((0.0, 0.0, 0.0), (float(span), 0.0, 0.0))], [prof], "miter", None
        )
        FrameMember.__init__(self, layout.members[0], layout, STEEL_COLOR)
        self.profile, self.span = prof, float(span)
        self.add_standard_anchors()
        self.apply_udl(float(udl), grade=grade, limit_ratio=float(limit_ratio))
        self.name = StringParameter(value=f"{prof.designation} span {span:g}")

