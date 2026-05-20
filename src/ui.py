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
    MOTIVATIONAL_MESSAGES, VT323_PATH)


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
        self.font_hud_sm  = pygame.font.Font(VT323_PATH, 16)
        self.font_hud_md  = pygame.font.Font(VT323_PATH, 20)
        self.font_hud_lg  = pygame.font.Font(VT323_PATH, 26)
        self.font_hud_time = pygame.font.Font(VT323_PATH, 24)
        self.font_title   = pygame.font.Font(VT323_PATH, 48)
        self.font_menu    = pygame.font.Font(VT323_PATH, 30)
        self.font_hint    = pygame.font.Font(VT323_PATH, 16)
        
        # HUD icons: wallet + phone, bottom-right.
        _icon_h    = 44
        _icon_w    = 40
        _icon_bot  = SCREEN_HEIGHT - 26          # bottom edge raised higher
        _wallet_x  = SCREEN_WIDTH - 16 - _icon_w
        self.wallet_icon_rect = pygame.Rect(_wallet_x,  _icon_bot - _icon_h, _icon_w, _icon_h)
        self.phone_icon_rect  = pygame.Rect(_wallet_x - _icon_w - 8, _icon_bot - _icon_h, _icon_w, _icon_h)
        
        # New Wallet UI constants
        cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
        self.wallet_bg_rect = pygame.Rect(cx - 340, cy - 220, 680, 440)
        
        # ID Card inside Left Slot 2 (visible area)
        self.wallet_id_rect = pygame.Rect(cx - 310, cy - 140, 280, 50)
        
        # Bill inside Right Slot 2 (visible area)
        self.wallet_bill_rect = pygame.Rect(cx + 30, cy - 140, 280, 50)

        # Yearbook inside Left Slot 3 (visible area)
        self.wallet_yearbook_rect = pygame.Rect(cx - 310, cy - 50, 280, 50)

        # Hacked Credentials inside Right Slot 3 (visible area)
        self.wallet_cred_rect = pygame.Rect(cx + 30, cy - 50, 280, 50)

        # Hover animation offsets for wallet items
        self._wallet_hover_offsets = {"id": 0.0, "bill": 0.0, "yearbook": 0.0, "cred": 0.0}

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
            
        # Player Avatars
        self.player_avatars = {}
        try:
            realistic_path = "assets/Imagenes realistas personajes/"
            # Aiden
            self.player_avatars[Character.AIDEN] = pygame.image.load(realistic_path + "Aiden Parker.png").convert_alpha()
            # Lena - checking user path first, then fallback to what I saw
            import os
            lena_path = realistic_path + "Lena Parker.png"
            if not os.path.exists(lena_path):
                lena_path = realistic_path + "Lena Aiden.png" # Fallback to what exists
            self.player_avatars[Character.LENA] = pygame.image.load(lena_path).convert_alpha()
        except:
            pass

        # Smile Club Image for Alarm
        self.smile_club_img = None
        try:
            img = pygame.image.load("assets/UI/smile club.png").convert_alpha()
            self.smile_club_img = pygame.transform.smoothscale(img, (260, 260))
        except Exception as e:
            print(f"Error loading smile club image: {e}")

    # ── notifications ─────────────────────────────────────────

    def show_notification(self, text: str, colour: tuple = NOTIF_INFO,
                          duration: float = 3.0):
        """Queue a notification (newest at bottom)."""
        self._notifs.append(Notification(text, colour, duration))
        if len(self._notifs) > self.MAX_NOTIFS:
            self._notifs.pop(0)

    def trigger_level_up(self, money_amount: int = 10):
        self._level_up_timer = 4.0
        self._level_up_money = money_amount

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
            font = pygame.font.Font(VT323_PATH, 80)
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

            money = getattr(self, '_level_up_money', 10)
            font_sub = pygame.font.Font(VT323_PATH, 50)
            sub_str = f"+${money}"
            sub_text = font_sub.render(sub_str, True, (100, 255, 100))
            sub_outline = font_sub.render(sub_str, True, (0, 0, 0))
            sub_w, sub_h = sub_text.get_size()
            sub_surf = pygame.Surface((sub_w + 4, sub_h + 4), pygame.SRCALPHA)
            for dx, dy in [(-2,-2), (2,-2), (-2,2), (2,2), (0,-2), (0,2), (-2,0), (2,0)]:
                sub_surf.blit(sub_outline, (2 + dx, 2 + dy))
            sub_surf.blit(sub_text, (2, 2))
            sub_surf.set_alpha(alpha)
            sub_y = cy + scaled_surf.get_height() // 2 + 25
            screen.blit(sub_surf, sub_surf.get_rect(center=(cx, sub_y)))

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
        title_font = pygame.font.Font(VT323_PATH, 54)
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
        # ── player avatar ──
        av_x, av_y = 16, 16
        av_radius = 34
        
        # Determine current character's avatar
        cur_char = getattr(player, "character", Character.AIDEN)
        avatar_img = self.player_avatars.get(cur_char)

        # Border color based on character
        border_col = UI_ACCENT if cur_char == Character.AIDEN else (255, 180, 220) # Lighter Pink for Lena
        
        # Border round
        pygame.draw.circle(screen, border_col, (av_x + av_radius, av_y + av_radius), av_radius + 2)
        pygame.draw.circle(screen, BLACK, (av_x + av_radius, av_y + av_radius), av_radius)
        
        if avatar_img:
            size = av_radius * 2
            av_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(av_surf, (255, 255, 255), (av_radius, av_radius), av_radius)
            scaled = pygame.transform.smoothscale(avatar_img, (size, size))
            av_surf.blit(scaled, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            screen.blit(av_surf, (av_x, av_y))
        else:
            # Fallback circle
            pygame.draw.circle(screen, (50, 50, 70), (av_x + av_radius, av_y + av_radius), av_radius)
            init_char = "L" if cur_char == Character.LENA else "A"
            init = self.font_hud_lg.render(init_char, True, WHITE)
            screen.blit(init, init.get_rect(center=(av_x + av_radius, av_y + av_radius)))

        # ── health bar ──
        bars_x = av_x + av_radius * 2 + 12
        self._bar(screen, bars_x, 16, 180, 14,
                  player.health, player.max_health,
                  HEALTH_RED, HEALTH_BG, "HP")

        # ── reputation bar ──
        try:
            rep_avg = int(reputation.average()) if reputation else 50
        except Exception:
            rep_avg = 50
        self._bar(screen, bars_x, 36, 180, 14,
                  rep_avg, 100,
                  UI_ACCENT, UI_PANEL, "REP")

        # ── stamina bar ──
        self._bar(screen, bars_x, 56, 180, 14,
                  player.stamina, player.max_stamina,
                  STAMINA_YELLOW, STAMINA_BG, "SP")

        # ── Level bar ──
        MAX_LEVEL = 30
        self._bar(screen, bars_x, 76, 180, 10,
                  player.level, MAX_LEVEL,
                  XP_BLUE, XP_BG, "Lv")

        # ── Basement Detection Meter ──
        if floor and floor.id == 3 and day_number >= 4:
            # We assume game object is accessible or we pass detection level via reputation hack or something.
            # Wait, ui doesn't have game access. We can access it via player or pass it explicitly.
            # Since I can't easily change draw_hud signature across all files without a big refactor,
            # I can stick the detection level onto the player object from game.py or access it via world_map.
            det_lvl = getattr(player, 'detection_level', 0.0) 
            self._bar(screen, bars_x, 92, 180, 10,
                      det_lvl, 100,
                      (255, 60, 60), (40, 20, 20), "DETECT")

        # ── money (to the right of bars) ──
        money_x = bars_x + 200
        money_surf = self.font_hud_lg.render(f"${player.money}", True, (57, 255, 20))
        screen.blit(money_surf, (money_x, 30))

        # ── day / phase ──
        phase_str = current_phase.value.replace("_", " ").title()
        day_text = f"Day {day_number}  —  {phase_str}"
        screen.blit(self.font_hud_sm.render(day_text, True, WHITE),
                    (bars_x, 106))

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

        if time_text:
            time_surf = self.font_hud_time.render(time_text, True, WHITE)
            # Position time display in bottom-left
            rep_y = SCREEN_HEIGHT - 36
            time_rect = time_surf.get_rect(midleft=(16, rep_y + 7))
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
        from src.controller import get_controller
        controller = get_controller()
        is_controller = controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller"

        # Label
        w_lbl = self.font_hint.render("Wallet", True, WHITE)
        screen.blit(w_lbl, w_lbl.get_rect(center=(wr.centerx, wr.top - 10)))
        # Key hint
        k_txt = "[X]" if is_controller else "[I]"
        k_lbl = self.font_hint.render(k_txt, True, WHITE)
        screen.blit(k_lbl, k_lbl.get_rect(center=(wr.centerx, wr.bottom + 10)))
        wallet_hover = wr.collidepoint(pygame.mouse.get_pos())
        if wallet_hover or hud_focus == "wallet":
            pygame.draw.rect(screen, (255, 220, 80), wr.inflate(6, 6), 2, border_radius=8)

        # ── phone icon (delegated to Phone.draw_hud_icon) ──
        # Drawn by game.py via self.phone.draw_hud_icon(screen, self.ui.phone_icon_rect, unread)
        # But we still draw the label + key-hint here for consistency
        pr = self.phone_icon_rect
        ph_lbl = self.font_hint.render("Phone", True, WHITE)
        screen.blit(ph_lbl, ph_lbl.get_rect(center=(pr.centerx, pr.top - 10)))
        ph_txt = "[LB]" if is_controller else "[P]"
        ph_key = self.font_hint.render(ph_txt, True, WHITE)
        screen.blit(ph_key, ph_key.get_rect(center=(pr.centerx, pr.bottom + 10)))
        phone_hover = pr.collidepoint(pygame.mouse.get_pos())
        if phone_hover or hud_focus == "phone":
            pygame.draw.rect(screen, (255, 220, 80), pr.inflate(6, 6), 2, border_radius=8)

    def draw_yearbook_view(self, screen: pygame.Surface, controller_connected: bool = False,
                          reputation_data: dict | None = None, npc_groups: dict | None = None,
                          selected_group: str = "Athletes", scroll_offset: int = 0):
        """Draw the yearbook view with social group stats and NPC relationships."""
        cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
        
        # Local helper for drawing premium progress bars
        def draw_stat_bar(s_surface, x, y, width, height, val, label, color):
            lbl_surf = self.font_hint.render(f"{label}: {val}", True, UI_TEXT_DIM)
            s_surface.blit(lbl_surf, (x, y))
            bar_rect = pygame.Rect(x, y + 14, width, height)
            pygame.draw.rect(s_surface, (25, 18, 12), bar_rect, border_radius=3)
            fill_w = int(width * max(0, min(100, val)) / 100)
            if fill_w > 0:
                pygame.draw.rect(s_surface, color, (bar_rect.x, bar_rect.y, fill_w, height), border_radius=3)
            pygame.draw.rect(s_surface, (80, 60, 40), bar_rect, 1, border_radius=3)

        # Main panel
        main_panel = pygame.Rect(cx - 600, cy - 300, 1200, 600)
        pygame.draw.rect(screen, (30, 20, 15), main_panel, border_radius=15)
        pygame.draw.rect(screen, (150, 110, 60), main_panel, 4, border_radius=15)
        
        # Title
        title = self.font_title.render("YEARBOOK - Social Statistics", True, UI_ACCENT)
        screen.blit(title, title.get_rect(center=(cx, main_panel.y + 30)))
        pygame.draw.line(screen, UI_ACCENT, (main_panel.x + 40, main_panel.y + 60), (main_panel.right - 40, main_panel.y + 60), 2)
        
        # Default data if not provided
        if reputation_data is None:
            reputation_data = {}
        if npc_groups is None:
            npc_groups = {}
        
        # Left panel: Social Group Stats
        left_panel = pygame.Rect(main_panel.x + 20, main_panel.y + 80, 280, main_panel.height - 100)
        pygame.draw.rect(screen, (50, 35, 25), left_panel, border_radius=10)
        pygame.draw.rect(screen, (100, 70, 40), left_panel, 2, border_radius=10)
        
        group_title = self.font_hud_lg.render("Group Rep", True, UI_ACCENT)
        screen.blit(group_title, (left_panel.x + 15, left_panel.y + 10))
        
        # Draw social groups and their reputation
        y_offset = left_panel.y + 45
        groups = ["Athletes", "Tech Club", "Populars", "Academics", "Rebels", "Outsiders"]
        for group_name in groups:
            btn_rect = pygame.Rect(left_panel.x + 10, y_offset - 6, left_panel.width - 20, 42)
            mouse_pos = pygame.mouse.get_pos()
            
            # Draw selection/hover state background
            if group_name == selected_group:
                pygame.draw.rect(screen, (80, 50, 25), btn_rect, border_radius=6)
                pygame.draw.rect(screen, UI_ACCENT, btn_rect, 2, border_radius=6)
                pygame.draw.circle(screen, UI_ACCENT, (btn_rect.x + 10, btn_rect.centery), 4)
                name_color = WHITE
            elif btn_rect.collidepoint(mouse_pos):
                pygame.draw.rect(screen, (60, 40, 22), btn_rect, border_radius=6)
                pygame.draw.rect(screen, (100, 75, 45), btn_rect, 1, border_radius=6)
                name_color = UI_TEXT
            else:
                name_color = UI_TEXT_DIM
            
            # Group name
            group_surf = self.font_hud_sm.render(group_name, True, name_color)
            x_text = left_panel.x + 22 if group_name == selected_group else left_panel.x + 15
            screen.blit(group_surf, (x_text, y_offset - 2))
            
            # Reputation bar
            rep_value = reputation_data.get(group_name.lower().replace(" ", "_"), 50)
            bar_width = 190
            bar_height = 8
            bar_rect = pygame.Rect(left_panel.x + 22 if group_name == selected_group else left_panel.x + 15, y_offset + 18, bar_width, bar_height)
            
            # Background
            pygame.draw.rect(screen, (30, 20, 15), bar_rect, border_radius=2)
            # Fill
            fill_w = int(bar_width * max(0, min(100, rep_value)) / 100)
            if fill_w > 0:
                pygame.draw.rect(screen, UI_ACCENT, (bar_rect.x, bar_rect.y, fill_w, bar_height), border_radius=2)
            pygame.draw.rect(screen, (80, 60, 40), bar_rect, 1, border_radius=2)
            
            # Value text
            val_surf = self.font_hint.render(f"{rep_value}", True, WHITE)
            screen.blit(val_surf, (bar_rect.right + 8, y_offset + 14))
            
            y_offset += 40
        
        # Right panel: NPCs by Group
        right_panel = pygame.Rect(left_panel.right + 20, main_panel.y + 80, main_panel.right - left_panel.right - 40, main_panel.height - 100)
        pygame.draw.rect(screen, (50, 35, 25), right_panel, border_radius=10)
        pygame.draw.rect(screen, (100, 70, 40), right_panel, 2, border_radius=10)
        
        npc_title = self.font_hud_lg.render(f"NPCs: {selected_group}", True, UI_ACCENT)
        screen.blit(npc_title, (right_panel.x + 15, right_panel.y + 10))
        
        # Get NPCs in selected group
        npcs = npc_groups.get(selected_group, [])
        max_scroll = max(0, len(npcs) - 4)
        scroll_offset = max(0, min(scroll_offset, max_scroll))
        
        # Draw scrollbar if there are more than 4 NPCs
        has_scroll = len(npcs) > 4
        if has_scroll:
            scrollbar_rect = pygame.Rect(right_panel.right - 14, right_panel.y + 50, 6, right_panel.height - 70)
            pygame.draw.rect(screen, (30, 20, 15), scrollbar_rect, border_radius=3)
            
            # Scroll handle
            visible_ratio = 4 / len(npcs)
            handle_height = max(25, int(scrollbar_rect.height * visible_ratio))
            scroll_ratio = scroll_offset / max_scroll
            handle_y = scrollbar_rect.y + int((scrollbar_rect.height - handle_height) * scroll_ratio)
            
            handle_rect = pygame.Rect(scrollbar_rect.x, handle_y, scrollbar_rect.width, handle_height)
            pygame.draw.rect(screen, UI_ACCENT, handle_rect, border_radius=3)
            pygame.draw.rect(screen, (180, 140, 90), handle_rect, 1, border_radius=3)

        # Slice NPCs to show only 4 at a time
        npcs_to_show = npcs[scroll_offset : scroll_offset + 4]
        y_offset = right_panel.y + 50
        
        if npcs_to_show:
            for npc_info in npcs_to_show:
                # Card Background Rect - adjust width if scrollbar exists
                card_w = right_panel.width - 30 - (15 if has_scroll else 0)
                card_rect = pygame.Rect(right_panel.x + 15, y_offset, card_w, 100)
                pygame.draw.rect(screen, (40, 28, 20), card_rect, border_radius=8)
                pygame.draw.rect(screen, (100, 75, 45), card_rect, 2, border_radius=8)
                
                # 1. Left Section: Name, Gender, Personality Mask
                name_text = self.font_hud_md.render(npc_info["name"], True, WHITE)
                screen.blit(name_text, (card_rect.x + 15, card_rect.y + 8))
                
                gender_str = npc_info.get("gender", "unspecified").title()
                gender_text = self.font_hint.render(f"Gender: {gender_str}", True, UI_TEXT_DIM)
                screen.blit(gender_text, (card_rect.x + 15, card_rect.y + 32))
                
                mask_revealed = npc_info.get("mask_revealed", False)
                if mask_revealed:
                    mask_label = self.font_hint.render("Personality: REVEALED", True, (100, 230, 100))
                    screen.blit(mask_label, (card_rect.x + 15, card_rect.y + 52))
                    
                    private_face = npc_info.get("private_personality", "Unknown")
                    face_desc = self.font_hint.render(f"Private Face: {private_face}", True, (180, 255, 180))
                    screen.blit(face_desc, (card_rect.x + 15, card_rect.y + 72))
                else:
                    mask_label = self.font_hint.render("Personality: MASKED", True, (220, 120, 120))
                    screen.blit(mask_label, (card_rect.x + 15, card_rect.y + 52))
                    
                    public_face = npc_info.get("public_personality", "Unknown")
                    face_desc = self.font_hint.render(f"Public Face: {public_face}", True, UI_TEXT_DIM)
                    screen.blit(face_desc, (card_rect.x + 15, card_rect.y + 72))
                
                # 2. Right Section: Progress Bars
                col_a_x = card_rect.x + (290 if has_scroll else 320)
                bar_w = 400 if has_scroll else 430
                bar_h = 12
                
                respect_val = npc_info.get("respect", 50)
                draw_stat_bar(screen, col_a_x, card_rect.y + 35, bar_w, bar_h, respect_val, "Reputation", (220, 180, 100))
                
                y_offset += 108
        else:
            placeholder = self.font_hud_md.render("No NPCs discovered in this group yet.", True, UI_TEXT_DIM)
            screen.blit(placeholder, (right_panel.x + 30, right_panel.y + 100))
            placeholder2 = self.font_hint.render("Talk to students around the school to expand your yearbook.", True, UI_TEXT_DIM)
            screen.blit(placeholder2, (right_panel.x + 30, right_panel.y + 130))
        
        # Return hint
        scroll_hint = " • Use Mouse Wheel or PageUp/Down to scroll" if len(npcs) > 4 else ""
        return_text = f"[B] Return to wallet{scroll_hint}" if controller_connected else f"Press ESC or click to return to wallet{scroll_hint}"
        hint_surface = self.font_hint.render(return_text, True, UI_ACCENT)
        screen.blit(hint_surface, hint_surface.get_rect(center=(cx, main_panel.bottom + 20)))

    def _bar(self, screen, x, y, w, h, cur, mx, fg, bg, label=""):
        """Utility: draw a filled bar with a label."""
        pygame.draw.rect(screen, bg, (x, y, w, h), border_radius=3)
        fill_w = int(w * max(0, cur) / max(1, mx))
        pygame.draw.rect(screen, fg, (x, y, fill_w, h), border_radius=3)
        pygame.draw.rect(screen, WHITE, (x, y, w, h), 1, border_radius=3)
        if label:
            lbl = self.font_hud_sm.render(f"{label} {int(cur)}/{int(mx)}", True, WHITE)
            screen.blit(lbl, (x + 6, y - 2))

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

    def draw_mission_select_menu(self, screen: pygame.Surface, sel: int, confirm: bool, confirm_sel: int, mission_list: list, mission_manager):
        """Semi-transparent mission select overlay."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))

        # Main Panel (adjusted dynamically to fit the missions text)
        line_h = 42
        start_y_offset = 110
        bottom_padding = 30
        ph = start_y_offset + len(mission_list) * line_h + bottom_padding
        pw = 960
        if ph > SCREEN_HEIGHT - 20:
            ph = SCREEN_HEIGHT - 20
        px = (SCREEN_WIDTH - pw) // 2
        py = (SCREEN_HEIGHT - ph) // 2
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((30, 30, 45, 230))
        pygame.draw.rect(panel, UI_ACCENT, panel.get_rect(), 3, border_radius=12)
        screen.blit(panel, (px, py))

        # Title
        title_surf = self.font_title.render("MISSION SELECT", True, UI_ACCENT)
        screen.blit(title_surf, title_surf.get_rect(center=(SCREEN_WIDTH // 2, py + 40)))

        # Subtitle
        sub_surf = self.font_hint.render("Select a mission to jump directly to it. Completed missions show [✓]", True, UI_TEXT_DIM)
        screen.blit(sub_surf, sub_surf.get_rect(center=(SCREEN_WIDTH // 2, py + 80)))

        # List missions
        start_y = py + 110
        line_h = 42
        for i, m_info in enumerate(mission_list):
            m_id = m_info[0]
            m_title = m_info[2]
            
            # Check completion status
            m_obj = mission_manager.missions.get(m_id)
            status_str = ""
            if m_obj:
                if m_obj.status.value == "completed":
                    status_str = "  [✓] Completed"
                elif m_obj.status.value == "active":
                    status_str = "  (Active)"

            col = UI_ACCENT if i == sel else UI_TEXT
            if i == sel:
                hl_rect = pygame.Rect(px + 30, start_y + i * line_h - 5, pw - 60, line_h)
                hl_surf = pygame.Surface(hl_rect.size, pygame.SRCALPHA)
                hl_surf.fill((100, 180, 255, 40))
                screen.blit(hl_surf, hl_rect)
                pygame.draw.rect(screen, UI_ACCENT, hl_rect, 1, border_radius=6)

            prefix = "► " if i == sel else "  "
            text_surf = self.font_menu.render(f"{prefix}{m_title}{status_str}", True, col)
            screen.blit(text_surf, (px + 50, start_y + i * line_h + 5))

        # Confirmation Box
        if confirm:
            cw, ch = 640, 260
            cx = (SCREEN_WIDTH - cw) // 2
            cy = (SCREEN_HEIGHT - ch) // 2
            conf_panel = pygame.Surface((cw, ch), pygame.SRCALPHA)
            conf_panel.fill((20, 20, 30, 250))
            pygame.draw.rect(conf_panel, (255, 100, 100), conf_panel.get_rect(), 3, border_radius=12)
            screen.blit(conf_panel, (cx, cy))

            q1 = self.font_menu.render("Are you sure you want to jump to this mission?", True, WHITE)
            q2 = self.font_hint.render("Previous progression and day will be adjusted.", True, (255, 150, 150))
            screen.blit(q1, q1.get_rect(center=(SCREEN_WIDTH // 2, cy + 50)))
            screen.blit(q2, q2.get_rect(center=(SCREEN_WIDTH // 2, cy + 100)))

            # Buttons
            btn_y = cy + 180
            yes_col = UI_ACCENT if confirm_sel == 0 else UI_TEXT_DIM
            no_col = UI_ACCENT if confirm_sel == 1 else UI_TEXT_DIM
            yes_prefix = "► " if confirm_sel == 0 else "  "
            no_prefix = "► " if confirm_sel == 1 else "  "

            yes_surf = self.font_menu.render(f"{yes_prefix}Yes, Jump", True, yes_col)
            no_surf = self.font_menu.render(f"{no_prefix}No, Cancel", True, no_col)

            screen.blit(yes_surf, yes_surf.get_rect(center=(SCREEN_WIDTH // 2 - 120, btn_y)))
            screen.blit(no_surf, no_surf.get_rect(center=(SCREEN_WIDTH // 2 + 120, btn_y)))

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
            ("Interact",     "E"),
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

    def draw_wallet(self, screen: pygame.Surface, active_item: str | None, character, 
                    controller_connected: bool = False, focus_item: str | None = None,
                    yearbook_data: dict | None = None, player=None, inventory=None):
        """Draw the wallet interface. Semi-transparent background."""
        from src.controller import get_controller
        controller = get_controller()
        controller_connected = controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller"

        money_val = player.money if player else 5
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
            elif self.wallet_yearbook_rect.collidepoint((mx, my)):
                mouse_item = "yearbook"
            elif self.wallet_cred_rect.collidepoint((mx, my)) and inventory and inventory.has_item("Hacked Credentials"):
                mouse_item = "cred"
            if mouse_item:
                highlight_item = mouse_item

            for key in ("id", "bill", "yearbook", "cred"):
                target = -24 if highlight_item == key else 0
                current = self._wallet_hover_offsets.get(key, 0.0)
                self._wallet_hover_offsets[key] = current + (target - current) * 0.25

            id_offset = int(round(self._wallet_hover_offsets["id"]))
            bill_offset = int(round(self._wallet_hover_offsets["bill"]))
            yearbook_offset = int(round(self._wallet_hover_offsets["yearbook"]))
            cred_offset = int(round(self._wallet_hover_offsets.get("cred", 0.0)))
            
            for i, sy in enumerate(slot_ys):
                # --- Left Side ---
                # Draw ID card before drawing its pocket cover (Slot 2 = index 1)
                if i == 1:
                    full_id_base = pygame.Rect(self.wallet_id_rect.x, self.wallet_id_rect.y, self.wallet_id_rect.width, 160)
                    full_id = full_id_base.move(0, id_offset)
                    pygame.draw.rect(screen, (215, 235, 255), full_id, border_radius=8)
                    pygame.draw.rect(screen, (120, 160, 220), full_id, 2, border_radius=8)
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
                    bill_title = self.font_hud_lg.render(f"${money_val}", True, (20, 60, 20))
                    screen.blit(bill_title, (full_bill.x + 10, full_bill.y + 6))
                    if highlight_item == "bill":
                        pygame.draw.rect(screen, UI_ACCENT, full_bill.inflate(6, 6), 2, border_radius=8)

                # --- Right Side Slot 3 ---
                if i == 2 and inventory and inventory.has_item("Hacked Credentials"):
                    full_cred_base = pygame.Rect(self.wallet_cred_rect.x, self.wallet_cred_rect.y, self.wallet_cred_rect.width, 160)
                    full_cred = full_cred_base.move(0, cred_offset)
                    pygame.draw.rect(screen, (240, 240, 245), full_cred, border_radius=4)
                    pygame.draw.rect(screen, (150, 150, 150), full_cred, 2, border_radius=4)
                    cred_title = self.font_hud_md.render("Hacked Credentials", True, (180, 40, 40))
                    screen.blit(cred_title, (full_cred.x + 10, full_cred.y + 12))
                    if highlight_item == "cred":
                        pygame.draw.rect(screen, UI_ACCENT, full_cred.inflate(6, 6), 2, border_radius=8)

                # Draw Right Pocket Cover
                pocket_rect_right = pygame.Rect(cx + 20, sy, 300, pocket_h)
                pygame.draw.rect(screen, (60, 30, 18), pocket_rect_right, border_radius=4)
                pygame.draw.rect(screen, (35, 18, 10), pocket_rect_right, 2, border_radius=4)
                pygame.draw.line(screen, (100, 50, 30), (pocket_rect_right.x + 5, pocket_rect_right.y + 4), (pocket_rect_right.right - 5, pocket_rect_right.y + 4), 1)

                # --- Left Side Slot 3 ---
                # Draw Yearbook before drawing its pocket cover (Slot 3 = index 2)
                if i == 2:
                    full_yearbook_base = pygame.Rect(self.wallet_yearbook_rect.x, self.wallet_yearbook_rect.y, self.wallet_yearbook_rect.width, 160)
                    full_yearbook = full_yearbook_base.move(0, yearbook_offset)
                    pygame.draw.rect(screen, (180, 140, 100), full_yearbook, border_radius=8)
                    pygame.draw.rect(screen, (120, 80, 40), full_yearbook, 2, border_radius=8)
                    yearbook_title = self.font_hud_md.render("Yearbook", True, (255, 250, 230))
                    screen.blit(yearbook_title, (full_yearbook.x + 10, full_yearbook.y + 12))
                    # Draw a small book icon decoration
                    pygame.draw.line(screen, (255, 250, 230), (full_yearbook.x + 20, full_yearbook.y + 40), (full_yearbook.x + 20, full_yearbook.bottom - 10), 2)
                    if highlight_item == "yearbook":
                        pygame.draw.rect(screen, UI_ACCENT, full_yearbook.inflate(6, 6), 2, border_radius=10)

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
                pygame.draw.rect(screen, (215, 235, 255), big_id, border_radius=12)
                pygame.draw.rect(screen, (120, 160, 220), big_id, 4, border_radius=12)
                
                # ID Header
                header = self.font_menu.render("Ravenside High - Student ID", True, (50, 50, 100))
                screen.blit(header, header.get_rect(center=(cx, big_id.y + 40)))
                pygame.draw.line(screen, (120, 160, 220), (big_id.x + 20, big_id.y + 70), (big_id.right - 20, big_id.y + 70), 3)
                
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
                    
                # Photo placeholder / Character Avatar
                photo_rect = pygame.Rect(big_id.right - 140, big_id.y + 100, 100, 130)
                cur_char = character if character else Character.AIDEN
                avatar_img = self.player_avatars.get(cur_char)
                if avatar_img:
                    scaled_av = pygame.transform.smoothscale(avatar_img, (photo_rect.width, photo_rect.height))
                    screen.blit(scaled_av, photo_rect)
                else:
                    pygame.draw.rect(screen, (180, 180, 190), photo_rect)
                pygame.draw.rect(screen, (100, 120, 160), photo_rect, 2)
                
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
                tl = self.font_title.render(str(money_val), True, (20, 60, 20))
                screen.blit(tl, (big_bill.x + 20, big_bill.y + 10))
                screen.blit(tl, (big_bill.right - 40, big_bill.y + 10))
                screen.blit(tl, (big_bill.x + 20, big_bill.bottom - 50))
                screen.blit(tl, (big_bill.right - 40, big_bill.bottom - 50))
                
                center_text = self.font_title.render(f"{money_val} DOLLARS", True, (40, 90, 40))
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

            elif active_item == "yearbook":
                # Call dedicated yearbook drawing method
                reputation_data = yearbook_data.get("reputation_data", {}) if yearbook_data else {}
                npc_groups = yearbook_data.get("npc_groups", {}) if yearbook_data else {}
                selected_group = yearbook_data.get("selected_group", "Athletes") if yearbook_data else "Athletes"
                scroll_offset = yearbook_data.get("scroll_offset", 0) if yearbook_data else 0
                self.draw_yearbook_view(screen, controller_connected, reputation_data, npc_groups, selected_group, scroll_offset)

            elif active_item == "cred":
                big_cred = pygame.Rect(cx - 250, cy - 150, 500, 300)
                pygame.draw.rect(screen, (245, 245, 250), big_cred, border_radius=8)
                pygame.draw.rect(screen, UI_ACCENT, big_cred, 4, border_radius=8)
                
                # Header
                header = self.font_menu.render("TECH LAB ADMIN - CREDENTIALS", True, (180, 40, 40))
                screen.blit(header, header.get_rect(center=(cx, big_cred.y + 40)))
                pygame.draw.line(screen, (180, 40, 40), (big_cred.x + 20, big_cred.y + 70), (big_cred.right - 20, big_cred.y + 70), 3)
                
                # Details (Username & Password)
                y_off = big_cred.y + 110
                details = [
                    "SYSTEM: Ravenside High School Mainframe",
                    "USERNAME: admin_techlab",
                    "PASSWORD: pWd_sMiLe_cLuB_99!",
                    "STATUS: ACTIVE (HACKED BY ALAN CHEN)",
                ]
                for d in details:
                    text = self.font_hud_md.render(d, True, BLACK)
                    screen.blit(text, (big_cred.x + 40, y_off))
                    y_off += 40

                return_text = "[B] Return to wallet" if controller_connected else "Press ESC or click to return to wallet"
                hint_surface = self.font_hint.render(return_text, True, UI_ACCENT)
                screen.blit(hint_surface, hint_surface.get_rect(center=(cx, big_cred.y - 40)))
                
                # Description panel
                desc_panel = pygame.Rect(big_cred.x + 30, big_cred.bottom + 20, big_cred.width - 60, 130)
                pygame.draw.rect(screen, (14, 14, 24), desc_panel, border_radius=18)
                pygame.draw.rect(screen, UI_ACCENT, desc_panel, 3, border_radius=18)

                title_bar = pygame.Rect(desc_panel.x + 18, desc_panel.y + 18, desc_panel.width - 36, 40)
                pygame.draw.rect(screen, (40, 60, 80), title_bar, border_radius=12)
                pygame.draw.rect(screen, UI_ACCENT, title_bar, 2, border_radius=12)
                desc_title = self.font_hud_md.render("Description", True, UI_ACCENT)
                screen.blit(desc_title, desc_title.get_rect(center=title_bar.center))

                body_text = "Hacked high school system credentials provided by Alan Chen."
                desc_body = self.font_hud_sm.render(body_text, True, UI_TEXT)
                screen.blit(desc_body, desc_body.get_rect(center=(desc_panel.centerx, title_bar.bottom + 32)))

            # Return hint rendered above the item (see blocks above)

    def draw_mainframe(self, screen: pygame.Surface, game):
        from src.controller import get_controller
        controller = get_controller()
        controller_connected = controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller"
        focus_idx = getattr(game, 'mainframe_focus_idx', 4)

        # 1. Background blur / darkening overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((10, 15, 25, 210))
        screen.blit(overlay, (0, 0))

        cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
        screen_type = getattr(game, 'mainframe_screen', 'login')

        if screen_type == "login":
            # Main Login Window
            panel = pygame.Rect(cx - 250, cy - 180, 500, 420)
            pygame.draw.rect(screen, (20, 25, 35), panel, border_radius=16)
            pygame.draw.rect(screen, (0, 180, 255), panel, 3, border_radius=16)

            # Header
            header = self.font_menu.render("Ravenside High School Mainframe", True, (0, 200, 255))
            screen.blit(header, header.get_rect(center=(cx, panel.y + 40)))
            pygame.draw.line(screen, (0, 180, 255), (panel.x + 30, panel.y + 75), (panel.right - 30, panel.y + 75), 2)

            # Subtitle / Status
            sub = self.font_hud_md.render("SECURE LOGIN REQUIRED", True, (180, 200, 220))
            screen.blit(sub, sub.get_rect(center=(cx, panel.y + 105)))

            # Username Field
            u_rect = pygame.Rect(cx - 150, cy - 40, 300, 40)
            u_active = getattr(game, 'mainframe_active_field', 'user') == 'user'
            pygame.draw.rect(screen, (10, 15, 25) if u_active else (30, 35, 45), u_rect, border_radius=8)
            pygame.draw.rect(screen, (0, 255, 255) if u_active else (100, 120, 140), u_rect, 2, border_radius=8)
            u_label = self.font_hud_sm.render("USERNAME", True, (120, 140, 160))
            screen.blit(u_label, (u_rect.x, u_rect.y - 22))
            u_text = self.font_hud_md.render(getattr(game, 'mainframe_user_input', ''), True, WHITE)
            screen.blit(u_text, (u_rect.x + 15, u_rect.y + 8))

            # Password Field
            p_rect = pygame.Rect(cx - 150, cy + 40, 300, 40)
            p_active = getattr(game, 'mainframe_active_field', 'user') == 'pass'
            pygame.draw.rect(screen, (10, 15, 25) if p_active else (30, 35, 45), p_rect, border_radius=8)
            pygame.draw.rect(screen, (0, 255, 255) if p_active else (100, 120, 140), p_rect, 2, border_radius=8)
            p_label = self.font_hud_sm.render("PASSWORD", True, (120, 140, 160))
            screen.blit(p_label, (p_rect.x, p_rect.y - 22))
            p_str = "*" * len(getattr(game, 'mainframe_pass_input', ''))
            p_text = self.font_hud_md.render(p_str, True, WHITE)
            screen.blit(p_text, (p_rect.x + 15, p_rect.y + 8))

            # Error message
            err = getattr(game, 'mainframe_error', '')
            if err:
                err_surf = self.font_hud_sm.render(err, True, (255, 80, 80))
                screen.blit(err_surf, err_surf.get_rect(center=(cx, cy + 85)))

            # Buttons: Login & Exit
            login_btn = pygame.Rect(cx - 150, cy + 110, 140, 45)
            pygame.draw.rect(screen, (0, 150, 220), login_btn, border_radius=8)
            l_lbl = self.font_hud_md.render("Login", True, WHITE)
            screen.blit(l_lbl, l_lbl.get_rect(center=login_btn.center))

            exit_btn = pygame.Rect(cx + 10, cy + 110, 140, 45)
            pygame.draw.rect(screen, (80, 90, 100), exit_btn, border_radius=8)
            e_lbl = self.font_hud_md.render("Exit", True, WHITE)
            screen.blit(e_lbl, e_lbl.get_rect(center=exit_btn.center))

            # Auto-Fill Button
            autofill_btn = pygame.Rect(cx - 150, cy + 170, 300, 35)
            pygame.draw.rect(screen, (40, 60, 80), autofill_btn, border_radius=8)
            pygame.draw.rect(screen, (0, 200, 255), autofill_btn, 1, border_radius=8)
            af_lbl = self.font_hud_sm.render("[Auto-Fill Hacked Credentials]", True, (0, 220, 255))
            screen.blit(af_lbl, af_lbl.get_rect(center=autofill_btn.center))

            # Controller focus highlight
            if controller_connected:
                focus_rects = [u_rect, p_rect, login_btn, exit_btn, autofill_btn]
                if 0 <= focus_idx < len(focus_rects):
                    pygame.draw.rect(screen, (0, 255, 255), focus_rects[focus_idx].inflate(6, 6), 2, border_radius=8)

            # Bottom Hint
            hint_txt = "Hint: [Auto-Fill] & Login" if controller_connected else "Hint: Enter Hacked Credentials (User: admin_techlab | Pass: pWd_sMiLe_cLuB_99!)"
            hint = self.font_hint.render(hint_txt, True, (150, 170, 190))
            screen.blit(hint, hint.get_rect(center=(cx, panel.bottom + 25)))

        elif screen_type == "desktop":
            # Simulated Windows Desktop Window
            panel = pygame.Rect(cx - 400, cy - 280, 800, 560)
            pygame.draw.rect(screen, (15, 40, 55), panel, border_radius=12)  # Desktop BG
            pygame.draw.rect(screen, (100, 150, 200), panel, 4, border_radius=12)

            # Taskbar at bottom
            taskbar = pygame.Rect(panel.x, panel.bottom - 45, panel.width, 45)
            pygame.draw.rect(screen, (10, 20, 30), taskbar, border_radius=12)
            start_btn = pygame.Rect(taskbar.x + 15, taskbar.y + 8, 80, 30)
            pygame.draw.rect(screen, (0, 120, 200), start_btn, border_radius=6)
            s_lbl = self.font_hud_sm.render("START", True, WHITE)
            screen.blit(s_lbl, s_lbl.get_rect(center=start_btn.center))
            time_lbl = self.font_hud_sm.render("14:32 PM", True, (180, 200, 220))
            screen.blit(time_lbl, (taskbar.right - 80, taskbar.y + 12))

            # Header / Prompt
            prompt = self.font_hud_md.render("MISSION OBJECTIVE: Open Mail and search the inbox for Eli's old email.", True, (0, 255, 200))
            screen.blit(prompt, prompt.get_rect(center=(cx, panel.y + 25)))

            # Desktop Icons: Mail, Files, Bin, Disconnect
            icons = [
                ("Mail (Unread)", pygame.Rect(cx - 240, cy - 150, 100, 100), (220, 60, 60)),
                ("System Files", pygame.Rect(cx - 100, cy - 150, 100, 100), (200, 180, 50)),
                ("Recycle Bin", pygame.Rect(cx + 40, cy - 150, 100, 100), (100, 120, 140)),
                ("Disconnect", pygame.Rect(cx + 180, cy - 150, 100, 100), (180, 40, 40)),
            ]
            for name, rect, col in icons:
                pygame.draw.rect(screen, col, pygame.Rect(rect.x + 20, rect.y + 15, 60, 50), border_radius=8)
                lbl = self.font_hud_sm.render(name, True, WHITE)
                screen.blit(lbl, lbl.get_rect(center=(rect.centerx, rect.bottom - 15)))

            # Controller focus highlight
            if controller_connected:
                focus_rects = [
                    pygame.Rect(cx - 240, cy - 150, 100, 100),
                    pygame.Rect(cx - 100, cy - 150, 100, 100),
                    pygame.Rect(cx + 40, cy - 150, 100, 100),
                    pygame.Rect(cx + 180, cy - 150, 100, 100),
                ]
                if 0 <= focus_idx < len(focus_rects):
                    pygame.draw.rect(screen, (0, 255, 255), focus_rects[focus_idx].inflate(6, 6), 3, border_radius=12)

        elif screen_type == "mail":
            # Mail Client Window
            panel = pygame.Rect(cx - 400, cy - 280, 800, 560)
            pygame.draw.rect(screen, (240, 245, 250), panel, border_radius=12) # Light Mail BG
            pygame.draw.rect(screen, (50, 70, 90), panel, 4, border_radius=12)

            # Top Mail Navbar
            navbar = pygame.Rect(panel.x, panel.y, panel.width, 50)
            pygame.draw.rect(screen, (40, 60, 80), navbar, border_radius=12)
            title = self.font_menu.render("Ravenside Mail Client - Inbox", True, WHITE)
            screen.blit(title, (navbar.x + 100, navbar.y + 12))

            # Back Button
            back_btn = pygame.Rect(cx - 380, cy - 230, 80, 35)
            pygame.draw.rect(screen, (100, 120, 140), back_btn, border_radius=6)
            b_lbl = self.font_hud_sm.render("< Desktop", True, WHITE)
            screen.blit(b_lbl, b_lbl.get_rect(center=back_btn.center))

            # Disconnect Button
            disc_btn = pygame.Rect(cx + 280, cy - 230, 100, 35)
            pygame.draw.rect(screen, (180, 50, 50), disc_btn, border_radius=6)
            d_lbl = self.font_hud_sm.render("Disconnect", True, WHITE)
            screen.blit(d_lbl, d_lbl.get_rect(center=disc_btn.center))

            # Left Sidebar
            sidebar = pygame.Rect(panel.x, panel.y + 50, 180, panel.height - 50)
            pygame.draw.rect(screen, (220, 225, 235), sidebar)
            folders = ["Inbox (1)", "Sent", "Drafts", "Archive", "Spam"]
            sy = sidebar.y + 20
            for f in folders:
                col = (0, 120, 200) if "Inbox" in f else (80, 90, 100)
                lbl = self.font_hud_md.render(f, True, col)
                screen.blit(lbl, (sidebar.x + 20, sy))
                sy += 40

            # Email List
            list_x = panel.x + 200
            list_y = panel.y + 70
            emails = [
                ("Principal Walsh", "Staff Meeting Agenda - Friday 3PM", False),
                ("Coach Davis", "Basketball Tournament Roster Updates", False),
                ("Eli", "Urgent: I saw them (Smile Club)", True),  # Target!
                ("IT Support", "Password Expiry Notice - Action Required", False),
            ]
            for sender, subj, is_target in emails:
                item_rect = pygame.Rect(list_x, list_y, 560, 50)
                bg_col = (255, 255, 200) if is_target else (255, 255, 255)
                pygame.draw.rect(screen, bg_col, item_rect, border_radius=6)
                pygame.draw.rect(screen, (200, 210, 220), item_rect, 1, border_radius=6)
                
                s_lbl = self.font_hud_md.render(sender, True, (180, 40, 40) if is_target else BLACK)
                subj_lbl = self.font_hud_sm.render(subj, True, (100, 20, 20) if is_target else (100, 100, 100))
                screen.blit(s_lbl, (item_rect.x + 15, item_rect.y + 5))
                screen.blit(subj_lbl, (item_rect.x + 15, item_rect.y + 26))
                
                if is_target:
                    hint_badge = self.font_hint.render("<< READ EMAIL" if controller_connected else "<< CLICK TO READ", True, (200, 50, 50))
                    screen.blit(hint_badge, (item_rect.right - 140, item_rect.y + 16))
                list_y += 60

            # Controller focus highlight
            if controller_connected:
                focus_rects = [
                    back_btn,
                    disc_btn,
                    pygame.Rect(cx - 200, panel.y + 190, 560, 50),  # Eli
                    pygame.Rect(cx - 200, panel.y + 70, 560, 50),   # Walsh
                    pygame.Rect(cx - 200, panel.y + 130, 560, 50),  # Davis
                    pygame.Rect(cx - 200, panel.y + 250, 560, 50),  # IT Support
                ]
                if 0 <= focus_idx < len(focus_rects):
                    pygame.draw.rect(screen, (0, 150, 255), focus_rects[focus_idx].inflate(4, 4), 2, border_radius=6)

            # Bottom objective prompt
            prompt = self.font_hud_sm.render("MISSION OBJECTIVE: Find and select Eli's email in the inbox list above.", True, (50, 100, 150))
            screen.blit(prompt, prompt.get_rect(center=(panel.x + 490, panel.bottom - 30)))

        elif screen_type == "mail_view":
            # Mail Client Window - View Email
            panel = pygame.Rect(cx - 400, cy - 280, 800, 560)
            pygame.draw.rect(screen, (240, 245, 250), panel, border_radius=12)
            pygame.draw.rect(screen, (50, 70, 90), panel, 4, border_radius=12)

            # Top Mail Navbar
            navbar = pygame.Rect(panel.x, panel.y, panel.width, 50)
            pygame.draw.rect(screen, (40, 60, 80), navbar, border_radius=12)
            title = self.font_menu.render("Ravenside Mail Client - Message View", True, WHITE)
            screen.blit(title, (navbar.x + 100, navbar.y + 12))

            # Back Button
            back_btn = pygame.Rect(cx - 380, cy - 230, 80, 35)
            pygame.draw.rect(screen, (100, 120, 140), back_btn, border_radius=6)
            b_lbl = self.font_hud_sm.render("< Inbox", True, WHITE)
            screen.blit(b_lbl, b_lbl.get_rect(center=back_btn.center))

            # Disconnect Button
            disc_btn = pygame.Rect(cx + 280, cy - 230, 100, 35)
            pygame.draw.rect(screen, (180, 50, 50), disc_btn, border_radius=6)
            d_lbl = self.font_hud_sm.render("Disconnect", True, WHITE)
            screen.blit(d_lbl, d_lbl.get_rect(center=disc_btn.center))

            # Email Header Info
            h_box = pygame.Rect(panel.x + 40, panel.y + 70, 720, 110)
            pygame.draw.rect(screen, WHITE, h_box, border_radius=8)
            pygame.draw.rect(screen, (200, 210, 220), h_box, 1, border_radius=8)

            headers = [
                "From: Eli <eli_student@ravenside.edu>",
                "To: Marcus Green <m_green@ravenside.edu>",
                "Subject: Urgent: I saw them (Smile Club)",
                "Date: October 14",
            ]
            hy = h_box.y + 10
            for h in headers:
                col = (180, 40, 40) if "Subject" in h else BLACK
                lbl = self.font_hud_sm.render(h, True, col)
                screen.blit(lbl, (h_box.x + 15, hy))
                hy += 24

            # Email Body
            body_box = pygame.Rect(panel.x + 40, panel.y + 195, 720, 240)
            pygame.draw.rect(screen, WHITE, body_box, border_radius=8)
            pygame.draw.rect(screen, (200, 210, 220), body_box, 1, border_radius=8)

            body_text = (
                "Marcus, I'm not crazy. I saw them last night in the basement. "
                "The masks, the robes... they call themselves the Smile Club. "
                "They are controlling everything in this school, even the faculty. "
                "I'm telling you everything before they find me. Don't trust anyone."
            )
            # Render wrapped text
            words = body_text.split()
            lines = []
            cur_line = ""
            for w in words:
                if self.font_hud_md.size(cur_line + w)[0] < body_box.width - 40:
                    cur_line += w + " "
                else:
                    lines.append(cur_line)
                    cur_line = w + " "
            if cur_line: lines.append(cur_line)

            ty = body_box.y + 20
            for l in lines:
                lbl = self.font_hud_md.render(l, True, (40, 40, 50))
                screen.blit(lbl, (body_box.x + 20, ty))
                ty += 32

            # Close Email Button
            close_btn = pygame.Rect(cx - 100, cy + 180, 200, 45)
            pygame.draw.rect(screen, (0, 120, 200), close_btn, border_radius=8)
            c_lbl = self.font_hud_md.render("Close Email", True, WHITE)
            screen.blit(c_lbl, c_lbl.get_rect(center=close_btn.center))

            # Controller focus highlight
            if controller_connected:
                focus_rects = [back_btn, disc_btn, close_btn]
                if 0 <= focus_idx < len(focus_rects):
                    pygame.draw.rect(screen, (0, 150, 255), focus_rects[focus_idx].inflate(4, 4), 2, border_radius=8)

            # Bottom prompt
            prompt = self.font_hud_sm.render("MISSION OBJECTIVE: Information acquired. Select Disconnect to exit the system.", True, (180, 40, 40))
            screen.blit(prompt, prompt.get_rect(center=(cx, panel.bottom - 25)))

        elif screen_type == "alarm":
            # Big Red Alarm Window
            panel = pygame.Rect(cx - 450, cy - 320, 900, 640)
            pygame.draw.rect(screen, (30, 10, 10), panel, border_radius=16)
            pygame.draw.rect(screen, (255, 50, 50), panel, 6, border_radius=16)

            # Warning Header
            w_font = pygame.font.Font(VT323_PATH, 56)
            header = w_font.render("WARNING: SECURITY BREACH DETECTED!", True, (255, 80, 80))
            screen.blit(header, header.get_rect(center=(cx, panel.y + 55)))
            pygame.draw.line(screen, (255, 50, 50), (panel.x + 50, panel.y + 90), (panel.right - 50, panel.y + 90), 3)

            # Smile Club Image
            if getattr(self, 'smile_club_img', None):
                img_rect = self.smile_club_img.get_rect(center=(cx, panel.y + 240))
                pygame.draw.rect(screen, (20, 5, 5), img_rect.inflate(16, 16), border_radius=12)
                pygame.draw.rect(screen, (255, 80, 80), img_rect.inflate(16, 16), 3, border_radius=12)
                screen.blit(self.smile_club_img, img_rect)

            # Alarm lines
            lines = [
                "SYSTEM ALARM: THE SMILE CLUB HAS TRACED YOUR CONNECTION.",
                "YOU HAVE BEEN DISCOVERED.",
                "PREPARE FOR WHAT IS COMING.",
            ]
            ly = panel.y + 425
            for l in lines:
                lbl = self.font_hud_lg.render(l, True, WHITE)
                screen.blit(lbl, lbl.get_rect(center=(cx, ly)))
                ly += 38

            # Acknowledge Button
            ack_btn = pygame.Rect(cx - 180, panel.bottom - 90, 360, 55)
            pygame.draw.rect(screen, (200, 40, 40), ack_btn, border_radius=12)
            pygame.draw.rect(screen, WHITE, ack_btn, 3, border_radius=12)
            a_lbl = self.font_menu.render("Acknowledge & Escape", True, WHITE)
            screen.blit(a_lbl, a_lbl.get_rect(center=ack_btn.center))

            # Controller focus highlight
            if controller_connected:
                pygame.draw.rect(screen, (255, 255, 255), ack_btn.inflate(6, 6), 2, border_radius=12)
