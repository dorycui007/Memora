"""Tests for the async event bus."""

from __future__ import annotations

import asyncio

import pytest

from memora.core.event_bus import Event, EventBus


@pytest.fixture
def bus():
    return EventBus()


class TestEventBusPublish:
    @pytest.mark.asyncio
    async def test_publish_returns_event_id(self, bus):
        event_id = await bus.publish("test.event", {"key": "value"})
        assert event_id
        assert isinstance(event_id, str)

    @pytest.mark.asyncio
    async def test_publish_increments_queue(self, bus):
        assert bus.queue_size == 0
        await bus.publish("test.event", {})
        assert bus.queue_size == 1


class TestEventBusSubscribe:
    @pytest.mark.asyncio
    async def test_exact_match(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("test.event", handler)
        await bus.start()
        await bus.publish("test.event", {"data": 1})
        await asyncio.sleep(0.1)
        await bus.stop()

        assert len(received) == 1
        assert received[0].payload == {"data": 1}

    @pytest.mark.asyncio
    async def test_wildcard_match(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("entity.*", handler)
        await bus.start()
        await bus.publish("entity.created", {})
        await bus.publish("entity.updated", {})
        await bus.publish("other.event", {})
        await asyncio.sleep(0.1)
        await bus.stop()

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_global_wildcard(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("*", handler)
        await bus.start()
        await bus.publish("a.b", {})
        await bus.publish("c.d", {})
        await asyncio.sleep(0.1)
        await bus.stop()

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_no_match(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("specific.event", handler)
        await bus.start()
        await bus.publish("other.event", {})
        await asyncio.sleep(0.1)
        await bus.stop()

        assert len(received) == 0


class TestEventBusLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, bus):
        await bus.start()
        assert bus._running
        await bus.stop()
        assert not bus._running

    @pytest.mark.asyncio
    async def test_event_count(self, bus):
        async def noop(event):
            pass

        bus.subscribe("*", noop)
        await bus.start()
        await bus.publish("a", {})
        await bus.publish("b", {})
        await asyncio.sleep(0.1)
        await bus.stop()

        assert bus.event_count == 2


class TestEventPriority:
    @pytest.mark.asyncio
    async def test_priority_ordering(self, bus):
        received = []

        async def handler(event):
            received.append(event.priority)

        bus.subscribe("*", handler)

        # Publish multiple events with different priorities before starting consumer
        await bus.publish("low", {}, priority=10)
        await bus.publish("high", {}, priority=1)
        await bus.publish("medium", {}, priority=5)

        await bus.start()
        await asyncio.sleep(0.2)
        await bus.stop()

        # Higher priority (lower number) should be processed first
        assert received[0] == 1
        assert received[1] == 5
        assert received[2] == 10


class TestEventMatching:
    def test_exact_match(self, bus):
        assert bus._matches("entity.created", "entity.created")
        assert not bus._matches("entity.created", "entity.updated")

    def test_wildcard_match(self, bus):
        assert bus._matches("entity.*", "entity.created")
        assert bus._matches("entity.*", "entity.updated")
        assert not bus._matches("entity.*", "other.event")

    def test_global_wildcard(self, bus):
        assert bus._matches("*", "anything")
        assert bus._matches("*", "entity.created")
