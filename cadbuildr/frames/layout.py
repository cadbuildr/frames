"""Frame layout: from a skeleton + profiles to per-member cut lengths, end
trims and gusset / end-cap positions. Pure maths, no geometry is built here,
so the cut list can be computed (and tested) without a kernel.

Conventions, per member end:

- ``d`` (the *into* direction) is the unit vector pointing from the end's node
  into the member's material (the start tangent at the start, minus the end
  tangent at the end).
- ``extension`` is how far the member's material reaches *beyond* the node
  (positive = longer than the skeleton segment, negative = cut back).
- a trim plane is given by a world point and the normal pointing *away* from
  the kept material (into the part that is cut off).

How each node is treated:

- one free end -> square cut at the node (``free``); end caps go here.
- ends lying inside another member (a T; or several ends, e.g. two rails
  meeting at a post's mid-height) -> each butted / coped onto it.
- two ends -> the frame's ``corner`` rule: ``miter`` (both cut on the
  bisector plane), ``butt`` (the longer member runs through, the other is
  trimmed to its face) or ``coped`` (as butt, but the trimmed member is cut to
  the outside of the through member — for round tubes). Collinear / tangent
  ends just continue (``continuous``).
- three or more ends -> the longest member runs through, the others are
  butted (or coped) to it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional, Sequence

from .geometry import (
    NODE_TOLERANCE,
    Arc3D,
    Basis,
    Line3D,
    Segment,
    Vec,
    add,
    basis_from_up,
    cross,
    dot,
    norm,
    scale,
    skeleton_normal,
    sub,
    unit,
)
from .profiles import Profile

CornerType = Literal["miter", "butt", "coped"]
CORNER_TYPES = ("miter", "butt", "coped")

# Profile "up" for non-planar skeletons, and the fallback for members that run
# parallel to up (e.g. the posts of a table frame): their profile v axis then
# points along world +X.
DEFAULT_UP: Vec = (0.0, 0.0, 1.0)
FALLBACK_UP: Vec = (1.0, 0.0, 0.0)

# Ends whose directions are within this angle of straight-through count as
# one continuous run (no trim).
COLLINEAR_TOLERANCE_DEG = 1e-3

# Trims flatter than this are square cuts (the extrusion end already is the cut).
SQUARE_CUT_TOLERANCE_DEG = 1e-6


@dataclass
class EndCut:
    """How one end of a member is cut."""

    kind: str  # free | continuous | miter | butt | through | coped
    extension: float = 0.0
    angle_deg: float = 0.0  # cut angle from square (0 = square cut)
    trim_point: Vec | None = None
    trim_normal: Vec | None = None  # points away from the kept material
    cope_member: int | None = None  # index of the member this end is coped to

    @property
    def needs_trim(self) -> bool:
        return (
            self.trim_normal is not None and self.angle_deg > SQUARE_CUT_TOLERANCE_DEG
        )


@dataclass
class MemberLayout:
    index: int
    segment: Segment
    profile: Profile
    basis: Basis  # orientation at the segment start
    end_basis: Basis  # orientation at the segment end
    start: EndCut = field(default_factory=lambda: EndCut("free"))
    end: EndCut = field(default_factory=lambda: EndCut("free"))

    @property
    def name(self) -> str:
        return f"member_{self.index + 1}"

    @property
    def origin(self) -> Vec:
        return self.segment.start

    @property
    def centerline_length(self) -> float:
        return self.segment.length

    @property
    def cut_length(self) -> float:
        """Overall (long-point to long-point) length of stock to cut."""
        return self.start.extension + self.centerline_length + self.end.extension

    def cut(self, which: str) -> EndCut:
        return self.start if which == "start" else self.end

    def into(self, which: str) -> Vec:
        if which == "start":
            return self.segment.start_tangent
        return scale(self.segment.end_tangent, -1.0)

    def frame_at(self, which: str) -> Basis:
        return self.basis if which == "start" else self.end_basis

    def node(self, which: str) -> Vec:
        return self.segment.start if which == "start" else self.segment.end

    def support(self, which: str, direction: Vec) -> float:
        """How far the profile reaches along world ``direction`` (its
        component across the member) at end ``which``."""
        _, y, z = self.frame_at(which)
        return self.profile.support(dot(direction, y), dot(direction, z))


@dataclass
class GussetLayout:
    member_a: int
    member_b: int
    corner: Vec  # inner corner point of the two members
    leg_a: Vec  # unit direction of the leg along member a
    leg_b: Vec  # unit direction of the leg along member b
    normal: Vec  # plate normal (towards the frame's up side)
    offset: float  # plate mid-plane offset along normal


# How the members meet at a node (``Junction.kind``).
JunctionKind = Literal["free", "continuous", "corner", "tee", "multi"]


@dataclass(frozen=True)
class JunctionEnd:
    """One member taking part in a junction. ``which`` is the member end at
    the node (``"start"`` / ``"end"``), or ``None`` when the node lies inside
    the member (the host of a T-junction)."""

    member: MemberLayout
    which: str | None

    @property
    def profile(self) -> Profile:
        return self.member.profile

    @property
    def cut(self) -> EndCut | None:
        return self.member.cut(self.which) if self.which else None

    @property
    def into(self) -> Vec:
        """Unit direction from the node into this member's material (for a
        T host: the member's own direction, it continues both ways)."""
        if self.which is None:
            return self.member.segment.start_tangent
        return self.member.into(self.which)

    @property
    def basis(self) -> Basis:
        """The member's orientation (x along the member, y / z = profile u /
        v) at the node."""
        if self.which is None:
            return self.member.basis
        return self.member.frame_at(self.which)


