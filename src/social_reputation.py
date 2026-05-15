"""
src/social_reputation.py  —  Social reputation system
=======================================================
Augments the base ReputationSystem with a multi-layer social architecture.
Manages subgroup relationships, atmospheric state, and interaction deltas.

NOT a replacement for ReputationSystem (kept for ending calculation),
but rather a NEW layer on top that drives moment-to-moment social dynamics.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from settings import (
    SocialGroup, ALLY_THRESHOLD,
)


# ══════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ══════════════════════════════════════════════════════════════

class AtmosphereState(Enum):
    """Global emotional tone of the school."""
    COLD    = auto()      # fear/tension dominant
    NEUTRAL = auto()      # balanced
    WARM    = auto()      # trust/openness dominant
    TENSE   = auto()      # mixed high-intensity emotions


@dataclass
class SubgroupRecord:
    """Tracks relationship metrics with a single social group."""
    respect: int = 50     # 0–100
    trust: int = 50
    fear: int = 0
    ally: bool = False    # auto-set when relationship >= ALLY_THRESHOLD

    def to_dict(self) -> dict:
        return {
            "respect": self.respect,
            "trust": self.trust,
            "fear": self.fear,
            "ally": self.ally,
        }


@dataclass
class ReputationDelta:
    """Represents a single reputation change (displayed to player)."""
    subgroup: str          # e.g. "athletes", "global_fear"
    stat: str              # e.g. "respect", "fear"
    delta: int             # positive or negative
    is_negative: bool = False  # True if delta < 0

    def __post_init__(self):
        self.is_negative = self.delta < 0


# ══════════════════════════════════════════════════════════════
#  SUBGROUP INTERACTION MATRIX
# ══════════════════════════════════════════════════════════════

SUBGROUP_MATRIX = {
    # RESPOND action (honest, respectful engagement)
    ("athletes", "respond"):       [
        ("athletes", "respect", +7),
        ("academics", "trust", -4),
        ("outsiders", "trust", +2),
    ],
    ("tech_club", "respond"):      [
        ("tech_club", "respect", +8),
        ("academics", "respect", +4),
        ("athletes", "trust", -2),
    ],
    ("populars", "respond"):       [
        ("populars", "respect", +6),
        ("rebels", "trust", -3),
        ("outsiders", "trust", -2),
    ],
    ("academics", "respond"):      [
        ("academics", "respect", +8),
        ("tech_club", "respect", +3),
        ("rebels", "trust", -5),
    ],
    ("rebels", "respond"):         [
        ("rebels", "respect", +7),
        ("populars", "trust", -5),
        ("outsiders", "trust", +3),
    ],
    ("outsiders", "respond"):      [
        ("outsiders", "respect", +6),
        ("tech_club", "trust", +2),
        ("populars", "trust", -4),
    ],

    # IGNORE action (dismissive, walking away)
    ("athletes", "ignore"):        [
        ("athletes", "respect", -5),
        ("populars", "respect", -3),
        ("outsiders", "trust", +4),
    ],
    ("tech_club", "ignore"):       [
        ("tech_club", "respect", -4),
        ("academics", "respect", -3),
        ("athletes", "trust", +3),
    ],
    ("populars", "ignore"):        [
        ("populars", "respect", -6),
        ("outsiders", "respect", +4),
        ("athletes", "trust", +2),
    ],
    ("academics", "ignore"):       [
        ("academics", "respect", -4),
        ("tech_club", "respect", -2),
        ("rebels", "respect", +5),
    ],
    ("rebels", "ignore"):          [
        ("rebels", "respect", -5),
        ("athletes", "respect", +3),
        ("academics", "respect", +2),
    ],
    ("outsiders", "ignore"):       [
        ("outsiders", "respect", -3),
        ("populars", "trust", +3),
        ("academics", "trust", +2),
    ],

    # INTIMIDATE action (aggressive, threatening)
    ("athletes", "intimidate"):    [
        ("rebels", "respect", +4),
        ("athletes", "respect", +3),
        ("outsiders", "fear", +6),
        ("global_trust", "value", -8),
    ],
    ("tech_club", "intimidate"):   [
        ("outsiders", "respect", +5),
        ("populars", "fear", +5),
        ("global_trust", "value", -10),
    ],
    ("populars", "intimidate"):    [
        ("rebels", "fear", +4),
        ("outsiders", "fear", +7),
        ("academics", "fear", +3),
        ("global_trust", "value", -12),
    ],
    ("academics", "intimidate"):   [
        ("populars", "fear", +5),
        ("rebels", "respect", +6),
        ("outsiders", "fear", +4),
        ("global_trust", "value", -9),
    ],
    ("rebels", "intimidate"):      [
        ("athletes", "fear", +6),
        ("populars", "fear", +5),
        ("outsiders", "fear", +3),
        ("global_trust", "value", -7),
    ],
    ("outsiders", "intimidate"):   [
        ("populars", "fear", +6),
        ("athletes", "fear", +4),
        ("academics", "fear", +3),
        ("global_trust", "value", -10),
    ],
}


# ══════════════════════════════════════════════════════════════
#  REPUTATION MANAGER
# ══════════════════════════════════════════════════════════════

class ReputationManager:
    """Manages per-subgroup relationship state and global atmosphere.
    
    This layer sits on top of the base ReputationSystem and provides
    real-time tracking of player standing with each social group,
    including fear, trust, and respect metrics.
    """

    def __init__(self):
        # Per-group relationship records
        self.subgroups: dict[str, SubgroupRecord] = {
            group.value: SubgroupRecord() for group in SocialGroup
        }
        
        # Global emotions
        self.global_fear = 0         # 0–100
        self.global_trust = 50       # 0–100
        self.global_popularity = 50  # 0–100

        # Keep reference to base ReputationSystem for compat
        self.reputation_system = None

    def set_reputation_system(self, rep_sys):
        """Link the base ReputationSystem for ending calculation compat."""
        self.reputation_system = rep_sys

    # ── INTERACTION MATRIX APPLICATION ────────────────────────────────

    def apply_interaction(self, group: str, action: str,
                         npc_id: str = "",
                         dry_run: bool = False) -> list[ReputationDelta]:
        """Apply consequences of an interaction with a group.

        Parameters
        ----------
        group : str
            SocialGroup.value (e.g. "athletes")
        action : str
            "respond", "ignore", or "intimidate"
        npc_id : str
            NPC id (optional, for logging)

        Returns
        -------
        list[ReputationDelta]
            Changes that were applied (to display in UI)
        """
        deltas = []
        key = (group, action)

        if key not in SUBGROUP_MATRIX:
            print(f"[SocialSystem] Missing subgroup key: {key}")
            return deltas

        # Apply each delta from the matrix
        for entry in SUBGROUP_MATRIX.get(key, []):
            if not isinstance(entry, (list, tuple)) or len(entry) != 3:
                print(f"[SocialSystem] Invalid reputation entry: {entry}")
                continue
                
            target_group, stat, value = entry
            
            if not isinstance(value, (int, float)):
                print(f"[SocialSystem] Invalid reputation value: {entry}")
                continue

            delta = ReputationDelta(target_group, stat, value)
            deltas.append(delta)

            # Skip actual mutation when doing a preview (dry run)
            if dry_run:
                continue

            # Apply the change
            if target_group.startswith("global_"):
                # Global stats
                attr = target_group.replace("global_", "")
                if hasattr(self, attr):
                    cur = getattr(self, attr)
                    new_val = max(0, min(100, cur + value))
                    setattr(self, attr, new_val)
                    print(f"[SocialSystem] Reputation updated: {target_group} {value:+d}")
            else:
                # Group-specific stats
                if stat not in ("respect", "trust", "fear"):
                    print(f"[SocialSystem] Invalid stat in entry: {entry}")
                    continue

                if target_group in self.subgroups:
                    rec = self.subgroups[target_group]
                    cur = getattr(rec, stat, 50)
                    new_val = max(0, min(100, cur + value))
                    setattr(rec, stat, new_val)

                    print(f"[SocialSystem] Reputation updated: {target_group.capitalize()} {stat} {value:+d}")

                    # Auto-update ally status
                    if stat == "respect":
                        rec.ally = new_val >= ALLY_THRESHOLD

        # Sync to base ReputationSystem (only when actually applying)
        if not dry_run and self.reputation_system:
            try:
                self.reputation_system.modify(group, max(-20, min(20, sum(
                    d.delta for d in deltas if d.subgroup == group and d.stat == "respect"
                ))))
            except Exception as e:
                print(f"[SocialSystem] Failed to sync with base reputation system: {e}")

        return deltas

    def apply_individual_npc_stats(self, npc, action: str):
        """Apply small stat changes directly to the individual NPC.

        These are separate from the subgroup-level reputation matrix and
        make the per-NPC relationship/trust/fear in the right panel respond
        visibly to each interaction.

        Parameters
        ----------
        npc : NPC
            The NPC that was interacted with.
        action : str
            "respond", "ignore", or "intimidate"
        """
        # Per-action deltas applied to the individual NPC
        _INDIVIDUAL_DELTAS = {
            "respond":    {"relationship": +6,  "npc_trust": +5,  "npc_fear": -2},
            "ignore":     {"relationship": -4,  "npc_trust": -3,  "npc_fear": +1},
            "intimidate": {"relationship": -8,  "npc_trust": -7,  "npc_fear": +10},
        }
        deltas = _INDIVIDUAL_DELTAS.get(action, {})
        for stat, delta in deltas.items():
            cur = getattr(npc, stat, 50)
            new_val = max(0, min(100, cur + delta))
            setattr(npc, stat, new_val)

        # Update allied status on individual NPC too
        npc.is_allied = npc.relationship >= ALLY_THRESHOLD

        print(f"[SocialSystem] {npc.name} personal stats updated via '{action}'")

    # ── QUERIES ───────────────────────────────────────────────────

    def get_atmosphere(self) -> AtmosphereState:
        """Determine the overall emotional state of the school."""
        avg_fear = self.global_fear
        avg_trust = self.global_trust
        
        if avg_fear > 70:
            return AtmosphereState.TENSE
        elif avg_fear > 50:
            return AtmosphereState.COLD
        elif avg_trust > 70:
            return AtmosphereState.WARM
        else:
            return AtmosphereState.NEUTRAL

    def is_allied(self, group: str) -> bool:
        """Check if player is allied with a group (respect ≥ ALLY_THRESHOLD)."""
        if group in self.subgroups:
            return self.subgroups[group].ally
        return False

    def get_display_data(self) -> dict:
        """Return a dict suitable for HUD/profile panel display."""
        return {
            "subgroups": {
                name: rec.to_dict() for name, rec in self.subgroups.items()
            },
            "global_fear": self.global_fear,
            "global_trust": self.global_trust,
            "global_popularity": self.global_popularity,
            "atmosphere": self.get_atmosphere().name,
        }

    def get_group_respect(self, group: str) -> int:
        """Convenience: get respect value for a group."""
        if group in self.subgroups:
            return self.subgroups[group].respect
        return 50

    def get_group_trust(self, group: str) -> int:
        """Convenience: get trust value for a group."""
        if group in self.subgroups:
            return self.subgroups[group].trust
        return 50

    def get_group_fear(self, group: str) -> int:
        """Convenience: get fear value for a group."""
        if group in self.subgroups:
            return self.subgroups[group].fear
        return 0

    def to_dict(self) -> dict:
        """Serialize for save/load."""
        return {
            "subgroups": {
                name: rec.to_dict() for name, rec in self.subgroups.items()
            },
            "global_fear": self.global_fear,
            "global_trust": self.global_trust,
            "global_popularity": self.global_popularity,
        }

    def from_dict(self, data: dict):
        """Deserialize from save/load."""
        if "subgroups" in data:
            for name, rec_dict in data["subgroups"].items():
                if name in self.subgroups:
                    rec = self.subgroups[name]
                    rec.respect = rec_dict.get("respect", 50)
                    rec.trust = rec_dict.get("trust", 50)
                    rec.fear = rec_dict.get("fear", 0)
                    rec.ally = rec_dict.get("ally", False)

        self.global_fear = data.get("global_fear", 0)
        self.global_trust = data.get("global_trust", 50)
        self.global_popularity = data.get("global_popularity", 50)
