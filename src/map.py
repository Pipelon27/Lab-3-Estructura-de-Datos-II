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
                 is_staircase=False):
        self.id          = room_id
        self.name        = name
        self.description = description
        self.rect        = pygame.Rect(x, y, w, h)
        self.color       = color
        self.locked      = locked
        self.mission_tag = mission_tag
        self.is_staircase = is_staircase
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

    def add_room(self, room):
        self.rooms[room.id] = room

    def get_room_at(self, x, y):
        for r in self.rooms.values():
            if r.rect.collidepoint(x, y):
                return r
        return None

    def draw(self, screen, camera):
        sw, sh = screen.get_width(), screen.get_height()
        bg = camera.apply_rect(pygame.Rect(0, 0, self.width, self.height))
        pygame.draw.rect(screen, self.bg_color, bg)
        font14 = pygame.font.SysFont("arial", 14)

        for room in self.rooms.values():
            r = camera.apply_rect(room.rect)
            if r.right < 0 or r.left > sw or r.bottom < 0 or r.top > sh:
                continue
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
                screen.blit(lbl, (r.x + 8, r.y + 8))

        for wall in self.walls:
            wr = camera.apply_rect(wall)
            if wr.right < 0 or wr.left > sw or wr.bottom < 0 or wr.top > sh:
                continue
            pygame.draw.rect(screen, self.WALL_COLOR, wr)

        font_sm = pygame.font.SysFont("arial", 13, bold=True)
        for tr in self.transitions:
            r = camera.apply_rect(tr.rect)
            if r.right < 0 or r.left > sw:
                continue
            pygame.draw.rect(screen, self.TRANSITION_COLOR, r)
            pygame.draw.rect(screen, WHITE, r, 1)
            if tr.label and r.width > 20:
                lbl = font_sm.render(tr.label, True, WHITE)
                screen.blit(lbl, (r.x + 2, r.y - 16))

    def __repr__(self):
        return f"Floor({self.id}, '{self.name}', rooms={len(self.rooms)})"


# ══════════════════════════════════════════════════════════════
#  STAIRCASE CONSTANTS & HELPER
# ══════════════════════════════════════════════════════════════

STAIR_W   = 500     # room width
STAIR_H   = 280     # room height  (taller = easier to navigate)
STAIR_GAP = 80      # U-turn gap width


