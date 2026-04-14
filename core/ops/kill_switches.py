"""Kill switch state for the ops dashboard.

Four kill switches the instructor can flip during class to respond to
problems quickly:

* ``PAUSE_AGENT_INFERENCE`` — agent inference proxy returns 503 to all
  CI LLM calls, freeing guapo for live student traffic.
* ``PAUSE_DEPLOYS`` — deploy-on-main workflow halts mid-flight or doesn't
  start. Used when the class needs to lock the live state.
* ``PANIC_STOP_APP`` — chat handler returns a maintenance error and the
  ops dashboard signals an external watchdog to take down the app
  container. Used when something is actively going wrong.
* ``RELOAD_FIREWALL`` — one-shot signal to re-apply the nftables egress
  allow-list. Used after manual firewall edits to verify the rules are
  in place.

The state is held in memory in this module. External services (the agent
proxy, the deploy workflow, the chat handler) read it via the
``GET /ops/switches`` endpoint to check whether they should proceed.

``RELOAD_FIREWALL`` is special: it's a one-shot trigger, not a persistent
state. Polling consumers see it as ``True`` exactly once per click before
it auto-resets to ``False``.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Final


class KillSwitch(str, Enum):
    """Identifiers for the four kill switches."""

    PAUSE_AGENT_INFERENCE = "pause_agent_inference"
    PAUSE_DEPLOYS = "pause_deploys"
    PANIC_STOP_APP = "panic_stop_app"
    RELOAD_FIREWALL = "reload_firewall"


# One-shot switches reset to False after being read once. Persistent
# switches stay set until the instructor clicks again.
_ONE_SHOT_SWITCHES: Final[frozenset[KillSwitch]] = frozenset({KillSwitch.RELOAD_FIREWALL})


@dataclass(frozen=True, slots=True)
class SwitchState:
    """A snapshot of one switch's current state."""

    switch: KillSwitch
    active: bool
    set_at_ns: int | None
    set_by: str | None  # email from Cf-Access header, or "system" for tests


@dataclass
class KillSwitchManager:
    """In-memory state for all four kill switches.

    Thread-safe via a single lock so the FastAPI handlers (which may run
    in worker threads under uvicorn) and the per-call check helpers
    (used from chat handlers) can share state without races.

    The :meth:`flip` and :meth:`set` methods record who flipped the switch
    so the dashboard's audit log shows attribution. ``set_by`` defaults
    to the string ``"system"`` when no email is supplied.
    """

    _states: dict[KillSwitch, SwitchState] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        """Initialise all four switches to inactive."""
        with self._lock:
            for sw in KillSwitch:
                if sw not in self._states:
                    self._states[sw] = SwitchState(
                        switch=sw, active=False, set_at_ns=None, set_by=None
                    )

    def get(self, switch: KillSwitch) -> bool:
        """Return whether the switch is currently active.

        For one-shot switches (``RELOAD_FIREWALL``), this method has the
        side effect of consuming the trigger: the next call returns
        ``False`` until the switch is flipped again.
        """
        with self._lock:
            state = self._states[switch]
            if state.active and switch in _ONE_SHOT_SWITCHES:
                # Consume the trigger.
                self._states[switch] = SwitchState(
                    switch=switch, active=False, set_at_ns=None, set_by=None
                )
            return state.active

    def peek(self, switch: KillSwitch) -> SwitchState:
        """Return the switch's current state without consuming a one-shot.

        Used by the dashboard for display — it shouldn't trigger one-shot
        consumption just by rendering the row.
        """
        with self._lock:
            return self._states[switch]

    def snapshot(self) -> dict[str, dict[str, object]]:
        """Return all switch states as a JSON-serialisable dict.

        Like :meth:`peek` for all switches at once. Does not consume
        one-shot triggers.
        """
        with self._lock:
            return {
                sw.value: {
                    "active": st.active,
                    "set_at_ns": st.set_at_ns,
                    "set_by": st.set_by,
                    "one_shot": sw in _ONE_SHOT_SWITCHES,
                }
                for sw, st in self._states.items()
            }

    def flip(self, switch: KillSwitch, by: str = "system") -> SwitchState:
        """Toggle the switch and return its new state.

        Args:
            switch: Which switch to flip.
            by: Email or service identifier of who flipped it. Recorded in
                the new ``SwitchState`` for the dashboard audit log.

        Returns:
            The new :class:`SwitchState` post-flip.
        """
        with self._lock:
            current = self._states[switch]
            new_state = SwitchState(
                switch=switch,
                active=not current.active,
                set_at_ns=time.time_ns() if not current.active else None,
                set_by=by if not current.active else None,
            )
            self._states[switch] = new_state
            return new_state

    def set(
        self,
        switch: KillSwitch,
        active: bool,
        by: str = "system",
    ) -> SwitchState:
        """Force the switch to a specific state regardless of its current value.

        Used by tests and by the deploy workflow's ``--unpause-after`` hook.
        """
        with self._lock:
            new_state = SwitchState(
                switch=switch,
                active=active,
                set_at_ns=time.time_ns() if active else None,
                set_by=by if active else None,
            )
            self._states[switch] = new_state
            return new_state

    def reset_all(self) -> None:
        """Clear every switch back to inactive. Used by tests."""
        with self._lock:
            for sw in KillSwitch:
                self._states[sw] = SwitchState(switch=sw, active=False, set_at_ns=None, set_by=None)
