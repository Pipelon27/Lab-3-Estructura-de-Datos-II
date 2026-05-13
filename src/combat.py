"""
src/combat.py  —  Aiden's combat system
=========================================
State-machine–based melee combat:
  IDLE → ATTACKING → COMBO_WINDOW → COMBO → IDLE
  IDLE → BLOCKING
  IDLE → DASHING

Attacks use rectangular hit-boxes.  Stamina limits how often the
player can swing.  Combos reward chaining hits within a timing window.
"""

from __future__ import annotations

import pygame
from enum import Enum, auto
from settings import (
    LIGHT_ATTACK_DAMAGE, HEAVY_ATTACK_DAMAGE, COMBO_DAMAGE,
    LIGHT_ATTACK_STAMINA, HEAVY_ATTACK_STAMINA, COMBO_STAMINA,
    BLOCK_DAMAGE_REDUCTION, ATTACK_RANGE, ATTACK_COOLDOWN, COMBO_WINDOW,
    PLAYER_SIZE,
    HEALTH_RED, HEALTH_BG, WHITE, BLACK, UI_ACCENT, UI_TEXT, UI_TEXT_DIM,
    NOTIF_SUCCESS, NOTIF_ERROR,
    SCREEN_WIDTH, SCREEN_HEIGHT,
    Direction,
    KEY_LIGHT_ATTACK, KEY_HEAVY_ATTACK, KEY_BLOCK, KEY_DASH, KEY_DASH_ALT, KEY_DASH_ALT2, VT323_PATH)


class CombatState(Enum):
    IDLE         = auto()
    LIGHT_ATTACK = auto()
    HEAVY_ATTACK = auto()
    COMBO_WINDOW = auto()      # brief window to chain
    COMBO_ATTACK = auto()
    BLOCKING     = auto()
    DASHING      = auto()
    FINISHED     = auto()


