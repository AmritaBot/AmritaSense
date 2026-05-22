# Event System

AmritaSense's event system is a runtime hook mechanism that operates **in parallel with and independently of** the workflow interpreter. It is not bound to any specific node or lifecycle. Instead, it provides a separate channel through which workflow nodes can trigger custom events, and registered handlers respond using the exact same dependency injection mechanism as nodes.

### Core Roles

| Role                                | Responsibility                                                                    |
| ----------------------------------- | --------------------------------------------------------------------------------- |
| `BaseEvent`                         | Base class for all custom events; defines the event type identifier               |
| `on_event(event_type)`              | Decorator that registers an async function as a handler for a specific event type |
| `MatcherFactory.trigger_event(...)` | Runtime entry point that dispatches an event to all matching handlers             |

### Dispatch Flow

When `trigger_event(event)` is called, the system:

1. Obtains the event type string from the `BaseEvent` instance
2. Looks up all registered handlers for that type in `EventRegistry`
3. For each handler, resolves any runtime dependencies declared via `Depends(...)`
4. Invokes the handlers in order of priority

If no handlers are registered for the event type, the call silently passes without any side effects.

## Broadcast Dispatch: The Essential Difference from Workflow Interruption

**The event system is broadcast-oriented** — it distributes an event to all matching handlers and then continues execution. It does **not** include built-in interruption or suspension capabilities. This is fundamentally different from Sense's workflow suspension/interruption mechanism:

|                             | Event System                                                      | Workflow Interruption                                                                   |
| --------------------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Pattern**                 | Broadcast dispatch                                                | Cooperative suspension                                                                  |
| **Control flow**            | Handlers return automatically after execution                     | Requires explicit `resume()` to continue after suspension                               |
| **Intervention capability** | Handlers can only react to events; they cannot pause the workflow | External systems can inject execution via `ARCHIVED_NODES` + `call_sub(interrupt=True)` |
| **Typical use cases**       | Logging, auditing, notifications, state synchronization           | Debugging, human approval, dynamic flow modification                                    |

If interruption or suspension behavior is needed inside an event handler, **it must be implemented manually by the developer** — for example, by explicitly calling `pc.object_io.wait_to_suspend()` or `pc.call_sub(interrupt=True)` within the handler to invoke an archived node. These capabilities come from the Sense workflow interpreter, not from the event system itself.

## Shared Dependency Injection with Workflow Nodes

Event handlers **fully reuse** AmritaSense's dependency injection system. Handlers can declare arbitrary dependencies via `Depends(...)` — including `POINTER_DEPENDS` to obtain the current `WorkflowInterpreter` instance — and the runtime will automatically resolve and inject them before invocation. This means event handlers enjoy the same DI capabilities as `@Node()` functions: type safety, concurrent resolution, and termination when a `Depends` factory returns `None`.

> **Relationship with Core's Event System**: AmritaSense's event system is an independent mirror of Core's event system. Both share identical API design and DI contracts, yet operate independently. Core event handlers do not need to be aware of Sense, and Sense nodes do not need to depend on Core — they collaborate solely through the `DependencyMeta` data structure.

## Custom Event Example

```python
from dataclasses import dataclass

from amrita_sense.hook.event import BaseEvent
from amrita_sense.hook.matcher import MatcherFactory, Depends
from amrita_sense.hook.on import on_event
from amrita_sense.node.core import Node
from amrita_sense.runtime.deps import POINTER_DEPENDS
from amrita_sense.runtime.workflow import WorkflowInterpreter

@dataclass
class TaskCompletedEvent(BaseEvent[str]):
    task_id: str

    @property
    def event_type(self) -> str:
        return "task.completed"

    def get_event_type(self) -> str:
        return self.event_type

@on_event("task.completed")
async def handle_task_completed(
    event: TaskCompletedEvent,
    pc: WorkflowInterpreter = Depends(POINTER_DEPENDS),
):
    print(f"Task completed: {event.task_id}")

@Node()
async def complete_task_node() -> str:
    # ... task logic ...
    await MatcherFactory.trigger_event(TaskCompletedEvent(task_id="email-send"))
    return "done"
```

## Handler Order and Blocking

Handlers for the same event type execute in ascending order of priority. A handler can immediately terminate the entire event chain by raising `CancelException`, or skip itself and let the next handler continue by raising `PassException`. Standard dispatch is cooperative — unless explicitly interrupted, all matching handlers are executed in order.
