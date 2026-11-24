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
    Extrusion,
    Lathe,
    Line,
    Part,
    Plane,
    Point,
    Rectangle,
    Sketch,
    StringParameter,
)
from cadbuildr.foundation import Frame as CoordinateFrame
from cadbuildr.foundation.math_utils import rotation_matrix_to_quaternion

from .cut_list import CutListItem, cut_list, format_cut_list
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
    MemberLayout,
    solve_layout,
)
from .profiles import Profile

STEEL_COLOR = "#9aa3ad"
PLATE_COLOR = "#6b7480"

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
        self.placement = _tf(g.corner, (g.leg_a, y, g.normal))


class EndCapPlate(_LocalPart):
    """Plate closing an open member end, the member's outer outline in size,
    added beyond the end (the cut length is unchanged)."""

    def __init__(
        self,
        member: MemberLayout,
        which: str,
        thickness: float,
        name: str,
        color: str | None,
    ):
        super().__init__()
        self.name = StringParameter(value=name)
        self.thickness = thickness
        shape = member.profile.outer(Sketch(self.yz()))
        depth = -thickness if which == "start" else thickness
        self.add_operation(Extrusion(shape, depth))
        if color is not None:
            self.paint(color)
        self.placement = _tf(member.node(which), member.frame_at(which))


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

    ``frame.cut_list()`` groups identical members (profile, length, end cuts).
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
        layout = solve_layout(
            segments, profiles, corner, vec(up) if up is not None else None
        )
        self.layout = layout
        self.corner = corner
        self.members: list[FrameMember] = []
        self.gussets: list[GussetPlate] = []
        self.end_caps: list[EndCapPlate] = []
        for m in layout.members:
            part = FrameMember(m, layout, color)
            self.members.append(part)
            self.add_component(part, tf=_tf(m.origin, m.basis))
        for i, spec in enumerate(gussets):
            g = layout.gusset(vec(spec.at), spec.position, spec.thickness)
            plate = GussetPlate(
                g, spec.size, spec.thickness, f"gusset_{i + 1}", plate_color
            )
            self.gussets.append(plate)
            self.add_component(plate, tf=plate.placement)
        if end_caps is not None:
            for i, (m, which) in enumerate(layout.free_ends()):
                cap = EndCapPlate(
                    m, which, end_caps.thickness, f"end_cap_{i + 1}", plate_color
                )
                self.end_caps.append(cap)
                self.add_component(cap, tf=cap.placement)

    def cut_list(self) -> list[CutListItem]:
        """Members grouped by profile, cut length and end cuts."""
        return cut_list(self.layout.members)

    def cut_list_table(self) -> str:
        """The cut list as a plain-text table."""
        return format_cut_list(self.cut_list())
