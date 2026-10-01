"""d15_event_trigger.py — ConstructableEvent + TRIGGER_EVENT instruction

Usage:
    python demos/d15_event_trigger.py
    python -i demos/d15_event_trigger.py   # same, then use `inter` directly in the REPL
"""

import asyncio
from dataclasses import dataclass

from amrita_sense import TRIGGER_EVENT, Node, WorkflowInterpreter
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
    print("Executing core logic...")
    return "completed"


composition = do_work >> TRIGGER_EVENT(AuditEvent)
# Module-level so a REPL can `from demos.d15_event_trigger import inter` and step into the trigger.
inter = WorkflowInterpreter(composition.render())


async def main() -> None:
    await inter.run()


if __name__ == "__main__":
    asyncio.run(main())
