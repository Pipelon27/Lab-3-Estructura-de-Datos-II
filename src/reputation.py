"""
src/reputation.py  —  Social reputation system
================================================
Tracks the player's standing with each ``SocialGroup`` and
accumulates a *karma* score from anti-bullying actions.
The final game ending is calculated from these values.
"""

from __future__ import annotations

from settings import (
    SocialGroup, Ending, GROUP_COLORS,
    NOTIF_SUCCESS, NOTIF_WARNING, NOTIF_ERROR,
)


class ReputationSystem:
    """Tracks reputation per social group and overall karma.

    Attributes
    ----------
    standings : dict[str, int]
        Group name → reputation value (0–100, 50 = neutral).
    karma : int
        Accumulated score from anti-bullying / pro-social actions.
        Positive = good, negative = dark.
    """

    def __init__(self):
        self.standings: dict[str, int] = {
            g.value: 50 for g in SocialGroup
        }
        self.karma: int = 0
        # global single-value reputation stat (starts at 0)
        self.reputation_score: int = 0

    # ── modify ────────────────────────────────────────────────

    def modify(self, group: str, delta: int):
        """Adjust reputation with *group* by *delta* (clamped 0–100).

        Parameters
        ----------
        group : group name string (e.g. ``SocialGroup.ATHLETES.value``)
        delta : positive or negative adjustment
        """
        if group in self.standings:
            self.standings[group] = max(0, min(100, self.standings[group] + delta))

    def modify_karma(self, delta: int):
        """Adjust the global karma counter."""
        self.karma += delta

    def modify_all(self, delta: int):
        """Apply *delta* to every group simultaneously."""
        for group in self.standings:
            self.modify(group, delta)

    # ── queries ───────────────────────────────────────────────

    def get(self, group: str) -> int:
        """Return current standing with *group* (default 50)."""
        return self.standings.get(group, 50)

    def get_all(self) -> dict[str, int]:
        """Return a copy of all standings."""
        return dict(self.standings)

    def average(self) -> float:
        """Weighted average across all groups."""
        vals = list(self.standings.values())
        return sum(vals) / len(vals) if vals else 50.0

    def highest_group(self) -> str:
        """Return the group with the highest reputation."""
        return max(self.standings, key=self.standings.get)

    def lowest_group(self) -> str:
        """Return the group with the lowest reputation."""
        return min(self.standings, key=self.standings.get)

    # ── ending calculation ────────────────────────────────────

    def calculate_ending(self) -> Ending:
        """Determine game ending based on accumulated reputation + karma.

        Rules
        -----
        * Good Ending   :  avg > 35  AND  karma > -20
        * Dark Ending   :  avg <= 35  OR   karma <= -20
        """
        avg = self.average()
        if avg <= 35 or self.karma <= -20:
            return Ending.DARK
        return Ending.GOOD

    def get_ending_color(self) -> tuple:
        """Return a UI colour matching the projected ending."""
        ending = self.calculate_ending()
        if ending == Ending.GOOD:
            return NOTIF_SUCCESS
        elif ending == Ending.DARK:
            return NOTIF_ERROR
        return NOTIF_WARNING

    # ── anti-bullying helpers ─────────────────────────────────

    def record_witness_action(self, action: str):
        """Called when the player witnesses bullying.

        *action* is one of ``"intervene"``, ``"record"``, ``"ignore"``.
        """
        if action == "intervene":
            self.modify_karma(10)
            self.modify_all(3)
        elif action == "record":
            self.modify_karma(5)
            self.modify(SocialGroup.TECH_CLUB.value, 5)
        elif action == "ignore":
            self.modify_karma(-5)
            self.modify_all(-2)

    def record_help_npc(self, group: str):
        """Player helped an NPC having a bad day."""
        self.modify_karma(8)
        self.modify(group, 10)

    def record_cyberbully_intercept(self):
        """Lena intercepted a cyberbullying campaign."""
        self.modify_karma(12)
        self.modify(SocialGroup.TECH_CLUB.value, 8)
        self.modify(SocialGroup.OUTSIDERS.value, 5)

    # ── serialisation ─────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"standings": dict(self.standings), "karma": self.karma, "reputation_score": self.reputation_score}

    def from_dict(self, data: dict):
        self.standings = data.get("standings", self.standings)
        self.karma     = data.get("karma", 0)
        self.reputation_score = data.get("reputation_score", 0)

    def __repr__(self):
        return f"Reputation(avg={self.average():.0f}, karma={self.karma})"
