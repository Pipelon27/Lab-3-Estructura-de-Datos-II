"""
src/hack.py  —  Lena's hacking mini-game
==========================================
Three mini-game variants, chosen by target type:

1. **Password Cracking**  – type the scrolling characters before they
   leave the screen (typing challenge).
2. **Security Override**  – match a pattern sequence that flashes briefly.
3. **Camera Control**     – simple camera-feed view (no puzzle, just info).

Difficulty scales with the target's ``difficulty`` value and Lena's
skill-tree bonuses.
"""

from __future__ import annotations

import random
import string
import pygame
from enum import Enum, auto
from settings import (
    UI_BG, UI_PANEL, UI_BORDER, UI_ACCENT,
    UI_TEXT, UI_TEXT_DIM, WHITE, BLACK,
    NOTIF_SUCCESS, NOTIF_ERROR, NOTIF_INFO,
    SCREEN_WIDTH, SCREEN_HEIGHT,
)


class HackPhase(Enum):
    INTRO      = auto()
    PLAYING    = auto()
    SUCCESS    = auto()
    FAILURE    = auto()


class HackingMinigame:
    """Full-screen hacking mini-game for Lena.

    Usage
    -----
    ``start(target_info, player)`` → ``handle_input(event)`` / ``update(dt)``
    → ``draw(screen)``  until result is returned by ``update()``.
    """

    # Character pool for password challenges
    CHARSET = string.ascii_uppercase + string.digits

    def __init__(self):
        self.active      = False
        self.phase       = HackPhase.INTRO
        self._result:  str | None = None    # "success" / "failure"

        # Target metadata
        self.target_info: dict = {}
        self.player      = None

        # Password cracking state
        self._sequence:    list[str]  = []
        self._input_buf:   str        = ""
        self._cursor:      int        = 0
        self._time_left:   float      = 0
        self._max_time:    float      = 0
        self._difficulty:  int        = 1

        # Security override state
        self._pattern:        list[int] = []
        self._pattern_display: float    = 0
        self._player_pattern: list[int] = []
        self._pattern_phase:  str       = "show"  # "show" / "input"
        self._pattern_len:    int       = 4

        # Intro timer
        self._intro_timer = 0.0

        # Visual
        self._scan_lines: list[str] = []

    # ── lifecycle ─────────────────────────────────────────────

    def start(self, target_info: dict, player):
        """Begin a hacking attempt on *target_info*.

        ``target_info`` keys: ``type`` (server / camera / npc_chat),
        ``difficulty`` (1–5), ``id``.
        """
        self.active      = True
        self.phase       = HackPhase.INTRO
        self._result     = None
        self.target_info = target_info
        self.player      = player

        self._difficulty = target_info.get("difficulty", 1)

        # Adjust for player skills
        time_bonus = getattr(player, "hack_time_bonus", 0)
        diff_red   = getattr(player, "hack_difficulty_reduction", 0)
        self._difficulty = max(1, self._difficulty - diff_red)

        hack_type = target_info.get("type", "server")

        if hack_type in ("server", "npc_chat"):
            self._setup_password_crack(time_bonus)
        elif hack_type == "camera":
            self._setup_camera_view()
        else:
            self._setup_password_crack(time_bonus)

        # Intro "booting" lines
        self._scan_lines = [
            f"> Connecting to {target_info.get('id', 'target')}…",
            f"> Difficulty level: {self._difficulty}",
            "> Initialising exploit payload…",
            "> ACCESS REQUIRED — BEGIN HACK",
        ]
        self._intro_timer = 2.0

    def _setup_password_crack(self, time_bonus: int):
        """Generate a random character sequence the player must type."""
        length = 4 + self._difficulty * 2
        self._sequence  = [random.choice(self.CHARSET) for _ in range(length)]
        self._input_buf = ""
        self._cursor    = 0
        self._max_time  = 8.0 + time_bonus + (5 - self._difficulty)
        self._time_left = self._max_time

    def _setup_camera_view(self):
        """Camera hack is simpler — just view a feed."""
        self._max_time  = 5.0
        self._time_left = self._max_time

    def _setup_override(self, time_bonus: int):
        """Pattern-matching override."""
        self._pattern_len = 3 + self._difficulty
        self._pattern = [random.randint(1, 4) for _ in range(self._pattern_len)]
        self._player_pattern = []
        self._pattern_display = 3.0
        self._pattern_phase = "show"
        self._max_time  = 10.0 + time_bonus
        self._time_left = self._max_time

    # ── input ─────────────────────────────────────────────────

    def handle_input(self, event: pygame.event.Event):
        if event.type != pygame.KEYDOWN or not self.active:
            return

        if event.key == pygame.K_ESCAPE:
            self._finish("failure")
            return

        if self.phase == HackPhase.INTRO:
            return        # inputs ignored during intro

        if self.phase != HackPhase.PLAYING:
            return

        hack_type = self.target_info.get("type", "server")

        if hack_type in ("server", "npc_chat"):
            self._handle_password_input(event)
        elif hack_type == "camera":
            # Any key closes the camera view → success
            self._finish("success")

    def _handle_password_input(self, event: pygame.event.Event):
        """Match typed character against the current sequence position."""
        if event.unicode and event.unicode.upper() in self.CHARSET:
            char = event.unicode.upper()
            if self._cursor < len(self._sequence):
                if char == self._sequence[self._cursor]:
                    self._cursor += 1
                    self._input_buf += char
                    if self._cursor >= len(self._sequence):
                        self._finish("success")
                else:
                    # Wrong character — penalty
                    self._time_left -= 1.0
                    if self._time_left <= 0:
                        self._finish("failure")

    # ── update ────────────────────────────────────────────────

    def update(self, dt: float) -> str | None:
        """Tick the mini-game.  Returns ``"success"``/``"failure"``
        when complete, else ``None``."""
        if not self.active:
            return self._result

        if self.phase == HackPhase.INTRO:
            self._intro_timer -= dt
            if self._intro_timer <= 0:
                self.phase = HackPhase.PLAYING
            return None

        if self.phase == HackPhase.PLAYING:
            self._time_left -= dt
            if self._time_left <= 0:
                self._finish("failure")

        if self.phase in (HackPhase.SUCCESS, HackPhase.FAILURE):
            return self._result

        return None

    def _finish(self, result: str):
        self._result = result
        self.phase   = HackPhase.SUCCESS if result == "success" else HackPhase.FAILURE
        self.active  = False

    # ── drawing ───────────────────────────────────────────────

    def draw(self, screen: pygame.Surface):
        if not self.active and self._result is None:
            return

        screen.fill((10, 15, 10))    # terminal green-black

        font_big   = pygame.font.SysFont("consolas", 32, bold=True)
        font_med   = pygame.font.SysFont("consolas", 24)
        font_sm    = pygame.font.SysFont("consolas", 18)
        font_hint  = pygame.font.SysFont("consolas", 16)

        cx = SCREEN_WIDTH // 2

        # Header
        hdr = font_big.render("[ LENA — HACK MODULE ]", True, (0, 255, 100))
        screen.blit(hdr, hdr.get_rect(center=(cx, 35)))

        # Phase: INTRO
        if self.phase == HackPhase.INTRO:
            y = 100
            for i, line in enumerate(self._scan_lines):
                alpha = max(0, min(255, int(255 * (2.0 - self._intro_timer + i * 0.3))))
                colour = (0, min(255, 150 + alpha // 3), 0)
                screen.blit(font_sm.render(line, True, colour), (60, y))
                y += 28
            return

        hack_type = self.target_info.get("type", "server")

        # ── Timer bar ──
        bar_w, bar_h = 500, 16
        bx = cx - bar_w // 2
        by = 75
        pct = max(0, self._time_left / self._max_time)
        bar_col = (0, 200, 80) if pct > 0.3 else (220, 180, 0) if pct > 0.1 else (220, 50, 50)
        pygame.draw.rect(screen, (30, 30, 30), (bx, by, bar_w, bar_h), border_radius=4)
        pygame.draw.rect(screen, bar_col, (bx, by, int(bar_w * pct), bar_h), border_radius=4)
        screen.blit(font_sm.render(f"TIME: {self._time_left:.1f}s", True, WHITE), (bx, by - 22))

        # ── Password cracking ──
        if hack_type in ("server", "npc_chat"):
            self._draw_password(screen, font_big, font_med, font_sm, cx)
        elif hack_type == "camera":
            self._draw_camera_view(screen, font_med, font_sm, cx)

        # Controls
        screen.blit(font_hint.render(
            "Type the characters  |  ESC Abort", True, (0, 150, 0)),
            (cx - 160, SCREEN_HEIGHT - 35))

    def _draw_password(self, screen, font_big, font_med, font_sm, cx):
        """Draw the password-cracking challenge."""
        # Sequence display
        y = 200
        seq_text = "  ".join(self._sequence)
        screen.blit(font_sm.render("DECRYPT SEQUENCE:", True, (0, 200, 80)), (cx - 200, y))
        y += 35

        # Draw each character with highlight
        x_start = cx - len(self._sequence) * 20
        for i, ch in enumerate(self._sequence):
            if i < self._cursor:
                colour = NOTIF_SUCCESS             # already typed
                bg = (0, 60, 0)
            elif i == self._cursor:
                colour = WHITE                     # current target
                bg = (0, 80, 40)
            else:
                colour = (0, 120, 0)               # upcoming
                bg = (15, 25, 15)

            char_rect = pygame.Rect(x_start + i * 42, y, 38, 48)
            pygame.draw.rect(screen, bg, char_rect, border_radius=4)
            pygame.draw.rect(screen, colour, char_rect, 2, border_radius=4)
            surf = font_big.render(ch, True, colour)
            screen.blit(surf, surf.get_rect(center=char_rect.center))

        # Input feedback
        y += 80
        typed = " ".join(self._input_buf) if self._input_buf else "…"
        screen.blit(font_med.render(f"INPUT: {typed}", True, (0, 255, 100)), (cx - 200, y))

        # Progress
        y += 40
        prog = f"{self._cursor}/{len(self._sequence)}"
        screen.blit(font_sm.render(f"Progress: {prog}", True, (0, 180, 80)), (cx - 80, y))

    def _draw_camera_view(self, screen, font_med, font_sm, cx):
        """Draw a fake camera feed (placeholder)."""
        view = pygame.Rect(cx - 250, 150, 500, 350)
        pygame.draw.rect(screen, (20, 20, 20), view)
        pygame.draw.rect(screen, (0, 200, 80), view, 2)

        # Scan lines effect
        for y in range(view.top, view.bottom, 4):
            pygame.draw.line(screen, (0, 30, 0, 40), (view.left, y), (view.right, y))

        screen.blit(font_med.render("CAMERA FEED", True, (0, 200, 80)),
                    (cx - 80, view.top + 10))
        screen.blit(font_sm.render(
            f"Target: {self.target_info.get('id', '???')}", True, (0, 150, 0)),
            (view.left + 15, view.bottom - 30))
        screen.blit(font_sm.render("Press any key to log footage", True, (0, 150, 0)),
                    (cx - 150, view.bottom + 20))
