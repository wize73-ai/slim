"""Tests for core.ops — events, kill switches, ring buffer semantics."""

from __future__ import annotations

import asyncio

import pytest

from core.ops.events import Event, EventSeverity, EventStream
from core.ops.kill_switches import KillSwitch, KillSwitchManager


# ────────────────────────────────────────────────────────────────────────────
# Event + EventStream
# ────────────────────────────────────────────────────────────────────────────


class TestEvent:
    def test_now_factory(self):
        e = Event.now(
            severity=EventSeverity.INFO,
            source="github",
            kind="pr_opened",
            summary="PR #42 opened",
        )
        assert e.severity == EventSeverity.INFO
        assert e.source == "github"
        assert e.kind == "pr_opened"
        assert e.summary == "PR #42 opened"
        assert e.id  # uuid populated
        assert e.timestamp_ns > 0
        assert e.payload == {}

    def test_to_json_dict(self):
        e = Event.now(
            severity=EventSeverity.CRITICAL,
            source="firewall",
            kind="drop",
            summary="egress to 1.2.3.4 blocked",
            payload={"dst": "1.2.3.4", "port": "443"},
        )
        d = e.to_json_dict()
        assert d["severity"] == "critical"
        assert d["source"] == "firewall"
        assert d["payload"] == {"dst": "1.2.3.4", "port": "443"}


class TestEventStream:
    def test_starts_empty(self):
        s = EventStream(capacity=10)
        assert len(s) == 0
        assert s.snapshot() == ()
        assert s.subscriber_count == 0

    def test_append_and_recent(self):
        s = EventStream(capacity=10)
        for i in range(5):
            s.append(
                Event.now(
                    severity=EventSeverity.INFO,
                    source="github",
                    kind="pr_opened",
                    summary=f"PR #{i}",
                )
            )
        assert len(s) == 5
        last_two = s.recent(2)
        assert len(last_two) == 2
        assert last_two[1].summary == "PR #4"

    def test_capacity_evicts_oldest(self):
        s = EventStream(capacity=3)
        for i in range(5):
            s.append(
                Event.now(
                    severity=EventSeverity.INFO,
                    source="github",
                    kind="pr_opened",
                    summary=f"PR #{i}",
                )
            )
        snap = s.snapshot()
        assert len(snap) == 3
        assert snap[0].summary == "PR #2"
        assert snap[-1].summary == "PR #4"

    def test_filter_by_source(self):
        s = EventStream(capacity=10)
        s.append(
            Event.now(
                severity=EventSeverity.INFO,
                source="github",
                kind="pr_opened",
                summary="x",
            )
        )
        s.append(
            Event.now(
                severity=EventSeverity.INFO,
                source="firewall",
                kind="drop",
                summary="y",
            )
        )
        gh = s.filter_by_source("github")
        fw = s.filter_by_source("firewall")
        assert len(gh) == 1
        assert len(fw) == 1
        assert gh[0].summary == "x"

    def test_filter_by_severity(self):
        s = EventStream(capacity=10)
        s.append(
            Event.now(
                severity=EventSeverity.INFO,
                source="github",
                kind="x",
                summary="info",
            )
        )
        s.append(
            Event.now(
                severity=EventSeverity.CRITICAL,
                source="agent",
                kind="malice",
                summary="bad",
            )
        )
        crits = s.filter_by_severity(EventSeverity.CRITICAL)
        assert len(crits) == 1
        assert crits[0].summary == "bad"

    def test_clear(self):
        s = EventStream(capacity=10)
        s.append(
            Event.now(
                severity=EventSeverity.INFO,
                source="github",
                kind="x",
                summary="x",
            )
        )
        assert len(s) == 1
        s.clear()
        assert len(s) == 0


