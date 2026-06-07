"""Tests for trigger_event.py — TRIGGER_EVENT instruction."""

import pytest

from amrita_sense.instructions.trigger_event import TRIGGER_EVENT


@pytest.mark.asyncio
async def test_trigger_event_compile_time_type_check():
    """TRIGGER_EVENT constructor accesses .constructor — non-BaseEvent
    objects without this attr fail at construction time."""
    with pytest.raises(AttributeError, match="constructor"):
        TRIGGER_EVENT("not_an_event")  # type: ignore[arg-type]
