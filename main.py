"""
main.py  —  Entry point for *Behind the Smile*
================================================
Initialises Pygame, presents the main menu, and launches the
selected game mode (solo / co-op host / co-op join).
Run from the project root:  ``python main.py``
"""

import pygame
import sys

from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE,
    UI_BG, UI_PANEL, UI_BORDER, UI_ACCENT,
    UI_TEXT, UI_TEXT_DIM, BLACK, WHITE,
    Character, GameState,
)
from src.controller import ControllerManager, init_controller


# ──────────────────────────────────────────────────────────────────
class MainMenu:
    """Full-screen main menu with keyboard navigation."""

    OPTIONS = [
        "Solo Play  (Aiden)",
        "Solo Play  (Lena)",
        "Host Co-op  (Aiden)",
        "Join Co-op  (Lena)",
        "Quit",
    ]

    def __init__(self, screen: pygame.Surface):
        self.screen   = screen
        self.clock    = pygame.time.Clock()
        self.selected = 0
        self.running  = True
        self.result   = None          # index chosen, or None

        # Fonts — SysFont so it works everywhere out of the box
        self.font_title    = pygame.font.SysFont("arial", 68, bold=True)
        self.font_subtitle = pygame.font.SysFont("arial", 22)
        self.font_option   = pygame.font.SysFont("arial", 34)
        self.font_hint     = pygame.font.SysFont("arial", 18)

        # Simple pulsing animation for the selector
        self._pulse_timer = 0.0

        # Controller support
        self.controller = ControllerManager()

        # Background image for the menu
        self.menu_bg: pygame.Surface | None = None
        self.menu_bg_overlay: pygame.Surface | None = None
        self.menu_panel: pygame.Surface | None = None
        self.menu_panel_border: pygame.Surface | None = None
        self.subtitle_colour = (120, 210, 255)  # neon blue tone
        try:
            bg = pygame.image.load("assets/UI/menu_bg.png")
            if bg.get_alpha() is not None:
                bg = bg.convert_alpha()
            else:
                bg = bg.convert()
            self.menu_bg = pygame.transform.smoothscale(bg, (SCREEN_WIDTH, SCREEN_HEIGHT))
            fade_width = int(SCREEN_WIDTH * 0.55)
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            for x in range(fade_width):
                alpha = int(190 * (1 - x / fade_width))
                overlay.fill((0, 0, 0, alpha), pygame.Rect(x, 0, 1, SCREEN_HEIGHT))

            # blur left section using downscale-upscale technique for softer falloff
            gradient_section = overlay.subsurface((0, 0, fade_width, SCREEN_HEIGHT)).copy()
            small_size = (
                max(1, fade_width // 12),
                max(1, SCREEN_HEIGHT // 12),
            )
            gradient_section = pygame.transform.smoothscale(gradient_section, small_size)
            gradient_section = pygame.transform.smoothscale(gradient_section, (fade_width, SCREEN_HEIGHT))
            overlay.blit(gradient_section, (0, 0))

            self.menu_bg_overlay = overlay

            panel_width = int(SCREEN_WIDTH * 0.44)
            panel_height = max(260, SCREEN_HEIGHT - 140)
            panel_surface = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
            panel_rect = panel_surface.get_rect()
            panel_surface.fill((0, 0, 0, 0))
            panel_colour = (10, 18, 32, 205)
            pygame.draw.rect(panel_surface, panel_colour, panel_rect, border_radius=24)

            border_surface = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
            pygame.draw.rect(border_surface, (44, 104, 168, 130), border_surface.get_rect(), 2, border_radius=24)

            self.menu_panel = panel_surface
            self.menu_panel_border = border_surface
        except (pygame.error, FileNotFoundError):
            # Fallback to solid colour background if the image is missing
            self.menu_bg = None
            self.menu_bg_overlay = None
            self.menu_panel = None
            self.menu_panel_border = None

    # ── loop ──────────────────────────────────────────────────
    def run(self) -> int | None:
        """Run the menu loop.  Returns the option index or *None*."""
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self._pulse_timer += dt
            self.controller.update(dt)  # Update controller input
            self._handle_events()
            self._handle_controller()   # Process controller navigation
            self._draw()
        return self.result

    # ── controller input ────────────────────────────────────
    def _handle_controller(self):
        """Handle Xbox controller input for menu navigation.
        
        Uses D-pad (cruzeta) for navigation instead of right stick.
        """
        if not self.controller.connected:
            return

        # D-pad (cruzeta) for navigation
        menu_dir = self.controller.get_menu_direction()
        if menu_dir == -1:
            self.selected = (self.selected - 1) % len(self.OPTIONS)
        elif menu_dir == 1:
            self.selected = (self.selected + 1) % len(self.OPTIONS)

        # A button to select
        if self.controller.is_confirm_pressed():
            self.result  = self.selected
            self.running = False

        # B button to quit
        if self.controller.is_cancel_pressed():
            self.result  = None
            self.running = False

    # ── events ────────────────────────────────────────────────
    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.result  = None
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    self.selected = (self.selected - 1) % len(self.OPTIONS)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self.selected = (self.selected + 1) % len(self.OPTIONS)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.result  = self.selected
                    self.running = False
                elif event.key == pygame.K_ESCAPE:
                    self.result  = None
                    self.running = False

    # ── render ────────────────────────────────────────────────
    def _draw(self):
        if self.menu_bg:
            self.screen.blit(self.menu_bg, (0, 0))
            if self.menu_bg_overlay:
                self.screen.blit(self.menu_bg_overlay, (0, 0))
        else:
            self.screen.fill(UI_BG)

        cx = SCREEN_WIDTH // 2
        base_x = int(SCREEN_WIDTH * 0.18)

        if self.menu_panel:
            panel_rect = self.menu_panel.get_rect()
            panel_rect.topleft = (base_x - 110, 80)
            self.screen.blit(self.menu_panel, panel_rect)
            if self.menu_panel_border:
                self.screen.blit(self.menu_panel_border, panel_rect)

        # Subtitle retained for flavour
        subtitle = self.font_subtitle.render(
            "Uncover the truth behind Ravenside High", True, self.subtitle_colour
        )
        subtitle_rect = subtitle.get_rect(midleft=(base_x, 170))
        self.screen.blit(subtitle, subtitle_rect)

        # Decorative line (repositioned to align with left column)
        line_width = 340
        pygame.draw.line(
            self.screen,
            UI_BORDER,
            (base_x, 200),
            (base_x + line_width, 200),
            2,
        )

        # ── options ──
        start_y = 240
        for i, label in enumerate(self.OPTIONS):
            is_sel = (i == self.selected)
            colour = UI_ACCENT if is_sel else UI_TEXT

            # Pulsing arrow
            import math
            arrow = "►" if int(self._pulse_timer * 3) % 2 == 0 and is_sel else " "
            text  = f" {arrow}  {label}"

            surf = self.font_option.render(text, True, colour)
            rect = surf.get_rect(midleft=(base_x, start_y + i * 60))

            if is_sel:
                bg = rect.inflate(50, 12)
                pygame.draw.rect(self.screen, UI_PANEL, bg, border_radius=10)
                pygame.draw.rect(self.screen, UI_ACCENT, bg, 2, border_radius=10)

            self.screen.blit(surf, rect)

        # ── bottom hint ──
        hint_text = "↑ ↓  Navigate   |   ENTER  Select   |   ESC  Quit"
        if self.controller.connected:
            hint_text = "[D-Pad] Navigate  |  [A] Select  |  [B] Quit"
        hint = self.font_hint.render(hint_text, True, UI_TEXT_DIM)
        hint_y = SCREEN_HEIGHT - 40
        if self.menu_panel:
            hint_y = panel_rect.bottom - 30
        hint_rect = hint.get_rect(midleft=(base_x, hint_y))
        self.screen.blit(hint, hint_rect)

        pygame.display.flip()


# ──────────────────────────────────────────────────────────────────
def main():
    """Initialise Pygame, show the main menu, launch the game."""
    pygame.init()
    pygame.mixer.init()

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption(TITLE)

    menu   = MainMenu(screen)
    choice = menu.run()

    # Quit requested
    if choice is None or choice == 4:
        pygame.quit()
        sys.exit()

    # Import Game here (lazy) to avoid circular-import issues
    from src.game import Game

    mode_map = {
        0: dict(character=Character.AIDEN, multiplayer=False),
        1: dict(character=Character.LENA,  multiplayer=False),
        2: dict(character=Character.AIDEN, multiplayer=True,  is_host=True),
        3: dict(character=Character.LENA,  multiplayer=True,  is_host=False),
    }
    params = mode_map[choice]
    game = Game(screen, **params)
    game.run()

    pygame.quit()
    sys.exit()


# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
