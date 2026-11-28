"""A trailer-style ladder frame: RHS 100x50x4 side rails, UPN 100 cross
members, an A-frame drawbar meeting at the coupling, gussets at the nose.

- the rails run through; cross members are butted between them (square
  saw cuts), the drawbar arms land on the rail front ends at an angle
  (compound saw angle in the cut list) and meet each other at the nose
  (one runs through, the other is butted at an angle);
- a coupling plate (gusset) under the nose;
- payload check: 750 kg spread over the 2.4 m deck, carried by the two
  rails as simple spans (``apply_udl``, L/250 and yield in ``__checks__``);
- prints the cut list (saw angle per end), the ISO 2553 weld list, the BOM
  with the total weld length and the 6 m stock plan.

Estimated: a typical 2400 x 1200 mm utility trailer layout for
illustration — not a homologated design (axle, suspension and coupling
are not modelled; the rails are checked as spans between the deck ends).
"""

from cadbuildr.foundation import show
from cadbuildr.frames import Frame, Gusset, Line3D, profile_from_designation

LENGTH, WIDTH, DRAWBAR = 2400.0, 1200.0, 1100.0
RAIL = profile_from_designation("RHS 100x50x4")
CROSS = profile_from_designation("UPN100")
ARM = profile_from_designation("RHS 80x40x3")

x0, x1, y = -LENGTH / 2, LENGTH / 2, WIDTH / 2
nose = (x0 - DRAWBAR, 0.0, 0.0)
rails = [Line3D((x0, -y, 0.0), (x1, -y, 0.0)), Line3D((x0, y, 0.0), (x1, y, 0.0))]
crosses = [Line3D((x, -y, 0.0), (x, y, 0.0)) for x in (x0, x0 + 600, x0 + 1200, x0 + 1800, x1)]
arms = [Line3D(nose, (x0, -y, 0.0)), Line3D(nose, (x0, y, 0.0))]

trailer = Frame(
    rails + crosses + arms,
    [RAIL, RAIL] + [CROSS] * len(crosses) + [ARM, ARM],
    corner="butt",
    gussets=[Gusset(at=nose, size=150, thickness=8, position="bottom")],
)

# 750 kg payload over the deck, half on each rail (kN/m).
payload_udl = 750 * 9.81 / (LENGTH / 1000.0) / 2 / 1000.0
checks = [trailer.apply_udl(i, payload_udl, span=LENGTH, grade="S355") for i in (0, 1)]

print(trailer.cut_list_table())
print()
print(trailer.weld_table())
print()
print(trailer.bom_table())
print()
for c in checks:
    print(c.summary())
print()
print(trailer.stock_plan(stock_length=6000, kerf=3).table())

show(trailer)
