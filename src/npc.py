"""
src/npc.py  —  NPCs and relationship graph
============================================
**Custom data-structure**: weighted *directed* graph for NPC
relationships (Friendship, Fear, Trust, Suspicion).

Each NPC has a *public face* and *private face* (the "mask" mechanic).
The private face is only revealed when the player's Trust with that
NPC exceeds a threshold (or Lena hacks their data).
"""

from __future__ import annotations

import json
import os
import random
import pygame
from collections import deque
from settings import (
    NPC_SIZE, NPC_SPEED, NPC_INTERACTION_RANGE,
    GROUP_COLORS, ZONE_NAMES,
    MEDIUM_GRAY, WHITE, UI_TEXT_DIM, BLACK,
    Character, SocialGroup, DayPhase, Direction,
    DATA_DIR,
)


# ══════════════════════════════════════════════════════════════
#  RELATIONSHIP GRAPH  (weighted directed, custom)
# ══════════════════════════════════════════════════════════════

class RelationshipEdge:
    """Directed edge carrying four relationship axes."""

    __slots__ = ("friendship", "respect", "fear", "trust", "suspicion")

    def __init__(self, friendship=50, respect=50, fear=0, trust=50, suspicion=0):
        self.friendship = friendship
        self.respect    = respect
        self.fear       = fear
        self.trust      = trust
        self.suspicion  = suspicion

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}

    def modify(self, stat: str, delta: int):
        """Clamp-safe modification of a single stat."""
        cur = getattr(self, stat, None)
        if cur is not None:
            setattr(self, stat, max(0, min(100, cur + delta)))

    def __repr__(self):
        return (f"Rel(fr={self.friendship}, re={self.respect}, "
                f"fe={self.fear}, tr={self.trust}, su={self.suspicion})")


class RelationshipGraph:
    """Weighted directed graph for NPC-to-NPC and NPC-to-Player relations.

    Nodes are identified by string IDs (NPC id or ``"player_aiden"`` /
    ``"player_lena"``).  Each directed edge stores a ``RelationshipEdge``.
    """

    def __init__(self):
        # adjacency: from_id → { to_id → RelationshipEdge }
        self._adj: dict[str, dict[str, RelationshipEdge]] = {}

    def add_node(self, node_id: str):
        if node_id not in self._adj:
            self._adj[node_id] = {}

    def add_relationship(self, from_id: str, to_id: str,
                         edge: RelationshipEdge | None = None):
        """Create or overwrite a directed edge."""
        self.add_node(from_id)
        self.add_node(to_id)
        self._adj[from_id][to_id] = edge or RelationshipEdge()

    def get_relationship(self, from_id: str, to_id: str) -> RelationshipEdge | None:
        return self._adj.get(from_id, {}).get(to_id)

    def update_relationship(self, from_id: str, to_id: str,
                            stat: str, delta: int):
        """Modify a single stat on an existing edge (creates edge if absent)."""
        edge = self.get_relationship(from_id, to_id)
        if edge is None:
            self.add_relationship(from_id, to_id)
            edge = self._adj[from_id][to_id]
        edge.modify(stat, delta)

    def get_allies(self, node_id: str, threshold: int = 70) -> list[str]:
        """Return IDs whose friendship with *node_id* ≥ threshold."""
        result = []
        for to_id, edge in self._adj.get(node_id, {}).items():
            if edge.friendship >= threshold:
                result.append(to_id)
        return result

    def get_enemies(self, node_id: str, threshold: int = 30) -> list[str]:
        """Return IDs whose friendship with *node_id* ≤ threshold."""
        result = []
        for to_id, edge in self._adj.get(node_id, {}).items():
            if edge.friendship <= threshold:
                result.append(to_id)
        return result

    def bfs(self, start: str, target: str) -> list[str] | None:
        """BFS shortest social path between two nodes."""
        if start not in self._adj or target not in self._adj:
            return None
        visited = {start}
        queue = deque([(start, [start])])
        while queue:
            cur, path = queue.popleft()
            if cur == target:
                return path
            for nb in self._adj.get(cur, {}):
                if nb not in visited:
                    visited.add(nb)
                    queue.append((nb, path + [nb]))
        return None

    def get_all_nodes(self) -> list[str]:
        return list(self._adj.keys())

    def __repr__(self):
        edges = sum(len(v) for v in self._adj.values())
        return f"RelationshipGraph(nodes={len(self._adj)}, edges={edges})"


# ══════════════════════════════════════════════════════════════
#  NPC
# ══════════════════════════════════════════════════════════════

