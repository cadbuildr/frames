"""Tube end preparation: copes (saddle cuts), mitres and weld-prep bevels.

All the maths here is kernel-free; the geometry is built by
:class:`~cadbuildr.frames.frame.FrameMember` (``cope`` / ``bevel``) and the
:class:`~cadbuildr.frames.fabrication.PreparedTube` configurable.

**How the cope is cut (a true saddle, not an approximation).** A branch
tube landing on a host tube is cut by a boolean subtraction of the host's
*outer envelope* — its outer profile extruded along the host axis — from
the branch. The kernel intersects the branch's outer and inner cylinders
with the host cylinder exactly, so both walls end on the true saddle
(intersection) curve; nothing is faceted or replaced by planes. Onto a
square / rectangular host the same subtraction leaves a plane (and the
corner radii where the branch reaches them).

The analytic saddle, used for the cut list, cope templates and weld
lengths: branch axis = local +X from the node, host axis through the node
at ``angle`` to the branch in the local XY plane, the branch axis offset
``offset`` from the host axis along local Z. A branch surface point at
angle ``phi`` (``y = r cos(phi)``, ``z = r sin(phi)``) leaves the host
cylinder of radius ``R`` at

    x(phi) = ( r cos(phi) cos(angle) + sqrt(R^2 - (offset + r sin(phi))^2) ) / sin(angle)

(the intersection of two cylinders; see e.g. Steinmetz-solid geometry, and
the classic pipe-fitter's cope template). It needs ``r + |offset| <= R``.
A flat host face at distance ``H`` gives the plane
``x = (y cos(angle) + H) / sin(angle)``.

**Bevels.** ``Bevel(angle, root_face)`` is a weld-preparation chamfer on a
square tube end: the fusion face makes ``angle`` with the plane of the end
(the bevel angle; a single-V groove's included angle is twice it), the
inner ``root_face`` of the wall is left square. Presets:

- ``BEVEL_ISO_9692_1_V``: ISO 9692-1:2013 ref. 1.3 single-V butt weld,
  t = 3..10 mm, included angle 40..60 deg -> bevel 30 deg, root face
  c <= 2 mm (1.5 mm used).
- ``BEVEL_ASME_B16_25``: ASME B16.25 butt-welding end, 37.5 deg +/- 2.5,
  root face (land) 1.6 mm +/- 0.8.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .profiles import Profile, RectTube, RoundBar, RoundTube


class EndPrepError(ValueError):
    """An end preparation that cannot be made on this member."""


class CopeError(EndPrepError):
    """A cope that does not fit (branch wider than the host, bad angle…)."""


class BevelError(EndPrepError):
    """A weld-prep bevel on an end or section that cannot take one."""


# Copes steeper than this from the host axis are refused (the saddle runs
# out along the host and the stock left is a sliver).
MIN_COPE_ANGLE_DEG = 15.0


@dataclass(frozen=True)
class Cope:
    """Cope (saddle-cut) a member end onto ``host`` (a profile: round tube /
    bar for a saddle, square / rectangular tube for a flat-face notch).
    ``angle``: degrees between the branch and the host axis (90 =
    perpendicular). ``offset``: branch axis offset from the host axis
    (mm, along the member's local Z)."""

    host: Profile
    angle: float = 90.0
    offset: float = 0.0

    def __post_init__(self) -> None:
        if not MIN_COPE_ANGLE_DEG <= self.angle <= 90.0:
            raise CopeError(
                f"cope angle {self.angle:g} deg must be between "
                f"{MIN_COPE_ANGLE_DEG:g} and 90"
            )

    @property
    def label(self) -> str:
        off = f", offset {self.offset:g}" if self.offset else ""
        return f"cope onto {self.host.designation} @ {self.angle:g} deg{off}"


@dataclass(frozen=True)
class Miter:
    """Mitre a member end: the cut plane turned ``angle`` degrees from
    square, about the profile's ``v`` axis (``about="v"``: a mitre seen from
    the frame's up side, the usual picture-frame cut) or ``u`` (a bevel
    cut through the depth)."""

    angle: float = 45.0
    about: str = "v"

    def __post_init__(self) -> None:
        if not 0.0 <= self.angle < 75.0:
            raise EndPrepError(f"miter angle {self.angle:g} must be in 0..75 deg")
        if self.about not in ("u", "v"):
            raise EndPrepError(f"miter about must be 'u' or 'v', got {self.about!r}")


@dataclass(frozen=True)
class Bevel:
    """Weld-preparation bevel of a square hollow-section end: ``angle``
    (degrees, the bevel angle from the end plane) and ``root_face`` (mm of
    wall left square at the inside)."""

    angle: float = 30.0
    root_face: float = 1.5
    standard: str = "ISO 9692-1 ref. 1.3"

    def __post_init__(self) -> None:
        if not 0.0 < self.angle <= 60.0:
            raise BevelError(f"bevel angle {self.angle:g} must be in (0, 60] deg")
        if self.root_face < 0:
            raise BevelError("bevel root_face must be >= 0")

    @property
    def label(self) -> str:
        return f"bevel {self.angle:g} deg / root face {self.root_face:g}"


BEVEL_ISO_9692_1_V = Bevel(30.0, 1.5, "ISO 9692-1 ref. 1.3 (single-V, 60 deg)")
BEVEL_ASME_B16_25 = Bevel(37.5, 1.6, "ASME B16.25")
BEVEL_PRESETS = {"ISO 9692-1": BEVEL_ISO_9692_1_V, "ASME B16.25": BEVEL_ASME_B16_25}


# --------------------------------------------------------------------------- #
# Host reach and the saddle
# --------------------------------------------------------------------------- #


def host_half_width(host: Profile) -> float:
    """Half the host's extent along its u axis (the offset direction)."""
    return host.support(1.0, 0.0)


def host_reach(host: Profile, b: float) -> float:
    """How far the host's outer outline reaches along its v axis (towards
    the branch) at ``u = b``. Raises :class:`CopeError` past its edge."""
    if isinstance(host, (RoundTube, RoundBar)):
        r = host.diameter / 2.0
        if abs(b) > r + 1e-9:
            raise CopeError(
                f"the branch overhangs {host.designation} ({abs(b):.2f} mm from "
                f"its axis, radius {r:g})"
            )
        return math.sqrt(max(r * r - b * b, 0.0))
    if not isinstance(host, RectTube):
        raise CopeError(
            f"copes onto {type(host).__name__} are not supported; the host must be "
            "a round tube / bar or a square / rectangular tube"
        )
    outer = host.outline()[0]
    best = None
    n = len(outer)
    for i in range(n):
        (u0, v0), (u1, v1) = outer[i], outer[(i + 1) % n]
        if (u0 - b) * (u1 - b) <= 0 and abs(u1 - u0) > 1e-12:
            v = v0 + (v1 - v0) * (b - u0) / (u1 - u0)
            best = v if best is None else max(best, v)
        elif abs(u0 - b) < 1e-12:
            best = v0 if best is None else max(best, v0)
    if best is None:
        raise CopeError(
            f"the branch overhangs {host.designation} (|u| = {abs(b):.2f} mm > "
            f"{host_half_width(host):g})"
        )
    return best


def cope_x(host: Profile, y: float, z: float, angle_deg: float, offset: float) -> float:
    """Local x (from the node, along the branch) where the branch surface
    point ``(y, z)`` meets the host's outer envelope."""
    a = math.radians(angle_deg)
    return (y * math.cos(a) + host_reach(host, z + offset)) / math.sin(a)


def _cope_lo(host: Profile, y: float, z: float, angle_deg: float, offset: float) -> float:
    a = math.radians(angle_deg)
    return (y * math.cos(a) - host_reach(host, z + offset)) / math.sin(a)


def branch_loops(profile: Profile) -> list[list[tuple[float, float]]]:
    """Outer and inner (if hollow) outlines of a branch profile."""
    outer, inner = profile.outline()
    return [outer] + ([inner] if inner else [])


def check_cope_fits(branch: Profile, cope: Cope) -> None:
    """Raise :class:`CopeError` when ``branch`` cannot be coped onto the
    host (it is wider than the host across the offset direction)."""
    reach_u = branch.support(0.0, 1.0) + abs(cope.offset)
    reach_l = branch.support(0.0, -1.0) + abs(cope.offset)
    half = host_half_width(cope.host)
    if max(reach_u, reach_l) > half + 1e-9:
        raise CopeError(
            f"{branch.designation} (+ offset {cope.offset:g}) is wider than "
            f"{cope.host.designation} across the joint; it cannot be coped onto "
            "it (use a larger host, a smaller branch or a butt joint)"
        )


def cope_extent(branch: Profile, cope: Cope) -> tuple[float, float]:
    """``(x_short, x_long)``: the branch's material starts at ``x_short``
    (its long point, closest to the host axis) and the saddle reaches
    ``x_long`` (the short point). Raises :class:`CopeError` for a cope
    that would leave a stub on the far side of the host."""
    check_cope_fits(branch, cope)
    xs, lo = [], []
    for loop in branch_loops(branch):
        for y, z in loop:
            xs.append(cope_x(cope.host, y, z, cope.angle, cope.offset))
            lo.append(_cope_lo(cope.host, y, z, cope.angle, cope.offset))
    x0, x1 = min(xs), max(xs)
    if max(lo) > x0 + 1e-6:
        raise CopeError(
            f"a {cope.angle:g} deg cope of {branch.designation} onto "
            f"{cope.host.designation} would leave material on the far side of the "
            "host; use a steeper angle"
        )
    return x0, x1


def saddle_curve(
    branch_diameter: float,
    host_diameter: float,
    angle: float = 90.0,
    offset: float = 0.0,
    n: int = 72,
) -> list[tuple[float, float]]:
    """``(phi_deg, x)`` samples of the saddle on a round branch of outside
    ``branch_diameter`` coped onto a round host: ``x`` is the axial
    position (from the host axis) where the branch's outer surface meets
    the host, at angle ``phi`` round the branch (0 = towards +Y, the side
    the host axis leans to)."""
    host = RoundBar(host_diameter)
    r = branch_diameter / 2.0
    if r + abs(offset) > host_diameter / 2.0 + 1e-9:
        raise CopeError(
            f"branch {branch_diameter:g} (+ offset {offset:g}) is wider than the "
            f"host {host_diameter:g}"
        )
    out = []
    for k in range(n + 1):
        phi = 2 * math.pi * k / n
        out.append(
            (
                math.degrees(phi),
                cope_x(host, r * math.cos(phi), r * math.sin(phi), angle, offset),
            )
        )
    return out


def cope_template(
    branch_diameter: float,
    host_diameter: float,
    angle: float = 90.0,
    offset: float = 0.0,
    n: int = 72,
) -> list[tuple[float, float]]:
    """The unrolled cope template: ``(s, depth)`` with ``s`` the distance
    round the branch's outside (0 .. pi * d) and ``depth`` how far the cut
    line lies back from a square end at the long point. Wrap it round the
    tube with its base on the square end and cut away the material below
    the line."""
    curve = saddle_curve(branch_diameter, host_diameter, angle, offset, n)
    x_min = min(x for _, x in curve)
    r = branch_diameter / 2.0
    return [(math.radians(phi) * r, x - x_min) for phi, x in curve]


def cope_template_svg(
    branch_diameter: float,
    host_diameter: float,
    angle: float = 90.0,
    offset: float = 0.0,
    n: int = 144,
) -> str:
    """The cope template as a 1:1 SVG (millimetre units) to print and wrap
    round the branch tube."""
    pts = cope_template(branch_diameter, host_diameter, angle, offset, n)
    width = math.pi * branch_diameter
    depth = max(d for _, d in pts)
    margin = 10.0
    height = depth + 2 * margin
    path = " ".join(
        f"{'M' if i == 0 else 'L'}{s:.3f},{margin + depth - d:.3f}"
        for i, (s, d) in enumerate(pts)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.2f}mm" '
        f'height="{height:.2f}mm" viewBox="0 0 {width:.3f} {height:.3f}">'
        f'<rect x="0" y="0" width="{width:.3f}" height="{height:.3f}" '
        'fill="none" stroke="#999" stroke-width="0.2"/>'
        f'<path d="{path}" fill="none" stroke="#000" stroke-width="0.35"/>'
        f'<text x="2" y="{height - 2:.2f}" font-size="3">cope OD {branch_diameter:g} '
        f"onto OD {host_diameter:g} @ {angle:g} deg, offset {offset:g}; base = square "
        "end at the long point</text></svg>"
    )


