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
        self.font_hud_time = pygame.font.SysFont("arial", 24, bold=True)
        self.font_title   = pygame.font.SysFont("arial", 48, bold=True)
        self.font_menu    = pygame.font.SysFont("arial", 30)
        self.font_hint    = pygame.font.SysFont("arial", 16)
        
        # HUD icons: wallet + phone, right-anchored to the left of the minimap
        # Minimap spans up to approx 160px from the right, so we offset by 170px
        _icon_h    = 44
        _icon_w    = 40
        _icon_bot  = SCREEN_HEIGHT - 26          # bottom edge raised higher
        _wallet_x  = SCREEN_WIDTH  - 170 - _icon_w # right margin 170px
        self.wallet_icon_rect = pygame.Rect(_wallet_x,  _icon_bot - _icon_h, _icon_w, _icon_h)
        self.phone_icon_rect  = pygame.Rect(_wallet_x - _icon_w - 8, _icon_bot - _icon_h, _icon_w, _icon_h)
        
        # New Wallet UI constants
        cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
        self.wallet_bg_rect = pygame.Rect(cx - 340, cy - 220, 680, 440)
        
        # ID Card inside Left Slot 2 (visible area)
        self.wallet_id_rect = pygame.Rect(cx - 310, cy - 140, 280, 50)
        
        # Bill inside Right Slot 2 (visible area)
        self.wallet_bill_rect = pygame.Rect(cx + 30, cy - 140, 280, 50)

        # Hover animation offsets for wallet items
        self._wallet_hover_offsets = {"id": 0.0, "bill": 0.0}

        # Announcement state
        self._announcement_timer = 0.0
        self._announcement_title = ""
        self._announcement_sub = ""
        self._bell_icon = None
        try:
            # Note: Path is specific to the generated asset
            self._bell_icon = pygame.image.load(r"C:\Users\boths\.gemini\antigravity\brain\ee9cae87-ae12-4b5e-b64b-2404224d3d3c\school_bell_icon_1777762071293.png")
            self._bell_icon = pygame.transform.smoothscale(self._bell_icon, (80, 80))
        except:
            pass

    # ── notifications ─────────────────────────────────────────

    def show_notification(self, text: str, colour: tuple = NOTIF_INFO,
                          duration: float = 3.0):
        """Queue a notification (newest at bottom)."""
        self._notifs.append(Notification(text, colour, duration))
        if len(self._notifs) > self.MAX_NOTIFS:
            self._notifs.pop(0)

    def trigger_level_up(self):
        self._level_up_timer = 4.0

    def trigger_announcement(self, title: str, sub: str):
        self._announcement_title = title
        self._announcement_sub = sub
        self._announcement_timer = 5.0

    def update(self, dt: float):
        """Tick notification timers."""
        for n in self._notifs:
            n.timer -= dt
        self._notifs = [n for n in self._notifs if not n.expired]
        if getattr(self, '_level_up_timer', 0) > 0:
            self._level_up_timer -= dt
        if getattr(self, '_announcement_timer', 0) > 0:
            self._announcement_timer -= dt

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

        timer = getattr(self, '_level_up_timer', 0)
        if timer > 0:
            font = pygame.font.SysFont("arial", 80, bold=True)
            text_str = "LEVEL UP!"
            text = font.render(text_str, True, (255, 215, 0))
            outline = font.render(text_str, True, (0, 0, 0))
            cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 4
            alpha = 255
            if timer < 1.0: alpha = int(255 * timer)
            w, h = text.get_size()
            surf = pygame.Surface((w + 6, h + 6), pygame.SRCALPHA)
            for dx, dy in [(-3,-3), (3,-3), (-3,3), (3,3), (0,-3), (0,3), (-3,0), (3,0)]:
                surf.blit(outline, (3 + dx, 3 + dy))
            surf.blit(text, (3, 3))
            surf.set_alpha(alpha)
            scale = 1.0 + 0.08 * math.sin(timer * 8)
            new_size = (int(surf.get_width() * scale), int(surf.get_height() * scale))
            scaled_surf = pygame.transform.smoothscale(surf, new_size)
            screen.blit(scaled_surf, scaled_surf.get_rect(center=(cx, cy)))

        self.draw_announcement(screen)

    def draw_announcement(self, screen: pygame.Surface):
        """Render a large centered announcement for school events."""
        timer = getattr(self, '_announcement_timer', 0)
        if timer <= 0:
            return

        cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3
        alpha = 255
        if timer < 1.0: alpha = int(255 * timer)
        elif timer > 4.5: alpha = int(255 * (5.0 - timer) / 0.5)

        # Draw panel
        panel_w, panel_h = 600, 120
        panel_rect = pygame.Rect(cx - panel_w//2, cy - panel_h//2, panel_w, panel_h)
        s = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        s.fill((20, 20, 35, min(alpha, 220)))
        pygame.draw.rect(s, UI_ACCENT, (0, 0, panel_w, panel_h), 2, border_radius=10)
        screen.blit(s, panel_rect)

        # Pulse effect
        pulse = 1.0 + 0.05 * math.sin(timer * 6)
        
        # Icon
        if self._bell_icon:
            icon_surf = self._bell_icon.copy()
            if pulse != 1.0:
                isize = (int(80 * pulse), int(80 * pulse))
                icon_surf = pygame.transform.smoothscale(icon_surf, isize)
            icon_rect = icon_surf.get_rect(midleft=(panel_rect.x + 30, cy))
            icon_surf.set_alpha(alpha)
            screen.blit(icon_surf, icon_rect)

        # Title
        title_font = pygame.font.SysFont("arial", 54, bold=True)
        title_surf = title_font.render(self._announcement_title, True, UI_ACCENT)
        title_surf.set_alpha(alpha)
        screen.blit(title_surf, (panel_rect.x + 130, cy - 35))

        # Subtext
        sub_surf = self.font_hud_md.render(self._announcement_sub, True, WHITE)
        sub_surf.set_alpha(alpha)
        screen.blit(sub_surf, (panel_rect.x + 132, cy + 15))

    # ── HUD ───────────────────────────────────────────────────

    def draw_hud(self, screen: pygame.Surface, player, current_phase,
                 day_number: int, floor=None, room=None, reputation=None,
                 time_text: str | None = None, hud_focus: str | None = None,
                 car_rect: pygame.Rect | None = None):
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
        total_xp = player.xp + (player.level - 1) * XP_PER_LEVEL
        MAX_LEVEL = 10
        max_total_xp = MAX_LEVEL * XP_PER_LEVEL
        self._bar(screen, 16, 56, 180, 10,
                  total_xp, max_total_xp,
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
        loc_rect = zn.get_rect(topright=(SCREEN_WIDTH - 16, 12))
        screen.blit(zn, loc_rect)

        # ── circular minimap (bottom-right) ──
        self._draw_minimap_circle(screen, floor, player, car_rect)

        # ── reputation bar (bottom-left) ──
        try:
            rep_val = reputation.reputation_score if reputation is not None else 0
        except Exception:
            rep_val = 0
        # draw above the bottom edge
        rep_x = 16
        rep_y = SCREEN_HEIGHT - 36
        self._bar(screen, rep_x, rep_y, 220, 14, rep_val, 100, UI_ACCENT, UI_PANEL, "Rep")

        if time_text:
            time_surf = self.font_hud_time.render(time_text, True, UI_TEXT_DIM)
            time_rect = time_surf.get_rect(midleft=(rep_x + 220 + 24, rep_y + 7))
            screen.blit(time_surf, time_rect)
            
            # ── Fast Forward Button ──
            self.ff_button_rect = pygame.Rect(time_rect.right + 12, time_rect.y - 4, 40, 32)
            
            mouse_pos = pygame.mouse.get_pos()
            hover = self.ff_button_rect.collidepoint(mouse_pos)
            is_pressed = pygame.mouse.get_pressed()[0] and hover
            highlight_ff = hover or hud_focus == "ff"
            
            btn_col = (120, 210, 255) if is_pressed else ((100, 150, 255) if hover else (40, 40, 60))
            pygame.draw.rect(screen, btn_col, self.ff_button_rect, border_radius=6)
            pygame.draw.rect(screen, WHITE, self.ff_button_rect, 1, border_radius=6)
            if highlight_ff:
                pygame.draw.rect(screen, (255, 220, 80), self.ff_button_rect.inflate(8, 8), 2, border_radius=8)
            
            # Double arrow icon >>
            arw = WHITE
            x, y, w, h = self.ff_button_rect.x, self.ff_button_rect.y, 40, 32
            # Tip 1
            pygame.draw.polygon(screen, arw, [(x+10, y+8), (x+20, y+16), (x+10, y+24)])
            # Tip 2
            pygame.draw.polygon(screen, arw, [(x+22, y+8), (x+32, y+16), (x+22, y+24)])

        # ── wallet icon ──
        wr = self.wallet_icon_rect
        pygame.draw.rect(screen, (95, 60, 30), wr, border_radius=6)
        pygame.draw.rect(screen, (150, 105, 55), wr, border_radius=6, width=2)
        # Flap
        flap = pygame.Rect(wr.centerx - 7, wr.y + 2, 14, 18)
        pygame.draw.rect(screen, (65, 38, 18), flap, border_radius=3)
        # Clasp
        pygame.draw.rect(screen, (220, 185, 55),
                         (wr.centerx - 4, wr.y + 14, 8, 7), border_radius=2)
        # Label
        w_lbl = self.font_hint.render("Wallet", True, UI_TEXT_DIM)
        screen.blit(w_lbl, w_lbl.get_rect(center=(wr.centerx, wr.top - 10)))
        # Key hint
        k_lbl = self.font_hint.render("[I]", True, UI_TEXT_DIM)
        screen.blit(k_lbl, k_lbl.get_rect(center=(wr.centerx, wr.bottom + 10)))
        wallet_hover = wr.collidepoint(pygame.mouse.get_pos())
        if wallet_hover or hud_focus == "wallet":
            pygame.draw.rect(screen, (255, 220, 80), wr.inflate(6, 6), 2, border_radius=8)

        # ── phone icon (delegated to Phone.draw_hud_icon) ──
        # Drawn by game.py via self.phone.draw_hud_icon(screen, self.ui.phone_icon_rect, unread)
        # But we still draw the label + key-hint here for consistency
        pr = self.phone_icon_rect
        ph_lbl = self.font_hint.render("Phone", True, UI_TEXT_DIM)
        screen.blit(ph_lbl, ph_lbl.get_rect(center=(pr.centerx, pr.top - 10)))
        ph_key = self.font_hint.render("[P]", True, UI_TEXT_DIM)
        screen.blit(ph_key, ph_key.get_rect(center=(pr.centerx, pr.bottom + 10)))
        phone_hover = pr.collidepoint(pygame.mouse.get_pos())
        if phone_hover or hud_focus == "phone":
            pygame.draw.rect(screen, (255, 220, 80), pr.inflate(6, 6), 2, border_radius=8)

    def _bar(self, screen, x, y, w, h, cur, mx, fg, bg, label=""):
        """Utility: draw a filled bar with a label."""
        pygame.draw.rect(screen, bg, (x, y, w, h), border_radius=3)
        fill_w = int(w * max(0, cur) / max(1, mx))
        pygame.draw.rect(screen, fg, (x, y, fill_w, h), border_radius=3)
        pygame.draw.rect(screen, WHITE, (x, y, w, h), 1, border_radius=3)
        if label:
            lbl = self.font_hud_sm.render(f"{label} {int(cur)}/{int(mx)}", True, WHITE)
            screen.blit(lbl, (x + 4, y - 1))

    def _draw_minimap_circle(self, screen, floor, player, car_rect=None):
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

        # Transitions removed from minimap as requested
        pass

        # Draw car on minimap
        if car_rect:
            cx = car_rect.x * scale - ox
            cy = car_rect.y * scale - oy
            cw = max(10, int(car_rect.width * scale))
            ch = max(4, int(car_rect.height * scale))
            bus_yellow = (250, 160, 30, 220)
            # Bus body
            pygame.draw.rect(mm_surf, bus_yellow, (int(cx), int(cy), cw, ch), border_radius=2)
            # Roof detail (stripes)
            pygame.draw.rect(mm_surf, (20, 20, 20, 220), (int(cx + 2), int(cy + ch * 0.2), cw - 4, 1))
            pygame.draw.rect(mm_surf, (20, 20, 20, 220), (int(cx + 2), int(cy + ch * 0.8), cw - 4, 1))
            # Windows
            pygame.draw.rect(mm_surf, (40, 60, 80, 220), (int(cx + 4), int(cy + ch * 0.4), cw - 8, max(1, int(ch * 0.2))))
            # Wheels
            pygame.draw.rect(mm_surf, (30, 30, 30, 255), (int(cx + cw*0.15), int(cy - 2), cw*0.15, 2))
            pygame.draw.rect(mm_surf, (30, 30, 30, 255), (int(cx + cw*0.7), int(cy - 2), cw*0.15, 2))
            pygame.draw.rect(mm_surf, (30, 30, 30, 255), (int(cx + cw*0.15), int(cy + ch), cw*0.15, 2))
            pygame.draw.rect(mm_surf, (30, 30, 30, 255), (int(cx + cw*0.7), int(cy + ch), cw*0.15, 2))

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

    def draw_pause_menu(self, screen: pygame.Surface, sel: int = 0, options: list[str] | None = None):
        """Semi-transparent pause overlay."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        screen.blit(overlay, (0, 0))

        cx = SCREEN_WIDTH // 2
        screen.blit(
            self.font_title.render("PAUSED", True, UI_ACCENT),
            self.font_title.render("PAUSED", True, UI_ACCENT).get_rect(center=(cx, 250)),
        )
        
        options = options or ["Resume", "Change Character", "Main Menu", "Quit"]
        for i, opt in enumerate(options):
            col = UI_ACCENT if i == sel else UI_TEXT_DIM
            prefix = "► " if i == sel else "  "
            text_surf = self.font_menu.render(prefix + opt, True, col)
            screen.blit(text_surf, text_surf.get_rect(center=(cx, 330 + i * 50)))

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

    # ── wallet ui ─────────────────────────────────────────────

    def draw_wallet(self, screen: pygame.Surface, active_item: str | None, character, controller_connected: bool = False, focus_item: str | None = None):
        """Draw the wallet interface. Semi-transparent background."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        screen.blit(overlay, (0, 0))

        cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
        
        if not active_item:
            # 1. Draw Wallet Background (Outside/Main Body)
            pygame.draw.rect(screen, (50, 25, 15), self.wallet_bg_rect, border_radius=12)
            pygame.draw.rect(screen, (30, 15, 10), self.wallet_bg_rect, 4, border_radius=12)
            
            # Middle fold
            pygame.draw.line(screen, (20, 10, 5), (cx, self.wallet_bg_rect.y), (cx, self.wallet_bg_rect.bottom), 6)
            
            # Stitching on the outer edge
            pygame.draw.rect(screen, (100, 50, 30), self.wallet_bg_rect.inflate(-12, -12), 2, border_radius=10)

            # 3. Draw Left & Right Slots
            slot_ys = [cy - 180, cy - 90, cy, cy + 90]

            highlight_item = focus_item
            mx, my = pygame.mouse.get_pos()
            mouse_item = None
            if self.wallet_id_rect.collidepoint((mx, my)):
                mouse_item = "id"
            elif self.wallet_bill_rect.collidepoint((mx, my)):
                mouse_item = "bill"
            if mouse_item:
                highlight_item = mouse_item

            for key in ("id", "bill"):
                target = -24 if highlight_item == key else 0
                current = self._wallet_hover_offsets[key]
                self._wallet_hover_offsets[key] = current + (target - current) * 0.25

            id_offset = int(round(self._wallet_hover_offsets["id"]))
            bill_offset = int(round(self._wallet_hover_offsets["bill"]))
            
            for i, sy in enumerate(slot_ys):
                # --- Left Side ---
                # Draw ID card before drawing its pocket cover (Slot 2 = index 1)
                if i == 1:
                    full_id_base = pygame.Rect(self.wallet_id_rect.x, self.wallet_id_rect.y, self.wallet_id_rect.width, 160)
                    full_id = full_id_base.move(0, id_offset)
                    pygame.draw.rect(screen, (220, 220, 230), full_id, border_radius=8)
                    pygame.draw.rect(screen, (100, 100, 150), full_id, 2, border_radius=8)
                    id_title = self.font_hud_md.render("Ravenside High ID", True, BLACK)
                    screen.blit(id_title, (full_id.x + 10, full_id.y + 8))
                    if highlight_item == "id":
                        pygame.draw.rect(screen, UI_ACCENT, full_id.inflate(6, 6), 2, border_radius=10)
                
                # Draw Left Pocket Cover
                pocket_h = self.wallet_bg_rect.bottom - sy - 10
                pocket_rect_left = pygame.Rect(self.wallet_bg_rect.x + 20, sy, 300, pocket_h)
                pygame.draw.rect(screen, (60, 30, 18), pocket_rect_left, border_radius=4)
                pygame.draw.rect(screen, (35, 18, 10), pocket_rect_left, 2, border_radius=4)
                pygame.draw.line(screen, (100, 50, 30), (pocket_rect_left.x + 5, pocket_rect_left.y + 4), (pocket_rect_left.right - 5, pocket_rect_left.y + 4), 1)

                # --- Right Side ---
                # Draw Bill before drawing its pocket cover (Slot 2 = index 1)
                if i == 1:
                    full_bill_base = pygame.Rect(self.wallet_bill_rect.x, self.wallet_bill_rect.y, self.wallet_bill_rect.width, 160)
                    full_bill = full_bill_base.move(0, bill_offset)
                    pygame.draw.rect(screen, (100, 150, 100), full_bill, border_radius=4)
                    pygame.draw.rect(screen, (50, 100, 50), full_bill, 2, border_radius=4)
                    bill_title = self.font_hud_lg.render("$5", True, (20, 60, 20))
                    screen.blit(bill_title, (full_bill.x + 10, full_bill.y + 6))
                    if highlight_item == "bill":
                        pygame.draw.rect(screen, UI_ACCENT, full_bill.inflate(6, 6), 2, border_radius=8)

                # Draw Right Pocket Cover
                pocket_rect_right = pygame.Rect(cx + 20, sy, 300, pocket_h)
                pygame.draw.rect(screen, (60, 30, 18), pocket_rect_right, border_radius=4)
                pygame.draw.rect(screen, (35, 18, 10), pocket_rect_right, 2, border_radius=4)
                pygame.draw.line(screen, (100, 50, 30), (pocket_rect_right.x + 5, pocket_rect_right.y + 4), (pocket_rect_right.right - 5, pocket_rect_right.y + 4), 1)

            # Hint - Adaptive: Xbox or Keyboard
            if controller_connected:
                hint_text = "[A] Inspect item  |  [B] Close Wallet"
            else:
                hint_text = "Click an item to inspect. Press ESC or click outside to close."
            hint = self.font_hint.render(hint_text, True, UI_TEXT_DIM)
            screen.blit(hint, hint.get_rect(center=(cx, self.wallet_bg_rect.bottom + 30)))
            
        else:
            for key in self._wallet_hover_offsets:
                self._wallet_hover_offsets[key] *= 0.6
                if abs(self._wallet_hover_offsets[key]) < 0.1:
                    self._wallet_hover_offsets[key] = 0.0
            # Draw active item zoomed in
            if active_item == "id":
                big_id = pygame.Rect(cx - 250, cy - 150, 500, 300)
                pygame.draw.rect(screen, (220, 220, 230), big_id, border_radius=12)
                pygame.draw.rect(screen, UI_ACCENT, big_id, 4, border_radius=12)
                
                # ID Header
                header = self.font_menu.render("Ravenside High - Student ID", True, (50, 50, 100))
                screen.blit(header, header.get_rect(center=(cx, big_id.y + 40)))
                pygame.draw.line(screen, (100, 100, 150), (big_id.x + 20, big_id.y + 70), (big_id.right - 20, big_id.y + 70), 3)
                
                # Details
                y_off = big_id.y + 100
                first_name = character.value.title() if character else "Aiden"
                details = [
                    f"Name: {first_name} Parker",
                    "Student ID: 202467",
                    "Grade: 10th grade",
                ]
                for d in details:
                    if d:
                        text = self.font_hud_lg.render(d, True, BLACK)
                    else:
                        # Add spacing line
                        y_off += 20
                        continue
                    screen.blit(text, (big_id.x + 40, y_off))
                    y_off += 50
                    
                # Photo placeholder
                photo_rect = pygame.Rect(big_id.right - 140, big_id.y + 100, 100, 130)
                pygame.draw.rect(screen, (180, 180, 190), photo_rect)
                pygame.draw.rect(screen, (100, 100, 100), photo_rect, 2)
                
                # Description panel
                desc_panel = pygame.Rect(big_id.x + 30, big_id.bottom + 20, big_id.width - 60, 130)
                pygame.draw.rect(screen, (14, 14, 24), desc_panel, border_radius=18)
                pygame.draw.rect(screen, UI_ACCENT, desc_panel, 3, border_radius=18)

                title_bar = pygame.Rect(desc_panel.x + 18, desc_panel.y + 18, desc_panel.width - 36, 40)
                pygame.draw.rect(screen, (40, 60, 80), title_bar, border_radius=12)
                pygame.draw.rect(screen, UI_ACCENT, title_bar, 2, border_radius=12)
                desc_title = self.font_hud_md.render("Description", True, UI_ACCENT)
                screen.blit(desc_title, desc_title.get_rect(center=title_bar.center))

                body_text = "Used for entering in some special rooms"
                desc_body = self.font_hud_sm.render(body_text, True, UI_TEXT)
                screen.blit(desc_body, desc_body.get_rect(center=(desc_panel.centerx, title_bar.bottom + 32)))

                return_text = "[B] Return to wallet" if controller_connected else "Press ESC or click to return to wallet"
                hint_surface = self.font_hint.render(return_text, True, UI_ACCENT)
                screen.blit(hint_surface, hint_surface.get_rect(center=(cx, big_id.y - 40)))

            elif active_item == "bill":
                big_bill = pygame.Rect(cx - 300, cy - 120, 600, 240)
                pygame.draw.rect(screen, (100, 150, 100), big_bill, border_radius=8)
                pygame.draw.rect(screen, UI_ACCENT, big_bill, 4, border_radius=8)
                
                # Bill details
                tl = self.font_title.render("5", True, (20, 60, 20))
                screen.blit(tl, (big_bill.x + 20, big_bill.y + 10))
                screen.blit(tl, (big_bill.right - 40, big_bill.y + 10))
                screen.blit(tl, (big_bill.x + 20, big_bill.bottom - 50))
                screen.blit(tl, (big_bill.right - 40, big_bill.bottom - 50))
                
                center_text = self.font_title.render("FIVE DOLLARS", True, (40, 90, 40))
                screen.blit(center_text, center_text.get_rect(center=(cx, cy)))

                return_text = "[B] Return to wallet" if controller_connected else "Press ESC or click to return to wallet"
                hint_surface = self.font_hint.render(return_text, True, UI_ACCENT)
                screen.blit(hint_surface, hint_surface.get_rect(center=(cx, big_bill.y - 40)))
                
                # Description panel
                desc_panel = pygame.Rect(big_bill.x + 30, big_bill.bottom + 20, big_bill.width - 60, 130)
                pygame.draw.rect(screen, (14, 14, 24), desc_panel, border_radius=18)
                pygame.draw.rect(screen, UI_ACCENT, desc_panel, 3, border_radius=18)

                title_bar = pygame.Rect(desc_panel.x + 18, desc_panel.y + 18, desc_panel.width - 36, 40)
                pygame.draw.rect(screen, (40, 60, 80), title_bar, border_radius=12)
                pygame.draw.rect(screen, UI_ACCENT, title_bar, 2, border_radius=12)
                desc_title = self.font_hud_md.render("Description", True, UI_ACCENT)
                screen.blit(desc_title, desc_title.get_rect(center=title_bar.center))

                body_text = "For lunch at the cafeteria"
                desc_body = self.font_hud_sm.render(body_text, True, UI_TEXT)
                screen.blit(desc_body, desc_body.get_rect(center=(desc_panel.centerx, title_bar.bottom + 32)))

            # Return hint rendered above the item (see blocks above)