def _add_stair_walls(floor, rx, ry, rw, rh, gap_side):
    """Add horizontal centre wall + enclosure for a compact staircase.

    gap_side = 'right' → gap on right, wall starts from left
    gap_side = 'left'  → gap on left,  wall starts from right end
    """
    cy = ry + rh // 2
    wall_len = rw - STAIR_GAP

    if gap_side == 'right':
        floor.walls.append(_hw(rx, cy, wall_len))
        floor.walls.append(_vw(rx + rw - WT, ry, rh))   # right enclosure
    else:
        floor.walls.append(_hw(rx + STAIR_GAP, cy, wall_len))
        floor.walls.append(_vw(rx, ry, rh))              # left enclosure

    floor.walls.append(_hw(rx, ry + rh - WT, rw))        # bottom enclosure


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
                        1400, 2500, 1200, 400, (50, 58, 50)))
        f.add_room(Room("c_parking", "Parking Lot",
                        "Student and staff parking",
                        100, 2100, 1100, 700, (48, 48, 48)))
        f.add_room(Room("c_building", "Main Building",
                        "Walk through to enter 1st Floor",
                        1400, 1100, 1200, 900, (58, 52, 52),
                        mission_tag="Enter to access 1st Floor"))
        f.add_room(Room("c_fountain", "Central Fountain",
                        "Grand fountain in the courtyard",
                        1700, 2050, 600, 350, (42, 58, 62)))
        f.add_room(Room("c_gardens", "English Gardens",
                        "Manicured gardens with hedge maze",
                        100, 150, 1200, 1000, (32, 58, 32)))
        f.add_room(Room("c_tennis", "Tennis Courts",
                        "Two courts for recreation",
                        3100, 2100, 780, 750, (48, 62, 48)))
        f.add_room(Room("c_coliseum", "Athletic Coliseum",
                        "Circular coliseum with basketball court",
                        2800, 150, 1080, 950, (58, 52, 42),
                        mission_tag="Sports Arena"))

        # Outer boundary
        f.walls.extend([
            _hw(0, 0, 4000), _hw(0, 3000 - WT, 4000),
            _vw(0, 0, 3000), _vw(4000 - WT, 0, 3000),
        ])
        # Building walls  (entrance door at bottom)
        bx, by, bw, bh = 1400, 1100, 1200, 900
        bdx = bx + (bw - DW) // 2        # door X in bottom wall
        f.walls.append(_hw(bx, by, bw))
        f.walls.append(_vw(bx, by, bh))
        f.walls.append(_vw(bx + bw - WT, by, bh))
        f.walls.extend(_hwall_gaps(by + bh - WT, bx, bx + bw, [(bdx, DW)]))
        # Coliseum
        cy = 150 + (950 - DW) // 2
        f.walls.extend([_hw(2800, 150, 1080), _hw(2800, 1100 - WT, 1080)])
        f.walls.extend(_vwall_gaps(2800, 150, 1100, [(cy, DW)]))
        f.walls.append(_vw(2800 + 1080 - WT, 150, 950))
        # Tennis
        ty = 2100 + (750 - DW) // 2
        f.walls.extend([_hw(3100, 2100, 780), _hw(3100, 2850 - WT, 780)])
        f.walls.extend(_vwall_gaps(3100, 2100, 2850, [(ty, DW)]))
        f.walls.append(_vw(3100 + 780 - WT, 2100, 750))
        # Garden hedges
        f.walls.extend([
            _hw(300, 500, 500), _hw(550, 800, 550),
            _vw(750, 250, 450), _vw(450, 650, 350),
        ])

        # Portal: building entrance → 1F reception
        f.transitions.append(FloorTransition(
            (bdx, by + bh - WT - 40, DW, 30),
            FLOOR_1F, 1600, 2200,
            label="Enter"))

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
                        mission_tag="Lena's base"))
        f.add_room(Room("f1_infirmary", "Infirmary",
                        "School nurse, bandages, rest beds",
                        16, 510, 1034, 370, (55, 55, 60)))
        f.add_room(Room("f1_auditorium", "Auditorium",
                        "Large hall for assemblies",
                        16, 880, 1034, by - 880, (52, 48, 55)))
        f.add_room(Room("f1_basement_stairs", "Basement Stairs",
                        "Staircase down to the Basement",
                        bx, by, bw, bh, (40, 38, 42),
                        is_staircase=True))

        # CENTRAL
        f.add_room(Room("f1_main_hall", "Main Hall",
                        "The central hub of Ravenside High",
                        1050, 16, 1100, 1934, (50, 50, 65)))
        f.add_room(Room("f1_reception", "Reception",
                        "Front desk — entrance from campus",
                        1050, 1950, 1100, 434, (48, 48, 55)))

        # RIGHT wing
        f.add_room(Room("f1_library", "Library",
                        "Quiet study hall hiding old secrets",
                        2150, 16, 1034, 584, (52, 45, 50)))
        f.add_room(Room("f1_cafeteria", "Cafeteria",
                        "Bustling with trays, rumours, and lunch money",
                        2150, 600, 1034, 500, (58, 52, 42)))
        f.add_room(Room("f1_counselor", "Counselor's Office",
                        "Safe space — the counselor is on your side",
                        2150, 1100, 1034, sy - 1100, (55, 55, 52),
                        mission_tag="Ally"))
        f.add_room(Room("f1_stairs_2f", "Stairs to 2F",
                        "Staircase up to the 2nd Floor",
                        sx, sy, sw, sh, (52, 55, 62),
                        is_staircase=True))

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
        f.walls.extend(_vwall_gaps(2150, 16, sy + sh, [
            (250, DW), (780, DW), (1250, DW),
            (_lower_door_y(sy, sh), DW),
        ]))

        # Left horizontal dividers
        f.walls.extend([_hw(16, 510, 1034), _hw(16, 880, 1034)])
        f.walls.append(_hw(16, by, 1034))               # top of basement stairs
        f.walls.append(_hw(16, by + bh - WT, 1034))      # bottom

        # Right horizontal dividers
        f.walls.extend([_hw(2150, 600, 1034), _hw(2150, 1100, 1034)])
        f.walls.append(_hw(2150, sy, 1034))              # top of 2F stairs
        f.walls.append(_hw(2150, sy + sh - WT, 1034))    # bottom

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
        f.add_room(Room("f2_art_room", "Art Room",
                        "Canvases, paint, and creative chaos",
                        16, art_y, 1034, 650, (60, 50, 55)))
        f.add_room(Room("f2_music_room", "Music Room",
                        "Instruments hung on walls, soundproofed",
                        16, mus_y, 1034, 420, (55, 48, 58)))
        f.add_room(Room("f2_science_lab", "Science Labs",
                        "Bunsen burners, chemicals, safety goggles",
                        16, sci_y, 1034, 584, (42, 55, 60)))

        # CENTRAL
        f.add_room(Room("f2_corridor", "2F Corridor",
                        "The upper-floor hallway",
                        1050, 16, 1100, 1934, (48, 48, 58)))
        f.add_room(Room("f2_classrooms", "Classrooms",
                        "Standard classrooms for lectures",
                        1050, 1950, 1100, 434, (48, 50, 55)))

        # RIGHT wing
        f.add_room(Room("f2_director", "Director's Office",
                        "Director Walsh's office — main quest",
                        2150, 16, 1034, 500, (62, 45, 45),
                        mission_tag="Main Quest"))
        f.add_room(Room("f2_conference", "Conference Room",
                        "Long table, projector — faculty meetings",
                        2150, 516, 1034, 434, (55, 52, 48)))
        f.add_room(Room("f2_admin", "Admin Offices",
                        "Administrative staff desks",
                        2150, 950, 1034, sy - 950, (52, 52, 55)))
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
            (art_y + 200, DW), (mus_y + 200, DW), (sci_y + 200, DW),
        ]))
        # Right divider — 1F stair door in UPPER corridor
        f.walls.extend(_vwall_gaps(2150, 16, sy + sh, [
            (200, DW), (640, DW), (1100, DW),
            (_upper_door_y(sy), DW),
        ]))

        # Left horizontal dividers
        f.walls.append(_hw(16, art_y, 1034))             # below rooftop stairs
        f.walls.append(_hw(16, ry + rh - WT, 1034))      # bottom of stair area
        f.walls.extend([_hw(16, mus_y, 1034), _hw(16, sci_y, 1034)])

        # Right horizontal dividers
        f.walls.extend([_hw(2150, 516, 1034), _hw(2150, 950, 1034)])
        f.walls.append(_hw(2150, sy, 1034))
        f.walls.append(_hw(2150, sy + sh - WT, 1034))

        # Classrooms divider
        cdx = 1050 + (1100 - DW) // 2
        f.walls.extend(_hwall_gaps(1950, 1050, 2150, [(cdx, DW)]))

        # Staircase interior walls
        _add_stair_walls(f, sx, sy, sw, sh, 'right')
        _add_stair_walls(f, rx, ry, rw, rh, 'left')

        return f

    # ──────────────────────────────────────────────────────────
    #  BASEMENT  (3200 × 2400)
    # ──────────────────────────────────────────────────────────

    def _build_basement(self):
        f = Floor(3, "Basement", 3200, 2400, FLOOR_BG_COLORS[3])

        bx, by, bw, bh = self.STAIR_1F_BS

        f.add_room(Room("b_stairs_up", "Stairs to 1F",
                        "Staircase up to the 1st Floor",
                        bx, by, bw, bh, (40, 40, 48),
                        is_staircase=True))
        f.add_room(Room("b_smile_club", "Smile Club Room",
                        "Where the Smile Club holds secret meetings",
                        300, 200, 800, 550, (35, 25, 30),
                        mission_tag="Secret meetings"))
        f.add_room(Room("b_server_room", "Server Room",
                        "The Smile Club's main servers hum menacingly",
                        1150, 200, 800, 550, (28, 32, 38),
                        mission_tag="Main Target"))
        f.add_room(Room("b_surveillance", "Surveillance Center",
                        "Screens showing every hallway in the school",
                        2000, 200, 700, 550, (30, 30, 35),
                        mission_tag="Security feeds"))
        f.add_room(Room("b_detention", "Detention Cells",
                        "Holding cells — some NPCs are trapped here",
                        300, 800, 800, 500, (30, 25, 28),
                        mission_tag="Rescuable NPCs"))
        f.add_room(Room("b_terminal", "Final Terminal",
                        "The terminal where you choose the ending",
                        1150, 800, 800, 500, (38, 28, 32),
                        mission_tag="Choose your ending"))

        # Outer boundary
        f.walls.extend([
            _hw(0, 0, 3200), _hw(0, 2400 - WT, 3200),
            _vw(0, 0, 2400), _vw(3200 - WT, 0, 2400),
        ])
        # Room cluster
        f.walls.extend([
            _hw(300, 200, 2400), _hw(300, 1300 - WT, 2400),
            _vw(300, 200, 1100), _vw(2700 - WT, 200, 1100),
        ])
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

        rx, ry, rw, rh = self.STAIR_2F_RT

        f.add_room(Room("rt_stairs_down", "Stairs to 2F",
                        "Staircase down to the 2nd Floor",
                        rx, ry, rw, rh, (38, 42, 55),
                        is_staircase=True))
        f.add_room(Room("rt_terrace", "Rooftop Terrace",
                        "Open sky — secret meetings at night",
                        1200, 500, 1200, 1200, (35, 50, 65),
                        mission_tag="Night meetings"))
        f.add_room(Room("rt_antenna", "Antenna Platform",
                        "Radio antenna and satellite equipment",
                        1500, 100, 400, 350, (40, 45, 55)))
        f.add_room(Room("rt_benches", "Resting Area",
                        "Benches with a view of the campus below",
                        1300, 1750, 800, 350, (38, 48, 50)))

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
        f.walls.extend([
            _hw(1500, 100, 400), _hw(1500, 450 - WT, 400),
            _vw(1500, 100, 350), _vw(1900 - WT, 100, 350),
        ])

        return f
