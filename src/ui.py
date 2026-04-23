"""
src/ui.py  —  HUD, menus, help screen, notifications
======================================================
Draws all overlay / full-screen UI elements using Pygame
primitives (no external assets needed).

Sections
--------
* HUD           – health, stamina, XP bars; zone name; day info
* Pause menu    – resume / quit options
* Help screen   – complete control reference (H key)
* Inventory     – delegates to Inventory.draw()
* Skill tree    – delegates to SkillTree.draw()
* Game Over     – ending screen
* Notifications – timed pop-up messages with fade
* Minimap       – tiny representation of the zone graph
"""

from __future__ import annotations

import math
import pygame
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    UI_BG, UI_PANEL, UI_BORDER, UI_ACCENT,
    UI_TEXT, UI_TEXT_DIM, WHITE, BLACK,
    HEALTH_RED, HEALTH_BG, STAMINA_YELLOW, STAMINA_BG,
    XP_BLUE, XP_BG,
    NOTIF_SUCCESS, NOTIF_WARNING, NOTIF_ERROR, NOTIF_INFO,
    ZONE_NAMES, ZONE_CONNECTIONS,
    FLOOR_NAMES,
    Character, Ending,
    MOTIVATIONAL_MESSAGES,
)


# ══════════════════════════════════════════════════════════════
#  NOTIFICATION SYSTEM
# ══════════════════════════════════════════════════════════════

class Notification:
    """A single timed notification."""
    def __init__(self, text: str, colour: tuple, duration: float = 3.0):
        self.text     = text
        self.colour   = colour
        self.duration = duration
        self.timer    = duration        # counts down

    @property
    def alpha(self) -> int:
        """Fade-out alpha (255 → 0)."""
        if self.timer < 0.5:
            return int(255 * self.timer / 0.5)
        return 255

    @property
    def expired(self) -> bool:
        return self.timer <= 0


# ══════════════════════════════════════════════════════════════
#  UI  (main class)
# ══════════════════════════════════════════════════════════════

