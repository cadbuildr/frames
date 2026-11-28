"""Weld annotations as metadata: per-joint welds with ISO 2553 symbols as
data, fillet sizes, lengths, deposit mass and the BOM totals.

No weld beads are modelled as solids (the joints stay clean for mating and
interference checks); each :class:`Weld` carries what a drawing's weld
symbol says and what the shop needs to order wire and time.

Sources:

- ISO 2553:2019 "Welding and allied processes — Symbolic representation on
  drawings — Welded joints": elementary symbols (fillet, square butt,
  single-V butt, single-bevel butt…), supplementary symbols (weld all
  round, field weld), the size prefix ``a`` (fillet throat) / ``z`` (fillet
  leg) / ``s`` (butt penetration) and the length after the symbol. This
  module stores them as fields; ``WeldSymbol.text()`` renders the
  designation the way the symbol's dimensions read (``a4 ◺ 120``).
- ISO 4063:2023 process reference numbers (135 = MAG with solid wire,
  141 = TIG, 111 = MMA, 136 = MAG flux-cored).
- ISO 5817:2023 quality levels B / C / D (the symbol's tail).
- EN 1993-1-8:2005 4.5.2(2): a fillet weld's effective throat should not
  be less than 3 mm.
- Fillet geometry: a mitre-faced fillet of throat ``a`` has leg
  ``z = a * sqrt(2)`` and cross-section ``z^2 / 2 = a^2``.

Estimated (default sizes; set your own with ``Frame.welds(throat=...)``):
``a = 0.7 x`` the thinner part, rounded to 0.5 mm, not below 3 mm unless
the thinner part itself is thinner (thin-wall tube: ``a = t``, flagged by
an info check). Butt-weld deposit areas assume ISO 9692-1 preparations:
square butt with a gap equal to the wall up to 3 mm, single-V with the
bevel's angle and root face.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

# ISO 2553 elementary symbols used by frames, with a Unicode approximation
# of the glyph (a drawing tool draws the real symbol from ``name``).
ISO_2553_ELEMENTARY: dict[str, dict[str, str]] = {
    "fillet": {"glyph": "◺", "description": "fillet weld"},
    "square_butt": {"glyph": "‖", "description": "square butt weld"},
    "single_v_butt": {"glyph": "V", "description": "single-V butt weld"},
    "single_bevel_butt": {"glyph": "⊾", "description": "single-bevel butt weld"},
    "plug": {"glyph": "⊓", "description": "plug / slot weld"},
}
ISO_2553_SUPPLEMENTARY: dict[str, str] = {
    "all_around": "○ weld all round",
    "field": "⚑ field (site) weld",
    "flat": "— flat (flush) finish",
    "convex": "⌒ convex finish",
    "concave": "⌣ concave finish",
}
ISO_4063_PROCESSES: dict[int, str] = {
    111: "manual metal arc (MMA)",
    135: "MAG, solid wire",
    136: "MAG, flux-cored wire",
    141: "TIG",
}

MIN_FILLET_THROAT = 3.0  # EN 1993-1-8 4.5.2(2)
WELD_METAL_DENSITY = 7850.0  # kg/m^3, steel filler


def _half(x: float) -> float:
    return round(x * 2.0) / 2.0


def default_throat(t_min: float) -> float:
    """Default fillet throat ``a`` (mm) for the thinner part ``t_min``:
    0.7 t rounded to 0.5 mm, at least 3 mm (EN 1993-1-8 4.5.2(2)) unless
    the part is thinner than that. Estimated shop default."""
    a = _half(0.7 * t_min)
    if a < MIN_FILLET_THROAT:
        a = min(MIN_FILLET_THROAT, max(_half(t_min), 0.5))
    return a


@dataclass(frozen=True)
class WeldSymbol:
    """An ISO 2553 weld symbol as data.

    ``elementary``: a key of :data:`ISO_2553_ELEMENTARY`. ``size`` with
    ``size_kind`` ``"a"`` (fillet throat), ``"z"`` (fillet leg) or ``"s"``
    (butt penetration). ``length``: weld length (mm, ``None`` = full
    length). ``side``: ``"arrow"`` / ``"other"`` / ``"both"`` side of the
    reference line. ``all_around`` / ``field`` supplementary symbols;
    ``process`` (ISO 4063 number) and ``quality`` (ISO 5817 level) for the
    tail."""

    elementary: str
    size: float | None = None
    size_kind: Literal["a", "z", "s"] = "a"
    length: float | None = None
    side: Literal["arrow", "other", "both"] = "arrow"
    all_around: bool = False
    field: bool = False
    process: int | None = 135
    quality: str | None = "C"

    def __post_init__(self) -> None:
        if self.elementary not in ISO_2553_ELEMENTARY:
            raise ValueError(
                f"unknown ISO 2553 elementary symbol {self.elementary!r}; known: "
                f"{', '.join(ISO_2553_ELEMENTARY)}"
            )
        if self.size_kind not in ("a", "z", "s"):
            raise ValueError("size_kind must be 'a', 'z' or 's'")
        if self.quality is not None and self.quality not in ("B", "C", "D"):
            raise ValueError("quality must be an ISO 5817 level B, C or D")

    def text(self) -> str:
        """The symbol's dimensions as written on the reference line:
        ``a4 ◺ 120``, plus the supplementary marks and the tail."""
        glyph = ISO_2553_ELEMENTARY[self.elementary]["glyph"]
        parts = []
        if self.size is not None:
            parts.append(f"{self.size_kind}{self.size:g}")
        parts.append(glyph)
        if self.length is not None:
            parts.append(f"{self.length:.0f}")
        text = " ".join(parts)
        marks = []
        if self.all_around:
            marks.append("all round")
        if self.field:
            marks.append("field")
        if self.side == "both":
            marks.append("both sides")
        elif self.side == "other":
            marks.append("other side")
        if marks:
            text += f" ({', '.join(marks)})"
        tail = []
        if self.process:
            tail.append(str(self.process))
        if self.quality:
            tail.append(f"ISO 5817-{self.quality}")
        return text + (f" < {' / '.join(tail)}" if tail else "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard": "ISO 2553",
            "elementary": self.elementary,
            "glyph": ISO_2553_ELEMENTARY[self.elementary]["glyph"],
            "size": self.size,
            "size_kind": self.size_kind,
            "length": self.length,
            "side": self.side,
            "all_around": self.all_around,
            "field": self.field,
            "process": self.process,
            "quality": self.quality,
            "text": self.text(),
        }


@dataclass(frozen=True)
class Weld:
    """One welded joint.

    ``joint`` names it (``"junction 3"``, ``"gusset_1"``, ``"end_cap_2"``);
    ``parts`` the welded components; ``kind`` the weld type (``fillet``,
    ``square_butt``, ``single_v_butt``); ``length`` the weld run per side
    (mm) and ``runs`` how many sides are welded (2 for a gusset welded both
    faces). ``throat`` is ``a`` for fillets, the penetration for butts.
    ``symbol`` is the ISO 2553 symbol as data."""

    joint: str
    parts: tuple[str, ...]
    kind: str
    length: float
    throat: float
    runs: int = 1
    symbol: WeldSymbol | None = None
    deposit_area: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def leg(self) -> float | None:
        """Fillet leg ``z = a * sqrt(2)``."""
        return self.throat * math.sqrt(2.0) if self.kind == "fillet" else None

    @property
    def total_length(self) -> float:
        return self.length * self.runs

    @property
    def area(self) -> float:
        """Deposit cross-section (mm^2): ``a^2`` for a fillet, the groove
        area for butts."""
        if self.deposit_area is not None:
            return self.deposit_area
        return self.throat**2

    @property
    def volume(self) -> float:
        return self.area * self.total_length

    def mass(self, density: float = WELD_METAL_DENSITY) -> float:
        """Deposited weld metal in kg."""
        return self.volume * 1e-9 * density

    def to_dict(self) -> dict[str, Any]:
        return {
            "joint": self.joint,
            "parts": list(self.parts),
            "kind": self.kind,
            "length_mm": self.length,
            "runs": self.runs,
            "total_length_mm": self.total_length,
            "throat_mm": self.throat,
            "leg_mm": self.leg,
            "deposit_kg": self.mass(),
            "symbol": self.symbol.to_dict() if self.symbol else None,
            "notes": list(self.notes),
        }


def fillet(
    joint: str,
    parts: tuple[str, ...],
    length: float,
    t_min: float,
    throat: float | None = None,
    runs: int = 1,
    all_around: bool = False,
    process: int | None = 135,
) -> Weld:
    """A fillet weld with the default throat for ``t_min`` unless given."""
    a = float(throat) if throat is not None else default_throat(t_min)
    notes = ()
    if a < MIN_FILLET_THROAT:
        notes = (
            f"throat a{a:g} is below the 3 mm minimum of EN 1993-1-8 4.5.2(2) "
            f"(thin {t_min:g} mm part); confirm with the designer",
        )
    symbol = WeldSymbol(
        "fillet",
        size=a,
        size_kind="a",
        length=None if all_around else length,
        side="both" if runs == 2 else "arrow",
        all_around=all_around,
        process=process,
    )
    return Weld(joint, parts, "fillet", length, a, runs, symbol, None, notes)


def butt(
    joint: str,
    parts: tuple[str, ...],
    length: float,
    wall: float,
    bevel: Any = None,
    all_around: bool = True,
    process: int | None = 135,
) -> Weld:
    """A full-penetration butt weld: square butt (gap = wall, up to 3 mm)
    or single-V when ``bevel`` (an ``end_prep.Bevel``) is given."""
    if bevel is None:
        kind = "square_butt"
        gap = min(wall, 3.0)
        area = wall * gap
    else:
        kind = "single_v_butt"
        h = max(wall - bevel.root_face, 0.0)
        # two bevelled ends meet: V of half-angle = bevel angle, 1 mm gap
        area = h * h * math.tan(math.radians(bevel.angle)) + wall * 1.0
    symbol = WeldSymbol(
        kind,
        size=wall,
        size_kind="s",
        length=None if all_around else length,
        all_around=all_around,
        process=process,
    )
    return Weld(joint, parts, kind, length, wall, 1, symbol, area)


def weld_summary(welds: list[Weld]) -> dict[str, dict[str, float]]:
    """Totals per weld type and size: ``{"fillet a3": {"length_mm":
    ..., "deposit_kg": ..., "count": ...}}``."""
    out: dict[str, dict[str, float]] = {}
    for w in welds:
        key = f"{w.kind} {'a' if w.kind == 'fillet' else 's'}{w.throat:g}"
        row = out.setdefault(key, {"length_mm": 0.0, "deposit_kg": 0.0, "count": 0})
        row["length_mm"] += w.total_length
        row["deposit_kg"] += w.mass()
        row["count"] += 1
    return out


def format_welds(welds: list[Weld]) -> str:
    rows = [("Joint", "Parts", "Weld", "Length", "Runs", "ISO 2553")]
    for w in welds:
        rows.append(
            (
                w.joint,
                ", ".join(w.parts),
                f"{w.kind} {'a' if w.kind == 'fillet' else 's'}{w.throat:g}",
                f"{w.length:.0f}",
                str(w.runs),
                w.symbol.text() if w.symbol else "",
            )
        )
    widths = [max(len(r[c]) for r in rows) for c in range(len(rows[0]))]
    lines = ["  ".join(c.ljust(wd) for c, wd in zip(r, widths)).rstrip() for r in rows]
    lines.insert(1, "  ".join("-" * wd for wd in widths))
    total = sum(w.total_length for w in welds)
    lines.append(f"total weld length: {total:.0f} mm")
    return "\n".join(lines)