# --------------------------------------------------------------------------- #
# Lengths and volumes
# --------------------------------------------------------------------------- #


def _closed_length(pts: Sequence[tuple[float, float, float]]) -> float:
    n = len(pts)
    return sum(math.dist(pts[i], pts[(i + 1) % n]) for i in range(n))


def plane_cut_perimeter(profile: Profile, normal: Sequence[float]) -> float:
    """Length of the outline a plane cut leaves on the member's outside:
    ``normal`` is the cut plane's normal in member coordinates (x along the
    member). A square cut gives the profile perimeter."""
    nx, ny, nz = normal
    if abs(nx) < 1e-9:
        raise EndPrepError("a cut plane parallel to the member has no end outline")
    outer = profile.outline()[0]
    return _closed_length([(-(ny * y + nz * z) / nx, y, z) for y, z in outer])


def cope_perimeter(branch: Profile, cope: Cope) -> float:
    """3D length of the saddle on the branch's outside: the weld run of a
    coped joint."""
    outer = branch.outline()[0]
    return _closed_length(
        [(cope_x(cope.host, y, z, cope.angle, cope.offset), y, z) for y, z in outer]
    )


def coped_volume(branch: Profile, cope: Cope, x_end: float, n_r: int = 24, n_phi: int = 360) -> float:
    """Volume (mm^3) of a round branch (tube or bar) coped onto ``cope``'s
    host and cut square at ``x_end`` (local x from the node). Midpoint-rule
    integration of ``x_end - x(rho, phi)`` over the cross-section."""
    if not isinstance(branch, (RoundTube, RoundBar)):
        raise EndPrepError("coped_volume integrates round branches only")
    ro = branch.diameter / 2.0
    ri = ro - branch.wall if isinstance(branch, RoundTube) else 0.0
    total = 0.0
    dr = (ro - ri) / n_r
    dphi = 2 * math.pi / n_phi
    for i in range(n_r):
        rho = ri + (i + 0.5) * dr
        for k in range(n_phi):
            phi = (k + 0.5) * dphi
            x = cope_x(cope.host, rho * math.cos(phi), rho * math.sin(phi), cope.angle, cope.offset)
            total += (x_end - x) * rho * dr * dphi
    return total


