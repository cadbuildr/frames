"""The frame connector hook: one extension point that lets a library put
joint hardware (brackets, fasteners, end caps…) on every junction of a
``Frame``, and machine the members for it.

A connector is either a plain callable ``connector(junction) -> Connection |
None`` or a :class:`ConnectorRule`, which can also choose which member runs
through a butt node and prepare every member (add anchors, holes) before it
is placed. The frame calls it once per :class:`~cadbuildr.frames.layout.Junction`
(free ends included), after the layout is solved and before any member Part
is added to the assembly — so machining requested by a connection lands on
the member geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence, Union

from .geometry import Vec
from .layout import FrameLayout, Junction, JunctionEnd, MemberLayout

if TYPE_CHECKING:  # pragma: no cover
    from .frame import FrameMember

# A member operation requested by a connection: called with the member's
# FrameMember Part (local coordinates: start at the origin, +X along the
# member, profile u / v = +Y / +Z) before the Part is added to the frame.
Machining = Callable[["FrameMember"], None]


@dataclass
class Placed:
    """A component and its placement in frame coordinates (a 4x4 matrix /
    transform dict / translation accepted by ``Assembly.add_component``;
    ``None`` = the component's own origin)."""

    component: Any
    tf: Any = None


@dataclass
class Connection:
    """What a connector adds at one junction: ``components`` (``Placed`` or
    bare components) and ``machining`` — ``(member, fn)`` pairs, ``member``
    being a ``MemberLayout``, a ``JunctionEnd`` or a member index."""

    components: Sequence[Union[Placed, Any]] = ()
    machining: Sequence[tuple[Any, Machining]] = field(default_factory=tuple)


class ConnectorRule:
    """Base class for connector rules; override what you need.

    - ``choose_through(node, ends)``: index (into ``ends``) of the member that
      runs through a butt / coped / multi node, or ``None`` for the frame's
      default (arc, then longest, then first).
    - ``prepare_member(part)``: called once per ``FrameMember`` before it is
      placed (e.g. add slot anchors).
    - ``connect(junction, layout)``: the hardware for one junction.
    """

    def choose_through(self, node: Vec, ends: Sequence[JunctionEnd]) -> Optional[int]:
        return None

    def prepare_member(self, part: "FrameMember") -> None:
        return None

    def connect(self, junction: Junction, layout: FrameLayout) -> Optional[Connection]:
        return None


ConnectorLike = Union[ConnectorRule, Callable[[Junction], Optional[Connection]]]


class _CallableRule(ConnectorRule):
    def __init__(self, fn: Callable[[Junction], Optional[Connection]]):
        self.fn = fn

    def connect(self, junction, layout):
        return self.fn(junction)


def as_rule(connector: ConnectorLike | None) -> ConnectorRule | None:
    if connector is None or isinstance(connector, ConnectorRule):
        return connector
    if callable(connector):
        return _CallableRule(connector)
    raise TypeError(
        "connector must be a ConnectorRule or a callable(junction) -> Connection, "
        f"got {type(connector).__name__}"
    )


def member_index(ref: Any) -> int:
    if isinstance(ref, JunctionEnd):
        return ref.member.index
    if isinstance(ref, MemberLayout):
        return ref.index
    if isinstance(ref, int):
        return ref
    raise TypeError(
        f"machining target must be a MemberLayout, JunctionEnd or index, got {ref!r}"
    )
