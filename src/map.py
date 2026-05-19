"""
src/map.py  —  Multi-floor map with compact horizontal-U staircases
=====================================================================
Staircases: 500 × 280 px, horizontal centre wall, ~5 s U-turn.
Campus ↔ 1F uses portal transitions at the actual doorways.
All zones UNLOCKED for testing.
"""

from __future__ import annotations

import pygame
from collections import deque
from settings import (
    WALL_THICKNESS as WT, DOOR_WIDTH as DW,
    FLOOR_SIZES, FLOOR_BG_COLORS, FLOOR_NAMES,
    FLOOR_CAMPUS, FLOOR_1F, FLOOR_2F, FLOOR_BASEMENT, FLOOR_ROOFTOP,
    ZONE_NAMES, ZONE_CONNECTIONS,
    MEDIUM_GRAY, WHITE, BLACK, UI_TEXT_DIM, UI_ACCENT,
    Character, VT323_PATH)


# ══════════════════════════════════════════════════════════════
#  CUSTOM GRAPH
# ══════════════════════════════════════════════════════════════

class GraphNode:
    def __init__(self, node_id, data=None):
        self.id = node_id
        self.data = data
        self.neighbors: dict = {}
    def add_neighbor(self, nid, data=None):
        self.neighbors[nid] = data or {}
    def remove_neighbor(self, nid):
        self.neighbors.pop(nid, None)
    def get_neighbors(self):
        return list(self.neighbors)
    def has_neighbor(self, nid):
        return nid in self.neighbors
    def __repr__(self):
        return f"GraphNode({self.id}, nb={list(self.neighbors)})"


class Graph:
    def __init__(self, directed=False):
        self.nodes: dict = {}
        self.directed = directed
    def add_node(self, nid, data=None):
        if nid not in self.nodes:
            self.nodes[nid] = GraphNode(nid, data)
        return self.nodes[nid]
    def remove_node(self, nid):
        if nid not in self.nodes:
            return
        for n in self.nodes.values():
            n.remove_neighbor(nid)
        del self.nodes[nid]
    def get_node(self, nid):
        return self.nodes.get(nid)
    def get_all_node_ids(self):
        return list(self.nodes)
    def add_edge(self, a, b, data=None):
        self.add_node(a); self.add_node(b)
        self.nodes[a].add_neighbor(b, data)
        if not self.directed:
            self.nodes[b].add_neighbor(a, data)
    def remove_edge(self, a, b):
        if a in self.nodes: self.nodes[a].remove_neighbor(b)
        if not self.directed and b in self.nodes: self.nodes[b].remove_neighbor(a)
    def has_edge(self, a, b):
        n = self.nodes.get(a)
        return n.has_neighbor(b) if n else False
    def get_neighbors(self, nid):
        n = self.nodes.get(nid)
        return n.get_neighbors() if n else []
    def bfs(self, start, target):
        if start not in self.nodes or target not in self.nodes:
            return None
        visited = {start}
        q = [(start, [start])]
        while q:
            cur, path = q.pop(0)
            if cur == target:
                return path
            for nb in self.get_neighbors(cur):
                if nb not in visited:
                    visited.add(nb)
                    q.append((nb, path + [nb]))
        return None
    def dfs(self, start, visited=None):
        if visited is None:
            visited = set()
        visited.add(start)
        r = [start]
        for nb in self.get_neighbors(start):
            if nb not in visited:
                r.extend(self.dfs(nb, visited))
        return r
    def is_connected(self, a, b):
        return self.bfs(a, b) is not None
    def __repr__(self):
        return "Graph(" + ", ".join(
            f"{k}->{v.get_neighbors()}" for k, v in self.nodes.items()
        ) + ")"


# ══════════════════════════════════════════════════════════════
#  WALL HELPERS
# ══════════════════════════════════════════════════════════════

def _vwall_gaps(x, y0, y1, gaps):
    walls = []
    cy = y0
    for gy, gh in sorted(gaps):
        if gy > cy:
            walls.append(pygame.Rect(x, cy, WT, gy - cy))
        cy = gy + gh
    if cy < y1:
        walls.append(pygame.Rect(x, cy, WT, y1 - cy))
    return walls


def _door(rect, color=None):
    return (pygame.Rect(rect), color)

def _hwall_gaps(y, x0, x1, gaps):
    walls = []
    cx = x0
    for gx, gw in sorted(gaps):
        if gx > cx:
            walls.append(pygame.Rect(cx, y, gx - cx, WT))
        cx = gx + gw
    if cx < x1:
        walls.append(pygame.Rect(cx, y, x1 - cx, WT))
    return walls

def _hw(x, y, length):
    return pygame.Rect(x, y, length, WT)

def _vw(x, y, length):
    return pygame.Rect(x, y, WT, length)


def _add_furn(floor, rect, ftype=None, blocking=True, **kw):
    """Helper to register a furniture piece and (optionally) its collider."""
    item = {"rect": rect}
    if ftype:
        item["type"] = ftype
    if "color" not in kw and ftype is None:
        kw["color"] = (140, 140, 150)
    item.update(kw)
    floor.furniture.append(item)
    if blocking:
        floor.walls.append(rect)


# ══════════════════════════════════════════════════════════════
#  ROOM
# ══════════════════════════════════════════════════════════════

class Room:
    def __init__(self, room_id, name, description,
                 x, y, w, h, color,
                 locked=False, mission_tag=None,
                 is_staircase=False, tile_path=None):
        self.id          = room_id
        self.name        = name
        self.description = description
        self.rect        = pygame.Rect(x, y, w, h)
        self.color       = color
        self.locked      = locked
        self.mission_tag = mission_tag
        self.is_staircase = is_staircase
        self.tile_path   = tile_path   # Optional: path to a tile image
    def __repr__(self):
        return f"Room({self.id}, '{self.name}')"


# ══════════════════════════════════════════════════════════════
#  FLOOR TRANSITION  (portal-type)
# ══════════════════════════════════════════════════════════════

class FloorTransition:
    def __init__(self, rect, target_floor, spawn_x, spawn_y,
                 label="", locked=False):
        self.rect         = pygame.Rect(rect)
        self.target_floor = target_floor
        self.spawn_x      = spawn_x
        self.spawn_y      = spawn_y
        self.label        = label
        self.locked       = locked


# ══════════════════════════════════════════════════════════════
#  DOOR
# ══════════════════════════════════════════════════════════════

class Door:
    def __init__(self, door_id, x, y, w, h, is_vertical=False, locked=False, color=None):
        self.id = door_id
        self.rect = pygame.Rect(x, y, w, h)
        self.is_vertical = is_vertical
        self.locked = locked
        self.color = color or (180, 180, 205)
        self.open_ratio = 0.0
        self.swing_dir = 1
        self.close_timer = 0.0


# ══════════════════════════════════════════════════════════════
#  SEAMLESS STAIRCASE
# ══════════════════════════════════════════════════════════════

class SeamlessStaircase:
    def __init__(self, rect, transition_y, floor_above, floor_below):
        self.rect         = pygame.Rect(rect)
        self.transition_y = transition_y
        self.floor_above  = floor_above
        self.floor_below  = floor_below

    def check(self, player_cx, player_cy, current_floor):
        if not self.rect.collidepoint(player_cx, player_cy):
            return None
        margin = 8
        if current_floor == self.floor_below and player_cy < self.transition_y - margin:
            return self.floor_above
        if current_floor == self.floor_above and player_cy > self.transition_y + margin:
            return self.floor_below
        return None


# ══════════════════════════════════════════════════════════════
#  FLOOR
# ══════════════════════════════════════════════════════════════