class TestEventStreamPubSub:
    @pytest.mark.asyncio
    async def test_subscribe_receives_new_events(self):
        s = EventStream(capacity=10)
        q = s.subscribe()
        assert s.subscriber_count == 1

        e = Event.now(
            severity=EventSeverity.INFO,
            source="github",
            kind="pr_opened",
            summary="hello",
        )
        s.append(e)

        received = await asyncio.wait_for(q.get(), timeout=1.0)
        assert received.summary == "hello"

        s.unsubscribe(q)
        assert s.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_multiple_subscribers_each_get_event(self):
        s = EventStream(capacity=10)
        q1 = s.subscribe()
        q2 = s.subscribe()

        s.append(
            Event.now(
                severity=EventSeverity.INFO,
                source="x",
                kind="y",
                summary="z",
            )
        )

        e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert e1.id == e2.id

    def test_unsubscribe_idempotent(self):
        s = EventStream(capacity=10)
        q = s.subscribe()
        s.unsubscribe(q)
        s.unsubscribe(q)  # second call must not raise
        assert s.subscriber_count == 0

    def test_full_subscriber_queue_drops_silently(self):
        # The EventStream should never block on a slow subscriber. Fill the
        # queue past its capacity and verify the central buffer is unaffected.
        s = EventStream(capacity=10)
        q = s.subscribe()
        # Drain capacity is 64; add many more.
        for i in range(200):
            s.append(
                Event.now(
                    severity=EventSeverity.INFO,
                    source="x",
                    kind="y",
                    summary=str(i),
                )
            )
        # Central buffer kept the most recent capacity rows.
        assert len(s) == 10
        # Subscriber queue capped at 64; no exceptions raised.
        assert q.qsize() <= 64


# ────────────────────────────────────────────────────────────────────────────
# KillSwitchManager
# ────────────────────────────────────────────────────────────────────────────


class TestKillSwitchManager:
    def test_initial_state_inactive(self):
        m = KillSwitchManager()
        for sw in KillSwitch:
            assert m.peek(sw).active is False

    def test_flip_toggles(self):
        m = KillSwitchManager()
        st1 = m.flip(KillSwitch.PAUSE_DEPLOYS, by="alice@example.com")
        assert st1.active is True
        assert st1.set_by == "alice@example.com"
        st2 = m.flip(KillSwitch.PAUSE_DEPLOYS, by="alice@example.com")
        assert st2.active is False
        assert st2.set_by is None

    def test_set_force_state(self):
        m = KillSwitchManager()
        m.set(KillSwitch.PAUSE_AGENT_INFERENCE, active=True, by="bob")
        assert m.peek(KillSwitch.PAUSE_AGENT_INFERENCE).active is True
        m.set(KillSwitch.PAUSE_AGENT_INFERENCE, active=False)
        assert m.peek(KillSwitch.PAUSE_AGENT_INFERENCE).active is False

    def test_one_shot_consumed_by_get(self):
        m = KillSwitchManager()
        m.set(KillSwitch.RELOAD_FIREWALL, active=True)
        # First get returns True and consumes the trigger.
        assert m.get(KillSwitch.RELOAD_FIREWALL) is True
        # Second get returns False — the trigger was consumed.
        assert m.get(KillSwitch.RELOAD_FIREWALL) is False

    def test_persistent_switch_not_consumed(self):
        m = KillSwitchManager()
        m.set(KillSwitch.PAUSE_DEPLOYS, active=True)
        assert m.get(KillSwitch.PAUSE_DEPLOYS) is True
        assert m.get(KillSwitch.PAUSE_DEPLOYS) is True  # still active

    def test_peek_does_not_consume_one_shot(self):
        m = KillSwitchManager()
        m.set(KillSwitch.RELOAD_FIREWALL, active=True)
        assert m.peek(KillSwitch.RELOAD_FIREWALL).active is True
        assert m.peek(KillSwitch.RELOAD_FIREWALL).active is True
        # Now get consumes it.
        assert m.get(KillSwitch.RELOAD_FIREWALL) is True
        assert m.get(KillSwitch.RELOAD_FIREWALL) is False

    def test_snapshot_marks_one_shot(self):
        m = KillSwitchManager()
        snap = m.snapshot()
        assert snap[KillSwitch.RELOAD_FIREWALL.value]["one_shot"] is True
        assert snap[KillSwitch.PAUSE_DEPLOYS.value]["one_shot"] is False

    def test_reset_all(self):
        m = KillSwitchManager()
        for sw in KillSwitch:
            m.set(sw, active=True)
        m.reset_all()
        for sw in KillSwitch:
            assert m.peek(sw).active is False
