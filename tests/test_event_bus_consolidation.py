from az_enterprise.core.events import EventBus as CanonicalEventBus
from az_enterprise.core.agents.event_bus import EventBus as AgentEventBus


def test_agent_event_bus_is_canonical_event_bus():
    assert AgentEventBus is CanonicalEventBus


def test_event_bus_memory_emit_and_subscription():
    received = []

    bus = CanonicalEventBus(
        db=None,
        project_id="eventbus_test",
    )

    bus.on("STAGE_COMPLETED", received.append)
    bus.emit(
        "STAGE_COMPLETED",
        {"stage": "assets"},
    )

    assert len(bus.memory_events) == 1
    assert bus.memory_events[0] == {
        "project_id": "eventbus_test",
        "type": "STAGE_COMPLETED",
        "payload": {"stage": "assets"},
    }

    assert received == [
        {
            "project_id": "eventbus_test",
            "type": "STAGE_COMPLETED",
            "payload": {"stage": "assets"},
        }
    ]
