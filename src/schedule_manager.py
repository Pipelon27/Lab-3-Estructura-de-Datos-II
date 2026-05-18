"""
src/schedule_manager.py  —  NPC Routine & Crowd Control System
================================================================
Manages the daily routines of all JSON-loaded NPCs (114 entities).
Handles:
 - Subgroup assignment based on social group
 - Time-block-based location assignment
 - Hybrid navigation (physical when on player's floor, teleport when off-screen)
 - Room capacity / crowd control
 - Detention system (Counselor's Office, 10:00-12:00)
 - Staggered movement delays for natural feel
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.npc import NPCManager, NPC
    from src.map import SchoolMap

from src.stair_routes import ROOM_FLOOR_MAP, build_multi_floor_route
from src.npc import get_safe_spawn_point


class ScheduleManager:
    """Manages NPC routines, crowd control, and hybrid navigation."""

    # ── Subgroup → preferred rooms ──────────────────────────────
    # Each social group is split 50/50 into two subgroups with
    # distinct zone preferences to avoid clustering.
    SUBGROUP_ZONES: dict[str, list[str]] = {
        # Academics (24 NPCs → 12 + 12)
        "academics_study":   ["f1_library", "f2_science_lab"],
        "academics_social":  ["f1_main_hall", "f2_corridor"],
        # Athletes (23 NPCs → 12 + 11)
        "athletes_sports":   ["ci_court", "ci_hall"],
        "athletes_casual":   ["c_tennis", "pi_hall"],
        # Populars (23 NPCs → 12 + 11)
        "populars_social":   ["c_fountain", "rt_terrace"],
        "populars_influence":["f2_corridor", "f1_main_hall"],
        # Rebels (17 NPCs → 9 + 8)
        "rebels_underground":["b_smile_club", "c_parking"],
        "rebels_roaming":    ["c_gardens", "f2_corridor"],
        # Tech Club (23 NPCs → 12 + 11)
        "tech_lab":          ["f1_computer_lab", "b_server_room"],
        "tech_casual":       ["f2_science_lab", "f1_library"],
    }

    # ── Social group → subgroup name mapping ────────────────────
    GROUP_TO_SUBGROUPS: dict[str, tuple[str, str]] = {
        "academics": ("academics_study", "academics_social"),
        "athletes":  ("athletes_sports", "athletes_casual"),
        "populars":  ("populars_social", "populars_influence"),
        "rebels":    ("rebels_underground", "rebels_roaming"),
        "tech_club": ("tech_lab", "tech_casual"),
    }

    # ── Room capacity limits ────────────────────────────────────
    ROOM_CAPACITY: dict[str, int] = {
        "f1_infirmary": 6, "f1_men_bath": 8, "f1_women_bath": 8,
        "f2_art_room": 10, "f2_music_room": 8, "f2_conference": 8,
        "f2_director": 3, "b_detention": 6, "b_terminal": 4,
        "b_surveillance": 4, "b_server_room": 8,
        "f1_cafeteria": 15, "c_fountain": 15,
        "c_gardens": 20, "rt_terrace": 15,
        "f1_counselor": 8, "pi_hall": 10,
    }
    DEFAULT_CAPACITY = 12

    # ── Time blocks (minutes from midnight) ─────────────────────
    # Single time block so NPCs stay in their assigned room ALL DAY
    TIME_BLOCKS: list[tuple[int, int, str, float]] = [
        (0,  1440, "classes",    0.8),   # 00:00-24:00
    ]

    RECESS_ZONES: list[str] = ["f1_cafeteria", "c_fountain", "c_gardens"]
    TRANSIT_ZONES: list[str] = ["f1_main_hall", "f2_corridor", "f1_men_bath", "f1_women_bath"]
    ARRIVAL_ZONES: list[str] = ["c_parking", "c_gardens", "c_fountain"]

    # Detention config
    DETENTION_ROOM = "f1_counselor"
    DETENTION_START = 0
    DETENTION_END = 0
    DETENTION_COUNT = (2, 4)  # min, max NPCs to detain

    def __init__(self):
        self._current_block: str = ""
        self._room_counts: dict[str, int] = {}
        self._detention_active: bool = False
        self._detention_npcs: list[str] = []  # IDs of detained NPCs
        self._managed_npc_ids: set[str] = set()
        self._allocation_map: dict[str, str] = {}

    # ──────────────────────────────────────────────────────────
    #  SUBGROUP ASSIGNMENT
    # ──────────────────────────────────────────────────────────

    def assign_subgroups(self, npc_manager: NPCManager) -> None:
        """Divide each social group's NPCs 50/50 into two subgroups."""
        from settings import SocialGroup

        # Bucket NPCs by their social group
        group_buckets: dict[str, list] = {}
        blocked_ids = {
            "npc_gordon", "npc_oscar", "npc_director",
            "npc_oscar_obs1", "npc_oscar_obs2", "npc_oscar_obs3", "npc_oscar_obs4",
            "npc_bath_m_attendant", "npc_bath_f_attendant",
            "npc_noah_carter",
        }
        for npc in npc_manager.npcs.values():
            if npc.id in blocked_ids:
                continue
            if getattr(npc, "ignore_schedule", False):
                continue
            group_name = npc.group.value if hasattr(npc.group, "value") else str(npc.group)
            group_name = group_name.lower()
            if group_name not in self.GROUP_TO_SUBGROUPS:
                # outsiders or faculty — assign to a random subgroup
                group_name = random.choice(list(self.GROUP_TO_SUBGROUPS.keys()))
            group_buckets.setdefault(group_name, []).append(npc)

        for group_name, npcs in group_buckets.items():
            subgroup_a, subgroup_b = self.GROUP_TO_SUBGROUPS[group_name]
            random.shuffle(npcs)
            half = len(npcs) // 2
            for npc in npcs[:half]:
                npc.subgroup = subgroup_a
                self._managed_npc_ids.add(npc.id)
            for npc in npcs[half:]:
                npc.subgroup = subgroup_b
                self._managed_npc_ids.add(npc.id)

    # ──────────────────────────────────────────────────────────
    #  TIME BLOCK DETECTION
    # ──────────────────────────────────────────────────────────

    def _get_block(self, time_minutes: float) -> tuple[str, float] | None:
        """Return (block_name, primary_ratio) for the current time, or None."""
        for start, end, name, ratio in self.TIME_BLOCKS:
            if start <= time_minutes < end:
                return name, ratio
        return None

    # ──────────────────────────────────────────────────────────
    #  CAPACITY TRACKING
    # ──────────────────────────────────────────────────────────

    def _recount_rooms(self, npc_manager: NPCManager, school_map: SchoolMap) -> None:
        """Recount how many managed NPCs are in each room."""
        self._room_counts.clear()
        for npc_id in self._managed_npc_ids:
            npc = npc_manager.npcs.get(npc_id)
            if not npc:
                continue
            floor = school_map.get_floor(npc.current_floor)
            if not floor:
                continue
            room = floor.get_room_at(npc.rect.centerx, npc.rect.centery)
            if room:
                self._room_counts[room.id] = self._room_counts.get(room.id, 0) + 1

    def update(self, time_minutes: float,
               npc_manager: NPCManager, school_map: SchoolMap,
               player_floor: int, is_visible=None, day_number: int = 1) -> None:
        """Called every frame from _update_class_schedule. Detects block changes.
        
        Args:
            is_visible: Optional callback(npc) -> bool. When provided,
                NPCs where is_visible returns True will use physical
                navigation instead of teleportation.
        """
        block_info = self._get_block(time_minutes)
        if not block_info:
            return

        block_name, primary_ratio = block_info

        # Detect block transition
        if block_name != self._current_block:
            old_block = self._current_block
            self._current_block = block_name
            self._recount_rooms(npc_manager, school_map)
            self._on_block_change(block_name, primary_ratio,
                                  npc_manager, school_map, player_floor,
                                  is_visible=is_visible, day_number=day_number)

        # Check detention timing
        if (self.DETENTION_START <= time_minutes < self.DETENTION_END
                and not self._detention_active):
            self._trigger_detention(npc_manager, school_map, player_floor,
                                    is_visible=is_visible)
        elif time_minutes >= self.DETENTION_END and self._detention_active:
            self._release_detention(npc_manager, school_map, player_floor,
                                     is_visible=is_visible)

    # ──────────────────────────────────────────────────────────
    #  BLOCK TRANSITION
    # ──────────────────────────────────────────────────────────

    def _on_block_change(self, block_name: str, primary_ratio: float,
                          npc_manager: NPCManager, school_map: SchoolMap,
                          player_floor: int, is_visible=None, day_number: int = 1) -> None:
        """Redistribute NPCs when the time block changes."""
        
        # Build balanced allocation map
        permitted_rooms = [
            "c_parking", "c_fountain", "c_gardens", "c_tennis",
            "f1_infirmary", "f1_auditorium", "f1_main_hall", "f1_reception", "f1_library", "f1_cafeteria", "f1_counselor",
            "f2_art_room", "f2_music_room", "f2_science_lab", "f2_corridor", "f2_classrooms", "f2_conference", "f2_admin",
            "rt_terrace", "rt_benches",
            "ci_court", "ci_hall"
        ]
        if day_number < 2:
            permitted_rooms.append("f1_computer_lab")
            
        large_rooms = [
            "f1_main_hall", "f1_cafeteria", "c_gardens", "c_fountain", "f2_corridor"
        ]
        
        managed_npcs = [npc_manager.npcs.get(nid) for nid in self._managed_npc_ids if npc_manager.npcs.get(nid)]
        # Use a stable random seed based on day number to ensure consistency throughout the day but variety between days
        rnd = random.Random(day_number * 1000 + 42)
        rnd.shuffle(managed_npcs)
        
        males = [n for n in managed_npcs if getattr(n, "gender", "") == "male"]
        females = [n for n in managed_npcs if getattr(n, "gender", "") == "female"]
        
        allocated_ids = set()
        self._allocation_map = {}
        
        # 1. Allocate bathrooms (exactly 4 of each gender)
        for n in males[:4]:
            self._allocation_map[n.id] = "f1_men_bath"
            allocated_ids.add(n.id)
        for n in females[:4]:
            self._allocation_map[n.id] = "f1_women_bath"
            allocated_ids.add(n.id)
            
        # 2. Filter remaining NPCs
        remaining_npcs = [n for n in managed_npcs if n.id not in allocated_ids]
        
        # 3. Base allocation: exactly 3 NPCs in each permitted room
        for room_id in permitted_rooms:
            for _ in range(3):
                if remaining_npcs:
                    n = remaining_npcs.pop()
                    self._allocation_map[n.id] = room_id
                    allocated_ids.add(n.id)
                    
        # 4. Secondary allocation: add a 4th NPC to each permitted room
        for room_id in permitted_rooms:
            if remaining_npcs:
                n = remaining_npcs.pop()
                self._allocation_map[n.id] = room_id
                allocated_ids.add(n.id)
                
        # 5. Overflow allocation: larger rooms get extra NPCs to look more populated
        while remaining_npcs:
            for room_id in large_rooms:
                if remaining_npcs:
                    n = remaining_npcs.pop()
                    self._allocation_map[n.id] = room_id
                    allocated_ids.add(n.id)
                    
        # Proceed with moving all NPCs to their balanced targets
        count = 0
        for npc_id in self._managed_npc_ids:
            npc = npc_manager.npcs.get(npc_id)
            if not npc:
                continue
            if getattr(npc, "_in_detention", False):
                continue

            target_room = self._pick_target_room(npc, block_name, primary_ratio)
            if not target_room:
                continue

            self._move_npc_to_room(npc, target_room, school_map, player_floor,
                                   delay=count * 0.15 + random.uniform(0, 3),
                                   is_visible=is_visible)
            count += 1

    def _pick_target_room(self, npc, block_name: str,
                          primary_ratio: float) -> str | None:
        """Choose a target room for an NPC based on the time block."""
        return self._allocation_map.get(npc.id, "f1_main_hall")

    # ──────────────────────────────────────────────────────────
    #  HYBRID MOVEMENT
    # ──────────────────────────────────────────────────────────

    def _move_npc_to_room(self, npc, target_room_id: str,
                          school_map: SchoolMap, player_floor: int,
                          delay: float = 0.0, is_visible=None) -> None:
        """Move an NPC to a room — physically if visible on camera, teleport otherwise.
        
        Args:
            is_visible: Optional callback(npc) -> bool. Uses camera viewport
                to determine visibility instead of just floor comparison.
        """
        target_floor = ROOM_FLOOR_MAP.get(target_room_id)
        if target_floor is None:
            return

        floor_obj = school_map.get_floor(target_floor)
        if not floor_obj:
            return

        room = floor_obj.rooms.get(target_room_id)
        if not room:
            return

        # Calculate a safe random position inside the target room
        final_x, final_y = get_safe_spawn_point(room.rect, floor_obj.walls, npc.rect.copy())


        npc.bound_rect = None
        npc.ai_enabled = True
        npc.stop_at_target = False
        npc.start_delay = delay

        # Determine if NPC is visible: use callback if available, fallback to floor check
        npc_is_visible = is_visible(npc) if is_visible else (npc.current_floor == player_floor)

        if npc_is_visible:
            # ── PHYSICAL MOVEMENT: player can see this NPC ──
            if target_floor == npc.current_floor:
                # Same floor: just walk to the room
                npc.target_pos = (final_x, final_y)
                npc.target_queue = []
            else:
                # Need to cross floors: user requested NO NPCs in stairs.
                # So we just teleport them immediately instead of walking to the stairs and bunching up.
                self._teleport_npc(npc, target_floor, final_x, final_y)
                return
        else:
            # ── TELEPORT: player cannot see this NPC ──
            self._teleport_npc(npc, target_floor, final_x, final_y)

    def _teleport_npc(self, npc, floor_id: int, x: int, y: int) -> None:
        """Instantly move an NPC to a position on a different floor."""
        npc.current_floor = floor_id
        npc.rect.centerx = x
        npc.rect.centery = y
        npc.target_pos = None
        npc.target_queue = []
        npc.ai_enabled = True
        npc.stop_at_target = False

    # ──────────────────────────────────────────────────────────
    #  DETENTION SYSTEM
    # ──────────────────────────────────────────────────────────

    def _trigger_detention(self, npc_manager: NPCManager,
                           school_map: SchoolMap, player_floor: int,
                           is_visible=None) -> None:
        """Between 10:00-12:00, send 2-4 random NPCs to the counselor's office."""
        self._detention_active = True
        candidates = [
            npc_id for npc_id in self._managed_npc_ids
            if not getattr(npc_manager.npcs.get(npc_id), "_in_detention", False)
        ]
        count = random.randint(*self.DETENTION_COUNT)
        chosen_ids = random.sample(candidates, min(count, len(candidates)))

        for npc_id in chosen_ids:
            npc = npc_manager.npcs.get(npc_id)
            if not npc:
                continue
            npc._in_detention = True
            self._detention_npcs.append(npc_id)
            self._move_npc_to_room(npc, self.DETENTION_ROOM, school_map,
                                   player_floor, delay=random.uniform(0, 2),
                                   is_visible=is_visible)

    def _release_detention(self, npc_manager: NPCManager,
                           school_map: SchoolMap, player_floor: int,
                           is_visible=None) -> None:
        """Release all detained NPCs back to their subgroup zones."""
        self._detention_active = False
        for npc_id in self._detention_npcs:
            npc = npc_manager.npcs.get(npc_id)
            if not npc:
                continue
            npc._in_detention = False
            # Send back to a preferred zone
            subgroup = getattr(npc, "subgroup", "")
            preferred = self.SUBGROUP_ZONES.get(subgroup, self.TRANSIT_ZONES)
            target = random.choice(preferred)
            self._move_npc_to_room(npc, target, school_map, player_floor,
                                   delay=random.uniform(0, 3),
                                   is_visible=is_visible)
        self._detention_npcs.clear()

    # ──────────────────────────────────────────────────────────
    #  DAY RESET
    # ──────────────────────────────────────────────────────────

    def reset_day(self) -> None:
        """Reset state for a new school day."""
        self._current_block = ""
        self._room_counts.clear()
        self._detention_active = False
        self._detention_npcs.clear()
