"""Tests for autonomous mode — triggers, condition checking, cooldown."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from aulinx.autonomous import (
    AutonomousLoop,
    ConditionChecker,
    Trigger,
    TriggerStore,
)

# ── TriggerStore CRUD ──────────────────────────────────────────────


class TestTriggerStore:
    @pytest.fixture(autouse=True)
    def temp_store(self, tmp_path):
        with (
            patch("aulinx.autonomous.TRIGGERS_DIR", tmp_path),
            patch("aulinx.autonomous.TRIGGERS_FILE", tmp_path / "triggers.json"),
        ):
            yield tmp_path

    def test_add_and_list(self):
        store = TriggerStore()
        t = Trigger(name="low_bat", condition="battery below 20%", action="enable power saver")
        store.add_trigger(t)

        triggers = store.list_triggers()
        assert len(triggers) == 1
        assert triggers[0].name == "low_bat"
        assert triggers[0].condition == "battery below 20%"

    def test_remove_existing(self):
        store = TriggerStore()
        store.add_trigger(Trigger(name="t1", condition="c", action="a"))
        assert store.remove_trigger("t1") is True
        assert store.list_triggers() == []

    def test_remove_nonexistent(self):
        store = TriggerStore()
        assert store.remove_trigger("nope") is False

    def test_persistence(self):
        store = TriggerStore()
        store.add_trigger(Trigger(name="persist", condition="c", action="a", cooldown_s=60))

        # Load into a fresh store
        store2 = TriggerStore()
        triggers = store2.list_triggers()
        assert len(triggers) == 1
        assert triggers[0].name == "persist"
        assert triggers[0].cooldown_s == 60

    def test_add_replaces_same_name(self):
        store = TriggerStore()
        store.add_trigger(Trigger(name="dup", condition="old", action="a"))
        store.add_trigger(Trigger(name="dup", condition="new", action="b"))
        triggers = store.list_triggers()
        assert len(triggers) == 1
        assert triggers[0].condition == "new"


# ── ConditionChecker ───────────────────────────────────────────────


class TestConditionChecker:
    def setup_method(self):
        self.checker = ConditionChecker()

    def test_battery_below_true(self):
        assert self.checker.check_condition("battery below 20%", {"battery_percent": 15})

    def test_battery_below_false(self):
        assert not self.checker.check_condition("battery below 20%", {"battery_percent": 50})

    def test_battery_below_missing(self):
        assert not self.checker.check_condition("battery below 20%", {})

    def test_time_after_true(self):
        ctx = {"hour": 23, "minute": 0}
        assert self.checker.check_condition("time after 22:00", ctx)

    def test_time_after_false(self):
        ctx = {"hour": 8, "minute": 30}
        assert not self.checker.check_condition("time after 22:00", ctx)

    def test_time_after_exact(self):
        ctx = {"hour": 22, "minute": 0}
        assert self.checker.check_condition("time after 22:00", ctx)

    def test_app_running_true(self):
        ctx = {"running_apps": ["Firefox", "Terminal"]}
        assert self.checker.check_condition("app Firefox running", ctx)

    def test_app_running_false(self):
        ctx = {"running_apps": ["Terminal"]}
        assert not self.checker.check_condition("app Firefox running", ctx)

    def test_app_running_case_insensitive(self):
        ctx = {"running_apps": ["firefox"]}
        assert self.checker.check_condition("app Firefox running", ctx)

    def test_app_not_running_true(self):
        ctx = {"running_apps": ["Terminal"]}
        assert self.checker.check_condition("app Firefox not running", ctx)

    def test_app_not_running_false(self):
        ctx = {"running_apps": ["Firefox"]}
        assert not self.checker.check_condition("app Firefox not running", ctx)

    def test_disk_usage_above_true(self):
        assert self.checker.check_condition("disk usage above 90%", {"disk_usage_percent": 95})

    def test_disk_usage_above_false(self):
        assert not self.checker.check_condition("disk usage above 90%", {"disk_usage_percent": 50})

    def test_disk_usage_above_missing(self):
        assert not self.checker.check_condition("disk usage above 90%", {})

    def test_unknown_condition_returns_false(self):
        assert not self.checker.check_condition("some unknown thing", {"battery_percent": 5})


# ── Trigger cooldown ───────────────────────────────────────────────


class TestCooldown:
    @pytest.fixture(autouse=True)
    def temp_store(self, tmp_path):
        with (
            patch("aulinx.autonomous.TRIGGERS_DIR", tmp_path),
            patch("aulinx.autonomous.TRIGGERS_FILE", tmp_path / "triggers.json"),
        ):
            yield tmp_path

    @pytest.mark.asyncio
    async def test_cooldown_prevents_retrigger(self):
        store = TriggerStore()
        t = Trigger(
            name="bat",
            condition="battery below 20%",
            action="save power",
            cooldown_s=600,
            last_triggered=time.time(),  # just fired
        )
        store.add_trigger(t)

        agent = AsyncMock()
        agent.desktop_ctx = AsyncMock()
        agent.desktop_ctx.snapshot = AsyncMock(return_value='{"system":{}, "running_apps":[]}')

        loop = AutonomousLoop(agent, store, check_interval_s=1)

        # Patch time context so condition matches
        with patch.object(
            loop, "_gather_context", return_value={"battery_percent": 10, "hour": 12, "minute": 0}
        ):
            await loop.check_and_act()

        # Agent should NOT have been called because cooldown hasn't expired
        agent.handle.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_fires_after_cooldown(self):
        store = TriggerStore()
        t = Trigger(
            name="bat",
            condition="battery below 20%",
            action="save power",
            cooldown_s=1,
            last_triggered=time.time() - 5,  # cooldown expired
        )
        store.add_trigger(t)

        agent = AsyncMock()
        loop = AutonomousLoop(agent, store, check_interval_s=1)

        with patch.object(
            loop, "_gather_context", return_value={"battery_percent": 10, "hour": 12, "minute": 0}
        ):
            await loop.check_and_act()

        agent.handle.assert_called_once_with("save power")

    @pytest.mark.asyncio
    async def test_disabled_trigger_skipped(self):
        store = TriggerStore()
        t = Trigger(name="off", condition="battery below 50%", action="act", enabled=False)
        store.add_trigger(t)

        agent = AsyncMock()
        loop = AutonomousLoop(agent, store, check_interval_s=1)

        with patch.object(
            loop, "_gather_context", return_value={"battery_percent": 10, "hour": 12, "minute": 0}
        ):
            await loop.check_and_act()

        agent.handle.assert_not_called()
