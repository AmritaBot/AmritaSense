from collections.abc import Awaitable, Callable
from types import FrameType
from typing import Any

from amrita_sense.hook.event import BaseEvent, ConstructableEvent
from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.hook.matcher import MatcherFactory
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.core import BaseNode, Node, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.runtime.workflow import WorkflowInterpreter


class EventTrigger(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    _c_offset: int
    _e_offset: int

    def __init__(self, c_offset: int, e_offset: int):
        self._c_offset = c_offset
        self._e_offset = e_offset
        self._init(self.__call__, "EventTrigger::__call__", False, False)

    async def __call__(self, pc: WorkflowInterpreter):
        event = await pc.call_offset(self._c_offset)
        if not isinstance(event, BaseEvent):
            raise TypeError(f"Expected an event object, got {type(event)}")
        await MatcherFactory.trigger_event(
            event, *pc._ava_args, exception_ignored=pc._exc_ignored, **pc._ava_kwargs
        )
        pc.jump_offset(self._e_offset)


class TriggerInstruction(SelfCompileInstruction):
    _constructor: Node[BaseEvent | Awaitable[BaseEvent]]

    def __init__(self, event: type[ConstructableEvent]):
        self._constructor = Node(
            event.constructor, "TriggerInstruction::constructor", False, False
        )

    def extract(self) -> NodeCompose:
        return EventTrigger(1, 2) >> self._constructor >> NOP


def TRIGGER_EVENT(event: type[ConstructableEvent]) -> TriggerInstruction:
    """Trigger an event for given type.

    Args:
        event (type[ConstructableEvent]): Event class to trigger, must inherit from ConstructableEvent and implement the constructor method.

    Returns:
        TriggerInstruction: Self-compile instruction for triggering the event.
    """
    return TriggerInstruction(event)