class UI:
    """Centralised UI renderer.

    The ``Game`` instance calls individual ``draw_*`` methods
    depending on the current ``GameState``.
    """

    MAX_NOTIFS = 5

    def __init__(self, screen: pygame.Surface):
        self.screen  = screen
        self._notifs: list[Notification] = []

        # Fonts (created once)
        self.font_hud_sm  = pygame.font.SysFont("arial", 16)
        self.font_hud_md  = pygame.font.SysFont("arial", 20)
        self.font_hud_lg  = pygame.font.SysFont("arial", 26, bold=True)
        self.font_title   = pygame.font.SysFont("arial", 48, bold=True)
        self.font_menu    = pygame.font.SysFont("arial", 30)
        self.font_hint    = pygame.font.SysFont("arial", 16)

    # ── notifications ─────────────────────────────────────────

    def show_notification(self, text: str, colour: tuple = NOTIF_INFO,
                          duration: float = 3.0):
        """Queue a notification (newest at bottom)."""
        self._notifs.append(Notification(text, colour, duration))
        if len(self._notifs) > self.MAX_NOTIFS:
            self._notifs.pop(0)

    def update(self, dt: float):
        """Tick notification timers."""
        for n in self._notifs:
            n.timer -= dt
        self._notifs = [n for n in self._notifs if not n.expired]

    def draw_notifications(self, screen: pygame.Surface):
        """Render active notifications (top-right corner)."""
        x = SCREEN_WIDTH - 20
        y = 60
        for notif in self._notifs:
            surf = self.font_hud_md.render(notif.text, True, notif.colour)
            surf.set_alpha(notif.alpha)
            r = surf.get_rect(topright=(x, y))
            # background
            bg = r.inflate(16, 6)
            bg_surf = pygame.Surface((bg.width, bg.height), pygame.SRCALPHA)
            bg_surf.fill((*UI_PANEL, min(200, notif.alpha)))
            screen.blit(bg_surf, bg)
            screen.blit(surf, r)
            y += 30

    # ── HUD ───────────────────────────────────────────────────

    def draw_hud(self, screen: pygame.Surface, player, current_phase,
                 day_number: int, floor=None, room=None):
        """Draw the in-game heads-up display."""
        # ── health bar ──
        self._bar(screen, 16, 16, 180, 14,
                  player.health, player.max_health,
                  HEALTH_RED, HEALTH_BG, "HP")

        # ── stamina bar ──
        self._bar(screen, 16, 36, 180, 14,
                  player.stamina, player.max_stamina,
                  STAMINA_YELLOW, STAMINA_BG, "SP")

        # ── XP bar ──
        from settings import XP_PER_LEVEL
        self._bar(screen, 16, 56, 180, 10,
                  player.xp, XP_PER_LEVEL,
                  XP_BLUE, XP_BG, f"Lv{player.level}")

        # ── day / phase ──
        phase_str = current_phase.value.replace("_", " ").title()
        day_text = f"Day {day_number}  —  {phase_str}"
        screen.blit(self.font_hud_sm.render(day_text, True, UI_TEXT_DIM),
                    (16, 76))

        # ── location (top-right): floor name + room name ──
        floor_name = floor.name if floor else "Unknown"
        room_name = room.name if room else ""
        loc_text = f"{floor_name}"
        if room_name:
            loc_text += f"  —  {room_name}"
        zn = self.font_hud_lg.render(loc_text, True, UI_ACCENT)
        screen.blit(zn, zn.get_rect(topright=(SCREEN_WIDTH - 16, 12)))

        # ── circular minimap (bottom-right) ──
        self._draw_minimap_circle(screen, floor, player)

    def _bar(self, screen, x, y, w, h, cur, mx, fg, bg, label=""):
        """Utility: draw a filled bar with a label."""
        pygame.draw.rect(screen, bg, (x, y, w, h), border_radius=3)
        fill_w = int(w * max(0, cur) / max(1, mx))
        pygame.draw.rect(screen, fg, (x, y, fill_w, h), border_radius=3)
        pygame.draw.rect(screen, WHITE, (x, y, w, h), 1, border_radius=3)
        if label:
            lbl = self.font_hud_sm.render(f"{label} {int(cur)}/{int(mx)}", True, WHITE)
            screen.blit(lbl, (x + 4, y - 1))

    def _draw_minimap_circle(self, screen, floor, player):
        """Circular minimap in bottom-right that follows the player."""
        if not floor:
            return

        radius = 70
        mm_cx = SCREEN_WIDTH - radius - 14
        mm_cy = SCREEN_HEIGHT - radius - 14
        diameter = radius * 2

        # Scale to fit the larger dimension within ~5x the minimap
        scale = min(diameter / floor.width, diameter / floor.height) * 2.8

        # Player position in minimap coords (centered)
        px = player.rect.centerx * scale
        py = player.rect.centery * scale
        # Offset so player is at the center of the minimap
        ox = px - radius
        oy = py - radius

        # Create minimap surface
        mm_surf = pygame.Surface((diameter, diameter), pygame.SRCALPHA)

        # Floor background
        fx = -ox
        fy = -oy
        fw = int(floor.width * scale)
        fh = int(floor.height * scale)
        pygame.draw.rect(mm_surf, (*floor.bg_color, 200),
                         (int(fx), int(fy), fw, fh))

        # Room fills
        for room in floor.rooms.values():
            rx = room.rect.x * scale - ox
            ry = room.rect.y * scale - oy
            rw = max(1, int(room.rect.width * scale))
            rh = max(1, int(room.rect.height * scale))
            col = (*room.color, 180)
            pygame.draw.rect(mm_surf, col, (int(rx), int(ry), rw, rh))

        # Walls
        for wall in floor.walls:
            wx = wall.x * scale - ox
            wy = wall.y * scale - oy
            ww = max(1, int(wall.width * scale))
            wh = max(1, int(wall.height * scale))
            pygame.draw.rect(mm_surf, (100, 100, 110, 220),
                             (int(wx), int(wy), ww, wh))

        # Transitions
        for tr in floor.transitions:
            tx = tr.rect.x * scale - ox
            ty = tr.rect.y * scale - oy
            tw = max(2, int(tr.rect.width * scale))
            th = max(2, int(tr.rect.height * scale))
            col = (180, 70, 70, 200) if tr.locked else (80, 180, 255, 200)
            pygame.draw.rect(mm_surf, col, (int(tx), int(ty), tw, th))

        # Player dot (always at center)
        pygame.draw.circle(mm_surf, (255, 220, 60), (radius, radius), 4)
        pygame.draw.circle(mm_surf, WHITE, (radius, radius), 4, 1)

        # Apply circular mask
        mask_surf = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        pygame.draw.circle(mask_surf, (255, 255, 255, 255),
                           (radius, radius), radius)
        mm_surf.blit(mask_surf, (0, 0),
                     special_flags=pygame.BLEND_RGBA_MIN)

        # Draw on screen
        screen.blit(mm_surf, (mm_cx - radius, mm_cy - radius))

        # Border ring
        pygame.draw.circle(screen, UI_BORDER, (mm_cx, mm_cy), radius, 2)
        pygame.draw.circle(screen, UI_ACCENT, (mm_cx, mm_cy), radius + 1, 1)

        # Floor label + hint
        lbl = self.font_hint.render(f"{floor.name}  [M]", True, UI_TEXT_DIM)
        screen.blit(lbl, lbl.get_rect(
            center=(mm_cx, mm_cy - radius - 10)))

    # ── pause menu ────────────────────────────────────────────

    def draw_pause_menu(self, screen: pygame.Surface):
        """Semi-transparent pause overlay."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        screen.blit(overlay, (0, 0))

        cx = SCREEN_WIDTH // 2
        screen.blit(
            self.font_title.render("PAUSED", True, UI_ACCENT),
            self.font_title.render("PAUSED", True, UI_ACCENT).get_rect(center=(cx, 250)),
        )
        screen.blit(
            self.font_menu.render("Press ESC to resume", True, UI_TEXT),
            self.font_menu.render("Press ESC to resume", True, UI_TEXT).get_rect(center=(cx, 330)),
        )
        screen.blit(
            self.font_menu.render("Press Q to quit", True, UI_TEXT_DIM),
            self.font_menu.render("Press Q to quit", True, UI_TEXT_DIM).get_rect(center=(cx, 380)),
        )

    # ── help screen ───────────────────────────────────────────

    def draw_help_screen(self, screen: pygame.Surface, character: Character):
        """Full-screen help / controls reference."""
        screen.fill(UI_BG)
        cx = SCREEN_WIDTH // 2

        screen.blit(
            self.font_title.render("HELP  —  Controls", True, UI_ACCENT),
            self.font_title.render("HELP  —  Controls", True, UI_ACCENT).get_rect(center=(cx, 45)),
        )

        lines = [
            ("Movement",     "W A S D"),
            ("Sprint",       "Hold SHIFT"),
            ("Interact",     "SPACE"),
            ("Use Item",     "E"),
            ("Inventory",    "I"),
            ("Skill Tree",   "K"),
            ("Map",          "M"),
            ("Help",         "H"),
            ("Pause",        "ESC"),
        ]

        if character == Character.AIDEN:
            lines += [
                ("", ""),
                ("── COMBAT (Aiden) ──", ""),
                ("Light Attack", "J"),
                ("Heavy Attack", "U"),
                ("Block",        "L"),
                ("Dash",         "SHIFT"),
            ]
        else:
            lines += [
                ("", ""),
                ("── HACKING (Lena) ──", ""),
                ("Start Hack",      "F"),
                ("Type characters",   "keyboard"),
                ("Abort",            "ESC"),
            ]

        lines += [
            ("", ""),
            ("── TIPS ──", ""),
            ("Talk to NPCs to uncover the Smile Club.", ""),
            ("Your actions affect your reputation!", ""),
            ("Help others during 'bad day' events.", ""),
            ("Multiple endings based on your choices.", ""),
        ]

        y = 100
        for label, value in lines:
            if label.startswith("──"):
                screen.blit(self.font_hud_lg.render(label, True, UI_ACCENT), (60, y))
            elif label == "":
                pass
            elif value:
                screen.blit(self.font_hud_md.render(label, True, UI_TEXT), (80, y))
                screen.blit(self.font_hud_md.render(value, True, UI_ACCENT), (380, y))
            else:
                screen.blit(self.font_hud_sm.render(label, True, UI_TEXT_DIM), (100, y))
            y += 28

        screen.blit(
            self.font_hint.render("Press H to close", True, UI_TEXT_DIM),
            (cx - 60, SCREEN_HEIGHT - 30),
        )

    # ── inventory / skill tree delegates ──────────────────────

    def draw_inventory(self, screen: pygame.Surface, inventory):
        """Delegate to Inventory's own draw method."""
        inventory.draw(screen)

    def draw_skill_tree(self, screen: pygame.Surface, skill_tree, player):
        """Delegate to SkillTree's own draw method."""
        if skill_tree:
            skill_tree.draw(screen, player)

    # ── game over / victory ───────────────────────────────────

    def draw_game_over(self, screen: pygame.Surface, ending: Ending):
        """Full-screen ending screen."""
        screen.fill(UI_BG)
        cx = SCREEN_WIDTH // 2

        colour_map = {
            Ending.GOOD:    NOTIF_SUCCESS,
            Ending.NEUTRAL: NOTIF_WARNING,
            Ending.DARK:    NOTIF_ERROR,
        }
        title_map = {
            Ending.GOOD:    "THE TRUTH PREVAILS",
            Ending.NEUTRAL: "A FRAGILE PEACE",
            Ending.DARK:    "BEHIND THE SMILE",
        }
        desc_map = {
            Ending.GOOD: (
                "You exposed the Smile Club, helped the victims, and\n"
                "changed Ravenside High for the better.\n\n"
                "The director was removed. Students finally feel safe.\n"
                "Every voice mattered — including yours."
            ),
            Ending.NEUTRAL: (
                "The Smile Club was weakened but not destroyed.\n"
                "Some students still suffer in silence.\n\n"
                "You made a difference, but the fight isn't over."
            ),
            Ending.DARK: (
                "The Smile Club tightened its grip.\n"
                "Fear rules the halls of Ravenside High.\n\n"
                "Sometimes doing nothing is the worst choice of all."
            ),
        }

        col = colour_map.get(ending, WHITE)
        screen.blit(
            self.font_title.render(title_map.get(ending, "THE END"), True, col),
            self.font_title.render(title_map.get(ending, "THE END"), True, col)
            .get_rect(center=(cx, 160)),
        )

        # Multi-line description
        desc = desc_map.get(ending, "")
        y = 260
        for line in desc.split("\n"):
            surf = self.font_hud_md.render(line, True, UI_TEXT)
            screen.blit(surf, surf.get_rect(center=(cx, y)))
            y += 28

        # Ending label
        y += 20
        screen.blit(
            self.font_menu.render(f"— {ending.value.upper()} ENDING —", True, col),
            self.font_menu.render(f"— {ending.value.upper()} ENDING —", True, col)
            .get_rect(center=(cx, y)),
        )

        screen.blit(
            self.font_hint.render("Press ESC to return to menu", True, UI_TEXT_DIM),
            (cx - 100, SCREEN_HEIGHT - 40),
        )
