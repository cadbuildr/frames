"""Frame (weldment) assembly: one Part per member, plus gusset plates and
end caps, all built from plain foundation operations (Extrusion, Lathe and
cut Extrusions on trim planes)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np
from cadbuildr.foundation import (
    Assembly,
    Axis,
    BoolParameter,
    Circle,
    Extrusion,
    Lathe,
    Line,
    Part,
    Plane,
    Point,
    Rectangle,
    RigidJoint,
    Sketch,
    StringParameter,
    make_anchor,
)
from cadbuildr.foundation import Frame as CoordinateFrame
from cadbuildr.foundation.holes import clearance_diameter
from cadbuildr.foundation.interfaces import PlaneFace, ScrewHole, Shaft
from cadbuildr.foundation.math_utils import (
    quaternion_multiply,
    rotation_matrix_to_quaternion,
)

from .connectors import (
    Connection,
    ConnectorLike,
    Placed,
    as_rule,
    member_index,
)
from .cut_list import (
    CutListItem,
    SawAngle,
    cut_list,
    end_prep_label,
    end_saw_angle,
    format_cut_list,
)
from .end_prep import (
    BEVEL_ISO_9692_1_V,
    Bevel,
    BevelError,
    Cope,
    CopeError,
    check_cope_fits,
    cope_perimeter,
    plane_cut_perimeter,
    profile_wall,
)
from .loads import DEFLECTION_LIMIT_RATIO, SpanCheck, simple_span_udl
from .welds import Weld, butt, fillet, format_welds, weld_summary
from .geometry import (
    Arc3D,
    Basis,
    Segment,
    Vec,
    add,
    cross,
    dot,
    rotate,
    scale,
    sub,
    to_local,
    unit,
    vec,
)
from .layout import (
    CornerType,
    EndCut,
    FrameLayout,
    GussetLayout,
    Junction,
    MemberLayout,
    solve_layout,
)
from .profiles import Lumber, Profile, RectTube, RoundBar, RoundTube
from .stock import STOCK_LENGTH_6M, Piece, StockPlan, stock_plan

STEEL_COLOR = "#9aa3ad"
PLATE_COLOR = "#6b7480"

# Material densities in kg/m^3 for ``Frame.weight``.
STEEL_DENSITY = 7850.0
STAINLESS_DENSITY = 8000.0
ALUMINIUM_DENSITY = 2700.0
SOFTWOOD_DENSITY = 500.0

# Long faces of a straight member: name -> outward (u, v) direction in the
# cross-section (u = local +Y, v = local +Z, the frame's ``up`` side).
MEMBER_FACES: dict[str, tuple[float, float]] = {
    "top": (0.0, 1.0),
    "bottom": (0.0, -1.0),
    "left": (1.0, 0.0),
    "right": (-1.0, 0.0),
}

# 180 degrees about X: the face-to-face flip of a mate.
_FLIP_Q = [0.0, 1.0, 0.0, 0.0]

# The inner (hollow) revolve of a bent member starts this far before the arc
# so it never shares a face with the outer revolve.
_INNER_REVOLVE_OVERLAP_RAD = math.radians(0.5)


def _tf(origin: Vec, basis: Basis) -> list[list[float]]:
    x, y, z = basis
    return [
        [x[0], y[0], z[0], origin[0]],
        [x[1], y[1], z[1], origin[1]],
        [x[2], y[2], z[2], origin[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def basis_transform(origin: Sequence[float], basis: Basis) -> list[list[float]]:
    """4x4 placement matrix of a local frame at ``origin`` whose x / y / z axes
    are the world directions in ``basis`` (e.g. a member end:
    ``basis_transform(end.member.node(end.which), end.basis)``)."""
    return _tf(vec(origin), basis)


def euler_deg(basis: Basis) -> tuple[float, float, float]:
    """``(rx, ry, rz)`` in degrees about the fixed X, Y, Z axes (the
    ``rot_deg`` of ``Assembly.ground`` / ``add_component``) of the rotation
    whose columns are ``basis``."""
    x, y, z = basis
    r = [[x[0], y[0], z[0]], [x[1], y[1], z[1]], [x[2], y[2], z[2]]]
    sy = max(-1.0, min(1.0, -r[2][0]))
    ry = math.asin(sy)
    if abs(sy) < 1.0 - 1e-9:
        rx = math.atan2(r[2][1], r[2][2])
        rz = math.atan2(r[1][0], r[0][0])
    else:  # gimbal lock: fold the X rotation into Z
        rx = 0.0
        rz = math.atan2(-r[0][1], r[1][1])
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))


def _flipped(anchor) -> tuple[list[float], list[float]]:
    """Position and quaternion of ``anchor`` turned face to face (180 deg
    about its X): the pose a mating part's anchor has in the same coordinates."""
    q = quaternion_multiply(list(anchor.frame.quaternion), _FLIP_Q)
    return [float(c) for c in anchor.frame.position], q


def _any_perp(z: Vec) -> Vec:
    trial = (1.0, 0.0, 0.0) if abs(z[0]) < 0.9 else (0.0, 1.0, 0.0)
    return unit(sub(trial, scale(z, dot(trial, z))))


class _LocalPart(Part):
    """A Part that can sketch on arbitrary planes given in its own
    coordinates."""

    def _plane(self, origin: Vec, x: Vec, z: Vec, name: str) -> Plane:
        x, z = unit(x), unit(z)
        y = cross(z, x)
        rot = np.array([x, y, z], dtype=float).T
        frame = CoordinateFrame(
            top_frame=self.frame,
            name=StringParameter(value=f"frame_{name}"),
            display=BoolParameter(value=False),
            position=[float(c) for c in origin],
            quaternion=[float(c) for c in rotation_matrix_to_quaternion(rot)],
        )
        return Plane(
            frame=frame,
            name=StringParameter(value=name),
            display=BoolParameter(value=False),
        )


