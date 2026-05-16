"""
src/stair_routes.py  —  Inter-floor navigation data
=====================================================
Pre-calculated waypoints for NPC pathfinding between floors.
Each route is a list of waypoints that may include floor-switch
string commands (e.g. "SWITCH_TO_2F") which the NPC.update()
method already handles via target_queue processing.
"""

# Waypoints for staircase-based floor transitions.
# Key: (from_floor_id, to_floor_id)
# Value: list of (x, y) tuples and "SWITCH_TO_*" commands
STAIR_ROUTES = {
    # 1F → 2F via f1_stairs_2f / f2_stairs_1f
    (1, 2): [
        (2400, 1860),
        "SWITCH_TO_F2",
        (2400, 1790),
        (2180, 1790),
    ],
    # 2F → 1F (reverse)
    (2, 1): [
        (2400, 1790),
        "SWITCH_TO_F1",
        (2400, 1936),
        (2180, 1936),
    ],
    # 1F → Basement via f1_basement_stairs
    (1, 3): [
        (800, 1860),
        "SWITCH_TO_F3",
        (800, 1720),
    ],
    # Basement → 1F (reverse)
    (3, 1): [
        (800, 1720),
        (800, 1860),
        "SWITCH_TO_F1",
        (800, 1720),
    ],
    # 2F → Rooftop via f2_roof_stairs
    (2, 4): [
        (800, 16),
        "SWITCH_TO_F4",
        (800, 296),
    ],
    # Rooftop → 2F (reverse)
    (4, 2): [
        (800, 296),
        (800, 16),
        "SWITCH_TO_F2",
        (800, 296),
    ],
    # Campus → 1F (portal at building entrance)
    (0, 1): [
        (2000, 2050),
        "SWITCH_TO_F1",
        (1600, 2200),
    ],
    # 1F → Campus (reverse)
    (1, 0): [
        (1600, 2200),
        "SWITCH_TO_F0",
        (2000, 2050),
    ],
}

# Floor adjacency graph for multi-hop route planning
# (e.g. Campus→Basement requires Campus→1F→Basement)
FLOOR_GRAPH = {
    0: [1],        # Campus connects to 1F
    1: [0, 2, 3],  # 1F connects to Campus, 2F, Basement
    2: [1, 4],     # 2F connects to 1F, Rooftop
    3: [1],        # Basement connects to 1F
    4: [2],        # Rooftop connects to 2F
}

# Mapping: room_id → floor_id
ROOM_FLOOR_MAP = {
    # Campus (Floor 0)
    "c_roundabout": 0, "c_parking": 0, "c_road": 0, "c_building": 0,
    "c_fountain": 0, "c_gardens": 0, "c_tennis": 0,
    "c_coliseum": 0, "c_coliseum_court": 0,
    # 1st Floor (Floor 1)
    "f1_computer_lab": 1, "f1_infirmary": 1, "f1_auditorium": 1,
    "f1_basement_stairs": 1, "f1_men_bath": 1, "f1_women_bath": 1,
    "f1_main_hall": 1, "f1_reception": 1, "f1_library": 1,
    "f1_cafeteria": 1, "f1_counselor": 1, "f1_stairs_2f": 1,
    # 2nd Floor (Floor 2)
    "f2_roof_stairs": 2, "f2_art_room": 2, "f2_music_room": 2,
    "f2_science_lab": 2, "f2_corridor": 2, "f2_classrooms": 2,
    "f2_director": 2, "f2_conference": 2, "f2_admin": 2, "f2_stairs_1f": 2,
    # Basement (Floor 3)
    "b_stairs_up": 3, "b_smile_club": 3, "b_server_room": 3,
    "b_surveillance": 3, "b_detention": 3, "b_terminal": 3,
    # Rooftop (Floor 4)
    "rt_stairs_down": 4, "rt_terrace": 4, "rt_benches": 4,
    # Special interiors
    "ci_hall": 5, "ci_court": 5,
    "pi_hall": 6,
}


def find_floor_path(from_floor: int, to_floor: int) -> list[int]:
    """BFS to find the shortest path of floors between *from_floor* and *to_floor*.
    Returns a list of floor IDs including both endpoints.
    """
    if from_floor == to_floor:
        return [from_floor]
    visited = {from_floor}
    queue = [[from_floor]]
    while queue:
        path = queue.pop(0)
        current = path[-1]
        for neighbour in FLOOR_GRAPH.get(current, []):
            if neighbour == to_floor:
                return path + [neighbour]
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append(path + [neighbour])
    return [from_floor]  # fallback — unreachable floor


def build_multi_floor_route(from_floor: int, to_floor: int) -> list:
    """Build a complete waypoint chain for travelling across multiple floors.
    Returns a mixed list of (x,y) tuples and "SWITCH_TO_FX" strings.
    """
    floor_path = find_floor_path(from_floor, to_floor)
    if len(floor_path) <= 1:
        return []
    route: list = []
    for i in range(len(floor_path) - 1):
        hop = (floor_path[i], floor_path[i + 1])
        hop_waypoints = STAIR_ROUTES.get(hop, [])
        route.extend(hop_waypoints)
    return route
