"""Standard cross-sections a frame member is swept with.

A profile is drawn in its member's cross-section plane: ``u`` runs along the
member's local y, ``v`` along its local z (the frame's ``up`` side). Every
profile is centred on the skeleton line at the centre of its bounding box.
Dimensions are millimetres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from cadbuildr.foundation import Circle, Point, Sketch

INCH = 25.4


class Profile:
    """Base class: an outer outline and an optional inner (hollow) outline.

    ``designation`` names the stock the way it is ordered (``SHS 40x40x3``,
    ``IPE200``); ``area`` is the cross-section area in mm^2 and
    ``mass_per_m(density)`` the weight in kg/m.
    """

    @property
    def designation(self) -> str:
        """The stock designation (a standard name when the profile came
        from :func:`~cadbuildr.frames.standards.standard_profile`)."""
        named = self.__dict__.get("_designation")
        return named if named else self._default_designation()

    def _default_designation(self) -> str:
        return type(self).__name__

    @property
    def area(self) -> float:
        """Cross-section area in mm^2."""
        raise NotImplementedError(
            f"{type(self).__name__} does not define its cross-section area"
        )

    @property
    def outer_area(self) -> float:
        """Area inside the outer outline in mm^2 (an end cap's size)."""
        raise NotImplementedError(
            f"{type(self).__name__} does not define its outer outline area"
        )

    def mass_per_m(self, density: float = 7850.0) -> float:
        """Weight in kg per metre of length for a material ``density`` in
        kg/m^3 (steel 7850, aluminium 2700, softwood ~500). A profile with a
        catalog weight (``weight_per_m``) returns that instead."""
        catalog = getattr(self, "weight_per_m", None)
        if catalog is not None:
            return float(catalog)
        return self.area * 1e-6 * density

    def outer(self, sketch: Sketch) -> Any:
        raise NotImplementedError

    def inner(self, sketch: Sketch) -> Any | None:
        return None

    def outline(self) -> tuple[list[tuple[float, float]], list[tuple[float, float]] | None]:
        """The outer (and inner, for hollow sections) outline as points in
        (u, v), arcs densified — what weld lengths and section properties
        are computed from."""
        raise NotImplementedError(
            f"{type(self).__name__} does not define its outline points"
        )

    def section_properties(self):
        """Area, centroid, second moments and elastic moduli
        (:class:`~cadbuildr.frames.sections.SectionProperties`)."""
        from .sections import section_properties

        return section_properties(self)

    def support(self, du: float, dv: float) -> float:
        """Largest ``u*du + v*dv`` over the outline: how far the profile
        reaches in the cross-section direction ``(du, dv)``."""
        raise NotImplementedError

    @property
    def size(self) -> tuple[float, float]:
        """Bounding box ``(u extent, v extent)``."""
        return (
            self.support(1.0, 0.0) + self.support(-1.0, 0.0),
            self.support(0.0, 1.0) + self.support(0.0, -1.0),
        )

    def __str__(self) -> str:
        return self.designation


def _polygon(sketch: Sketch, pts: list[tuple[float, float]]) -> Any:
    pencil = sketch.pencil
    pencil.move_to(*pts[0])
    for p in pts[1:]:
        pencil.line_to(*p)
    return pencil.close()


class PolygonProfile(Profile):
    """A profile whose outline is a polygon (and optional polygon hole).

    ``outer_points`` / ``inner_points`` are the sharp polygon vertices;
    ``outer_radii`` / ``inner_radii`` (one per vertex, 0 = sharp) turn
    corners into true arcs — root and toe radii of rolled sections, corner
    radii of cold-formed tubes. A rounded loop is drawn as ONE
    ``CompactPolygon`` (lines + arcs); areas, supports and section
    properties use the rounded outline."""

    def outer_points(self) -> list[tuple[float, float]]:
        raise NotImplementedError

    def inner_points(self) -> list[tuple[float, float]] | None:
        return None

    def outer_radii(self) -> list[float] | None:
        return None

    def inner_radii(self) -> list[float] | None:
        return None

    def _loop(self, pts, radii):
        from .sections import rounded_polygon

        if pts is None:
            return None
        if radii and any(r > 0 for r in radii):
            return rounded_polygon(pts, radii)
        return [(u, v, 0.0) for u, v in pts]

    def outer_loop(self):
        """Outer outline as ``(u, v, bulge)`` vertices."""
        return self._loop(self.outer_points(), self.outer_radii())

    def inner_loop(self):
        return self._loop(self.inner_points(), self.inner_radii())

    def outline(self):
        from .sections import densify

        inner = self.inner_loop()
        return densify(self.outer_loop()), (densify(inner) if inner else None)

    def _draw(self, sketch: Sketch, pts, radii) -> Any:
        if radii and any(r > 0 for r in radii):
            from .sections import draw_loop, rounded_polygon

            return draw_loop(sketch, rounded_polygon(pts, radii))
        return _polygon(sketch, pts)

    def outer(self, sketch: Sketch) -> Any:
        return self._draw(sketch, self.outer_points(), self.outer_radii())

    def inner(self, sketch: Sketch) -> Any | None:
        pts = self.inner_points()
        return self._draw(sketch, pts, self.inner_radii()) if pts else None

    def support(self, du: float, dv: float) -> float:
        return max(u * du + v * dv for u, v in self.outline()[0])

    @property
    def outer_area(self) -> float:
        return _shoelace(self.outline()[0])

    @property
    def area(self) -> float:
        outer, inner = self.outline()
        return _shoelace(outer) - (_shoelace(inner) if inner else 0.0)


def _shoelace(pts: list[tuple[float, float]]) -> float:
    n = len(pts)
    return abs(
        sum(
            pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
            for i in range(n)
        )
        / 2.0
    )


def _rect(w: float, h: float) -> list[tuple[float, float]]:
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def _positive(**dims: float) -> None:
    for name, value in dims.items():
        if not value > 0:
            raise ValueError(f"{name} must be > 0, got {value}")


@dataclass(frozen=True, repr=False)
class RectTube(PolygonProfile):
    """Rectangular hollow section ``width`` (u) x ``height`` (v), wall ``wall``.

    ``corner_radius`` is the outer corner radius ``r_o`` (the inner one is
    ``r_o - wall``, never below 0). 0 (the default) draws sharp corners;
    ``standard_profile("SHS" / "RHS", ...)`` uses the EN 10219-2 values
    (:func:`en10219_corner_radius`)."""

    width: float
    height: float
    wall: float
    corner_radius: float = 0.0

    def __post_init__(self) -> None:
        _positive(width=self.width, height=self.height, wall=self.wall)
        if 2 * self.wall >= min(self.width, self.height):
            raise ValueError("RectTube wall is too thick for its size")
        if self.corner_radius < 0 or 2 * self.corner_radius > min(
            self.width, self.height
        ):
            raise ValueError(
                f"RectTube corner_radius {self.corner_radius:g} does not fit a "
                f"{self.width:g} x {self.height:g} section"
            )

    @property
    def inner_corner_radius(self) -> float:
        return max(self.corner_radius - self.wall, 0.0)

    def outer_radii(self):
        return [self.corner_radius] * 4 if self.corner_radius > 0 else None

    def inner_radii(self):
        r = self.inner_corner_radius
        return [r] * 4 if r > 0 else None

    def _default_designation(self) -> str:
        return f"RHS {self.width:g}x{self.height:g}x{self.wall:g}"

    def outer_points(self):
        return _rect(self.width, self.height)

    def inner_points(self):
        return _rect(self.width - 2 * self.wall, self.height - 2 * self.wall)


class SquareTube(RectTube):
    """Square hollow section ``size`` x ``size``, wall ``wall``."""

    def __init__(self, size: float, wall: float, corner_radius: float = 0.0):
        super().__init__(size, size, wall, corner_radius)

    def _default_designation(self) -> str:
        return f"SHS {self.width:g}x{self.width:g}x{self.wall:g}"


@dataclass(frozen=True, repr=False)
class RoundTube(Profile):
    """Circular hollow section of outside ``diameter`` and ``wall``."""

    diameter: float
    wall: float

    def __post_init__(self) -> None:
        _positive(diameter=self.diameter, wall=self.wall)
        if 2 * self.wall >= self.diameter:
            raise ValueError("RoundTube wall is too thick for its diameter")

    def _default_designation(self) -> str:
        return f"CHS {self.diameter:g}x{self.wall:g}"

    def outer(self, sketch: Sketch) -> Any:
        return Circle(Point(sketch, 0.0, 0.0), self.diameter / 2)

    def inner(self, sketch: Sketch) -> Any:
        return Circle(Point(sketch, 0.0, 0.0), self.diameter / 2 - self.wall)

    def outline(self):
        from .sections import circle_points

        return circle_points(self.diameter / 2), circle_points(
            self.diameter / 2 - self.wall
        )

    @property
    def outer_area(self) -> float:
        return math.pi / 4 * self.diameter**2

    @property
    def area(self) -> float:
        d_in = self.diameter - 2 * self.wall
        return math.pi / 4 * (self.diameter**2 - d_in**2)

    def support(self, du: float, dv: float) -> float:
        return self.diameter / 2 * math.hypot(du, dv)


@dataclass(frozen=True, repr=False)
class RoundBar(Profile):
    """Solid round bar of ``diameter``."""

    diameter: float

    def __post_init__(self) -> None:
        _positive(diameter=self.diameter)

    def _default_designation(self) -> str:
        return f"Round bar {self.diameter:g}"

    def outer(self, sketch: Sketch) -> Any:
        return Circle(Point(sketch, 0.0, 0.0), self.diameter / 2)

    def outline(self):
        from .sections import circle_points

        return circle_points(self.diameter / 2), None

    @property
    def area(self) -> float:
        return math.pi / 4 * self.diameter**2

    @property
    def outer_area(self) -> float:
        return self.area

    def support(self, du: float, dv: float) -> float:
        return self.diameter / 2 * math.hypot(du, dv)


@dataclass(frozen=True, repr=False)
class RectBar(PolygonProfile):
    """Solid rectangular bar / flat bar ``width`` (u) x ``height`` (v)."""

    width: float
    height: float

    def __post_init__(self) -> None:
        _positive(width=self.width, height=self.height)

    def _default_designation(self) -> str:
        return f"Flat bar {self.width:g}x{self.height:g}"

    def outer_points(self):
        return _rect(self.width, self.height)


@dataclass(frozen=True, repr=False)
class Angle(PolygonProfile):
    """Equal or unequal angle (L section): legs ``width`` (u) and ``height``
    (v), ``thickness``. The heel is at the -u/-v corner of the bounding box.

    ``root_radius`` (EN 10056-1 ``r1``, inside the heel) and ``toe_radius``
    (``r2``, the inner edge of each leg tip) round the rolled outline; 0
    (the default) is sharp. ``standard_profile("L", ...)`` sets the
    tabulated radii."""

    width: float
    height: float
    thickness: float
    root_radius: float = 0.0
    toe_radius: float = 0.0

    def __post_init__(self) -> None:
        _positive(width=self.width, height=self.height, thickness=self.thickness)
        if self.thickness >= min(self.width, self.height):
            raise ValueError("Angle thickness must be smaller than its legs")
        if self.root_radius < 0 or self.toe_radius < 0:
            raise ValueError("Angle radii must be >= 0")
        if self.toe_radius >= self.thickness:
            raise ValueError("Angle toe_radius must be smaller than its thickness")

    def outer_radii(self):
        r1, r2 = self.root_radius, self.toe_radius
        return [0.0, 0.0, r2, r1, r2, 0.0] if (r1 or r2) else None

    def _default_designation(self) -> str:
        return f"L {self.width:g}x{self.height:g}x{self.thickness:g}"

    def outer_points(self):
        w, h, t = self.width / 2, self.height / 2, self.thickness
        return [(-w, -h), (w, -h), (w, -h + t), (-w + t, -h + t), (-w + t, h), (-w, h)]


@dataclass(frozen=True, repr=False)
class Channel(PolygonProfile):
    """C / U channel: ``height`` (v, web depth) x ``width`` (u, flange
    width), web thickness ``web``, flange thickness ``flange``. The web is at
    -u, the flanges open towards +u.

    Rolled shape options (0 = sharp / parallel, the defaults):
    ``root_radius`` (web-to-flange fillet, ``r1`` / ``r``), ``toe_radius``
    (inner edge of the flange tip, ``r2``) and ``taper`` — the slope of the
    inner flange faces (0.08 = 8 % for DIN 1026-1 UPN; 0 for parallel-flange
    PFC / UPE). With a taper, ``flange`` is the thickness at half the flange
    width from the back of the web (DIN 1026-1, figure 1)."""

    height: float
    width: float
    web: float
    flange: float
    root_radius: float = 0.0
    toe_radius: float = 0.0
    taper: float = 0.0

    def __post_init__(self) -> None:
        _positive(
            height=self.height, width=self.width, web=self.web, flange=self.flange
        )
        if self.web >= self.width or 2 * self.flange >= self.height:
            raise ValueError("Channel web/flange too thick for its size")
        if min(self.root_radius, self.toe_radius, self.taper) < 0 or self.taper > 0.2:
            raise ValueError("Channel radii must be >= 0 and taper in 0..0.2")

    def outer_radii(self):
        r1, r2 = self.root_radius, self.toe_radius
        if not (r1 or r2):
            return None
        return [0.0, 0.0, r2, r1, r1, r2, 0.0, 0.0]

    def _default_designation(self) -> str:
        return f"C {self.height:g}x{self.width:g}x{self.web:g}/{self.flange:g}"

    def outer_points(self):
        w, h, tw, tf = self.width / 2, self.height / 2, self.web, self.flange
        k = self.taper
        toe = tf - k * w  # flange thickness at the tip (u = +w)
        root = tf + k * (w - tw)  # at the web face (u = -w + tw)
        return [
            (-w, -h),
            (w, -h),
            (w, -h + toe),
            (-w + tw, -h + root),
            (-w + tw, h - root),
            (w, h - toe),
            (w, h),
            (-w, h),
        ]


@dataclass(frozen=True, repr=False)
class IBeam(PolygonProfile):
    """I / H beam: ``height`` (v) x flange ``width`` (u), ``web`` and
    ``flange`` thicknesses, ``root_radius`` (web-to-flange fillet, 0 =
    sharp; the EN 10365 tables set it)."""

    height: float
    width: float
    web: float
    flange: float
    root_radius: float = 0.0

    def __post_init__(self) -> None:
        _positive(
            height=self.height, width=self.width, web=self.web, flange=self.flange
        )
        if self.web >= self.width or 2 * self.flange >= self.height:
            raise ValueError("IBeam web/flange too thick for its size")
        if self.root_radius < 0:
            raise ValueError("IBeam root_radius must be >= 0")

    def outer_radii(self):
        r = self.root_radius
        if not r:
            return None
        return [0.0, 0.0, 0.0, r, r, 0.0, 0.0, 0.0, 0.0, r, r, 0.0]

    def _default_designation(self) -> str:
        return f"I {self.height:g}x{self.width:g}x{self.web:g}/{self.flange:g}"

    def outer_points(self):
        w, h, tw, tf = self.width / 2, self.height / 2, self.web / 2, self.flange
        return [
            (-w, -h),
            (w, -h),
            (w, -h + tf),
            (tw, -h + tf),
            (tw, h - tf),
            (w, h - tf),
            (w, h),
            (-w, h),
            (-w, h - tf),
            (-tw, h - tf),
            (-tw, -h + tf),
            (-w, -h + tf),
        ]


# Actual (dressed) sizes of North American dimensional lumber, in inches
# (thickness, depth) — same table as cadbuildr.wood.standards.
LUMBER_SIZES_IN: dict[str, tuple[float, float]] = {
    "1x2": (0.75, 1.5),
    "1x4": (0.75, 3.5),
    "1x6": (0.75, 5.5),
    "2x2": (1.5, 1.5),
    "2x3": (1.5, 2.5),
    "2x4": (1.5, 3.5),
    "2x6": (1.5, 5.5),
    "2x8": (1.5, 7.25),
    "2x10": (1.5, 9.25),
    "2x12": (1.5, 11.25),
    "4x4": (3.5, 3.5),
    "6x6": (5.5, 5.5),
}


class Lumber(RectBar):
    """Dimensional lumber by nominal size (``"2x4"``…): the actual dressed
    thickness runs along u, the depth along v (on edge, towards ``up``)."""

    def __init__(self, nominal: str):
        key = nominal.lower().replace(" ", "")
        if key not in LUMBER_SIZES_IN:
            raise ValueError(
                f"unknown lumber size {nominal!r}; known: {', '.join(LUMBER_SIZES_IN)}"
            )
        t, d = LUMBER_SIZES_IN[key]
        super().__init__(t * INCH, d * INCH)
        object.__setattr__(self, "nominal", key)

    def _default_designation(self) -> str:
        return f"Lumber {self.nominal}"  # type: ignore[attr-defined]
