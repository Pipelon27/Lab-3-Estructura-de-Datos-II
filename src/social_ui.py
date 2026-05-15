"""
src/social_ui.py  —  Social interaction UI & animations
========================================================
Pure rendering layer for NPC interaction interface.
Handles layout, animations, and visual feedback for dialogue choices.
"""

from __future__ import annotations

import pygame
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    UI_BG, UI_PANEL, UI_BORDER, UI_ACCENT, UI_TEXT, UI_TEXT_DIM,
    NOTIF_SUCCESS, NOTIF_ERROR, GROUP_COLORS, VT323_PATH)


class SocialInteractionUI:
    """Renders the NPC interaction interface.

    Layout:
    - Bottom panel (18% of screen height): NPC line + 3 options
    - Right panel (18% of screen width): NPC profile + metrics

    Animations:
    - Bottom panel slides in from below (150ms ease)
    - Right panel fades in from right (200ms ease)
    """

    def __init__(self):
        self._visible = False
        self._npc = None
        self._options = []
        self._selected_idx = 0
        self._npc_line = ""      # NPC opening line
        self._reaction_line = "" # NPC reaction after choice

        # Animation state
        self._anim_timer = 0.0
        self._anim_duration = 0.2  # seconds

        # Layout constants
        self.bottom_panel_height = 240
        self.right_panel_width = int(SCREEN_WIDTH * 0.20)
        self.bottom_panel_y = SCREEN_HEIGHT - self.bottom_panel_height - 80
        self.right_panel_x = SCREEN_WIDTH - self.right_panel_width

        self._option_rects = []
        self._phase = "CHOOSING"      # "CHOOSING" or "NPC_RESPONSE"
        self._response_text = ""
        self._response_deltas = []

    # ── PUBLIC API ─────────────────────────────────────────────

    def get_clicked_option(self, mouse_pos: tuple[int, int]) -> int | None:
        """Return the index of the clicked option, or None if no collision."""
        for i, rect in enumerate(self._option_rects):
            if rect.collidepoint(mouse_pos):
                return i
        return None

    def show(self, npc, options_with_deltas: list[dict]):
        """Show the UI for an NPC interaction."""
        self._npc = npc
        self._options = options_with_deltas
        self._selected_idx = 0
        self._visible = True
        self._anim_timer = 0.0
        self._phase = "CHOOSING"
        self._response_text = ""
        self._response_deltas = []
        print(f"[SocialUI] Opening dialogue UI for {npc.name}")

    def show_response(self, text: str, deltas: list):
        """Switch the UI to the NPC reaction phase."""
        self._phase = "NPC_RESPONSE"
        self._response_text = text
        self._response_deltas = deltas

    def hide(self):
        """Hide the UI."""
        self._visible = False
        self._npc = None
        self._options = []
        self._npc_line = ""
        self._response_text = ""
        self._response_deltas = []
        print("[SocialUI] Dialogue UI closed")

    def set_selected(self, idx: int):
        """Update the currently selected option (0–2)."""
        self._selected_idx = max(0, min(len(self._options) - 1, idx))

    def update(self, dt: float):
        """Tick animation timers."""
        if self._visible and self._anim_timer < self._anim_duration:
            self._anim_timer += dt

    def draw(self, screen: pygame.Surface):
        """Main render call. Draw both panels."""
        if screen is None or not hasattr(screen, 'blit'):
            return

        if not self._visible or not self._npc:
            return

        # Animation progress (0.0 to 1.0, eased)
        raw_progress = self._anim_timer / self._anim_duration
        progress = max(0.0, min(1.0, float(raw_progress)))
        progress = self._ease_in_out(progress)

        self._draw_bottom_panel(screen, progress)
        self._draw_right_panel(screen, progress)

    # ── PRIVATE RENDERING ─────────────────────────────────────

    def _draw_bottom_panel(self, screen: pygame.Surface, progress: float):
        """Draw the dialogue options panel at the bottom."""
        panel_height = self.bottom_panel_height
        panel_width = SCREEN_WIDTH - self.right_panel_width - 10

        if panel_width <= 0 or panel_height <= 0:
            return

        # Slide in from bottom
        y_offset = int((1.0 - progress) * panel_height * 0.5)
        panel_y = self.bottom_panel_y + y_offset

        # Panel background
        panel_rect = pygame.Rect(10, panel_y, panel_width - 10, panel_height - 10)
        if hasattr(screen, 'get_rect'):
            panel_rect.clamp_ip(screen.get_rect())

        panel_surf = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel_surf, (*UI_PANEL, int(220 * progress)), panel_surf.get_rect(), border_radius=10)
        pygame.draw.rect(panel_surf, (*UI_BORDER, int(255 * progress)), panel_surf.get_rect(), 2, border_radius=10)
        screen.blit(panel_surf, panel_rect)

        # ── NPC name + group badge ──────────────────────────────
        font_name = pygame.font.Font(VT323_PATH, 22)
        name_surf = font_name.render(f"[ {self._npc.name.upper()} ]", True, UI_ACCENT)
        screen.blit(name_surf, (panel_rect.x + 14, panel_rect.y + 10))

        # Group badge (colored dot + group label)
        group_val = self._npc.group.value
        badge_color = GROUP_COLORS.get(group_val, (150, 150, 160))
        badge_x = panel_rect.x + 14 + name_surf.get_width() + 10
        badge_y = panel_rect.y + 14
        pygame.draw.circle(screen, badge_color, (badge_x + 5, badge_y + 8), 5)
        font_badge = pygame.font.Font(VT323_PATH, 14)
        badge_surf = font_badge.render(group_val.upper().replace("_", " "), True, badge_color)
        screen.blit(badge_surf, (badge_x + 14, badge_y + 2))

        # ── NPC opening line / reaction line ──────────────────
        font_line = pygame.font.Font(VT323_PATH, 18)
        display_line = self._response_text if self._phase == "NPC_RESPONSE" else self._npc_line

        if not display_line:
            display_line = "..."

        # Speech bubble style
        bubble_x = panel_rect.x + 14
        bubble_y = panel_rect.y + 38
        max_text_w = panel_rect.width - 28

        wrapped = self._wrap_text(f'"{display_line}"', font_line, max_text_w)
        for i, wline in enumerate(wrapped[:3]):
            color = UI_ACCENT if self._phase == "NPC_RESPONSE" else UI_TEXT
            lsurf = font_line.render(wline, True, color)
            screen.blit(lsurf, (bubble_x, bubble_y + i * 22))

        # ── Options or Reaction ────────────────────────────────
        self._option_rects.clear()

        if self._phase == "CHOOSING":
            option_start_y = panel_rect.y + 100
            option_spacing = 38
            option_x = panel_rect.x + 10

            for idx, opt in enumerate(self._options[:3]):
                option_y = option_start_y + (idx * option_spacing)
                self._draw_option_button(screen, idx, opt, option_x, option_y,
                                        progress, panel_rect.width - 20)

            # Keyboard hint
            hint_font = pygame.font.Font(VT323_PATH, 13)
            hint_surf = hint_font.render("[W/S] Navigate   [ENTER] or [CLICK] Confirm   [ESC] Cancel", True, UI_TEXT_DIM)
            screen.blit(hint_surf, (panel_rect.x + 10, panel_rect.bottom - 20))

        else:
            # NPC_RESPONSE phase — show reaction deltas + close hint
            delta_y = panel_rect.y + 115
            delta_x = panel_rect.x + 14

            if self._response_deltas:
                font_delta = pygame.font.Font(VT323_PATH, 15)
                for d in self._response_deltas:
                    # Fix: use d.subgroup (the correct attribute)
                    label = getattr(d, 'subgroup', '?')
                    stat  = getattr(d, 'stat', '')
                    val   = getattr(d, 'delta', 0)
                    color = NOTIF_SUCCESS if val > 0 else NOTIF_ERROR
                    sign  = "+" if val > 0 else ""
                    text  = f"{sign}{val} {label.upper()} {stat}"
                    dsurf = font_delta.render(text, True, color)
                    if delta_x + dsurf.get_width() + 10 > panel_rect.right - 10:
                        delta_x = panel_rect.x + 14
                        delta_y += 20
                    screen.blit(dsurf, (delta_x, delta_y))
                    delta_x += dsurf.get_width() + 18

            # Close hint
            hint_font = pygame.font.Font(VT323_PATH, 13)
            hint_surf = hint_font.render("[ENTER] or [CLICK] Continue   [ESC] Close", True, UI_TEXT_DIM)
            screen.blit(hint_surf, (panel_rect.x + 10, panel_rect.bottom - 20))

    def _draw_option_button(self, screen: pygame.Surface, idx: int, opt: dict,
                           x: int, y: int, progress: float, width: int):
        """Draw a single option button with delta preview."""
        is_selected = (idx == self._selected_idx)

        btn_height = 34
        if width <= 0 or btn_height <= 0:
            return

        btn_rect = pygame.Rect(x, y, width, btn_height)
        self._option_rects.append(btn_rect)

        # Background
        btn_surf = pygame.Surface(btn_rect.size, pygame.SRCALPHA)
        if is_selected:
            bg = (*UI_ACCENT, int(190 * progress))
            border = (*UI_ACCENT, 255)
        else:
            bg = (*UI_PANEL, int(160 * progress))
            border = (*UI_BORDER, int(180 * progress))
        pygame.draw.rect(btn_surf, bg, btn_surf.get_rect(), border_radius=6)
        pygame.draw.rect(btn_surf, border, btn_surf.get_rect(), 2, border_radius=6)
        screen.blit(btn_surf, btn_rect)

        # Cursor + label
        cursor = "► " if is_selected else "  "
        font = pygame.font.Font(VT323_PATH, 18)
        text_color = (10, 10, 20) if is_selected else UI_TEXT
        label_surf = font.render(f"{cursor}{opt['label']}", True, text_color)
        screen.blit(label_surf, (x + 8, y + 8))

        # Deltas preview (right side, muted)
        if opt.get("deltas"):
            primary_deltas = opt["deltas"][:2]
            parts = []
            for d in primary_deltas:
                val = getattr(d, 'delta', 0)
                label = getattr(d, 'subgroup', '?')
                sign = "+" if val > 0 else ""
                parts.append(f"{sign}{val} {label[:4].upper()}")
            deltas_text = "  ".join(parts)
            delta_font = pygame.font.Font(VT323_PATH, 12)
            d_color = UI_TEXT_DIM if not is_selected else (10, 10, 40)
            dsurf = delta_font.render(deltas_text, True, d_color)
            screen.blit(dsurf, (x + width - dsurf.get_width() - 10, y + 11))

    def _draw_right_panel(self, screen: pygame.Surface, progress: float):
        """Draw the NPC profile panel on the right."""
        panel_width = self.right_panel_width
        panel_height = int(SCREEN_HEIGHT * 0.42)

        if panel_width <= 0 or panel_height <= 0:
            return

        panel_y = SCREEN_HEIGHT - panel_height

        # Fade in
        alpha = max(0, min(255, int(220 * progress)))
        panel_rect = pygame.Rect(self.right_panel_x, panel_y, panel_width - 6, panel_height - 10)
        if hasattr(screen, 'get_rect'):
            panel_rect.clamp_ip(screen.get_rect())

        panel_surf = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel_surf, (*UI_PANEL, alpha), panel_surf.get_rect(), border_radius=10)
        pygame.draw.rect(panel_surf, (*UI_BORDER, alpha), panel_surf.get_rect(), 2, border_radius=10)
        screen.blit(panel_surf, panel_rect)

        px = panel_rect.x + 10
        py = panel_rect.y + 10

        # NPC name
        font_header = pygame.font.Font(VT323_PATH, 16)
        name_surf = font_header.render(self._npc.name[:16], True, UI_ACCENT)
        screen.blit(name_surf, (px, py))

        # Group label
        group_val = self._npc.group.value
        group_color = GROUP_COLORS.get(group_val, (150, 150, 160))
        group_surf = pygame.font.Font(VT323_PATH, 12).render(
            f"[{group_val.upper().replace('_',' ')}]", True, group_color)
        screen.blit(group_surf, (px, py + 20))

        # ── Stat bars ──────────────────────────────────────────
        font_metric = pygame.font.Font(VT323_PATH, 13)
        metrics_y = py + 42

        def draw_bar(label, value, bar_color, y_pos):
            lsurf = font_metric.render(f"{label}:", True, UI_TEXT_DIM)
            screen.blit(lsurf, (px, y_pos))
            bar_x = px + 58
            bar_w = panel_rect.width - 68
            bar_h = 8
            bar_bg = pygame.Rect(bar_x, y_pos + 3, bar_w, bar_h)
            pygame.draw.rect(screen, (40, 40, 60), bar_bg, border_radius=3)
            fill_w = int(bar_w * max(0, min(100, value)) / 100)
            if fill_w > 0:
                bar_fill = pygame.Rect(bar_x, y_pos + 3, fill_w, bar_h)
                pygame.draw.rect(screen, bar_color, bar_fill, border_radius=3)
            val_surf = font_metric.render(str(value), True, UI_TEXT)
            screen.blit(val_surf, (bar_x + bar_w + 4, y_pos))

        draw_bar("Rel",   self._npc.relationship, (80, 180, 255), metrics_y)
        draw_bar("Trust", self._npc.npc_trust,    (80, 220, 130), metrics_y + 20)
        fear_col = (220, 60, 60) if self._npc.npc_fear > 50 else (180, 100, 60)
        draw_bar("Fear",  self._npc.npc_fear,     fear_col,       metrics_y + 40)

        # Emotional state badge
        em_state = getattr(self._npc, 'emotional_state', 'neutral')
        em_colors = {
            "neutral": (150, 150, 170),
            "open":    (80, 220, 130),
            "nervous": (230, 180, 50),
            "hostile": (220, 60, 60),
        }
        em_color = em_colors.get(em_state, (150, 150, 170))
        em_surf = font_metric.render(f"Mood: {em_state.upper()}", True, em_color)
        screen.blit(em_surf, (px, metrics_y + 68))

        # Traits
        if self._npc.traits:
            traits_y = metrics_y + 88
            tl_surf = pygame.font.Font(VT323_PATH, 12).render("Traits:", True, UI_TEXT_DIM)
            screen.blit(tl_surf, (px, traits_y))
            for tidx, trait in enumerate(self._npc.traits[:3]):
                ts = pygame.font.Font(VT323_PATH, 12).render(f"• {trait}", True, UI_TEXT)
                screen.blit(ts, (px + 4, traits_y + 14 + tidx * 14))

        # Allied indicator
        if getattr(self._npc, 'is_allied', False):
            ally_surf = font_header.render("★ ALLY", True, (255, 215, 0))
            screen.blit(ally_surf, (px, panel_rect.bottom - 26))

    # ── ANIMATION & UTILITIES ──────────────────────────────

    def _ease_in_out(self, t: float) -> float:
        """Smooth easing function (cubic ease-in-out)."""
        if t < 0.5:
            return 4 * t * t * t
        else:
            t = 2 * t - 2
            return 0.5 * (t * t * t + 2)

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        """Wrap text to fit within max_width pixels."""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines if lines else [text]

    def set_npc_line(self, line: str):
        """Update the NPC opening dialogue line."""
        self._npc_line = line