def bevel_volume(profile: Profile, bevel: Bevel) -> float:
    """Material (mm^3) a bevel removes from a round tube end (exact) or a
    square / rectangular tube end (the four walls as plane wedges, sharp
    corners)."""
    t = profile_wall(profile)
    if bevel.root_face >= t:
        raise BevelError(
            f"root face {bevel.root_face:g} mm leaves no bevel on a {t:g} mm wall"
        )
    k = math.tan(math.radians(bevel.angle))
    if isinstance(profile, RoundTube):
        ro = profile.diameter / 2.0
        a = ro - t + bevel.root_face
        return 2 * math.pi * k * ((ro**3 - a**3) / 3.0 - a * (ro**2 - a**2) / 2.0)
    if isinstance(profile, RectTube):
        h = t - bevel.root_face
        wedge = 0.5 * h * h * k  # cross-section of the wedge per mm of face
        return wedge * 2 * (profile.width + profile.height)
    raise BevelError(f"bevels are for hollow sections, not {profile.designation}")


def profile_wall(profile: Profile) -> float:
    """The thickness that governs welding: tube wall, angle thickness, the
    thinner of web / flange, or the bar's smaller dimension."""
    for name in ("wall", "thickness"):
        value = getattr(profile, name, None)
        if value:
            return float(value)
    web, flange = getattr(profile, "web", None), getattr(profile, "flange", None)
    if web and flange:
        return float(min(web, flange))
    return float(min(profile.size))


__all__ = [
    "BEVEL_ASME_B16_25",
    "BEVEL_ISO_9692_1_V",
    "BEVEL_PRESETS",
    "Bevel",
    "BevelError",
    "Cope",
    "CopeError",
    "EndPrepError",
    "Miter",
    "bevel_volume",
    "check_cope_fits",
    "cope_extent",
    "cope_perimeter",
    "cope_template",
    "cope_template_svg",
    "cope_x",
    "coped_volume",
    "host_reach",
    "plane_cut_perimeter",
    "profile_wall",
    "saddle_curve",
]