class NPC:
    """A non-player character in Ravenside High.

    Each NPC has two "faces":
      • ``public_personality``  — what everyone sees
      • ``private_personality`` — revealed at high trust or via hacking

    Attributes (notable)
    --------------------
    schedule : dict[DayPhase, int]   maps day phase → zone id
    having_bad_day : bool            random-event flag
    """

    def __init__(self, npc_id: str, name: str, group: SocialGroup,
                 public_personality: str, private_personality: str,
                 schedule: dict | None = None,
                 dialogue_ids: dict | None = None):
        self.id                  = npc_id
        self.name                = name
        self.group               = group
        self.public_personality  = public_personality
        self.private_personality = private_personality
        self.schedule            = schedule or {}      # DayPhase.value → zone_id
        self.dialogue_ids        = dialogue_ids or {}  # character_value → dialogue_id
        self.having_bad_day      = False
        self.mask_revealed       = False               # True when private face shown

        # Current zone & position
        self.current_zone = 0
        self.current_floor = 1       # floor the NPC is on (default: 1F)
        self.rect = pygame.Rect(
            random.randint(60, 600),
            random.randint(60, 500),
            NPC_SIZE, NPC_SIZE,
        )
        self.direction = random.choice(list(Direction))
        self.color = GROUP_COLORS.get(group.value, MEDIUM_GRAY)

        # Simple wander AI
        self._wander_timer = random.uniform(1, 4)
        self._wander_dx    = 0
        self._wander_dy    = 0

    # ── schedule ──────────────────────────────────────────────

    def get_zone_for_phase(self, phase: DayPhase) -> int:
        """Return zone id this NPC should be in during *phase*."""
        return self.schedule.get(phase.value, 0)

    def move_to_zone(self, zone_id: int):
        """Teleport NPC to a new zone (resets position randomly)."""
        from settings import ZONE_TO_FLOOR
        self.current_zone = zone_id
        entry = ZONE_TO_FLOOR.get(zone_id, (1, 400, 400))
        self.current_floor = entry[0]
        # Spawn near the mapped spawn point with some randomness
        sx, sy = entry[1], entry[2]
        self.rect.x = sx + random.randint(-80, 80)
        self.rect.y = sy + random.randint(-80, 80)

    # ── stats / mask ──────────────────────────────────────────

    def get_personality(self) -> str:
        """Return the currently visible personality string."""
        return self.private_personality if self.mask_revealed else self.public_personality

    def reveal_mask(self):
        """Permanently reveal the private face."""
        self.mask_revealed = True

    def get_dialogue_id(self, character: Character) -> str | None:
        """Return a dialogue tree id for this NPC when talking to *character*."""
        return self.dialogue_ids.get(character.value)

    def modify_stat(self, stat: str, value):
        """Convenience — delegates to the global relationship graph."""
        # This is handled externally by NPCManager
        pass

    # ── AI wander ─────────────────────────────────────────────

    def update(self, dt: float, walls: list[pygame.Rect] | None = None):
        """Simple random wander behaviour."""
        self._wander_timer -= dt
        if self._wander_timer <= 0:
            self._wander_timer = random.uniform(2, 5)
            self._wander_dx = random.choice([-1, 0, 0, 1]) * NPC_SPEED
            self._wander_dy = random.choice([-1, 0, 0, 1]) * NPC_SPEED
            if self._wander_dx > 0:
                self.direction = Direction.RIGHT
            elif self._wander_dx < 0:
                self.direction = Direction.LEFT
            elif self._wander_dy > 0:
                self.direction = Direction.DOWN
            elif self._wander_dy < 0:
                self.direction = Direction.UP

        self.rect.x += int(self._wander_dx * dt * 30)
        self.rect.y += int(self._wander_dy * dt * 30)

        # Stay within zone bounds (uses floor bounds if available)
        max_x = getattr(self, '_floor_w', 3200) - NPC_SIZE - 30
        max_y = getattr(self, '_floor_h', 2400) - NPC_SIZE - 30
        self.rect.clamp_ip(pygame.Rect(30, 30, max_x, max_y))

    # ── drawing ───────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, camera):
        """Draw NPC as a coloured square with group-tinted outline."""
        dr = camera.apply(self)
        pygame.draw.rect(screen, self.color, dr, border_radius=4)
        pygame.draw.rect(screen, WHITE, dr, 1, border_radius=4)

        # Name label
        font = pygame.font.SysFont("arial", 13)
        label = font.render(self.name, True, WHITE)
        screen.blit(label, label.get_rect(center=(dr.centerx, dr.top - 10)))

        # Bad-day indicator
        if self.having_bad_day:
            ind = font.render("😟", True, WHITE)
            screen.blit(ind, (dr.right + 2, dr.top))

    # ── serialisation ─────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "group": self.group.value,
            "public_personality": self.public_personality,
            "private_personality": self.private_personality,
            "schedule": self.schedule,
            "dialogue_ids": self.dialogue_ids,
            "zone": self.current_zone,
            "floor": self.current_floor,
            "x": self.rect.x, "y": self.rect.y,
        }

    @classmethod
    def from_dict(cls, data: dict) -> NPC:
        return cls(
            npc_id=data["id"], name=data["name"],
            group=SocialGroup(data["group"]),
            public_personality=data.get("public_personality", ""),
            private_personality=data.get("private_personality", ""),
            schedule=data.get("schedule", {}),
            dialogue_ids=data.get("dialogue_ids", {}),
        )

    def __repr__(self):
        return f"NPC({self.id}, '{self.name}', {self.group.value})"


