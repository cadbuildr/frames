"""Load check of a simply supported member under a uniformly distributed
load (UDL): deflection against span / 250 and bending stress against yield.

Formulas (simply supported span ``L``, UDL ``w`` in N/mm = kN/m):

- mid-span deflection ``delta = 5 w L^4 / (384 E I)`` and maximum moment
  ``M = w L^2 / 8`` (Roark's Formulas for Stress and Strain, 8th ed.,
  Table 8.1 case 2e, uniform load on a simply supported beam);
- elastic bending resistance ``M_c,Rd = W_el f_y / gamma_M0`` with
  ``gamma_M0 = 1.0`` (EN 1993-1-1:2005 6.2.5(2) eq. 6.14 for class 3
  sections and 6.1(1) recommended value) — conservative for class 1 / 2
  sections that could use ``W_pl``;
- ``E = 210 000 N/mm^2`` (EN 1993-1-1 3.2.6(1));
- yield strengths ``f_y`` for t <= 40 mm (EN 1993-1-1 Table 3.1, EN 10025-2
  grades): S235 235, S275 275, S355 355 N/mm^2; EN 10219 hollow sections
  (EN 1993-1-1 Table 3.1, S235H / S275H / S355H) use the same values;
- deflection limit ``L / 250``: the usual Eurocode national-annex limit for
  members without brittle finishes (EN 1990 A1.4.3 leaves the value to the
  national annex). Pass ``limit_ratio=`` for another one.

Not checked (stated in every result): lateral-torsional buckling (assumes
the compression flange is restrained), shear, local buckling of slender
walls, web bearing at the supports, dynamic loads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .profiles import Profile

E_STEEL = 210_000.0  # N/mm^2
GAMMA_M0 = 1.0
DEFLECTION_LIMIT_RATIO = 250.0
G = 9.81  # m/s^2

STEEL_GRADES: dict[str, float] = {"S235": 235.0, "S275": 275.0, "S355": 355.0}

NOT_CHECKED = (
    "not checked: lateral-torsional buckling (compression flange assumed "
    "restrained), shear, local buckling, web bearing, dynamic loads"
)


class LoadCheckError(ValueError):
    """Bad input to the span check (span <= 0, unknown grade…)."""


def yield_strength(grade: str | float) -> float:
    if isinstance(grade, (int, float)):
        if grade <= 0:
            raise LoadCheckError(f"yield strength must be > 0, got {grade}")
        return float(grade)
    try:
        return STEEL_GRADES[grade.upper()]
    except KeyError:
        raise LoadCheckError(
            f"unknown steel grade {grade!r}; known: {', '.join(STEEL_GRADES)} "
            "(or pass f_y in N/mm^2)"
        ) from None


@dataclass(frozen=True)
class SpanCheck:
    """Result of :func:`simple_span_udl`. Units: mm, N/mm (= kN/m),
    N/mm^2. ``udl_total`` includes the self-weight when it was asked for."""

    designation: str
    span: float
    udl: float
    self_weight: float
    udl_total: float
    deflection: float
    deflection_limit: float
    stress: float
    yield_strength: float
    i_u: float
    w_u: float

    @property
    def deflection_utilisation(self) -> float:
        return self.deflection / self.deflection_limit

    @property
    def stress_utilisation(self) -> float:
        return self.stress * GAMMA_M0 / self.yield_strength

    @property
    def utilisation(self) -> float:
        return max(self.deflection_utilisation, self.stress_utilisation)

    @property
    def governs(self) -> str:
        return (
            "deflection"
            if self.deflection_utilisation >= self.stress_utilisation
            else "yield"
        )

    @property
    def ok(self) -> bool:
        return self.utilisation <= 1.0 + 1e-9

    def summary(self) -> str:
        return (
            f"{self.designation} span {self.span:g} mm, UDL {self.udl_total:.3g} kN/m "
            f"(incl. self-weight {self.self_weight:.3g}): deflection "
            f"{self.deflection:.2f} mm vs L/{self.span / self.deflection_limit:g} = "
            f"{self.deflection_limit:.2f} mm ({self.deflection_utilisation:.0%}), "
            f"stress {self.stress:.0f} vs f_y {self.yield_strength:g} N/mm^2 "
            f"({self.stress_utilisation:.0%})"
        )

    def issues(self, component: str | None = None) -> list[dict[str, Any]]:
        """Check issues (``Assembly.check()`` shape) for a ``__checks__``
        hook: one error per failed limit, else one info line."""
        from cadbuildr.foundation import issue

        comps = [component] if component else []
        out = []
        if self.deflection_utilisation > 1.0 + 1e-9:
            out.append(
                issue(
                    "error",
                    "frames.load.deflection",
                    f"{self.summary()} -> deflection exceeds L/"
                    f"{self.span / self.deflection_limit:g}",
                    components=comps,
                    fix="use a deeper section, shorten the span or add a support",
                )
            )
        if self.stress_utilisation > 1.0 + 1e-9:
            out.append(
                issue(
                    "error",
                    "frames.load.yield",
                    f"{self.summary()} -> bending stress exceeds f_y",
                    components=comps,
                    fix="use a stronger section or grade, or reduce the load",
                )
            )
        if not out:
            out.append(
                issue(
                    "info",
                    "frames.load.ok",
                    f"{self.summary()}; {NOT_CHECKED}",
                    components=comps,
                )
            )
        for i in out:
            i["data"] = {
                "span_mm": self.span,
                "udl_kN_per_m": self.udl_total,
                "deflection_mm": self.deflection,
                "deflection_limit_mm": self.deflection_limit,
                "stress_N_per_mm2": self.stress,
                "f_y_N_per_mm2": self.yield_strength,
                "utilisation": self.utilisation,
                "governs": self.governs,
            }
        return out


def simple_span_udl(
    profile: Profile,
    span: float,
    udl: float,
    grade: str | float = "S235",
    limit_ratio: float = DEFLECTION_LIMIT_RATIO,
    self_weight: bool = True,
    density: float = 7850.0,
    e_modulus: float = E_STEEL,
) -> SpanCheck:
    """Check ``profile`` as a simply supported beam of ``span`` mm under a
    UDL of ``udl`` kN/m (= N/mm) bending about its u axis (load along v,
    the frame's up side). ``self_weight`` adds the member's own weight."""
    if not span > 0:
        raise LoadCheckError(f"span must be > 0 mm, got {span}")
    if udl < 0:
        raise LoadCheckError(f"udl must be >= 0 kN/m, got {udl}")
    if not limit_ratio > 0:
        raise LoadCheckError("limit_ratio must be > 0")
    fy = yield_strength(grade)
    props = profile.section_properties()
    sw = profile.mass_per_m(density) * G / 1000.0 if self_weight else 0.0  # kN/m
    w = udl + sw
    deflection = 5.0 * w * span**4 / (384.0 * e_modulus * props.i_u)
    moment = w * span**2 / 8.0
    return SpanCheck(
        designation=profile.designation,
        span=float(span),
        udl=float(udl),
        self_weight=sw,
        udl_total=w,
        deflection=deflection,
        deflection_limit=span / limit_ratio,
        stress=moment / props.w_u,
        yield_strength=fy,
        i_u=props.i_u,
        w_u=props.w_u,
    )


@dataclass(frozen=True)
class LoadTableRow:
    """Allowable UDL (kN/m, net of self-weight) of one span: by deflection,
    by yield, and the governing (smaller) one."""

    span: float
    by_deflection: float
    by_yield: float

    @property
    def allowable(self) -> float:
        return min(self.by_deflection, self.by_yield)

    @property
    def governs(self) -> str:
        return "deflection" if self.by_deflection <= self.by_yield else "yield"


def load_table(
    profile: Profile,
    spans: Sequence[float],
    grade: str | float = "S235",
    limit_ratio: float = DEFLECTION_LIMIT_RATIO,
    density: float = 7850.0,
    e_modulus: float = E_STEEL,
) -> list[LoadTableRow]:
    """Safe-load table: for each span, the largest UDL (kN/m, on top of the
    self-weight) meeting ``L / limit_ratio`` and ``f_y`` — the inverse of
    :func:`simple_span_udl`."""
    fy = yield_strength(grade)
    props = profile.section_properties()
    sw = profile.mass_per_m(density) * G / 1000.0
    rows = []
    for span in spans:
        if not span > 0:
            raise LoadCheckError(f"span must be > 0 mm, got {span}")
        w_d = (span / limit_ratio) * 384.0 * e_modulus * props.i_u / (5.0 * span**4)
        w_y = 8.0 * fy / GAMMA_M0 * props.w_u / span**2
        rows.append(LoadTableRow(float(span), max(w_d - sw, 0.0), max(w_y - sw, 0.0)))
    return rows


def format_load_table(profile: Profile, rows: Sequence[LoadTableRow]) -> str:
    lines = [
        f"{profile.designation}: allowable UDL (kN/m, net of self-weight)",
        "Span mm   defl.    f_y      allowable  governs",
    ]
    for r in rows:
        lines.append(
            f"{r.span:<9g} {r.by_deflection:<8.2f} {r.by_yield:<8.2f} "
            f"{r.allowable:<10.2f} {r.governs}"
        )
    return "\n".join(lines)
