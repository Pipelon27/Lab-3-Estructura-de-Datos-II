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
    Character,
)


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
    WALL_TOP_COLOR   = (238, 240, 248)
    WALL_FACE_COLOR  = (128, 126, 120)
    WALL_SHADE_COLOR = (74, 70, 76)
    WALL_EDGE_COLOR  = (48, 48, 70)
    WALL_HILITE      = (255, 255, 255)
    TRANSITION_COLOR = (80, 160, 240)
    STAIR_STEP_A     = (55, 55, 68)
    STAIR_STEP_B     = (48, 48, 58)
    STAIR_ARROW_COL  = (120, 130, 160)

    def __init__(self, floor_id, name, width, height, bg_color):
        self.id       = floor_id
        self.name     = name
        self.width    = width
        self.height   = height
        self.bg_color = bg_color
        self.rooms:       dict[str, Room]       = {}
        self.walls:       list[pygame.Rect]     = []
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

    def draw(self, screen, camera):
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

        font14 = pygame.font.SysFont("arial", 14)

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
                steps = max(4, r.height // 12)
                for si in range(steps):
                    sy = r.y + int(r.height * si / steps)
                    col = self.STAIR_STEP_A if si % 2 == 0 else self.STAIR_STEP_B
                    pygame.draw.line(screen, col,
                                     (r.x + 4, sy), (r.x + r.width - 4, sy), 1)
                if r.width > 40 and r.height > 30:
                    arr = font14.render("\u2191\u2193", True, self.STAIR_ARROW_COL)
                    screen.blit(arr, (r.centerx - arr.get_width() // 2,
                                      r.centery - arr.get_height() // 2))
            elif r.width > 50:
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

        door_color = (180, 180, 205)
        for door in self.doors:
            dr = camera.apply_rect(door.rect)
            if dr.right < 0 or dr.left > sw or dr.bottom < 0 or dr.top > sh:
                continue
            pygame.draw.rect(screen, door.color or door_color, dr)
            pygame.draw.rect(screen, (40, 40, 50), dr, 1)
            # Visual indicator for locked doors
            if door.locked:
                pygame.draw.line(screen, (200, 50, 50), (dr.x, dr.y), (dr.right, dr.bottom), 2)
                pygame.draw.line(screen, (200, 50, 50), (dr.right, dr.y), (dr.left, dr.bottom), 2)

        for furn in self.furniture:
            fr = camera.apply_rect(furn["rect"])
            if fr.right < 0 or fr.left > sw or fr.bottom < 0 or fr.top > sh:
                continue
            if furn.get("type") == "bookshelf":
                self._draw_bookshelf(screen, fr)
                continue
            pygame.draw.rect(screen, furn["color"], fr)
            outline = furn.get("outline")
            if outline:
                pygame.draw.rect(screen, outline, fr, 2)

        for wall in self.walls:
            wr = camera.apply_rect(wall)
            if wr.right < 0 or wr.left > sw or wr.bottom < 0 or wr.top > sh:
                continue
            
            # Special case for ping pong tables
            if wall in getattr(self, 'ping_pong_tables', []):
                self._draw_ping_pong_table(screen, wr)
            elif getattr(self, 'ping_pong_table', None) and wall == self.ping_pong_table:
                self._draw_ping_pong_table(screen, wr)
            # Skip drawing fountain collision rect (it's invisible, only for collision)
            elif getattr(self, 'fountain_rect', None) and wall == self.fountain_rect:
                continue
            else:
                self._draw_topdown_wall(screen, wr)

        # Draw realistic fountain for Central Fountain room
        if self.id == 0:  # Campus floor
            fountain_room = self.rooms.get("c_fountain")
            if fountain_room:
                import math, time
                cx = fountain_room.rect.centerx
                cy = fountain_room.rect.centery
                t = time.time()
                fx, fy = camera.apply_pos(cx, cy)

                # STONE BASE - multiple tiers for realistic look
                # Bottom tier (outer rim)
                base_r1 = 80
                pygame.draw.circle(screen, (100, 105, 110), (fx, fy), base_r1)
                pygame.draw.circle(screen, (70, 75, 80), (fx, fy), base_r1, 3)
                # Shadow/depth ring
                pygame.draw.circle(screen, (80, 85, 90), (fx, fy), base_r1 - 5)
                # Middle tier
                base_r2 = 55
                pygame.draw.circle(screen, (120, 125, 130), (fx, fy), base_r2)
                pygame.draw.circle(screen, (90, 95, 100), (fx, fy), base_r2, 2)
                # Top tier (inner basin edge)
                base_r3 = 35
                pygame.draw.circle(screen, (140, 145, 150), (fx, fy), base_r3)
                pygame.draw.circle(screen, (110, 115, 120), (fx, fy), base_r3, 2)

                # WATER BASIN (inside the stone rim)
                water_r = 30
                # Dark water base
                pygame.draw.circle(screen, (40, 70, 90), (fx, fy), water_r)
                # Water shimmer/reflections
                shimmer_alpha = int(60 + math.sin(t * 2) * 20)
                shimmer_surf = pygame.Surface((water_r*2, water_r*2), pygame.SRCALPHA)
                pygame.draw.circle(shimmer_surf, (100, 160, 200, shimmer_alpha), (water_r, water_r), water_r)
                screen.blit(shimmer_surf, (fx - water_r, fy - water_r))

                # CENTRAL PILLAR/STATUE BASE
                pillar_r = 12
                pillar_h = 35
                # Pillar shadow
                pygame.draw.ellipse(screen, (50, 55, 60), (fx - pillar_r - 3, fy + pillar_r - 3, pillar_r*2 + 6, pillar_r))
                # Pillar body (stone cylinder)
                pygame.draw.rect(screen, (130, 135, 140), (fx - pillar_r, fy - pillar_h, pillar_r*2, pillar_h))
                # Pillar highlight
                pygame.draw.rect(screen, (150, 155, 160), (fx - pillar_r + 2, fy - pillar_h + 2, pillar_r, pillar_h - 4))
                # Pillar top cap
                pygame.draw.ellipse(screen, (140, 145, 150), (fx - pillar_r - 2, fy - pillar_h - 4, pillar_r*2 + 4, 8))
                pygame.draw.ellipse(screen, (160, 165, 170), (fx - pillar_r, fy - pillar_h - 2, pillar_r*2, 6))

                # WATER SPOUT from top of pillar
                spout_h = int(25 + math.sin(t * 3) * 5)
                spout_r = 8
                # Water column (tapering)
                for i in range(spout_h):
                    progress = i / max(spout_h, 1)
                    w = int(spout_r * (1 - progress * 0.5))
                    alpha = int(200 - progress * 80)
                    col_surf = pygame.Surface((w*2, 2), pygame.SRCALPHA)
                    col_surf.fill((180, 220, 255, alpha))
                    screen.blit(col_surf, (fx - w, fy - pillar_h - 2 - i))

                # TOP WATER BURST/BOWL
                bowl_y = fy - pillar_h - spout_h - 5
                # Bowl base
                pygame.draw.ellipse(screen, (160, 200, 240), (fx - 18, bowl_y, 36, 12))
                pygame.draw.ellipse(screen, (140, 180, 220), (fx - 15, bowl_y + 2, 30, 8))
                # Overflow streams
                for angle in [math.pi/2, math.pi*0.8, math.pi*1.2]:
                    stream_len = 15 + math.sin(t * 4 + angle) * 3
                    sx1 = fx + int(math.cos(angle) * 12)
                    sy1 = bowl_y + 6
                    sx2 = fx + int(math.cos(angle) * (12 + stream_len))
                    sy2 = bowl_y + 6 + int(stream_len * 0.3)
                    pygame.draw.line(screen, (200, 230, 255), (sx1, sy1), (sx2, sy2), 3)

                # RIPPLES in basin water
                for i, (r_base, speed, offset) in enumerate([(20, 2, 0), (25, 1.5, 1), (15, 2.5, 2)]):
                    ripple_r = r_base + math.sin(t * speed + offset) * 3
                    ripple_alpha = int(100 - i * 20 + math.sin(t * 3 + offset) * 30)
                    ripple_surf = pygame.Surface((int(ripple_r)*2, int(ripple_r)*2), pygame.SRCALPHA)
                    pygame.draw.circle(ripple_surf, (150, 200, 230, ripple_alpha),
                                      (int(ripple_r), int(ripple_r)), int(ripple_r), 2)
                    screen.blit(ripple_surf, (fx - int(ripple_r), fy - int(ripple_r)))

                # SPLASH DROPLETS falling from bowl
                for i in range(12):
                    drop_t = (t * 3 + i * 0.5) % 2  # cycle time for each drop
                    if drop_t < 0.3:  # only show during part of cycle
                        continue
                    angle = (i / 12) * math.pi * 2 + math.sin(t) * 0.2
                    # Parabolic arc for falling drops
                    fall_progress = (drop_t - 0.3) / 1.7
                    drop_dist = 10 + fall_progress * 35
                    drop_height = 40 * (1 - (fall_progress - 0.5)**2 * 4)  # arc
                    if drop_height < 0:
                        drop_height = 0
                    dfx = fx + int(math.cos(angle) * drop_dist)
                    dfy = bowl_y + 10 + int(drop_height)
                    drop_size = int(3 + math.sin(drop_t * 10) * 2)
                    # Fade out near bottom
                    alpha = int(255 * (1 - fall_progress * 0.7))
                    drop_surf = pygame.Surface((drop_size*2, drop_size*2), pygame.SRCALPHA)
                    pygame.draw.circle(drop_surf, (220, 240, 255, alpha), (drop_size, drop_size), drop_size)
                    screen.blit(drop_surf, (dfx - drop_size, dfy - drop_size))

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
                for item in self.garden_decorations:
                    if item[0] == 'tree':
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
            
            if hasattr(self, "basketball_court"):
                import math
                bc = self.basketball_court
                r = camera.apply_rect(bc)
                if r.right > 0 and r.left < sw:
                    # Lines are white
                    lc = (240, 240, 240)
                    # Outer boundary
                    pygame.draw.rect(screen, lc, r, 3)
                    # Mid-court line
                    pygame.draw.line(screen, lc, (r.centerx, r.top), (r.centerx, r.bottom), 3)
                    # Center circle
                    pygame.draw.circle(screen, lc, r.center, 70, 3)
                    
                    # Arcs/Lines for each half
                    key_w = 220
                    key_h = 300
                    tp_rad = 380
                    
                    for side in [-1, 1]:
                        # Key area (rectangle)
                        if side == -1:
                            kx = r.left
                        else:
                            kx = r.right - key_w
                        
                        ky = r.centery - key_h // 2
                        key_rect = pygame.Rect(kx, ky, key_w, key_h)
                        pygame.draw.rect(screen, lc, key_rect, 3)
                        
                        # Three point line (large arc)
                        tp_center = (r.left if side == -1 else r.right, r.centery)
                        tp_rect = pygame.Rect(tp_center[0] - tp_rad, tp_center[1] - tp_rad, tp_rad * 2, tp_rad * 2)
                        if side == -1:
                            # Left side arc
                            pygame.draw.arc(screen, lc, tp_rect, -math.pi/2, math.pi/2, 3)
                        else:
                            # Right side arc
                            pygame.draw.arc(screen, lc, tp_rect, math.pi/2, 3*math.pi/2, 3)

        # Transitions drawing - only for interior floors (to show the exit)
        if self.id != 0:
            font_sm = pygame.font.SysFont("arial", 13, bold=True)
            for tr in self.transitions:
                r = camera.apply_rect(tr.rect)
                if r.right < 0 or r.left > sw:
                    continue
                pygame.draw.rect(screen, (80, 180, 255, 180), r)
                pygame.draw.rect(screen, WHITE, r, 1)
                if tr.label and r.width > 20:
                    lbl = font_sm.render(tr.label, True, WHITE)
                    screen.blit(lbl, (r.x + 2, r.y - 16))

    def _draw_topdown_wall(self, screen: pygame.Surface, rect: pygame.Rect):
        """Draw a collision wall with a top-down 3D treatment."""
        if rect.width <= 0 or rect.height <= 0:
            return

        horizontal = rect.width >= rect.height
        thickness = rect.height if horizontal else rect.width
        depth = max(6, min(26, int(thickness * 0.75)))
        depth = min(depth, max(4, thickness))

        shadow = rect.move(4, 5)
        shadow_surf = pygame.Surface((shadow.width, shadow.height), pygame.SRCALPHA)
        shadow_surf.fill((*BLACK, 45))
        screen.blit(shadow_surf, shadow)

        pygame.draw.rect(screen, self.WALL_FACE_COLOR, rect)

        if horizontal:
            face = pygame.Rect(rect.x, rect.bottom - depth, rect.width, depth)
            cap_h = max(3, rect.height - depth)
            cap = pygame.Rect(rect.x + 2, rect.y + 2, max(1, rect.width - 4), max(1, cap_h - 2))
            pygame.draw.rect(screen, self.WALL_SHADE_COLOR, face)
            pygame.draw.rect(screen, self.WALL_TOP_COLOR, cap)
            pygame.draw.line(
                screen, self.WALL_HILITE,
                (rect.left + 1, rect.top + 1), (rect.right - 2, rect.top + 1), 2
            )
            pygame.draw.line(
                screen, self.WALL_EDGE_COLOR,
                (rect.left, rect.bottom - depth), (rect.right, rect.bottom - depth), 2
            )
        else:
            face = pygame.Rect(rect.right - depth, rect.y, depth, rect.height)
            cap_w = max(3, rect.width - depth)
            cap = pygame.Rect(rect.x + 2, rect.y + 2, max(1, cap_w - 2), max(1, rect.height - 4))
            pygame.draw.rect(screen, self.WALL_SHADE_COLOR, face)
            pygame.draw.rect(screen, self.WALL_TOP_COLOR, cap)
            pygame.draw.line(
                screen, self.WALL_HILITE,
                (rect.left + 1, rect.top + 1), (rect.left + 1, rect.bottom - 2), 2
            )
            pygame.draw.line(
                screen, self.WALL_EDGE_COLOR,
                (rect.right - depth, rect.top), (rect.right - depth, rect.bottom), 2
            )

        pygame.draw.rect(screen, self.WALL_EDGE_COLOR, rect, 2)

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
            c_idx = row
            while x < rect.right - pad - 6:
                w = 5 + ((x + row * 3) % 5)
                h = max(8, shelf_h - 5 - ((x + row) % 4))
                color = book_colors[c_idx % len(book_colors)]
                pygame.draw.rect(screen, color, pygame.Rect(x, y + shelf_h - h - 1, w, h))
                x += w + 3
                c_idx += 1

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
                            pygame.draw.rect(screen, (110, 122, 142), rooftop)
                            pygame.draw.rect(screen, (70, 82, 102), rooftop, 3)
                            ac1 = pygame.Rect(rooftop.x + 20, rooftop.y + 20, 46, 26)
                            ac2 = pygame.Rect(rooftop.right - 70, rooftop.y + 28, 50, 28)
                            pygame.draw.rect(screen, (82, 88, 98), ac1)
                            pygame.draw.rect(screen, (82, 88, 98), ac2)
                            pygame.draw.rect(screen, (48, 54, 64), ac1, 2)
                            pygame.draw.rect(screen, (48, 54, 64), ac2, 2)
                        else:
                            pygame.draw.rect(screen, spec["trim_color"], roof_rect)
                            pygame.draw.line(screen, (45, 45, 50), (roof_rect.x, roof_rect.bottom - 2),
                                             (roof_rect.right, roof_rect.bottom - 2), 2)

                        pygame.draw.rect(screen, spec["wall_color"], facade_rect)
                        pygame.draw.rect(screen, spec["trim_color"], facade_rect, 3)
                        sign_rect = pygame.Rect(facade_rect.x + 14, facade_rect.y + 8, facade_rect.width - 28, 26)
                        pygame.draw.rect(screen, (72, 72, 82), sign_rect)
                        pygame.draw.rect(screen, (205, 205, 215), sign_rect, 2)
                        sign_font = pygame.font.SysFont("arial", max(11, min(17, sign_rect.height - 7)), bold=True)
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
                            font_title = pygame.font.SysFont("arial", 24, bold=True)
                            text = font_title.render("RAVENSIDE HIGH SCHOOL", True, (220, 230, 240))
                            tw, th = text.get_size()
                            # Positioned above the door
                            tx = door_rect.centerx - tw // 2
                            ty = door_rect.y - th - 15
                            # Subtle shadow/plate behind text
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
                        100, 150, 1200, 1000, (32, 58, 32)))
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
        f.walls.extend([
            _hw(0, 0, 4000), _hw(0, 3000 - WT, 4000),
            _vw(0, 0, 3000), _vw(4000 - WT, 0, 3000),
        ])
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
        # Garden hedges
        f.walls.extend([
            _hw(300, 500, 500), _hw(550, 800, 550),
            _vw(750, 250, 450), _vw(450, 650, 350),
        ])
        
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
        for _ in range(50):
            for _ in range(10):
                tx = rng.randint(150, 1250)
                ty = rng.randint(200, 1100)
                rad = rng.randint(20, 35)
                treect = pygame.Rect(tx - rad//2, ty - rad//2, rad, rad)
                if not any(treect.colliderect(w) for w in f.walls):
                    f.garden_decorations.append(('tree', tx, ty, rad))
                    f.walls.append(pygame.Rect(tx - 10, ty - 10, 20, 20))
                    break
        for _ in range(120):
            fx = rng.randint(150, 1250)
            fy = rng.randint(200, 1100)
            color = rng.choice([(255, 100, 100), (255, 200, 100), (150, 150, 255), (255, 200, 200), (255, 255, 255)])
            f.garden_decorations.append(('flower', fx, fy, color))

        # Benches
        for _ in range(10):
            for _ in range(10):
                bx = rng.randint(150, 1250)
                by = rng.randint(200, 1100)
                rect = pygame.Rect(bx, by, 60, 25)
                if not any(rect.colliderect(w) for w in f.walls):
                    f.furniture.append({"rect": rect, "color": (120, 80, 40), "outline": (80, 50, 20)})
                    f.walls.append(rect)
                    break
        
        # Roundabout bushes decoration (neat rows on each side)
        for side_x in [1420, 2580]: # Left and Right edges
            for by in range(2520, 2850, 45):
                rad = 18
                f.garden_decorations.append(('bush', side_x, by, rad))
        
        # Parking Lot bushes (strictly outside the perimeter)
        # Top edge (above the parking lot)
        for px in range(20, 1180, 50):
            f.garden_decorations.append(('bush', px, 2100 - 25, 18))
        # Right edge (to the right of the parking lot)
        for py in range(2100, 2850, 50):
            f.garden_decorations.append(('bush', 1200 + 25, py, 18))

        # Main Building perimeters
        for bx in range(1400, 2600, 60): # Top
            f.garden_decorations.append(('bush', bx, 1100 - 25, 20))
        for by in range(1100, 1950, 60): # Sides
            f.garden_decorations.append(('bush', 1400 - 25, by, 20))
            f.garden_decorations.append(('bush', 2600 + 25, by, 20))

        # Athletic Coliseum perimeters
        for cx in range(2800, 3880, 70): # Top
            f.garden_decorations.append(('bush', cx, 150 - 30, 22))
        for cy in range(150, 1050, 70): # Sides
            f.garden_decorations.append(('bush', 2800 - 30, cy, 22))
            f.garden_decorations.append(('bush', 3880 + 30, cy, 22))

        # Ping Pong Court perimeters
        for tx in range(3100, 3880, 60): # Top
            f.garden_decorations.append(('bush', tx, 2100 - 25, 20))
        for ty in range(2100, 2750, 60): # Sides
            f.garden_decorations.append(('bush', 3100 - 25, ty, 20))
            f.garden_decorations.append(('bush', 3880 + 25, ty, 20))

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
            self.FLOOR_PINGPONG_INTERIOR, 800, 1000,
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
        # Library door at y=300 (center of library room y=16+584/2=308)
        f.walls.extend(_vwall_gaps(2150, 16, sy + sh, [
            (250, DW), (300, 3 * DW),  # Library door - wider (3x)
            (780 - DW, 3 * DW), (1250, DW),
            (_lower_door_y(sy, sh), DW),
        ]))
        # Cafeteria door object (Triple size)
        f.add_door(Door("door_cafeteria", 2150, 780 - DW, 16, 3 * DW, is_vertical=True))

        # ── Cafeteria furniture ──────────────────────────────
        TABLE_COL  = (100, 70, 45)
        TABLE_OUTL = (80, 55, 35)
        COUNTER_COL  = (110, 80, 50)
        COUNTER_OUTL = (90, 65, 40)

        # L-shaped serving counter (top-right corner of cafeteria)
        # It sticks to the top wall (y=616) and right wall (x=3184)
        counter_h = pygame.Rect(2700, 616, 484, 40)
        counter_v = pygame.Rect(3144, 616, 40, 350)
        f.furniture.append({"rect": counter_h, "color": COUNTER_COL, "outline": COUNTER_OUTL})
        f.furniture.append({"rect": counter_v, "color": COUNTER_COL, "outline": COUNTER_OUTL})
        f.walls.extend([counter_h, counter_v])

        # 3 dining tables (vertical rectangles spread across the cafeteria)
        caf_tables = [
            pygame.Rect(2300, 720, 130, 300),  # left table
            pygame.Rect(2560, 720, 130, 300),  # centre table
            pygame.Rect(2860, 720, 130, 300),  # right table
        ]
        for tbl in caf_tables:
            f.furniture.append({"rect": tbl, "color": TABLE_COL, "outline": TABLE_OUTL})
            f.walls.append(tbl)

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
        f.add_room(Room("rt_antenna", "Antenna Platform",
                        "Radio antenna and satellite equipment",
                        1500, 100, 400, 350, (40, 45, 55),
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

        # Parapet
        f.walls.extend([
            _hw(1200, 500, 1200), _hw(1200, 1700 - WT, 1200),
        ])
        f.walls.extend(_vwall_gaps(1200, 500, 1700, [(900, DW)]))
        f.walls.append(_vw(2400 - WT, 500, 1200))
        # Antenna enclosure
        # Antenna enclosure
        f.walls.extend([
            _hw(1500, 100, 400), _hw(1500, 450 - WT, 400),
        ])
        f.walls.extend(_vwall_gaps(1500, 100, 450, [(235, DW)]))
        f.walls.append(_vw(1900 - WT, 100, 350))
        f.add_door(Door("rt_antenna_door", 1500, 235, WT, DW, is_vertical=True, color=(100, 100, 120)))

        return f

    def _build_coliseum_interior(self):
        f = Floor(self.FLOOR_COLISEUM_INTERIOR, "Athletic Coliseum Interior", 1800, 1300, (44, 40, 36))

        f.add_room(Room("ci_hall", "Coliseum Hall",
                        "Indoor arena corridors and access points",
                        0, 0, 1800, 1300, (62, 56, 50)))
        f.add_room(Room("ci_court", "Arena Court",
                        "Main indoor basketball arena",
                        220, 180, 1360, 850, (176, 110, 66)))

        f.walls.extend([
            _hw(0, 0, 1800), _hw(0, 1300 - WT, 1800),
            _vw(0, 0, 1300), _vw(1800 - WT, 0, 1300),
        ])

        # Court enclosure with a center gate at the bottom, top corridor gap, and side corridors.
        gate_w = 3 * DW
        gate_x = 220 + (1360 - gate_w) // 2
        f.walls.extend(_hwall_gaps(180, 220, 220 + 1360, [(gate_x, gate_w)]))
        # Left wall with gap for corridor
        f.walls.extend(_vwall_gaps(220, 180, 180 + 850, [(180 + 350, 150)]))
        # Right wall with gap for corridor
        f.walls.extend(_vwall_gaps(220 + 1360 - WT, 180, 180 + 850, [(180 + 350, 150)]))
        f.walls.extend(_hwall_gaps(180 + 850 - WT, 220, 220 + 1360, [(gate_x, gate_w)]))
        
        # Entrance Hallway walls (purple wall requested by user)
        f.walls.append(_vw(gate_x - WT, 180 + 850, 1300 - (180 + 850)))
        f.walls.append(_vw(gate_x + gate_w, 180 + 850, 1300 - (180 + 850)))
        # Block the rest of the bottom area except the hallway
        f.walls.append(pygame.Rect(0, 180 + 850, gate_x - WT, 1300 - (180 + 850)))
        f.walls.append(pygame.Rect(gate_x + gate_w + WT, 180 + 850, 1800 - (gate_x + gate_w + WT), 1300 - (180 + 850)))

        # Indoor court lines.
        f.basketball_court = pygame.Rect(220 + WT, 180 + WT, 1360 - 2 * WT, 850 - 2 * WT)

        # Exit back to campus at the very bottom of the hallway (purple cross requested by user).
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