@dataclass(frozen=True)
class Junction:
    """A skeleton node and how its members are joined — what a frame's
    ``connector`` hook is called with.

    - ``kind``: ``"free"`` (one open end), ``"continuous"`` (two collinear
      ends), ``"corner"`` (two ends at an angle), ``"tee"`` (an end landing
      inside another member) or ``"multi"`` (three or more ends).
    - ``through``: the member that runs through (``None`` for free,
      continuous and mitered nodes); ``butting``: the members trimmed to it
      (for a miter / free / continuous node: every end).
    - ``corner``: the frame's corner rule (``miter`` / ``butt`` / ``coped``).
    """

    index: int
    node: Vec
    kind: JunctionKind
    corner: str
    through: JunctionEnd | None
    butting: tuple[JunctionEnd, ...]
    up: Vec

    @property
    def ends(self) -> tuple[JunctionEnd, ...]:
        return ((self.through,) if self.through else ()) + self.butting


# Optional override of which member runs through a butt / coped / multi node:
# called with the node and its member ends, returns an index into them, or
# None to keep the default rule (arc, then longest, then first).
ThroughChooser = Callable[[Vec, Sequence[JunctionEnd]], Optional[int]]


@dataclass
class FrameLayout:
    members: list[MemberLayout]
    up: Vec
    # two-member corners, keyed by node: (member a, end a, member b, end b)
    corners: list[tuple[MemberLayout, str, MemberLayout, str]]
    tolerance: float
    junctions: list[Junction] = field(default_factory=list)

    def free_ends(self) -> list[tuple[MemberLayout, str]]:
        """Member ends that connect to nothing (where end caps go)."""
        return [
            (m, w)
            for m in self.members
            for w in ("start", "end")
            if m.cut(w).kind == "free"
        ]

    def gusset(
        self, point: Vec, position: str = "center", thickness: float = 0.0
    ) -> GussetLayout:
        """Where a gusset plate sits in the corner at ``point``."""
        return _gusset(
            point, self.corners, self.tolerance, self.up, position, thickness
        )


def _angle_between(a: Vec, b: Vec) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(a, b)))))


def _perp(v: Vec, axis: Vec) -> Vec:
    """Unit component of ``v`` perpendicular to unit ``axis``."""
    return unit(sub(v, scale(axis, dot(v, axis))))


def _miter(a: MemberLayout, wa: str, b: MemberLayout, wb: str) -> None:
    da, db = a.into(wa), b.into(wb)
    node = a.node(wa)
    for m, w, d, other in ((a, wa, da, db), (b, wb, db, da)):
        nu = unit(sub(d, other))  # points into this member's kept side
        cos = dot(nu, d)
        cut = m.cut(w)
        cut.kind = "miter"
        cut.extension = m.support(w, nu) / cos
        cut.angle_deg = _angle_between(nu, d)
        cut.trim_point = node
        cut.trim_normal = scale(nu, -1.0)


