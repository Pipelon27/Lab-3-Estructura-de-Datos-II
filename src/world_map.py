"""
src/world_map.py  —  Interactive map viewer (M key)
=====================================================
Full-screen overlay showing a floor-plan schematic.

Features
--------
* 4 floor tabs: Campus, 1st Floor, 2nd Floor, Basement
* Drag to pan the view
* Scroll to zoom in/out
* Hover over rooms to see name, description, mission tag
* Player position indicator
"""

from __future__ import annotations

import pygame
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    UI_BG, UI_PANEL, UI_BORDER, UI_ACCENT,
    UI_TEXT, UI_TEXT_DIM, WHITE, BLACK,
    FLOOR_NAMES, FLOOR_SIZES,
    FLOOR_CAMPUS, FLOOR_1F, FLOOR_2F, FLOOR_BASEMENT, FLOOR_ROOFTOP,
    NOTIF_INFO, NOTIF_WARNING,
)


class WorldMap:
    """Interactive map viewer toggled by the M key.

    The ``Game`` class creates one instance and delegates events
    and drawing when the state is ``GameState.MAP``.
    """

    TAB_HEIGHT   = 44
    TAB_WIDTH    = 130
    TOOLTIP_PAD  = 8
    ZOOM_MIN     = 0.08
    ZOOM_MAX     = 1.2
    ZOOM_STEP    = 0.05

    def __init__(self, school_map):
        self.school_map      = school_map
        self.current_tab     = FLOOR_1F     # start showing 1st floor
        self.offset_x: float = 0.0
        self.offset_y: float = 0.0
        self.zoom: float     = 0.22         # initial zoom scale

        self._dragging       = False
        self._drag_start     = (0, 0)
        self._drag_offset0   = (0.0, 0.0)

        # Hover state
        self._hovered_room   = None

        # Player position (updated by Game each frame)
        self.player_floor    = FLOOR_1F
        self.player_x        = 0
        self.player_y        = 0

        # Fonts
        self._font_tab    = pygame.font.SysFont("arial", 18, bold=True)
        self._font_room   = pygame.font.SysFont("arial", 11)
        self._font_tip_t  = pygame.font.SysFont("arial", 16, bold=True)
        self._font_tip    = pygame.font.SysFont("arial", 14)
        self._font_header = pygame.font.SysFont("arial", 28, bold=True)

        self._centre_on_floor(self.current_tab)

    # ── public helpers ────────────────────────────────────────

    def set_player_pos(self, floor_id: int, x: int, y: int):
        self.player_floor = floor_id
        self.player_x     = x
        self.player_y     = y

    # ── event handling ────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Process input. Return True if the map should close."""
        if event.type == pygame.KEYDOWN:
            from settings import KEY_MAP, KEY_PAUSE
            if event.key in (KEY_MAP, KEY_PAUSE):
                return True

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # Check tab clicks
                tab = self._tab_at(event.pos)
                if tab is not None:
                    self.current_tab = tab
                    self._centre_on_floor(tab)
                    return False
                # Start drag
                self._dragging     = True
                self._drag_start   = event.pos
                self._drag_offset0 = (self.offset_x, self.offset_y)
            elif event.button == 4:  # scroll up → zoom in
                self._zoom_at(event.pos, self.ZOOM_STEP)
            elif event.button == 5:  # scroll down → zoom out
                self._zoom_at(event.pos, -self.ZOOM_STEP)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self._dragging = False

        elif event.type == pygame.MOUSEMOTION:
            if self._dragging:
                dx = event.pos[0] - self._drag_start[0]
                dy = event.pos[1] - self._drag_start[1]
                self.offset_x = self._drag_offset0[0] + dx
                self.offset_y = self._drag_offset0[1] + dy
            # Hover detection
            self._update_hover(event.pos)

        elif event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            self._zoom_at((mx, my), event.y * self.ZOOM_STEP)

        return False

    # ── drawing ───────────────────────────────────────────────

    def draw(self, screen: pygame.Surface):
        """Render the map viewer overlay."""
        screen.fill(UI_BG)

        # Header
        header = self._font_header.render(
            f"SCHOOL MAP — {FLOOR_NAMES[self.current_tab]}", True, UI_ACCENT)
        screen.blit(header, header.get_rect(center=(SCREEN_WIDTH // 2, 24)))

        # Floor tabs
        self._draw_tabs(screen)

        # Clip area below tabs
        map_y0 = self.TAB_HEIGHT + 4
        clip = pygame.Rect(0, map_y0, SCREEN_WIDTH, SCREEN_HEIGHT - map_y0)
        screen.set_clip(clip)

        floor = self.school_map.get_floor(self.current_tab)
        if floor:
            self._draw_floor_plan(screen, floor, map_y0)

        screen.set_clip(None)

        # Tooltip (drawn on top, outside clip)
        self._draw_tooltip(screen)

        # Controls hint
        hint = self._font_room.render(
            "Drag: pan   Scroll: zoom   Click tabs to switch   M / ESC: close",
            True, UI_TEXT_DIM)
        screen.blit(hint, (12, SCREEN_HEIGHT - 20))

    # ── internal ──────────────────────────────────────────────

    def _centre_on_floor(self, floor_id: int):
        """Reset offset so the floor is centred on screen."""
        w, h = FLOOR_SIZES.get(floor_id, (3200, 2400))
        map_y0 = self.TAB_HEIGHT + 4
        avail_h = SCREEN_HEIGHT - map_y0
        self.offset_x = (SCREEN_WIDTH - w * self.zoom) / 2
        self.offset_y = map_y0 + (avail_h - h * self.zoom) / 2

    def _world_to_screen(self, wx, wy):
        sx = wx * self.zoom + self.offset_x
        sy = wy * self.zoom + self.offset_y
        return int(sx), int(sy)

    def _screen_to_world(self, sx, sy):
        wx = (sx - self.offset_x) / self.zoom
        wy = (sy - self.offset_y) / self.zoom
        return wx, wy

    def _zoom_at(self, screen_pos, delta):
        """Zoom centred on *screen_pos*."""
        old_zoom = self.zoom
        self.zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self.zoom + delta))
        ratio = self.zoom / old_zoom
        # Adjust offset so the point under the cursor stays fixed
        sx, sy = screen_pos
        self.offset_x = sx - (sx - self.offset_x) * ratio
        self.offset_y = sy - (sy - self.offset_y) * ratio

    def _tab_at(self, pos) -> int | None:
        n = len(FLOOR_NAMES)
        x0 = (SCREEN_WIDTH - n * self.TAB_WIDTH) // 2
        for i in range(n):
            tx = x0 + i * self.TAB_WIDTH
            if pygame.Rect(tx, 0, self.TAB_WIDTH, self.TAB_HEIGHT).collidepoint(pos):
                return i
        return None

    def _update_hover(self, pos):
        """Set _hovered_room based on mouse pos."""
        floor = self.school_map.get_floor(self.current_tab)
        if not floor:
            self._hovered_room = None
            return
        wx, wy = self._screen_to_world(pos[0], pos[1])
        self._hovered_room = floor.get_room_at(wx, wy)

    # ── tab drawing ───────────────────────────────────────────

    def _draw_tabs(self, screen):
        n = len(FLOOR_NAMES)
        x0 = (SCREEN_WIDTH - n * self.TAB_WIDTH) // 2
        labels = FLOOR_NAMES[:]

        for i, label in enumerate(labels):
            tx = x0 + i * self.TAB_WIDTH
            rect = pygame.Rect(tx, 0, self.TAB_WIDTH, self.TAB_HEIGHT)
            is_active = (i == self.current_tab)
            bg = UI_ACCENT if is_active else UI_PANEL
            fg = BLACK if is_active else UI_TEXT_DIM
            pygame.draw.rect(screen, bg, rect, border_radius=4)
            pygame.draw.rect(screen, UI_BORDER, rect, 1, border_radius=4)
            lbl = self._font_tab.render(label, True, fg)
            screen.blit(lbl, lbl.get_rect(center=rect.center))

    # ── floor plan drawing ────────────────────────────────────

    def _draw_floor_plan(self, screen, floor, map_y0):
        z = self.zoom

        # Floor outline
        fx, fy = self._world_to_screen(0, 0)
        fw = int(floor.width * z)
        fh = int(floor.height * z)
        pygame.draw.rect(screen, (25, 25, 32), (fx, fy, fw, fh))

        # Room fills
        for room in floor.rooms.values():
            rx, ry = self._world_to_screen(room.rect.x, room.rect.y)
            rw = int(room.rect.width * z)
            rh = int(room.rect.height * z)
            r = pygame.Rect(rx, ry, rw, rh)

            col = room.color
            if room is self._hovered_room:
                col = tuple(min(255, c + 40) for c in col)
            if room.locked:
                col = tuple(max(0, c - 15) for c in col)

            pygame.draw.rect(screen, col, r)
            pygame.draw.rect(screen, (80, 80, 90), r, 1)

            # Room label (only when zoomed in enough)
            if rw > 60 and rh > 24:
                lbl = self._font_room.render(room.name, True, (200, 200, 210))
                screen.blit(lbl, (rx + 4, ry + 4))
                if room.locked:
                    lock = self._font_room.render("🔒", True, (220, 60, 60))
                    screen.blit(lock, (rx + 4, ry + 18))

        # Walls
        wall_col = (90, 90, 100)
        for wall in floor.walls:
            wx, wy = self._world_to_screen(wall.x, wall.y)
            ww = max(1, int(wall.width * z))
            wh = max(1, int(wall.height * z))
            pygame.draw.rect(screen, wall_col, (wx, wy, ww, wh))

        # Transitions
        for tr in floor.transitions:
            tx, ty = self._world_to_screen(tr.rect.x, tr.rect.y)
            tw = max(4, int(tr.rect.width * z))
            th = max(4, int(tr.rect.height * z))
            col = (180, 60, 60) if tr.locked else (80, 180, 255)
            pygame.draw.rect(screen, col, (tx, ty, tw, th))
            if tw > 30:
                lbl = self._font_room.render(tr.label, True, WHITE)
                screen.blit(lbl, (tx + 2, ty - 14))

        # Player indicator
        if self.current_tab == self.player_floor:
            px, py = self._world_to_screen(self.player_x, self.player_y)
            r = max(4, int(8 * z * 3))
            pygame.draw.circle(screen, (255, 220, 60), (px, py), r)
            pygame.draw.circle(screen, WHITE, (px, py), r, 2)
            you = self._font_room.render("YOU", True, (255, 220, 60))
            screen.blit(you, you.get_rect(center=(px, py - r - 8)))

    # ── tooltip drawing ───────────────────────────────────────

    def _draw_tooltip(self, screen):
        room = self._hovered_room
        if not room:
            return
        mx, my = pygame.mouse.get_pos()

        lines = [room.name]
        lines.append(room.description)
        if room.mission_tag:
            lines.append(f"📋 {room.mission_tag}")
        if room.locked:
            lines.append("🔒 LOCKED")

        # Calculate size
        surfs = []
        max_w = 0
        for i, line in enumerate(lines):
            font = self._font_tip_t if i == 0 else self._font_tip
            col = UI_ACCENT if i == 0 else UI_TEXT
            if "🔒" in line:
                col = (220, 70, 70)
            elif "📋" in line:
                col = (100, 200, 100)
            s = font.render(line, True, col)
            surfs.append(s)
            max_w = max(max_w, s.get_width())

        p = self.TOOLTIP_PAD
        tw = max_w + p * 2
        th = sum(s.get_height() + 2 for s in surfs) + p * 2
        tx = min(mx + 16, SCREEN_WIDTH - tw - 4)
        ty = min(my + 16, SCREEN_HEIGHT - th - 4)

        # Background
        bg = pygame.Surface((tw, th), pygame.SRCALPHA)
        bg.fill((20, 20, 30, 230))
        screen.blit(bg, (tx, ty))
        pygame.draw.rect(screen, UI_BORDER, (tx, ty, tw, th), 1, border_radius=4)

        # Text
        cy = ty + p
        for s in surfs:
            screen.blit(s, (tx + p, cy))
            cy += s.get_height() + 2
