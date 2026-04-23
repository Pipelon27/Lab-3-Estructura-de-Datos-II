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

    # ── loop ──────────────────────────────────────────────────
    def run(self) -> int | None:
        """Run the menu loop.  Returns the option index or *None*."""
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self._pulse_timer += dt
            self._handle_events()
            self._draw()
        return self.result

    # ── events ────────────────────────────────────────────────
    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.result  = None
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    self.selected = (self.selected - 1) % len(self.OPTIONS)
                elif event.key == pygame.K_DOWN:
                    self.selected = (self.selected + 1) % len(self.OPTIONS)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.result  = self.selected
                    self.running = False
                elif event.key == pygame.K_ESCAPE:
                    self.result  = None
                    self.running = False

    # ── render ────────────────────────────────────────────────
    def _draw(self):
        self.screen.fill(UI_BG)

        cx = SCREEN_WIDTH // 2

        # ── title ──
        title = self.font_title.render("Behind the Smile", True, UI_ACCENT)
        self.screen.blit(title, title.get_rect(center=(cx, 130)))

        # ── subtitle ──
        sub = self.font_subtitle.render(
            "Uncover the truth behind Ravenside High", True, UI_TEXT_DIM
        )
        self.screen.blit(sub, sub.get_rect(center=(cx, 195)))

        # ── decorative line ──
        pygame.draw.line(
            self.screen, UI_BORDER,
            (cx - 220, 230), (cx + 220, 230), 2,
        )

        # ── options ──
        start_y = 290
        for i, label in enumerate(self.OPTIONS):
            is_sel = (i == self.selected)
            colour = UI_ACCENT if is_sel else UI_TEXT

            # Pulsing arrow
            import math
            arrow = "►" if int(self._pulse_timer * 3) % 2 == 0 and is_sel else " "
            text  = f" {arrow}  {label}"

            surf = self.font_option.render(text, True, colour)
            rect = surf.get_rect(center=(cx, start_y + i * 60))

            if is_sel:
                bg = rect.inflate(50, 12)
                pygame.draw.rect(self.screen, UI_PANEL, bg, border_radius=10)
                pygame.draw.rect(self.screen, UI_ACCENT, bg, 2, border_radius=10)

            self.screen.blit(surf, rect)

        # ── bottom hint ──
        hint = self.font_hint.render(
            "↑ ↓  Navigate   |   ENTER  Select   |   ESC  Quit",
            True, UI_TEXT_DIM,
        )
        self.screen.blit(hint, hint.get_rect(center=(cx, SCREEN_HEIGHT - 35)))

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
