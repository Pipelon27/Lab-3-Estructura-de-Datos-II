"""
main.py  —  Entry point for *Behind the Smile*
================================================
Initialises Pygame, presents the main menu, and launches the
selected game mode (solo / co-op host / co-op join).
Run from the project root:  ``python main.py``
"""

import pygame
import sys
import random
import string
import threading

from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE,
    UI_BG, UI_PANEL, UI_BORDER, UI_ACCENT,
    UI_TEXT, UI_TEXT_DIM, BLACK, WHITE,
    Character, GameState, VT323_PATH)
from src.controller import ControllerManager, init_controller
from src.phone import Phone
from network.server import GameServer
from network.client import GameClient
from network.discovery import discover_room


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
        self.font_title    = pygame.font.Font(VT323_PATH, 68)
        self.font_subtitle = pygame.font.Font(VT323_PATH, 22)
        self.font_option   = pygame.font.Font(VT323_PATH, 34)
        self.font_hint     = pygame.font.Font(VT323_PATH, 18)

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
class HostLobbyMenu:
    """Screen that generates a room code and waits for Player 2."""
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True
        self.server = None
        self.room_code = ''.join(random.choices(string.ascii_uppercase, k=3)) + ''.join(random.choices(string.digits, k=3))
        
        self.font_title = pygame.font.Font(VT323_PATH, 48)
        self.font_code = pygame.font.Font(VT323_PATH, 72)
        self.font_status = pygame.font.Font(VT323_PATH, 24)

    def run(self):
        self.server = GameServer(room_code=self.room_code)
        self.server.start()

        while self.running:
            self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.server.stop()
                    return None
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.server.stop()
                    return None
            
            if self.server.is_connected:
                pygame.time.wait(500) # give it a moment
                return self.server

            self.screen.fill(UI_BG)
            
            title = self.font_title.render("Host Co-op (Aiden)", True, WHITE)
            self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH//2, 150)))
            
            code_surf = self.font_code.render(self.room_code, True, UI_ACCENT)
            self.screen.blit(code_surf, code_surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 50)))
            
            dots = "." * ((pygame.time.get_ticks() // 500) % 4)
            status = self.font_status.render(f"Waiting for Player 2 - Lena to join{dots}", True, UI_TEXT_DIM)
            self.screen.blit(status, status.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 50)))
            
            hint = self.font_status.render("ESC to Cancel", True, UI_TEXT_DIM)
            self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT - 50)))

            pygame.display.flip()

        self.server.stop()
        return None

# ──────────────────────────────────────────────────────────────────
class JoinLobbyMenu:
    """Screen to enter a room code and connect to the host."""
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True
        self.client = None
        self.input_text = ""
        self.status_text = "Enter the 6-character room code:"
        self.searching = False
        
        self.font_title = pygame.font.Font(VT323_PATH, 48)
        self.font_input = pygame.font.Font(VT323_PATH, 72)
        self.font_status = pygame.font.Font(VT323_PATH, 24)

    def _discover_and_connect(self):
        ip_port = discover_room(self.input_text, timeout=5.0)
        if ip_port:
            ip, port = ip_port
            try:
                client = GameClient(host=ip, port=port)
                client.connect()
                self.client = client
            except Exception as e:
                self.status_text = f"Connection failed: {e}"
        else:
            self.status_text = "Room not found. Check code and try again."
        self.searching = False

    def run(self):
        while self.running:
            self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and len(self.input_text) == 6 and not self.searching:
                        self.searching = True
                        self.status_text = "Searching for room..."
                        threading.Thread(target=self._discover_and_connect, daemon=True).start()
                    elif event.key == pygame.K_BACKSPACE:
                        self.input_text = self.input_text[:-1]
                    elif event.unicode.isalnum() and len(self.input_text) < 6 and not self.searching:
                        self.input_text += event.unicode.upper()

            if self.client and self.client.is_connected:
                pygame.time.wait(500)
                return self.client

            self.screen.fill(UI_BG)
            
            title = self.font_title.render("Join Co-op (Lena)", True, WHITE)
            self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH//2, 150)))
            
            status = self.font_status.render(self.status_text, True, UI_TEXT_DIM if not self.status_text.startswith("Room not") else (255, 100, 100))
            self.screen.blit(status, status.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 80)))

            input_surf = self.font_input.render(self.input_text + ("_" if len(self.input_text) < 6 else ""), True, UI_ACCENT)
            self.screen.blit(input_surf, input_surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2)))
            
            hint_str = "ENTER to Join  |  ESC to Cancel" if not self.searching else "ESC to Cancel"
            hint = self.font_status.render(hint_str, True, UI_TEXT_DIM)
            self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT - 50)))

            pygame.display.flip()

        return None

# ──────────────────────────────────────────────────────────────────
def main():
    """Initialise Pygame, show the main menu, launch the game."""
    pygame.init()
    pygame.mixer.init()

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption(TITLE)

    mode_map = {
        0: dict(character=Character.AIDEN, multiplayer=False),
        1: dict(character=Character.LENA,  multiplayer=False),
        2: dict(character=Character.AIDEN, multiplayer=True,  is_host=True),
        3: dict(character=Character.LENA,  multiplayer=True,  is_host=False),
    }

    # Import Game lazily to avoid circular import at module load
    from src.game import Game

    while True:
        # Flush leftover input so button presses from the game don't carry over
        pygame.event.clear()
        pygame.time.wait(150)  # brief delay to let buttons release
        pygame.event.clear()

        menu = MainMenu(screen)
        choice = menu.run()

        # Quit requested
        if choice is None or choice == 4:
            break

        params = mode_map[choice]

        network_instance = None
        if choice == 2:  # Host Co-op
            lobby = HostLobbyMenu(screen)
            network_instance = lobby.run()
            if not network_instance:
                continue # User cancelled or failed
        elif choice == 3:  # Join Co-op
            lobby = JoinLobbyMenu(screen)
            network_instance = lobby.run()
            if not network_instance:
                continue # User cancelled or failed

        while True:
            game = Game(screen, network_instance=network_instance, **params)
            game.run()

            if game.return_to_menu:
                # Go back to the main menu loop
                break

            # Game finished normally or player chose Quit
            pygame.quit()
            sys.exit()

    pygame.quit()
    sys.exit()


# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