class CombatSystem:
    """Manages one combat encounter between the player and an NPC.

    Public API
    ----------
    ``start_combat(player, npc)``  – begin encounter
    ``handle_input(event, player)`` – process key during combat
    ``update(dt)``                  – tick combat logic
    ``draw(screen, camera)``        – overlay combat HUD
    """

    def __init__(self):
        self.active    = False
        self.state     = CombatState.IDLE
        self.player    = None
        self.target    = None
        self.timer     = 0          # generic frame counter

        # Target (NPC) combat stats
        self.target_health     = 0
        self.target_max_health = 0
        self.target_damage     = 5
        self.hit_combo_count   = 0

        self._hit_flash  = 0       # visual feedback
        self._result     = None    # "win" / "lose" / "flee"

    # ── start / end ───────────────────────────────────────────

    def start_combat(self, player, npc):
        """Initialise a combat encounter against *npc*."""
        self.active    = True
        self.state     = CombatState.IDLE
        self.player    = player
        self.target    = npc
        self.timer     = 0
        self.hit_combo_count = 0
        self._result   = None
        self._hit_flash = 0

        # Give the NPC some health based on its type
        self.target_max_health = 60
        self.target_health     = self.target_max_health
        self.target_damage     = 8

    def _end_combat(self, result: str):
        self.state   = CombatState.FINISHED
        self._result = result
        self.active  = False

    # ── input ─────────────────────────────────────────────────

    def handle_input(self, event: pygame.event.Event, player):
        """Handle a KEYDOWN during combat."""
        if event.type != pygame.KEYDOWN or not self.active:
            return

        if event.key == pygame.K_ESCAPE:
            self._end_combat("flee")
            return

        if self.state == CombatState.IDLE:
            if event.key == KEY_LIGHT_ATTACK:
                if player.stamina >= LIGHT_ATTACK_STAMINA:
                    player.stamina -= LIGHT_ATTACK_STAMINA
                    self.state = CombatState.LIGHT_ATTACK
                    self.timer = ATTACK_COOLDOWN
            elif event.key == KEY_HEAVY_ATTACK:
                if player.stamina >= HEAVY_ATTACK_STAMINA:
                    player.stamina -= HEAVY_ATTACK_STAMINA
                    self.state = CombatState.HEAVY_ATTACK
                    self.timer = ATTACK_COOLDOWN + 5
            elif event.key == KEY_BLOCK:
                self.state = CombatState.BLOCKING
            elif event.key in (KEY_DASH, KEY_DASH_ALT, KEY_DASH_ALT2):
                player.start_dash()
                self.state = CombatState.DASHING
                self.timer = 10

        elif self.state == CombatState.COMBO_WINDOW:
            if event.key == KEY_LIGHT_ATTACK:
                if player.stamina >= COMBO_STAMINA:
                    player.stamina -= COMBO_STAMINA
                    self.state = CombatState.COMBO_ATTACK
                    self.timer = ATTACK_COOLDOWN
                    self.hit_combo_count += 1

        elif self.state == CombatState.BLOCKING:
            # Release block on any other key
            if event.key != KEY_BLOCK:
                self.state = CombatState.IDLE

    # ── update ────────────────────────────────────────────────

    def update(self, dt: float) -> str | None:
        """Tick combat logic.  Returns ``"win"``/``"lose"``/``"flee"``
        when combat ends, else ``None``."""
        if not self.active:
            return self._result

        self._hit_flash = max(0, self._hit_flash - 1)

        # State machine
        if self.state in (CombatState.LIGHT_ATTACK, CombatState.HEAVY_ATTACK,
                          CombatState.COMBO_ATTACK):
            self.timer -= 1
            if self.timer <= 0:
                self._apply_attack()
                if self.target_health <= 0:
                    self._end_combat("win")
                    return self._result
                self.state = CombatState.COMBO_WINDOW
                self.timer = COMBO_WINDOW

        elif self.state == CombatState.COMBO_WINDOW:
            self.timer -= 1
            if self.timer <= 0:
                self.hit_combo_count = 0
                self.state = CombatState.IDLE
                self._npc_counter_attack()

        elif self.state == CombatState.BLOCKING:
            # NPC tries to attack while player blocks
            self.timer += 1
            if self.timer % 40 == 0:
                dmg = int(self.target_damage * (1 - BLOCK_DAMAGE_REDUCTION))
                self.player.take_damage(dmg)

        elif self.state == CombatState.DASHING:
            self.timer -= 1
            if self.timer <= 0:
                self.state = CombatState.IDLE

        elif self.state == CombatState.IDLE:
            # NPC attacks on a slow cycle
            self.timer += 1
            if self.timer % 60 == 0:
                self._npc_counter_attack()

        # Check lose condition
        if self.player and not self.player.is_alive():
            self._end_combat("lose")
            return self._result

        # Stamina regen during combat (slower)
        if self.player:
            self.player.stamina = min(
                self.player.max_stamina,
                self.player.stamina + 0.2,
            )

        return None

    def _apply_attack(self):
        """Deal damage to the target based on current attack state."""
        if self.state == CombatState.LIGHT_ATTACK:
            dmg = LIGHT_ATTACK_DAMAGE + self.player.attack_damage
        elif self.state == CombatState.HEAVY_ATTACK:
            dmg = HEAVY_ATTACK_DAMAGE + self.player.attack_damage
        elif self.state == CombatState.COMBO_ATTACK:
            dmg = COMBO_DAMAGE + self.player.attack_damage + self.hit_combo_count * 3
        else:
            dmg = 0

        self.target_health = max(0, self.target_health - dmg)
        self._hit_flash = 8

    def _npc_counter_attack(self):
        """The NPC attacks the player."""
        if self.player and self.state != CombatState.BLOCKING:
            self.player.take_damage(self.target_damage)
            self._hit_flash = 4

    # ── drawing ───────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, camera):
        """Draw the combat overlay HUD."""
        if not self.active and self._result is None:
            return

        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 80))
        screen.blit(overlay, (0, 0))

        font      = pygame.font.Font(VT323_PATH, 28)
        font_sm   = pygame.font.Font(VT323_PATH, 20)
        font_hint = pygame.font.Font(VT323_PATH, 16)

        # ── Header ──
        header = font.render("⚔  COMBAT  ⚔", True, HEALTH_RED)
        screen.blit(header, header.get_rect(center=(SCREEN_WIDTH // 2, 40)))

        # ── Player health bar ──
        bar_w, bar_h = 250, 20
        px, py = 60, 80
        self._draw_bar(screen, px, py, bar_w, bar_h,
                       self.player.health, self.player.max_health,
                       HEALTH_RED, HEALTH_BG)
        screen.blit(font_sm.render(
            f"{self.player.character.value.title()}  HP {self.player.health}/{self.player.max_health}",
            True, WHITE), (px, py - 22))

        # ── Target health bar ──
        tx, ty = SCREEN_WIDTH - 310, 80
        self._draw_bar(screen, tx, ty, bar_w, bar_h,
                       self.target_health, self.target_max_health,
                       (230, 120, 50), HEALTH_BG)
        target_name = self.target.name if self.target else "Enemy"
        screen.blit(font_sm.render(
            f"{target_name}  HP {self.target_health}/{self.target_max_health}",
            True, WHITE), (tx, ty - 22))

        # ── State label ──
        state_labels = {
            CombatState.IDLE:         "Ready",
            CombatState.LIGHT_ATTACK: "Light Attack!",
            CombatState.HEAVY_ATTACK: "Heavy Attack!",
            CombatState.COMBO_WINDOW: f"COMBO x{self.hit_combo_count}! Press J!",
            CombatState.COMBO_ATTACK: "COMBO HIT!",
            CombatState.BLOCKING:     "Blocking…",
            CombatState.DASHING:      "Dash!",
        }
        lbl = state_labels.get(self.state, "")
        colour = NOTIF_SUCCESS if "COMBO" in lbl else UI_ACCENT
        screen.blit(font.render(lbl, True, colour),
                    (SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 - 30))

        # ── Hit flash ──
        if self._hit_flash > 0:
            flash = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            flash.fill((255, 80, 80, int(40 * self._hit_flash / 8)))
            screen.blit(flash, (0, 0))

        # ── Controls ──
        screen.blit(font_hint.render(
            "J Light  |  U Heavy  |  L Block  |  SHIFT Dash  |  ESC Flee",
            True, UI_TEXT_DIM),
            (SCREEN_WIDTH // 2 - 200, SCREEN_HEIGHT - 40))

    @staticmethod
    def _draw_bar(screen, x, y, w, h, current, maximum, fg, bg):
        pygame.draw.rect(screen, bg, (x, y, w, h), border_radius=4)
        fill = int(w * max(0, current) / max(1, maximum))
        pygame.draw.rect(screen, fg, (x, y, fill, h), border_radius=4)
        pygame.draw.rect(screen, WHITE, (x, y, w, h), 1, border_radius=4)
