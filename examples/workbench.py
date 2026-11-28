"""A welded workbench base from the library configurables.

- ``TableFrame``: 1500 x 700 top on four SHS 40x40x3 legs, a shelf frame at
  150 mm, bolt-down ``BasePlate`` feet connected to the leg ends;
- a row of M8 holes along the front top rail (each one a ``ScrewHole``
  interface a screw mates onto) for a vice or a worktop;
- cut list, weight and a 6 m stock plan for ordering.

Run it with ``python workbench.py`` or open it in the Prototype app.
"""

from cadbuildr.foundation import show
from cadbuildr.frames import STEEL_DENSITY, TableFrame

bench = TableFrame(
    width=1500,
    depth=700,
    height=900,
    section="SHS 40x40x3",
    shelf_height=150,
    feet="base_plate",
)

# Worktop fixing holes on the front rail's top face (member_1, -Y side).
front = bench.member("member_1")
front.drill("top", size="M8", count=6, margin=80)

print(bench.cut_list_table())
print(f"\nweight: {bench.weight(STEEL_DENSITY):.1f} kg")
print(bench.stock_plan(stock_length=6000, kerf=3).table())

show(bench)
