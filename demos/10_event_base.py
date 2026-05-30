"""10_event_base.py — BaseEvent + on_event + MatcherFactory.trigger_event

Usage:
    python demos/10_event_base.py
"""

import asyncio
from dataclasses import dataclass

from amrita_sense import BaseEvent, Node, WorkflowInterpreter
from amrita_sense.hook.matcher import MatcherFactory
from amrita_sense.hook.on import on_event


@dataclass
class NotifyEvent(BaseEvent[str]):
    """Custom event"""

    message: str

    @property
    def event_type(self) -> str:
        return "notify"

    def get_event_type(self) -> str:
        return self.event_type


# Register an event handler
@on_event("notify").handle()
async def handle_notify(event: NotifyEvent) -> None:
    print(f"[Handler] Received notification: {event.message}")


@Node()
async def produce_event() -> str:
    """Dispatch an event"""
    await MatcherFactory.trigger_event(NotifyEvent("Workflow started"))
    return "done"


@Node()
async def finish(result: str) -> None:
    print(f"[Finish] Workflow completed: {result}")


async def main() -> None:

    comp = (produce_event >> finish).render()
    await WorkflowInterpreter(comp).run()


if __name__ == "__main__":
    asyncio.run(main())