class Floor:
    WALL_COLOR       = (70, 70, 80)
    WALL_TOP_COLOR   = (210, 212, 222)       # lighter top surface
    WALL_FACE_COLOR  = (128, 126, 120)
    WALL_SHADE_COLOR = (88, 82, 78)          # bottom face (slightly lighter for contrast)
    WALL_RIGHT_COLOR = (72, 68, 64)          # right face (darker = further from light)
    WALL_EDGE_COLOR  = (42, 40, 55)          # outline
    WALL_HILITE      = (245, 245, 255)       # top-left highlight
    WALL_DEPTH       = 14                    # base depth of the 3D extrusion
    TRANSITION_COLOR = (80, 160, 240)
    STAIR_STEP_A     = (55, 55, 68)
    STAIR_STEP_B     = (48, 48, 58)
    STAIR_ARROW_COL  = (210, 215, 235)
    STAIR_TREAD_LO   = (70, 70, 86)
    STAIR_TREAD_HI   = (158, 162, 184)
    STAIR_NOSING     = (220, 224, 244)
    STAIR_RISER      = (18, 18, 26)
    STAIR_RAIL       = (28, 28, 38)
    STAIR_RAIL_HI    = (130, 135, 155)

    def __init__(self, floor_id, name, width, height, bg_color):
        self.id       = floor_id
        self.name     = name
        self.width    = width
        self.height   = height
        self.bg_color = bg_color
        self.rooms:       dict[str, Room]       = {}
        self.walls:       list[pygame.Rect]     = []
        self.invisible_walls: list[pygame.Rect] = []
        self.transitions: list[FloorTransition] = []
        self.hackable_objects: list[dict]        = []
        self.doors:       list[Door]             = []
        self.furniture:   list[dict]             = []  # {"rect": Rect, "color": tuple, "outline": tuple|None}
        self.bg_tile_path = None
        self._tile_cache: dict[str, pygame.Surface] = {}  # path -> loaded Surface

    def add_room(self, room):
        self.rooms[room.id] = room

    def add_door(self, door: Door):
        self.doors.append(door)
        # If the door is locked, it should also act as a wall
        # We handle this in the Game class collision logic

    def get_room_at(self, x, y):
        for r in self.rooms.values():
            if r.rect.collidepoint(x, y):
                return r
        return None

    def _load_sprite(self, sprite_name):
        """Load a sprite by name from data/tiles or assets folders."""
        import os
        
        # Try data/tiles first
        data_tiles_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "tiles", sprite_name
        )
        if os.path.isfile(data_tiles_path):
            try:
                return pygame.image.load(data_tiles_path).convert_alpha()
            except Exception as e:
                print(f"Failed to load sprite {sprite_name} from {data_tiles_path}: {e}")
        
        # Try assets folders
        asset_base = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "assets", "BehindTheSmile_Assets", "BehindTheSmile_Assets"
        )
        
        # Try common folder
        common_path = os.path.join(asset_base, "common", f"{sprite_name}")
        if os.path.isfile(common_path):
            try:
                return pygame.image.load(common_path).convert_alpha()
            except Exception as e:
                print(f"Failed to load sprite {sprite_name} from {common_path}: {e}")
        
        # Try other common locations
        for folder in ["campus", "floor1", "floor2", "basement"]:
            folder_path = os.path.join(asset_base, folder, f"{sprite_name}")
            if os.path.isfile(folder_path):
                try:
                    return pygame.image.load(folder_path).convert_alpha()
                except Exception as e:
                    print(f"Failed to load sprite {sprite_name} from {folder_path}: {e}")
        
        # Sprite not found - return None (rendering code will skip it)
        print(f"Sprite {sprite_name} not found in assets or data/tiles")
        return None

    def draw(self, screen, camera, player=None, npcs=None, draw_furniture=True):
        sw, sh = screen.get_width(), screen.get_height()
        bg_rect = pygame.Rect(0, 0, self.width, self.height)
        bg = camera.apply_rect(bg_rect)
        pygame.draw.rect(screen, self.bg_color, bg)

        # Draw background tile if set
        if self.bg_tile_path:
            if self.bg_tile_path not in self._tile_cache:
                try:
                    self._tile_cache[self.bg_tile_path] = pygame.image.load(self.bg_tile_path).convert()
                except Exception:
                    self._tile_cache[self.bg_tile_path] = None
            
            tile_surf = self._tile_cache.get(self.bg_tile_path)
            if tile_surf:
                tw, th = tile_surf.get_size()
                old_clip = screen.get_clip()
                screen.set_clip(bg)
                cam_ox = int(camera.offset.x)
                cam_oy = int(camera.offset.y)
                # Tile over the entire floor area, but only for visible tiles
                start_wx = (cam_ox // tw) * tw
                start_wy = (cam_oy // th) * th
                wx = start_wx
                while wx < cam_ox + sw and wx < self.width:
                    wy = start_wy
                    while wy < cam_oy + sh and wy < self.height:
                        screen.blit(tile_surf, (wx - cam_ox, wy - cam_oy))
                        wy += th
                    wx += tw
                screen.set_clip(old_clip)

        font14 = pygame.font.Font(VT323_PATH, 14)

        for room in sorted(self.rooms.values(), key=lambda r: r.is_staircase):
            r = camera.apply_rect(room.rect)
            if r.right < 0 or r.left > sw or r.bottom < 0 or r.top > sh:
                continue
            # Draw room: tiled texture if tile_path set, otherwise solid color
            if room.tile_path:
                if room.tile_path not in self._tile_cache:
                    try:
                        self._tile_cache[room.tile_path] = pygame.image.load(room.tile_path).convert()
                    except Exception:
                        self._tile_cache[room.tile_path] = None
                tile_surf = self._tile_cache.get(room.tile_path)
                if tile_surf:
                    tw, th = tile_surf.get_size()
                    # Clip drawing to this room's screen rect
                    old_clip = screen.get_clip()
                    screen.set_clip(r)
                    # Tile across the room (world-space aligned so tiles don't drift with camera)
                    cam_ox = int(camera.offset.x)
                    cam_oy = int(camera.offset.y)
                    start_wx = (room.rect.x // tw) * tw
                    start_wy = (room.rect.y // th) * th
                    wx = start_wx
                    while wx < room.rect.right:
                        wy = start_wy
                        while wy < room.rect.bottom:
                            screen.blit(tile_surf, (wx - cam_ox, wy - cam_oy))
                            wy += th
                        wx += tw
                    screen.set_clip(old_clip)
                else:
                    pygame.draw.rect(screen, room.color, r)
            else:
                pygame.draw.rect(screen, room.color, r)
            if room.is_staircase and r.height > 20:
                self._draw_staircase_3d(screen, r, font14)
            elif r.width > 50:
                pass  # labels drawn after walls


        if npcs is None:
            npcs = []

        door_color = (180, 180, 205)
        for door in self.doors:
            dr = camera.apply_rect(door.rect)
            if dr.right < 0 or dr.left > sw or dr.bottom < 0 or dr.top > sh:
                continue

            # Check if player or any NPC is colliding with the door
            is_pushed = False
            pusher = None
            is_double_sliding = door.id in ("door_library", "door_cafeteria", "door_computer_lab", "door_science_lab", "door_admin", "door_director", "door_conference")
            is_double_swinging = door.id == "door_classrooms"
            if is_double_sliding:
                touch_rect = door.rect.inflate(60, 12)
            elif is_double_swinging:
                touch_rect = door.rect.inflate(12, 60)
            else:
                touch_rect = door.rect.inflate(16, 16)

            if not door.locked:
                if player and player.rect.colliderect(touch_rect):
                    is_pushed = True
                    pusher = player
                else:
                    for npc in npcs:
                        if npc.rect.colliderect(touch_rect):
                            is_pushed = True
                            pusher = npc
                            break

            if is_pushed and pusher:
                if door.open_ratio == 0.0:
                    px, py = pusher.rect.center
                    dx, dy = door.rect.center
                    if door.is_vertical:
                        door.swing_dir = 1 if px < dx else -1
                    else:
                        door.swing_dir = 1 if py > dy else -1
                door.open_ratio = min(1.0, door.open_ratio + 0.2)
                door.close_timer = 45.0 if (is_double_sliding or is_double_swinging) else 15.0
            else:
                if door.close_timer > 0:
                    door.close_timer -= 1
                else:
                    close_speed = 0.08 if (is_double_sliding or is_double_swinging) else 0.15
                    door.open_ratio = max(0.0, door.open_ratio - close_speed)

            if is_double_sliding:
                half_h = door.rect.height / 2.0
                slide = door.open_ratio * half_h
                top_rect = pygame.Rect(door.rect.x, door.rect.y - slide, door.rect.width, half_h)
                bot_rect = pygame.Rect(door.rect.x, door.rect.y + half_h + slide, door.rect.width, half_h)
                panels = [top_rect, bot_rect]
                for p_rect in panels:
                    pdr = camera.apply_rect(p_rect)
                    if pdr.right < 0 or pdr.left > sw or pdr.bottom < 0 or pdr.top > sh:
                        continue
                    pygame.draw.rect(screen, door.color or door_color, pdr)
                    pygame.draw.rect(screen, (40, 40, 50), pdr, 1)
                    if door.locked:
                        pygame.draw.line(screen, (200, 50, 50), (pdr.x, pdr.y), (pdr.right, pdr.bottom), 2)
                        pygame.draw.line(screen, (200, 50, 50), (pdr.right, pdr.y), (pdr.left, pdr.bottom), 2)
            elif is_double_swinging:
                half_w = door.rect.width / 2.0
                panel_surf = pygame.Surface((half_w, door.rect.height), pygame.SRCALPHA)
                pygame.draw.rect(panel_surf, door.color or door_color, panel_surf.get_rect())
                pygame.draw.rect(panel_surf, (40, 40, 50), panel_surf.get_rect(), 1)
                if door.locked:
                    pr = panel_surf.get_rect()
                    pygame.draw.line(panel_surf, (200, 50, 50), (pr.x, pr.y), (pr.right, pr.bottom), 2)
                    pygame.draw.line(panel_surf, (200, 50, 50), (pr.right, pr.y), (pr.left, pr.bottom), 2)

                import math
                angle = door.open_ratio * 90.0

                rot_left = angle if door.swing_dir == 1 else -angle
                surf_left = pygame.transform.rotate(panel_surf, rot_left)
                if door.swing_dir == 1:
                    lx = door.rect.x
                    ly = door.rect.y - half_w * math.sin(math.radians(angle))
                else:
                    lx = door.rect.x
                    ly = door.rect.bottom - door.rect.height * math.cos(math.radians(angle))

                rot_right = -angle if door.swing_dir == 1 else angle
                surf_right = pygame.transform.rotate(panel_surf, rot_right)
                if door.swing_dir == 1:
                    rx = door.rect.right - (door.rect.height * math.sin(math.radians(angle)) + half_w * math.cos(math.radians(angle)))
                    ry = door.rect.y - half_w * math.sin(math.radians(angle))
                else:
                    rx = door.rect.right - (half_w * math.cos(math.radians(angle)) + door.rect.height * math.sin(math.radians(angle)))
                    ry = door.rect.bottom - door.rect.height * math.cos(math.radians(angle))

                screen.blit(surf_left, camera.apply_pos(lx, ly))
                screen.blit(surf_right, camera.apply_pos(rx, ry))
            else:
                panel_surf = pygame.Surface((door.rect.width, door.rect.height), pygame.SRCALPHA)
                pygame.draw.rect(panel_surf, door.color or door_color, panel_surf.get_rect())
                pygame.draw.rect(panel_surf, (40, 40, 50), panel_surf.get_rect(), 1)
                if door.locked:
                    pr = panel_surf.get_rect()
                    pygame.draw.line(panel_surf, (200, 50, 50), (pr.x, pr.y), (pr.right, pr.bottom), 2)
                    pygame.draw.line(panel_surf, (200, 50, 50), (pr.right, pr.y), (pr.left, pr.bottom), 2)

                import math
                angle = door.open_ratio * 90.0
                rot_angle = angle if door.swing_dir == 1 else -angle
                rotated_surf = pygame.transform.rotate(panel_surf, rot_angle)

                if door.swing_dir == 1:
                    shift_x = 0
                    shift_y = door.rect.width * math.sin(math.radians(angle))
                else:
                    shift_x = door.rect.height * math.sin(math.radians(angle))
                    shift_y = 0

                blit_x = door.rect.x - shift_x
                blit_y = door.rect.y - shift_y
                screen_pos = camera.apply_pos(blit_x, blit_y)
                screen.blit(rotated_surf, screen_pos)

        if draw_furniture:
            for furn in self.furniture:
                self.draw_single_furn(screen, camera, furn)

        # ── Two-pass wall rendering ──────────────────────────────
        # Pass 1: shadows + 3-D extrusions (bottom/right faces)
        # Pass 2: top surfaces (caps)
        # This prevents one wall's extrusion from overlapping
        # another wall's top surface.
        pp_tables = getattr(self, 'ping_pong_tables', [])
        pp_table  = getattr(self, 'ping_pong_table', None)
        fountain  = getattr(self, 'fountain_rect', None)
        # Collect all furniture rects so they are drawn as furniture, not walls
        furniture_rects = set()
        for furn in self.furniture:
            furniture_rects.add(id(furn["rect"]))

        visible_walls = []  # (wall, screen_rect)
        for wall in self.walls:
            if wall in self.invisible_walls:
                continue
            wr = camera.apply_rect(wall)
            d = self.WALL_DEPTH
            if wr.right + d < 0 or wr.left > sw or wr.bottom + d < 0 or wr.top > sh:
                continue
            visible_walls.append((wall, wr))

        # Pass 1 — extrusions (back layer)
        for wall, wr in visible_walls:
            if wall in pp_tables or (pp_table and wall == pp_table):
                continue
            if fountain and wall == fountain:
                continue
            if id(wall) in furniture_rects:
                continue
            self._draw_wall_extrusion(screen, wr, wall=wall)

        # Pass 2 — top caps + special items (front layer)
        for wall, wr in visible_walls:
            if wall in pp_tables or (pp_table and wall == pp_table):
                self._draw_ping_pong_table(screen, wr)
            elif fountain and wall == fountain:
                continue
            elif id(wall) in furniture_rects:
                continue
            else:
                self._draw_wall_cap(screen, wr, wall=wall)

        # ── Room name labels (drawn AFTER walls so they stay visible) ──
        for room in self.rooms.values():
            if room.is_staircase:
                continue
            r = camera.apply_rect(room.rect)
            if r.right < 0 or r.left > sw or r.bottom < 0 or r.top > sh:
                continue
            if r.width > 50:
                lbl = font14.render(room.name, True, (200, 200, 210))
                y_offset = 24 if room.id == "c_tennis" else 8
                x_offset = 30 if room.id == "c_tennis" else 8
                lx, ly = r.x + x_offset, r.y + y_offset
                for other in self.rooms.values():
                    if other.is_staircase and other.rect.collidepoint(
                            room.rect.x + 8, room.rect.y + 8):
                        ly = camera.apply_rect(other.rect).bottom + 4
                        break
                if room.id == "f1_women_bath":
                    stair = self.rooms.get("f1_stairs_2f")
                    if stair:
                        lx, ly = camera.apply_pos(stair.rect.right + 12,
                                                   room.rect.y + 12)
                screen.blit(lbl, (lx, ly))

        if self.id == 0:  # Campus floor

            if hasattr(self, 'basketball_court'):
                bcr = camera.apply_rect(self.basketball_court)
                if bcr.right > 0 and bcr.left < sw and bcr.bottom > 0 and bcr.top < sh:
                    pygame.draw.line(screen, WHITE, (bcr.centerx, bcr.top), (bcr.centerx, bcr.bottom), 3)
                    pygame.draw.circle(screen, WHITE, bcr.center, int(bcr.height * 0.15), 3)
                    key_w = int(bcr.width * 0.2)
                    key_h = int(bcr.height * 0.4)
                    left_key = pygame.Rect(bcr.left, bcr.centery - key_h//2, key_w, key_h)
                    pygame.draw.rect(screen, WHITE, left_key, 3)
                    pygame.draw.circle(screen, WHITE, (left_key.right, left_key.centery), int(key_h//2), 3)
                    right_key = pygame.Rect(bcr.right - key_w, bcr.centery - key_h//2, key_w, key_h)
                    pygame.draw.rect(screen, WHITE, right_key, 3)
                    pygame.draw.circle(screen, WHITE, (right_key.left, right_key.centery), int(key_h//2), 3)

            if hasattr(self, 'garden_decorations'):
                # Initialize sprite cache if not present
                if not hasattr(self, '_sprite_cache'):
                    self._sprite_cache = {}
                
                for item in self.garden_decorations:
                    if item[0] == 'sprite':
                        sx_world, sy_world, sprite_name = item[1], item[2], item[3]
                        sx, sy = camera.apply_pos(sx_world, sy_world)
                        
                        # Try to load sprite if not cached
                        if sprite_name not in self._sprite_cache:
                            sprite_surf = self._load_sprite(sprite_name)
                            self._sprite_cache[sprite_name] = sprite_surf
                        
                        sprite_surf = self._sprite_cache[sprite_name]
                        if sprite_surf is not None:
                            # Optionally scale sprites that include width/height
                            if len(item) == 6:
                                _, _, _, _, sprite_w, sprite_h = item
                                sprite_surf = pygame.transform.smoothscale(sprite_surf, (sprite_w, sprite_h))
                            # Draw sprite centered at world position
                            sprite_rect = sprite_surf.get_rect(center=(sx, sy))
                            if -60 < sprite_rect.centerx < sw + 60 and -60 < sprite_rect.centery < sh + 60:
                                screen.blit(sprite_surf, sprite_rect)
                    
                    elif item[0] == 'tree':
                        _, tx, ty, rad = item
                        sx, sy = camera.apply_pos(tx, ty)
                        draw_rad = rad * 2
                        if -60 < sx < sw + 60 and -60 < sy < sh + 60:
                            pygame.draw.circle(screen, (20, 40, 20), (sx + 5, sy + 5), draw_rad)
                    elif item[0] == 'flower':
                        _, fx, fy, color = item
                        sx, sy = camera.apply_pos(fx, fy)
                        if -10 < sx < sw + 10 and -10 < sy < sh + 10:
                            pygame.draw.circle(screen, color, (sx, sy), 4)
                            pygame.draw.circle(screen, (255, 255, 0), (sx, sy), 2)
                    elif item[0] == 'bush':
                        _, bx, by, rad = item
                        sx, sy = camera.apply_pos(bx, by)
                        if -40 < sx < sw + 40 and -40 < sy < sh + 40:
                            # Drawing a bush as a cluster of circles for texture
                            pygame.draw.circle(screen, (34, 60, 34), (sx, sy), rad)
                            pygame.draw.circle(screen, (46, 82, 46), (sx - 4, sy - 2), int(rad*0.7))
                            pygame.draw.circle(screen, (24, 48, 24), (sx + 4, sy + 3), int(rad*0.6))
                            
            # Road dashed lines
            road_y = 2925
            if hasattr(self, 'rooms') and "c_road" in self.rooms:
                road_room = self.rooms["c_road"].rect
                ry_screen = camera.apply_pos(road_room.x, road_y)[1]
                if -10 < ry_screen < sh + 10:
                    dash_len = 80
                    dash_gap = 60
                    for lx in range(road_room.x, road_room.right, dash_len + dash_gap):
                        start_pos = camera.apply_pos(lx, road_y)
                        end_pos = camera.apply_pos(min(lx + dash_len, road_room.right), road_y)
                        if start_pos[0] < sw and end_pos[0] > 0:
                            pygame.draw.line(screen, (220, 220, 220), start_pos, end_pos, 4)
            if hasattr(self, "curved_road"):
                import math
                c = self.curved_road
                cx, cy = c["center"]
                radius = c["radius"]
                curve_points = [(cx, cy)]
                for i in range(17):
                    ang = -math.pi / 2 + (i / 16) * (math.pi / 2)
                    curve_points.append((cx + int(math.cos(ang) * radius),
                                         cy + int(math.sin(ang) * radius)))
                pygame.draw.polygon(screen, c["color"], [camera.apply_pos(x, y) for x, y in curve_points])
                arc_rect = camera.apply_rect(pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2))
                pygame.draw.arc(screen, (220, 220, 220), arc_rect, -math.pi / 2, 0, 4)
            
        # Draw coliseum basketball court (pre-rendered tile based from assets/Baloncesto.png)
        if self.id == 5 and hasattr(self, "basketball_court"):
            bc = self.basketball_court
            cam_ox = int(camera.offset.x)
            cam_oy = int(camera.offset.y)
            court_x = bc.x - cam_ox
            court_y = bc.y - cam_oy
            
            # Check visibility (size is 848x694)
            if -848 < court_x < sw and -694 < court_y < sh:
                # Initialize resources
                if "baloncesto" not in self._tile_cache:
                    try:
                        self._tile_cache["baloncesto"] = pygame.image.load("assets/Baloncesto.png").convert_alpha()
                    except Exception:
                        self._tile_cache["baloncesto"] = None
                        
                if not hasattr(self, "_court_surface"):
                    sheet = self._tile_cache.get("baloncesto")
                    if sheet:
                        # 1. Crop and scale Horizontal Court: cols = 108..531 (width 424), rows = 3..349 (height 347)
                        court_orig = sheet.subsurface(pygame.Rect(108, 3, 424, 347))
                        self._court_surface = pygame.transform.scale(court_orig, (848, 694))
                        
                        # 2. Left Hoop: Hoop 2 (cols = 4..91, rows = 163..289, height = 127, width = 88)
                        # This hoop has orange on the right (facing right, goes on left side)
                        left_hoop_orig = sheet.subsurface(pygame.Rect(4, 163, 88, 127))
                        self._left_hoop_surface = pygame.transform.scale(left_hoop_orig, (132, 190))
                        
                        # 3. Right Hoop: Hoop 1 (cols = 4..91, rows = 3..129, height = 127, width = 88)
                        # This hoop has orange on the left (facing left, goes on right side)
                        right_hoop_orig = sheet.subsurface(pygame.Rect(4, 3, 88, 127))
                        self._right_hoop_surface = pygame.transform.scale(right_hoop_orig, (132, 190))
                        
                # Blit everything centered on the wood floor color!
                if hasattr(self, "_court_surface") and self._court_surface:
                    screen.blit(self._court_surface, (court_x, court_y))

        # Transitions drawing - only for interior floors (to show the exit)
        if self.id != 0:
            font_sm = pygame.font.Font(VT323_PATH, 13)
            for tr in self.transitions:
                r = camera.apply_rect(tr.rect)
                if r.right < 0 or r.left > sw:
                    continue
                pygame.draw.rect(screen, (80, 180, 255, 180), r)
                pygame.draw.rect(screen, WHITE, r, 1)
                if tr.label and r.width > 20:
                    lbl = font_sm.render(tr.label, True, WHITE)
                    screen.blit(lbl, (r.x + 2, r.y - 16))

    def draw_single_furn(self, screen, camera, furn):
        sw, sh = screen.get_width(), screen.get_height()
        fr = camera.apply_rect(furn["rect"])
        if fr.right < 0 or fr.left > sw or fr.bottom < 0 or fr.top > sh:
            return
        ftype = furn.get("type")
        if ftype == "bookshelf":
            self._draw_bookshelf(screen, fr)
        elif ftype == "round_table":
            pygame.draw.circle(screen, furn["color"], fr.center, fr.width // 2)
            if furn.get("outline"):
                pygame.draw.circle(screen, furn["outline"], fr.center, fr.width // 2, 2)
        elif ftype == "lamp":
            # Base
            pygame.draw.circle(screen, (80, 80, 80), fr.center, fr.width // 3)
            # Shade
            pygame.draw.circle(screen, furn["color"], fr.center, fr.width // 2)
            # Glow
            glow_surf = pygame.Surface((fr.width * 2, fr.height * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (255, 255, 200, 40), (fr.width, fr.height), fr.width)
            screen.blit(glow_surf, (fr.centerx - fr.width, fr.centery - fr.height))
        elif ftype == "plant":
            self._draw_plant(screen, fr, furn["color"])
        elif ftype == "bench":
            self._draw_bench(screen, fr)
        elif ftype == "buffet_tray":
            # Silver outer tray
            pygame.draw.rect(screen, (190, 190, 200), fr, border_radius=4)
            pygame.draw.rect(screen, (150, 150, 160), fr, 2, border_radius=4)
            # Inner food area
            inner = fr.inflate(-8, -8)
            if inner.width > 0 and inner.height > 0:
                pygame.draw.rect(screen, furn["color"], inner, border_radius=2)
        elif ftype == "toilet":
            self._draw_toilet(screen, fr, furn.get("facing", "down"))
        elif ftype == "computer":
            self._draw_computer(screen, fr, furn.get("facing", "up"))
        elif ftype == "lab_bench":
            self._draw_lab_bench(screen, fr)
        elif ftype == "piano":
            self._draw_piano(screen, fr)
        elif ftype == "drum_set":
            self._draw_drum_set(screen, fr)
        elif ftype == "guitar":
            self._draw_guitar(screen, fr)
        elif ftype == "easel":
            self._draw_easel(screen, fr)
        elif ftype == "locker":
            self._draw_locker(screen, fr)
        elif ftype == "office_desk":
            self._draw_office_desk(screen, fr, furn.get("facing", "down"))
        elif ftype == "office_chair":
            self._draw_office_chair(screen, fr)
        elif ftype == "hospital_bed":
            self._draw_hospital_bed(screen, fr, furn.get("facing", "down"))
        elif ftype == "stage":
            self._draw_stage(screen, fr)
        elif ftype == "auditorium_seat":
            self._draw_auditorium_seat(screen, fr)
        elif ftype == "executive_desk":
            self._draw_executive_desk(screen, fr)
        elif ftype == "sofa_chair":
            self._draw_sofa_chair(screen, fr)
        elif ftype == "umbrella_table":
            self._draw_umbrella_table(screen, fr)
        elif ftype == "chalkboard":
            self._draw_chalkboard(screen, fr, furn.get("facing", "up"))
        elif ftype == "sink":
            self._draw_sink(screen, fr, furn.get("facing", "down"))
        else:
            pygame.draw.rect(screen, furn["color"], fr)
            if furn.get("outline"):
                pygame.draw.rect(screen, furn["outline"], fr, 2)

    def _draw_basement_lighting(self, screen, camera, player):
        import math, time, random
        sw, sh = screen.get_width(), screen.get_height()
        
        # 1. Prepare dark surface
        if not hasattr(self, '_basement_dark_surf') or self._basement_dark_surf.get_size() != (sw, sh):
            self._basement_dark_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        
        # Very dark purple-black tint
        self._basement_dark_surf.fill((8, 4, 15, 245)) 
        
        # 2. Spotlight position
        if player:
            # We use center of player rect
            px, py = camera.apply_pos(player.rect.centerx, player.rect.centery)
        else:
            px, py = sw // 2, sh // 2
            
        # 3. Stabilized Atmosphere (Subtle movement)
        t = time.time()
        # Very subtle jitter (reduced from 0.98-1.02 to 0.995-1.005)
        flicker = random.uniform(0.995, 1.005)
        
        # Very slow and subtle pulse (reduced from 0.04 to 0.015 and slower frequency)
        pulse = 1.0 + math.sin(t * 0.8) * 0.015
        
        radius = int(280 * flicker * pulse)
        
        # 4. Draw the light mask (Spotlight)
        if not hasattr(self, '_light_mask_base'):
            # Create a base radial gradient mask
            msize = 600
            self._light_mask_base = pygame.Surface((msize, msize), pygame.SRCALPHA)
            center = msize // 2
            for r in range(center, 0, -2):
                # Quadratic falloff for a more natural flashlight look
                ratio = r / center
                alpha = int(255 * (1 - ratio * ratio))
                pygame.draw.circle(self._light_mask_base, (0, 0, 0, alpha), (center, center), r)
        
        # Scale and blit mask with SUBtraction to "punch a hole" in the darkness
        mask = pygame.transform.scale(self._light_mask_base, (radius * 2, radius * 2))
        self._basement_dark_surf.blit(mask, (px - radius, py - radius), special_flags=pygame.BLEND_RGBA_SUB)
        
        # 5. Add a very faint yellow glow at the core
        glow_r = int(radius * 0.3)
        glow_surf = pygame.Surface((glow_r*2, glow_r*2), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (220, 200, 100, 15), (glow_r, glow_r), glow_r)
        self._basement_dark_surf.blit(glow_surf, (px - glow_r, py - glow_r))

        # 6. Apply final result to screen
        screen.blit(self._basement_dark_surf, (0, 0))

    # ── Staircase 3D rendering ───────────────────────────────────

    def _draw_staircase_3d(self, screen: pygame.Surface, rect: pygame.Rect,
                           font: pygame.font.Font):
        """Draw a top-down staircase with a clear 3D stepped look.

        Each step is a tread slab with a bright nosing edge and a dark
        riser shadow, plus side rails. Treads alternate slightly so the
        ascent reads at a glance.
        """
        if rect.width <= 0 or rect.height <= 0:
            return

        inset = 3
        inner = rect.inflate(-inset * 2, -inset * 2)
        if inner.width <= 4 or inner.height <= 4:
            return

        # Backdrop (dark stairwell shaft beneath the steps)
        pygame.draw.rect(screen, (24, 24, 32), rect)
        pygame.draw.rect(screen, self.STAIR_RAIL, rect, 2)

        horizontal_climb = inner.width >= inner.height

        if horizontal_climb:
            target_step = 14
            n = max(6, inner.width // target_step)
            step_w = inner.width / n
            for i in range(n):
                x0 = int(inner.x + i * step_w)
                x1 = int(inner.x + (i + 1) * step_w)
                w = max(1, x1 - x0)
                t = i / max(1, n - 1)
                # Treads brighten toward the front (right side)
                shade_r = int(self.STAIR_TREAD_LO[0] + (self.STAIR_TREAD_HI[0] - self.STAIR_TREAD_LO[0]) * t)
                shade_g = int(self.STAIR_TREAD_LO[1] + (self.STAIR_TREAD_HI[1] - self.STAIR_TREAD_LO[1]) * t)
                shade_b = int(self.STAIR_TREAD_LO[2] + (self.STAIR_TREAD_HI[2] - self.STAIR_TREAD_LO[2]) * t)
                pygame.draw.rect(screen, (shade_r, shade_g, shade_b),
                                 (x0, inner.y, w, inner.height))
                # Riser shadow on the back edge of each step
                pygame.draw.rect(screen, self.STAIR_RISER,
                                 (x0, inner.y, max(1, min(2, w)), inner.height))
                # Nosing highlight on the front edge of each step
                pygame.draw.line(screen, self.STAIR_NOSING,
                                 (x1 - 1, inner.y + 1),
                                 (x1 - 1, inner.bottom - 2), 1)
            # Side rails (top and bottom long edges)
            pygame.draw.rect(screen, self.STAIR_RAIL,
                             (inner.x, inner.y, inner.width, 3))
            pygame.draw.rect(screen, self.STAIR_RAIL,
                             (inner.x, inner.bottom - 3, inner.width, 3))
            pygame.draw.line(screen, self.STAIR_RAIL_HI,
                             (inner.x + 1, inner.y + 3),
                             (inner.right - 2, inner.y + 3), 1)
        else:
            target_step = 12
            n = max(6, inner.height // target_step)
            step_h = inner.height / n
            for i in range(n):
                y0 = int(inner.y + i * step_h)
                y1 = int(inner.y + (i + 1) * step_h)
                h = max(1, y1 - y0)
                t = i / max(1, n - 1)
                shade_r = int(self.STAIR_TREAD_LO[0] + (self.STAIR_TREAD_HI[0] - self.STAIR_TREAD_LO[0]) * t)
                shade_g = int(self.STAIR_TREAD_LO[1] + (self.STAIR_TREAD_HI[1] - self.STAIR_TREAD_LO[1]) * t)
                shade_b = int(self.STAIR_TREAD_LO[2] + (self.STAIR_TREAD_HI[2] - self.STAIR_TREAD_LO[2]) * t)
                pygame.draw.rect(screen, (shade_r, shade_g, shade_b),
                                 (inner.x, y0, inner.width, h))
                # Riser shadow on the back (upper) edge of each step
                pygame.draw.rect(screen, self.STAIR_RISER,
                                 (inner.x, y0, inner.width, max(1, min(2, h))))
                # Nosing highlight on the front (lower) edge of each step
                pygame.draw.line(screen, self.STAIR_NOSING,
                                 (inner.x + 1, y1 - 1),
                                 (inner.right - 2, y1 - 1), 1)
            # Side rails (left and right vertical edges)
            pygame.draw.rect(screen, self.STAIR_RAIL,
                             (inner.x, inner.y, 3, inner.height))
            pygame.draw.rect(screen, self.STAIR_RAIL,
                             (inner.right - 3, inner.y, 3, inner.height))
            pygame.draw.line(screen, self.STAIR_RAIL_HI,
                             (inner.x + 3, inner.y + 1),
                             (inner.x + 3, inner.bottom - 2), 1)

        # Up/down arrow guide
        if rect.width > 40 and rect.height > 30:
            arr = font.render("\u2191\u2193", True, self.STAIR_ARROW_COL)
            arr_surf = pygame.Surface(arr.get_size(), pygame.SRCALPHA)
            arr_surf.fill((0, 0, 0, 110))
            screen.blit(arr_surf,
                        (rect.centerx - arr.get_width() // 2,
                         rect.centery - arr.get_height() // 2))
            screen.blit(arr,
                        (rect.centerx - arr.get_width() // 2,
                         rect.centery - arr.get_height() // 2))

    # ── Two-pass wall helpers ────────────────────────────────────

    def _draw_wall_extrusion(self, screen: pygame.Surface, rect: pygame.Rect, wall=None):
        """Pass 1: draw shadow + right face + bottom face (the 3-D sides)."""
        if rect.width <= 0 or rect.height <= 0:
            return

        d = self.WALL_DEPTH
        orig_wall = wall if wall is not None else rect
        is_windowed = hasattr(self, 'windowed_walls') and orig_wall in self.windowed_walls

        # Drop shadow
        sh_off = d + 2
        shadow = rect.move(sh_off, sh_off)
        shadow_surf = pygame.Surface((shadow.width, shadow.height), pygame.SRCALPHA)
        shadow_surf.fill((*BLACK, 55))
        screen.blit(shadow_surf, shadow)

        # Right face (east side, darkest)
        right_face = [
            (rect.right, rect.top),
            (rect.right + d, rect.top + d),
            (rect.right + d, rect.bottom + d),
            (rect.right, rect.bottom),
        ]
        pygame.draw.polygon(screen, (80, 90, 100) if is_windowed else self.WALL_RIGHT_COLOR, right_face)
        pygame.draw.polygon(screen, (40, 45, 50) if is_windowed else self.WALL_EDGE_COLOR, right_face, 2)

        # Bottom face (south side, medium shade)
        bottom_face = [
            (rect.left, rect.bottom),
            (rect.right, rect.bottom),
            (rect.right + d, rect.bottom + d),
            (rect.left + d, rect.bottom + d),
        ]
        if is_windowed:
            pygame.draw.polygon(screen, (50, 55, 60), bottom_face)
            pane_w = 40
            post_w = 6
            cur_x = rect.left
            while cur_x < rect.right:
                pw = min(pane_w, rect.right - cur_x)
                box_w = pw + d
                box_h = d
                if box_w > 0 and box_h > 0:
                    glass_surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
                    glass_surf.fill((0, 0, 0, 0))
                    local_poly = [
                        (0, 0),
                        (pw, 0),
                        (pw + d, d),
                        (d, d),
                    ]
                    pygame.draw.polygon(glass_surf, (140, 210, 250, 140), local_poly)
                    pygame.draw.line(glass_surf, (255, 255, 255, 180), (pw // 2, 0), (pw // 2 + d - 2, d - 2), 2)
                    screen.blit(glass_surf, (cur_x, rect.bottom))
                
                cur_x += pw
                if cur_x < rect.right:
                    post_poly = [
                        (cur_x, rect.bottom),
                        (cur_x + post_w, rect.bottom),
                        (cur_x + post_w + d, rect.bottom + d),
                        (cur_x + d, rect.bottom + d),
                    ]
                    pygame.draw.polygon(screen, (70, 75, 80), post_poly)
                    pygame.draw.polygon(screen, (30, 35, 40), post_poly, 1)
                    cur_x += post_w
            pygame.draw.polygon(screen, (30, 35, 40), bottom_face, 2)
        else:
            pygame.draw.polygon(screen, self.WALL_SHADE_COLOR, bottom_face)
            pygame.draw.polygon(screen, self.WALL_EDGE_COLOR, bottom_face, 2)

    def _draw_wall_cap(self, screen: pygame.Surface, rect: pygame.Rect, wall=None):
        """Pass 2: draw the top surface (cap) of the wall."""
        if rect.width <= 0 or rect.height <= 0:
            return

        orig_wall = wall if wall is not None else rect
        is_windowed = hasattr(self, 'windowed_walls') and orig_wall in self.windowed_walls
        if is_windowed:
            pygame.draw.rect(screen, (160, 170, 180), rect)
            pygame.draw.rect(screen, (60, 65, 70), rect, 2)
            pygame.draw.line(screen, (120, 200, 240), (rect.left + 2, rect.centery), (rect.right - 2, rect.centery), 2)
            return

        # Top surface
        pygame.draw.rect(screen, self.WALL_TOP_COLOR, rect)

        # Subtle highlight at top edge
        hilite_h = max(2, min(4, rect.height // 3))
        hilite_rect = pygame.Rect(rect.x + 1, rect.y + 1,
                                  rect.width - 2, hilite_h)
        hilite_surf = pygame.Surface((hilite_rect.width, hilite_rect.height), pygame.SRCALPHA)
        hilite_surf.fill((*self.WALL_HILITE, 70))
        screen.blit(hilite_surf, hilite_rect)

        # Subtle darker band at bottom edge of cap
        shade_h = max(2, min(4, rect.height // 4))
        shade_rect = pygame.Rect(rect.x + 1, rect.bottom - shade_h,
                                 rect.width - 2, shade_h)
        shade_surf = pygame.Surface((shade_rect.width, shade_rect.height), pygame.SRCALPHA)
        shade_surf.fill((*BLACK, 30))
        screen.blit(shade_surf, shade_rect)

        # Outline
        pygame.draw.rect(screen, self.WALL_EDGE_COLOR, rect, 2)

    def _draw_topdown_wall(self, screen: pygame.Surface, rect: pygame.Rect, wall=None):
        """Legacy single-call: draw both extrusion and cap in one go."""
        self._draw_wall_extrusion(screen, rect, wall=wall)
        self._draw_wall_cap(screen, rect, wall=wall)


    def _draw_ping_pong_table(self, screen: pygame.Surface, rect: pygame.Rect):
        """Draw a top-down ping pong table."""
        pygame.draw.rect(screen, (24, 105, 40), rect)
        pygame.draw.rect(screen, WHITE, rect, 3)
        pygame.draw.line(screen, WHITE, (rect.centerx, rect.top + 3), (rect.centerx, rect.bottom - 3), 3)
        pygame.draw.line(screen, WHITE, (rect.left + 3, rect.centery), (rect.right - 3, rect.centery), 2)
        net = pygame.Rect(rect.centerx - 3, rect.top - 5, 6, rect.height + 10)
        pygame.draw.rect(screen, (225, 235, 245), net)
        pygame.draw.rect(screen, (55, 65, 75), net, 1)

    def _draw_bookshelf(self, screen: pygame.Surface, rect: pygame.Rect):
        """Draw a compact library bookshelf with colored books."""
        pygame.draw.rect(screen, (92, 58, 34), rect)
        pygame.draw.rect(screen, (55, 34, 22), rect, 2)
        shelf_count = 3 if rect.height >= 58 else 2
        book_colors = [
            (150, 45, 55), (45, 90, 150), (60, 130, 75),
            (185, 150, 55), (115, 70, 145),
        ]
        pad = 6
        shelf_h = max(10, (rect.height - pad * 2) // shelf_count)
        for row in range(shelf_count):
            y = rect.top + pad + row * shelf_h
            pygame.draw.line(screen, (50, 30, 20), (rect.left + 4, y + shelf_h), (rect.right - 4, y + shelf_h), 2)
            x = rect.left + pad
            book_idx = 0  # camera-independent index for deterministic sizing
            while x < rect.right - pad - 6:
                w = 5 + ((book_idx + row * 3) % 5)
                h = max(8, shelf_h - 5 - ((book_idx + row) % 4))
                color = book_colors[(book_idx + row) % len(book_colors)]
                pygame.draw.rect(screen, color, pygame.Rect(x, y + shelf_h - h - 1, w, h))
                x += w + 3
                book_idx += 1

    # ── Detailed furniture renderers ─────────────────────────────

    def _draw_toilet(self, screen: pygame.Surface, rect: pygame.Rect, facing: str = "down"):
        """Top-down toilet: tank at the back, oval bowl at the front."""
        if rect.width <= 4 or rect.height <= 4:
            return
        bowl_col = (240, 244, 250)
        tank_col = (215, 220, 230)
        edge = (140, 144, 160)
        seat = (200, 205, 218)
        # Background tile (white-ish floor patch)
        pygame.draw.rect(screen, (250, 252, 255), rect)
        pygame.draw.rect(screen, edge, rect, 1)
        # Orient: tank goes at the "back" side, bowl at the front
        if facing in ("down", "up"):
            tank_h = max(6, rect.height // 3)
            if facing == "down":
                tank_rect = pygame.Rect(rect.x + 2, rect.y + 2, rect.width - 4, tank_h)
                bowl_rect = pygame.Rect(rect.x + 4, rect.y + tank_h + 1, rect.width - 8, rect.height - tank_h - 4)
            else:
                tank_rect = pygame.Rect(rect.x + 2, rect.bottom - tank_h - 2, rect.width - 4, tank_h)
                bowl_rect = pygame.Rect(rect.x + 4, rect.y + 2, rect.width - 8, rect.height - tank_h - 4)
            pygame.draw.rect(screen, tank_col, tank_rect)
            pygame.draw.rect(screen, edge, tank_rect, 1)
            pygame.draw.ellipse(screen, bowl_col, bowl_rect)
            pygame.draw.ellipse(screen, edge, bowl_rect, 1)
            inner = bowl_rect.inflate(-6, -6)
            if inner.width > 0 and inner.height > 0:
                pygame.draw.ellipse(screen, seat, inner)
                pygame.draw.ellipse(screen, edge, inner, 1)
        else:
            tank_w = max(6, rect.width // 3)
            if facing == "right":
                tank_rect = pygame.Rect(rect.x + 2, rect.y + 2, tank_w, rect.height - 4)
                bowl_rect = pygame.Rect(rect.x + tank_w + 1, rect.y + 4, rect.width - tank_w - 4, rect.height - 8)
            else:
                tank_rect = pygame.Rect(rect.right - tank_w - 2, rect.y + 2, tank_w, rect.height - 4)
                bowl_rect = pygame.Rect(rect.x + 2, rect.y + 4, rect.width - tank_w - 4, rect.height - 8)
            pygame.draw.rect(screen, tank_col, tank_rect)
            pygame.draw.rect(screen, edge, tank_rect, 1)
            pygame.draw.ellipse(screen, bowl_col, bowl_rect)
            pygame.draw.ellipse(screen, edge, bowl_rect, 1)
            inner = bowl_rect.inflate(-6, -6)
            if inner.width > 0 and inner.height > 0:
                pygame.draw.ellipse(screen, seat, inner)
                pygame.draw.ellipse(screen, edge, inner, 1)

    def _draw_computer(self, screen: pygame.Surface, rect: pygame.Rect, facing: str = "up"):
        """Top-down desktop computer: monitor + keyboard + mouse on a desk."""
        if rect.width <= 6 or rect.height <= 6:
            return
        desk = (148, 110, 70)
        desk_edge = (90, 64, 38)
        monitor = (28, 30, 38)
        screen_col = (90, 175, 230)
        keyboard = (40, 42, 50)
        keys = (210, 215, 225)
        mouse_col = (35, 35, 45)
        pygame.draw.rect(screen, desk, rect)
        pygame.draw.rect(screen, desk_edge, rect, 1)

        if facing in ("up", "down"):
            mon_w = int(rect.width * 0.6)
            mon_h = max(8, int(rect.height * 0.35))
            kb_w = int(rect.width * 0.7)
            kb_h = max(6, int(rect.height * 0.18))
            if facing == "up":
                mon_rect = pygame.Rect(rect.centerx - mon_w // 2, rect.y + 3, mon_w, mon_h)
                kb_rect = pygame.Rect(rect.centerx - kb_w // 2, rect.bottom - kb_h - 5, kb_w, kb_h)
                mouse_pos = (rect.right - 8, rect.bottom - 8)
            else:
                mon_rect = pygame.Rect(rect.centerx - mon_w // 2, rect.bottom - mon_h - 3, mon_w, mon_h)
                kb_rect = pygame.Rect(rect.centerx - kb_w // 2, rect.y + 5, kb_w, kb_h)
                mouse_pos = (rect.left + 8, rect.y + 8)
            pygame.draw.rect(screen, monitor, mon_rect, border_radius=2)
            inner_screen = mon_rect.inflate(-4, -4)
            if inner_screen.width > 0 and inner_screen.height > 0:
                pygame.draw.rect(screen, screen_col, inner_screen)
            pygame.draw.rect(screen, keyboard, kb_rect, border_radius=2)
            # key dots
            if kb_rect.width > 18 and kb_rect.height > 6:
                for i in range(3):
                    ky = kb_rect.y + 2 + i * (kb_rect.height // 3)
                    pygame.draw.line(screen, keys, (kb_rect.x + 3, ky), (kb_rect.right - 3, ky), 1)
            pygame.draw.circle(screen, mouse_col, mouse_pos, 3)
        else:
            mon_w = max(8, int(rect.width * 0.35))
            mon_h = int(rect.height * 0.6)
            kb_w = max(6, int(rect.width * 0.18))
            kb_h = int(rect.height * 0.7)
            if facing == "left":
                mon_rect = pygame.Rect(rect.x + 3, rect.centery - mon_h // 2, mon_w, mon_h)
                kb_rect = pygame.Rect(rect.right - kb_w - 5, rect.centery - kb_h // 2, kb_w, kb_h)
                mouse_pos = (rect.right - 8, rect.bottom - 8)
            else:
                mon_rect = pygame.Rect(rect.right - mon_w - 3, rect.centery - mon_h // 2, mon_w, mon_h)
                kb_rect = pygame.Rect(rect.x + 5, rect.centery - kb_h // 2, kb_w, kb_h)
                mouse_pos = (rect.x + 8, rect.y + 8)
            pygame.draw.rect(screen, monitor, mon_rect, border_radius=2)
            inner_screen = mon_rect.inflate(-4, -4)
            if inner_screen.width > 0 and inner_screen.height > 0:
                pygame.draw.rect(screen, screen_col, inner_screen)
            pygame.draw.rect(screen, keyboard, kb_rect, border_radius=2)
            if kb_rect.height > 18 and kb_rect.width > 6:
                for i in range(3):
                    kx = kb_rect.x + 2 + i * (kb_rect.width // 3)
                    pygame.draw.line(screen, keys, (kx, kb_rect.y + 3), (kx, kb_rect.bottom - 3), 1)
            pygame.draw.circle(screen, mouse_col, mouse_pos, 3)

    def _draw_lab_bench(self, screen: pygame.Surface, rect: pygame.Rect):
        """Chemistry lab bench: dark surface with beakers, flasks, bunsen burner, rack."""
        if rect.width <= 8 or rect.height <= 8:
            return
        bench = (60, 65, 78)
        bench_edge = (28, 32, 44)
        pygame.draw.rect(screen, bench, rect)
        pygame.draw.rect(screen, bench_edge, rect, 2)
        # Lay equipment along the bench length (horizontal or vertical)
        horizontal = rect.width >= rect.height
        cx, cy = rect.centerx, rect.centery
        if horizontal:
            spots = [
                (rect.x + 14, cy),
                (rect.x + 36, cy),
                (rect.x + 58, cy),
                (cx + 10, cy),
                (cx + 32, cy),
                (rect.right - 16, cy),
            ]
        else:
            spots = [
                (cx, rect.y + 14),
                (cx, rect.y + 36),
                (cx, rect.y + 58),
                (cx, cy + 10),
                (cx, cy + 32),
                (cx, rect.bottom - 16),
            ]
        equipment = [
            ("beaker", (135, 210, 240)),
            ("flask", (170, 240, 180)),
            ("burner", (180, 120, 60)),
            ("tube_rack", (140, 90, 60)),
            ("beaker", (240, 180, 130)),
            ("flask", (220, 150, 220)),
        ]
        for (ex, ey), (kind, col) in zip(spots, equipment):
            if not rect.collidepoint(ex, ey):
                continue
            if kind == "beaker":
                # Square beaker with liquid
                br = pygame.Rect(ex - 5, ey - 6, 10, 12)
                pygame.draw.rect(screen, (235, 240, 245), br)
                pygame.draw.rect(screen, (40, 40, 50), br, 1)
                liquid = pygame.Rect(ex - 4, ey - 2, 8, 7)
                pygame.draw.rect(screen, col, liquid)
            elif kind == "flask":
                # Erlenmeyer flask: triangle body with neck
                pygame.draw.line(screen, (40, 40, 50), (ex, ey - 7), (ex, ey - 2), 2)
                points = [(ex - 6, ey + 6), (ex + 6, ey + 6), (ex + 2, ey - 2), (ex - 2, ey - 2)]
                pygame.draw.polygon(screen, (235, 240, 245), points)
                pygame.draw.polygon(screen, (40, 40, 50), points, 1)
                liquid_pts = [(ex - 5, ey + 5), (ex + 5, ey + 5), (ex + 1, ey + 1), (ex - 1, ey + 1)]
                pygame.draw.polygon(screen, col, liquid_pts)
            elif kind == "burner":
                # Bunsen burner: dark base + blue flame
                pygame.draw.rect(screen, (50, 50, 60), pygame.Rect(ex - 4, ey - 2, 8, 8))
                pygame.draw.polygon(screen, (90, 160, 220),
                                    [(ex - 3, ey - 2), (ex + 3, ey - 2), (ex, ey - 8)])
                pygame.draw.polygon(screen, (230, 220, 120),
                                    [(ex - 1, ey - 3), (ex + 1, ey - 3), (ex, ey - 6)])
            elif kind == "tube_rack":
                rack = pygame.Rect(ex - 8, ey - 4, 16, 8)
                pygame.draw.rect(screen, col, rack)
                pygame.draw.rect(screen, (60, 40, 25), rack, 1)
                for i in range(4):
                    tx = rack.x + 2 + i * 4
                    pygame.draw.line(screen, (220, 230, 240), (tx, rack.y - 4), (tx, rack.y), 2)

    def _draw_piano(self, screen: pygame.Surface, rect: pygame.Rect):
        """Upright piano viewed from above: black body with white keys row."""
        if rect.width <= 6 or rect.height <= 6:
            return
        body = (24, 24, 28)
        wood = (50, 32, 22)
        keys_white = (240, 240, 245)
        keys_edge = (40, 40, 50)
        pygame.draw.rect(screen, body, rect)
        pygame.draw.rect(screen, wood, rect, 2)
        horizontal = rect.width >= rect.height
        if horizontal:
            keys_rect = pygame.Rect(rect.x + 4, rect.bottom - 12, rect.width - 8, 8)
            pygame.draw.rect(screen, keys_white, keys_rect)
            pygame.draw.rect(screen, keys_edge, keys_rect, 1)
            n = max(8, keys_rect.width // 8)
            for i in range(1, n):
                kx = keys_rect.x + int(keys_rect.width * i / n)
                pygame.draw.line(screen, keys_edge, (kx, keys_rect.y), (kx, keys_rect.bottom), 1)
            # Black keys (groups of 2 and 3)
            for i in range(n):
                if i % 7 in (1, 3, 4):
                    kx = keys_rect.x + int(keys_rect.width * i / n)
                    bkw = max(2, keys_rect.width // n - 3)
                    pygame.draw.rect(screen, body, (kx + 1, keys_rect.y, bkw, keys_rect.height // 2))
        else:
            keys_rect = pygame.Rect(rect.right - 12, rect.y + 4, 8, rect.height - 8)
            pygame.draw.rect(screen, keys_white, keys_rect)
            pygame.draw.rect(screen, keys_edge, keys_rect, 1)
            n = max(8, keys_rect.height // 8)
            for i in range(1, n):
                ky = keys_rect.y + int(keys_rect.height * i / n)
                pygame.draw.line(screen, keys_edge, (keys_rect.x, ky), (keys_rect.right, ky), 1)
            for i in range(n):
                if i % 7 in (1, 3, 4):
                    ky = keys_rect.y + int(keys_rect.height * i / n)
                    bkh = max(2, keys_rect.height // n - 3)
                    pygame.draw.rect(screen, body, (keys_rect.x, ky + 1, keys_rect.width // 2, bkh))

    def _draw_drum_set(self, screen: pygame.Surface, rect: pygame.Rect):
        """Drum kit viewed from above: bass + snare + toms + cymbals."""
        if rect.width <= 8 or rect.height <= 8:
            return
        cx, cy = rect.centerx, rect.centery
        # Background carpet
        pygame.draw.rect(screen, (60, 30, 35), rect)
        pygame.draw.rect(screen, (35, 18, 22), rect, 1)
        # Bass drum (largest, centre)
        bass_r = max(6, min(rect.width, rect.height) // 3)
        pygame.draw.circle(screen, (220, 220, 230), (cx, cy), bass_r)
        pygame.draw.circle(screen, (60, 60, 70), (cx, cy), bass_r, 2)
        # Snare (front centre)
        snare_r = max(4, bass_r // 2)
        pygame.draw.circle(screen, (235, 235, 245), (cx, cy + bass_r + snare_r // 2), snare_r)
        pygame.draw.circle(screen, (50, 50, 60), (cx, cy + bass_r + snare_r // 2), snare_r, 1)
        # Tom-toms (left + right of bass)
        tom_r = max(3, bass_r // 2)
        pygame.draw.circle(screen, (180, 90, 60), (cx - bass_r - 2, cy - 2), tom_r)
        pygame.draw.circle(screen, (60, 30, 18), (cx - bass_r - 2, cy - 2), tom_r, 1)
        pygame.draw.circle(screen, (180, 90, 60), (cx + bass_r + 2, cy - 2), tom_r)
        pygame.draw.circle(screen, (60, 30, 18), (cx + bass_r + 2, cy - 2), tom_r, 1)
        # Cymbals (gold rings above)
        cymb_r = max(3, bass_r // 2 + 1)
        pygame.draw.circle(screen, (220, 180, 60), (cx - bass_r - 4, cy - bass_r), cymb_r)
        pygame.draw.circle(screen, (140, 110, 30), (cx - bass_r - 4, cy - bass_r), cymb_r, 1)
        pygame.draw.circle(screen, (220, 180, 60), (cx + bass_r + 4, cy - bass_r), cymb_r)
        pygame.draw.circle(screen, (140, 110, 30), (cx + bass_r + 4, cy - bass_r), cymb_r, 1)

    def _draw_guitar(self, screen: pygame.Surface, rect: pygame.Rect):
        """Guitar viewed from above (on a stand)."""
        if rect.width <= 4 or rect.height <= 4:
            return
        body_col = (170, 70, 35)
        edge = (70, 30, 14)
        neck = (210, 175, 120)
        # Body (lower oval) and neck (upper rect)
        body_h = int(rect.height * 0.55)
        body_rect = pygame.Rect(rect.x, rect.bottom - body_h, rect.width, body_h)
        neck_rect = pygame.Rect(rect.centerx - max(2, rect.width // 6),
                                rect.y, max(4, rect.width // 3), rect.height - body_h + 4)
        pygame.draw.rect(screen, neck, neck_rect)
        pygame.draw.rect(screen, edge, neck_rect, 1)
        pygame.draw.ellipse(screen, body_col, body_rect)
        pygame.draw.ellipse(screen, edge, body_rect, 1)
        # Sound hole
        hole_r = max(2, body_rect.width // 6)
        pygame.draw.circle(screen, (20, 14, 10), (body_rect.centerx, body_rect.centery), hole_r)
        # Frets
        for i in range(1, 4):
            fy = neck_rect.y + neck_rect.height * i // 4
            pygame.draw.line(screen, edge, (neck_rect.x, fy), (neck_rect.right, fy), 1)

    def _draw_easel(self, screen: pygame.Surface, rect: pygame.Rect):
        """Painter's easel from above: tripod legs + canvas with rough sketch."""
        if rect.width <= 6 or rect.height <= 6:
            return
        wood = (115, 75, 40)
        wood_dark = (70, 44, 24)
        canvas = (245, 240, 222)
        # Tripod legs (three rectangles forming an A)
        leg_w = max(2, rect.width // 14)
        pygame.draw.line(screen, wood, (rect.x + 3, rect.bottom - 2),
                         (rect.centerx, rect.y + 4), leg_w)
        pygame.draw.line(screen, wood, (rect.right - 3, rect.bottom - 2),
                         (rect.centerx, rect.y + 4), leg_w)
        pygame.draw.line(screen, wood_dark, (rect.centerx, rect.y + 6),
                         (rect.centerx, rect.bottom - 4), leg_w)
        # Canvas in centre
        cw = int(rect.width * 0.65)
        ch = int(rect.height * 0.55)
        canvas_rect = pygame.Rect(rect.centerx - cw // 2, rect.y + 4, cw, ch)
        pygame.draw.rect(screen, canvas, canvas_rect)
        pygame.draw.rect(screen, wood_dark, canvas_rect, 2)
        # Sketch strokes: random-ish colored shapes
        sketch_colors = [(200, 80, 60), (60, 110, 180), (60, 160, 90), (220, 180, 60)]
        for i, c in enumerate(sketch_colors):
            sx = canvas_rect.x + 4 + (i * 7) % max(1, canvas_rect.width - 12)
            sy = canvas_rect.y + 4 + ((i * 11) % max(1, canvas_rect.height - 10))
            pygame.draw.line(screen, c, (sx, sy), (sx + 6, sy + 4), 2)
        # Horizon line sketch
        pygame.draw.line(screen, (100, 100, 110),
                         (canvas_rect.x + 4, canvas_rect.centery),
                         (canvas_rect.right - 4, canvas_rect.centery), 1)

    def _draw_locker(self, screen: pygame.Surface, rect: pygame.Rect):
        """A row of school lockers (tall narrow doors)."""
        if rect.width <= 4 or rect.height <= 4:
            return
        body = (78, 110, 150)
        body_dark = (40, 64, 92)
        edge = (24, 38, 58)
        handle = (210, 215, 225)
        pygame.draw.rect(screen, body, rect)
        pygame.draw.rect(screen, edge, rect, 2)
        horizontal = rect.width >= rect.height
        if horizontal:
            n = max(2, rect.width // 28)
            door_w = rect.width / n
            for i in range(n):
                dx = rect.x + int(i * door_w)
                pygame.draw.line(screen, edge, (dx, rect.y), (dx, rect.bottom), 1)
                # Top vent slits
                pygame.draw.line(screen, body_dark,
                                 (dx + 4, rect.y + 5), (dx + int(door_w) - 5, rect.y + 5), 1)
                pygame.draw.line(screen, body_dark,
                                 (dx + 4, rect.y + 9), (dx + int(door_w) - 5, rect.y + 9), 1)
                # Handle
                hx = dx + int(door_w) - 6
                hy = rect.centery
                pygame.draw.rect(screen, handle, (hx, hy - 1, 3, 3))
        else:
            n = max(2, rect.height // 28)
            door_h = rect.height / n
            for i in range(n):
                dy = rect.y + int(i * door_h)
                pygame.draw.line(screen, edge, (rect.x, dy), (rect.right, dy), 1)
                pygame.draw.line(screen, body_dark,
                                 (rect.x + 5, dy + 4), (rect.x + 5, dy + int(door_h) - 5), 1)
                pygame.draw.line(screen, body_dark,
                                 (rect.x + 9, dy + 4), (rect.x + 9, dy + int(door_h) - 5), 1)
                hx = rect.centerx
                hy = dy + int(door_h) - 6
                pygame.draw.rect(screen, handle, (hx - 1, hy, 3, 3))

    def _draw_office_desk(self, screen: pygame.Surface, rect: pygame.Rect, facing: str = "down"):
        """Wood office desk with a small notebook and pen tray."""
        if rect.width <= 6 or rect.height <= 6:
            return
        wood = (148, 110, 70)
        wood_dark = (88, 60, 34)
        paper = (240, 240, 230)
        pen_tray = (60, 50, 40)
        pygame.draw.rect(screen, wood, rect)
        pygame.draw.rect(screen, wood_dark, rect, 2)
        # Notebook + pen tray on the user side
        pad = 4
        if facing == "down":
            paper_rect = pygame.Rect(rect.x + pad + 4, rect.y + pad, max(8, rect.width // 3), max(8, rect.height // 2))
            tray_rect = pygame.Rect(rect.right - rect.width // 3 - pad, rect.y + pad, max(8, rect.width // 4), 6)
        elif facing == "up":
            paper_rect = pygame.Rect(rect.x + pad + 4, rect.bottom - rect.height // 2 - pad, max(8, rect.width // 3), max(8, rect.height // 2))
            tray_rect = pygame.Rect(rect.right - rect.width // 3 - pad, rect.bottom - 10, max(8, rect.width // 4), 6)
        elif facing == "right":
            paper_rect = pygame.Rect(rect.x + pad, rect.y + pad + 4, max(8, rect.width // 2), max(8, rect.height // 3))
            tray_rect = pygame.Rect(rect.x + pad, rect.bottom - rect.height // 3 - pad, 6, max(8, rect.height // 4))
        else:  # left
            paper_rect = pygame.Rect(rect.right - rect.width // 2 - pad, rect.y + pad + 4, max(8, rect.width // 2), max(8, rect.height // 3))
            tray_rect = pygame.Rect(rect.right - 10, rect.bottom - rect.height // 3 - pad, 6, max(8, rect.height // 4))
        pygame.draw.rect(screen, paper, paper_rect)
        pygame.draw.rect(screen, wood_dark, paper_rect, 1)
        # Paper lines
        for i in range(1, 4):
            ly = paper_rect.y + paper_rect.height * i // 4
            pygame.draw.line(screen, (170, 170, 160),
                             (paper_rect.x + 2, ly), (paper_rect.right - 2, ly), 1)
        pygame.draw.rect(screen, pen_tray, tray_rect)
        pygame.draw.rect(screen, (180, 60, 40),
                         (tray_rect.x + 1, tray_rect.y + 1, max(2, tray_rect.width - 6), 2))

    def _draw_office_chair(self, screen: pygame.Surface, rect: pygame.Rect):
        """Small swivel office chair from above (seat + backrest hint)."""
        if rect.width <= 4 or rect.height <= 4:
            return
        seat = (60, 64, 78)
        seat_edge = (30, 32, 44)
        pygame.draw.ellipse(screen, seat, rect)
        pygame.draw.ellipse(screen, seat_edge, rect, 1)
        # Backrest stripe (top)
        back = pygame.Rect(rect.x + 2, rect.y + 1, rect.width - 4, max(2, rect.height // 4))
        pygame.draw.rect(screen, seat_edge, back, border_radius=2)

    def _draw_hospital_bed(self, screen: pygame.Surface, rect: pygame.Rect, facing: str = "down"):
        """Infirmary cot: mattress + pillow + blanket."""
        if rect.width <= 6 or rect.height <= 6:
            return
        frame = (200, 205, 215)
        frame_edge = (110, 115, 130)
        mattress = (245, 248, 252)
        pillow = (235, 240, 250)
        blanket = (180, 70, 80)
        pygame.draw.rect(screen, frame, rect, border_radius=3)
        pygame.draw.rect(screen, frame_edge, rect, 2, border_radius=3)
        inner = rect.inflate(-6, -6)
        if inner.width <= 0 or inner.height <= 0:
            return
        pygame.draw.rect(screen, mattress, inner, border_radius=2)
        if facing == "down":
            pillow_rect = pygame.Rect(inner.x + 2, inner.y + 2, inner.width - 4, max(6, inner.height // 4))
            blanket_rect = pygame.Rect(inner.x + 2, inner.centery, inner.width - 4, inner.bottom - inner.centery - 2)
        elif facing == "up":
            pillow_rect = pygame.Rect(inner.x + 2, inner.bottom - max(6, inner.height // 4) - 2, inner.width - 4, max(6, inner.height // 4))
            blanket_rect = pygame.Rect(inner.x + 2, inner.y + 2, inner.width - 4, inner.centery - inner.y - 2)
        elif facing == "right":
            pillow_rect = pygame.Rect(inner.x + 2, inner.y + 2, max(6, inner.width // 4), inner.height - 4)
            blanket_rect = pygame.Rect(inner.centerx, inner.y + 2, inner.right - inner.centerx - 2, inner.height - 4)
        else:
            pillow_rect = pygame.Rect(inner.right - max(6, inner.width // 4) - 2, inner.y + 2, max(6, inner.width // 4), inner.height - 4)
            blanket_rect = pygame.Rect(inner.x + 2, inner.y + 2, inner.centerx - inner.x - 2, inner.height - 4)
        pygame.draw.rect(screen, blanket, blanket_rect, border_radius=2)
        pygame.draw.rect(screen, pillow, pillow_rect, border_radius=2)
        pygame.draw.rect(screen, frame_edge, pillow_rect, 1, border_radius=2)
        # Red cross on blanket
        cx, cy = blanket_rect.center
        pygame.draw.rect(screen, (240, 240, 240), (cx - 1, cy - 5, 2, 10))
        pygame.draw.rect(screen, (240, 240, 240), (cx - 5, cy - 1, 10, 2))

    def _draw_stage(self, screen: pygame.Surface, rect: pygame.Rect):
        """Auditorium stage: raised wooden platform with red curtains on the sides."""
        if rect.width <= 8 or rect.height <= 8:
            return
        stage_col = (120, 80, 45)
        stage_edge = (60, 38, 18)
        plank_col = (90, 60, 32)
        curtain = (140, 30, 35)
        curtain_dark = (80, 14, 16)
        pygame.draw.rect(screen, stage_col, rect)
        pygame.draw.rect(screen, stage_edge, rect, 2)
        # Planks (parallel to long side)
        if rect.width >= rect.height:
            n = max(4, rect.height // 16)
            for i in range(1, n):
                py = rect.y + rect.height * i // n
                pygame.draw.line(screen, plank_col, (rect.x + 4, py), (rect.right - 4, py), 1)
            # Curtains on left + right
            cw = max(10, rect.width // 12)
            for i in range(4):
                col = curtain if i % 2 == 0 else curtain_dark
                pygame.draw.rect(screen, col,
                                 (rect.x + i * (cw // 4), rect.y, cw // 4 + 1, rect.height))
                pygame.draw.rect(screen, col,
                                 (rect.right - cw + i * (cw // 4), rect.y, cw // 4 + 1, rect.height))
        else:
            n = max(4, rect.width // 16)
            for i in range(1, n):
                px = rect.x + rect.width * i // n
                pygame.draw.line(screen, plank_col, (px, rect.y + 4), (px, rect.bottom - 4), 1)
            ch = max(10, rect.height // 12)
            for i in range(4):
                col = curtain if i % 2 == 0 else curtain_dark
                pygame.draw.rect(screen, col,
                                 (rect.x, rect.y + i * (ch // 4), rect.width, ch // 4 + 1))
                pygame.draw.rect(screen, col,
                                 (rect.x, rect.bottom - ch + i * (ch // 4), rect.width, ch // 4 + 1))

    def _draw_auditorium_seat(self, screen: pygame.Surface, rect: pygame.Rect):
        """Folding theatre seat from above."""
        if rect.width <= 3 or rect.height <= 3:
            return
        cushion = (120, 30, 40)
        edge = (60, 14, 20)
        back = (90, 22, 30)
        pygame.draw.rect(screen, cushion, rect, border_radius=2)
        pygame.draw.rect(screen, edge, rect, 1, border_radius=2)
        # Backrest hint along the back edge
        if rect.height >= rect.width:
            pygame.draw.rect(screen, back, (rect.x, rect.y, rect.width, max(2, rect.height // 3)))
        else:
            pygame.draw.rect(screen, back, (rect.x, rect.y, max(2, rect.width // 3), rect.height))

    def _draw_executive_desk(self, screen: pygame.Surface, rect: pygame.Rect):
        """Large director's desk: dark hardwood, gold trim, blotter and pen."""
        if rect.width <= 8 or rect.height <= 8:
            return
        wood = (78, 46, 24)
        wood_hi = (130, 80, 44)
        edge = (40, 22, 12)
        gold = (212, 168, 80)
        blotter = (24, 28, 48)
        paper = (245, 240, 220)
        pygame.draw.rect(screen, wood, rect)
        # Top highlight band
        pygame.draw.rect(screen, wood_hi, (rect.x, rect.y, rect.width, max(3, rect.height // 8)))
        pygame.draw.rect(screen, edge, rect, 3)
        # Gold trim inside
        trim = rect.inflate(-6, -6)
        if trim.width > 0 and trim.height > 0:
            pygame.draw.rect(screen, gold, trim, 1)
        # Leather blotter in centre
        blot_w = int(rect.width * 0.55)
        blot_h = int(rect.height * 0.55)
        blot_rect = pygame.Rect(rect.centerx - blot_w // 2,
                                rect.centery - blot_h // 2, blot_w, blot_h)
        pygame.draw.rect(screen, blotter, blot_rect, border_radius=3)
        pygame.draw.rect(screen, gold, blot_rect, 1, border_radius=3)
        # Paper sheet on blotter
        sheet = blot_rect.inflate(-int(blot_rect.width * 0.3), -int(blot_rect.height * 0.3))
        pygame.draw.rect(screen, paper, sheet)
        pygame.draw.rect(screen, edge, sheet, 1)
        for i in range(1, 4):
            ly = sheet.y + sheet.height * i // 4
            pygame.draw.line(screen, (170, 165, 140),
                             (sheet.x + 2, ly), (sheet.right - 2, ly), 1)

    def _draw_sofa_chair(self, screen: pygame.Surface, rect: pygame.Rect):
        """Plush executive sofa-chair from above."""
        if rect.width <= 6 or rect.height <= 6:
            return
        upholstery = (74, 36, 30)
        cushion = (110, 60, 48)
        edge = (30, 14, 12)
        pygame.draw.rect(screen, upholstery, rect, border_radius=6)
        pygame.draw.rect(screen, edge, rect, 2, border_radius=6)
        # Inner cushion
        inner = rect.inflate(-8, -8)
        if inner.width > 0 and inner.height > 0:
            pygame.draw.rect(screen, cushion, inner, border_radius=4)
            pygame.draw.rect(screen, edge, inner, 1, border_radius=4)
            # Tufting dots
            for dx in (inner.x + inner.width // 3, inner.x + 2 * inner.width // 3):
                for dy in (inner.y + inner.height // 3, inner.y + 2 * inner.height // 3):
                    pygame.draw.circle(screen, edge, (dx, dy), 1)

    def _draw_umbrella_table(self, screen: pygame.Surface, rect: pygame.Rect):
        """Patio table with parasol umbrella covering it (umbrella above the table)."""
        if rect.width <= 6 or rect.height <= 6:
            return
        cx, cy = rect.centerx, rect.centery
        radius = min(rect.width, rect.height) // 2 - 2
        if radius <= 2:
            return
        # Table (lighter ring underneath)
        pygame.draw.circle(screen, (210, 200, 180), (cx, cy), radius - 2)
        pygame.draw.circle(screen, (110, 100, 80), (cx, cy), radius - 2, 1)
        # Umbrella canopy: alternating wedges
        wedge_colors = [(220, 70, 60), (240, 240, 240)]
        import math as _math
        seg = 8
        for i in range(seg):
            a0 = (i / seg) * _math.tau - _math.pi / 2
            a1 = ((i + 1) / seg) * _math.tau - _math.pi / 2
            pts = [
                (cx, cy),
                (cx + radius * _math.cos(a0), cy + radius * _math.sin(a0)),
                (cx + radius * _math.cos((a0 + a1) / 2), cy + radius * _math.sin((a0 + a1) / 2)),
                (cx + radius * _math.cos(a1), cy + radius * _math.sin(a1)),
            ]
            pygame.draw.polygon(screen, wedge_colors[i % 2], pts)
        pygame.draw.circle(screen, (60, 40, 30), (cx, cy), radius, 2)
        # Centre pole
        pygame.draw.circle(screen, (40, 30, 22), (cx, cy), max(2, radius // 7))

    def _draw_bench(self, screen: pygame.Surface, rect: pygame.Rect):
        """Top-down wooden park bench with slat details and metal armrests."""
        if rect.width <= 4 or rect.height <= 4:
            return
        wood_col = (160, 105, 60)
        wood_dark = (110, 70, 35)
        metal = (60, 65, 70)
        pygame.draw.rect(screen, wood_col, rect, border_radius=3)
        pygame.draw.rect(screen, wood_dark, rect, 2, border_radius=3)
        # Wooden slats
        if rect.width >= rect.height:
            slat_h = max(2, rect.height // 4)
            pygame.draw.line(screen, wood_dark, (rect.left + 4, rect.y + slat_h), (rect.right - 4, rect.y + slat_h), 1)
            pygame.draw.line(screen, wood_dark, (rect.left + 4, rect.centery), (rect.right - 4, rect.centery), 1)
            pygame.draw.line(screen, wood_dark, (rect.left + 4, rect.bottom - slat_h), (rect.right - 4, rect.bottom - slat_h), 1)
            # Metal armrests at ends
            pygame.draw.rect(screen, metal, (rect.left + 2, rect.y + 1, 4, rect.height - 2), border_radius=1)
            pygame.draw.rect(screen, metal, (rect.right - 6, rect.y + 1, 4, rect.height - 2), border_radius=1)
        else:
            slat_w = max(2, rect.width // 4)
            pygame.draw.line(screen, wood_dark, (rect.x + slat_w, rect.top + 4), (rect.x + slat_w, rect.bottom - 4), 1)
            pygame.draw.line(screen, wood_dark, (rect.centerx, rect.top + 4), (rect.centerx, rect.bottom - 4), 1)
            pygame.draw.line(screen, wood_dark, (rect.right - slat_w, rect.top + 4), (rect.right - slat_w, rect.bottom - 4), 1)
            pygame.draw.rect(screen, metal, (rect.x + 1, rect.top + 2, rect.width - 2, 4), border_radius=1)
            pygame.draw.rect(screen, metal, (rect.x + 1, rect.bottom - 6, rect.width - 2, 4), border_radius=1)

    def _draw_plant(self, screen: pygame.Surface, rect: pygame.Rect, color: tuple):
        """Top-down potted plant with ceramic pot and lush leaves."""
        if rect.width <= 4 or rect.height <= 4:
            return
        if "maceta" not in self._tile_cache:
            try:
                img = pygame.image.load("assets/UI/maceta.png").convert_alpha()
                self._tile_cache["maceta"] = img
            except Exception:
                self._tile_cache["maceta"] = None

        maceta_img = self._tile_cache.get("maceta")
        if maceta_img:
            disp_w = int(rect.width * 2.8)
            disp_h = int(rect.height * 2.8)
            scaled_img = pygame.transform.smoothscale(maceta_img, (disp_w, disp_h))
            blit_x = rect.centerx - disp_w // 2
            blit_y = rect.bottom - disp_h
            screen.blit(scaled_img, (blit_x, blit_y))
        else:
            # Pot
            pygame.draw.circle(screen, (139, 69, 19), rect.center, rect.width // 3)
            # Leaves
            pygame.draw.circle(screen, color, (rect.centerx - 4, rect.centery - 4), rect.width // 2)
            pygame.draw.circle(screen, (34, 139, 34), (rect.centerx + 4, rect.centery + 4), rect.width // 2)
            pygame.draw.circle(screen, color, (rect.centerx, rect.centery), rect.width // 2)

    def _draw_chalkboard(self, screen: pygame.Surface, rect: pygame.Rect, facing: str = "up"):
        """Portable green chalkboard with wooden frame and two wheels.

        ``facing`` controls which side the wheels protrude from (the side
        opposite to the user / facing direction).
        """
        if rect.width <= 8 or rect.height <= 8:
            return
        wood = (140, 90, 50)
        wood_dark = (78, 48, 24)
        wood_hi = (180, 130, 80)
        board = (40, 95, 60)        # classic chalkboard green
        board_edge = (22, 60, 38)
        chalk = (220, 230, 215)
        wheel_dark = (35, 35, 42)
        wheel_rim = (185, 188, 200)

        # Outer wooden frame
        pygame.draw.rect(screen, wood, rect)
        pygame.draw.rect(screen, wood_dark, rect, 2)
        # Subtle highlight on the top edge for a wood grain feel
        pygame.draw.line(screen, wood_hi,
                         (rect.x + 2, rect.y + 1), (rect.right - 2, rect.y + 1), 1)

        # Inner green board
        pad = max(3, min(rect.width, rect.height) // 8)
        inner = rect.inflate(-pad * 2, -pad * 2)
        if inner.width > 0 and inner.height > 0:
            pygame.draw.rect(screen, board, inner)
            pygame.draw.rect(screen, board_edge, inner, 1)
            # A few chalk strokes / equation hints
            if inner.width > 30 and inner.height > 16:
                # Top-left smudge lines
                for i in range(2):
                    sy = inner.y + 4 + i * 4
                    pygame.draw.line(screen, chalk,
                                     (inner.x + 4, sy),
                                     (inner.x + max(6, inner.width // 3), sy), 1)
                # Centre equation: a small "+" and "="
                cx_, cy_ = inner.center
                pygame.draw.line(screen, chalk, (cx_ - 9, cy_), (cx_ - 3, cy_), 2)
                pygame.draw.line(screen, chalk, (cx_ - 6, cy_ - 3), (cx_ - 6, cy_ + 3), 2)
                pygame.draw.line(screen, chalk, (cx_ + 2, cy_ - 1), (cx_ + 8, cy_ - 1), 2)
                pygame.draw.line(screen, chalk, (cx_ + 2, cy_ + 1), (cx_ + 8, cy_ + 1), 2)
            # Chalk tray ledge on the bottom of the frame (small wood bar)
            tray_h = max(2, pad - 1)
            tray_rect = pygame.Rect(inner.x - 2, inner.bottom + 1, inner.width + 4, tray_h)
            if tray_rect.width > 0 and tray_rect.height > 0 and tray_rect.bottom <= rect.bottom:
                pygame.draw.rect(screen, wood_hi, tray_rect)
                pygame.draw.rect(screen, wood_dark, tray_rect, 1)
                # A piece of chalk
                pygame.draw.rect(screen, chalk,
                                 (tray_rect.x + 4, tray_rect.y + 1, 6, max(1, tray_h - 2)))

        # Two wheels at the base (side opposite of "facing")
        wheel_r = max(3, min(rect.width, rect.height) // 8)
        if facing == "up":
            wheels = [
                (rect.x + wheel_r + 2, rect.bottom + wheel_r - 1),
                (rect.right - wheel_r - 2, rect.bottom + wheel_r - 1),
            ]
        elif facing == "down":
            wheels = [
                (rect.x + wheel_r + 2, rect.y - wheel_r + 1),
                (rect.right - wheel_r - 2, rect.y - wheel_r + 1),
            ]
        elif facing == "left":
            wheels = [
                (rect.right + wheel_r - 1, rect.y + wheel_r + 2),
                (rect.right + wheel_r - 1, rect.bottom - wheel_r - 2),
            ]
        else:  # right
            wheels = [
                (rect.x - wheel_r + 1, rect.y + wheel_r + 2),
                (rect.x - wheel_r + 1, rect.bottom - wheel_r - 2),
            ]
        for wx, wy in wheels:
            pygame.draw.circle(screen, wheel_dark, (wx, wy), wheel_r)
            pygame.draw.circle(screen, wheel_rim, (wx, wy), wheel_r, 1)
            # Hub spot
            pygame.draw.circle(screen, wheel_rim, (wx, wy), max(1, wheel_r // 3))

    def _draw_sink(self, screen: pygame.Surface, rect: pygame.Rect, facing: str = "down"):
        """Bathroom sink (lavamanos) seen from above.

        Porcelain basin with an inner bowl, a drain in the centre and a
        chrome faucet on the wall side (opposite to ``facing``).
        """
        if rect.width <= 6 or rect.height <= 6:
            return
        porcelain = (245, 247, 250)
        porcelain_in = (210, 218, 228)
        porcelain_deep = (175, 185, 200)
        edge = (130, 138, 150)
        chrome = (195, 200, 210)
        chrome_dark = (115, 120, 130)
        drain = (70, 78, 92)

        # Outer porcelain rim
        pygame.draw.rect(screen, porcelain, rect, border_radius=3)
        pygame.draw.rect(screen, edge, rect, 1, border_radius=3)

        # Inner bowl
        pad = max(2, min(rect.width, rect.height) // 5)
        inner = rect.inflate(-pad * 2, -pad * 2)
        if inner.width > 1 and inner.height > 1:
            pygame.draw.rect(screen, porcelain_in, inner, border_radius=2)
            pygame.draw.rect(screen, edge, inner, 1, border_radius=2)
            # Soft shadow on the inside (deeper bowl tone, top + left)
            if inner.width > 6 and inner.height > 6:
                pygame.draw.line(screen, porcelain_deep,
                                 (inner.x + 1, inner.y + 1),
                                 (inner.right - 2, inner.y + 1), 1)
                pygame.draw.line(screen, porcelain_deep,
                                 (inner.x + 1, inner.y + 1),
                                 (inner.x + 1, inner.bottom - 2), 1)
            # Drain hole
            drain_r = max(1, min(inner.width, inner.height) // 5)
            pygame.draw.circle(screen, drain, inner.center, drain_r)
            pygame.draw.circle(screen, (30, 30, 38), inner.center, max(1, drain_r // 2))

        # Faucet: small chrome spout + handle on the wall side (opposite ``facing``)
        if facing == "down":   # user stands south → wall is north
            sw_ = max(3, rect.width // 5)
            sh_ = max(4, rect.height // 4)
            base = pygame.Rect(rect.centerx - sw_ // 2, rect.y - 1, sw_, sh_)
            spout = pygame.Rect(rect.centerx - max(1, sw_ // 4),
                                base.bottom - 1,
                                max(2, sw_ // 2),
                                max(3, sh_ // 2))
            # Side handles
            handle_w = max(2, sw_ // 3)
            lh = pygame.Rect(base.x - handle_w - 1, base.y + sh_ // 4, handle_w, max(3, sh_ // 2))
            rh = pygame.Rect(base.right + 1,        base.y + sh_ // 4, handle_w, max(3, sh_ // 2))
        elif facing == "up":   # user stands north → wall is south
            sw_ = max(3, rect.width // 5)
            sh_ = max(4, rect.height // 4)
            base = pygame.Rect(rect.centerx - sw_ // 2, rect.bottom - sh_ + 1, sw_, sh_)
            spout = pygame.Rect(rect.centerx - max(1, sw_ // 4),
                                base.y - max(3, sh_ // 2) + 1,
                                max(2, sw_ // 2),
                                max(3, sh_ // 2))
            handle_w = max(2, sw_ // 3)
            lh = pygame.Rect(base.x - handle_w - 1, base.y + sh_ // 4, handle_w, max(3, sh_ // 2))
            rh = pygame.Rect(base.right + 1,        base.y + sh_ // 4, handle_w, max(3, sh_ // 2))
        elif facing == "left": # user stands west → wall is east
            sw_ = max(3, rect.height // 5)
            sh_ = max(4, rect.width // 4)
            base = pygame.Rect(rect.right - sh_ + 1, rect.centery - sw_ // 2, sh_, sw_)
            spout = pygame.Rect(base.x - max(3, sh_ // 2) + 1,
                                rect.centery - max(1, sw_ // 4),
                                max(3, sh_ // 2),
                                max(2, sw_ // 2))
            handle_w = max(2, sw_ // 3)
            lh = pygame.Rect(base.x + sh_ // 4, base.y - handle_w - 1, max(3, sh_ // 2), handle_w)
            rh = pygame.Rect(base.x + sh_ // 4, base.bottom + 1,       max(3, sh_ // 2), handle_w)
        else:                  # right: user east → wall west
            sw_ = max(3, rect.height // 5)
            sh_ = max(4, rect.width // 4)
            base = pygame.Rect(rect.x - 1, rect.centery - sw_ // 2, sh_, sw_)
            spout = pygame.Rect(base.right - 1,
                                rect.centery - max(1, sw_ // 4),
                                max(3, sh_ // 2),
                                max(2, sw_ // 2))
            handle_w = max(2, sw_ // 3)
            lh = pygame.Rect(base.x + sh_ // 4, base.y - handle_w - 1, max(3, sh_ // 2), handle_w)
            rh = pygame.Rect(base.x + sh_ // 4, base.bottom + 1,       max(3, sh_ // 2), handle_w)

        for fr_ in (base, spout, lh, rh):
            pygame.draw.rect(screen, chrome, fr_)
            pygame.draw.rect(screen, chrome_dark, fr_, 1)

    def draw_foreground(self, screen, camera, player):
        sw, sh = screen.get_width(), screen.get_height()
        
        if self.id == 0:
            # Draw top-down facades matching a city-street style reference.
            building_specs = [
                ("c_building", {
                    "wall_color": (145, 164, 188),
                    "trim_color": (68, 82, 104),
                    "window_color": (145, 190, 220),
                    "window_cols": 3,
                    "window_rows": 2,
                    "window_mode": "grid",
                    "sign": "MAIN BUILDING",
                    "entry": "double_glass",
                    "rooftop": True,
                }),
                ("c_tennis", {
                    "wall_color": (188, 168, 132),
                    "trim_color": (92, 78, 58),
                    "window_color": (152, 196, 222),
                    "window_cols": 2,
                    "window_rows": 1,
                    "window_mode": "double_normal",
                    "sign": "PING PONG",
                    "entry": "pingpong_icon",
                    "rooftop": False,
                }),
                ("c_coliseum", {
                    "wall_color": (170, 163, 146),
                    "trim_color": (90, 84, 68),
                    "window_color": (145, 184, 208),
                    "window_cols": 2,
                    "window_rows": 1,
                    "window_mode": "double_large",
                    "sign": "ATHLETIC COLISEUM",
                    "entry": "gate",
                    "rooftop": False,
                }),
            ]

            for rid, spec in building_specs:
                room = self.rooms.get(rid)
                if room:
                    rr = camera.apply_rect(room.rect)
                    if rr.right > 0 and rr.left < sw and rr.bottom > 0 and rr.top < sh:
                        roof_h = max(20, int(rr.height * 0.2))
                        facade_h = max(90, int(rr.height * 0.45))
                        body_rect = pygame.Rect(rr.x, rr.y, rr.width, rr.height)
                        facade_rect = pygame.Rect(rr.x, rr.bottom - facade_h, rr.width, facade_h)
                        roof_rect = pygame.Rect(rr.x, rr.y, rr.width, roof_h)
                        sidewalk_rect = pygame.Rect(rr.x, rr.bottom + 2, rr.width, 20)

                        pygame.draw.rect(screen, spec["wall_color"], body_rect)
                        pygame.draw.line(screen, spec["trim_color"],
                                         (body_rect.x + 2, body_rect.y + 2),
                                         (body_rect.right - 3, body_rect.y + 2), 2)
                        pygame.draw.line(screen, (50, 50, 56),
                                         (body_rect.x + 2, body_rect.bottom - 3),
                                         (body_rect.right - 3, body_rect.bottom - 3), 2)
                        pygame.draw.rect(screen, spec["trim_color"], body_rect, 3)

                        if spec["rooftop"]:
                            rooftop = pygame.Rect(rr.x + 10, rr.y + 10, rr.width - 20, rr.height - facade_h - 16)
                            # Fill the rooftop with the same tile used on the Rooftop floor
                            rt_tile_path = "data/tiles/piso_rooftop.png"
                            if rt_tile_path not in self._tile_cache:
                                try:
                                    self._tile_cache[rt_tile_path] = pygame.image.load(rt_tile_path).convert()
                                except Exception:
                                    self._tile_cache[rt_tile_path] = None
                            rt_tile = self._tile_cache.get(rt_tile_path)
                            if rt_tile is not None:
                                old_clip = screen.get_clip()
                                screen.set_clip(rooftop)
                                tw, th = rt_tile.get_size()
                                for ty in range(rooftop.y, rooftop.bottom, th):
                                    for tx in range(rooftop.x, rooftop.right, tw):
                                        screen.blit(rt_tile, (tx, ty))
                                screen.set_clip(old_clip)
                            else:
                                pygame.draw.rect(screen, (110, 122, 142), rooftop)
                            pygame.draw.rect(screen, (70, 82, 102), rooftop, 3)
                            # Keep a pair of A/C units in the back corner
                            ac1 = pygame.Rect(rooftop.x + 20, rooftop.y + 20, 46, 26)
                            ac2 = pygame.Rect(rooftop.right - 70, rooftop.y + 28, 50, 28)
                            pygame.draw.rect(screen, (82, 88, 98), ac1)
                            pygame.draw.rect(screen, (82, 88, 98), ac2)
                            pygame.draw.rect(screen, (48, 54, 64), ac1, 2)
                            pygame.draw.rect(screen, (48, 54, 64), ac2, 2)
                            # Rooftop walls (stairwell housing and terrace parapets)
                            wt = 12
                            rt_walls = [
                                # Top parapet wall
                                pygame.Rect(rooftop.x + 160, rooftop.y + 90, 760, wt),
                                # Left parapet wall (upper piece)
                                pygame.Rect(rooftop.x + 160, rooftop.y + 90, wt, 85),
                                # Left parapet wall (lower piece, leaving a doorway gap)
                                pygame.Rect(rooftop.x + 160, rooftop.y + 225, wt, 127),
                                # Right parapet wall (upper piece)
                                pygame.Rect(rooftop.x + 908, rooftop.y + 90, wt, 85),
                                # Right parapet wall (lower piece, leaving a doorway gap)
                                pygame.Rect(rooftop.x + 908, rooftop.y + 225, wt, 127),
                                # Bottom parapet wall (right half only, leaving left half open)
                                pygame.Rect(rooftop.x + 540, rooftop.y + 340, 380, wt),
                            ]
                            self.windowed_walls = [rt_walls[-1]]
                            for rw in rt_walls:
                                self._draw_topdown_wall(screen, rw, wall=rw)
                            # 3D Staircase (top-left, fitting exactly in the corner, horizontal climb)
                            stair_rect = pygame.Rect(rooftop.x + 75, rooftop.y + 20, 85, 70)
                            font14 = pygame.font.Font(VT323_PATH, 14)
                            self._draw_staircase_3d(screen, stair_rect, font14)
                            # Parasol umbrellas matching the Rooftop Terrace layout
                            umbrella_layout = [
                                (0.28, 0.32),
                                (0.58, 0.32),
                                (0.28, 0.58),
                                (0.58, 0.58),
                                (0.43, 0.45),
                            ]
                            umbrella_r = max(7, min(rooftop.width, rooftop.height) // 15)
                            import math as _math
                            for fx, fy in umbrella_layout:
                                cx = int(rooftop.x + fx * rooftop.width)
                                cy = int(rooftop.y + fy * rooftop.height)
                                # Four chairs around the umbrella table
                                cw = max(6, int(umbrella_r * 0.55))
                                ch = max(6, int(umbrella_r * 0.5))
                                tr = umbrella_r
                                self._draw_sofa_chair(screen, pygame.Rect(cx - cw // 2, cy - tr - ch - 3, cw, ch))
                                self._draw_sofa_chair(screen, pygame.Rect(cx - cw // 2, cy + tr + 3, cw, ch))
                                self._draw_sofa_chair(screen, pygame.Rect(cx - tr - cw - 3, cy - ch // 2, cw, ch))
                                self._draw_sofa_chair(screen, pygame.Rect(cx + tr + 3, cy - ch // 2, cw, ch))
                                # Soft drop shadow
                                shadow_surf = pygame.Surface((umbrella_r * 2 + 4, umbrella_r * 2 + 4), pygame.SRCALPHA)
                                pygame.draw.circle(shadow_surf, (0, 0, 0, 80),
                                                   (umbrella_r + 2, umbrella_r + 2), umbrella_r + 1)
                                screen.blit(shadow_surf, (cx - umbrella_r - 2 + 2, cy - umbrella_r - 2 + 3))
                                # Alternating red/white wedges
                                seg = 8
                                wedges = [(212, 60, 56), (245, 245, 240)]
                                for i in range(seg):
                                    a0 = (i / seg) * _math.tau - _math.pi / 2
                                    a1 = ((i + 1) / seg) * _math.tau - _math.pi / 2
                                    pts = [
                                        (cx, cy),
                                        (cx + umbrella_r * _math.cos(a0), cy + umbrella_r * _math.sin(a0)),
                                        (cx + umbrella_r * _math.cos((a0 + a1) / 2),
                                         cy + umbrella_r * _math.sin((a0 + a1) / 2)),
                                        (cx + umbrella_r * _math.cos(a1), cy + umbrella_r * _math.sin(a1)),
                                    ]
                                    pygame.draw.polygon(screen, wedges[i % 2], pts)
                                pygame.draw.circle(screen, (70, 45, 32), (cx, cy), umbrella_r, 1)
                                # Centre pole tip
                                pygame.draw.circle(screen, (40, 30, 22), (cx, cy), max(2, umbrella_r // 5))
                            # Resting Area furniture (benches and planters) outside bottom parapet
                            for bx in (rooftop.x + 260, rooftop.x + 480, rooftop.x + 700):
                                self._draw_bench(screen, pygame.Rect(bx, rooftop.y + 390, 90, 32))
                            for px in (rooftop.x + 200, rooftop.x + 395, rooftop.x + 615, rooftop.x + 835):
                                self._draw_plant(screen, pygame.Rect(px, rooftop.y + 388, 36, 36), (40, 160, 60))
                        pygame.draw.rect(screen, spec["wall_color"], facade_rect)
                        pygame.draw.rect(screen, spec["trim_color"], facade_rect, 3)
                        if spec["rooftop"]:
                            sign_rect = pygame.Rect(facade_rect.x + 14, facade_rect.y + 8, facade_rect.width - 28, 26)
                        else:
                            sign_rect = pygame.Rect(facade_rect.x + 14, facade_rect.y + 38, facade_rect.width - 28, 26)
                        pygame.draw.rect(screen, (72, 72, 82), sign_rect)
                        pygame.draw.rect(screen, (205, 205, 215), sign_rect, 2)
                        sign_font = pygame.font.Font(VT323_PATH, max(11, min(17, sign_rect.height - 7)))
                        sign_txt = sign_font.render(spec["sign"], True, (230, 232, 240))
                        screen.blit(sign_txt, (sign_rect.centerx - sign_txt.get_width() // 2,
                                               sign_rect.centery - sign_txt.get_height() // 2))

                        door_w = max(56, min(110, int(facade_rect.width * 0.18)))
                        if spec["entry"] == "double_glass":
                            door_w = max(120, min(200, int(facade_rect.width * 0.34)))
                        door_h = max(46, int(facade_rect.height * 0.56))
                        door_rect = pygame.Rect(
                            facade_rect.centerx - door_w // 2,
                            facade_rect.bottom - door_h - 4,
                            door_w,
                            door_h,
                        )
                        if spec["entry"] == "double_glass":
                            pygame.draw.rect(screen, (80, 115, 142), door_rect)
                            pygame.draw.rect(screen, (42, 54, 68), door_rect, 2)
                            pygame.draw.line(screen, (220, 230, 240),
                                             (door_rect.centerx, door_rect.y + 2),
                                             (door_rect.centerx, door_rect.bottom - 3), 2)
                            pygame.draw.rect(screen, (210, 226, 240),
                                             (door_rect.x + 6, door_rect.y + 6, 8, door_rect.height - 14), 1)
                            pygame.draw.rect(screen, (210, 226, 240),
                                             (door_rect.right - 14, door_rect.y + 6, 8, door_rect.height - 14), 1)
                        elif spec["entry"] == "gate":
                            pygame.draw.rect(screen, (82, 72, 66), door_rect)
                            pygame.draw.rect(screen, (45, 38, 35), door_rect, 2)
                            for gx in range(door_rect.x + 8, door_rect.right - 6, 10):
                                pygame.draw.line(screen, (34, 30, 28),
                                                 (gx, door_rect.y + 4), (gx, door_rect.bottom - 4), 2)
                            pygame.draw.rect(screen, (118, 108, 92),
                                             (door_rect.x + 2, door_rect.y + 2, door_rect.width - 4, 6))
                        else:
                            pygame.draw.rect(screen, (86, 116, 124), door_rect)
                            pygame.draw.rect(screen, (38, 48, 54), door_rect, 2)
                            icon_cx, icon_cy = door_rect.centerx, door_rect.y + 14
                            pygame.draw.circle(screen, (235, 245, 250), (icon_cx - 10, icon_cy), 5)
                            pygame.draw.circle(screen, (255, 165, 85), (icon_cx + 8, icon_cy), 4)
                            pygame.draw.rect(screen, (222, 182, 120), (icon_cx - 2, icon_cy + 6, 9, 3))

                        # Building Nameplate
                        if rid == "c_building":
                            font_title = pygame.font.Font(VT323_PATH, 24)
                            text = font_title.render("RAVENSIDE HIGH SCHOOL", True, (220, 230, 240))
                            tw, th = text.get_size()
                            tx = door_rect.centerx - tw // 2
                            ty = door_rect.y - th - 15
                            plate = pygame.Rect(tx - 10, ty - 5, tw + 20, th + 10)
                            pygame.draw.rect(screen, (40, 45, 55), plate, border_radius=3)
                            pygame.draw.rect(screen, (80, 95, 110), plate, 1, border_radius=3)
                            screen.blit(text, (tx, ty))

                        mode = spec.get("window_mode", "grid")
                        if mode in ("double_large", "double_normal"):
                            side_margin = max(26, int(facade_rect.width * 0.1))
                            top_margin = 46
                            gap = max(24, int(facade_rect.width * 0.08))
                            cell_h = max(28, int(facade_rect.height * (0.23 if mode == "double_large" else 0.16)))
                            usable_w = facade_rect.width - 2 * side_margin - gap
                            cell_w = max(52, usable_w // 2)
                            wx1 = facade_rect.x + side_margin
                            wx2 = wx1 + cell_w + gap
                            wy = facade_rect.y + top_margin
                            for wx in (wx1, wx2):
                                win = pygame.Rect(wx, wy, cell_w, cell_h)
                                pygame.draw.rect(screen, spec["window_color"], win)
                                pygame.draw.rect(screen, spec["trim_color"], win, 2)
                                pygame.draw.line(screen, (210, 230, 245),
                                                 (win.x + 3, win.y + 3), (win.x + 3, win.bottom - 4), 1)
                        else:
                            cols = spec["window_cols"]
                            rows = spec["window_rows"]
                            side_margin = max(14, int(facade_rect.width * 0.07))
                            top_margin = 42
                            bottom_margin = max(10, int(facade_rect.height * 0.1))
                            usable_w = facade_rect.width - (2 * side_margin)
                            usable_h = facade_rect.height - top_margin - bottom_margin
                            cell_w = max(32, usable_w // max(1, cols * 2 - 1))
                            cell_h = max(18, usable_h // max(1, rows * 2))
                            x_gap = max(10, (usable_w - cols * cell_w) // max(1, cols - 1))
                            y_gap = max(8, (usable_h - rows * cell_h) // max(1, rows - 1))

                            for row in range(rows):
                                wy = facade_rect.y + top_margin + row * (cell_h + y_gap)
                                for col in range(cols):
                                    wx = facade_rect.x + side_margin + col * (cell_w + x_gap)
                                    win = pygame.Rect(wx, wy, cell_w, cell_h)
                                    if win.colliderect(door_rect.inflate(24, 8)):
                                        continue
                                    pygame.draw.rect(screen, spec["window_color"], win)
                                    pygame.draw.rect(screen, spec["trim_color"], win, 2)
                                    pygame.draw.line(
                                        screen,
                                        (210, 230, 245),
                                        (win.x + 3, win.y + 3),
                                        (win.x + 3, win.bottom - 4),
                                        1,
                                    )

                        pygame.draw.rect(screen, (168, 168, 176), sidewalk_rect)
                        pygame.draw.line(screen, (210, 210, 220),
                                         (sidewalk_rect.x, sidewalk_rect.y + 2),
                                         (sidewalk_rect.right, sidewalk_rect.y + 2), 2)
                        pygame.draw.line(screen, (110, 110, 120),
                                         (sidewalk_rect.x, sidewalk_rect.bottom - 2),
                                         (sidewalk_rect.right, sidewalk_rect.bottom - 2), 2)
                            
    def draw_roofs(self, screen, camera, player):
        """Draw overhanging tiled roofs after players and NPCs so characters pass underneath."""
        sw, sh = screen.get_width(), screen.get_height()
        if self.id == 0:
            building_specs = [
                ("c_tennis", {"rooftop": False}),
                ("c_coliseum", {"rooftop": False}),
            ]
            for rid, spec in building_specs:
                room = self.rooms.get(rid)
                if room:
                    rr = camera.apply_rect(room.rect)
                    if rr.right > -100 and rr.left < sw + 100 and rr.bottom > -100 and rr.top < sh + 100:
                        facade_h = max(90, int(rr.height * 0.45))
                        # Tiled roof sticks out much more: 36px on sides, 36px overhang in front
                        full_roof = pygame.Rect(rr.x - 36, rr.y - 20, rr.width + 72, rr.height - facade_h + 36)
                        pygame.draw.rect(screen, (120, 85, 60), full_roof)
                        tile_w = 16
                        tile_h = 12
                        old_clip = screen.get_clip()
                        screen.set_clip(full_roof)
                        for ty in range(full_roof.y, full_roof.bottom, tile_h):
                            shadow_y = ty + tile_h - 2
                            pygame.draw.line(screen, (80, 55, 35), (full_roof.x, shadow_y), (full_roof.right, shadow_y), 2)
                            pygame.draw.line(screen, (55, 35, 20), (full_roof.x, shadow_y + 1), (full_roof.right, shadow_y + 1), 1)
                            pygame.draw.line(screen, (155, 115, 85), (full_roof.x, ty), (full_roof.right, ty), 1)
                            for tx in range(full_roof.x, full_roof.right, tile_w):
                                pygame.draw.line(screen, (90, 60, 40), (tx, ty), (tx, ty + tile_h), 2)
                                pygame.draw.line(screen, (145, 105, 75), (tx + 2, ty), (tx + 2, ty + tile_h), 1)
                        screen.set_clip(old_clip)
                        pygame.draw.rect(screen, (70, 45, 30), full_roof, 3)
                        pygame.draw.line(screen, (45, 30, 20), (full_roof.x, full_roof.bottom - 1), (full_roof.right, full_roof.bottom - 1), 2)
                        pygame.draw.line(screen, (30, 30, 35), (rr.x - 20, full_roof.bottom), (rr.right + 20, full_roof.bottom), 6)

    def draw_top_layer(self, screen, camera):
        """Draw elements that should be above everything else (like tree canopies)."""
        sw, sh = screen.get_width(), screen.get_height()
        if self.id == 0:
            if hasattr(self, 'garden_decorations'):
                for item in self.garden_decorations:
                    if item[0] == 'tree':
                        _, tx, ty, rad = item
                        sx, sy = camera.apply_pos(tx, ty)
                        draw_rad = rad * 2
                        if -60 < sx < sw + 60 and -60 < sy < sh + 60:
                            # Shadow/Outline
                            pygame.draw.circle(screen, (20, 40, 20), (sx + 4, sy + 4), draw_rad)
                            # Canopy
                            pygame.draw.circle(screen, (34, 100, 34), (sx, sy), draw_rad)
                            # Highlight
                            pygame.draw.circle(screen, (40, 120, 40),
                                               (sx - int(draw_rad * 0.2), sy - int(draw_rad * 0.2)),
                                               int(draw_rad * 0.7))
        elif self.id == 5 and hasattr(self, "basketball_court"):
            bc = self.basketball_court
            cam_ox = int(camera.offset.x)
            cam_oy = int(camera.offset.y)
            court_x = bc.x - cam_ox
            court_y = bc.y - cam_oy
            
            # Check visibility (size is 848x694)
            if -848 < court_x < sw and -694 < court_y < sh and not getattr(self, "hide_hoops", False):
                # Symmetrically place hoops at 1.5x on the top layer so characters pass underneath!
                if hasattr(self, "_left_hoop_surface") and self._left_hoop_surface:
                    screen.blit(self._left_hoop_surface, (court_x + 10, court_y + 222))
                if hasattr(self, "_right_hoop_surface") and self._right_hoop_surface:
                    screen.blit(self._right_hoop_surface, (court_x + 706, court_y + 222))

    def __repr__(self):
        return f"Floor({self.id}, '{self.name}', rooms={len(self.rooms)})"


# ══════════════════════════════════════════════════════════════
#  STAIRCASE CONSTANTS & HELPER
# ══════════════════════════════════════════════════════════════

STAIR_W   = 500     # room width
STAIR_H   = 280     # room height  (taller = easier to navigate)
STAIR_GAP = 80      # U-turn gap width


def _add_stair_walls(floor, rx, ry, rw, rh, gap_side):
    """Add horizontal centre wall + full enclosure for a staircase."""
    cy = ry + rh // 2
    wall_len = rw - STAIR_GAP
    
    # Top and bottom are always solid
    floor.walls.append(_hw(rx, ry, rw))
    floor.walls.append(_hw(rx, ry + rh - WT, rw))

    # Side enclosure (leave the other side open for the door)
    if gap_side == 'right':
        # Gap on right (inner), wall on right (outer)? 
        # Actually, for the right staircase, the door is on the LEFT.
        floor.walls.append(_vw(rx + rw - WT, ry, rh)) # Right wall
        short_len = rw // 2                            # ~half width, leaving larger gap
        floor.walls.append(_hw(rx, cy, short_len))    # Divider from left (shortened)
    else:
        # Gap on left (inner), wall on left (outer)?
        # For the left staircase, the door is on the RIGHT.
        floor.walls.append(_vw(rx, ry, rh))           # Left wall
        floor.walls.append(_hw(rx + STAIR_GAP, cy, wall_len)) # Divider from right


def _upper_door_y(ry):
    """Y for a door in the upper corridor (30 px below room top)."""
    return ry + 30

def _lower_door_y(ry, rh):
    """Y for a door in the lower corridor (safely below centre wall)."""
    return ry + rh // 2 + WT + 20


# ══════════════════════════════════════════════════════════════
#  SCHOOL MAP
# ══════════════════════════════════════════════════════════════

class SchoolMap:
    FLOOR_COLISEUM_INTERIOR = 5
    FLOOR_PINGPONG_INTERIOR = 6

    # Staircase positions (same rect on BOTH connected floors)
    #   Right wing: door at x=2150, gap on RIGHT
    STAIR_1F_2F = (2150, 1720, STAIR_W, STAIR_H)    # y: 1720-2000
    #   Left wing:  door at x=1050, gap on LEFT
    STAIR_1F_BS = (550,  1620, STAIR_W, STAIR_H)    # y: 1620-1900
    STAIR_2F_RT = (550,  16,   STAIR_W, STAIR_H)    # y: 16-296

    def __init__(self):
        self.graph  = Graph(directed=False)
        self.floors: dict[int, Floor] = {}
        self.staircases: list[SeamlessStaircase] = []
        self._build_all()

    def get_floor(self, fid):
        return self.floors.get(fid)
    def find_path(self, a, b):
        return self.graph.bfs(a, b)
    def unlock_zone(self, zone_id):
        pass
    def unlock_director(self):
        pass
    def get_connected_zones(self, zone_id):
        return self.graph.get_neighbors(zone_id)
    def get_zone(self, zone_id):
        from settings import ZONE_TO_FLOOR
        fid = ZONE_TO_FLOOR.get(zone_id, (1,))[0]
        return self.get_floor(fid)

    def _build_all(self):
        for zid, nbs in ZONE_CONNECTIONS.items():
            for nb in nbs:
                if not self.graph.has_edge(zid, nb):
                    self.graph.add_edge(zid, nb)

        self.floors[0] = self._build_campus()
        self.floors[1] = self._build_floor1()
        self.floors[2] = self._build_floor2()
        self.floors[3] = self._build_basement()
        self.floors[4] = self._build_rooftop()
        self.floors[self.FLOOR_COLISEUM_INTERIOR] = self._build_coliseum_interior()
        self.floors[self.FLOOR_PINGPONG_INTERIOR] = self._build_pingpong_interior()

        # ── seamless staircases (stairs only, NOT campus) ─────
        for (rect, fab, fbl) in [
            (self.STAIR_1F_2F, FLOOR_2F,      FLOOR_1F),
            (self.STAIR_1F_BS, FLOOR_1F,      FLOOR_BASEMENT),
            (self.STAIR_2F_RT, FLOOR_ROOFTOP, FLOOR_2F),
        ]:
            rx, ry, rw, rh = rect
            self.staircases.append(SeamlessStaircase(
                rect,
                transition_y=ry + rh // 2,
                floor_above=fab,
                floor_below=fbl,
            ))

    # ──────────────────────────────────────────────────────────
    #  CAMPUS  (4000 × 3000)
    # ──────────────────────────────────────────────────────────

    def _build_campus(self):
        f = Floor(0, "Campus", 4000, 3000, FLOOR_BG_COLORS[0])
        f.bg_tile_path = "data/tiles/ME_Singles_Terrains_and_Fences_32x32_Grass_Water_3_9.png"

        f.add_room(Room("c_roundabout", "Entrance Roundabout",
                        "Main entrance to Ravenside High",
                        1400, 2500, 1200, 350, (50, 58, 50)))
        f.add_room(Room("c_parking", "Parking Lot",
                        "Student and staff parking",
                        0, 2100, 1200, 750, (48, 48, 48)))
        f.add_room(Room("c_road", "Main Road",
                        "Paved street with curved ending",
                        0, 2850, 2900, 150, (35, 35, 40)))
        f.add_room(Room("c_building", "Main Building",
                        "Walk through to enter 1st Floor",
                        1400, 1100, 1200, 900, (48, 48, 55),
                        mission_tag="Enter to access 1st Floor"))

        f.add_room(Room("c_fountain", "Central Fountain",
                        "Grand fountain in the courtyard",
                        1700, 2050, 600, 350, (42, 58, 62)))
        f.add_room(Room("c_gardens", "English Gardens",
                        "Manicured gardens with hedge maze",
                        100, 150, 1200, 1000, (32, 58, 32),
                        tile_path="data/tiles/ME_Singles_Terrains_and_Fences_32x32_Grass_Water_3_9.png"))
        f.add_room(Room("c_tennis", "Ping Pong Court",
                        "One court for recreation",
                        3100, 2100, 780, 750, (40, 52, 44),
                        tile_path="assets/UI/wood_tile_orange.png"))
        f.add_room(Room("c_coliseum", "Athletic Coliseum",
                        "Circular coliseum with basketball court",
                        2800, 150, 1080, 950, (44, 40, 36),
                        mission_tag="Sports Arena"))
        f.add_room(Room("c_coliseum_court", "Basketball Court",
                        "The main court",
                        2800 + WT + 100, 150 + WT + 100, 1080 - 2 * WT - 200, 950 - 2 * WT - 200, (176, 110, 66)))

        # Outer boundary
        outer_bounds = [
            _hw(0, 0, 4000), _hw(0, 3000 - WT, 4000),
            _vw(0, 0, 3000), _vw(4000 - WT, 0, 3000),
        ]
        f.walls.extend(outer_bounds)
        f.invisible_walls = outer_bounds
        # Building walls (new double-width entrance at bottom)
        bx, by, bw, bh = 1400, 1100, 1200, 900
        bdoor_w = 4 * DW
        bdx = bx + (bw - bdoor_w) // 2
        f.walls.append(_hw(bx, by, bw))
        f.walls.append(_vw(bx, by, bh))
        f.walls.append(_vw(bx + bw - WT, by, bh))
        f.walls.extend(_hwall_gaps(by + bh - WT, bx, bx + bw, [(bdx, bdoor_w)]))
        
        # Facade collision (purple areas mentioned by user)
        facade_depth = int(bh * 0.4)
        f.walls.append(pygame.Rect(bx, by + bh - facade_depth, bdx - bx, facade_depth))
        f.walls.append(pygame.Rect(bdx + bdoor_w, by + bh - facade_depth, (bx + bw) - (bdx + bdoor_w), facade_depth))
        # Side walls for the entrance hallway
        f.walls.append(_vw(bdx - WT, by + bh - facade_depth, facade_depth))
        f.walls.append(_vw(bdx + bdoor_w, by + bh - facade_depth, facade_depth))
        
        # Entrance Hallway back-wall (blocks going further "up")
        f.walls.append(_hw(bdx - WT, by + bh - 60, bdoor_w + 2 * WT))
        # Coliseum (new gate at bottom)
        cx, cy, cw, ch = 2800, 150, 1080, 950
        col_gate_w = 3 * DW
        col_gate_x = cx + (cw - col_gate_w) // 2
        f.walls.append(_hw(cx, cy, cw))
        f.walls.append(_vw(cx, cy, ch))
        f.walls.append(_vw(cx + cw - WT, cy, ch))
        f.walls.extend(_hwall_gaps(cy + ch - WT, cx, cx + cw, [(col_gate_x, col_gate_w)]))
        
        # Facade collision for Coliseum
        facade_depth_col = int(ch * 0.45)
        f.walls.append(pygame.Rect(cx, cy + ch - facade_depth_col, col_gate_x - cx, facade_depth_col))
        f.walls.append(pygame.Rect(col_gate_x + col_gate_w, cy + ch - facade_depth_col, (cx + cw) - (col_gate_x + col_gate_w), facade_depth_col))
        # Side walls for the gate
        f.walls.append(_vw(col_gate_x - WT, cy + ch - facade_depth_col, facade_depth_col))
        f.walls.append(_vw(col_gate_x + col_gate_w, cy + ch - facade_depth_col, facade_depth_col))
        
        # Internal walls around the basketball court on Campus floor
        court_x, court_y = 2800 + WT + 100, 150 + WT + 100
        court_w, court_h = 1080 - 2 * WT - 200, 950 - 2 * WT - 200
        f.walls.extend([
            _hw(court_x, court_y, court_w),
            _vw(court_x, court_y, court_h),
            _vw(court_x + court_w - WT, court_y, court_h)
        ])
        # Bottom wall of the court with gap for entrance
        f.walls.extend(_hwall_gaps(court_y + court_h - WT, court_x, court_x + court_w, [(col_gate_x, col_gate_w)]))
        
        # Entrance Hallway back-wall for Coliseum
        f.walls.append(_hw(col_gate_x - WT, cy + ch - 60, col_gate_w + 2 * WT))
        
        # Ping Pong Court (new centered entrance at bottom)
        tx, ty, tw, th = 3100, 2100, 780, 750
        tennis_door_w = 2 * DW
        tennis_door_x = tx + (tw - tennis_door_w) // 2
        f.walls.append(_hw(tx, ty, tw))
        f.walls.append(_vw(tx, ty, th))
        f.walls.append(_vw(tx + tw - WT, ty, th))
        f.walls.extend(_hwall_gaps(ty + th - WT, tx, tx + tw, [(tennis_door_x, tennis_door_w)]))
        
        # Facade collision for Ping Pong Court
        facade_depth_pp = int(th * 0.5)
        f.walls.append(pygame.Rect(tx, ty + th - facade_depth_pp, tennis_door_x - tx, facade_depth_pp))
        f.walls.append(pygame.Rect(tennis_door_x + tennis_door_w, ty + th - facade_depth_pp, (tx + tw) - (tennis_door_x + tennis_door_w), facade_depth_pp))
        # Side walls for the entrance
        f.walls.append(_vw(tennis_door_x - WT, ty + th - facade_depth_pp, facade_depth_pp))
        f.walls.append(_vw(tennis_door_x + tennis_door_w, ty + th - facade_depth_pp, facade_depth_pp))
        
        # Entrance Hallway back-wall for Ping Pong
        f.walls.append(_hw(tennis_door_x - WT, ty + th - 60, tennis_door_w + 2 * WT))
        
        # Interior columns for Ping Pong to prevent walking through the whole building
        f.walls.append(pygame.Rect(tx + 100, ty + 100, 40, 40))
        f.walls.append(pygame.Rect(tx + tw - 140, ty + 100, 40, 40))
        # Garden hedges removed per user request; replaced with benches and planters
        for bx in (300, 550, 800, 1050):
            _add_furn(f, pygame.Rect(bx, 450, 120, 40), "bench")
            _add_furn(f, pygame.Rect(bx, 750, 120, 40), "bench")
        for px in (240, 490, 740, 990, 1220):
            _add_furn(f, pygame.Rect(px, 452, 36, 36), "plant", color=(40, 160, 60))
            _add_furn(f, pygame.Rect(px, 752, 36, 36), "plant", color=(40, 160, 60))

        
        # Ping pong table in the middle of Ping Pong Courts
        # Court bounds: x=3100, y=2100, w=780, h=750
        # Center = 3100 + 390 = 3490, 2100 + 375 = 2475
        f.ping_pong_table = pygame.Rect(3400, 2420, 180, 110)
        f.walls.append(f.ping_pong_table)

        # Fountain collision - circular base at center of c_fountain room
        # Room center: 1700+300=2000, 2050+175=2225
        fountain_cx, fountain_cy = 2000, 2225
        fountain_base_r = 85
        # Approximate circle with a square collision (slightly larger than visual)
        f.fountain_rect = pygame.Rect(
            fountain_cx - fountain_base_r,
            fountain_cy - fountain_base_r,
            fountain_base_r * 2,
            fountain_base_r * 2
        )
        f.walls.append(f.fountain_rect)

        # Basketball court
        f.basketball_court = pygame.Rect(2800 + WT, 150 + WT, 1080 - 2 * WT, 950 - 2 * WT)
        f.curved_road = {"center": (2900, 3000), "radius": 150, "color": (35, 35, 40)}

        # Garden decorations
        import random
        rng = random.Random(42)
        f.garden_decorations = []
        
        # Tree sprite
        tree_sprite = 'ME_Singles_City_Props_32x32_Tree_12.png'
        # Fountain sprites
        fountain_2_3 = 'ME_Singles_Garden_32x32_Fountain_2_3.png'
        fountain_3_3 = 'ME_Singles_Garden_32x32_Fountain_3_3.png'
        # Flower sprites (rotate through available options)
        flower_sprites = [
            'ME_Singles_Villas_32x32_Villa_Yard_Flowers_5.png',
            'ME_Singles_Villas_32x32_Villa_Yard_Flowers_6.png',
            'ME_Singles_Villas_32x32_Villa_Yard_Flowers_7.png',
            'ME_Singles_Villas_32x32_Villa_Yard_Flowers_8.png',
            'ME_Singles_Villas_32x32_Villa_Yard_Flowers_9 copy 2.png',
        ]
        # Trunk/prop sprites (yard_props_17, 18, 19)
        prop_sprites = [
            'ME_Singles_Villas_32x32_Villa_Yard_Props_17.png',
            'ME_Singles_Villas_32x32_Villa_Yard_Props_18.png',
            'ME_Singles_Villas_32x32_Villa_Yard_Props_19.png',
        ]
        
        # Trees - reduced by 70% (15 remaining from 50)
        for _ in range(15):
            for _ in range(10):
                tx = rng.randint(150, 1250)
                ty = rng.randint(200, 1100)
                rad = rng.randint(20, 35)
                treect = pygame.Rect(tx - rad//2, ty - rad//2, rad, rad)
                if not any(treect.colliderect(w) for w in f.walls):
                    f.garden_decorations.append(('sprite', tx, ty, tree_sprite))
                    f.walls.append(pygame.Rect(tx - 10, ty - 10, 20, 20))
                    break
        
        # Flower groups - reduced by 70% (12 remaining), uniformly distributed
        # Garden area: x: 150-1250, y: 200-1100
        cols = 4
        rows = 3
        x_step = (1250 - 150) / cols
        y_step = (1100 - 200) / rows
        
        for row in range(rows):
            for col in range(cols):
                fx = int(150 + col * x_step + x_step / 2)
                fy = int(200 + row * y_step + y_step / 2)
                # Add slight random offset for natural look
                fx += rng.randint(-20, 20)
                fy += rng.randint(-20, 20)
                flower = rng.choice(flower_sprites)
                f.garden_decorations.append(('sprite', fx, fy, flower))
        
        # Trunks/props - reduced by 70% (3 remaining), uniformly distributed
        prop_cols = 3
        prop_rows = 1
        prop_x_step = (1250 - 150) / prop_cols
        prop_y_step = (1100 - 200) / prop_rows
        
        for row in range(prop_rows):
            for col in range(prop_cols):
                px = int(150 + col * prop_x_step + prop_x_step / 2)
                py = int(200 + row * prop_y_step + prop_y_step / 2)
                # Add slight random offset for natural look
                px += rng.randint(-15, 15)
                py += rng.randint(-15, 15)
                prop = rng.choice(prop_sprites)
                f.garden_decorations.append(('sprite', px, py, prop))
                f.walls.append(pygame.Rect(px - 10, py - 10, 20, 20))
        
        # Use the fountain sprite only at the Central Fountain POI
        f.garden_decorations.append(('sprite', 2000, 2225, fountain_3_3, 280, 350))
        
        # New bush sprites to alternate
        bush_sprites = [
            'ME_Singles_Garden_32x32_Bush_1.png',
            'ME_Singles_Garden_32x32_Bush_2.png',
            'ME_Singles_Garden_32x32_Bush_8.png',
            'ME_Singles_Garden_32x32_Bush_12.png',
        ]
        bush_idx = 0
        def next_bush():
            nonlocal bush_idx
            b = bush_sprites[bush_idx]
            bush_idx = (bush_idx + 1) % len(bush_sprites)
            return b

        # Roundabout bushes decoration (neat rows on each side)
        for side_x in [1420, 2580]: # Left and Right edges
            for by in range(2520, 2850, 45):
                f.garden_decorations.append(('sprite', side_x, by, next_bush()))
        
        # Benches (removed - brown rects deleted)
        
        # Parking Lot bushes (strictly outside the perimeter)
        # Top edge (above the parking lot)
        for px in range(20, 1180, 50):
            f.garden_decorations.append(('sprite', px, 2100 - 25, next_bush()))
        # Right edge (to the right of the parking lot)
        for py in range(2100, 2850, 50):
            f.garden_decorations.append(('sprite', 1200 + 25, py, next_bush()))

        # Main Building perimeters
        for bx in range(1400, 2600, 60): # Top
            f.garden_decorations.append(('sprite', bx, 1100 - 25, next_bush()))
        for by in range(1100, 1950, 60): # Sides
            f.garden_decorations.append(('sprite', 1400 - 25, by, next_bush()))
            f.garden_decorations.append(('sprite', 2600 + 25, by, next_bush()))

        # Athletic Coliseum perimeters
        for cx in range(2800, 3880, 70): # Top
            f.garden_decorations.append(('sprite', cx, 150 - 30, next_bush()))
        for cy in range(150, 1050, 70): # Sides
            f.garden_decorations.append(('sprite', 2800 - 30, cy, next_bush()))
            f.garden_decorations.append(('sprite', 3880 + 30, cy, next_bush()))

        # Ping Pong Court perimeters
        for tx in range(3100, 3880, 60): # Top
            f.garden_decorations.append(('sprite', tx, 2100 - 25, next_bush()))
        for ty in range(2100, 2750, 60): # Sides
            f.garden_decorations.append(('sprite', 3100 - 25, ty, next_bush()))
            f.garden_decorations.append(('sprite', 3880 + 25, ty, next_bush()))

        # Portal: building entrance → 1F reception
        f.transitions.append(FloorTransition(
            (bdx, by + bh - 30, bdoor_w, 60),
            FLOOR_1F, 1600, 2200,
            label="Enter"))

        # Portal: Coliseum entrance → Coliseum Interior
        f.transitions.append(FloorTransition(
            (col_gate_x, cy + ch - 30, col_gate_w, 60),
            self.FLOOR_COLISEUM_INTERIOR, 900, 1100,
            label="Enter Arena"))

        # Portal: Ping Pong entrance → Ping Pong Interior
        f.transitions.append(FloorTransition(
            (tennis_door_x, ty + th - 30, tennis_door_w, 60),
            self.FLOOR_PINGPONG_INTERIOR, 650, 900,
            label="Enter Court"))

        # Building visual specifications
        f.building_specs = {
            "Main Building": {
                "facade_rect": pygame.Rect(bx, by, bw, bh),
                "facade_color": (145, 164, 188),
                "trim_color": (110, 125, 145),
                "window_color": (30, 45, 60),
                "window_rows": 3,
                "window_cols": 12,
                "entry": "double_door"
            },
            "Athletic Coliseum": {
                "facade_rect": pygame.Rect(cx, cy, cw, ch),
                "facade_color": (155, 145, 135),
                "trim_color": (115, 105, 95),
                "window_color": (40, 35, 30),
                "window_rows": 2,
                "window_cols": 8,
                "entry": "gate"
            },
            "Ping Pong Court": {
                "facade_rect": pygame.Rect(tx, ty, tw, th),
                "facade_color": (135, 155, 145),
                "trim_color": (95, 115, 105),
                "window_color": (35, 45, 40),
                "window_rows": 2,
                "window_cols": 6,
                "entry": "door"
            }
        }

        return f

    # ──────────────────────────────────────────────────────────
    #  1st FLOOR  (3200 × 2400)
    # ──────────────────────────────────────────────────────────

    def _build_floor1(self):
        f = Floor(1, "1st Floor", 3200, 2400, FLOOR_BG_COLORS[1])

        sx, sy, sw, sh = self.STAIR_1F_2F     # right-wing (up to 2F)
        bx, by, bw, bh = self.STAIR_1F_BS     # left-wing  (down to basement)

        # LEFT wing
        f.add_room(Room("f1_computer_lab", "Computer Lab",
                        "Rows of monitors — Lena's territory",
                        16, 16, 1034, 494, (38, 52, 65),
                        mission_tag="Lena's base",
                        tile_path="data/tiles/piso_labs.png"))
        f.add_room(Room("f1_infirmary", "Infirmary",
                        "School nurse, bandages, rest beds",
                        16, 510, 1034, 370, (55, 55, 60),
                        tile_path="data/tiles/piso_blancobaldosa.png"))
        f.add_room(Room("f1_auditorium", "Auditorium",
                        "Large hall for assemblies",
                        16, 880, 1034, by - 880, (52, 48, 55),
                        tile_path="data/tiles/piso_hall.png"))
        f.add_room(Room("f1_basement_stairs", "Basement Stairs",
                        "Staircase down to the Basement",
                        bx, by, bw, bh, (40, 38, 42),
                        is_staircase=True))
        men_bath_y = by + bh
        men_bath_h = max(180, 2400 - 16 - men_bath_y)
        f.add_room(Room("f1_men_bath", "Man Bathroom",
                        "Men's restroom tucked beside the stairwell",
                        16, by, 1034, 2400 - 16 - by, (36, 52, 70),
                        tile_path="data/tiles/piso_blancobaldosa.png"))
        men_door_rect = (1050 - WT + 17, men_bath_y + 140, WT, DW)
        f.add_door(Door("f1_men_bath_door", *men_door_rect, color=(120, 160, 200)))

        # CENTRAL
        f.add_room(Room("f1_main_hall", "Main Hall",
                        "The central hub of Ravenside High",
                        1050, 16, 1100, 1934, (50, 50, 65),
                        tile_path="data/tiles/piso_hall.png"))
        f.add_room(Room("f1_reception", "Reception",
                        "Front desk — entrance from campus",
                        1050, 1950, 1100, 434, (48, 48, 55),
                        tile_path="data/tiles/piso_recepcion.png"))

        # RIGHT wing
        f.add_room(Room("f1_library", "Library",
                        "Quiet study hall hiding old secrets",
                        2150, 16, 1034, 584, (52, 45, 50),
                        tile_path="data/tiles/piso_hall.png"))
        f.add_room(Room("f1_cafeteria", "Cafeteria",
                        "Bustling with trays, rumours, and lunch money",
                        2150, 600, 1034, 500, (58, 52, 42),
                        tile_path="data/tiles/piso_cafeteria.png"))
        f.add_room(Room("f1_counselor", "Counselor's Office",
                        "Safe space — the counselor is on your side",
                        2150, 1100, 1034, sy - 1100, (55, 55, 52),
                        mission_tag="Ally",
                        tile_path="data/tiles/piso_hall.png"))
        f.add_room(Room("f1_stairs_2f", "Stairs to 2F",
                        "Staircase up to the 2nd Floor",
                        sx, sy, sw, sh, (52, 55, 62),
                        is_staircase=True))
        women_bath_y = sy + sh
        women_bath_h = max(160, 2400 - 16 - women_bath_y)
        f.add_room(Room("f1_women_bath", "Woman Bathroom",
                        "Women's restroom beside the stairwell",
                        2150, sy, 1034, 2400 - 16 - sy, (58, 48, 68),
                        tile_path="data/tiles/piso_blancobaldosa.png"))
        women_door_rect = (2150, women_bath_y + 139, WT, DW)
        f.add_door(Door("f1_women_bath_door", *women_door_rect, color=(200, 140, 200)))

        # Library bookshelves - repositioned to corners flush with walls
        library_shelves = [
            pygame.Rect(2166, 32, 400, 56),        # Top-Left corner (horizontal)
            pygame.Rect(3168 - 400, 32, 400, 56),  # Top-Right corner (horizontal)
            pygame.Rect(2166, 584 - 56, 400, 56),  # Bottom-Left corner (horizontal)
            pygame.Rect(3168 - 400, 584 - 56, 400, 56), # Bottom-Right corner (horizontal)
            pygame.Rect(3168 - 56, 32, 56, 552),   # Right wall (vertical, full height minus wall)
        ]
        for shelf in library_shelves:
            f.furniture.append({"rect": shelf, "type": "bookshelf", "color": (92, 58, 34), "outline": (55, 34, 22)})
            f.walls.append(shelf)

        # Library Tables & Decorations
        TABLE_R_COL = (120, 80, 50)
        TABLE_R_OUT = (90, 60, 35)
        CHAIR_COL = (85, 55, 35)
        CHAIR_OUT = (60, 38, 22)

        # Round Table 1
        t1_rect = pygame.Rect(2400, 250, 100, 100)
        f.furniture.append({"rect": t1_rect, "type": "round_table", "color": TABLE_R_COL, "outline": TABLE_R_OUT})
        f.walls.append(t1_rect)
        # Table 1 Chairs (Left and Right)
        c1l = pygame.Rect(2360, 285, 30, 30)
        c1r = pygame.Rect(2510, 285, 30, 30)
        f.furniture.append({"rect": c1l, "color": CHAIR_COL, "outline": CHAIR_OUT})
        f.furniture.append({"rect": c1r, "color": CHAIR_COL, "outline": CHAIR_OUT})
        f.walls.extend([c1l, c1r])

        # Round Table 2
        t2_rect = pygame.Rect(2800, 250, 100, 100)
        f.furniture.append({"rect": t2_rect, "type": "round_table", "color": TABLE_R_COL, "outline": TABLE_R_OUT})
        f.walls.append(t2_rect)
        # Table 2 Chairs (Top and Bottom)
        c2t = pygame.Rect(2835, 210, 30, 30)
        c2b = pygame.Rect(2835, 360, 30, 30)
        f.furniture.append({"rect": c2t, "color": CHAIR_COL, "outline": CHAIR_OUT})
        f.furniture.append({"rect": c2b, "color": CHAIR_COL, "outline": CHAIR_OUT})
        f.walls.extend([c2t, c2b])

        # 2 Lamps
        lamp1_rect = pygame.Rect(2435, 120, 30, 30)
        lamp2_rect = pygame.Rect(2835, 120, 30, 30)
        f.furniture.append({"rect": lamp1_rect, "type": "lamp", "color": (255, 255, 180)})
        f.furniture.append({"rect": lamp2_rect, "type": "lamp", "color": (255, 255, 180)})
        f.walls.extend([lamp1_rect, lamp2_rect])


        # Outer boundary
        f.walls.extend([
            _hw(0, 0, 3200), _hw(0, 2400 - WT, 3200),
            _vw(0, 0, 2400), _vw(3200 - WT, 0, 2400),
        ])

        # Left divider (x=1050) — basement stair door in UPPER corridor
        f.walls.extend(_vwall_gaps(1050, 16, 1950, [
            (200, DW), (640, DW), (1080, DW),
            (_upper_door_y(by), DW),
        ]))
        # Right divider (x=2150) — 2F stair door in LOWER corridor
        # Library door at y=200 (shifted up to make wall longer)
        f.walls.extend(_vwall_gaps(2150, 16, sy + sh, [
            (200, 3 * DW),  # Library door (shifted up)
            (880 - DW, 3 * DW), (1250, DW),
            (_lower_door_y(sy, sh), DW),
        ]))
        # Cafeteria door object (Triple size, shifted down to make wall longer)
        f.add_door(Door("door_library", 2150, 200, 16, 3 * DW, is_vertical=True))
        f.add_door(Door("door_cafeteria", 2150, 880 - DW, 16, 3 * DW, is_vertical=True))
        f.add_door(Door("door_computer_lab", 1050, 200, 16, DW, is_vertical=True))
        f.add_door(Door("door_infirmary", 1050, 640, 16, DW, is_vertical=True))
        f.add_door(Door("door_auditorium", 1050, 1080, 16, DW, is_vertical=True))
        f.add_door(Door("door_counselor", 2150, 1250, 16, DW, is_vertical=True))

        # ── Cafeteria furniture ──────────────────────────────
        TABLE_COL  = (255, 255, 255)
        TABLE_OUTL = (200, 200, 200)
        COUNTER_COL  = (140, 140, 150)
        COUNTER_OUTL = (100, 100, 110)

        # L-shaped serving counter (top-right corner of cafeteria)
        # It sticks to the top wall (y=616) and right wall (x=3184)
        counter_h = pygame.Rect(2700, 616, 484, 40)
        counter_v = pygame.Rect(3144, 616, 40, 350)
        f.furniture.append({"rect": counter_h, "color": COUNTER_COL, "outline": COUNTER_OUTL})
        f.furniture.append({"rect": counter_v, "color": COUNTER_COL, "outline": COUNTER_OUTL})
        f.walls.extend([counter_h, counter_v])

        # Buffet trays with colorful food on the counter
        food_colors = [(200, 60, 60), (220, 200, 50), (139, 69, 19), (240, 150, 50), (100, 200, 100)]
        for i in range(5):
            tray_h = pygame.Rect(2720 + i * 80, 621, 60, 30)
            f.furniture.append({"rect": tray_h, "type": "buffet_tray", "color": food_colors[i % len(food_colors)]})
        for i in range(3):
            tray_v = pygame.Rect(3149, 700 + i * 80, 30, 60)
            f.furniture.append({"rect": tray_v, "type": "buffet_tray", "color": food_colors[(i+2) % len(food_colors)]})

        # 3 dining tables (vertical rectangles spread across the cafeteria)
        caf_tables = [
            pygame.Rect(2300, 720, 130, 300),  # left table
            pygame.Rect(2560, 720, 130, 300),  # centre table
            pygame.Rect(2860, 720, 130, 300),  # right table
        ]
        CHAIR_COL  = (128, 128, 128)
        CHAIR_OUTL = (80, 80, 80)
        CHAIR_W, CHAIR_H = 28, 28
        chair_gap = 8  # gap between chair and table edge

        for tbl in caf_tables:
            f.furniture.append({"rect": tbl, "color": TABLE_COL, "outline": TABLE_OUTL})
            f.walls.append(tbl)

            # Chairs along left side (3 chairs)
            for i in range(3):
                cy = tbl.top + 30 + i * 110
                cr = pygame.Rect(tbl.left - CHAIR_W - chair_gap, cy, CHAIR_W, CHAIR_H)
                f.furniture.append({"rect": cr, "color": CHAIR_COL, "outline": CHAIR_OUTL})
            # Chairs along right side (3 chairs)
            for i in range(3):
                cy = tbl.top + 30 + i * 110
                cr = pygame.Rect(tbl.right + chair_gap, cy, CHAIR_W, CHAIR_H)
                f.furniture.append({"rect": cr, "color": CHAIR_COL, "outline": CHAIR_OUTL})
            # Chair at top
            cr = pygame.Rect(tbl.centerx - CHAIR_W // 2, tbl.top - CHAIR_H - chair_gap, CHAIR_W, CHAIR_H)
            f.furniture.append({"rect": cr, "color": CHAIR_COL, "outline": CHAIR_OUTL})
            # Chair at bottom
            cr = pygame.Rect(tbl.centerx - CHAIR_W // 2, tbl.bottom + chair_gap, CHAIR_W, CHAIR_H)
            f.furniture.append({"rect": cr, "color": CHAIR_COL, "outline": CHAIR_OUTL})

        # Store seat positions around each table for NPC seating
        f.cafeteria_seats = []
        seat_offset = 30  # distance from table edge
        for tbl in caf_tables:
            # 2 seats on left side, 2 on right side, 1 top, 1 bottom
            f.cafeteria_seats.extend([
                (tbl.left - seat_offset, tbl.top + tbl.height // 3),
                (tbl.left - seat_offset, tbl.top + 2 * tbl.height // 3),
                (tbl.right + seat_offset, tbl.top + tbl.height // 3),
                (tbl.right + seat_offset, tbl.top + 2 * tbl.height // 3),
                (tbl.centerx, tbl.top - seat_offset),
                (tbl.centerx, tbl.bottom + seat_offset),
            ])

        # Left horizontal dividers
        f.walls.extend([_hw(16, 510, 1034), _hw(16, 880, 1034)])
        f.walls.append(_hw(16, by, 1034))               # top of basement stairs

        # Right horizontal dividers
        f.walls.extend([_hw(2150, 600, 1034), _hw(2150, 1100, 1034)])
        f.walls.append(_hw(2150, sy, 1034))              # top of 2F stairs

        # Bathroom partitions vs reception (doorway shifted away from stairs)
        f.walls.extend(_vwall_gaps(1050, men_bath_y, men_bath_y + men_bath_h, [
            (men_bath_y + 140, DW),
        ]))
        f.walls.extend(_vwall_gaps(2150, women_bath_y, women_bath_y + women_bath_h, [
            (women_bath_y + 140, DW),
        ]))

        # Reception divider
        rdx = 1050 + (1100 - DW) // 2
        f.walls.extend(_hwall_gaps(1950, 1050, 2150, [(rdx, DW)]))

        # Staircase interior walls
        _add_stair_walls(f, sx, sy, sw, sh, 'right')
        _add_stair_walls(f, bx, by, bw, bh, 'left')

        # Portal: reception exit → campus
        f.transitions.append(FloorTransition(
            (rdx, 2400 - WT - 30, DW, 30),
            FLOOR_CAMPUS, 2000, 2020,
            label="Campus"))

        f.hackable_objects = [
            {"type": "server", "x": 400, "y": 300, "difficulty": 3, "id": "lab_server"},
            {"type": "camera", "x": 600, "y": 200, "difficulty": 2, "id": "lab_camera"},
            {"type": "camera", "x": 1600, "y": 100, "difficulty": 1, "id": "hall_camera"},
        ]

        # ── Detailed furniture per room ───────────────────────────
        # Computer Lab: two long rows of desktops, plus a teacher's desk
        for col in range(6):
            cx = 90 + col * 150
            _add_furn(f, pygame.Rect(cx, 90, 90, 64), "computer", facing="down")
            _add_furn(f, pygame.Rect(cx + 18, 162, 54, 30), "office_chair")
            _add_furn(f, pygame.Rect(cx, 320, 90, 64), "computer", facing="up")
            _add_furn(f, pygame.Rect(cx + 18, 290, 54, 30), "office_chair")
        _add_furn(f, pygame.Rect(850, 200, 140, 70), "office_desk", facing="left")
        _add_furn(f, pygame.Rect(960, 220, 36, 30), "office_chair")

        # Infirmary: four cots and a nurse desk
        for i in range(4):
            bx_ = 80 + i * 220
            _add_furn(f, pygame.Rect(bx_, 555, 80, 130), "hospital_bed", facing="down")
        _add_furn(f, pygame.Rect(440, 760, 160, 70), "office_desk", facing="up")
        _add_furn(f, pygame.Rect(490, 836, 36, 30), "office_chair")

        # Auditorium: stage with curtains + rows of seats, right-side aisle
        _add_furn(f, pygame.Rect(110, 905, 820, 110), "stage")
        seat_w, seat_h = 30, 30
        seat_gap_x = 12
        seat_pitch_x = seat_w + seat_gap_x
        seat_pitch_y = 50
        cols_seats = 16
        rows_seats = 9
        seats_x0 = 60
        seats_y0 = 1080
        for row in range(rows_seats):
            for col in range(cols_seats):
                _add_furn(
                    f,
                    pygame.Rect(seats_x0 + col * seat_pitch_x,
                                seats_y0 + row * seat_pitch_y,
                                seat_w, seat_h),
                    "auditorium_seat",
                )

        # Main Hall: lockers along the inner walls, avoiding doors
        # Left wall (just inside x=1066), doors at y in {200,640,1080} (80 wide)
        locker_thickness = 28
        left_locker_x = 1050 + WT  # just inside left divider
        right_locker_x = 2150 - locker_thickness  # flush against right divider
        for (y0, y1) in [(40, 184), (300, 624), (724, 1064), (1164, 1500)]:
            _add_furn(f, pygame.Rect(left_locker_x, y0, locker_thickness, y1 - y0), "locker")
        # Right wall doors: y=200 (triple), y=800 (triple to 1040), y=1250 (single)
        for (y0, y1) in [(40, 184), (504, 784), (1064, 1234), (1340, 1500)]:
            _add_furn(f, pygame.Rect(right_locker_x, y0, locker_thickness, y1 - y0), "locker")

        # Library Bench/Counselor's Office: personal desks with chairs
        _add_furn(f, pygame.Rect(2260, 1180, 160, 80), "office_desk", facing="down")
        _add_furn(f, pygame.Rect(2305, 1264, 70, 36), "office_chair")
        _add_furn(f, pygame.Rect(2700, 1380, 160, 80), "office_desk", facing="up")
        _add_furn(f, pygame.Rect(2745, 1336, 70, 36), "office_chair")
        _add_furn(f, pygame.Rect(2980, 1180, 80, 160), "office_desk", facing="left")
        _add_furn(f, pygame.Rect(2924, 1230, 36, 60), "office_chair")

        # Men's Bathroom: cubicles with toilets along the left wall + bottom row
        # Left strip (x≈16..550, y from by=1620 to 2384)
        cubicle_partition_col = (220, 222, 232)
        cubicle_partition_outl = (140, 142, 156)
        toilet_w, toilet_h = 60, 70
        cub_w = 130
        for i in range(4):
            ty = by + 30 + i * 165
            # Toilet (faces right, tank on left)
            _add_furn(f, pygame.Rect(34, ty, toilet_w, toilet_h), "toilet", facing="right")
            # Partition wall divider below each cubicle (except after the last one)
            if i < 3:
                _add_furn(f, pygame.Rect(16 + WT, ty + toilet_h + 16, cub_w, 6),
                          color=cubicle_partition_col, outline=cubicle_partition_outl)
        # Bottom strip (x=16..1050, y=men_bath_y..men_bath_y+men_bath_h) along bottom wall
        cub_partition_h = 90
        for i in range(5):
            tx_ = 120 + i * 170
            _add_furn(f, pygame.Rect(tx_, men_bath_y + men_bath_h - 90, toilet_w, toilet_h),
                      "toilet", facing="up")
            if i < 4:
                _add_furn(f, pygame.Rect(tx_ + toilet_w + 4, men_bath_y + men_bath_h - 100,
                                         6, cub_partition_h),
                          color=cubicle_partition_col, outline=cubicle_partition_outl)
        # Sinks (lavamanos) mounted just under the staircase wall, facing south
        sink_w, sink_h = 70, 46
        for i in range(4):
            sxn = 590 + i * 110
            _add_furn(f, pygame.Rect(sxn, by + bh + 12, sink_w, sink_h),
                      "sink", facing="down")

        # Women's Bathroom: mirror layout on right strip + bottom row
        for i in range(4):
            ty = sy + 30 + i * 165
            _add_furn(f, pygame.Rect(3134 - toilet_w, ty, toilet_w, toilet_h), "toilet", facing="left")
            if i < 3:
                _add_furn(f, pygame.Rect(3184 - WT - cub_w, ty + toilet_h + 16, cub_w, 6),
                          color=cubicle_partition_col, outline=cubicle_partition_outl)
        for i in range(5):
            tx_ = 2230 + i * 170
            _add_furn(f, pygame.Rect(tx_, women_bath_y + women_bath_h - 90, toilet_w, toilet_h),
                      "toilet", facing="up")
            if i < 4:
                _add_furn(f, pygame.Rect(tx_ + toilet_w + 4, women_bath_y + women_bath_h - 100,
                                         6, cub_partition_h),
                          color=cubicle_partition_col, outline=cubicle_partition_outl)
        # Sinks under the staircase wall, facing south
        for i in range(4):
            sxn = 2190 + i * 110
            _add_furn(f, pygame.Rect(sxn, sy + sh + 12, sink_w, sink_h),
                      "sink", facing="down")

        return f

    # ──────────────────────────────────────────────────────────
    #  2nd FLOOR  (3200 × 2400)
    # ──────────────────────────────────────────────────────────

    def _build_floor2(self):
        f = Floor(2, "2nd Floor", 3200, 2400, FLOOR_BG_COLORS[2])

        sx, sy, sw, sh = self.STAIR_1F_2F     # right-wing (down to 1F)
        rx, ry, rw, rh = self.STAIR_2F_RT     # left-wing  (up to rooftop)

        # LEFT wing
        art_y = ry + rh                        # 296
        mus_y = art_y + 650                    # 946
        sci_y = mus_y + 420                    # 1366

        f.add_room(Room("f2_roof_stairs", "Stairs to Rooftop",
                        "Staircase up to the Rooftop",
                        rx, ry, rw, rh, (38, 48, 58),
                        is_staircase=True))
        _tile_mad   = "data/tiles/piso_mad.png"
        _tile_mad2  = "data/tiles/piso_mad2.png"
        _tile_mad3  = "data/tiles/piso_mad3.png"
        _tile_dir   = "data/tiles/piso_director.png"
        _tile_hall  = "data/tiles/piso_hall.png"
        f.add_room(Room("f2_art_room", "Art Room",
                        "Canvases, paint, and creative chaos",
                        16, art_y, 1034, 650, (60, 50, 55),
                        tile_path=_tile_hall))
        f.add_room(Room("f2_music_room", "Music Room",
                        "Instruments hung on walls, soundproofed",
                        16, mus_y, 1034, 420, (55, 48, 58),
                        tile_path=_tile_hall))
        f.add_room(Room("f2_science_lab", "Science Labs",
                        "Bunsen burners, chemicals, safety goggles",
                        16, sci_y, 1034, 584, (42, 55, 60),
                        tile_path="data/tiles/piso_labs.png"))

        # CENTRAL
        f.add_room(Room("f2_corridor", "2F Corridor",
                        "The upper-floor hallway",
                        1050, 16, 1100, 1934, (48, 48, 58),
                        tile_path=_tile_hall))
        f.add_room(Room("f2_classrooms", "Classrooms",
                        "Standard classrooms for lectures",
                        1050, 1950, 1100, 434, (48, 50, 55),
                        tile_path=_tile_hall))

        # RIGHT wing
        f.add_room(Room("f2_director", "Director's Office",
                        "Director Walsh's office — main quest",
                        2150, 16, 1034, 500, (62, 45, 45),
                        mission_tag="Main Quest",
                        tile_path=_tile_dir))
        f.add_room(Room("f2_conference", "Conference Room",
                        "Long table, projector — faculty meetings",
                        2150, 516, 1034, 434, (55, 52, 48),
                        tile_path="data/tiles/piso_conference.png"))
        f.add_room(Room("f2_admin", "Admin Offices",
                        "Administrative staff desks",
                        2150, 950, 1034, sy - 950, (52, 52, 55),
                        tile_path=_tile_hall))
        f.add_room(Room("f2_stairs_1f", "Stairs to 1F",
                        "Staircase down to the 1st Floor",
                        sx, sy, sw, sh, (52, 55, 62),
                        is_staircase=True))

        # Outer boundary
        f.walls.extend([
            _hw(0, 0, 3200), _hw(0, 2400 - WT, 3200),
            _vw(0, 0, 2400), _vw(3200 - WT, 0, 2400),
        ])

        # Left divider — rooftop stair door in LOWER corridor
        f.walls.extend(_vwall_gaps(1050, 16, 1950, [
            (_lower_door_y(ry, rh), DW),
            (art_y + 200 - DW//2, 2 * DW), (mus_y + 200 - DW//2, 2 * DW), (sci_y + 200 - DW//2, 2 * DW),
        ]))
        # Right divider — 1F stair door in UPPER corridor
        f.walls.extend(_vwall_gaps(2150, 16, sy + sh, [
            (200 - DW//2, 2 * DW), (640 - DW//2, 2 * DW), (1100 - DW//2, 2 * DW),
            (_upper_door_y(sy), DW),
        ]))

        # Left horizontal dividers
        f.walls.append(_hw(16, art_y, 1034))             # below rooftop stairs
        f.walls.append(_hw(16, ry + rh - WT, 1034))      # bottom of stair area
        f.walls.extend([_hw(16, mus_y, 1034), _hw(16, sci_y, 1034), _hw(16, 1950, 1034)])

        # Right horizontal dividers
        f.walls.extend([_hw(2150, 516, 1034), _hw(2150, 950, 1034)])
        f.walls.append(_hw(2150, sy, 1034))
        f.walls.append(_hw(2150, sy + sh - WT, 1034))

        # Classrooms divider (Triple door)
        cdx = 1050 + (1100 - 3 * DW) // 2
        f.walls.extend(_hwall_gaps(1950, 1050, 2150, [(cdx, 3 * DW)]))
        # Side walls for Classrooms
        f.walls.append(_vw(1050, 1950, 2400 - 1950))
        f.walls.append(_vw(2150 - WT, 1950, 2400 - 1950))

        # Staircase interior walls
        _add_stair_walls(f, sx, sy, sw, sh, 'right')
        _add_stair_walls(f, rx, ry, rw, rh, 'left')

        f.add_door(Door("door_art_room", 1050, art_y + 200 - DW//2, 16, 2 * DW, is_vertical=True))
        f.add_door(Door("door_music_room", 1050, mus_y + 200 - DW//2, 16, 2 * DW, is_vertical=True))
        f.add_door(Door("door_science_lab", 1050, sci_y + 200 - DW//2, 16, 2 * DW, is_vertical=True))

        f.add_door(Door("door_director", 2150, 200 - DW//2, 16, 2 * DW, is_vertical=True))
        f.add_door(Door("door_conference", 2150, 640 - DW//2, 16, 2 * DW, is_vertical=True))
        f.add_door(Door("door_admin", 2150, 1100 - DW//2, 16, 2 * DW, is_vertical=True))

        f.add_door(Door("door_classrooms", cdx, 1950, 3 * DW, 16, is_vertical=False))

        # ── Detailed furniture per room ───────────────────────────
        # Art Room: easels with canvases in three rows
        easel_w, easel_h = 70, 90
        for row in range(3):
            for col in range(5):
                ex = 80 + col * 180
                ey = art_y + 40 + row * 180
                _add_furn(f, pygame.Rect(ex, ey, easel_w, easel_h), "easel")
        # Teacher's desk
        _add_furn(f, pygame.Rect(820, art_y + 540, 160, 70), "office_desk", facing="up")
        _add_furn(f, pygame.Rect(870, art_y + 615, 60, 30), "office_chair")

        # Music Room: piano + drum kit + guitar stands + speaker bookshelf
        _add_furn(f, pygame.Rect(80, mus_y + 60, 220, 80), "piano")
        _add_furn(f, pygame.Rect(380, mus_y + 60, 150, 120), "drum_set")
        for i in range(3):
            _add_furn(f, pygame.Rect(620 + i * 80, mus_y + 60, 50, 130), "guitar")
        _add_furn(f, pygame.Rect(880, mus_y + 60, 130, 60),
                  "bookshelf", color=(92, 58, 34), outline=(55, 34, 22))
        _add_furn(f, pygame.Rect(80, mus_y + 260, 220, 80), "piano")
        _add_furn(f, pygame.Rect(400, mus_y + 260, 100, 50), "office_desk", facing="up")
        _add_furn(f, pygame.Rect(430, mus_y + 314, 40, 30), "office_chair")

        # Science Labs: chemistry benches with beakers / flasks / burner
        for i in range(3):
            _add_furn(
                f,
                pygame.Rect(120, sci_y + 60 + i * 150, 820, 70),
                "lab_bench",
            )
        # Teacher demo bench (vertical)
        _add_furn(f, pygame.Rect(980 - 70, sci_y + 60, 60, 470), "lab_bench")

        # Director's Office: presidential desk with a table lamp on top and a sofa-chair
        _add_furn(f, pygame.Rect(2520, 200, 280, 110), "executive_desk")
        # Lamp sits ON TOP of the desk, near the back-right corner
        _add_furn(f, pygame.Rect(2740, 210, 36, 36), "lamp",
                  color=(255, 235, 170), blocking=False)
        # Sofa-chair behind the desk (director's seat)
        _add_furn(f, pygame.Rect(2600, 330, 120, 80), "sofa_chair")

        # Admin Offices: rows of personal desks + chairs
        for row in range(3):
            for col in range(2):
                dx = 2230 + col * 480
                dy = 1000 + row * 220
                _add_furn(f, pygame.Rect(dx, dy, 160, 80), "office_desk", facing="down")
                _add_furn(f, pygame.Rect(dx + 50, dy + 90, 60, 36), "office_chair")

        # Classrooms: single teacher setup against the LEFT wall.
        # Chalkboard is vertical and faces left (wheels poke to the right).
        # Chair is east of the chalkboard, teacher's desk is further east.
        _add_furn(f, pygame.Rect(1066, 2080, 40, 240),
                  "chalkboard", facing="left")
        _add_furn(f, pygame.Rect(1140, 2180, 50, 60), "office_chair")
        _add_furn(f, pygame.Rect(1210, 2150, 180, 120),
                  "office_desk", facing="left")

        # Conference Room: same teacher setup at the south end of the room
        cr_cx = 2666  # centre of conference room (x range 2150..3184)
        _add_furn(f, pygame.Rect(cr_cx - 130, 870, 260, 40),
                  "chalkboard", facing="up")
        _add_furn(f, pygame.Rect(cr_cx - 35, 800, 70, 36), "office_chair")
        _add_furn(f, pygame.Rect(cr_cx - 110, 700, 220, 90),
                  "office_desk", facing="up")

        # 2F Corridor: lockers along inner walls (matching the 1F main hall feel)
        locker_thickness2 = 28
        left_locker_x2 = 1050 + WT
        right_locker_x2 = 2150 - locker_thickness2
        for (y0, y1) in [(40, 184), (290, 444), (640, 1090), (1290, 1510)]:
            _add_furn(f, pygame.Rect(left_locker_x2, y0, locker_thickness2, y1 - y0), "locker")
        for (y0, y1) in [(40, 144), (340, 584), (784, 1044), (1244, 1700)]:
            _add_furn(f, pygame.Rect(right_locker_x2, y0, locker_thickness2, y1 - y0), "locker")

        return f

    # ──────────────────────────────────────────────────────────
    #  BASEMENT  (3200 × 2400)
    # ──────────────────────────────────────────────────────────

    def _build_basement(self):
        f = Floor(3, "Basement", 3200, 2400, FLOOR_BG_COLORS[3])
        f.bg_tile_path = "data/tiles/piso_basement.png"

        bx, by, bw, bh = self.STAIR_1F_BS

        _tile_b = "data/tiles/piso_basement.png"
        f.add_room(Room("b_stairs_up", "Stairs to 1F",
                        "Staircase up to the 1st Floor",
                        bx, by, bw, bh, (40, 40, 48),
                        is_staircase=True,
                        tile_path=_tile_b))
        f.add_room(Room("b_smile_club", "Smile Club Room",
                        "Where the Smile Club holds secret meetings",
                        300, 200, 800, 550, (35, 25, 30),
                        mission_tag="Secret meetings",
                        tile_path=_tile_b))
        f.add_room(Room("b_server_room", "Server Room",
                        "The Smile Club's main servers hum menacingly",
                        1150, 200, 800, 550, (28, 32, 38),
                        mission_tag="Main Target",
                        tile_path=_tile_b))
        f.add_room(Room("b_surveillance", "Surveillance Center",
                        "Screens showing every hallway in the school",
                        2000, 200, 700, 550, (30, 30, 35),
                        mission_tag="Security feeds",
                        tile_path=_tile_b))
        f.add_room(Room("b_detention", "Detention Cells",
                        "Holding cells — some NPCs are trapped here",
                        300, 800, 800, 500, (30, 25, 28),
                        mission_tag="Rescuable NPCs",
                        tile_path=_tile_b))
        f.add_room(Room("b_terminal", "Final Terminal",
                        "The terminal where you choose the ending",
                        1150, 800, 800, 500, (38, 28, 32),
                        mission_tag="Choose your ending",
                        tile_path=_tile_b))

        # Outer boundary
        f.walls.extend([
            _hw(0, 0, 3200), _hw(0, 2400 - WT, 3200),
            _vw(0, 0, 2400), _vw(3200 - WT, 0, 2400),
        ])
        # Room cluster
        f.walls.extend([
            _vw(300, 200, 1100), _vw(2700 - WT, 200, 1100),
        ])
        f.walls.extend(_hwall_gaps(200, 300, 2700, [(600, DW), (1450, DW), (2300, DW)]))
        f.walls.extend(_hwall_gaps(1300 - WT, 300, 2700, [(600, DW), (1450, DW), (2300, DW)]))
        f.walls.extend(_vwall_gaps(1150, 200, 1300, [(400, DW), (950, DW)]))
        f.walls.extend(_vwall_gaps(2000, 200, 1300, [(400, DW), (950, DW)]))
        f.walls.extend(_hwall_gaps(750, 300, 2700, [(600, DW), (1450, DW)]))

        # Stair area divider — door in LOWER corridor (going UP)
        f.walls.extend(_vwall_gaps(1050, by, by + bh, [
            (_lower_door_y(by, bh), DW),
        ]))
        f.walls.append(_hw(bx, by, 1034 - bx + 16))
        f.walls.append(_hw(bx, by + bh - WT, 1034 - bx + 16))

        _add_stair_walls(f, bx, by, bw, bh, 'left')

        # Top outer wall doors (y=200)
        f.add_door(Door("door_b_smile_top", 600, 200, DW, 16, is_vertical=False))
        f.add_door(Door("door_b_server_top", 1450, 200, DW, 16, is_vertical=False))
        f.add_door(Door("door_b_surv_top", 2300, 200, DW, 16, is_vertical=False))

        # Bottom outer wall doors (y=1300 - WT)
        f.add_door(Door("door_b_detention_bot", 600, 1300 - 16, DW, 16, is_vertical=False))
        f.add_door(Door("door_b_terminal_bot", 1450, 1300 - 16, DW, 16, is_vertical=False))
        f.add_door(Door("door_b_surv_bot", 2300, 1300 - 16, DW, 16, is_vertical=False))

        # Vertical internal doors (x=1150 and x=2000)
        f.add_door(Door("door_b_smile_server", 1150, 400, 16, DW, is_vertical=True))
        f.add_door(Door("door_b_detention_terminal", 1150, 950, 16, DW, is_vertical=True))
        f.add_door(Door("door_b_server_surv", 2000, 400, 16, DW, is_vertical=True))
        f.add_door(Door("door_b_terminal_surv", 2000, 950, 16, DW, is_vertical=True))

        # Horizontal internal doors (y=750)
        f.add_door(Door("door_b_smile_detention", 600, 750, DW, 16, is_vertical=False))
        f.add_door(Door("door_b_server_terminal", 1450, 750, DW, 16, is_vertical=False))

        f.hackable_objects = [
            {"type": "server", "x": 1550, "y": 450, "difficulty": 5, "id": "smile_server"},
            {"type": "camera", "x": 2350, "y": 450, "difficulty": 4, "id": "surv_cam"},
        ]
        return f

    # ──────────────────────────────────────────────────────────
    #  ROOFTOP  (3200 × 2400)
    # ──────────────────────────────────────────────────────────

    def _build_rooftop(self):
        f = Floor(4, "Rooftop", 3200, 2400, FLOOR_BG_COLORS[4])
        f.bg_tile_path = "data/tiles/piso_rooftop.png"

        rx, ry, rw, rh = self.STAIR_2F_RT

        _tile_rt = "data/tiles/piso_rooftop.png"
        f.add_room(Room("rt_stairs_down", "Stairs to 2F",
                        "Staircase down to the 2nd Floor",
                        rx, ry, rw, rh, (38, 42, 55),
                        is_staircase=True,
                        tile_path=_tile_rt))
        f.add_room(Room("rt_terrace", "Rooftop Terrace",
                        "Open sky — secret meetings at night",
                        1200, 500, 1200, 1200, (35, 50, 65),
                        mission_tag="Night meetings",
                        tile_path=_tile_rt))
        f.add_room(Room("rt_benches", "Resting Area",
                        "Benches with a view of the campus below",
                        1300, 1750, 800, 350, (38, 48, 50),
                        tile_path=_tile_rt))

        # Outer boundary
        f.walls.extend([
            _hw(0, 0, 3200), _hw(0, 2400 - WT, 3200),
            _vw(0, 0, 2400), _vw(3200 - WT, 0, 2400),
        ])
        # Stair divider — door in UPPER corridor (going DOWN)
        f.walls.extend(_vwall_gaps(1050, ry, ry + rh, [
            (_upper_door_y(ry), DW),
        ]))
        f.walls.append(_hw(rx, ry + rh - WT, 1034 - rx + 16))

        _add_stair_walls(f, rx, ry, rw, rh, 'left')

        # Parapet (bottom wall keeps right half only: x=1800..2400)
        bot_wall = _hw(1800, 1700 - WT, 600)
        f.walls.extend([
            _hw(1200, 500, 1200), bot_wall,
        ])
        f.windowed_walls = [bot_wall]
        f.walls.extend(_vwall_gaps(1200, 500, 1700, [(900, DW)]))
        f.walls.extend(_vwall_gaps(2400 - WT, 500, 1700, [(900, DW)]))

        # ── Rooftop Terrace furniture: patio tables with parasol umbrellas ──
        # Terrace bounds: x=1200..2400, y=500..1700 (parapet)
        table_d = 120
        chair_w, chair_h = 32, 28
        table_positions = [
            (1380, 720),
            (1880, 720),
            (1380, 1120),
            (1880, 1120),
            (1620, 920),  # centre table
        ]
        for tx, ty in table_positions:
            _add_furn(f, pygame.Rect(tx, ty, table_d, table_d), "umbrella_table")
            # Four chairs around the table (N, S, E, W)
            cx_t = tx + table_d // 2
            cy_t = ty + table_d // 2
            _add_furn(f, pygame.Rect(cx_t - chair_w // 2, ty - chair_h - 6, chair_w, chair_h), "sofa_chair")
            _add_furn(f, pygame.Rect(cx_t - chair_w // 2, ty + table_d + 6, chair_w, chair_h), "sofa_chair")
            _add_furn(f, pygame.Rect(tx - chair_w - 6, cy_t - chair_h // 2, chair_w, chair_h), "sofa_chair")
            _add_furn(f, pygame.Rect(tx + table_d + 6, cy_t - chair_h // 2, chair_w, chair_h), "sofa_chair")

        # ── Resting Area furniture: benches and planters ──
        # Resting Area bounds: x=1300..2100, y=1750..2100
        for bx in (1400, 1640, 1880):
            _add_furn(f, pygame.Rect(bx, 1820, 120, 40), "bench")
        for px in (1340, 1570, 1810, 2040):
            _add_furn(f, pygame.Rect(px, 1822, 36, 36), "plant", color=(40, 160, 60))

        return f

    def _build_coliseum_interior(self):
        f = Floor(self.FLOOR_COLISEUM_INTERIOR, "Athletic Coliseum Interior", 1800, 1300, (44, 40, 36))

        f.add_room(Room("ci_hall", "Coliseum Hall",
                        "Indoor arena corridors and access points",
                        0, 0, 1800, 1300, (62, 56, 50)))
        f.add_room(Room("ci_court", "Arena Court",
                        "Main indoor basketball arena",
                        220, 180, 1360, 850, (176, 110, 66)))

        # Define gate coordinates for the bottom exit transition
        gate_w = 3 * DW
        gate_x = 220 + (1360 - gate_w) // 2

        # Outer perimeter walls with a gap at the bottom for the exit transition
        f.walls.extend([
            _hw(0, 0, 1800),
            _vw(0, 0, 1300), _vw(1800 - WT, 0, 1300),
        ])
        f.walls.extend(_hwall_gaps(1300 - WT, 0, 1800, [(gate_x, gate_w)]))

        # Indoor court lines (pre-rendered horizontal court from Baloncesto.png)
        f.basketball_court = pygame.Rect(476, 258, 848, 694)

        # Add hoop base walls (only the base of the hoop blocks the player!)
        # Left hoop: centered collision rect at (489, 646, 32, 24)
        f.walls.append(pygame.Rect(489, 646, 32, 24))
        
        # Right hoop: centered collision rect at (1278, 646, 32, 24)
        f.walls.append(pygame.Rect(1278, 646, 32, 24))

        # Exit back to campus at the bottom gap
        f.transitions.append(FloorTransition(
            (gate_x, 1300 - 40, gate_w, 40),
            FLOOR_CAMPUS, 3340, 1130,
            label="Campus"))
        return f

    def _build_pingpong_interior(self):
        f = Floor(self.FLOOR_PINGPONG_INTERIOR, "Ping Pong Court Interior", 1300, 1000, (40, 52, 44))

        f.add_room(Room("pi_hall", "Ping Pong Hall",
                        "Indoor practice court",
                        0, 0, 1300, 1000, (58, 72, 62),
                        tile_path="assets/UI/wood_tile_orange.png"))

        f.walls.extend([
            _hw(0, 0, 1300), _hw(0, 1000 - WT, 1300),
            _vw(0, 0, 1000), _vw(1300 - WT, 0, 1000),
        ])

        # Centered bottom door.
        door_w = 2 * DW
        door_x = (1300 - door_w) // 2
        f.walls.extend(_hwall_gaps(1000 - WT, 0, 1300, [(door_x, door_w)]))

        # Tables in a 2x2 grid.
        t_w, t_h = 220, 120
        table_pos = [
            (300, 250), (780, 250),
            (300, 550), (780, 550)
        ]
        f.ping_pong_tables = []
        for i, (tx, ty) in enumerate(table_pos):
            t_rect = pygame.Rect(tx, ty, t_w, t_h)
            f.walls.append(t_rect)
            f.furniture.append({"rect": t_rect, "color": (30, 100, 40), "outline": WHITE})
            f.ping_pong_tables.append(t_rect)
        
        # Set the main interactive table for minigame logic if needed
        f.ping_pong_table = f.ping_pong_tables[0]

        f.transitions.append(FloorTransition(
            (door_x, 1000 - WT - 34, door_w, 30),
            FLOOR_CAMPUS, 3490, 2880,
            label="Campus"))
        return f
