"""
src/mission.py  —  Mission system & daily event queue
======================================================
**Custom data-structure**: ``EventQueue`` wraps ``collections.deque``
to manage the school-day schedule (arrival → class → break → …).

``MissionManager`` loads missions from JSON, tracks progress,
and checks objective completion every frame.
"""

from __future__ import annotations

import json
import os
import random
from collections import deque
from settings import (
    MissionStatus, DayPhase, DAY_SCHEDULE, DATA_DIR,
    MOTIVATIONAL_MESSAGES,
)


# ══════════════════════════════════════════════════════════════
#  EVENT QUEUE  (backed by collections.deque)
# ══════════════════════════════════════════════════════════════

class EventQueue:
    """Queue of daily events processed in FIFO order.

    The queue is loaded at the start of each in-game day with the
    school schedule phases.  Random events can be injected between
    phases to add variety.
    """

    def __init__(self):
        self._queue: deque[dict] = deque()

    def load_day_schedule(self):
        """Populate the queue with the standard day phases."""
        self._queue.clear()
        for phase, duration in DAY_SCHEDULE:
            self._queue.append({
                "type":     "phase",
                "phase":    phase,
                "duration": duration,
            })

    def inject_event(self, event: dict, position: int | None = None):
        """Insert a random event into the queue.

        If *position* is ``None`` the event is appended; otherwise it
        is inserted at that index (0 = front).
        """
        if position is None:
            self._queue.append(event)
        else:
            # deque doesn't support insert; convert, insert, remake
            tmp = list(self._queue)
            tmp.insert(min(position, len(tmp)), event)
            self._queue = deque(tmp)

    def next_event(self) -> dict | None:
        """Pop and return the front event, or *None* if empty."""
        try:
            return self._queue.popleft()
        except IndexError:
            return None

    def peek(self) -> dict | None:
        """Peek at the front event without removing it."""
        return self._queue[0] if self._queue else None

    def is_empty(self) -> bool:
        return len(self._queue) == 0

    def size(self) -> int:
        return len(self._queue)

    def clear(self):
        self._queue.clear()

    def __repr__(self):
        return f"EventQueue(size={self.size()})"


# ══════════════════════════════════════════════════════════════
#  MISSION OBJECTIVE
# ══════════════════════════════════════════════════════════════