# ══════════════════════════════════════════════════════════════
#  NPC MANAGER
# ══════════════════════════════════════════════════════════════

class NPCManager:
    """Owns all NPCs, the global relationship graph, and zone queries."""

    def __init__(self):
        self.npcs: dict[str, NPC] = {}
        self.relationships = RelationshipGraph()

    # ── loading ───────────────────────────────────────────────

    def load_npcs_from_json(self):
        """Load NPCs from ``data/npcs.json``.  Falls back to defaults."""
        path = os.path.join(DATA_DIR, "npcs.json")
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            for entry in data.get("npcs", []):
                npc = NPC.from_dict(entry)
                self.npcs[npc.id] = npc
                self.relationships.add_node(npc.id)
            # Load relationship edges
            for rel in data.get("relationships", []):
                self.relationships.add_relationship(
                    rel["from"], rel["to"],
                    RelationshipEdge(**rel.get("stats", {})),
                )
        except (FileNotFoundError, json.JSONDecodeError):
            self._create_default_npcs()

        # Always add player nodes
        self.relationships.add_node("player_aiden")
        self.relationships.add_node("player_lena")
        # Create default player→NPC relationships
        for npc_id in self.npcs:
            if not self.relationships.get_relationship("player_aiden", npc_id):
                self.relationships.add_relationship("player_aiden", npc_id)
            if not self.relationships.get_relationship("player_lena", npc_id):
                self.relationships.add_relationship("player_lena", npc_id)

    def _create_default_npcs(self):
        """Fallback NPCs when JSON is missing."""
        defaults = [
            ("npc_marcus",  "Marcus Rivera", SocialGroup.ATHLETES,
             "Friendly team captain", "Secretly pressured by Smile Club",
             {"arrival": 0, "class_1": 0, "break_1": 1, "lunch": 3,
              "activities": 1, "departure": 0, "night": 5},
             {"aiden": "dlg_marcus_aiden", "lena": "dlg_marcus_lena"}),
            ("npc_sophie",  "Sophie Chen", SocialGroup.TECH_CLUB,
             "Quiet coder", "Runs an anonymous anti-bullying blog",
             {"arrival": 0, "class_1": 2, "break_1": 4, "lunch": 3,
              "activities": 2, "departure": 0, "night": 2},
             {"aiden": "dlg_sophie_aiden", "lena": "dlg_sophie_lena"}),
            ("npc_dylan",   "Dylan Brooks", SocialGroup.POPULARS,
             "Charming influencer", "Core member of the Smile Club",
             {"arrival": 0, "class_1": 0, "break_1": 3, "lunch": 3,
              "activities": 5, "departure": 0, "night": 5},
             {"aiden": "dlg_dylan_aiden", "lena": "dlg_dylan_lena"}),
            ("npc_emma",    "Emma Torres", SocialGroup.ACADEMICS,
             "Studious valedictorian", "Being blackmailed for grades",
             {"arrival": 0, "class_1": 4, "break_1": 4, "lunch": 3,
              "activities": 4, "departure": 0, "night": 4},
             {"aiden": "dlg_emma_aiden", "lena": "dlg_emma_lena"}),
            ("npc_jake",    "Jake Morrison", SocialGroup.REBELS,
             "Troublemaker", "Has evidence against Smile Club",
             {"arrival": 0, "class_1": 0, "break_1": 5, "lunch": 3,
              "activities": 5, "departure": 0, "night": 5},
             {"aiden": "dlg_jake_aiden", "lena": "dlg_jake_lena"}),
            ("npc_mia",     "Mia Nakamura", SocialGroup.OUTSIDERS,
             "Transfer student", "Victim of cyberbullying campaign",
             {"arrival": 0, "class_1": 0, "break_1": 4, "lunch": 3,
              "activities": 4, "departure": 0, "night": 0},
             {"aiden": "dlg_mia_aiden", "lena": "dlg_mia_lena"}),
            ("npc_director","Director Walsh", SocialGroup.ACADEMICS,
             "Respected principal", "Created Smile Club for social control",
             {"arrival": 0, "class_1": 0, "break_1": 0, "lunch": 0,
              "activities": 0, "departure": 0, "night": 6},
             {"aiden": "dlg_walsh_aiden", "lena": "dlg_walsh_lena"}),
            ("npc_tyler",   "Tyler Dunn", SocialGroup.ATHLETES,
             "Star quarterback", "Bullies others to maintain status",
             {"arrival": 0, "class_1": 0, "break_1": 1, "lunch": 3,
              "activities": 1, "departure": 0, "night": 5},
             {"aiden": "dlg_tyler_aiden", "lena": "dlg_tyler_lena"}),
            ("npc_ava",     "Ava Patel", SocialGroup.POPULARS,
             "Social media queen", "Runs the cyber-harassment accounts",
             {"arrival": 0, "class_1": 0, "break_1": 3, "lunch": 3,
              "activities": 2, "departure": 0, "night": 5},
             {"aiden": "dlg_ava_aiden", "lena": "dlg_ava_lena"}),
            ("npc_lucas",   "Lucas Kim", SocialGroup.TECH_CLUB,
             "Hardware enthusiast", "Unknowingly maintains Smile servers",
             {"arrival": 0, "class_1": 2, "break_1": 2, "lunch": 3,
              "activities": 2, "departure": 0, "night": 2},
             {"aiden": "dlg_lucas_aiden", "lena": "dlg_lucas_lena"}),
            ("npc_zoe",     "Zoe Martin", SocialGroup.REBELS,
             "Graffiti artist", "Leaves coded messages about Smile Club",
             {"arrival": 0, "class_1": 0, "break_1": 5, "lunch": 3,
              "activities": 5, "departure": 0, "night": 5},
             {"aiden": "dlg_zoe_aiden", "lena": "dlg_zoe_lena"}),
            ("npc_noah",    "Noah Harris", SocialGroup.OUTSIDERS,
             "Shy bookworm", "Knows history of the original anti-bully system",
             {"arrival": 0, "class_1": 4, "break_1": 4, "lunch": 3,
              "activities": 4, "departure": 0, "night": 4},
             {"aiden": "dlg_noah_aiden", "lena": "dlg_noah_lena"}),
        ]
        for npc_id, name, group, pub, priv, sched, dlg in defaults:
            npc = NPC(npc_id, name, group, pub, priv, sched, dlg)
            self.npcs[npc_id] = npc
            self.relationships.add_node(npc_id)

        # Some default NPC-to-NPC relationships
        self.relationships.add_relationship("npc_marcus", "npc_tyler", RelationshipEdge(friendship=70, trust=40))
        self.relationships.add_relationship("npc_dylan", "npc_ava", RelationshipEdge(friendship=80, trust=60, suspicion=10))
        self.relationships.add_relationship("npc_sophie", "npc_lucas", RelationshipEdge(friendship=75, trust=65))
        self.relationships.add_relationship("npc_jake", "npc_zoe", RelationshipEdge(friendship=65, trust=55))
        self.relationships.add_relationship("npc_mia", "npc_noah", RelationshipEdge(friendship=55, trust=45))
        self.relationships.add_relationship("npc_director", "npc_dylan", RelationshipEdge(friendship=30, trust=20, fear=40))

    # ── queries ───────────────────────────────────────────────

    def get_npc_by_id(self, npc_id: str) -> NPC | None:
        return self.npcs.get(npc_id)

    def get_npcs_in_zone(self, zone_id: int) -> list[NPC]:
        """Return all NPCs whose current_zone matches (legacy compat)."""
        return [n for n in self.npcs.values() if n.current_zone == zone_id]

    def get_npcs_on_floor(self, floor_id: int) -> list[NPC]:
        """Return all NPCs on the given floor."""
        return [n for n in self.npcs.values() if n.current_floor == floor_id]

    def get_npcs_by_group(self, group: SocialGroup) -> list[NPC]:
        return [n for n in self.npcs.values() if n.group == group]

    # ── schedule update ───────────────────────────────────────

    def update_schedules(self, phase: DayPhase):
        """Move every NPC to the zone their schedule dictates."""
        for npc in self.npcs.values():
            target_zone = npc.get_zone_for_phase(phase)
            if npc.current_zone != target_zone:
                npc.move_to_zone(target_zone)
            npc.having_bad_day = False      # reset each phase

    # ── per-frame update ──────────────────────────────────────

    def update(self, dt: float, current_zone: int):
        """Tick AI for NPCs in the active zone (legacy)."""
        for npc in self.get_npcs_in_zone(current_zone):
            npc.update(dt)

    def update_on_floor(self, dt: float, floor_id: int, floor=None):
        """Tick AI for NPCs on the given floor."""
        for npc in self.get_npcs_on_floor(floor_id):
            if floor:
                npc._floor_w = floor.width
                npc._floor_h = floor.height
            npc.update(dt)

    def __repr__(self):
        return f"NPCManager({len(self.npcs)} npcs, {self.relationships})"
