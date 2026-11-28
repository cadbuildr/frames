"""Four small frames showing every cadbuildr.frames feature.

- a mitered square-tube rectangle with a gusset in each corner,
- a welded table base (butted corners where three members meet, capped feet),
- a round-tube hand rail with a bent end, a coped post and an end cap,
- a channel bracket with a butt corner and a gusset.

Each frame is laid out where it belongs (``rectangle(center=...)``,
``offset_skeleton``) and grounded in the scene — no transforms. Run it with
``python frames_showcase.py`` (prints the cut lists) or open it in the
Prototype app / Playground to see it.
"""

from cadbuildr.foundation import Assembly, show
from cadbuildr.frames import (
    Arc3D,
    Channel,
    EndCap,
    Frame,
    Gusset,
    Line3D,
    RoundTube,
    SquareTube,
    offset_skeleton,
    polyline,
    rectangle,
)

scene = Assembly()

# 1. Mitered rectangle, 10 mm square tube, a gusset in every corner.
mitered = Frame(
    skeleton=rectangle(120, 80, center=(0, -170, 0)),
    profile=SquareTube(10, 1),
    corner="miter",
    gussets=[
        Gusset(at=(x, y - 170, 0), size=20, thickness=1.5)
        for x in (-60, 60)
        for y in (-40, 40)
    ],
)

# 2. Table base: top rectangle + 4 legs. Three members meet at each top
#    corner, so the longest (the 100 mm rail) runs through and the others are
#    butted to it. The legs' free feet get end caps.
corners = [(-50, -90), (50, -90), (50, -30), (-50, -30)]
top = polyline([(x, y, 60) for x, y in corners], closed=True)
legs = [Line3D((x, y, 60), (x, y, 0)) for x, y in corners]
table = Frame(top + legs, SquareTube(8, 1), end_caps=EndCap(thickness=2))

# 3. Hand rail: round tube with a 20 mm bend, a post coped to the rail and an
#    end cap on the open end.
rail_skeleton = [
    Line3D((-60, 0, 40), (40, 0, 40)),
    Arc3D((40, 0, 40), (60, 0, 20), (40, 0, 0)),
    Line3D((-10, 0, 0), (-10, 0, 40)),
    Line3D((40, 0, 0), (-10, 0, 0)),
]
rail = Frame(
    offset_skeleton(rail_skeleton, (0, 40, 0)),
    RoundTube(8, 1),
    corner="coped",
    end_caps=EndCap(thickness=1.5),
)

# 4. Channel bracket: butt corner (the longer arm runs through), gusset.
bracket = Frame(
    polyline([(-40, 100, 0), (40, 100, 0), (40, 100, 40)]),
    Channel(12, 6, 1.5, 1.5),
    corner="butt",
    up=(0, 1, 0),
    gussets=[Gusset(at=(40, 100, 0), size=15, thickness=1.5)],
)

for name, frame in (
    ("mitered", mitered),
    ("table", table),
    ("rail", rail),
    ("bracket", bracket),
):
    scene.ground(frame)
    print(f"\n{name}\n{frame.cut_list_table()}")

show(scene)
