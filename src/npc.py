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
    FLOOR_1F, FLOOR_2F,
    DATA_DIR, VT323_PATH)


# ══════════════════════════════════════════════════════════════
#  HELPERS & CONSTANTS
# ══════════════════════════════════════════════════════════════

def is_generic_wanderer(npc_id: str) -> bool:
    special = {
        "npc_gordon", "npc_oscar", "npc_director",
        "npc_oscar_obs1", "npc_oscar_obs2", "npc_oscar_obs3", "npc_oscar_obs4",
        "npc_bath_m_attendant", "npc_bath_f_attendant",
        "npc_noah_carter", "npc_axel_knight", "npc_ava_thompson",
        "npc_alan_chen", "npc_lena", "npc_aiden"
    }
    return not npc_id.startswith("npc_class_") and npc_id not in special


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
                 dialogue_ids: dict | None = None,
                 gender: str = "unspecified"):
        self.id                  = npc_id
        self.name                = name
        self.group               = group
        self.public_personality  = public_personality
        self.private_personality = private_personality
        self.schedule            = schedule or {}      # DayPhase.value → zone_id
        self.dialogue_ids        = dialogue_ids or {}  # character_value → dialogue_id
        self.having_bad_day      = False
        self.mask_revealed       = False               # True when private face shown
        self.gender              = (gender or "unspecified").lower()

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

        self.ignore_schedule = False
        self.subgroup: str = ""          # assigned by ScheduleManager
        self.walk_speed_variance: float = random.uniform(0.9, 1.1)

        # ──────── SOCIAL COMPONENT ────────────────────────────
        # Personal relationship metrics with the player
        self.relationship: int = 50        # personal relationship (0–100)
        self.npc_trust: int = 50           # personal trust
        self.npc_fear: int = 0             # personal fear
        self.traits: list[str] = []        # e.g. ["Manipulative", "Observant"]
        self.interaction_cooldown: float = 0.0

        # Social memory (persistent per session)
        self.last_interaction_type: str | None = None   # "respond"|"ignore"|"intimidate"
        self.interaction_count: int = 0
        self.intimidation_count: int = 0
        self.avoidance_tendency: float = 0.0  # 0.0–1.0

        # Behavioral state derived from memory
        self.is_afraid: bool = False
        self.is_allied: bool = False
        self.emotional_state: str = "neutral"  # "neutral"|"nervous"|"open"|"hostile"
        # ───────────────────────────────────────────────────

        # Movement / AI state
        self.target_pos: tuple[int, int] | None = None
        self.target_queue: list[tuple[int, int]] = []
        self.start_delay = 0.0 # Staggered start delay
        self.stop_at_target = False # Disable AI upon reaching final target
        self._wander_timer = random.uniform(1, 4)
        self._wander_dx    = 0
        self._wander_dy    = 0
        self.ai_enabled    = True
        self.show_name     = True

        # Combat state
        self.max_health = 50
        self.health = 50
        self.is_hostile = False
        self.attack_cooldown = 0.0
        self.knockout_timer = 0.0

        # Stealth state
        self.stealth_state = "PATROL" # IDLE, PATROL, SUSPICIOUS, SEARCHING, ALERTED
        self.suspicion_level = 0.0
        self.vision_cone_angle = 90.0 # degrees

        # Animation state
        self.hurt_timer = 0.0
        self.knockout_time_elapsed = 0.0
        self.attack_timer = 0.0
        self.animations = {
            "idle_up": [], "idle_down": [], "idle_left": [], "idle_right": [],
            "walk_up": [], "walk_down": [], "walk_left": [], "walk_right": [],
            "attack_up": [], "attack_down": [], "attack_left": [], "attack_right": [],
            "hurt_up": [], "hurt_down": [], "hurt_left": [], "hurt_right": [],
            "knockout": [],
        }
        self.state = "idle"
        self.frame_index = 0
        self.animation_timer = 0.0
        self.image: pygame.Surface | None = None
        self._load_sprites()

    def _advance_animation(self, dt: float):
        """Advance sprite frames independently from AI movement."""
        if not self.animations:
            return

        if self.state == "knockout":
            anim_key = f"knockout_{self.direction.value}"
            frames = self.animations.get(anim_key, [])
            if not frames:
                frames = self.animations.get("knockout", [])
            if frames:
                self.frame_index = min(len(frames) - 1, int(self.knockout_time_elapsed * 6.0))
                self.image = frames[self.frame_index]
            return

        if self.state == "hurt":
            anim_key = f"hurt_{self.direction.value}"
            frames = self.animations.get(anim_key, [])
            if frames:
                self.frame_index = int((0.4 - self.hurt_timer) * 10.0) % len(frames)
                self.image = frames[self.frame_index]
            return

        if self.state == "attack":
            anim_key = f"attack_{self.direction.value}"
            frames = self.animations.get(anim_key, [])
            if frames:
                self.frame_index = int((0.2 - self.attack_timer) * 30.0) % len(frames)
                self.image = frames[self.frame_index]
            return

        fps = 10.0 if self.state == "walk" else 6.0
        self.animation_timer += dt * fps
        if self.animation_timer >= 1.0:
            self.animation_timer = 0.0
            self.frame_index = (self.frame_index + 1) % 6

        key = f"{self.state}_{self.direction.value}"
        frames = self.animations.get(key)
        if frames:
            self.image = frames[self.frame_index % len(frames)]

    def _load_sprites(self):
        """Extract idle and walk frames from the spritesheet."""
        base_dir = os.path.dirname(os.path.dirname(__file__))
        folder_map = {
            "academics": "ACADEMICS",
            "athletes": "ATHLETES",
            "populars": "POPULARS",
            "rebels": "REBELS",
            "tech_club": "TECH CLUB",
        }
        if self.id == "npc_aiden":
            path = os.path.join(base_dir, "assets", "Characters BEHIND THE SMILE", "PROTAGONISTS", "Aiden Parker.png")
        elif self.id == "npc_lena":
            path = os.path.join(base_dir, "assets", "Characters BEHIND THE SMILE", "PROTAGONISTS", "Lena Parker.png")
        elif self.id == "npc_director":
            path = os.path.join(base_dir, "assets", "Characters BEHIND THE SMILE", "especiales", "director walsh.png")
        elif self.id == "npc_gordon":
            path = os.path.join(base_dir, "assets", "Characters BEHIND THE SMILE", "especiales", "el gastroo.png")
        else:
            folder = folder_map.get(self.group.value)
            if not folder:
                return

            path = os.path.join(base_dir, "assets", "Characters BEHIND THE SMILE", folder, f"{self.name}.png")
            if not os.path.exists(path):
                return


        sheet = pygame.image.load(path).convert_alpha()
        frame_w, frame_h = 32, 64

        def get_frame(col, row):
            try:
                rect = pygame.Rect(col * frame_w, row * frame_h, frame_w, frame_h)
                return sheet.subsurface(rect).copy()
            except ValueError:
                # Safe fallback if bounds are exceeded
                return self.animations.get("idle_down", [None])[0]

        # Row 1 (Idle): Right (0-5), Up (6-11), Left (12-17), Down (18-23)
        self.animations["idle_right"] = [get_frame(c, 1) for c in range(0, 6)]
        self.animations["idle_up"]    = [get_frame(c, 1) for c in range(6, 12)]
        self.animations["idle_left"]  = [get_frame(c, 1) for c in range(12, 18)]
        self.animations["idle_down"]  = [get_frame(c, 1) for c in range(18, 24)]

        # Row 2 (Walk/Run): Right (0-5), Up (6-11), Left (12-17), Down (18-23)
        self.animations["walk_right"] = [get_frame(c, 2) for c in range(0, 6)]
        self.animations["walk_up"]    = [get_frame(c, 2) for c in range(6, 12)]
        self.animations["walk_left"]  = [get_frame(c, 2) for c in range(12, 18)]
        self.animations["walk_down"]  = [get_frame(c, 2) for c in range(18, 24)]

        # Row 12 (Shoot/Attack): Right (0-5), Up (6-11), Left (12-17), Down (18-23)
        self.animations["shoot_right"] = [get_frame(c, 12) for c in range(0, 6)]
        self.animations["shoot_up"]    = [get_frame(c, 12) for c in range(6, 12)]
        self.animations["shoot_left"]  = [get_frame(c, 12) for c in range(12, 18)]
        self.animations["shoot_down"]  = [get_frame(c, 12) for c in range(18, 24)]

        self.animations["attack_right"] = self.animations["shoot_right"]
        self.animations["attack_up"]    = self.animations["shoot_up"]
        self.animations["attack_left"]  = self.animations["shoot_left"]
        self.animations["attack_down"]  = self.animations["shoot_down"]

        # Row 7, Cols 0-11: Hurt recoil (3 frames per direction: Right, Up, Left, Down)
        self.animations["hurt_right"] = [get_frame(c, 7) for c in range(0, 3)]
        self.animations["hurt_up"]    = [get_frame(c, 7) for c in range(3, 6)]
        self.animations["hurt_left"]  = [get_frame(c, 7) for c in range(6, 9)]
        self.animations["hurt_down"]  = [get_frame(c, 7) for c in range(9, 12)]

        # Row 9, Cols 0-23: Sitting without book (6 frames per direction)
        self.animations["knockout_right"] = [get_frame(c, 9) for c in range(0, 6)]
        self.animations["knockout_up"]    = [get_frame(c, 9) for c in range(6, 12)]
        self.animations["knockout_left"]  = [get_frame(c, 9) for c in range(12, 18)]
        self.animations["knockout_down"]  = [get_frame(c, 9) for c in range(18, 24)]

        # Set default image
        self.image = self.animations["idle_down"][0]

    # ── schedule ──────────────────────────────────────────────

    def get_zone_for_phase(self, phase: DayPhase) -> int:
        """Return zone id this NPC should be in during *phase*."""
        return self.schedule.get(phase.value, 0)

    def move_to_zone(self, zone_id: int, school_map=None):
        """Teleport NPC to a new zone (resets position randomly)."""
        from settings import ZONE_TO_FLOOR
        self.current_zone = zone_id
        entry = ZONE_TO_FLOOR.get(zone_id, (1, 400, 400))
        self.current_floor = entry[0]
        
        if school_map:
            floor = school_map.get_floor(self.current_floor)
            if floor and floor.rooms:
                room = random.choice(list(floor.rooms.values()))
                rx, ry = get_safe_spawn_point(room.rect, floor.walls, self.rect)
                self.rect.center = (rx, ry)
                return

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

    # ── SOCIAL COMPONENT ──────────────────────────────────────

    def update_social_memory(self, action_type: str):
        """Update internal social state based on interaction action.
        
        Parameters
        ----------
        action_type : str
            "respond", "ignore", or "intimidate"
        """
        self.interaction_count += 1
        self.last_interaction_type = action_type

        if action_type == "intimidate":
            self.intimidation_count += 1
            self.is_afraid = True
            self.emotional_state = "nervous"
            self.avoidance_tendency = min(1.0, self.avoidance_tendency + 0.15)
        elif action_type == "respond":
            self.emotional_state = "open"
            self.avoidance_tendency = max(0.0, self.avoidance_tendency - 0.1)
        elif action_type == "ignore":
            self.avoidance_tendency = min(1.0, self.avoidance_tendency + 0.05)
            self.emotional_state = "neutral"

    def draw_interaction_prompt(self, screen: pygame.Surface, camera):
        """Draw the '[E] Talk' prompt above NPC when in interaction range.
        
        Called during normal game draw to show prompt to player.
        """
        if self.health <= 0:
            return
        from settings import NPC_SOCIAL_RANGE, UI_ACCENT, UI_TEXT
        
        from src.controller import get_controller
        controller = get_controller()
        is_controller = controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller"
        
        # Check if we should draw (will be called conditionally from game loop)
        if is_controller:
            prompt_text = "[A] Skills" if self.id == "npc_gordon" else "[A] Talk"
        else:
            prompt_text = "[E] Skills" if self.id == "npc_gordon" else "[E] Talk"
            
        font = pygame.font.Font(VT323_PATH, 12)
        text_surf = font.render(prompt_text, True, UI_ACCENT)
        
        # Draw above NPC sprite
        dr = camera.apply(self)
        text_rect = text_surf.get_rect(midbottom=(dr.centerx, dr.top - 15))
        
        # Draw semi-transparent background
        bg_rect = text_rect.inflate(6, 4)
        bg_surf = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(bg_surf, (0, 0, 0, 180), bg_surf.get_rect(), border_radius=3)
        screen.blit(bg_surf, bg_rect)
        screen.blit(text_surf, text_rect)

    def get_dialogue_id(self, character: Character) -> str | None:
        """Return a dialogue tree id for this NPC when talking to *character*."""
        return self.dialogue_ids.get(character.value)

    def modify_stat(self, stat: str, value):
        """Convenience — delegates to the global relationship graph."""
        # This is handled externally by NPCManager
        pass

    # ── AI wander ─────────────────────────────────────────────

    def update(self, dt: float, walls: list[pygame.Rect] | None = None):
        """Update AI and movement."""
        if not hasattr(self, '_prev_health'):
            self._prev_health = self.health

        # Monitor health changes
        if self.health < self._prev_health:
            self.hurt_timer = 0.4
            self.knockout_time_elapsed = 0.0
            self._prev_health = self.health
        elif self.health > self._prev_health:
            self._prev_health = self.health

        if self.hurt_timer > 0:
            self.hurt_timer -= dt

        if getattr(self, 'attack_timer', 0) > 0:
            self.attack_timer -= dt
            if self.attack_timer <= 0:
                self.state = "idle"

        if self.health <= 0:
            self.state = "knockout"
            self.knockout_time_elapsed += dt
            self._advance_animation(dt)
            
            if self.knockout_timer > 0:
                self.knockout_timer -= dt
                if self.knockout_timer <= 0:
                    self.health = self.max_health
                    self.knockout_timer = 0.0
                    self.state = "idle"
                    self.knockout_time_elapsed = 0.0
                    self._prev_health = self.health
            return

        if self.hurt_timer > 0:
            self.state = "hurt"
            self._advance_animation(dt)
            return

        if getattr(self, 'attack_timer', 0) > 0:
            self.state = "attack"
            self._advance_animation(dt)
            return

        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt

        if not self.ai_enabled:
            self._advance_animation(dt)
            return
            
        if self.start_delay > 0:
            self.start_delay -= dt
            return

        # Handle guided movement (towards target_pos)
        if getattr(self, "target_pos", None):
            tx, ty = self.target_pos
            dx_raw = tx - self.rect.centerx
            dy_raw = ty - self.rect.centery
            dist = (dx_raw**2 + dy_raw**2)**0.5
            
            if dist > 15:
                # Stuck detection
                if not hasattr(self, '_stuck_timer'):
                    self._stuck_timer = 0.0
                    self._last_pos = self.rect.center
                
                if walls and (self.rect.centerx - self._last_pos[0])**2 + (self.rect.centery - self._last_pos[1])**2 < 4:
                    self._stuck_timer += dt
                else:
                    self._stuck_timer = 0.0
                self._last_pos = self.rect.center
                
                if self._stuck_timer > 1.5:
                    self._stuck_timer = 0.0
                    # Skip to next waypoint or give up
                    if getattr(self, "target_queue", None) and len(self.target_queue) > 0:
                        self.target_pos = None # will pick up next waypoint on next frame
                    else:
                        self.target_pos = None
                        if getattr(self, "stop_at_target", False):
                            self.ai_enabled = False
                            self.stop_at_target = False
                        self._wander_timer = 0
                    return

                speed = NPC_SPEED * getattr(self, 'speed_multiplier', 1.0) * 1.5
                self._wander_dx = (dx_raw / dist) * speed
                self._wander_dy = (dy_raw / dist) * speed
                self._wander_timer = 0.5 # keep targeting
                # Update visual direction
                if abs(self._wander_dx) > abs(self._wander_dy):
                    self.direction = Direction.RIGHT if self._wander_dx > 0 else Direction.LEFT
                else:
                    self.direction = Direction.DOWN if self._wander_dy > 0 else Direction.UP
            else:
                if getattr(self, "target_queue", None) and len(self.target_queue) > 0:
                    next_target = self.target_queue.pop(0)
                    
                    if isinstance(next_target, str):
                        # Handle floor transitions (SWITCH_TO_F0..F6)
                        if next_target.startswith("SWITCH_TO_F"):
                            try:
                                floor_id = int(next_target[len("SWITCH_TO_F"):])
                                self.current_floor = floor_id
                            except ValueError:
                                pass
                        
                        # Get the next coordinate target if it exists
                        if self.target_queue:
                            nt = self.target_queue.pop(0)
                            if not isinstance(nt, str):
                                self.target_pos = nt
                    else:
                        self.target_pos = next_target
                else:
                    self.target_pos = None # Reached final target!
                    if getattr(self, "stop_at_target", False):
                        self.ai_enabled = False
                        self.stop_at_target = False
                    self._wander_timer = 0 # Resume normal wandering
        
        elif self._wander_timer <= 0:
            self._wander_timer = random.uniform(1, 3)
            speed = NPC_SPEED * getattr(self, 'speed_multiplier', 1.0)
            self._wander_dx = random.choice([-1, 0, 1]) * speed
            self._wander_dy = random.choice([-1, 0, 1]) * speed
            if self._wander_dx > 0:
                self.direction = Direction.RIGHT
            elif self._wander_dx < 0:
                self.direction = Direction.LEFT
            elif self._wander_dy > 0:
                self.direction = Direction.DOWN
            elif self._wander_dy < 0:
                self.direction = Direction.UP
        else:
            self._wander_timer -= dt

        dx = int(self._wander_dx * dt * 30)
        dy = int(self._wander_dy * dt * 30)

        collided = False
        if walls:
            self.rect.x += dx
            collided = self._collide(walls, dx, 0) or collided
            self.rect.y += dy
            collided = self._collide(walls, 0, dy) or collided
        else:
            self.rect.x += dx
            self.rect.y += dy

        # Stay within zone bounds (uses floor bounds if available)
        bound_rect = getattr(self, 'bound_rect', None)
        if bound_rect:
            before_clamp = self.rect.copy()
            self.rect.clamp_ip(bound_rect)
            collided = collided or self.rect.topleft != before_clamp.topleft
        else:
            before_clamp = self.rect.copy()
            max_x = getattr(self, '_floor_w', 3200) - NPC_SIZE - 30
            max_y = getattr(self, '_floor_h', 2400) - NPC_SIZE - 30
            self.rect.clamp_ip(pygame.Rect(30, 30, max_x, max_y))
            collided = collided or self.rect.topleft != before_clamp.topleft

        if collided:
            if not getattr(self, "target_pos", None):
                self._wander_timer = 0 # Repick direction immediately next frame
            else:
                self._wander_dx = 0
                self._wander_dy = 0
            self._wander_timer = min(self._wander_timer, 0.25)

        # Animation state update
        if abs(self._wander_dx) > 0 or abs(self._wander_dy) > 0:
            self.state = "walk"
        else:
            self.state = "idle"

        self._advance_animation(dt)

    def _collide(self, walls: list[pygame.Rect], dx: float, dy: float) -> bool:
        """Slide the NPC along walls instead of teleporting - prevents jitter."""
        collided = False
        # Separate axis handling for smoother sliding
        # First, handle X collisions
        if dx != 0:
            for wall in walls:
                if self.rect.colliderect(wall):
                    collided = True
                    if dx > 0:  # moving right
                        overlap = self.rect.right - wall.left
                        if overlap > 0 and overlap < self.rect.width:
                            self.rect.right = wall.left
                    elif dx < 0:  # moving left
                        overlap = wall.right - self.rect.left
                        if overlap > 0 and overlap < self.rect.width:
                            self.rect.left = wall.right
        
        # Then, handle Y collisions
        if dy != 0:
            for wall in walls:
                if self.rect.colliderect(wall):
                    collided = True
                    if dy > 0:  # moving down
                        overlap = self.rect.bottom - wall.top
                        if overlap > 0 and overlap < self.rect.height:
                            self.rect.bottom = wall.top
                    elif dy < 0:  # moving up
                        overlap = wall.bottom - self.rect.top
                        if overlap > 0 and overlap < self.rect.height:
                            self.rect.top = wall.bottom
        return collided

    # ── drawing ───────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, camera):
        """Draw NPC as a sprite or fallback to coloured square."""
        dr = camera.apply(self)
        
        if self.image:
            # The sprite is 32x64, we draw it so its bottom-center aligns with the collision rect bottom-center
            draw_rect = self.image.get_rect(midbottom=dr.midbottom)
            if getattr(self, "hurt_timer", 0) > 0 and int(self.hurt_timer * 20) % 2 == 0:
                # Premium red silhouette/flash using mask
                mask = pygame.mask.from_surface(self.image)
                mask_surf = mask.to_surface(setcolor=(255, 50, 50, 255), unsetcolor=(0, 0, 0, 0))
                screen.blit(self.image, draw_rect)
                mask_surf.set_alpha(150)
                screen.blit(mask_surf, draw_rect)
            else:
                screen.blit(self.image, draw_rect)
            
            # Name label (can be hidden for observers)
            if getattr(self, 'show_name', True):
                font = pygame.font.Font(VT323_PATH, 13)
                label = font.render(self.name, True, WHITE)
                screen.blit(label, label.get_rect(center=(draw_rect.centerx, draw_rect.top - 10)))
                
            # Bad-day indicator
            if self.having_bad_day:
                ind = font.render("😟", True, WHITE)
                screen.blit(ind, (draw_rect.right + 2, draw_rect.top))
        else:
            pygame.draw.rect(screen, self.color, dr, border_radius=4)
            pygame.draw.rect(screen, WHITE, dr, 1, border_radius=4)

            # Name label (can be hidden for observers)
            if getattr(self, 'show_name', True):
                font = pygame.font.Font(VT323_PATH, 13)
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
            gender=data.get("gender", "unspecified"),
        )

    def __repr__(self):
        return f"NPC({self.id}, '{self.name}', {self.group.value})"


