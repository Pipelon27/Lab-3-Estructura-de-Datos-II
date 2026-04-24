"""
src/player.py  —  Playable characters (Aiden & Lena)
=====================================================
Base ``Player`` class handles movement, collision, health, stamina,
XP / levelling, and skin selection.  ``Aiden`` and ``Lena`` are
concrete subclasses with character-specific abilities and skill trees.
"""

from __future__ import annotations

import pygame
from settings import (
    PLAYER_SIZE, PLAYER_SPEED, PLAYER_SPRINT_SPEED,
    PLAYER_MAX_HEALTH, PLAYER_MAX_STAMINA,
    STAMINA_REGEN_RATE, STAMINA_SPRINT_COST,
    DASH_STAMINA_COST, DASH_SPEED, DASH_DURATION,
    AIDEN_COLOR, AIDEN_OUTLINE, LENA_COLOR, LENA_OUTLINE,
    SCREEN_WIDTH, SCREEN_HEIGHT,
    XP_PER_LEVEL, SKILL_POINT_PER_LEVEL,
    Character, Direction,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_DASH, KEY_DASH_ALT, KEY_DASH_ALT2,
    WHITE, BLACK,
)
from src.skill_tree import SkillTree, build_aiden_tree, build_lena_tree


# ══════════════════════════════════════════════════════════════
#  BASE PLAYER
# ══════════════════════════════════════════════════════════════

