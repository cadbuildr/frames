"""A welded workbench frame: SHS 50x50x3 legs and rails, a mitred angle
lip for the worktop, a round-tube footrest, anchor-bolt base plates.

- legs run through, top and shelf rails are butted onto the legs
  (``_LegsThrough``-style ``ConnectorRule``), the CHS 26.9 footrest is
  butted onto the legs' flat faces (a round tube onto a flat face);
- a second frame of EN 10056-1 L50x50x5 angle, mitred at the corners,
  sits on the top rails as the worktop lip (heel on the outside);
- ``AnchorBasePlate`` feet (4 x M12, EN 1090-2 normal holes) mate onto the
  leg ends and are welded all round;
- the front top rail carries 3 kN/m as a simple span (``apply_udl``): the
  ``__checks__`` hook reports L/250 deflection and yield;
- prints the cut list with saw angles, the weld list (ISO 2553 symbols),
  the BOM with the total weld length, a load table and the 6 m stock plan.

Estimated: overall sizes are a typical 1500 x 700 x 850 mm bench, not a
published design.
"""

from cadbuildr.foundation import Assembly, StringParameter, show
from cadbuildr.frames import (
    AnchorBasePlate,
    ConnectorRule,
    Frame,
    Line3D,
    format_load_table,
    load_table,
    polyline,
    profile_from_designation,
    rectangle,
)

WIDTH, DEPTH, HEIGHT = 1500.0, 700.0, 850.0
SHS = profile_from_designation("SHS 50x50x3")
CHS = profile_from_designation("CHS 26.9x2")
ANGLE = profile_from_designation("L50x50x5")


class LegsThrough(ConnectorRule):
    """Vertical members run through every node they reach."""

    def choose_through(self, node, ends):
        for i, e in enumerate(ends):
            if abs(abs(e.into[2]) - 1.0) < 1e-9:
                return i
        return None


corners = [(-WIDTH / 2, -DEPTH / 2), (WIDTH / 2, -DEPTH / 2), (WIDTH / 2, DEPTH / 2), (-WIDTH / 2, DEPTH / 2)]
top_z = HEIGHT - 25.0  # rail centre line: top face at HEIGHT
skeleton = polyline([(x, y, top_z) for x, y in corners], closed=True)
skeleton += [Line3D((x, y, top_z), (x, y, 0.0)) for x, y in corners]
skeleton += polyline([(x, y, 180.0) for x, y in corners], closed=True)
# footrest between the front legs, 300 mm up
skeleton.append(Line3D((-WIDTH / 2, -DEPTH / 2, 300.0), (WIDTH / 2, -DEPTH / 2, 300.0)))
profiles = [SHS] * 12 + [CHS]

bench = Frame(skeleton, profiles, corner="butt", connector=LegsThrough())

# Worktop lip: L50x50x5 mitred rectangle on the top rails (heel outside).
lip = Frame(rectangle(WIDTH, DEPTH, center=(0.0, 0.0, HEIGHT + 25.0)), ANGLE, corner="miter")

# Bolt-down feet on the leg ends.
bench.feet = []
for i in range(4, 8):
    leg = bench.members[i]
    plate = AnchorBasePlate(
        column="SHS 50x50x3", width=150, depth=150, thickness=8, anchor="M12", edge=25
    )
    plate.name = StringParameter(value=f"foot_{i - 3}")
    plate.welded_to = leg
    bench.connect(plate.interface("top"), leg.interface("end_b"))
    bench.feet.append(plate)
bench.refresh_bom_lines()

# 3 kN/m on the front top rail (worktop + a vice), simply supported 1500.
check = bench.apply_udl("member_1", 3.0, span=WIDTH, grade="S235")

workbench = Assembly()
workbench.add_component(bench)
workbench.add_component(lip)

print(bench.cut_list_table())
print(lip.cut_list_table())
print()
print(bench.weld_table())
print(lip.weld_table())
print()
print(bench.bom_table())
print()
print(check.summary())
print(format_load_table(SHS, load_table(SHS, [1000, 1500, 2000])))
print()
print(bench.stock_plan(stock_length=6000, kerf=3).table())

show(workbench)