# ══════════════════════════════════════════════════════════════
#  NPC MANAGER & HELPERS
# ══════════════════════════════════════════════════════════════

def get_safe_spawn_point(room_rect, floor_walls, npc_rect, max_attempts=40) -> tuple[int, int]:
    """Find a random coordinate inside room_rect that does not collide with floor_walls.
    Returns (x, y). If all attempts fail, returns the room center."""
    import random
    inner = room_rect.inflate(-60, -60)
    if inner.width <= 0 or inner.height <= 0:
        inner = room_rect
    for _ in range(max_attempts):
        x = random.randint(inner.left, inner.right)
        y = random.randint(inner.top, inner.bottom)
        npc_rect.center = (x, y)
        if not any(npc_rect.colliderect(w) for w in floor_walls):
            return x, y
    return inner.centerx, inner.centery


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
                if entry.get("id", "").startswith("npc_oscar_obs"):
                    continue
                npc = NPC.from_dict(entry)
                if npc.gender == "unspecified":
                    npc.gender = entry.get("gender") or random.choice(["male", "female"])
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
            ("npc_marcus",  "Marcus Green", SocialGroup.ATHLETES,
             "Friendly team captain", "Secretly pressured by Smile Club",
             {"arrival": 0, "class_1": 0, "break_1": 1, "lunch": 3,
              "activities": 1, "departure": 0, "night": 5},
             {"aiden": "dlg_marcus_aiden", "lena": "dlg_marcus_lena"}, "male"),
            ("npc_sophie",  "Sophie Chen", SocialGroup.TECH_CLUB,
             "Quiet coder", "Runs an anonymous anti-bullying blog",
             {"arrival": 0, "class_1": 2, "break_1": 4, "lunch": 3,
              "activities": 2, "departure": 0, "night": 2},
             {"aiden": "dlg_sophie_aiden", "lena": "dlg_sophie_lena"}, "female"),
            ("npc_dylan",   "Dylan Brooks", SocialGroup.POPULARS,
             "Charming influencer", "Core member of the Smile Club",
             {"arrival": 0, "class_1": 0, "break_1": 3, "lunch": 3,
              "activities": 5, "departure": 0, "night": 5},
             {"aiden": "dlg_dylan_aiden", "lena": "dlg_dylan_lena"}, "male"),
            ("npc_emma",    "Emma Torres", SocialGroup.ACADEMICS,
             "Studious valedictorian", "Being blackmailed for grades",
             {"arrival": 0, "class_1": 4, "break_1": 4, "lunch": 3,
              "activities": 4, "departure": 0, "night": 4},
             {"aiden": "dlg_emma_aiden", "lena": "dlg_emma_lena"}, "female"),
            ("npc_jake",    "Jake Morrison", SocialGroup.REBELS,
             "Troublemaker", "Has evidence against Smile Club",
             {"arrival": 0, "class_1": 0, "break_1": 5, "lunch": 3,
              "activities": 5, "departure": 0, "night": 5},
             {"aiden": "dlg_jake_aiden", "lena": "dlg_jake_lena"}, "male"),
            ("npc_mia",     "Mia Nakamura", SocialGroup.OUTSIDERS,
             "Transfer student", "Victim of cyberbullying campaign",
             {"arrival": 0, "class_1": 0, "break_1": 4, "lunch": 3,
              "activities": 4, "departure": 0, "night": 0},
             {"aiden": "dlg_mia_aiden", "lena": "dlg_mia_lena"}, "female"),
            ("npc_director","Director Walsh", SocialGroup.ACADEMICS,
             "Respected principal", "Created Smile Club for social control",
             {"arrival": 0, "class_1": 0, "break_1": 0, "lunch": 0,
              "activities": 0, "departure": 0, "night": 6},
             {"aiden": "dlg_walsh_aiden", "lena": "dlg_walsh_lena"}, "male"),
            ("npc_tyler",   "Tyler Dunn", SocialGroup.ATHLETES,
             "Star quarterback", "Bullies others to maintain status",
             {"arrival": 0, "class_1": 0, "break_1": 1, "lunch": 3,
              "activities": 1, "departure": 0, "night": 5},
             {"aiden": "dlg_tyler_aiden", "lena": "dlg_tyler_lena"}, "male"),
            ("npc_ava",     "Ava Patel", SocialGroup.POPULARS,
             "Social media queen", "Runs the cyber-harassment accounts",
             {"arrival": 0, "class_1": 0, "break_1": 3, "lunch": 3,
              "activities": 2, "departure": 0, "night": 5},
             {"aiden": "dlg_ava_aiden", "lena": "dlg_ava_lena"}, "female"),
            ("npc_lucas",   "Lucas Kim", SocialGroup.TECH_CLUB,
             "Hardware enthusiast", "Unknowingly maintains Smile servers",
             {"arrival": 0, "class_1": 2, "break_1": 2, "lunch": 3,
              "activities": 2, "departure": 0, "night": 2},
             {"aiden": "dlg_lucas_aiden", "lena": "dlg_lucas_lena"}, "male"),
            ("npc_zoe",     "Zoe Martin", SocialGroup.REBELS,
             "Graffiti artist", "Leaves coded messages about Smile Club",
             {"arrival": 0, "class_1": 0, "break_1": 5, "lunch": 3,
              "activities": 5, "departure": 0, "night": 5},
             {"aiden": "dlg_zoe_aiden", "lena": "dlg_zoe_lena"}, "female"),
            ("npc_noah",    "Noah Harris", SocialGroup.OUTSIDERS,
             "Shy bookworm", "Knows history of the original anti-bully system",
             {"arrival": 0, "class_1": 4, "break_1": 4, "lunch": 3,
              "activities": 4, "departure": 0, "night": 4},
             {"aiden": "dlg_noah_aiden", "lena": "dlg_noah_lena"}, "male"),
        ]
        for npc_id, name, group, pub, priv, sched, dlg, gender in defaults:
            npc = NPC(npc_id, name, group, pub, priv, sched, dlg, gender)
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

    def update_schedules(self, phase: DayPhase, school_map=None, is_visible=None):
        """Move every NPC to the zone their schedule dictates.
        
        Args:
            is_visible: Optional callback(npc) -> bool. If provided,
                NPCs where is_visible returns True will NOT be teleported.
        """
        from settings import FLOOR_CAMPUS, FLOOR_1F, FLOOR_2F, SocialGroup
        special_ids = {"npc_director", "npc_oscar", "npc_noah_carter", "npc_gordon",
                       "npc_oscar_obs1", "npc_oscar_obs2", "npc_oscar_obs3", "npc_oscar_obs4",
                       "npc_bath_m_attendant", "npc_bath_f_attendant"}

        regular_populars = [
            n for n in self.npcs.values()
            if n.group == SocialGroup.POPULARS and n.id not in special_ids and n.id != "npc_ava_thompson"
        ]
        scheduled_rooftop_populars = [n for n in regular_populars if n.get_zone_for_phase(phase) == 5]
        needed = 5 - len(scheduled_rooftop_populars)
        other_populars = [n for n in regular_populars if n not in scheduled_rooftop_populars]
        rooftop_populars = set(scheduled_rooftop_populars + other_populars[:max(0, needed)])

        for npc in self.npcs.values():
            if getattr(npc, "ignore_schedule", False):
                continue
                
            target_zone = npc.get_zone_for_phase(phase)
            if npc in rooftop_populars:
                target_zone = 5
            elif target_zone == 5 and npc.id != "npc_jake":
                target_zone = 0

            if npc.current_zone != target_zone:
                # If target is cafeteria (Zone 3), don't teleport - let game.py handle walking them in
                if target_zone == 3:
                    npc.current_zone = 3
                    continue
                # Skip teleportation if NPC is visible on camera
                if is_visible and is_visible(npc):
                    npc.current_zone = target_zone  # Update zone logically
                    continue
                npc.move_to_zone(target_zone, school_map)

            # Natural behavior for generic NPCs: scatter within valid rooms on their current floor
            # Only scatter if we JUST changed zone or if they aren't on any floor yet
            if npc.id not in special_ids and school_map and (npc.current_zone != target_zone or npc.current_floor == -1):
                # Skip scattering if NPC is visible on camera
                if is_visible and is_visible(npc):
                    continue
                floor = school_map.get_floor(npc.current_floor)
                if floor and floor.rooms:
                    # Filter out campus building interiors/facades, stairs, and bathrooms
                    _campus_excluded = {
                        "c_building", "f1_cafeteria",
                        "c_tennis", "c_coliseum", "c_coliseum_court",
                        "f1_stairs_2f", "f1_basement_stairs",
                        "f2_stairs_1f", "f2_stairs_rooftop", "bs_stairs_1f",
                        "f1_men_bath", "f1_women_bath"
                    }
                    valid_rooms = [r for r in floor.rooms.values() if r.id not in _campus_excluded]
                    if valid_rooms:
                        room = random.choice(valid_rooms)
                        rx, ry = get_safe_spawn_point(room.rect, floor.walls, npc.rect)
                        npc.rect.center = (rx, ry)
                        
                        # Natural movement: Give them a target inside the room to walk towards
                        if random.random() < 0.6:
                            tx, ty = get_safe_spawn_point(room.rect, floor.walls, npc.rect.copy())
                            npc.target_pos = (tx, ty)
                            npc.target_queue = []
                            npc.stop_at_target = False
                        else:
                            npc.target_pos = None

            npc.having_bad_day = False      # reset each phase

    # ── per-frame update ──────────────────────────────────────

    def update(self, dt: float, current_zone: int):
        """Tick AI for NPCs in the active zone (legacy)."""
        for npc in self.get_npcs_in_zone(current_zone):
            npc.update(dt)

    def update_on_floor(self, dt: float, floor_id: int, floor=None, walls: list[pygame.Rect] | None = None,
                        classrooms_restricted: bool = False, restricted_rooms: list[str] | None = None,
                        is_visible=None):
        """Tick AI for NPCs on the given floor."""
        npcs = self.get_npcs_on_floor(floor_id)
        for npc in npcs:
            if floor:
                npc._floor_w = floor.width
                npc._floor_h = floor.height
            
            # 1. Door avoidance for generic NPCs to keep exits clear
            if is_generic_wanderer(npc.id) and npc.target_pos is None:
                # Door locations on 2F
                doors = [(1080, 496), (1080, 1146), (1080, 1566), (1560, 1900), (2120, 200), (2120, 640)]
                for dx, dy in doors:
                    dist_sq = (npc.rect.centerx - dx)**2 + (npc.rect.centery - dy)**2
                    if dist_sq < 60**2: # Within 60 pixels
                        # Gentle push away
                        px = npc.rect.x
                        py = npc.rect.y
                        if npc.rect.centerx < dx: npc.rect.x -= 2
                        else: npc.rect.x += 2
                        if npc.rect.centery < dy: npc.rect.y -= 2
                        else: npc.rect.y += 2
                        if walls and any(npc.rect.colliderect(w) for w in walls):
                            npc.rect.x = px
                            npc.rect.y = py

            # 2. Build wall list including static walls + other NPCs (avoid self)
            npc_is_visible = is_visible(npc) if is_visible else True
            previous_rect = npc.rect.copy()
            
            if not npc_is_visible:
                # Off-camera optimization: ghost movement
                npc.update(dt, None)
            else:
                combined_walls: list[pygame.Rect] = list(walls) if walls else []
                for other in npcs:
                    if other is npc:
                        continue
                    # If NPC is seeking a target (e.g., exiting a room), 
                    # ignore other NPCs to avoid bottlenecks at narrow doors
                    if npc.target_pos is not None:
                        continue
                    combined_walls.append(other.rect.copy())
                
                npc.update(dt, combined_walls)
                
            # Classroom/Staircase restriction for generic wanderers
            if restricted_rooms and is_generic_wanderer(npc.id):
                room = floor.get_room_at(npc.rect.centerx, npc.rect.centery)
                if room and room.id in restricted_rooms:
                    # If in stairs, immediately eject to corridor center of that floor
                    if room.is_staircase or "stairs" in room.id:
                        npc.rect.center = (1600, 1000) if floor_id != 4 else (1600, 500)
                        npc.target_pos = None
                        npc.target_queue = []
                    else:
                        # If already inside another restricted room, push to corridor; otherwise block entry
                        if room.rect.collidepoint(previous_rect.center):
                            if room.id == "f2_classrooms":
                                npc.rect.centery = 1900
                            else:
                                npc.rect.centerx = 1080
                        else:
                            npc.rect.update(previous_rect)

            # Prevent NPCs from spawning/stuck in the empty/void spaces on Floor 2
            if floor_id == FLOOR_2F and is_generic_wanderer(npc.id):
                # Bottom-left void: x < 1050 and y > 1950
                # Bottom-right void: x > 2150 and y > 1720
                if (npc.rect.centerx < 1050 and npc.rect.centery > 1950) or \
                   (npc.rect.centerx > 2150 and npc.rect.centery > 1720):
                    npc.rect.center = (1600, 1000)
                    npc.target_pos = None
                    npc.target_queue = []

            if floor and floor.id == FLOOR_1F:
                room = floor.get_room_at(npc.rect.centerx, npc.rect.centery)
                gender = getattr(npc, "gender", "unspecified")
                if room:
                    if room.id == "f1_men_bath" and gender != "male":
                        npc.rect.update(previous_rect)
                    elif room.id == "f1_women_bath" and gender != "female":
                        npc.rect.update(previous_rect)

    def update_animations_on_floor(self, dt: float, floor_id: int):
        """Update only the animations of NPCs on a floor (used by co-op clients)."""
        for npc in self.get_npcs_on_floor(floor_id):
            npc._advance_animation(dt)

    def __repr__(self):
        return f"NPCManager({len(self.npcs)} npcs, {self.relationships})"