class Player:
    """Abstract base for a playable character.

    Handles:
    * WASD movement with wall collision
    * Sprint (hold SHIFT) consuming stamina
    * Dash (tap SHIFT) with brief invulnerability
    * Health, stamina, XP, levelling
    * Placeholder rectangle rendering
    * Skin index (for later sprite-sheet swapping)

    Subclasses set ``character``, ``color``, ``outline``, and
    attach a character-specific ``SkillTree``.
    """

    def __init__(self, x: int, y: int, character: Character,
                 color: tuple, outline: tuple):
        # Identity
        self.character = character
        self.color     = color
        self.outline   = outline
        self.skin_index = 0              # selectable skin variant

        # Spatial
        self.rect = pygame.Rect(x - PLAYER_SIZE // 2,
                                y - PLAYER_SIZE // 2,
                                PLAYER_SIZE, PLAYER_SIZE)
        self.direction = Direction.DOWN
        self.speed     = PLAYER_SPEED
        self.sprint_speed = PLAYER_SPRINT_SPEED

        # Dash state
        self._dashing       = False
        self._dash_timer    = 0
        self._dash_dx       = 0
        self._dash_dy       = 0
        self._dash_trail    = []  # List of (Rect, timer)

        # Stats
        self.health      = PLAYER_MAX_HEALTH
        self.max_health  = PLAYER_MAX_HEALTH
        self.stamina     = PLAYER_MAX_STAMINA
        self.max_stamina = PLAYER_MAX_STAMINA

        # XP / levelling
        self.xp            = 0
        self.level         = 1
        self.skill_points  = 0

        # Combat extras (overridden by Aiden)
        self.attack_damage  = 10
        self.combo_speed    = 1
        self.knockback_force = 0
        self.dodge_distance  = 0

        # Hacking extras (overridden by Lena)
        self.hack_time_bonus          = 0
        self.hack_difficulty_reduction = 0
        self.camera_range             = 0
        self.clue_radius              = 0
        self.puzzle_hints             = 0
        self.xp_multiplier            = 0
        self.trade_bonus              = 0
        self.persuasion_level         = 0
        self.trust_reveal_threshold   = 50

        # Popularity extras (Aiden)
        self.rep_athletes_bonus = 0
        self.crowd_chance       = 0
        self.respect_aura       = 0

        # Skill tree (set by subclass)
        self.skill_tree: SkillTree | None = None

    # ── movement & update ─────────────────────────────────────

    def update(self, keys, walls: list[pygame.Rect], dt: float):
        """Process movement keys, apply velocity, handle collisions."""
        if self._dashing:
            self._update_dash(walls)
            return

        dx, dy = 0, 0
        if keys[KEY_UP]:
            dy = -1; self.direction = Direction.UP
        if keys[KEY_DOWN]:
            dy = 1;  self.direction = Direction.DOWN
        if keys[KEY_LEFT]:
            dx = -1; self.direction = Direction.LEFT
        if keys[KEY_RIGHT]:
            dx = 1;  self.direction = Direction.RIGHT

        # Normalise diagonal movement
        if dx != 0 and dy != 0:
            dx *= 0.7071
            dy *= 0.7071

        # Sprint
        sprinting = (keys[KEY_DASH] or keys[KEY_DASH_ALT] or keys[KEY_DASH_ALT2]) and self.stamina > 0 and (dx != 0 or dy != 0)
        spd = self.sprint_speed if sprinting else self.speed
        if sprinting:
            self.stamina = max(0, self.stamina - STAMINA_SPRINT_COST)

        # Apply velocity and collide
        self.rect.x += int(dx * spd)
        self._collide(walls, dx, 0)
        self.rect.y += int(dy * spd)
        self._collide(walls, 0, dy)

        # Stamina regen
        if not sprinting:
            self.stamina = min(self.max_stamina,
                               self.stamina + STAMINA_REGEN_RATE)

        # Update dash trail
        new_trail = []
        for r, t in self._dash_trail:
            if t > 0:
                new_trail.append((r, t - 1))
        self._dash_trail = new_trail

    def start_dash(self):
        """Initiate a quick dash in the current direction."""
        if self.stamina < DASH_STAMINA_COST or self._dashing:
            return
        self.stamina -= DASH_STAMINA_COST
        self._dashing    = True
        self._dash_timer = DASH_DURATION

        dx, dy = 0, 0
        if self.direction == Direction.UP:    dy = -1
        elif self.direction == Direction.DOWN:  dy = 1
        elif self.direction == Direction.LEFT:  dx = -1
        elif self.direction == Direction.RIGHT: dx = 1
            
        self._dash_dx = dx * DASH_SPEED
        self._dash_dy = dy * DASH_SPEED

    def _update_dash(self, walls):
        self._dash_trail.append((self.rect.copy(), 15))
        self.rect.x += int(self._dash_dx)
        self._collide(walls, self._dash_dx, 0)
        self.rect.y += int(self._dash_dy)
        self._collide(walls, 0, self._dash_dy)
        self._dash_timer -= 1
        if self._dash_timer <= 0:
            self._dashing = False

    def _collide(self, walls: list[pygame.Rect], dx: float, dy: float):
        """Push the player out of any wall it overlaps."""
        for wall in walls:
            if self.rect.colliderect(wall):
                if dx > 0:
                    self.rect.right = wall.left
                elif dx < 0:
                    self.rect.left = wall.right
                if dy > 0:
                    self.rect.bottom = wall.top
                elif dy < 0:
                    self.rect.top = wall.bottom

    # ── XP & levelling ────────────────────────────────────────

    def gain_xp(self, amount: int):
        """Add XP, levelling up when the threshold is reached."""
        multiplier = 1.0 + self.xp_multiplier / 100.0
        self.xp += int(amount * multiplier)
        while self.xp >= XP_PER_LEVEL:
            self.xp -= XP_PER_LEVEL
            self.level += 1
            self.skill_points += SKILL_POINT_PER_LEVEL

    # ── damage ────────────────────────────────────────────────

    def take_damage(self, amount: int):
        """Reduce health (clamped to 0)."""
        self.health = max(0, self.health - amount)

    def heal(self, amount: int):
        """Restore health (clamped to max)."""
        self.health = min(self.max_health, self.health + amount)

    def is_alive(self) -> bool:
        return self.health > 0

    # ── rendering (placeholder) ───────────────────────────────

    def draw(self, screen: pygame.Surface, camera):
        """Draw the player as a coloured rectangle with a direction arrow."""
        # Draw dash trail
        for r, t in self._dash_trail:
            alpha = int(255 * (t / 15.0) * 0.4)
            trail_surf = pygame.Surface(r.size, pygame.SRCALPHA)
            trail_surf.fill((*self.color[:3], alpha))
            screen.blit(trail_surf, camera.apply_rect(r))

        draw_rect = camera.apply(self)

        # Body
        pygame.draw.rect(screen, self.color, draw_rect, border_radius=6)
        pygame.draw.rect(screen, self.outline, draw_rect, 2, border_radius=6)

        # Direction indicator (small triangle)
        cx, cy = draw_rect.center
        sz = 6
        if self.direction == Direction.UP:
            pts = [(cx, cy - sz - 4), (cx - sz, cy - 2), (cx + sz, cy - 2)]
        elif self.direction == Direction.DOWN:
            pts = [(cx, cy + sz + 4), (cx - sz, cy + 2), (cx + sz, cy + 2)]
        elif self.direction == Direction.LEFT:
            pts = [(cx - sz - 4, cy), (cx - 2, cy - sz), (cx - 2, cy + sz)]
        else:
            pts = [(cx + sz + 4, cy), (cx + 2, cy - sz), (cx + 2, cy + sz)]
        pygame.draw.polygon(screen, WHITE, pts)

        # Name tag
        font = pygame.font.SysFont("arial", 14)
        name_surf = font.render(self.character.value.title(), True, WHITE)
        screen.blit(name_surf,
                    name_surf.get_rect(center=(cx, draw_rect.top - 10)))

    # ── serialisation (for network) ───────────────────────────

    def to_dict(self) -> dict:
        return {
            "character": self.character.value,
            "x": self.rect.x,  "y": self.rect.y,
            "direction": self.direction.value,
            "health": self.health, "stamina": self.stamina,
            "xp": self.xp, "level": self.level,
        }

    def __repr__(self):
        return (f"Player({self.character.value}, "
                f"hp={self.health}/{self.max_health}, "
                f"lvl={self.level})")


# ══════════════════════════════════════════════════════════════
#  AIDEN  —  combat-focused
# ══════════════════════════════════════════════════════════════

class Aiden(Player):
    """Aiden Parker — athletic, combat-oriented brother.

    Special access to sports-related content.
    Skill tree branches: Strength, Athleticism, Popularity.
    """

    def __init__(self, x: int, y: int):
        super().__init__(x, y, Character.AIDEN, AIDEN_COLOR, AIDEN_OUTLINE)
        self.attack_damage = 12          # slightly higher base
        self.sprint_speed  = PLAYER_SPRINT_SPEED + 1
        self.skill_tree    = build_aiden_tree()


# ══════════════════════════════════════════════════════════════
#  LENA  —  hacking-focused
# ══════════════════════════════════════════════════════════════

class Lena(Player):
    """Lena Parker — intelligent, hacker sister.

    Special access to tech-related content.
    Skill tree branches: Hacking, Intelligence, Social Engineering.
    """

    def __init__(self, x: int, y: int):
        super().__init__(x, y, Character.LENA, LENA_COLOR, LENA_OUTLINE)
        self.hack_time_bonus = 2         # starts with small bonus
        self.skill_tree      = build_lena_tree()
