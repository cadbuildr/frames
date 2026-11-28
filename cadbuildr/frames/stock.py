"""Stock planning: nest a frame's cut pieces into stock bars.

``stock_plan(pieces, stock_length=6000, kerf=3)`` packs pieces of the same
profile into as few bars as it can (first-fit decreasing: longest piece
first, into the first bar it still fits). It is a quick ordering estimate,
not an optimiser — the usual result is within one bar of the best packing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

# Common stock lengths in mm (6 m European bar, 20 ft / 24 ft US stick).
STOCK_LENGTH_6M = 6000.0
STOCK_LENGTH_20FT = 6096.0
STOCK_LENGTH_24FT = 7315.2


@dataclass(frozen=True)
class Piece:
    """One cut piece: ``profile`` designation, ``length`` (mm), ``member``
    name."""

    profile: str
    length: float
    member: str


@dataclass
class StockBar:
    """One stock bar and the pieces cut from it (in cutting order)."""

    profile: str
    length: float
    kerf: float
    pieces: list[Piece] = field(default_factory=list)

    @property
    def used(self) -> float:
        """Length consumed by the pieces and one kerf per cut."""
        return sum(p.length for p in self.pieces) + self.kerf * len(self.pieces)

    @property
    def offcut(self) -> float:
        return max(0.0, self.length - self.used)

    def fits(self, piece: Piece) -> bool:
        # the last piece needs no kerf if it uses the bar to its end
        return self.used + piece.length <= self.length + 1e-9


@dataclass
class StockPlan:
    """Bars per profile and the totals."""

    bars: list[StockBar]
    stock_length: float
    kerf: float

    def count(self, profile: str | None = None) -> int:
        return len([b for b in self.bars if profile is None or b.profile == profile])

    @property
    def waste(self) -> float:
        """Total offcut length (mm)."""
        return sum(b.offcut for b in self.bars)

    @property
    def utilisation(self) -> float:
        """Fraction of the bought stock that ends up in pieces."""
        bought = sum(b.length for b in self.bars)
        return (
            sum(p.length for b in self.bars for p in b.pieces) / bought
            if bought
            else 0.0
        )

    def table(self) -> str:
        """Plain-text summary: one line per bar."""
        lines = [f"Stock {self.stock_length:g} mm, kerf {self.kerf:g} mm"]
        for i, b in enumerate(self.bars, 1):
            cuts = " + ".join(f"{p.length:.1f}" for p in b.pieces)
            lines.append(f"bar {i}  {b.profile}: {cuts}  (offcut {b.offcut:.1f})")
        lines.append(
            f"{len(self.bars)} bars, {self.utilisation * 100:.1f}% used, "
            f"{self.waste:.0f} mm offcut"
        )
        return "\n".join(lines)


class PieceTooLongError(ValueError):
    """A cut piece longer than the stock bar."""


def stock_plan(
    pieces: Iterable[Piece],
    stock_length: float = STOCK_LENGTH_6M,
    kerf: float = 3.0,
) -> StockPlan:
    """Pack ``pieces`` into bars of ``stock_length`` (first-fit decreasing,
    per profile), ``kerf`` mm lost per cut."""
    if not stock_length > 0:
        raise ValueError(f"stock_length must be > 0, got {stock_length}")
    if kerf < 0:
        raise ValueError(f"kerf must be >= 0, got {kerf}")
    items: Sequence[Piece] = sorted(pieces, key=lambda p: (p.profile, -p.length))
    bars: list[StockBar] = []
    for piece in items:
        if piece.length > stock_length + 1e-9:
            raise PieceTooLongError(
                f"{piece.member} ({piece.profile}) is {piece.length:.1f} mm, longer "
                f"than the {stock_length:g} mm stock; use longer stock or split it"
            )
        for bar in bars:
            if bar.profile == piece.profile and bar.fits(piece):
                bar.pieces.append(piece)
                break
        else:
            bars.append(StockBar(piece.profile, stock_length, kerf, [piece]))
    return StockPlan(bars, stock_length, kerf)
