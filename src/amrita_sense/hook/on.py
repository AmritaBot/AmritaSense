from .matcher import Matcher


def on_event(event_type: str, priority: int = 10, block: bool = True):
    return Matcher(event_type, priority, block)