def _butt(
    through: MemberLayout,
    through_which: str | None,
    host_axis: Vec,
    host_frame: str,
    butting: MemberLayout,
    bw: str,
    node: Vec,
    coped: bool,
) -> float:
    """Trim ``butting`` (end ``bw``) to ``through``; return how far the
    through member must reach beyond the node to cover it."""
    du = butting.into(bw)
    if abs(dot(du, host_axis)) > math.cos(math.radians(COLLINEAR_TOLERANCE_DEG)):
        raise ValueError(
            f"{butting.name} runs along {through.name} at a shared node; "
            "overlapping members cannot be trimmed"
        )
    m = _perp(du, host_axis)  # from the through member's axis towards the butting one
    face = through.support(host_frame, m)  # through member's face on that side
    m_du = dot(m, du)
    plane_offset = 0.0 if coped else face
    cut = butting.cut(bw)
    cut.kind = "coped" if coped else "butt"
    cut.extension = (butting.support(bw, m) - plane_offset) / m_du
    cut.angle_deg = 0.0 if coped else _angle_between(m, du)
    cut.trim_point = add(node, scale(m, plane_offset))
    cut.trim_normal = scale(m, -1.0)
    if coped:
        cut.cope_member = through.index
        c = unit(cross(host_axis, m))
        for side in (c, scale(c, -1.0)):
            if butting.support(bw, side) > through.support(host_frame, side) + 1e-9:
                raise ValueError(
                    f"{butting.name} is wider than {through.name}, it cannot be "
                    "coped to it; use corner='butt'"
                )
    if through_which is None:
        return 0.0
    # Through member's reach (along -d_T) over the butting member's end face.
    dt = through.into(through_which)
    k = dot(dt, du) / m_du
    w = add(scale(dt, -1.0), scale(m, k))
    return -dot(dt, du) * face / m_du + butting.support(bw, w)


def _pick_through(ends: Sequence[tuple[MemberLayout, str]]) -> int:
    """Index (into ``ends``) of the member that runs through a butt node: an
    arc over a line (arcs cannot be cut back), then the longest, then the
    first in skeleton order."""

    def key(item: tuple[int, tuple[MemberLayout, str]]):
        i, (m, _) = item
        return (isinstance(m.segment, Arc3D), m.centerline_length, -m.index)

    return max(enumerate(ends), key=key)[0]


def _cluster_ends(members: Sequence[MemberLayout], tol: float):
    clusters: list[tuple[Vec, list[tuple[MemberLayout, str]]]] = []
    for m in members:
        for which in ("start", "end"):
            p = m.node(which)
            for point, ends in clusters:
                if norm(sub(point, p)) <= tol:
                    ends.append((m, which))
                    break
            else:
                clusters.append((p, [(m, which)]))
    return clusters


