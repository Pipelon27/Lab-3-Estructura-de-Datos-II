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
    # ── RESPOND — engaging honestly: strong gains with that group, small ripples elsewhere
    ("athletes", "respond"):       [
        ("athletes",  "respect", +10),
        ("outsiders", "respect", +4),
        ("academics", "respect", -2),
    ],
    ("tech_club", "respond"):      [
        ("tech_club", "respect", +10),
        ("academics", "respect", +5),
        ("athletes",  "respect", -2),
    ],
    ("populars", "respond"):       [
        ("populars",  "respect", +9),
        ("outsiders", "respect", +3),
        ("rebels",    "respect", -2),
    ],
    ("academics", "respond"):      [
        ("academics", "respect", +10),
        ("tech_club", "respect", +4),
        ("rebels",    "respect", -3),
    ],
    ("rebels", "respond"):         [
        ("rebels",    "respect", +10),
        ("outsiders", "respect", +4),
        ("populars",  "respect", -3),
    ],
    ("outsiders", "respond"):      [
        ("outsiders", "respect", +9),
        ("tech_club", "respect", +3),
        ("populars",  "respect", -2),
    ],

    # ── IGNORE — dismissive: hurts that group, slight boost from rivals
    ("athletes", "ignore"):        [
        ("athletes",  "respect", -6),
        ("populars",  "respect", -4),
        ("outsiders", "respect", +3),
    ],
    ("tech_club", "ignore"):       [
        ("tech_club", "respect", -5),
        ("academics", "respect", -4),
        ("rebels",    "respect", +3),
    ],
    ("populars", "ignore"):        [
        ("populars",  "respect", -7),
        ("outsiders", "respect", +3),
        ("rebels",    "respect", +2),
    ],
    ("academics", "ignore"):       [
        ("academics", "respect", -5),
        ("tech_club", "respect", -3),
        ("rebels",    "respect", +4),
    ],
    ("rebels", "ignore"):          [
        ("rebels",    "respect", -6),
        ("athletes",  "respect", +3),
        ("academics", "respect", +2),
    ],
    ("outsiders", "ignore"):       [
        ("outsiders", "respect", -5),
        ("populars",  "respect", +3),
        ("academics", "respect", +2),
    ],

    # ── INTIMIDATE — aggressive
    ("athletes", "intimidate"):    [
        ("rebels",    "respect", +5),
        ("athletes",  "respect", -4),
        ("outsiders", "respect", -7),
    ],
    ("tech_club", "intimidate"):   [
        ("outsiders", "respect", -6),
        ("populars",  "respect", -5),
    ],
    ("populars", "intimidate"):    [
        ("rebels",    "respect", +5),
        ("outsiders", "respect", -8),
        ("academics", "respect", -4),
    ],
    ("academics", "intimidate"):   [
        ("populars",  "respect", -5),
        ("rebels",    "respect", +6),
        ("outsiders", "respect", -5),
    ],
    ("rebels", "intimidate"):      [
        ("athletes",  "respect", -7),
        ("populars",  "respect", -5),
        ("outsiders", "respect", -4),
    ],
    ("outsiders", "intimidate"):   [
        ("populars",  "respect", -6),
        ("athletes",  "respect", -4),
        ("academics", "respect", -4),
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
                changed_subgroups = set(d.subgroup for d in deltas if not d.subgroup.startswith("global_"))
                for grp in changed_subgroups:
                    subgroup_respect_sum = sum(d.delta for d in deltas if d.subgroup == grp and d.stat == "respect")
                    if subgroup_respect_sum != 0:
                        self.reputation_system.modify(grp, subgroup_respect_sum)
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
        # Per-action deltas applied directly to the individual NPC's personal stats.
        # Respond gives significantly better gains to encourage kind play.
        _INDIVIDUAL_DELTAS = {
            "respond":    {"relationship": +10, "npc_trust": +8,  "npc_fear": -4},
            "ignore":     {"relationship": -5,  "npc_trust": -4,  "npc_fear": +2},
            "intimidate": {"relationship": -10, "npc_trust": -9,  "npc_fear": +14},
        }
        deltas = _INDIVIDUAL_DELTAS.get(action, {})
        for stat, delta in deltas.items():
            cur = getattr(npc, stat, 50)
            new_val = max(0, min(100, cur + delta))
            setattr(npc, stat, new_val)

        # Update allied status on individual NPC too
        npc.is_allied = npc.relationship >= ALLY_THRESHOLD

        # Synchronize individual stats to the game's RelationshipGraph
        if hasattr(self, "game") and self.game:
            try:
                player_key = f"player_{self.game.character.value}"
                rel_edge = self.game.npc_manager.relationships.get_relationship(player_key, npc.id)
                if rel_edge:
                    rel_edge.friendship = npc.relationship
                    rel_edge.trust = npc.npc_trust
                    rel_edge.fear = npc.npc_fear
                    if npc.group and npc.group.value in self.subgroups:
                        rel_edge.respect = self.subgroups[npc.group.value].respect
                    print(f"[SocialSystem] Synced RelationshipGraph edge for {npc.name}: {rel_edge}")
            except Exception as e:
                print(f"[SocialSystem] Failed to sync with RelationshipGraph: {e}")

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
