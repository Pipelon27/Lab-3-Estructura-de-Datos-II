"""
src/player.py  —  Playable characters (Aiden & Lena)
=====================================================
Base ``Player`` class handles movement, collision, health, stamina,
XP / levelling, and skin selection.  ``Aiden`` and ``Lena`` are
concrete subclasses with character-specific abilities and skill trees.
"""

from __future__ import annotations

import os
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
    WHITE, BLACK, VT323_PATH)
from src.skill_tree import SkillTree, build_aiden_tree, build_lena_tree
from src.controller import get_controller, get_combined_movement


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
        self.current_floor = 1

        # Real-time Combat
        self.is_attacking = False
        self.attack_timer = 0.0
        self.attack_cooldown = 0.0
        self._hit_npcs = set()

        # XP / levelling
        self.xp            = 0
        self.level         = 1
        self.skill_points  = 0
        self.money         = 5           # Start with $5 as requested

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

        self.hurt_timer = 0.0
        self.knockout_time_elapsed = 0.0

        # Animation
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

        # Footstep sound
        self.step_sound = None
        self._is_stepping = False

        # Skill tree (set by subclass)
        self.skill_tree: SkillTree | None = None

    # ── movement & update ─────────────────────────────────────

    def update(self, keys, walls: list[pygame.Rect], dt: float, trail_decay: int = 1, speed_multiplier: float = 1.0):
        """Process movement from controller and keyboard, apply velocity, handle collisions."""
        if not hasattr(self, '_prev_health'):
            self._prev_health = self.health

        # Detect health reduction
        if self.health < self._prev_health:
            self.hurt_timer = 0.4
            self.knockout_time_elapsed = 0.0
            self._prev_health = self.health
        elif self.health > self._prev_health:
            self._prev_health = self.health

        # Update hurt timer
        if self.hurt_timer > 0:
            self.hurt_timer -= dt

        # Knocked out logic
        if self.health <= 0:
            self.state = "knockout"
            self.knockout_time_elapsed += dt
            if self.step_sound and self._is_stepping:
                self.step_sound.stop()
                self._is_stepping = False
            
            # Animate knockout (directional sitting pose)
            anim_key = f"knockout_{self.direction.value}"
            frames = self.animations.get(anim_key, [])
            if not frames:
                frames = self.animations.get("knockout", [])
            if frames:
                self.frame_index = min(len(frames) - 1, int(self.knockout_time_elapsed * 6.0))
                self.image = frames[self.frame_index]
            return

        # Hurt / hitstun state
        if self.hurt_timer > 0:
            self.state = "hurt"
            if self.step_sound and self._is_stepping:
                self.step_sound.stop()
                self._is_stepping = False
            
            # Animate hurt recoil
            anim_key = f"hurt_{self.direction.value}"
            frames = self.animations.get(anim_key, [])
            if frames:
                self.frame_index = int((0.4 - self.hurt_timer) * 10.0) % len(frames)
                self.image = frames[self.frame_index]
            return

        if self._dashing:
            self._update_dash(walls)
            return

        # Get combined movement from controller (left stick) and keyboard
        dx, dy = get_combined_movement(keys)

        # Update direction based on movement
        if abs(dy) > abs(dx):
            if dy < -0.1:
                self.direction = Direction.UP
            elif dy > 0.1:
                self.direction = Direction.DOWN
        else:
            if dx < -0.1:
                self.direction = Direction.LEFT
            elif dx > 0.1:
                self.direction = Direction.RIGHT

        # Check for dash trigger from controller (RT)
        controller = get_controller()
        dash_triggered = controller.is_dash_triggered()

        # Sprint (keyboard dash keys OR controller RT)
        sprinting = (keys[KEY_DASH] or keys[KEY_DASH_ALT] or keys[KEY_DASH_ALT2] or
                    controller.rt_value > 0.3) and self.stamina > 0 and (dx != 0 or dy != 0)
        spd = (self.sprint_speed if sprinting else self.speed) * speed_multiplier
        if sprinting:
            self.stamina = max(0, self.stamina - STAMINA_SPRINT_COST)

        # Apply velocity and collide
        self.rect.x += int(dx * spd)
        self._collide(walls, dx, 0)
        self.rect.y += int(dy * spd)
        self._collide(walls, 0, dy)

        # Update animation state
        if dx == 0 and dy == 0:
            self.state = "idle"
            if self.step_sound and self._is_stepping:
                self.step_sound.stop()
                self._is_stepping = False
        else:
            self.state = "walk"
            if self.step_sound is None:
                try:
                    if pygame.mixer.get_init():
                        self.step_sound = pygame.mixer.Sound("sound/pasos.mp3")
                        self.step_sound.set_volume(0.85)
                except Exception:
                    pass
            if self.step_sound and not self._is_stepping:
                self.step_sound.play(-1)
                self._is_stepping = True

        if getattr(self, "is_attacking", False):
            self.state = "attack"

        # Update animation frame
        anim_key = f"{self.state}_{self.direction.value}"
        frames = self.animations.get(anim_key, [])
        if frames:
            if self.state == "attack":
                # Advance attack animation based on attack_timer (active for 0.2s, 6 frames -> ~30fps)
                self.frame_index = int((0.2 - getattr(self, "attack_timer", 0.0)) * 30.0) % len(frames)
                self.image = frames[self.frame_index]
            else:
                # Animation speed: 12.0 frames/sec for walking, 6.0 frames/sec for idle
                anim_speed = 12.0 if self.state == "walk" else 6.0
                if sprinting:
                    anim_speed *= 1.5
                
                self.animation_timer += dt * anim_speed
                if self.animation_timer >= len(frames):
                    self.animation_timer = 0.0
                self.frame_index = int(self.animation_timer) % len(frames)
                self.image = frames[self.frame_index]

        # Stamina regen
        if not sprinting:
            self.stamina = min(self.max_stamina,
                               self.stamina + STAMINA_REGEN_RATE)

        # Real-time combat update
        if getattr(self, "attack_timer", 0) > 0:
            self.attack_timer -= dt
            if self.attack_timer <= 0:
                self.is_attacking = False
        if getattr(self, "attack_cooldown", 0) > 0:
            self.attack_cooldown -= dt

        # Update dash trail
        new_trail = []
        for r, t in self._dash_trail:
            if t > 0:
                new_trail.append((r, t - trail_decay))
        self._dash_trail = new_trail

    def stop_audio(self):
        """Immediately cut any active footstep audio."""
        if self.step_sound and self._is_stepping:
            self.step_sound.stop()
            self._is_stepping = False

    def start_dash(self):
        """Initiate a quick dash in the current direction."""
        if self.stamina < DASH_STAMINA_COST or self._dashing:
            return
        
        # Controller rumble feedback
        controller = get_controller()
        if controller.connected:
            controller.rumble(0.4, 0.6, 150)  # Light rumble on dash
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

    def start_attack(self):
        """Initiate an attack if enough stamina and off cooldown."""
        if self.attack_cooldown <= 0 and self.stamina >= 5:
            # Controller rumble feedback
            controller = get_controller()
            if controller.connected:
                controller.rumble(0.2, 0.4, 100)
            self.stamina -= 5
            self.is_attacking = True
            self.attack_timer = 0.2  # 0.2s active hitbox
            self.attack_cooldown = 1.0
            self._hit_npcs.clear()

    def get_attack_hitbox(self) -> pygame.Rect | None:
        if not self.is_attacking:
            return None
        from settings import ATTACK_RANGE
        hr = pygame.Rect(0, 0, ATTACK_RANGE, ATTACK_RANGE)
        if self.direction == Direction.UP:
            hr.midbottom = self.rect.midtop
        elif self.direction == Direction.DOWN:
            hr.midtop = self.rect.midbottom
        elif self.direction == Direction.LEFT:
            hr.midright = self.rect.midleft
        elif self.direction == Direction.RIGHT:
            hr.midleft = self.rect.midright
        return hr

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

    def update_remote(self, data: dict, dt: float, trail_decay: int = 1):
        """Update remote player state from network data."""
        self._dashing = data.get("dashing", False)
        
        # Save previous pos for movement detection
        old_x, old_y = self.rect.x, self.rect.y

        # Position with simple interpolation to smooth movement
        target_x = data.get("x", self.rect.x)
        target_y = data.get("y", self.rect.y)
        
        # LERP (Linear Interpolation) for smoother movement
        # 0.4 is a balance between responsiveness and smoothness
        # Only LERP if we are far enough to avoid integer truncation issues
        dx = (target_x - self.rect.x)
        dy = (target_y - self.rect.y)
        
        if abs(dx) < 2:
            self.rect.x = target_x
        else:
            self.rect.x += int(dx * 0.4)
            
        if abs(dy) < 2:
            self.rect.y = target_y
        else:
            self.rect.y += int(dy * 0.4)

        # Movement detection
        # We use the state sent from the network if available, otherwise infer it
        network_state = data.get("state")
        if network_state:
            self.state = network_state
        else:
            # Fallback movement detection
            is_moving = abs(target_x - old_x) > 2.0 or abs(target_y - old_y) > 2.0
            self.state = "walk" if is_moving else "idle"

        direction_val = data.get("direction")
        if direction_val is not None:
            from settings import Direction
            try:
                self.direction = Direction(direction_val)
            except ValueError:
                pass

        # Update animation frame (sync with local player logic)
        anim_key = f"{self.state}_{self.direction.value}"
        frames = self.animations.get(anim_key, [])
        if frames:
            anim_speed = 12.0 if self.state == "walk" else 6.0
            self.animation_timer += dt * anim_speed
            if self.animation_timer >= len(frames):
                self.animation_timer = 0.0
            self.frame_index = int(self.animation_timer) % len(frames)
            self.image = frames[self.frame_index]

        # Dash trail for remote player
        if self._dashing:
            self._dash_trail.append((self.rect.copy(), 15))

        # Trail decay (needed for remote players since update() isn't called)
        new_trail = []
        for r, t in self._dash_trail:
            if t > 0:
                new_trail.append((r, t - trail_decay))
        self._dash_trail = new_trail

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
        """Draw the player (sprite or fallback rectangle)."""
        # Draw dash trail
        for r, t in self._dash_trail:
            alpha = max(0, min(255, int(255 * (t / 15.0) * 0.4)))
            trail_surf = pygame.Surface(r.size, pygame.SRCALPHA)
            trail_surf.fill((*self.color[:3], alpha))
            screen.blit(trail_surf, camera.apply_rect(r))

        draw_rect = camera.apply(self)

        if self.image:
            # Align bottom-center of the sprite with bottom-center of the hitbox
            sprite_rect = self.image.get_rect(midbottom=draw_rect.midbottom)
            if getattr(self, "hurt_timer", 0) > 0 and int(self.hurt_timer * 20) % 2 == 0:
                # Premium red silhouette/flash using mask
                mask = pygame.mask.from_surface(self.image)
                mask_surf = mask.to_surface(setcolor=(255, 50, 50, 255), unsetcolor=(0, 0, 0, 0))
                screen.blit(self.image, sprite_rect)
                mask_surf.set_alpha(150)
                screen.blit(mask_surf, sprite_rect)
            else:
                screen.blit(self.image, sprite_rect)
            
            # Optional debug hitbox (can be removed later)
            # pygame.draw.rect(screen, (255, 0, 0), draw_rect, 1)
        else:
            # Fallback Body
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
        font = pygame.font.Font(VT323_PATH, 14)
        name_surf = font.render(self.character.value.title(), True, WHITE)
        screen.blit(name_surf,
                    name_surf.get_rect(center=(draw_rect.centerx, draw_rect.top - 10)))

        # Draw attack hitbox if attacking
        if self.is_attacking:
            hitbox = self.get_attack_hitbox()
            if hitbox:
                hr_draw = camera.apply_rect(hitbox)
                pygame.draw.rect(screen, (255, 50, 50), hr_draw, 2, border_radius=4)

    # ── serialisation (for network) ───────────────────────────

    def to_dict(self) -> dict:
        return {
            "character": self.character.value,
            "x": self.rect.x,  "y": self.rect.y,
            "direction": self.direction.value,
            "state": self.state,
            "health": self.health, "stamina": self.stamina,
            "xp": self.xp, "level": self.level,
            "dashing": self._dashing,
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
        self.hack_time_bonus = 2         # matched with Lena's base
        self.skill_tree    = build_aiden_tree()
        self._load_sprites()

    def _load_sprites(self):
        """Extract idle, walk, and combat frames from the spritesheet."""
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, "assets", "Characters BEHIND THE SMILE", "PROTAGONISTS", "Aiden Parker.png")
        if not os.path.exists(path):
            print(f"Warning: Aiden spritesheet not found at {path}")
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
        self.attack_damage = 12          # matched with Aiden's base
        self.sprint_speed  = PLAYER_SPRINT_SPEED + 1  # matched with Aiden's base
        self.hack_time_bonus = 2         # starts with small bonus
        self.skill_tree      = build_lena_tree()
        self._load_sprites()

    def _load_sprites(self):
        """Extract idle, walk, and combat frames from the spritesheet."""
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, "assets", "Characters BEHIND THE SMILE", "PROTAGONISTS", "Lena Parker.png")
        if not os.path.exists(path):
            print(f"Warning: Lena spritesheet not found at {path}")
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