def solve_layout(
    skeleton: Sequence[Segment],
    profiles: Sequence[Profile],
    corner: CornerType,
    up: Vec | None,
    choose_through: ThroughChooser | None = None,
) -> FrameLayout:
    if corner not in CORNER_TYPES:
        raise ValueError(f"corner must be one of {CORNER_TYPES}, got {corner!r}")
    if not skeleton:
        raise ValueError("a frame needs at least one skeleton segment")
    for seg in skeleton:
        if not isinstance(seg, (Line3D, Arc3D)):
            raise TypeError(
                f"skeleton items must be Line3D or Arc3D, got {type(seg).__name__}"
            )
    if up is None:
        up = skeleton_normal(skeleton) or DEFAULT_UP
    up = unit(up)

    members: list[MemberLayout] = []
    for i, (seg, prof) in enumerate(zip(skeleton, profiles)):
        basis = basis_from_up(seg.start_tangent, up, FALLBACK_UP)
        members.append(MemberLayout(i, seg, prof, basis, seg.end_basis(basis)))

    span = max(
        norm(sub(p, members[0].origin)) for m in members for p in m.segment.points()
    )
    tol = max(NODE_TOLERANCE, 1e-9 * span)
    straight = math.cos(math.radians(COLLINEAR_TOLERANCE_DEG))
    corners: list[tuple[MemberLayout, str, MemberLayout, str]] = []
    records: list[tuple[Vec, str, JunctionEnd | None, list[JunctionEnd]]] = []

    def record(node, kind, through, butting):
        records.append((node, kind, through, [JunctionEnd(m, w) for m, w in butting]))

    for node, ends in _cluster_ends(members, tol):
        # a node lying inside another member: every end there is butted
        # (coped) onto that host — one end is a T, several ends (e.g. two
        # shelf rails meeting at a table leg) all land on the host's faces
        ending = {id(m) for m, _ in ends}
        host = next(
            (
                h
                for h in members
                if id(h) not in ending
                and h.segment.contains_interior(node, tol) is not None
            ),
            None,
        )
        if host is not None:
            for m, w in ends:
                _butt(
                    host,
                    None,
                    host.segment.start_tangent,
                    "start",
                    m,
                    w,
                    node,
                    corner == "coped",
                )
            record(node, "tee", JunctionEnd(host, None), ends)
            continue
        if len(ends) == 1:
            record(node, "free", None, ends)
            continue
        if len(ends) == 2:
            (a, wa), (b, wb) = ends
            da, db = a.into(wa), b.into(wb)
            if dot(da, db) < -straight:
                a.cut(wa).kind = b.cut(wb).kind = "continuous"
                record(node, "continuous", None, ends)
                continue
            if dot(da, db) > straight:
                raise ValueError(f"{a.name} and {b.name} overlap at {node}")
            corners.append((a, wa, b, wb))
            if corner == "miter":
                _miter(a, wa, b, wb)
                record(node, "corner", None, ends)
                continue
        # butt / coped corner, or a node joining three or more members
        ti = None
        if choose_through is not None:
            ti = choose_through(node, [JunctionEnd(m, w) for m, w in ends])
            if ti is not None and not 0 <= ti < len(ends):
                raise ValueError(
                    f"choose_through returned {ti!r} for a node with {len(ends)} ends"
                )
        if ti is None:
            ti = _pick_through(ends)
        through, tw = ends[ti]
        reach = 0.0
        for j, (m, w) in enumerate(ends):
            if j == ti:
                continue
            reach = max(
                reach,
                _butt(
                    through,
                    tw,
                    through.into(tw),
                    tw,
                    m,
                    w,
                    node,
                    corner == "coped",
                ),
            )
        tc = through.cut(tw)
        tc.kind = "through"
        tc.extension = reach
        record(
            node,
            "corner" if len(ends) == 2 else "multi",
            JunctionEnd(through, tw),
            [e for j, e in enumerate(ends) if j != ti],
        )

    for m in members:
        if isinstance(m.segment, Arc3D):
            for w in ("start", "end"):
                if m.cut(w).extension < -1e-9:
                    raise ValueError(
                        f"{m.name} is an arc and cannot be cut back at its {w}; "
                        "let it run through or use a miter"
                    )
        if m.cut_length <= 0:
            raise ValueError(
                f"{m.name} is trimmed away entirely (cut length {m.cut_length:.3f})"
            )

    junctions = [
        Junction(i, node, kind, corner, through, tuple(butting), up)
        for i, (node, kind, through, butting) in enumerate(records)
    ]
    return FrameLayout(members, up, corners, tol, junctions)


def _gusset(
    point: Vec,
    corners: Sequence[tuple[MemberLayout, str, MemberLayout, str]],
    tol: float,
    up: Vec,
    position: str,
    thickness: float,
) -> GussetLayout:
    for a, wa, b, wb in corners:
        node = a.node(wa)
        if norm(sub(node, point)) > max(tol, 1e-6):
            continue
        da, db = a.into(wa), b.into(wb)
        s = norm(cross(da, db))  # sin of the corner angle
        ma, mb = _perp(db, da), _perp(da, db)
        ha, hb = a.support(wa, ma), b.support(wb, mb)
        inner = add(node, add(scale(da, hb / s), scale(db, ha / s)))
        k = unit(cross(da, db))
        if dot(k, up) < 0:
            k = scale(k, -1.0)
        if position == "center":
            offset = 0.0
        elif position == "top":
            offset = min(a.support(wa, k), b.support(wb, k)) - thickness / 2
        elif position == "bottom":
            k_down = scale(k, -1.0)
            offset = -(
                min(a.support(wa, k_down), b.support(wb, k_down)) - thickness / 2
            )
        else:
            raise ValueError(
                f"gusset position must be center|top|bottom, got {position!r}"
            )
        return GussetLayout(a.index, b.index, inner, da, db, k, offset)
    raise ValueError(
        f"no two-member corner at {point}; gussets go on frame corners "
        "(a node where exactly two members meet at an angle)"
    )
