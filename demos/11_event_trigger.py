"""11_event_trigger.py — ConstructableEvent + TRIGGER_EVENT instruction

Usage:
    python demos/11_event_trigger.py
"""

import asyncio
from dataclasses import dataclass

from amrita_sense import NOP, TRIGGER_EVENT, Node, WorkflowInterpreter
from amrita_sense.hook.event import ConstructableEvent
from amrita_sense.hook.on import on_event


@dataclass
class AuditEvent(ConstructableEvent):
    """Constructable event — triggered by TRIGGER_EVENT in a workflow"""
    action: str

    @property
    def event_type(self) -> str:
        return "audit"

    def get_event_type(self) -> str:
        return self.event_type

    @classmethod
    def constructor(cls, action: str = "unknown") -> "AuditEvent":
        """TRIGGER_EVENT calls this to construct the event at runtime"""
        return cls(action=action)


# Register an event handler
@on_event("audit").handle()
async def audit_handler(event: AuditEvent) -> None:
    print(f"[Audit] Action: {event.action}")


@Node()
async def do_work() -> str:
    print("执行核心逻辑...")
    return "completed"


async def main() -> None:
    comp = (do_work >> TRIGGER_EVENT(AuditEvent) >> NOP).render()
    await WorkflowInterpreter(comp).run()


if __name__ == "__main__":
    asyncio.run(main())