class FrameMember(_LocalPart):
    """One cut length of profile. Local coordinates: the member starts at the
    origin and runs along +X (the skeleton segment), the profile's u / v axes
    are +Y / +Z."""

    def __init__(
        self, member: MemberLayout, layout: FrameLayout, color: str | None = STEEL_COLOR
    ):
        super().__init__()
        self.name = StringParameter(value=member.name)
        self.member_name = member.name
        self.profile_designation = member.profile.designation
        self.cut_length = member.cut_length
        self.n_planes = 0
        self.member_layout = member
        self.frame_layout = layout
        if isinstance(member.segment, Arc3D):
            self._build_bent()
        else:
            self._build_straight()
        for which in ("start", "end"):
            self._apply_trim(which)
        if color is not None:
            self.paint(color)

    # ------------------------------------------------------------ public API
    @property
    def length_range(self) -> tuple[float, float]:
        """Local x range of the member's material: ``(-start extension,
        centreline length + end extension)``."""
        m = self.member_layout
        return (-m.start.extension, m.centerline_length + m.end.extension)

    def local_point(self, p: Sequence[float]) -> Vec:
        """A frame (world) point in this member's local coordinates."""
        return self._local_point(vec(p))

    def local_dir(self, v: Sequence[float]) -> Vec:
        """A frame (world) direction in this member's local coordinates."""
        return self._local_dir(vec(v))

    def plane(self, origin: Sequence[float], x: Sequence[float], z: Sequence[float]):
        """A sketch plane in local coordinates (origin, x axis, normal z) —
        for machining requested by a connector."""
        return self._new_plane(vec(origin), vec(x), vec(z))

    # ------------------------------------------------------ anchors / mating
    def has_anchor(self, name: str) -> bool:
        return any(a.name.value == name for a in self.anchors)

    def _ensure_anchor(self, name: str, position: Sequence[float], **orient):
        if self.has_anchor(name):
            return self.anchor(name)
        return self.add_anchor(
            make_anchor(name, tuple(float(c) for c in position), **orient)
        )

    def _ensure_interface(self, spec, name: str) -> None:
        if any(i.anchor.name.value == name for i in (self.interfaces or [])):
            return
        self.add_interface(spec, name)

    def add_standard_anchors(self) -> None:
        """Anchors (and interfaces) every member carries, in local coordinates
        (the member runs along +X from its start node at the origin):

        - ``node_a`` / ``node_b``: the skeleton nodes, axes = the member's
          orientation there (x along the member, y / z = profile u / v);
          the frame places the member by ``node_a``.
        - ``end_a`` / ``end_b``: the material ends (long point), +Z out of
          the member — ``PlaneFace`` interfaces (end caps, base plates and
          feet mate here).
        - ``axis``: at ``end_a``, +Z along the member — a ``Shaft`` interface
          for round tube / bar (clamps, bushings, wheels slide on it).
        - straight members: ``face_top`` / ``face_bottom`` / ``face_left`` /
          ``face_right`` on the outside of the profile at ``end_a``, +Z out
          of the face, +X along the member — ``PlaneFace`` interfaces;
          ``part.anchor("face_top").offset([d, 0, 0])`` is a point ``d`` mm
          along that face.

        Anchors a connector's ``prepare_member`` already added under the same
        name (e.g. ``cadbuildr-tslot``'s ``end_a``) are kept. Called by
        ``Frame`` for every member; idempotent.
        """
        m = self.member_layout
        x0, x1 = self.length_range
        bent = isinstance(m.segment, Arc3D)
        self._ensure_anchor("node_a", (0.0, 0.0, 0.0))
        node_b = self._local_point(m.segment.end)
        ex, _, ez = (self._local_dir(a) for a in m.end_basis)
        self._ensure_anchor("node_b", node_b, z_axis=ez, x_axis=ex)
        self._ensure_anchor("end_a", (x0, 0.0, 0.0), z_axis=(-1.0, 0.0, 0.0))
        if bent:
            end_b = add(node_b, scale(ex, m.end.extension))
            self._ensure_anchor("end_b", end_b, z_axis=ex)
        else:
            self._ensure_anchor("end_b", (x1, 0.0, 0.0), z_axis=(1.0, 0.0, 0.0))
        self._ensure_anchor("axis", (x0, 0.0, 0.0), z_axis=(1.0, 0.0, 0.0))
        self._ensure_interface(PlaneFace(name="end"), "end_a")
        self._ensure_interface(PlaneFace(name="end"), "end_b")
        if isinstance(m.profile, (RoundTube, RoundBar)):
            self._ensure_interface(Shaft(d=m.profile.diameter), "axis")
        if bent:
            return
        for face, (du, dv) in MEMBER_FACES.items():
            off = m.profile.support(du, dv)
            name = f"face_{face}"
            self._ensure_anchor(
                name,
                (x0, du * off, dv * off),
                z_axis=(0.0, du, dv),
                x_axis=(1.0, 0.0, 0.0),
            )
            self._ensure_interface(PlaneFace(name="face"), name)

    def drill(
        self,
        face: str = "top",
        size: str | None = "M8",
        diameter: float | None = None,
        at: Sequence[float] = (),
        count: int | None = None,
        pitch: float | None = None,
        margin: float | None = None,
        offset: float = 0.0,
        through: bool = False,
        fit: str = "NORMAL",
        name: str = "hole",
    ) -> list:
        """Drill a row of holes into one long face of a straight member and
        return their anchors (``<name>_<i>``, +Z out of the face, each with a
        ``ScrewHole`` interface so a screw / bolt mates onto it).

        Args:
            face: ``"top"``, ``"bottom"``, ``"left"`` or ``"right"``.
            size: metric screw (``"M8"``): the hole is its ISO 273 clearance
                diameter (``fit`` close / normal / loose).
            diameter: an explicit hole diameter in mm instead of ``size``.
            at: hole positions in mm from ``end_a`` (the start of the
                material). Or give ``count`` with ``pitch`` (centred on the
                member) or with ``margin`` (first / last hole that far from
                the ends, evenly spaced).
            offset: shift across the face (along the profile's other axis).
            through: drill both walls (through the whole section); default
                only the face's wall (to the centre line).
            name: anchor name stem.
        """
        m = self.member_layout
        if isinstance(m.segment, Arc3D):
            raise ValueError(f"{m.name}: holes on bent members are not supported")
        if face not in MEMBER_FACES:
            raise ValueError(
                f"face must be one of {', '.join(MEMBER_FACES)}, got {face!r}"
            )
        x0, x1 = self.length_range
        length = x1 - x0
        positions = [float(a) for a in at]
        if count is not None:
            if positions:
                raise ValueError("drill: give either at= or count=, not both")
            if count < 1:
                raise ValueError(f"drill: count must be >= 1, got {count}")
            if (pitch is None) == (margin is None):
                raise ValueError("drill: count= needs exactly one of pitch= or margin=")
            if pitch is not None:
                start = (length - (count - 1) * pitch) / 2
                positions = [start + i * pitch for i in range(count)]
            else:
                span = length - 2 * float(margin)  # type: ignore[arg-type]
                step = span / (count - 1) if count > 1 else 0.0
                positions = [
                    (float(margin) + i * step) if count > 1 else length / 2  # type: ignore[arg-type]
                    for i in range(count)
                ]
        if not positions:
            raise ValueError("drill: no hole positions (give at= or count=)")
        if diameter is None:
            if size is None:
                raise ValueError("drill: give size= (e.g. 'M8') or diameter=")
            nominal = float(str(size).upper().lstrip("M"))
            diameter = clearance_diameter(nominal, fit)
        r = diameter / 2.0
        du, dv = MEMBER_FACES[face]
        face_off = m.profile.support(du, dv)
        across_u, across_v = (dv, du)  # the face's in-plane axis across the member
        half_across = m.profile.support(across_u, across_v)
        if abs(offset) + r > half_across + 1e-9:
            raise ValueError(
                f"{m.name}: a {diameter:g} mm hole at offset {offset:g} does not "
                f"fit on the {face} face ({2 * half_across:g} mm wide)"
            )
        for a in positions:
            if a - r < -1e-9 or a + r > length + 1e-9:
                raise ValueError(
                    f"{m.name}: hole at {a:g} mm runs off the member "
                    f"({length:g} mm long)"
                )
        back = m.profile.support(-du, -dv)
        depth = face_off + back + 1.0 if through else face_off
        wall = getattr(m.profile, "wall", None) or getattr(m.profile, "thickness", None)
        grip = face_off + back if through else (wall or face_off)
        normal = (0.0, du, dv)
        across = (0.0, across_u, across_v)
        anchors = []
        for i, a in enumerate(positions):
            p = (
                x0 + a,
                du * face_off + across[1] * offset,
                dv * face_off + across[2] * offset,
            )
            sk = Sketch(self._new_plane(p, (1.0, 0.0, 0.0), normal))
            self.add_operation(
                Extrusion(Circle(sk.origin, r), 1.0, start=-depth, cut=True)
            )
            anchor = self.add_anchor(
                make_anchor(f"{name}_{i}", p, z_axis=normal, x_axis=(1.0, 0.0, 0.0))
            )
            if size is not None:
                self.add_interface(
                    ScrewHole(size=str(size).upper(), depth=grip), anchor, group=name
                )
            anchors.append(anchor)
        return anchors

    # ------------------------------------------------------- end preparation
    def _end_frame(self, which: str) -> tuple[Vec, Vec, Vec]:
        """Node, into-direction and lateral (+Y side) axis of end ``which``
        in local coordinates (straight members)."""
        if which not in ("start", "end"):
            raise ValueError(f"which must be 'start' or 'end', got {which!r}")
        if isinstance(self.member_layout.segment, Arc3D):
            raise CopeError(
                f"{self.member_layout.name}: end preparation on bent members is "
                "not supported"
            )
        if which == "start":
            return (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
        length = self.member_layout.centerline_length
        return (length, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0)

    def cope(self, which: str, cope: Cope) -> None:
        """Cope (saddle-cut) end ``which`` onto ``cope.host``: subtract the
        host's outer profile, extruded along the host axis, from this
        member — the exact saddle on both walls (see
        :mod:`cadbuildr.frames.end_prep`). The host axis passes through the
        end's node at ``cope.angle`` to this member (in the local XY plane)
        and ``cope.offset`` below its axis (local -Z). The member's material
        must reach the host (``PreparedTube`` sets the end extension from
        :func:`~cadbuildr.frames.end_prep.cope_extent`)."""
        node, d, y = self._end_frame(which)
        m = self.member_layout
        check_cope_fits(m.profile, cope)
        a = math.radians(cope.angle)
        h = add(scale(d, math.cos(a)), scale(y, math.sin(a)))
        origin = add(node, (0.0, 0.0, -float(cope.offset)))
        plane = self._new_plane(origin, (0.0, 0.0, 1.0), h)
        span = 4.0 * (self._reach() + max(cope.host.size)) / math.sin(a) + 50.0
        self.add_operation(
            Extrusion(cope.host.outer(Sketch(plane)), span, start=-span, cut=True)
        )
        cut = m.cut(which)
        cut.kind = "coped"
        cut.cope = cope

    def bevel(self, which: str, bevel: Bevel = BEVEL_ISO_9692_1_V) -> None:
        """Weld-prep bevel on square end ``which`` of a round or
        square / rectangular tube: the outside of the wall is chamfered at
        ``bevel.angle`` from the end plane, leaving ``bevel.root_face`` of
        the wall square (single-V butt preparation, ISO 9692-1 / ASME
        B16.25). Round tubes get a true conical bevel (a revolved cut);
        rectangular tubes one plane wedge per wall."""
        m = self.member_layout
        _, d, _ = self._end_frame(which)
        cut = m.cut(which)
        if cut.needs_trim or cut.cope is not None or cut.cope_member is not None:
            raise BevelError(
                f"{m.name}: bevel the {which} end only when it is cut square "
                f"(it is {cut.kind})"
            )
        prof = m.profile
        if not isinstance(prof, (RoundTube, RectTube)):
            raise BevelError(
                f"{m.name}: weld-prep bevels are for round / rectangular tube, not "
                f"{prof.designation}"
            )
        t = profile_wall(prof)
        c = float(bevel.root_face)
        if c >= t:
            raise BevelError(
                f"{m.name}: root face {c:g} mm leaves no bevel on a {t:g} mm wall"
            )
        x0, x1 = self.length_range
        x_e = x0 if which == "start" else x1
        out = -d[0]  # +1: material ends towards +X
        k = math.tan(math.radians(bevel.angle))
        margin = 1.0

        def wedge(sk: Sketch, inner: float, outer: float):
            pencil = sk.pencil
            pencil.move_to(out * margin, inner)
            pencil.line_to(0.0, inner)
            pencil.line_to(-out * (outer + margin - inner) * k, outer + margin)
            pencil.line_to(out * margin, outer + margin)
            return pencil.close()

        if isinstance(prof, RoundTube):
            ro = prof.diameter / 2.0
            sk = Sketch(self._new_plane((x_e, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0)))
            shape = wedge(sk, ro - t + c, ro)
            axis = Axis(Line(Point(sk, 0.0, 0.0), Point(sk, 1.0, 0.0)))
            self.add_operation(Lathe(shape, axis, angle=360.0, cut=True))
        else:
            for du, dv in MEMBER_FACES.values():
                n = (0.0, du, dv)
                reach = prof.support(du, dv)
                across = prof.support(dv, du)
                z = cross((1.0, 0.0, 0.0), n)
                sk = Sketch(self._new_plane((x_e, 0.0, 0.0), (1.0, 0.0, 0.0), z))
                shape = wedge(sk, reach - t + c, reach)
                self.add_operation(
                    Extrusion(shape, across + margin, start=-(across + margin), cut=True)
                )
        cut.bevel = bevel

    def saw_angle(self, which: str) -> SawAngle | None:
        """Saw setting of end ``which`` (``None``: a saddle cope, not a saw
        cut)."""
        return end_saw_angle(self.member_layout, which, self.frame_layout.members)

    # ------------------------------------------------------------ load check
    def apply_udl(
        self,
        udl: float,
        span: float | None = None,
        grade: str | float = "S235",
        limit_ratio: float = DEFLECTION_LIMIT_RATIO,
        self_weight: bool = True,
    ) -> SpanCheck:
        """Declare a uniformly distributed load (kN/m) on this member as a
        simply supported span (default: its centre-line length). The
        member's ``__checks__`` then reports the deflection (L / 250) and
        yield check (:mod:`cadbuildr.frames.loads`); returns the result."""
        span = float(span) if span is not None else self.member_layout.centerline_length
        self._load = dict(
            udl=float(udl),
            span=span,
            grade=grade,
            limit_ratio=limit_ratio,
            self_weight=self_weight,
        )
        return self.span_check()

    def span_check(self) -> SpanCheck | None:
        """The load check declared with :meth:`apply_udl` (``None`` if none)."""
        load = getattr(self, "_load", None)
        if not load:
            return None
        return simple_span_udl(
            self.member_layout.profile,
            load["span"],
            load["udl"],
            grade=load["grade"],
            limit_ratio=load["limit_ratio"],
            self_weight=load["self_weight"],
            density=self.density,
        )

    def __checks__(self) -> list:
        result = self.span_check()
        return result.issues(self.name.value) if result is not None else []

    # ------------------------------------------------------------------- BOM
    @property
    def density(self) -> float:
        """Material density (kg/m^3): softwood for lumber, else steel."""
        return SOFTWOOD_DENSITY if isinstance(self.member_layout.profile, Lumber) else STEEL_DENSITY

    def __bom__(self) -> dict:
        """BOM contract (``cadbuildr-bom``): one stock piece with its cut
        length, saw angles and end preparation."""
        m = self.member_layout
        saws = [self.saw_angle(w) for w in ("start", "end")]
        return {
            "designation": f"{m.profile.designation} x {m.cut_length:.0f}",
            "category": "Frames/Members",
            "procurement": "stock",
            "stock": m.profile.designation,
            "cut_length": round(m.cut_length, 1),
            "mass_kg": m.cut_length / 1000.0 * m.profile.mass_per_m(self.density),
            "mass_source": "computed",
            "extra": {
                "end_cuts": [m.start.kind, m.end.kind],
                "saw_angles": ["cope" if a is None else str(a) for a in saws],
                "end_preps": [
                    end_prep_label(m, w, self.frame_layout.members)
                    for w in ("start", "end")
                ],
            },
        }

    # ----------------------------------------------------------------- helpers
    def _local_point(self, p: Vec) -> Vec:
        m = self.member_layout
        return to_local(m.basis, sub(p, m.origin))

    def _local_dir(self, v: Vec) -> Vec:
        return to_local(self.member_layout.basis, v)

    def _new_plane(self, origin: Vec, x: Vec, z: Vec) -> Plane:
        self.n_planes += 1
        return self._plane(origin, x, z, f"{self.member_layout.name}_p{self.n_planes}")

    def _section_plane(self, origin: Vec, basis: Basis) -> Plane:
        """Cross-section plane at ``origin`` (local) with the profile axes of
        world ``basis``: sketch u = basis y, v = basis z, normal = basis x."""
        return self._new_plane(
            origin, self._local_dir(basis[1]), self._local_dir(basis[0])
        )

    def _reach(self) -> float:
        w, h = self.member_layout.profile.size
        return max(w, h)

    # -------------------------------------------------------------- geometry
    def _build_straight(self) -> None:
        m = self.member_layout
        x0, x1 = -m.start.extension, m.centerline_length + m.end.extension
        prof = m.profile
        self.add_operation(Extrusion(prof.outer(Sketch(self.yz())), x1, start=x0))
        inner = prof.inner(Sketch(self.yz()))
        if inner is not None:
            self.add_operation(Extrusion(inner, x1 + 1.0, start=x0 - 1.0, cut=True))

    def _build_bent(self) -> None:
        m = self.member_layout
        arc: Arc3D = m.segment  # type: ignore[assignment]
        prof = m.profile
        c = self._local_point(arc.center)
        k = self._local_dir(arc.normal)
        sweep_deg = math.degrees(arc.sweep)

        sk = Sketch(self.yz())
        axis = Axis(Line(Point(sk, c[1], c[2]), Point(sk, c[1] + k[1], c[2] + k[2])))
        self.add_operation(Lathe(prof.outer(sk), axis, angle=sweep_deg))

        has_hole = prof.inner(Sketch(self.yz())) is not None
        if has_hole:
            # start the hollow slightly before the arc (rotated back about the
            # arc axis) so the inner revolve overlaps both end faces
            back = -_INNER_REVOLVE_OVERLAP_RAD
            o = add(c, rotate(scale(c, -1.0), k, back))
            u_axis = rotate((0.0, 1.0, 0.0), k, back)
            n_axis = rotate((1.0, 0.0, 0.0), k, back)
            plane = self._new_plane(o, u_axis, n_axis)
            sk2 = Sketch(plane)
            # arc centre / axis in the rotated plane's own sketch coordinates
            v_axis = cross(n_axis, u_axis)
            rel = sub(c, o)
            cu, cv = dot(rel, u_axis), dot(rel, v_axis)
            ku, kv = dot(k, u_axis), dot(k, v_axis)
            axis2 = Axis(Line(Point(sk2, cu, cv), Point(sk2, cu + ku, cv + kv)))
            self.add_operation(
                Lathe(
                    prof.inner(sk2),
                    axis2,
                    angle=sweep_deg + 2 * math.degrees(_INNER_REVOLVE_OVERLAP_RAD),
                    cut=True,
                )
            )

        # straight stubs carry a miter / through overhang past the arc ends
        if m.start.extension > 1e-9:
            e = m.start.extension
            self.add_operation(Extrusion(prof.outer(Sketch(self.yz())), -e))
            if has_hole:
                self.add_operation(
                    Extrusion(
                        prof.inner(Sketch(self.yz())), 0.0, start=-e - 1.0, cut=True
                    )
                )
        if m.end.extension > 1e-9:
            e = m.end.extension
            origin = self._local_point(arc.end)
            self.add_operation(
                Extrusion(
                    prof.outer(Sketch(self._section_plane(origin, m.end_basis))), e
                )
            )
            if has_hole:
                self.add_operation(
                    Extrusion(
                        prof.inner(Sketch(self._section_plane(origin, m.end_basis))),
                        e + 1.0,
                        cut=True,
                    )
                )

    def _apply_trim(self, which: str) -> None:
        cut: EndCut = self.member_layout.cut(which)
        if cut.cope_member is not None:
            self._apply_cope(cut)
        if not cut.needs_trim:
            return
        z = self._local_dir(cut.trim_normal)  # type: ignore[arg-type]
        p = self._local_point(cut.trim_point)  # type: ignore[arg-type]
        sk = Sketch(self._new_plane(p, _any_perp(z), z))
        side = 4.0 * self._reach() + 4.0 * abs(cut.extension) + 100.0
        depth = 2.0 * self._reach() + 2.0 * abs(cut.extension) + 10.0
        box = Rectangle.from_center_and_sides(sk.origin, side, side)
        self.add_operation(Extrusion(box, depth, cut=True))

    def _apply_cope(self, cut: EndCut) -> None:
        """Remove the through member's outer envelope from this end."""
        host = self.frame_layout.members[cut.cope_member]  # type: ignore[index]
        node = cut.trim_point  # a coped trim plane passes through the node
        assert node is not None
        # host orientation and material range along its +x near the node
        s_param = None
        for which in ("start", "end"):
            if (
                sum((a - b) ** 2 for a, b in zip(host.node(which), node)) < 1e-12
            ):  # same node
                s_param = which
        if s_param == "start":
            basis = host.basis
            lo, hi = -host.start.extension, host.centerline_length
        elif s_param == "end":
            basis = host.end_basis
            lo, hi = -host.centerline_length, host.end.extension
        else:  # T-junction onto the host's interior (straight host)
            basis = host.basis
            s = dot(sub(node, host.origin), host.segment.start_tangent)
            lo, hi = (
                -s - host.start.extension,
                host.centerline_length - s + host.end.extension,
            )
        reach = 4.0 * (self._reach() + max(host.profile.size))
        lo, hi = max(lo, -reach), min(hi, reach)
        plane = self._section_plane(self._local_point(node), basis)
        self.add_operation(
            Extrusion(host.profile.outer(Sketch(plane)), hi, start=lo, cut=True)
        )


class GussetPlate(_LocalPart):
    """Triangular corner plate. Local coordinates: the members' inner corner
    at the origin, the first leg along +X, plate normal +Z."""

    def __init__(
        self,
        g: GussetLayout,
        size: float,
        thickness: float,
        name: str,
        color: str | None,
    ):
        super().__init__()
        self.name = StringParameter(value=name)
        self.size = size
        self.thickness = thickness
        self.corner_point = g.corner
        y = cross(g.normal, g.leg_a)
        bx, by = dot(g.leg_b, g.leg_a), dot(g.leg_b, y)
        pencil = Sketch(self.xy()).pencil
        pencil.move_to(0.0, 0.0)
        pencil.line_to(size, 0.0)
        pencil.line_to(size * bx, size * by)
        tri = pencil.close()
        self.add_operation(
            Extrusion(tri, g.offset + thickness / 2, start=g.offset - thickness / 2)
        )
        if color is not None:
            self.paint(color)
        self.gusset_layout = g
        self.plate_area = 0.5 * size * size * abs(by)
        self.placement = _tf(g.corner, (g.leg_a, y, g.normal))
        # welded to member a at the corner (see Frame: rigid joint)
        self.add_anchor(make_anchor("corner", (0.0, 0.0, 0.0)))


class EndCapPlate(_LocalPart):
    """Plate closing an open member end, the member's outer outline in size,
    added beyond the end (the cut length is unchanged).

    Its local coordinates are its member's (start node at the origin, +X
    along the member), so with ``member_part`` it carries a ``seat`` anchor
    (``PlaneFace``) that is the member's ``end_a`` / ``end_b`` turned face to
    face: ``assembly.connect(cap.interface("seat"),
    member.interface("end_a"))`` puts it in place. ``placement`` is the
    equivalent world transform (the member's)."""

    def __init__(
        self,
        member: MemberLayout,
        which: str,
        thickness: float,
        name: str,
        color: str | None,
        member_part: "FrameMember | None" = None,
    ):
        super().__init__()
        self.name = StringParameter(value=name)
        self.thickness = thickness
        self.which = which
        self.member_layout = member
        node = to_local(member.basis, sub(member.node(which), member.origin))
        bx, by, _ = (to_local(member.basis, a) for a in member.frame_at(which))
        plane = self._plane(node, by, bx, f"{name}_section")
        shape = member.profile.outer(Sketch(plane))
        depth = -thickness if which == "start" else thickness
        self.add_operation(Extrusion(shape, depth))
        if color is not None:
            self.paint(color)
        self.placement = _tf(member.origin, member.basis)
        if member_part is not None:
            end = member_part.anchor("end_a" if which == "start" else "end_b")
            position, quaternion = _flipped(end)
            seat = self.add_anchor(make_anchor("seat", position, quaternion))
            self.add_interface(PlaneFace(name="end"), seat)


@dataclass(frozen=True)
class Gusset:
    """A triangular gusset plate in the frame corner at ``at``: legs of
    ``size`` along both members from their inner corner, ``thickness`` thick.
    ``position``: ``"center"`` (on the frame's mid-plane), ``"top"`` or
    ``"bottom"`` (flush with that face of the members; top = the ``up``
    side)."""

    at: Sequence[float]
    size: float = 60.0
    thickness: float = 5.0
    position: Literal["center", "top", "bottom"] = "center"


@dataclass(frozen=True)
class EndCap:
    """Plates of ``thickness`` closing every open member end."""

    thickness: float = 3.0


@dataclass(frozen=True)
class HolePattern:
    """A row of holes drilled into one face of a frame member — the
    arguments of :meth:`FrameMember.drill` plus ``member`` (index in skeleton
    order). ``Frame(..., holes=[HolePattern(0, face="top", size="M8",
    count=4, margin=50)])``."""

    member: int
    face: str = "top"
    size: str | None = "M8"
    diameter: float | None = None
    at: Sequence[float] = ()
    count: int | None = None
    pitch: float | None = None
    margin: float | None = None
    offset: float = 0.0
    through: bool = False
    fit: str = "NORMAL"
    name: str = "hole"

    def apply(self, part: "FrameMember") -> list:
        return part.drill(
            face=self.face,
            size=self.size,
            diameter=self.diameter,
            at=self.at,
            count=self.count,
            pitch=self.pitch,
            margin=self.margin,
            offset=self.offset,
            through=self.through,
            fit=self.fit,
            name=self.name,
        )


class Frame(Assembly):
    """A weldment / structural frame: ``profile`` swept along every segment
    of ``skeleton``, one Part per member, corners trimmed by ``corner``.

    - ``skeleton``: ``Line3D`` / ``Arc3D`` segments (see ``rectangle``,
      ``polyline``, ``box_edges``). Segments sharing an end point are joined.
    - ``profile``: one ``Profile`` for all members, or one per segment.
    - ``corner``: ``"miter"`` (default), ``"butt"`` (the longer member runs
      through, the other is trimmed to its face) or ``"coped"`` (as butt, but
      cut to the through member's outer shape — round tubes). Nodes with three
      or more members and T-junctions are always butted (coped with
      ``corner="coped"``).
    - ``up``: the side the profiles' v axis faces. Default: the skeleton's
      plane normal (towards +Z) for a planar skeleton, else +Z.
    - ``gussets``: ``Gusset`` plates at corners; ``end_caps``: an ``EndCap``
      for every free end.
    - ``connector``: joint hardware hook — a ``ConnectorRule`` or a callable
      ``connector(junction) -> Connection | None`` called once per junction
      (see ``frame.junctions``); its components are added to the frame
      (``frame.connectors``) and its machining is applied to the members.
    - ``holes``: ``HolePattern`` rows drilled into members (each hole gets a
      ``ScrewHole`` interface a fastener mates onto).

    Placement is by anchors and joints, not transforms: every member is
    fixed to the frame by its ``node_a`` anchor (a rigid joint to the
    skeleton node), end caps ``connect`` face to face onto the member's
    ``end_a`` / ``end_b``, gussets are jointed to an anchor on their first
    member. Members expose ``node_a/b``, ``end_a/b``, ``axis`` and
    ``face_*`` anchors with interfaces (see
    :meth:`FrameMember.add_standard_anchors`) so other parts mate to a frame.

    ``frame.cut_list()`` groups identical members (profile, length, end cuts);
    ``frame.weight()`` and ``frame.stock_plan()`` estimate material.
    """

    def __init__(
        self,
        skeleton: Sequence[Segment],
        profile: Profile | Sequence[Profile],
        corner: CornerType = "miter",
        up: Sequence[float] | None = None,
        gussets: Sequence[Gusset] = (),
        end_caps: EndCap | None = None,
        color: str | None = STEEL_COLOR,
        plate_color: str | None = PLATE_COLOR,
        connector: ConnectorLike | None = None,
        holes: Sequence[HolePattern] = (),
    ):
        super().__init__()
        segments = list(skeleton)
        if isinstance(profile, (list, tuple)):
            profiles = list(profile)
            if len(profiles) != len(segments):
                raise ValueError(
                    f"got {len(profiles)} profiles for {len(segments)} skeleton segments"
                )
        else:
            profiles = [profile] * len(segments)
        rule = as_rule(connector)
        layout = solve_layout(
            segments,
            profiles,
            corner,
            vec(up) if up is not None else None,
            choose_through=rule.choose_through if rule is not None else None,
        )
        self.layout = layout
        self.corner = corner
        self.members: list[FrameMember] = []
        self.gussets: list[GussetPlate] = []
        self.end_caps: list[EndCapPlate] = []
        self.connectors: list = []
        self.connections: list[tuple[Junction, Connection]] = []
        machining: dict[int, list] = {}
        if rule is not None:
            for junction in layout.junctions:
                conn = rule.connect(junction, layout)
                if conn is None:
                    continue
                self.connections.append((junction, conn))
                for ref, fn in conn.machining:
                    machining.setdefault(member_index(ref), []).append(fn)
        hole_specs: dict[int, list[HolePattern]] = {}
        for spec in holes:
            if not 0 <= spec.member < len(layout.members):
                raise ValueError(
                    f"HolePattern.member {spec.member} is not a member index "
                    f"(the frame has {len(layout.members)} members)"
                )
            hole_specs.setdefault(spec.member, []).append(spec)
        gusset_layouts = [
            layout.gusset(vec(spec.at), spec.position, spec.thickness)
            for spec in gussets
        ]
        self.holes: dict[int, list] = {}
        for m in layout.members:
            part = FrameMember(m, layout, color)
            if rule is not None:
                rule.prepare_member(part)
            for fn in machining.get(m.index, ()):
                fn(part)
            for spec in hole_specs.get(m.index, ()):
                self.holes.setdefault(m.index, []).extend(spec.apply(part))
            part.add_standard_anchors()
            for i, g in enumerate(gusset_layouts):
                if g.member_a == m.index:
                    part.add_anchor(
                        make_anchor(
                            f"gusset_{i + 1}",
                            part.local_point(g.corner),
                            z_axis=part.local_dir(g.normal),
                            x_axis=part.local_dir(g.leg_a),
                        )
                    )
            self.members.append(part)
            # placed by its start node: a rigid joint to the skeleton node
            self.ground(
                part.anchor("node_a"), at=list(m.origin), rot_deg=euler_deg(m.basis)
            )
        for i, (spec, g) in enumerate(zip(gussets, gusset_layouts)):
            plate = GussetPlate(
                g, spec.size, spec.thickness, f"gusset_{i + 1}", plate_color
            )
            self.gussets.append(plate)
            host = self.members[g.member_a]
            self.add_joint(
                RigidJoint(
                    parent_anchor=host.anchor(f"gusset_{i + 1}"),
                    child_anchor=plate.anchor("corner"),
                    flip=BoolParameter(value=False),
                )
            )
        if end_caps is not None:
            for i, (m, which) in enumerate(layout.free_ends()):
                host = self.members[m.index]
                cap = EndCapPlate(
                    m,
                    which,
                    end_caps.thickness,
                    f"end_cap_{i + 1}",
                    plate_color,
                    member_part=host,
                )
                self.end_caps.append(cap)
                end = "end_a" if which == "start" else "end_b"
                self.connect(cap.interface("seat"), host.interface(end))
        for _, conn in self.connections:
            for item in conn.components:
                placed = item if isinstance(item, Placed) else Placed(item)
                self.connectors.append(placed.component)
                if placed.tf is None:
                    self.add_component(placed.component)
                else:
                    self.add_component(placed.component, tf=placed.tf)
        self.refresh_bom_lines()

    @property
    def junctions(self) -> list[Junction]:
        """Every skeleton node and how its members are joined."""
        return self.layout.junctions

    def cut_list(self) -> list[CutListItem]:
        """Members grouped by profile, cut length and end cuts."""
        return cut_list(self.layout.members)

    def cut_list_table(self) -> str:
        """The cut list as a plain-text table."""
        return format_cut_list(self.cut_list())

    def member(self, name_or_index: str | int) -> FrameMember:
        """A member Part by index (skeleton order) or name (``member_3``)."""
        if isinstance(name_or_index, int):
            return self.members[name_or_index]
        for part in self.members:
            if part.member_name == name_or_index:
                return part
        raise KeyError(
            f"no member {name_or_index!r}; members: "
            f"{', '.join(p.member_name for p in self.members)}"
        )

    def total_length(self) -> dict[str, float]:
        """Stock length per profile designation (mm, long point to long
        point)."""
        out: dict[str, float] = {}
        for m in self.layout.members:
            key = m.profile.designation
            out[key] = out.get(key, 0.0) + m.cut_length
        return out

    def weight(self, density: float = STEEL_DENSITY) -> float:
        """Estimated weight in kg: members from their stock length (long
        point, what you buy) times the profile's kg/m, plus gusset and end
        cap plates; ``density`` in kg/m^3 (``STEEL_DENSITY``,
        ``ALUMINIUM_DENSITY``, ``SOFTWOOD_DENSITY``…). Sections are the
        simplified ones (sharp corners, no root fillets)."""
        total = 0.0
        for m in self.layout.members:
            total += m.cut_length / 1000.0 * m.profile.mass_per_m(density)
        for g in self.gussets:
            total += g.plate_area * g.thickness * 1e-9 * density
        for cap in self.end_caps:
            m = cap.member_layout
            total += m.profile.outer_area * cap.thickness * 1e-9 * density
        return total

    def pieces(self) -> list[Piece]:
        """Every member as a cut piece (for :func:`stock_plan`)."""
        return [
            Piece(m.profile.designation, m.cut_length, m.name)
            for m in self.layout.members
        ]

    # ----------------------------------------------------------------- welds
    def welds(self, throat: float | None = None, process: int | None = 135) -> list[Weld]:
        """Every welded joint as metadata (:mod:`cadbuildr.frames.welds`):

        - mitred corners: an all-round butt weld on the mitre outline
          (square butt; single-V when the ends carry a ``Bevel``);
        - butt / coped / tee / multi nodes: an all-round fillet on each
          trimmed member's end outline (the plane-cut outline, or the 3D
          saddle of a cope onto a round host);
        - gussets: a fillet along each leg, both faces;
        - end caps and feet (``frame.feet``): an all-round fillet on the
          member's outside.

        ``throat`` overrides the default fillet size (``welds.default_throat``
        of the thinner part); ``process`` is the ISO 4063 number on every
        symbol."""
        members = self.layout.members
        out: list[Weld] = []

        def local_normal(m: MemberLayout, which: str) -> Vec:
            cut = m.cut(which)
            if cut.trim_normal is None:
                return (1.0, 0.0, 0.0)
            return to_local(m.frame_at(which), cut.trim_normal)

        for j in self.layout.junctions:
            label = f"junction {j.index + 1}"
            if j.kind in ("free", "continuous"):
                continue
            if j.through is None:  # mitred corner
                a, b = j.butting
                length = plane_cut_perimeter(a.profile, local_normal(a.member, a.which))
                wall = min(profile_wall(a.profile), profile_wall(b.profile))
                bevel = a.cut.bevel if a.cut is not None else None
                out.append(
                    butt(label, (a.member.name, b.member.name), length, wall, bevel, True, process)
                )
                continue
            host = j.through.member
            for e in j.butting:
                m = e.member
                cut = m.cut(e.which)
                if cut.cope_member is not None and isinstance(host.profile, (RoundTube, RoundBar)):
                    host_axis = host.into(j.through.which) if j.through.which else host.segment.start_tangent
                    ang = math.degrees(math.acos(min(1.0, abs(dot(e.into, host_axis)))))
                    length = cope_perimeter(m.profile, Cope(host.profile, max(ang, 15.0)))
                else:
                    length = plane_cut_perimeter(m.profile, local_normal(m, e.which))
                t_min = min(profile_wall(m.profile), profile_wall(host.profile))
                out.append(
                    fillet(label, (m.name, host.name), length, t_min, throat, 1, True, process)
                )
        for g in self.gussets:
            ga = members[g.gusset_layout.member_a]
            gb = members[g.gusset_layout.member_b]
            for leg in (ga, gb):
                t_min = min(g.thickness, profile_wall(leg.profile))
                out.append(
                    fillet(g.name.value, (g.name.value, leg.name), g.size, t_min, throat, 2, False, process)
                )
        for cap in self.end_caps:
            m = cap.member_layout
            length = plane_cut_perimeter(m.profile, (1.0, 0.0, 0.0))
            t_min = min(cap.thickness, profile_wall(m.profile))
            out.append(
                fillet(cap.name.value, (cap.name.value, m.name), length, t_min, throat, 1, True, process)
            )
        for foot in getattr(self, "feet", None) or []:
            leg = getattr(foot, "welded_to", None)
            if leg is None:
                continue
            m = leg.member_layout
            length = plane_cut_perimeter(m.profile, (1.0, 0.0, 0.0))
            t_min = min(float(foot.thickness), profile_wall(m.profile))
            out.append(
                fillet(foot.name.value, (foot.name.value, m.name), length, t_min, throat, 1, True, process)
            )
        return out

    def weld_length(self, throat: float | None = None) -> float:
        """Total weld run (mm, every side counted)."""
        return sum(w.total_length for w in self.welds(throat))

    def weld_table(self, throat: float | None = None) -> str:
        """The weld list as a plain-text table (ISO 2553 designations)."""
        return format_welds(self.welds(throat))

    def bom(self, density: float = STEEL_DENSITY, throat: float | None = None) -> list[dict]:
        """Bill of materials rows: cut members (one row per cut-list item
        with saw angles), plates (gussets, end caps, feet) and one row per
        weld type and size with its total length and deposit mass. The last
        row (``kind = "total"``) carries the total weld length and mass."""
        rows: list[dict] = []
        for r in self.cut_list():
            per_m = next(
                m.profile.mass_per_m(density)
                for m in self.layout.members
                if m.name in r.members
            )
            rows.append(
                {
                    "kind": "member",
                    "designation": r.profile,
                    "qty": r.count,
                    "length_mm": r.length,
                    "saw": ["cope" if a is None else str(a) for a in r.saw_angles],
                    "ends": list(r.end_cuts),
                    "preps": [p for p in r.end_preps if p],
                    "mass_kg": r.count * r.length / 1000.0 * per_m,
                }
            )
        plates: dict[str, dict] = {}
        for g in self.gussets:
            key = f"Gusset {g.size:g} x {g.thickness:g}"
            row = plates.setdefault(key, {"kind": "plate", "designation": key, "qty": 0, "mass_kg": 0.0})
            row["qty"] += 1
            row["mass_kg"] += g.plate_area * g.thickness * 1e-9 * density
        for cap in self.end_caps:
            m = cap.member_layout
            key = f"End cap {m.profile.designation} t{cap.thickness:g}"
            row = plates.setdefault(key, {"kind": "plate", "designation": key, "qty": 0, "mass_kg": 0.0})
            row["qty"] += 1
            row["mass_kg"] += m.profile.outer_area * cap.thickness * 1e-9 * density
        for foot in getattr(self, "feet", None) or []:
            key = getattr(foot, "designation", None) or "Base plate"
            row = plates.setdefault(key, {"kind": "plate", "designation": key, "qty": 0, "mass_kg": 0.0})
            row["qty"] += 1
            row["mass_kg"] += float(getattr(foot, "mass_kg", 0.0) or 0.0)
        rows += list(plates.values())
        welds = self.welds(throat)
        for key, w in weld_summary(welds).items():
            rows.append(
                {
                    "kind": "weld",
                    "designation": f"{key} (ISO 2553)",
                    "qty": int(w["count"]),
                    "length_mm": w["length_mm"],
                    "mass_kg": w["deposit_kg"],
                }
            )
        rows.append(
            {
                "kind": "total",
                "designation": "total",
                "mass_kg": sum(r.get("mass_kg", 0.0) for r in rows),
                "weld_length_mm": sum(w.total_length for w in welds),
            }
        )
        return rows

    def bom_table(self, density: float = STEEL_DENSITY, throat: float | None = None) -> str:
        """:meth:`bom` as a plain-text table."""
        lines = ["Kind    Qty  Designation                       Length   Mass kg  Notes"]
        for r in self.bom(density, throat):
            if r["kind"] == "total":
                lines.append(
                    f"total                                               "
                    f"{r['mass_kg']:8.2f}  weld length {r['weld_length_mm']:.0f} mm"
                )
                continue
            length = f"{r['length_mm']:.0f}" if "length_mm" in r else ""
            notes = ""
            if r["kind"] == "member":
                notes = f"saw {'/'.join(r['saw'])}" + (f"; {'; '.join(r['preps'])}" if r["preps"] else "")
            lines.append(
                f"{r['kind']:<7} {r['qty']:<4} {r['designation']:<33} {length:>7}  "
                f"{r['mass_kg']:7.2f}  {notes}".rstrip()
            )
        return "\n".join(lines)

    def apply_udl(self, member: str | int, udl: float, **kwargs) -> SpanCheck:
        """:meth:`FrameMember.apply_udl` on one member (index or name)."""
        return self.member(member).apply_udl(udl, **kwargs)

    def refresh_bom_lines(self, throat: float | None = None) -> None:
        """Add the weld totals as non-geometric BOM lines when
        ``cadbuildr-bom`` is installed (``add_bom_line``, unit mm); replaces
        lines a previous call added. Called by ``Frame``; call it again
        after adding parts that are welded on."""
        try:
            from cadbuildr.bom import add_bom_line
        except ImportError:
            return
        lines = self.__dict__.get("_bom_lines")
        if lines:
            self.__dict__["_bom_lines"] = [
                i for i in lines if not (i.category or "").startswith("Frames/Welds")
            ]
        for key, w in weld_summary(self.welds(throat)).items():
            add_bom_line(
                self,
                designation=f"Weld {key} (ISO 2553)",
                quantity=round(w["length_mm"], 1),
                unit="mm",
                category="Frames/Welds",
                procurement="make",
                notes=f"{int(w['count'])} joints, {w['deposit_kg']:.3f} kg deposit",
            )

    def stock_plan(
        self, stock_length: float = STOCK_LENGTH_6M, kerf: float = 3.0
    ) -> StockPlan:
        """How many stock bars to buy and how to cut them (first-fit
        decreasing per profile). Bent members are counted by their developed
        (centre line) length."""
        return stock_plan(self.pieces(), stock_length, kerf)
