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
    NOTIF_SUCCESS, NOTIF_ERROR,
)


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
        self._npc_line = ""  # NPC dialogue line
        
        # Animation state
        self._anim_timer = 0.0
        self._anim_duration = 0.2  # seconds
        
        # Layout constants
        self.bottom_panel_height = 230
        self.right_panel_width = int(SCREEN_WIDTH * 0.18)
        self.bottom_panel_y = SCREEN_HEIGHT - self.bottom_panel_height - 90
        self.right_panel_x = SCREEN_WIDTH - self.right_panel_width
        
        self._option_rects = []
        self._phase = "CHOOSING"
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
        if self._visible and self._npc == npc and self._phase == "CHOOSING":
            return  # Already showing (prevent spam)
        
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
        """Switch the UI to the response phase."""
        self._phase = "NPC_RESPONSE"
        self._response_text = text
        self._response_deltas = deltas

    def hide(self):
        """Hide the UI (with fade-out animation)."""
        self._visible = False
        self._npc = None
        self._options = []
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
            print("[SocialUI] Invalid bottom panel dimensions")
            return
        
        # Slide in from bottom
        y_offset = int((1.0 - progress) * panel_height * 0.5)
        panel_y = self.bottom_panel_y + y_offset
        
        # Panel background
        panel_rect = pygame.Rect(10, panel_y, panel_width - 10, panel_height - 10)
        if hasattr(screen, 'get_rect'):
            panel_rect.clamp_ip(screen.get_rect())
            
        panel_surf = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel_surf, (*UI_PANEL, int(210 * progress)), panel_surf.get_rect(), border_radius=8)
        pygame.draw.rect(panel_surf, UI_BORDER, panel_surf.get_rect(), 2, border_radius=8)
        screen.blit(panel_surf, panel_rect)

        # NPC name at top
        font_name = pygame.font.SysFont("arial", 16, bold=True)
        name_text = font_name.render(f"[ {self._npc.name.upper()} ]", True, UI_ACCENT)
        screen.blit(name_text, (20, panel_y + 12))

        # NPC dialogue line
        font_line = pygame.font.SysFont("arial", 13)
        line_text = font_line.render(self._npc_line if hasattr(self, '_npc_line') else "...", 
                                     True, UI_TEXT)
        # Wrap text to fit panel width
        max_width = panel_width - 40
        wrapped_lines = self._wrap_text(line_text.get_text() if hasattr(line_text, 'get_text') 
                                        else str(self._npc.name), font_line, max_width)
        
        line_y = panel_y + 40
        for wrapped_line in wrapped_lines[:2]:  # Max 2 lines
            line_surf = font_line.render(wrapped_line, True, UI_TEXT_DIM)
            screen.blit(line_surf, (20, line_y))
            line_y += 20

        # Options or Response
        self._option_rects.clear()
        
        if self._phase == "CHOOSING":
            option_start_y = panel_rect.y + 92
            option_spacing = 30
            option_x = panel_rect.x + 10
            
            for idx, opt in enumerate(self._options[:3]):
                option_y = option_start_y + (idx * option_spacing)
                self._draw_option_button(screen, idx, opt, option_x, option_y, 
                                        progress, panel_rect.width - 20)
        else:
            # Draw NPC Response
            response_y = panel_rect.y + 100
            font_resp = pygame.font.SysFont("arial", 18, italic=True)
            max_text_width = panel_rect.width - 80
            resp_lines = self._wrap_text(f'"{self._response_text}"', font_resp, max_text_width)
            
            for r_line in resp_lines:
                r_surf = font_resp.render(r_line, True, UI_TEXT)
                screen.blit(r_surf, (panel_rect.x + 20, response_y))
                response_y += 24
                
            # Draw deltas at the bottom if any
            if self._response_deltas:
                delta_y = panel_rect.bottom - 35
                delta_x = panel_rect.x + 20
                for d in self._response_deltas:
                    color = NOTIF_SUCCESS if d.delta > 0 else NOTIF_ERROR
                    sign = "+" if d.delta > 0 else ""
                    dt_surf = pygame.font.SysFont("arial", 14, bold=True).render(
                        f"{sign}{d.delta} {d.group.upper()}", True, color
                    )
                    screen.blit(dt_surf, (delta_x, delta_y))
                    delta_x += dt_surf.get_width() + 15

    def _draw_option_button(self, screen: pygame.Surface, idx: int, opt: dict,
                           x: int, y: int, progress: float, width: int):
        """Draw a single option button with delta preview."""
        is_selected = (idx == self._selected_idx)
        
        # Button background
        btn_height = 28
        if width <= 0 or btn_height <= 0:
            return
            
        btn_rect = pygame.Rect(x, y, width, btn_height)
        
        bg_color = UI_ACCENT if is_selected else UI_PANEL
        btn_surf = pygame.Surface(btn_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn_surf, (*bg_color, int(200 * progress)), btn_surf.get_rect(), 
                        border_radius=4)
        screen.blit(btn_surf, btn_rect)
        self._option_rects.append(btn_rect)

        # Cursor (►) if selected
        cursor = " ► " if is_selected else "   "
        
        # Label
        font = pygame.font.SysFont("arial", 16, bold=is_selected)
        label_text = f"{cursor}{opt['label']}"
        max_text_width = width - 80
        
        # Simple truncation if too long (to keep on one line)
        if font.size(label_text)[0] > max_text_width:
            while font.size(label_text + "...")[0] > max_text_width and len(label_text) > 5:
                label_text = label_text[:-1]
            label_text += "..."
            
        label_surf = font.render(label_text, True, UI_TEXT)
        screen.blit(label_surf, (x + 6, y + 6))

        # Deltas preview (right side of button, muted)
        if opt.get("deltas"):
            deltas_text = " | ".join([
                f"+{d.delta}" if d.delta > 0 else str(d.delta)
                for d in opt["deltas"][:2]  # Show first 2 deltas
            ])
            deltas_surf = pygame.font.SysFont("arial", 10).render(deltas_text, True, UI_TEXT_DIM)
            screen.blit(deltas_surf, (x + width - deltas_surf.get_width() - 10, y + 6))

    def _draw_right_panel(self, screen: pygame.Surface, progress: float):
        """Draw the NPC profile panel on the right."""
        panel_width = self.right_panel_width
        panel_height = int(SCREEN_HEIGHT * 0.4)
        
        if panel_width <= 0 or panel_height <= 0:
            print("[SocialUI] Invalid right panel dimensions")
            return
            
        panel_y = SCREEN_HEIGHT - panel_height
        
        # Fade in from right
        alpha = max(0, min(255, int(210 * progress)))
        panel_rect = pygame.Rect(self.right_panel_x, panel_y, panel_width - 10, panel_height - 10)
        if hasattr(screen, 'get_rect'):
            panel_rect.clamp_ip(screen.get_rect())
            
        panel_surf = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel_surf, (*UI_PANEL, alpha), panel_surf.get_rect(), border_radius=8)
        pygame.draw.rect(panel_surf, UI_BORDER, panel_surf.get_rect(), 2, border_radius=8)
        screen.blit(panel_surf, panel_rect)

        # NPC name header
        font_header = pygame.font.SysFont("arial", 12, bold=True)
        name_surf = font_header.render(self._npc.name[:14], True, UI_ACCENT)
        screen.blit(name_surf, (self.right_panel_x + 8, panel_y + 8))

        # Group label
        group_label = f"[{self._npc.group.value.upper()}]"
        group_surf = pygame.font.SysFont("arial", 10).render(group_label, True, UI_TEXT_DIM)
        screen.blit(group_surf, (self.right_panel_x + 8, panel_y + 24))

        # Metrics
        font_metric = pygame.font.SysFont("arial", 10)
        metrics_y = panel_y + 44
        
        # Respect
        respect_text = f"Respect: {self._npc.relationship}"
        respect_surf = font_metric.render(respect_text, True, UI_TEXT)
        screen.blit(respect_surf, (self.right_panel_x + 8, metrics_y))
        
        # Trust
        trust_text = f"Trust:   {self._npc.npc_trust}"
        trust_surf = font_metric.render(trust_text, True, UI_TEXT)
        screen.blit(trust_surf, (self.right_panel_x + 8, metrics_y + 18))
        
        # Fear
        fear_text = f"Fear:    {self._npc.npc_fear}"
        fear_color = NOTIF_ERROR if self._npc.npc_fear > 50 else UI_TEXT
        fear_surf = font_metric.render(fear_text, True, fear_color)
        screen.blit(fear_surf, (self.right_panel_x + 8, metrics_y + 36))

        # Traits (if any)
        if self._npc.traits:
            traits_y = metrics_y + 60
            traits_label = font_metric.render("Traits:", True, UI_TEXT_DIM)
            screen.blit(traits_label, (self.right_panel_x + 8, traits_y))
            
            for tidx, trait in enumerate(self._npc.traits[:3]):  # Show up to 3 traits
                trait_surf = font_metric.render(f"• {trait}", True, UI_TEXT)
                screen.blit(trait_surf, (self.right_panel_x + 12, traits_y + 16 + tidx * 14))

        # Allied indicator
        if self._npc.is_allied:
            allied_surf = font_header.render("[ALLY]", True, NOTIF_SUCCESS)
            screen.blit(allied_surf, (self.right_panel_x + 8, panel_y + panel_height - 28))

    # ── ANIMATION & UTILITIES ──────────────────────────────

    def _ease_in_out(self, t: float) -> float:
        """Smooth easing function (cubic ease-in-out)."""
        if t < 0.5:
            return 4 * t * t * t
        else:
            t = 2 * t - 2
            return 0.5 * (t * t * t + 2)

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        """Wrap text to fit within max_width."""
        if len(text) <= 60:
            return [text]
        
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
        
        return lines

    def set_npc_line(self, line: str):
        """Update the NPC dialogue line (called from dialogue manager)."""
        self._npc_line = line