class MissionObjective:
    """A single task within a mission.

    Supported objective types
    -------------------------
    ``talk_to``       – interact with a specific NPC
    ``go_to_zone``    – enter a zone
    ``collect_item``  – possess an item
    ``hack_target``   – successfully hack an object
    ``win_combat``    – defeat an NPC in combat
    ``reach_reputation`` – achieve a rep threshold with a group
    """

    def __init__(self, obj_type: str, target: str,
                 description: str = "", amount: int = 1):
        self.type        = obj_type
        self.target      = target
        self.description = description
        self.required    = amount
        self.progress    = 0
        self.completed   = False

    def check(self, player, npc_manager, reputation, inventory,
              current_zone: int | None = None) -> bool:
        """Evaluate whether the objective is met.  Returns *True*
        when newly completed."""
        if self.completed:
            return False

        done = False
        if self.type == "collect_item":
            if inventory.has_item(self.target, self.required):
                done = True
        elif self.type == "go_to_zone":
            if current_zone is not None and str(current_zone) == str(self.target):
                done = True
        elif self.type == "reach_reputation":
            parts = self.target.split(":")     # "athletes:70"
            if len(parts) == 2:
                group, threshold = parts[0], int(parts[1])
                if reputation.get(group) >= threshold:
                    done = True
        # talk_to, hack_target, win_combat are event-driven
        # and set externally via advance_objective()

        if done:
            self.progress  = self.required
            self.completed = True
        return done

    def advance(self, amount: int = 1):
        """Manually advance progress (used for event-driven objectives)."""
        self.progress += amount
        if self.progress >= self.required:
            self.completed = True

    def to_dict(self) -> dict:
        return {
            "type": self.type, "target": self.target,
            "description": self.description,
            "required": self.required, "progress": self.progress,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MissionObjective:
        obj = cls(d["type"], d["target"], d.get("description", ""),
                  d.get("required", 1))
        obj.progress  = d.get("progress", 0)
        obj.completed = d.get("completed", False)
        return obj


# ══════════════════════════════════════════════════════════════
#  MISSION
# ══════════════════════════════════════════════════════════════

class Mission:
    """A single quest with objectives, prerequisites, and rewards.

    Attributes
    ----------
    id            : unique string
    title         : display title
    description   : quest-log text
    objectives    : list[MissionObjective]
    prerequisites : list[str]  mission ids that must be completed first
    rewards       : dict       {"xp": int, "items": list, "reputation": dict}
    status        : MissionStatus
    """

    def __init__(self, mission_id: str, title: str, description: str,
                 objectives: list[MissionObjective] | None = None,
                 prerequisites: list[str] | None = None,
                 rewards: dict | None = None):
        self.id            = mission_id
        self.title         = title
        self.description   = description
        self.objectives    = objectives or []
        self.prerequisites = prerequisites or []
        self.rewards       = rewards or {}
        self.status        = MissionStatus.LOCKED

    def is_complete(self) -> bool:
        return all(o.completed for o in self.objectives)

    def check_prerequisites(self, completed_ids: set[str]) -> bool:
        """Return *True* when all prerequisite missions are finished."""
        return all(pid in completed_ids for pid in self.prerequisites)

    def advance_objective(self, obj_type: str, target: str, amount: int = 1):
        """Advance the first matching incomplete objective."""
        for obj in self.objectives:
            if not obj.completed and obj.type == obj_type and obj.target == target:
                obj.advance(amount)
                return

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title,
            "description": self.description,
            "objectives": [o.to_dict() for o in self.objectives],
            "prerequisites": self.prerequisites,
            "rewards": self.rewards,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Mission:
        m = cls(
            d["id"], d["title"], d.get("description", ""),
            [MissionObjective.from_dict(o) for o in d.get("objectives", [])],
            d.get("prerequisites", []),
            d.get("rewards", {}),
        )
        m.status = MissionStatus(d.get("status", "locked"))
        return m

    def __repr__(self):
        return f"Mission({self.id}, {self.status.value})"


# ══════════════════════════════════════════════════════════════
#  MISSION MANAGER
# ══════════════════════════════════════════════════════════════

class MissionManager:
    """Manages all missions: loading, progress checking, rewards."""

    def __init__(self):
        self.missions:     dict[str, Mission] = {}
        self.completed_ids: set[str]           = set()

    # ── loading ───────────────────────────────────────────────

    def load_missions_from_json(self):
        """Load from ``data/missions.json``.  Falls back to defaults."""
        path = os.path.join(DATA_DIR, "missions.json")
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            for entry in data.get("missions", []):
                m = Mission.from_dict(entry)
                self.missions[m.id] = m
        except (FileNotFoundError, json.JSONDecodeError):
            self._create_defaults()

        # Unlock missions whose prerequisites are met
        self._refresh_availability()

    def _create_defaults(self):
        """Hard-coded starter missions."""
        m1 = Mission(
            "mission_first_day", "First Day at Ravenside",
            "Explore the school and meet some students.",
            objectives=[
                MissionObjective("go_to_zone", "3", "Visit the Cafeteria"),
                MissionObjective("talk_to", "npc_marcus_green", "Talk to Marcus Green"),
            ],
            rewards={"xp": 50},
        )
        m1.status = MissionStatus.AVAILABLE

        m2 = Mission(
            "mission_strange_rumours", "Strange Rumours",
            "Investigate the rumours about the Smile Club.",
            objectives=[
                MissionObjective("talk_to", "npc_sophie", "Talk to Sophie Chen"),
                MissionObjective("go_to_zone", "2", "Visit the Computer Lab"),
            ],
            prerequisites=["mission_first_day"],
            rewards={"xp": 80, "reputation": {"tech_club": 10}},
        )

        m3 = Mission(
            "mission_unmasked", "Unmasked",
            "Find proof of the Smile Club's activities.",
            objectives=[
                MissionObjective("hack_target", "lab_server", "Hack the lab server"),
                MissionObjective("talk_to", "npc_jake", "Confront Jake Morrison"),
            ],
            prerequisites=["mission_strange_rumours"],
            rewards={"xp": 120, "reputation": {"rebels": 15}},
        )

        m4 = Mission(
            "mission_final_showdown", "Final Showdown",
            "Enter the Basement and explore the labyrinth to find the Smile Club.",
            objectives=[
                MissionObjective("go_to_zone", "6", "Explore the labyrinth"),
                MissionObjective("win_combat", "npc_ava_thompson", "Knock out Ava Thompson"),
                MissionObjective("win_combat", "npc_marcus_green", "Knock out Marcus Green"),
                MissionObjective("win_combat", "npc_noah_carter", "Knock out Noah Carter"),
            ],
            prerequisites=["mission_unmasked"],
            rewards={"xp": 200},
        )

        for m in (m1, m2, m3, m4):
            self.missions[m.id] = m

    # ── runtime ───────────────────────────────────────────────

    def _refresh_availability(self):
        """Promote LOCKED missions to AVAILABLE if prereqs met."""
        for m in self.missions.values():
            if m.status == MissionStatus.LOCKED:
                if m.check_prerequisites(self.completed_ids):
                    m.status = MissionStatus.AVAILABLE

    def activate_mission(self, mission_id: str) -> bool:
        """Start an AVAILABLE mission.  Returns *True* on success."""
        m = self.missions.get(mission_id)
        if m and m.status == MissionStatus.AVAILABLE:
            m.status = MissionStatus.ACTIVE
            return True
        return False

    def unlock_mission(self, mission_id: str):
        """Force a mission to AVAILABLE (e.g. from dialogue)."""
        m = self.missions.get(mission_id)
        if m and m.status == MissionStatus.LOCKED:
            m.status = MissionStatus.AVAILABLE

    def complete_mission(self, mission_id: str) -> dict | None:
        """Mark mission completed and return its rewards dict."""
        m = self.missions.get(mission_id)
        if m and m.status == MissionStatus.ACTIVE and m.is_complete():
            m.status = MissionStatus.COMPLETED
            self.completed_ids.add(mission_id)
            self._refresh_availability()
            return m.rewards
        return None

    def check_objectives(self, player, npc_manager, reputation, inventory,
                         current_zone: int | None = None):
        """Called each frame to evaluate passive objectives.

        Returns a list of mission_ids that just completed.
        """
        newly_completed: list[str] = []
        for m in self.missions.values():
            if m.status != MissionStatus.ACTIVE:
                continue
            for obj in m.objectives:
                obj.check(player, npc_manager, reputation, inventory, current_zone)
            if m.is_complete():
                newly_completed.append(m.id)
        return newly_completed

    def advance_objective_event(self, obj_type: str, target: str):
        """Called by game events (talk, hack, combat win)."""
        for m in self.missions.values():
            if m.status == MissionStatus.ACTIVE:
                m.advance_objective(obj_type, target)

    # ── queries ───────────────────────────────────────────────

    def get_active(self) -> list[Mission]:
        return [m for m in self.missions.values() if m.status == MissionStatus.ACTIVE]

    def get_available(self) -> list[Mission]:
        return [m for m in self.missions.values() if m.status == MissionStatus.AVAILABLE]

    def get_completed(self) -> list[Mission]:
        return [m for m in self.missions.values() if m.status == MissionStatus.COMPLETED]

    def get_all(self) -> list[Mission]:
        return list(self.missions.values())

    def get_motivational_message(self) -> str:
        """Return a random motivational string (displayed on mission complete)."""
        return random.choice(MOTIVATIONAL_MESSAGES)

    def __repr__(self):
        return f"MissionManager({len(self.missions)} missions)"
