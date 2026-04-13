"""Autonomous mode — monitor desktop and proactively act on triggers."""

import asyncio
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

TRIGGERS_DIR = Path.home() / ".local/share/aulinx"
TRIGGERS_FILE = TRIGGERS_DIR / "triggers.json"


@dataclass
class Trigger:
    """A condition-action pair that fires when the desktop matches."""

    name: str
    condition: str  # natural language, e.g. "battery below 20%"
    action: str  # natural language, e.g. "enable power saver mode"
    cooldown_s: int = 300  # don't re-trigger within this window
    enabled: bool = True
    last_triggered: float = 0.0  # timestamp


class TriggerStore:
    """Persist triggers to ~/.local/share/aulinx/triggers.json."""

    def __init__(self):
        TRIGGERS_DIR.mkdir(parents=True, exist_ok=True)
        self._triggers: dict[str, Trigger] = {}
        self.load()

    def add_trigger(self, trigger: Trigger) -> Trigger:
        """Add or replace a trigger by name."""
        self._triggers[trigger.name] = trigger
        self.save()
        return trigger

    def remove_trigger(self, name: str) -> bool:
        """Remove a trigger by name. Returns True if it existed."""
        if name in self._triggers:
            del self._triggers[name]
            self.save()
            return True
        return False

    def list_triggers(self) -> list[Trigger]:
        """Return all triggers."""
        return list(self._triggers.values())

    def save(self):
        """Write triggers to disk."""
        data = [asdict(t) for t in self._triggers.values()]
        try:
            TRIGGERS_FILE.write_text(json.dumps(data, indent=2))
        except OSError:
            logger.warning("Failed to save triggers to %s", TRIGGERS_FILE)

    def load(self):
        """Load triggers from disk."""
        if not TRIGGERS_FILE.exists():
            return
        try:
            data = json.loads(TRIGGERS_FILE.read_text())
            for item in data:
                t = Trigger(**item)
                self._triggers[t.name] = t
        except (json.JSONDecodeError, OSError, TypeError):
            logger.warning("Failed to load triggers from %s", TRIGGERS_FILE)


class ConditionChecker:
    """Evaluate natural-language conditions against desktop context.

    Built-in patterns:
      - "battery below N%"
      - "time after HH:MM"
      - "app X running"
      - "app X not running"
      - "disk usage above N%"
    """

    # Compiled patterns for built-in conditions
    _BATTERY_BELOW = re.compile(r"battery\s+below\s+(\d+)%", re.IGNORECASE)
    _TIME_AFTER = re.compile(r"time\s+after\s+(\d{1,2}):(\d{2})", re.IGNORECASE)
    _APP_RUNNING = re.compile(r"app\s+(.+?)\s+running$", re.IGNORECASE)
    _APP_NOT_RUNNING = re.compile(r"app\s+(.+?)\s+not\s+running$", re.IGNORECASE)
    _DISK_ABOVE = re.compile(r"disk\s+usage\s+above\s+(\d+)%", re.IGNORECASE)

    def check_condition(self, condition: str, context: dict) -> bool:
        """Return True if *condition* matches the given *context* dict.

        Context keys used:
          - battery_percent (int)
          - hour, minute (int) — current time components
          - running_apps (list[str])
          - disk_usage_percent (int)
        """
        condition = condition.strip()

        # battery below N%
        m = self._BATTERY_BELOW.search(condition)
        if m:
            threshold = int(m.group(1))
            level = context.get("battery_percent")
            if level is None:
                return False
            return level < threshold

        # time after HH:MM
        m = self._TIME_AFTER.search(condition)
        if m:
            target_h, target_m = int(m.group(1)), int(m.group(2))
            cur_h = context.get("hour")
            cur_m = context.get("minute")
            if cur_h is None or cur_m is None:
                return False
            return (cur_h, cur_m) >= (target_h, target_m)

        # app X not running (must be checked before "app X running")
        m = self._APP_NOT_RUNNING.search(condition)
        if m:
            app_name = m.group(1).strip().lower()
            running = [a.lower() for a in context.get("running_apps", [])]
            return app_name not in running

        # app X running
        m = self._APP_RUNNING.search(condition)
        if m:
            app_name = m.group(1).strip().lower()
            running = [a.lower() for a in context.get("running_apps", [])]
            return app_name in running

        # disk usage above N%
        m = self._DISK_ABOVE.search(condition)
        if m:
            threshold = int(m.group(1))
            usage = context.get("disk_usage_percent")
            if usage is None:
                return False
            return usage > threshold

        # Unknown condition — never match to avoid false positives
        return False


class AutonomousLoop:
    """Periodically check triggers and ask the agent to act on matches."""

    def __init__(self, agent, triggers: TriggerStore, check_interval_s: int = 30):
        self.agent = agent
        self.triggers = triggers
        self.checker = ConditionChecker()
        self.check_interval_s = check_interval_s
        self._running = False
        self._task: asyncio.Task | None = None

    async def run(self):
        """Main loop — runs until stop() is called."""
        self._running = True
        logger.info("Autonomous mode started (interval=%ds)", self.check_interval_s)
        try:
            while self._running:
                await self.check_and_act()
                await asyncio.sleep(self.check_interval_s)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            logger.info("Autonomous mode stopped")

    async def check_and_act(self):
        """Check all enabled triggers and execute matching ones."""
        context = await self._gather_context()
        now = time.time()

        for trigger in self.triggers.list_triggers():
            if not trigger.enabled:
                continue
            if now - trigger.last_triggered < trigger.cooldown_s:
                continue
            if self.checker.check_condition(trigger.condition, context):
                logger.info("Trigger fired: %s", trigger.name)
                trigger.last_triggered = now
                self.triggers.save()
                try:
                    await self.agent.handle(trigger.action)
                except Exception:
                    logger.exception("Error executing trigger %s", trigger.name)

    def stop(self):
        """Signal the loop to stop after the current iteration."""
        self._running = False
        if self._task is not None:
            self._task.cancel()

    async def _gather_context(self) -> dict:
        """Build a context dict from the desktop snapshot."""
        ctx: dict = {}
        try:
            if hasattr(self.agent, "desktop_ctx"):
                raw = await self.agent.desktop_ctx.snapshot()
                snapshot = json.loads(raw) if isinstance(raw, str) else raw
                # Map snapshot fields to checker keys
                sys_info = snapshot.get("system", {})
                ctx["running_apps"] = snapshot.get("running_apps", [])
                ctx["battery_percent"] = sys_info.get("battery_percent")
                ctx["disk_usage_percent"] = sys_info.get("disk_usage_percent")
        except Exception:
            logger.debug("Failed to gather desktop context", exc_info=True)

        # Always include current time
        from datetime import datetime

        now = datetime.now()
        ctx["hour"] = now.hour
        ctx["minute"] = now.minute
        return ctx
