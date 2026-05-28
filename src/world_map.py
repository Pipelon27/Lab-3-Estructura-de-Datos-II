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
    NOTIF_INFO, NOTIF_WARNING, VT323_PATH)


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

        # Teleport confirmation
        self._confirm_teleport = False
        self._teleport_target  = None

        # Hover state
        self._hovered_room   = None
        self._tooltip_pos    = None

        # Player position (updated by Game each frame)
        self.player_floor    = FLOOR_1F
        self.player_x        = 0
        self.player_y        = 0
        
        # Remote player position (for co-op)
        self.remote_floor    = -1
        self.remote_x        = 0
        self.remote_y        = 0
        self.remote_name     = ""

        # Controller selection state
        self._room_order: list = []
        self._selected_room_index: int = -1
        self.teleport_requested = False


        # Fonts
        self._font_tab    = pygame.font.Font(VT323_PATH, 18)
        self._font_room   = pygame.font.Font(VT323_PATH, 11)
        self._font_tip_t  = pygame.font.Font(VT323_PATH, 16)
        self._font_tip    = pygame.font.Font(VT323_PATH, 14)
        self._font_header = pygame.font.Font(VT323_PATH, 28)

        self._centre_on_floor(self.current_tab)
        self._refresh_room_selection()
        # Optional named markers (e.g., NPCs) to show on the map: {name: (floor, x, y, color)}
        self._markers = {}

    def set_marker(self, name: str, floor_id: int, x: int, y: int, color=(200, 120, 40)):
        """Register or update a named marker to be drawn on the map."""
        self._markers[name] = (floor_id, x, y, color)

    def clear_marker(self, name: str):
        if name in self._markers:
            del self._markers[name]

    # ── public helpers ────────────────────────────────────────

    def set_player_pos(self, floor_id: int, x: int, y: int):
        self.player_floor = floor_id
        self.player_x     = x
        self.player_y     = y

    def set_remote_player_pos(self, floor_id: int, x: int, y: int, name: str):
        self.remote_floor = floor_id
        self.remote_x     = x
        self.remote_y     = y
        self.remote_name  = name

    def reset_teleport_state(self):
        """Clear any pending teleport confirmation/selection."""
        self._confirm_teleport = False
        self._teleport_target = None
        self.teleport_requested = False

    # ── event handling ────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Process input. Return True if the map should close."""
        if event.type == pygame.KEYDOWN:
            from settings import KEY_MAP, KEY_PAUSE
            if self._confirm_teleport:
                if event.key == pygame.K_SPACE:
                    self.teleport_requested = True
                    self.teleport_floor = self._teleport_target[0]
                    self.teleport_pos = (self._teleport_target[1], self._teleport_target[2])
                    self._confirm_teleport = False
                    return True
                elif event.key == pygame.K_ESCAPE:
                    self.reset_teleport_state()
                    return False
            else:
                if event.key in (KEY_MAP, KEY_PAUSE):
                    return True

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # Check tab clicks
                tab = self._tab_at(event.pos)
                if tab is not None:
                    self.current_tab = tab
                    self._centre_on_floor(tab)
                    self.reset_teleport_state()
                    self._refresh_room_selection(reset_index=True)
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
                if self._dragging:
                    self._dragging = False
                    dx = abs(event.pos[0] - self._drag_start[0])
                    dy = abs(event.pos[1] - self._drag_start[1])
                    if dx < 5 and dy < 5 and not self._confirm_teleport:
                        wx, wy = self._screen_to_world(*event.pos)
                        target_tab = self.current_tab
                        tx, ty = wx, wy
                        
                        # Special case: Redirect clicks on Campus buildings to their interiors
                        if self.current_tab == 0 and self._hovered_room:
                            rid = self._hovered_room.id
                            if rid == "c_coliseum":
                                target_tab = self.school_map.FLOOR_COLISEUM_INTERIOR
                                tx, ty = 900, 1100 # Default interior spawn
                            elif rid == "c_tennis":
                                target_tab = self.school_map.FLOOR_PINGPONG_INTERIOR
                                tx, ty = 650, 900 # Default interior spawn
                            elif rid == "c_building":
                                target_tab = 0 # Campus
                                tx, ty = 2000, 2100 # In front of Main Building
                        
                        self._teleport_target = (target_tab, tx, ty)
                        self._confirm_teleport = True
                        self.teleport_requested = False
                        return False

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

    def handle_controller(self, controller) -> bool:
        """Process controller input. Return True if the map should close."""
        if controller is None or not controller.connected:
            return False

        # Teleport confirmation prompt takes priority
        if self._confirm_teleport:
            if controller.is_confirm_pressed():
                if self._teleport_target:
                    self.teleport_requested = True
                    self.teleport_floor = self._teleport_target[0]
                    self.teleport_pos = (self._teleport_target[1], self._teleport_target[2])
                    self._confirm_teleport = False
                    return True
            elif controller.is_cancel_pressed():
                self.reset_teleport_state()
            return False

        # Floor tab navigation with LB/RB
        if controller.is_block_pressed():
            self._change_tab(1)
        elif controller.is_attack_pressed():
            self._change_tab(-1)

        # Room selection via D-pad
        menu_dir = controller.get_menu_direction()
        if menu_dir == -1:
            self._move_room_selection(-1)
        elif menu_dir == 1:
            self._move_room_selection(1)

        # Confirm selection
        if controller.is_confirm_pressed() and self._teleport_target:
            self._confirm_teleport = True
            self.teleport_requested = False

        if controller.is_cancel_pressed():
            self.reset_teleport_state()
            return True

        return False

    # ── drawing ───────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, controller_connected: bool = False):
        """Render the map viewer overlay."""
        from src.controller import get_controller
        controller = get_controller()
        controller_connected = controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller"

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
        if not self._confirm_teleport:
            self._draw_tooltip(screen)

        # Controls hint
        if controller_connected:
            hint_text = "LB/RB: floors   D-Pad: select room   A: teleport   B: cancel   View: close"
        else:
            hint_text = "Click: Teleport   Drag: pan   Scroll: zoom   Click tabs to switch   M / ESC: close"
        hint = self._font_room.render(hint_text, True, UI_TEXT_DIM)
        screen.blit(hint, (12, SCREEN_HEIGHT - 20))

        if self._confirm_teleport:
            self._draw_teleport_confirm(screen, controller_connected)

    # ── internal ──────────────────────────────────────────────

    def _centre_on_floor(self, floor_id: int):
        """Reset offset so the floor is centred on screen."""
        w, h = FLOOR_SIZES.get(floor_id, (3200, 2400))
        map_y0 = self.TAB_HEIGHT + 4
        avail_h = SCREEN_HEIGHT - map_y0
        self.offset_x = (SCREEN_WIDTH - w * self.zoom) / 2
        self.offset_y = map_y0 + (avail_h - h * self.zoom) / 2

    def _refresh_room_selection(self, reset_index: bool = False):
        """Rebuild the list of rooms for controller navigation."""
        floor = self.school_map.get_floor(self.current_tab)
        if not floor:
            self._room_order = []
            self._selected_room_index = -1
            if not self._confirm_teleport:
                self._hovered_room = None
            self._teleport_target = None
            return

        rooms = list(floor.rooms.values())
        rooms.sort(key=lambda r: (r.rect.centery, r.rect.centerx))
        self._room_order = rooms

        if not rooms:
            self._selected_room_index = -1
            if not self._confirm_teleport:
                self._hovered_room = None
            self._teleport_target = None
            return

        if reset_index:
            self._selected_room_index = -1
            self._hovered_room = None
            self._tooltip_pos = None
            self._teleport_target = None
            return
        if not (0 <= self._selected_room_index < len(rooms)):
            self._selected_room_index = 0

        self._hovered_room = rooms[self._selected_room_index]
        self._set_tooltip_to_room(self._hovered_room)
        cx, cy = self._hovered_room.rect.center
        self._teleport_target = (self.current_tab, cx, cy)

    def _change_tab(self, delta: int):
        n = len(FLOOR_NAMES)
        self.current_tab = (self.current_tab + delta) % n
        self._centre_on_floor(self.current_tab)
        self.reset_teleport_state()
        self._refresh_room_selection(reset_index=True)

    def _move_room_selection(self, step: int):
        if not self._room_order:
            return
        self._selected_room_index = (self._selected_room_index + step) % len(self._room_order)
        room = self._room_order[self._selected_room_index]
        self._hovered_room = room
        # Pre-select teleport target at room centre for quick confirm
        cx, cy = room.rect.center
        self._teleport_target = (self.current_tab, cx, cy)
        self._set_tooltip_to_room(room)

    def _set_tooltip_to_room(self, room):
        if not room:
            self._tooltip_pos = None
            return
        sx, sy = self._world_to_screen(room.rect.centerx, room.rect.centery)
        self._tooltip_pos = (sx, sy)

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
            self._tooltip_pos = None
            return
        wx, wy = self._screen_to_world(pos[0], pos[1])
        self._hovered_room = floor.get_room_at(wx, wy)
        self._tooltip_pos = pos

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

        # Room fills (staircases last so they draw on top)
        for room in sorted(floor.rooms.values(), key=lambda r: r.is_staircase):
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
                lx, ly = rx + 4, ry + 4
                if not room.is_staircase:
                    for other in floor.rooms.values():
                        if other.is_staircase and other.rect.collidepoint(
                                room.rect.x + 8, room.rect.y + 8):
                            _, sbot = self._world_to_screen(0, other.rect.bottom + 4)
                            ly = sbot
                            break
                if room.id == "f1_women_bath":
                    stair = floor.rooms.get("f1_stairs_2f")
                    if stair:
                        lx, ly = self._world_to_screen(stair.rect.right + 12,
                                                       room.rect.y + 12)
                screen.blit(lbl, (lx, ly))
                if room.locked:
                    lock = self._font_room.render("🔒", True, (220, 60, 60))
                    screen.blit(lock, (rx + 4, ry + 18))

        # Walls
        for wall in floor.walls:
            wx, wy = self._world_to_screen(wall.x, wall.y)
            ww = max(1, int(wall.width * z))
            wh = max(1, int(wall.height * z))
            wall_rect = pygame.Rect(wx, wy, ww, wh)
            pygame.draw.rect(screen, (90, 90, 100), wall_rect)

        door_col = (200, 200, 230)
        for door in getattr(floor, "doors", []):
            dx, dy = self._world_to_screen(door.rect.x, door.rect.y)
            dw = max(1, int(door.rect.width * z))
            dh = max(1, int(door.rect.height * z))
            colour = door.color or door_col
            pygame.draw.rect(screen, colour, (dx, dy, dw, dh))
            pygame.draw.rect(screen, (50, 50, 60), (dx, dy, dw, dh), 1)
            # Locked door indicator on world map
            if door.locked:
                pygame.draw.line(screen, (200, 50, 50), (dx, dy), (dx + dw, dy + dh), 1)
                pygame.draw.line(screen, (200, 50, 50), (dx + dw, dy), (dx, dy + dh), 1)

        # Transitions removed from map as requested
        pass

        # Player indicator
        if self.current_tab == self.player_floor:
            px, py = self._world_to_screen(self.player_x, self.player_y)
            r = max(4, int(8 * z * 3))
            pygame.draw.circle(screen, (255, 220, 60), (px, py), r)
            pygame.draw.circle(screen, WHITE, (px, py), r, 2)
            you = self._font_room.render("YOU", True, (255, 220, 60))
            screen.blit(you, you.get_rect(center=(px, py - r - 8)))

        # Remote player indicator
        if self.remote_floor == self.current_tab:
            rx, ry = self._world_to_screen(self.remote_x, self.remote_y)
            r = max(4, int(8 * z * 3))
            # Use character-specific color (pink for Lena, blue for Aiden)
            # We'll use a generic bright color for now or try to match
            col = (255, 100, 255) if "lena" in self.remote_name.lower() else (100, 150, 255)
            pygame.draw.circle(screen, col, (rx, ry), r)
            pygame.draw.circle(screen, WHITE, (rx, ry), r, 2)
            lbl = self._font_room.render(self.remote_name.upper(), True, col)
            screen.blit(lbl, lbl.get_rect(center=(rx, ry - r - 8)))

        # Draw any markers (e.g., Oscar) if they are on this floor
        for name, (mfloor, mx, my, mcol) in self._markers.items():
            if mfloor != self.current_tab:
                continue
            sx, sy = self._world_to_screen(mx, my)
            mr = max(3, int(6 * z * 3))
            
            if name.lower() in ("car", "school bus"):
                cw = max(24, int(60 * z))
                ch = max(12, int(24 * z))
                cx = sx - cw // 2
                cy = sy - ch // 2
                # Try to load and display the bus sprite
                import os
                sprite_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    "data", "tiles", "ME_Singles_Vehicles_32x32_Bus_Left_1.png"
                )
                try:
                    if not hasattr(self, '_bus_sprite_cache'):
                        self._bus_sprite_cache = pygame.image.load(sprite_path).convert_alpha()
                    bus_sprite = self._bus_sprite_cache
                    scaled_sprite = pygame.transform.scale(bus_sprite, (cw, ch))
                    screen.blit(scaled_sprite, (cx, cy))
                except Exception:
                    # Fallback: draw yellow bus if sprite not found
                    bus_yellow = (250, 160, 30)
                    pygame.draw.rect(screen, bus_yellow, (cx, cy, cw, ch), border_radius=2)
                    pygame.draw.rect(screen, (20, 20, 20), (cx + 2, cy + ch * 0.2, cw - 4, 2))
                    pygame.draw.rect(screen, (20, 20, 20), (cx + 2, cy + ch * 0.8, cw - 4, 2))
                # Windows (black rect down the middle)
                pygame.draw.rect(screen, (40, 60, 80), (cx + 4, cy + ch * 0.4, cw - 8, ch * 0.2))
                # Wheels
                pygame.draw.rect(screen, (30, 30, 30), (cx + cw*0.15, cy - 2, cw*0.15, 4))
                pygame.draw.rect(screen, (30, 30, 30), (cx + cw*0.7, cy - 2, cw*0.15, 4))
                pygame.draw.rect(screen, (30, 30, 30), (cx + cw*0.15, cy + ch - 2, cw*0.15, 4))
                pygame.draw.rect(screen, (30, 30, 30), (cx + cw*0.7, cy + ch - 2, cw*0.15, 4))
            elif name.lower() == "fountain":
                # Draw fountain icon (figure only, no name)
                import math, time
                t = time.time()
                fz = max(8, int(18 * z))  # fountain size
                # Base pool
                pygame.draw.circle(screen, (80, 120, 140), (sx, sy), fz)
                pygame.draw.circle(screen, (120, 180, 200), (sx, sy), fz, 2)
                # Water spout (animated height)
                spout_h = int(fz * 0.6 + math.sin(t * 3) * fz * 0.15)
                pygame.draw.rect(screen, (150, 210, 240), (sx - fz//4, sy - spout_h - fz//3, fz//2, spout_h))
                # Top water burst
                pygame.draw.circle(screen, (180, 230, 255), (sx, sy - spout_h - fz//3), fz//3)
                # Skip name label for fountain
                continue
            else:
                pygame.draw.circle(screen, mcol, (sx, sy), mr)
                pygame.draw.circle(screen, WHITE, (sx, sy), mr, 1)
            lbl = self._font_room.render(name.replace('_', ' ').upper(), True, mcol)
            screen.blit(lbl, lbl.get_rect(center=(sx, sy - mr - 8)))

    # ── tooltip drawing ───────────────────────────────────────

    def _draw_tooltip(self, screen):
        room = self._hovered_room
        if not room:
            return
        if self._tooltip_pos:
            mx, my = self._tooltip_pos
        else:
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

    # ── teleport confirm drawing ──────────────────────────────

    def _draw_teleport_confirm(self, screen, controller_connected: bool = False):
        box_w, box_h = 400, 160
        bx = (SCREEN_WIDTH - box_w) // 2
        by = (SCREEN_HEIGHT - box_h) // 2

        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))

        pygame.draw.rect(screen, UI_PANEL, (bx, by, box_w, box_h), border_radius=8)
        pygame.draw.rect(screen, UI_ACCENT, (bx, by, box_w, box_h), 2, border_radius=8)

        title = self._font_tip_t.render("Teleport to this zone?", True, WHITE)
        screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, by + 40)))

        if controller_connected:
            hint1 = self._font_tip.render("Press A to confirm", True, (100, 200, 100))
            hint2 = self._font_tip.render("Press B to cancel", True, (220, 100, 100))
        else:
            hint1 = self._font_tip.render("Press SPACE to confirm", True, (100, 200, 100))
            hint2 = self._font_tip.render("Press ESC to cancel", True, (220, 100, 100))

        screen.blit(hint1, hint1.get_rect(center=(SCREEN_WIDTH // 2, by + 90)))
        screen.blit(hint2, hint2.get_rect(center=(SCREEN_WIDTH // 2, by + 120)))
