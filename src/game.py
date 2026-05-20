"""
src/game.py  —  Core game loop & state manager
================================================
The ``Game`` class owns every subsystem (map, player, NPCs, combat,
hacking, dialogue, missions, UI, network…) and drives the main
loop:  **events → update → draw**.

A state machine (``GameState`` enum) determines which subsystem
receives input and which draw calls are active.
"""

from __future__ import annotations

import random
import math
import os
import pygame
from collections import deque

from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS,
    BLACK, WHITE,
    FLOOR_1F, FLOOR_2F, FLOOR_CAMPUS, FLOOR_BASEMENT, FLOOR_ROOFTOP, FLOOR_SIZES, ZONE_TO_FLOOR,
    PLAYER_SIZE, NPC_INTERACTION_RANGE, ATTACK_RANGE, NPC_SPEED,
    GameState, Character, DayPhase, ItemCategory, Ending, SocialGroup, Direction, MissionStatus,
    NOTIF_SUCCESS, NOTIF_WARNING, NOTIF_ERROR, NOTIF_INFO,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
    KEY_INTERACT, KEY_USE, KEY_INVENTORY, KEY_SKILL_TREE,
    KEY_HELP, KEY_PAUSE, KEY_MAP,
    KEY_LIGHT_ATTACK, KEY_HEAVY_ATTACK, KEY_BLOCK, KEY_DASH, KEY_DASH_ALT, KEY_DASH_ALT2,
    KEY_HACK, KEY_PHONE,
    MOTIVATIONAL_MESSAGES, VT323_PATH)
from src.phone      import Phone
from src.map        import SchoolMap
from src.player     import Aiden, Lena
from src.npc        import NPCManager, NPC, is_generic_wanderer
from src.camera     import Camera
from src.inventory  import Inventory
from src.mission    import MissionManager, EventQueue
from src.reputation import ReputationSystem
from src.combat     import CombatSystem
from src.hack       import HackingMinigame
from src.trade      import TradeSystem
from src.dialogue   import DialogueSystem
from src.ui         import UI
from src.world_map  import WorldMap
from src.pingpong   import PingPongGame
from src.basketball import BasketballGame
from src.social_reputation import ReputationManager
from src.social_dialogue import SocialDialogueManager
from src.social_ui import SocialInteractionUI
from src.rooftop_party import RooftopParty
from src.controller import get_controller, init_controller, update_controller, XBOX_A
from src.schedule_manager import ScheduleManager

FLOOR_COLISEUM_INTERIOR = 5
FLOOR_PINGPONG_INTERIOR = 6





class Game:
    """Central game controller.

    Parameters
    ----------
    screen      : pygame display surface
    character   : which character the local player controls
    multiplayer : co-op mode enabled?
    is_host     : True → server (Aiden), False → client (Lena)
    """

    @property
    def minutes(self) -> float:
        """Return the current time of day in total minutes."""
        return self.time_of_day_minutes

    def __init__(self, screen: pygame.Surface, *,
                 character: Character = Character.AIDEN,
                 multiplayer: bool = False,
                 is_host: bool = True,
                 network_instance = None):
        self.screen      = screen
        self.clock       = pygame.time.Clock()
        self.character   = character
        self.multiplayer = multiplayer
        self.is_host     = is_host
        self.network     = network_instance

        # Seed randomness for co-op sync
        if self.multiplayer and self.network and hasattr(self.network, 'seed'):
            import random
            random.seed(self.network.seed)
            print(f"[Game] Seeding randomness with {self.network.seed}")

        self.running        = True
        self.state          = GameState.INTRO_CINEMATIC
        self.previous_state = GameState.INTRO_CINEMATIC
        self.active_wallet_item = None
        self.wallet_focus_item = None
        self.selected_yearbook_group = "Athletes"
        self.yearbook_scroll_offset = 0
        self.pause_sel      = 0

        # Transition cooldown (prevents rapid re-triggering)
        self._transition_cooldown: float = 0.0
        self._current_main_mission_text: str = "Mission 1: Follow Noah Carter through the school."
        self._bathroom_block_timer: float = 0.0
        self._bathroom_blocked_room: str | None = None
        self._cafeteria_block_timer: float = 0.0
        self._library_block_timer: float = 0.0
        self._pending_pingpong_result: str | None = None
        self._day1_story_complete: bool = False
        self._remote_day1_story_complete: bool = False
        self._remote_day2_story_complete: bool = False
        self._remote_day3_story_complete: bool = False
        self._oscar_win_dialogue_active: bool = False
        self._oscar_win_dialogue_index: int = 0
        self._oscar_win_dialogue_completed: bool = False
        self._oscar_win_dialogue_lines: list[tuple[str, str]] = []
        self._marcus_win_dialogue_active: bool = False
        self._marcus_win_dialogue_index: int = 0
        self._marcus_win_dialogue_completed: bool = False
        self._marcus_win_dialogue_lines: list[tuple[str, str]] = []
        self._net_sync_accum: float = 0.0
        self._net_force_sync: bool = True
        self._last_remote_data: dict | None = None
        self._net_last_mission_sig = None
        self._net_last_npc_sig = None
        self._net_mission_refresh_timer: float = 0.0
        self._net_npc_refresh_timer: float = 0.0
        self._net_mission_refresh_interval: float = 0.75
        self._net_npc_refresh_interval: float = 0.20
        self._normal_gameplay_music_playing: bool = False
        self._rooftop_party_music_playing: bool = False
        self._basement_mission_music_playing: bool = False

        # ── Day 4: Rooftop party scene state ──
        self._day4_npcs_placed: bool = False              # Ava/Marcus/Noah on rooftop
        self._ava_rooftop_dialogue_active: bool = False   # Talking to Ava at party
        self._ava_rooftop_dialogue_index: int = 0
        self._ava_rooftop_dialogue_lines: list[tuple[str, str]] = []
        self._ava_rooftop_dialogue_completed: bool = False
        # Cinematic: Marcus & Noah walk to stairs
        self._party_exit_cinematic_active: bool = False
        self._party_exit_phase: str = ""    # "pan_to_npcs" | "npcs_walking" | "pan_back" | "done"
        self._party_exit_timer: float = 0.0
        self._party_exit_cam_target: tuple = (0, 0)
        self._party_exit_cam_origin: tuple = (0, 0)
        # Phone spy mechanic (Mission 12)
        self._ava_phone_on_chair: bool = False            # Phone visible on chair
        self._ava_phone_chair_pos: tuple = (1520, 770)    # World pos of the chair (east chair)
        self._ava_phone_prompt_active: bool = False       # "Press ENTER to check phone"
        self._ava_phone_spying: bool = False              # Player is viewing Ava's phone
        self._ava_phone_timer: float = 15.0              # Countdown timer
        self._ava_phone_timer_active: bool = False        # Countdown running
        self._ava_phone_completed: bool = False           # Mission 12 done
        self._ava_phone_found_chat: bool = False          # Group chat discovered
        # Coop: Lena talks to NPCs to add time
        self._coop_time_bonus_npcs: set = set()           # NPCs Lena has talked to
        # Post-phone narrative
        self._post_phone_active: bool = False
        self._post_phone_lines: list = []
        self._post_phone_index: int = 0
        self._player_bad_feeling_shown: bool = False      # "bad feeling" monologue shown
        # Day 4 finale: Smile Club reveal, contained fight, and office resolution
        self._final_smile_ids: tuple[str, str, str] = (
            "npc_ava_thompson", "npc_marcus_green", "npc_noah_carter"
        )
        self._final_smile_room_ready: bool = False
        self._final_reveal_started: bool = False
        self._final_reveal_finished: bool = False
        self._final_reveal_active: bool = False
        self._final_reveal_phase: str = "pan"
        self._final_reveal_timer: float = 0.0
        self._final_reveal_index: int = 0
        self._final_reveal_lines: list[tuple[str, str]] = []
        self._final_office_active: bool = False
        self._final_office_index: int = 0
        self._final_office_lines: list[tuple[str, str]] = []
        self._final_office_started: bool = False
        self._final_real_names: dict[str, str] = {}

        # Day-cycle
        self.day_number     = 1
        self.event_queue    = EventQueue()
        self.day_timer: float = 0.0
        self.current_phase  = DayPhase.ARRIVAL
        self.phase_duration: float = 0.0

        # In-game clock (starts at 07:00 AM)
        self.time_of_day_minutes: float = 7 * 60
        self._time_scale: float = 1.2   # minutes advanced per real-time second (was 2.0)
        self._last_time_minutes: float = self.time_of_day_minutes

        # Schedule state (cafeteria timing for non-classroom NPCs)
        self._caf_seat_pool: list = []
        self._school_day_ended: bool = False  # True once 4 PM hits — clock freezes

        # ── Intro cinematic state ──
        self._cine_phase: str = "car"       # car | exit | dialogue | mission | guide
        self._cine_timer: float = 0.0
        self._car_x: float = float(SCREEN_WIDTH + 200)
        self._car_target_x: float = float(SCREEN_WIDTH // 2 - 100)
        self._car_y: float = float(SCREEN_HEIGHT // 2 + 157)  # Aligned with Main Road (y=2925) when camera centers on Roundabout
        self._car_speed: float = 400.0      # px / sec
        self._cine_dlg_lines: list[str] = [
            "Hey\u2026 you're new, right? Ravenside can be\u2026 a lot at first. Just\u2014 don't trust every smile you see here.",
            "And don't look at everyone like that. You don't know who they are.. Anyway, I'm glad you showed up. You might need someone on your side.",
            "Anyway\u2014 I'm Noah. Noah Carter.",
            "You're probably trying to find the main classroom, right?",
            "Everyone gets lost on day one. I'll meet you there.",
        ]
        self._cine_dlg_index: int = 0
        self._cine_show_mission: bool = False
        self._cine_mission_timer: float = 0.0
        self._noah_guide_active: bool = False
        self._noah_route: list = []   # waypoints for Noah
        self._noah_route_idx: int = 0
        self._noah_wait_for_player: bool = False
        self._cinematic_stairs_unlocked: bool = False  # allow seamless stairs after Noah switches floor
        self._noah_final_dialogue: bool = False
        self._exit_car_timer: float = 0.0
        self._exit_car_player_y: float = 0.0
        self._noah_final_dlg_lines: list[str] = [
            "Here we are \u2014 the 2nd Floor corridor.",
            "Classrooms, labs, and the Director's office are all up here.",
            "Good luck\u2026 and don't be afraid to explore.",
        ]
        self._noah_final_dlg_index: int = 0
        self._player_spawned: bool = False
        self._hud_focus: str | None = None  # "ff" | "wallet" | None
        self._ff_controller_active: bool = False
        self._cine_skip_focused: bool = False  # controller focus on skip button
        self.pause_options: list[str] = ["Resume", "Select Mission", "Change Character", "Main Menu", "Quit"]
        self.mission_select_sel: int = 0
        self.mission_select_confirm: bool = False
        self.mission_confirm_sel: int = 0
        self.return_to_menu: bool = False

        # ── Day transition screen ──
        self._day_transition_active: bool = False
        self._day_transition_timer: float = 0.0
        self._day_transition_target_day: int = 2
        self._pingpong_unlocked: bool = False
        self._library_unlocked: bool = False

        # ── Parked car (parking lot) ──
        self._parked_car_rect = pygame.Rect(900, 2400, 300, 105)
        self._extra_parked_cars = [
            (pygame.Rect(350, 2600, 200, 90), 'ME_Singles_Vehicles_32x32_Car_Left_4.png', 180),    # Red, faces LEFT
            (pygame.Rect(700, 2100, 200, 90), 'ME_Singles_Vehicles_32x32_Car_Right_1.png', 0),     # Blue, faces RIGHT
            (pygame.Rect(600, 2750, 200, 90), 'ME_Singles_Vehicles_32x32_Car_Left_2.png', 180),    # Green, faces LEFT
            (pygame.Rect(350, 2150, 200, 90), 'ME_Singles_Vehicles_32x32_Car_Right_6.png', 0),     # Silver/Grey, faces RIGHT
            (pygame.Rect(1000, 2600, 200, 90), 'ME_Singles_Vehicles_32x32_Car_Left_5.png', 180),   # Black, faces LEFT
        ]
        self._car_panel_active: bool = False  # "End day?" confirmation panel
        self._car_panel_input_delay: float = 0.0  # delay before accepting input
        self._car_panel_cooldown: float = 0.0     # cooldown before re-triggering
        self._entry_prompt_target: dict | None = None
        self._entry_prompt_cooldown: float = 0.0

        # ── Car departure cinematic ──
        self._car_departure_active: bool = False
        self._car_depart_phase: str = ""      # "walk_to_car" | "drive_away"
        self._car_depart_x: float = 0.0
        self._car_depart_timer: float = 0.0

        # ── init subsystems (order matters) ──
        self._init_map()
        self._init_players()
        self._init_npcs()
        self._init_systems()
        self._init_ui()
        self._init_controller()

        # Network (optional)
        if self.multiplayer and not self.network:
            self._init_network()

        # Kick off the first school day
        self.event_queue.load_day_schedule()
        self._advance_phase()

        # Auto-activate available missions
        for m in self.mission_manager.get_available():
            self.mission_manager.activate_mission(m.id)

    # ──────────────────────────────────────────────────────────
    #  INITIALISATION HELPERS
    # ──────────────────────────────────────────────────────────

    def _get_parked_vehicle_rects(self) -> list[pygame.Rect]:
        """Collision boxes for every visible vehicle in the campus parking lot."""
        rects = [self._parked_car_rect]
        rects.extend(rect for rect, _, _ in self._extra_parked_cars)
        return rects

    def _play_button_sound(self):
        if not pygame.mixer.get_init():
            return
        if not hasattr(self, "_button_sound"):
            try:
                self._button_sound = pygame.mixer.Sound("assets/sounds/sonido_boton.mp3")
                self._button_sound.set_volume(0.25)
            except Exception:
                self._button_sound = None
        if self._button_sound:
            self._button_sound.play()

    def _init_map(self):
        self.school_map    = SchoolMap()
        self.current_floor = FLOOR_CAMPUS
        floor = self.school_map.get_floor(self.current_floor)
        self._floor_w = floor.width  if floor else 4000
        self._floor_h = floor.height if floor else 3000

    def _init_players(self):
        # Hide player off-screen for intro cinematic; spawned after car arrives
        cx, cy = -200, -200
        self.remote_player = None

        self.aiden = Aiden(cx, cy)
        self.lena = Lena(cx, cy)

        if self.character == Character.AIDEN:
            self.player = self.aiden
            if self.multiplayer:
                self.remote_player = self.lena
        else:
            self.player = self.lena
            if self.multiplayer:
                self.remote_player = self.aiden

        self.inventory = Inventory()
        # Starting items
        self.inventory.add_item(
            "Lunch Money", ItemCategory.MONEY,
            "Some cash for the cafeteria", quantity=5,
        )
        self.inventory.add_item(
            "Student ID", ItemCategory.SPECIAL,
            "Your Ravenside High student ID",
        )

    def _init_npcs(self):
        self.npc_manager = NPCManager()
        self.npc_manager.load_npcs_from_json()
        from settings import SocialGroup, NPC_SIZE

        # Initialize the sibling as an NPC
        sched = {"arrival": 0, "class_1": 4, "break_1": 4, "lunch": 3, "activities": 4, "departure": 0, "night": 4}
        if self.character == Character.AIDEN:
            self.sibling_npc = NPC("npc_lena", "Lena Parker", SocialGroup.TECH_CLUB, "Hacker", "Sister", sched, {}, "female")
        else:
            self.sibling_npc = NPC("npc_aiden", "Aiden Parker", SocialGroup.ATHLETES, "Athlete", "Brother", sched, {}, "male")
        
        self.sibling_npc.ai_enabled = True
        self.npc_manager.npcs[self.sibling_npc.id] = self.sibling_npc
        self.npc_manager.relationships.add_node(self.sibling_npc.id)
        
        # Position Marcus Green at the basketball court (Coliseum interior)
        marcus = self.npc_manager.get_npc_by_id("npc_marcus_green")
        if marcus:
            marcus.current_floor = FLOOR_COLISEUM_INTERIOR
            marcus.ai_enabled = False
            marcus.ignore_schedule = True
            marcus.rect.centerx = 650
            marcus.rect.centery = 500
            marcus.show_name = True

        # Position Oscar and observers inside the Ping Pong interior floor
        oscar = self.npc_manager.get_npc_by_id("npc_oscar")
        if oscar:
            oscar.current_floor = FLOOR_PINGPONG_INTERIOR
            oscar.ai_enabled = True
            oscar.bound_rect = pygame.Rect(40, 40, 1300 - 80 - NPC_SIZE, 1000 - 80 - NPC_SIZE)
            # Place Oscar near the centre of the court
            oscar.rect.centerx = 650
            oscar.rect.centery = 430
            # gather observers and arrange them in a circle around Oscar
            obs_ids = [
                "npc_oscar_obs1",
                "npc_oscar_obs2",
                "npc_oscar_obs3",
                "npc_oscar_obs4",
            ]
            radius = 210
            for i, oid in enumerate(obs_ids):
                obs = self.npc_manager.get_npc_by_id(oid)
                if not obs:
                    continue
                obs.current_floor = FLOOR_PINGPONG_INTERIOR
                obs.ai_enabled = True
                obs.bound_rect = pygame.Rect(40, 40, 1300 - 80 - NPC_SIZE, 1000 - 80 - NPC_SIZE)
                obs.name = "Club Member"
                obs.show_name = True
                angle = (i / len(obs_ids)) * (2 * math.pi)
                obs.rect.centerx = oscar.rect.centerx + int(math.cos(angle) * radius)
                obs.rect.centery = oscar.rect.centery + int(math.sin(angle) * radius)

        # ── El Gastroo (The Chef) ──
        self._place_ava_for_story()
        f1 = self.school_map.get_floor(FLOOR_1F)
        caf = f1.rooms.get("f1_cafeteria")
        if caf:
            gordon = NPC(
                "npc_gordon", "El Gastroo", 
                SocialGroup.FACULTY, "Chef", "El Gastroo is shouting about undercooked lamb.",
                gender="male"
            )
            gordon.current_floor = FLOOR_1F
            from settings import NPC_SIZE
            # Place Gordon at the bottom-right corner of the cafeteria
            gordon.rect.x = caf.rect.right  - NPC_SIZE - 40
            gordon.rect.y = caf.rect.bottom - NPC_SIZE - 40
            # Gordon walks around the entire cafeteria area (not just a small corner)
            gordon.bound_rect = caf.rect.inflate(-60, -60)
            gordon.ignore_schedule = True  # He belongs in the kitchen
            gordon.ai_enabled = True  # Enable AI so he can walk around
            self.npc_manager.npcs[gordon.id] = gordon
            self.npc_manager.relationships.add_node(gordon.id)

        # Ensure fixed story NPC placement
        self._initialize_director_office()
        self._place_axel_knight()

        # ── Position Noah Carter in the Entrance for the intro cinematic ──
        noah_carter = self.npc_manager.get_npc_by_id("npc_noah_carter")
        if noah_carter:
            noah_carter.current_floor = FLOOR_CAMPUS
            noah_carter.rect.center = (2000, 2650)
            noah_carter.ai_enabled = False
            noah_carter.ignore_schedule = True
            noah_carter.show_name = True

        # ── Push random NPCs out of staircase rooms during cinematic ──
        stair_ids = {"f1_stairs_2f", "f1_basement_stairs", "f2_stairs_1f", "f2_roof_stairs", "b_stairs_up", "rt_stairs_down"}
        for npc in self.npc_manager.npcs.values():
            if is_generic_wanderer(npc.id):
                fl = self.school_map.get_floor(npc.current_floor)
                if fl:
                    room = fl.get_room_at(npc.rect.centerx, npc.rect.centery)
                    if room and room.id in stair_ids:
                        # Move to centre of the floor's main corridor
                        npc.rect.center = (1600, 1000) if npc.current_floor != 4 else (1600, 500)

        # Ensure Noah's spawn area is clear
        self._clear_noah_area(radius=160)

        # ── Initialize Schedule Manager for NPC routines ──
        self.schedule_manager = ScheduleManager()
        self.schedule_manager.assign_subgroups(self.npc_manager)

    def _init_systems(self):
        self.reputation      = ReputationSystem()
        self.mission_manager = MissionManager()
        self.mission_manager.multiplayer = self.multiplayer
        self.mission_manager.is_host = self.is_host
        self.mission_manager.load_missions_from_json()
        self.combat_system   = CombatSystem()
        self.hacking_game    = HackingMinigame()
        self.trade_system    = TradeSystem()
        self.dialogue_system = DialogueSystem()
        self.dialogue_system.game = self
        self.dialogue_system.load_dialogues_from_json()
        
        # Coop sync dialogue / cinematic / events voting flags
        self.dialogue_continue_voted = False
        self.cinematic_continue_voted = False
        self.cinematic_skip_voted = False
        self._pending_dialogue_request = None
        self.remote_dialogue_continue = False
        self.remote_cinematic_continue = False
        self.remote_cinematic_skip = False
        self.car_departure_voted = False
        self.remote_car_departure_voted = False
        self._host_viewed_oscar_post = False
        self._client_viewed_oscar_post = False
        self._remote_client_viewed_oscar_post = False
        self.camera = Camera(self._floor_w, self._floor_h)
        # Snap camera to entrance for intro cinematic to prevent lerp-from-zero spawn bugs
        target_x = 2000 - SCREEN_WIDTH // 2
        target_y = 2700 - SCREEN_HEIGHT // 2
        self.camera.offset.x = max(0, min(target_x, self.camera.map_width - SCREEN_WIDTH))
        self.camera.offset.y = max(0, min(target_y, self.camera.map_height - SCREEN_HEIGHT))
        # Ping-pong minigame
        self.pingpong = PingPongGame()
        # Basketball minigame
        self.basketball = BasketballGame()
        # Ping Pong multiplayer state
        self._pingpong_match_won = False
        self._remote_pingpong_match_won = False
        self._spectating_pingpong = False
        self._pingpong_exit_voted = False
        self._remote_pingpong_exit_voted = False
        self._pending_pp_cheer = False
        
        # Rooftop Party (Day 3 event)
        self.rooftop_party = RooftopParty(self.screen)
        
        # ── NEW SOCIAL SYSTEMS ────────────────────────────────
        self.social_reputation_manager = ReputationManager()
        self.social_reputation_manager.set_reputation_system(self.reputation)
        self.social_reputation_manager.game = self
        
        self.social_dialogue_manager = SocialDialogueManager()
        self.social_dialogue_manager.reputation_manager = self.social_reputation_manager
        
        self.social_ui = SocialInteractionUI()
        self.social_dialogue_manager.social_ui = self.social_ui
        # ──────────────────────────────────────────────────────
        
        from settings import Character
        self.aiden_phone = Phone(self.screen, time_source=lambda: self.time_of_day_minutes, player_name="aiden")
        self.lena_phone = Phone(self.screen, time_source=lambda: self.time_of_day_minutes, player_name="lena")
        
        self.phone = self.aiden_phone if self.character == Character.AIDEN else self.lena_phone

    def _initialize_director_office(self):
        director = self.npc_manager.get_npc_by_id("npc_director")
        floor2 = self.school_map.get_floor(FLOOR_2F)
        if not director or not floor2:
            return
        office = floor2.rooms.get("f2_director")
        if not office:
            return
        director.current_floor = FLOOR_2F
        director.ai_enabled = True
        director.ignore_schedule = True
        director.bound_rect = office.rect.inflate(-120, -120)
        director.rect.center = office.rect.center

    def _place_axel_knight(self):
        axel = self.npc_manager.get_npc_by_id("npc_axel_knight")
        if not axel:
            return
        axel.current_floor = FLOOR_2F
        axel.ai_enabled = False
        axel.ignore_schedule = True
        axel.show_name = True
        from settings import Direction
        axel.direction = Direction.RIGHT
        axel.rect.center = (1058, 224)  # Literally in the entrance of the stairs

    def _is_npc_on_camera(self, npc) -> bool:
        """Return True if the NPC is on the same floor as the player AND within the camera viewport.
        This is used to prevent teleporting visible NPCs."""
        if npc.current_floor != self.current_floor:
            return False
        # Calculate screen-space position of the NPC
        cam = self.camera
        margin = 64  # extra margin so NPCs don't pop in/out at edges
        screen_x = npc.rect.centerx - cam.offset.x
        screen_y = npc.rect.centery - cam.offset.y
        return (-margin <= screen_x <= cam.view_w + margin and
                -margin <= screen_y <= cam.view_h + margin)

    def _register_npc(self, npc: NPC):
        self.npc_manager.npcs[npc.id] = npc
        self.npc_manager.relationships.add_node(npc.id)

    def _place_ava_for_story(self):
        self._place_alan_chen_for_story()
        # On Day 4 Ava is on the Rooftop — don't override her position
        if self.day_number >= 4:
            return
        ava = self.npc_manager.get_npc_by_id("npc_ava_thompson")
        floor1 = self.school_map.get_floor(FLOOR_1F)
        if not ava or not floor1:
            return
        target_room_id = "f1_computer_lab" if self.day_number >= 2 else "f1_library"
        room = floor1.rooms.get(target_room_id) or floor1.rooms.get("f1_library")
        if not room:
            return
        ava.current_floor = FLOOR_1F
        ava.current_zone = 2 if target_room_id == "f1_computer_lab" else 4
        ava.ai_enabled = False
        ava.ignore_schedule = True
        ava.show_name = True
        ava.bound_rect = room.rect.inflate(-120, -120)
        ava.rect.center = (room.rect.centerx + 120, room.rect.centery + 40)
        if self.day_number >= 2 and target_room_id == "f1_computer_lab":
            ava.dialogue_ids = {"aiden": "dlg_ava_tech_lab", "lena": "dlg_ava_tech_lab"}
            self._clear_tech_lab_for_ava(room)
        else:
            ava.dialogue_ids = {"aiden": "dlg_ava_thompson", "lena": "dlg_ava_thompson"}

    def _place_alan_chen_for_story(self):
        alan = self.npc_manager.get_npc_by_id("npc_alan_chen")
        floor1 = self.school_map.get_floor(FLOOR_1F)
        if not alan or not floor1:
            return
        room = floor1.rooms.get("f1_men_bath")
        if not room:
            return
        alan.current_floor = FLOOR_1F
        alan.current_zone = 0
        alan.ai_enabled = False
        alan.ignore_schedule = True
        alan.show_name = True
        alan.rect.center = room.rect.center
        alan.dialogue_ids = {"aiden": "dlg_alan_chen", "lena": "dlg_alan_chen"}

    def _clear_tech_lab_for_ava(self, room):
        for npc in self.npc_manager.npcs.values():
            if npc.id in ("npc_ava_thompson", "npc_aiden", "npc_lena"):
                continue
            if npc.current_floor == FLOOR_1F and room.rect.collidepoint(npc.rect.centerx, npc.rect.centery):
                npc.rect.center = (1600, 1000)
                npc.current_zone = 1
                npc.target_pos = npc.rect.center
                npc.target_queue = []

    def _init_ui(self):
        self.ui = UI(self.screen)
        self.world_map = WorldMap(self.school_map)
        self.aiden_phone._map_ref = self.world_map
        self.lena_phone._map_ref = self.world_map

    def _enforce_sibling_safe_location(self):
        if not getattr(self, 'sibling_npc', None):
            return

        # Sibling character enum
        sib_char = Character.LENA if self.character == Character.AIDEN else Character.AIDEN

        from settings import FLOOR_ROOFTOP, FLOOR_BASEMENT, FLOOR_CAMPUS, FLOOR_1F, FLOOR_2F

        # 1. Check restricted floors
        relocate = False
        if self.sibling_npc.current_floor == FLOOR_PINGPONG_INTERIOR and not self._is_pingpong_unlocked():
            relocate = True
        elif self.sibling_npc.current_floor == FLOOR_ROOFTOP and not getattr(self, '_rooftop_unlocked', False):
            relocate = True
        elif self.sibling_npc.current_floor == FLOOR_BASEMENT and not self._is_basement_unlocked():
            relocate = True

        if relocate:
            # Move sibling to Floor 1F safe hallway
            self.sibling_npc.current_floor = FLOOR_1F
            self.sibling_npc.rect.center = (1080, 500)
            self.sibling_npc.target_pos = None
            self.sibling_npc.target_queue = []
            return

        # 2. Check restricted rooms on sibling's current floor
        floor = self.school_map.get_floor(self.sibling_npc.current_floor)
        if not floor:
            return

        room = floor.get_room_at(self.sibling_npc.rect.centerx, self.sibling_npc.rect.centery)
        if not room:
            return

        room_invalid = False
        if self.sibling_npc.current_floor == FLOOR_CAMPUS:
            if room.id == "c_tennis" and not self._is_pingpong_unlocked():
                room_invalid = True
            elif room.id in ("c_coliseum", "c_coliseum_court") and not self._is_coliseum_unlocked():
                room_invalid = True
            elif room.id in ("c_b_lab", "c_b_lib", "c_b_hall"):
                if room.id == "c_b_lab" and not self._is_tech_lab_unlocked(): room_invalid = True
                elif room.id == "c_b_lib" and not self._is_library_mission_unlocked(): room_invalid = True
        elif self.sibling_npc.current_floor == FLOOR_1F:
            if room.id == "f1_cafeteria" and not self._is_cafeteria_open():
                room_invalid = True
            elif room.id == "f1_computer_lab" and not self._is_tech_lab_unlocked():
                room_invalid = True
            elif room.id == "f1_library" and not self._is_library_mission_unlocked():
                room_invalid = True
            else:
                allowed_bath, _ = self._is_bathroom_access_allowed(room.id, sib_char)
                if not allowed_bath:
                    room_invalid = True

        if room_invalid:
            # Teleport sibling to safe corridor/spawn on that floor
            if self.sibling_npc.current_floor == FLOOR_CAMPUS:
                self.sibling_npc.rect.center = (2000, 2500)
            elif self.sibling_npc.current_floor == FLOOR_1F:
                self.sibling_npc.rect.center = (1080, 500)
            elif self.sibling_npc.current_floor == FLOOR_2F:
                self.sibling_npc.rect.center = (1080, 500)
            self.sibling_npc.target_pos = None
            self.sibling_npc.target_queue = []

    def _swap_character(self):
        if self.multiplayer:
            self.ui.show_notification("Cannot change character: Roles are already established in co-op mode.", NOTIF_ERROR)
            return

        self._enforce_sibling_safe_location()

        from settings import SocialGroup
        old_floor = self.current_floor
        old_x, old_y = self.player.rect.center

        # Swap character enum
        new_char = Character.LENA if self.character == Character.AIDEN else Character.AIDEN
        self.character = new_char

        # Get the new player instance
        self.player = self.aiden if new_char == Character.AIDEN else self.lena

        # New player takes position of sibling_npc
        new_floor = self.sibling_npc.current_floor
        new_x, new_y = self.sibling_npc.rect.center
        self.current_floor = new_floor
        self.player.current_floor = new_floor
        self.player.rect.center = (new_x, new_y)

        # Update sibling_npc to represent the previous character
        if new_char == Character.AIDEN:
            # Sibling is now Lena
            self.sibling_npc.id = "npc_lena"
            self.sibling_npc.name = "Lena Parker"
            self.sibling_npc.group = SocialGroup.TECH_CLUB
            self.sibling_npc.public_personality = "Hacker"
            self.sibling_npc.private_personality = "Sister"
            self.sibling_npc.gender = "female"
            self.phone = self.aiden_phone
        else:
            # Sibling is now Aiden
            self.sibling_npc.id = "npc_aiden"
            self.sibling_npc.name = "Aiden Parker"
            self.sibling_npc.group = SocialGroup.ATHLETES
            self.sibling_npc.public_personality = "Athlete"
            self.sibling_npc.private_personality = "Brother"
            self.sibling_npc.gender = "male"
            self.phone = self.lena_phone

        self.sibling_npc.current_floor = old_floor
        self.sibling_npc.rect.center = (old_x, old_y)
        self.sibling_npc.target_pos = None
        self.sibling_npc.target_queue = []
        self.sibling_npc._wander_timer = 3.0  # Give them a few seconds in this direction
        self.sibling_npc._wander_dx = 100.0 if old_x % 2 == 0 else -100.0  # Force instant movement
        self.sibling_npc._wander_dy = 0.0
        self.sibling_npc.start_delay = 0.0
        self.sibling_npc.ai_enabled = True
        self.sibling_npc.stop_at_target = False
        self.sibling_npc._load_sprites()
        
        # Ensure sibling NPC is registered in manager with new ID
        self.npc_manager.npcs = {k: v for k, v in self.npc_manager.npcs.items() if k not in ("npc_aiden", "npc_lena")}
        self.npc_manager.npcs[self.sibling_npc.id] = self.sibling_npc

        # Snap camera to the new player
        self.camera.offset.x = self.player.rect.centerx - SCREEN_WIDTH // 2
        self.camera.offset.y = self.player.rect.centery - SCREEN_HEIGHT // 2
        self.camera.offset.x = max(0, min(self.camera.offset.x, self.camera.map_width - SCREEN_WIDTH))
        self.camera.offset.y = max(0, min(self.camera.offset.y, self.camera.map_height - SCREEN_HEIGHT))

        self.ui.show_notification(f"Swapped to {self.character.value.title()}", NOTIF_INFO)
        self._last_known_level = self.player.level
        self.state = getattr(self, 'previous_state', GameState.PLAYING)


    def _init_controller(self):
        """Initialize controller input handling."""
        init_controller()
        self.controller = get_controller()

    def _init_network(self):
        try:
            if self.is_host:
                from network.server import GameServer
                self.network = GameServer()
                self.network.start()
            else:
                from network.client import GameClient
                self.network = GameClient()
                self.network.connect()
        except Exception as exc:
            print(f"[Network] Init failed: {exc}")
            self.multiplayer = False
            self.network     = None

    # ──────────────────────────────────────────────────────────
    #  MAIN LOOP
    # ──────────────────────────────────────────────────────────

    def run(self):
        """Block until the player quits."""
        self.running = True
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            update_controller(dt)  # Update controller input
            self._handle_controller_input()  # Process controller buttons
            self._handle_events()
            self._update(dt)
            self._draw()
        # Cleanup (if loop exited because running=False)
        if self.network:
            self.network.stop()
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                if getattr(self, '_fountain_sound', None):
                    self._fountain_sound.stop()
                if hasattr(self.player, 'stop_audio'):
                    self.player.stop_audio()
        except Exception:
            pass

    def _exit_mainframe_success(self):
        self.state = GameState.PLAYING
        if self.multiplayer and not self.is_host:
            self._net_mainframe_completed = True
            return
        m_obj = self.mission_manager.missions.get("mission_high_school_mainframe")
        if m_obj:
            m_obj.status = MissionStatus.COMPLETED
            for obj in m_obj.objectives:
                obj.completed = True
                obj.progress = obj.required
            self.mission_manager.completed_ids.add("mission_high_school_mainframe")
        self._complete_day2_story()

    def _handle_mainframe_event(self, event):
        if event.type == pygame.KEYDOWN:
            if self.mainframe_screen == "login":
                if event.key == pygame.K_TAB:
                    self.mainframe_active_field = "pass" if self.mainframe_active_field == "user" else "user"
                elif event.key == pygame.K_RETURN:
                    if self.mainframe_user_input == "admin_techlab" and self.mainframe_pass_input == "pWd_sMiLe_cLuB_99!":
                        self.mainframe_screen = "desktop"
                        self.mainframe_error = ""
                    else:
                        self.mainframe_error = "INVALID CREDENTIALS"
                elif event.key == pygame.K_BACKSPACE:
                    if self.mainframe_active_field == "user":
                        self.mainframe_user_input = self.mainframe_user_input[:-1]
                    else:
                        self.mainframe_pass_input = self.mainframe_pass_input[:-1]
                elif event.key == pygame.K_ESCAPE:
                    self.state = GameState.PLAYING
                else:
                    if len(event.unicode) > 0 and event.unicode.isprintable():
                        if self.mainframe_active_field == "user":
                            self.mainframe_user_input += event.unicode
                        else:
                            self.mainframe_pass_input += event.unicode
            elif self.mainframe_screen == "desktop":
                if event.key == pygame.K_ESCAPE:
                    self.mainframe_screen = "alarm"
            elif self.mainframe_screen == "mail":
                if event.key == pygame.K_ESCAPE:
                    self.mainframe_screen = "desktop"
            elif self.mainframe_screen == "mail_view":
                if event.key == pygame.K_ESCAPE:
                    self.mainframe_screen = "mail"
            elif self.mainframe_screen == "alarm":
                if event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE):
                    self._exit_mainframe_success()

        elif event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
            if self.mainframe_screen == "login":
                user_rect = pygame.Rect(cx - 150, cy - 40, 300, 40)
                pass_rect = pygame.Rect(cx - 150, cy + 40, 300, 40)
                login_btn = pygame.Rect(cx - 150, cy + 110, 140, 45)
                exit_btn  = pygame.Rect(cx + 10, cy + 110, 140, 45)
                autofill_btn = pygame.Rect(cx - 150, cy + 170, 300, 35)

                if user_rect.collidepoint(pos):
                    self.mainframe_active_field = "user"
                elif pass_rect.collidepoint(pos):
                    self.mainframe_active_field = "pass"
                elif login_btn.collidepoint(pos):
                    if self.mainframe_user_input == "admin_techlab" and self.mainframe_pass_input == "pWd_sMiLe_cLuB_99!":
                        self.mainframe_screen = "desktop"
                        self.mainframe_error = ""
                    else:
                        self.mainframe_error = "INVALID CREDENTIALS"
                elif exit_btn.collidepoint(pos):
                    self.state = GameState.PLAYING
                elif autofill_btn.collidepoint(pos):
                    self.mainframe_user_input = "admin_techlab"
                    self.mainframe_pass_input = "pWd_sMiLe_cLuB_99!"
                    self.mainframe_screen = "desktop"
                    self.mainframe_error = ""

            elif self.mainframe_screen == "desktop":
                mail_icon = pygame.Rect(cx - 240, cy - 150, 100, 100)
                disc_icon = pygame.Rect(cx + 180, cy - 150, 100, 100)

                if mail_icon.collidepoint(pos):
                    self.mainframe_screen = "mail"
                elif disc_icon.collidepoint(pos):
                    self.mainframe_screen = "alarm"

            elif self.mainframe_screen == "mail":
                back_btn = pygame.Rect(cx - 380, cy - 230, 80, 35)
                disc_btn = pygame.Rect(cx + 280, cy - 230, 100, 35)
                eli_item = pygame.Rect(cx - 180, cy - 60, 560, 50)
                if back_btn.collidepoint(pos):
                    self.mainframe_screen = "desktop"
                elif disc_btn.collidepoint(pos):
                    self.mainframe_screen = "alarm"
                elif eli_item.collidepoint(pos):
                    self.mainframe_screen = "mail_view"
                    self.mainframe_selected_email = "eli"

            elif self.mainframe_screen == "mail_view":
                back_btn = pygame.Rect(cx - 380, cy - 230, 80, 35)
                disc_btn = pygame.Rect(cx + 280, cy - 230, 100, 35)
                close_btn = pygame.Rect(cx - 100, cy + 180, 200, 45)
                if back_btn.collidepoint(pos) or close_btn.collidepoint(pos):
                    self.mainframe_screen = "mail"
                elif disc_btn.collidepoint(pos):
                    self.mainframe_screen = "alarm"

            elif self.mainframe_screen == "alarm":
                ack_btn = pygame.Rect(cx - 180, cy + 230, 360, 55)
                if ack_btn.collidepoint(pos):
                    self._exit_mainframe_success()

    # ──────────────────────────────────────────────────────────
    #  EVENT HANDLING
    # ──────────────────────────────────────────────────────────

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            
            # Switch input mode to keyboard on keypress or mouse click
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                if self.controller:
                    self.controller.last_input_method = "keyboard"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._play_button_sound()
            if getattr(self, "_oscar_win_dialogue_active", False):
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    self._advance_oscar_win_dialogue()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._advance_oscar_win_dialogue()
                continue
            if getattr(self, "_marcus_win_dialogue_active", False):
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    self._advance_marcus_win_dialogue()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._advance_marcus_win_dialogue()
                continue
            if getattr(self, "_ava_rooftop_dialogue_active", False):
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    self._advance_ava_rooftop_dialogue()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._advance_ava_rooftop_dialogue()
                continue
            if getattr(self, "_bad_feeling_active", False):
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    self._advance_bad_feeling()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._advance_bad_feeling()
                continue
            if getattr(self, "_post_phone_active", False):
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    self._advance_post_phone()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._advance_post_phone()
                continue
            if getattr(self, "_final_reveal_active", False):
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_e):
                    self._advance_final_reveal()
                elif event.type == pygame.MOUSEBUTTONDOWN and getattr(self, "_final_reveal_phase", "") == "dialogue":
                    self._advance_final_reveal()
                continue
            if getattr(self, "_final_office_active", False):
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_e):
                    self._advance_final_office_scene()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._advance_final_office_scene()
                continue
            if getattr(self, "_ava_phone_spying", False):
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if getattr(self, "_ava_phone_active_chat", None) is not None:
                            self._ava_phone_active_chat = None
                        else:
                            self._ava_phone_spying = False
                            self._ava_phone_timer_active = False
                            if getattr(self, "_ava_phone_completed", False):
                                self._show_post_phone_monologue()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    for rect, key in getattr(self, "_ava_phone_chat_rects", []):
                        if rect.collidepoint(event.pos):
                            self._ava_phone_active_chat = key
                            break
                continue
            if getattr(self, 'phone', None) and self.phone.is_visible:
                if self.phone.handle_input(event):
                    continue
            # MAP state delegates to WorldMap
            if self.state == GameState.MAP:
                close = self.world_map.handle_event(event)
                if close:
                    self.state = self.previous_state
                    if self.phone.is_visible:
                        self.phone.close()
                    did_request_teleport = getattr(self.world_map, 'teleport_requested', False)
                    if did_request_teleport:
                        self.world_map.teleport_requested = False
                        tfloor = self.world_map.teleport_floor
                        tx, ty = self.world_map.teleport_pos
                        if not self._try_teleport_to(tfloor, int(tx), int(ty)):
                            continue
                    self.world_map.reset_teleport_state()
                continue
            if self.state == GameState.MAINFRAME:
                self._handle_mainframe_event(event)
                continue
            if event.type == pygame.KEYDOWN:
                self._on_key_down(event)
            elif event.type == pygame.KEYUP:
                pass  # movement uses get_pressed()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Skip button in cinematic
                if self.state == GameState.INTRO_CINEMATIC:
                    skip_rect = getattr(self, '_skip_btn_rect', None)
                    if skip_rect and skip_rect.collidepoint(event.pos):
                        if self.multiplayer:
                            self.cinematic_skip_voted = True
                        else:
                            self._skip_cinematic()
                        continue
                    elif self._cine_phase in ("dialogue", "final_dialogue"):
                        if self.multiplayer:
                            self.cinematic_continue_voted = True
                        else:
                            self._advance_cinematic_dialogue()
                        continue
                if self.state == GameState.TRADING:
                    self.trade_system.handle_click(event.pos)
                elif self.state == GameState.BASKETBALL:
                    self.basketball.handle_input(event)
                elif self.state == GameState.PLAYING:
                    if getattr(self.ui, 'phone_icon_rect', None) and self.ui.phone_icon_rect.collidepoint(event.pos):
                        self.phone.toggle_phone()
                    elif self.ui.wallet_icon_rect.collidepoint(event.pos):
                        self.previous_state = self.state
                        self.state = GameState.WALLET
                        self.active_wallet_item = None
                        self.wallet_focus_item = None
                elif self.state == GameState.WALLET:
                    if self.active_wallet_item:
                        if self.active_wallet_item == "yearbook":
                            if event.button == 4: # Scroll Up
                                self.yearbook_scroll_offset = max(0, self.yearbook_scroll_offset - 1)
                                print(f"[Yearbook] Scroll UP. Offset: {self.yearbook_scroll_offset}")
                                return
                            elif event.button == 5: # Scroll Down
                                self.yearbook_scroll_offset += 1
                                print(f"[Yearbook] Scroll DOWN. Offset: {self.yearbook_scroll_offset}")
                                return

                            cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
                            main_panel = pygame.Rect(cx - 600, cy - 300, 1200, 600)
                            left_panel = pygame.Rect(main_panel.x + 20, main_panel.y + 80, 280, main_panel.height - 100)
                            if left_panel.collidepoint(event.pos):
                                y_click = event.pos[1]
                                start_y = left_panel.y + 45
                                clicked_idx = (y_click - start_y) // 40
                                if 0 <= clicked_idx < 6:
                                    groups = ["Athletes", "Tech Club", "Populars", "Academics", "Rebels", "Outsiders"]
                                    old_group = self.selected_yearbook_group
                                    self.selected_yearbook_group = groups[clicked_idx]
                                    if self.selected_yearbook_group != old_group:
                                        self.yearbook_scroll_offset = 0
                                    print(f"[Yearbook] Selected group: {self.selected_yearbook_group}")
                                return
                            elif main_panel.collidepoint(event.pos):
                                return
                        # Click anywhere else to go back to wallet view
                        self.active_wallet_item = None
                        self.wallet_focus_item = None
                    else:
                        if self.ui.wallet_id_rect.collidepoint(event.pos):
                            self.active_wallet_item = "id"
                            self.wallet_focus_item = "id"
                        elif self.ui.wallet_bill_rect.collidepoint(event.pos):
                            self.active_wallet_item = "bill"
                            self.wallet_focus_item = "bill"
                        elif self.ui.wallet_yearbook_rect.collidepoint(event.pos):
                            self.active_wallet_item = "yearbook"
                            self.wallet_focus_item = "yearbook"
                        elif getattr(self.ui, 'wallet_cred_rect', None) and self.ui.wallet_cred_rect.collidepoint(event.pos) and self.inventory.has_item("Hacked Credentials"):
                            self.active_wallet_item = "cred"
                            self.wallet_focus_item = "cred"
                        elif not self.ui.wallet_bg_rect.collidepoint(event.pos) and not self.ui.wallet_bill_rect.collidepoint(event.pos):
                            self.state = GameState.PLAYING
                            self.wallet_focus_item = None
            elif event.type == pygame.MOUSEBUTTONUP:
                if self.state == GameState.BASKETBALL:
                    self.basketball.handle_input(event)

    def _handle_controller_input(self):
        """Handle Xbox controller button input (called every frame)."""
        if not self.controller or not self.controller.connected:
            return

        controller = self.controller

        if getattr(self, "_oscar_win_dialogue_active", False):
            if controller.is_confirm_pressed() or controller.is_interact_pressed():
                self._advance_oscar_win_dialogue()
            return

        if getattr(self, "_ava_rooftop_dialogue_active", False):
            if controller.is_confirm_pressed() or controller.is_interact_pressed():
                self._advance_ava_rooftop_dialogue()
            return

        if getattr(self, "_bad_feeling_active", False):
            if controller.is_confirm_pressed() or controller.is_interact_pressed():
                self._advance_bad_feeling()
            return

        if getattr(self, "_post_phone_active", False):
            if controller.is_confirm_pressed() or controller.is_interact_pressed():
                self._advance_post_phone()
            return
        if getattr(self, "_final_reveal_active", False):
            if controller.is_confirm_pressed() or controller.is_interact_pressed():
                self._advance_final_reveal()
            return
        if getattr(self, "_final_office_active", False):
            if controller.is_confirm_pressed() or controller.is_interact_pressed():
                self._advance_final_office_scene()
            return

        if getattr(self, "_ava_phone_spying", False):
            if controller.is_cancel_pressed():
                if getattr(self, "_ava_phone_active_chat", None) is not None:
                    self._ava_phone_active_chat = None
                else:
                    self._ava_phone_spying = False
                    self._ava_phone_timer_active = False
                    if getattr(self, "_ava_phone_completed", False):
                        self._show_post_phone_monologue()
            return

        # During the ping pong minigame, delegate all controller input (including
        # Start/pause) directly to the minigame so the pause menu works there.
        if self.state == GameState.PINGPONG:
            self._handle_controller_pingpong(controller)
            return

        # ── universal controller buttons ──
        # Start = Pause (always available, including cinematic)
        if controller.is_pause_pressed():
            self._toggle_pause()
            return

        if getattr(self, "phone", None) and self.phone.is_visible and self.phone.is_map_fullscreen():
            close = self.world_map.handle_controller(controller)
            if close:
                self.phone._map_close_to_home()
            return

        if self.state == GameState.INTRO_CINEMATIC:
            # Block map/inventory/skill tree during cinematic
            pass
        else:
            # Back/View: abre mapa directamente sin pasar por home
            if controller.is_map_pressed():
                if self.state == GameState.PLAYING and getattr(self, "phone", None):
                    self.phone.open_map_direct()
                return

        # X = Wallet (inventory removed, only wallet remains)
        if controller.is_inventory_pressed():
            if self.state == GameState.PLAYING:
                self.previous_state = self.state
                self.state = GameState.WALLET
                self.active_wallet_item = None
                self.wallet_focus_item = None
            elif self.state == GameState.WALLET:
                self.state = GameState.PLAYING
                self.wallet_focus_item = None
            return

        # Y = Skill Tree
        if controller.is_skill_tree_pressed():
            if self.state == GameState.PLAYING:
                self.previous_state = self.state
                self.state = GameState.SKILL_TREE_SCREEN
            elif self.state == GameState.SKILL_TREE_SCREEN:
                self.state = GameState.PLAYING
            return

        # B = Cancel / Back out of overlay screens
        if controller.is_cancel_pressed():
            if self.state in (
                GameState.HELP,
                GameState.SKILL_TREE_SCREEN,
                GameState.INVENTORY_SCREEN,
            ):
                self.state = GameState.PLAYING
                return

        # ── state-specific controller input ──
        if self.state == GameState.INTRO_CINEMATIC:
            # Dedicated skip button: Y button, Back button, or B button skips cinematic directly!
            if controller.is_skill_tree_pressed() or controller.is_map_pressed() or controller.is_cancel_pressed():
                self._skip_cinematic()
                return

            # D-pad toggles focus on Skip button
            menu_h = controller.get_menu_direction_horizontal()
            menu_v = controller.get_menu_direction()
            if menu_h != 0 or menu_v != 0:
                self._cine_skip_focused = not self._cine_skip_focused
            # A button: if skip is focused, skip; otherwise advance dialogue
            if controller.is_confirm_pressed() or controller.is_interact_pressed():
                if self._cine_skip_focused:
                    if self.multiplayer:
                        self.cinematic_skip_voted = True
                    else:
                        self._skip_cinematic()
                else:
                    if self.multiplayer:
                        self.cinematic_continue_voted = True
                    else:
                        self._advance_cinematic_dialogue()
        elif self.state == GameState.PLAYING:
            self._handle_controller_playing(controller)
        elif self.state == GameState.PAUSED:
            self._handle_controller_paused(controller)
        elif self.state == GameState.MISSION_SELECT:
            self._handle_controller_mission_select(controller)
        elif self.state == GameState.DIALOGUE:
            # Dialogue is handled via the dialogue system's handle_controller method
            self.dialogue_system.handle_controller(controller)
        elif self.state == GameState.COMBAT:
            self._handle_controller_combat(controller)
        elif self.state == GameState.HACKING:
            self._handle_controller_hacking(controller)
        elif self.state == GameState.WALLET:
            self._handle_controller_wallet(controller)
        elif self.state == GameState.MAP:
            self._handle_controller_map(controller)
        elif self.state == GameState.SOCIAL_INTERACTION:
            self.social_dialogue_manager.handle_controller(controller)
        elif self.state == GameState.BASKETBALL:
            self.basketball.handle_controller(controller)
        elif self.state == GameState.MAINFRAME:
            self._handle_controller_mainframe(controller)
        elif self.state == GameState.TRADING:
            self._handle_controller_trading(controller)
        elif self.state == GameState.INVENTORY_SCREEN:
            self._handle_controller_inventory(controller)
        elif self.state == GameState.SKILL_TREE_SCREEN:
            self._handle_controller_skill_tree(controller)
        elif self.state == GameState.HELP:
            self._handle_controller_help(controller)


    def _toggle_pause(self):
        """Toggle pause state."""
        if self.state == GameState.PAUSED:
            self.state = getattr(self, 'previous_state', GameState.PLAYING)
        elif self.state in (GameState.PLAYING, GameState.INTRO_CINEMATIC, GameState.BASKETBALL):
            self.previous_state = self.state
            self.state = GameState.PAUSED
        elif self.state in (GameState.INVENTORY_SCREEN,
                            GameState.SKILL_TREE_SCREEN,
                            GameState.HELP,
                            GameState.WALLET):
            if self.state == GameState.WALLET and self.active_wallet_item:
                # Close active item view but stay in wallet; retain focus on that item
                self.wallet_focus_item = self.active_wallet_item
                self.active_wallet_item = None
            else:
                self.state = GameState.PLAYING
                self.wallet_focus_item = None
        elif self.state == GameState.MISSION_SELECT:
            if getattr(self, 'mission_select_confirm', False):
                self.mission_select_confirm = False
            else:
                self.state = GameState.PAUSED

    def _toggle_map(self):
        """Toggle map state."""
        if self.state == GameState.PLAYING:
            self.previous_state = self.state
            self.state = GameState.MAP
            map_floor = self.current_floor if self.current_floor in FLOOR_SIZES else FLOOR_CAMPUS
            self.world_map.current_tab = map_floor
            self.world_map._centre_on_floor(map_floor)
            self.world_map.reset_teleport_state()
            self.world_map._refresh_room_selection(reset_index=True)
        elif self.state == GameState.MAP:
            self.state = self.previous_state
            self.world_map.reset_teleport_state()
            if self.phone.is_visible:
                self.phone.close()

    def _handle_controller_playing(self, controller):
        """Handle controller input during PLAYING state."""
        # ── Phone active ──
        if self.phone.is_visible:
            self.phone.handle_controller(controller)
            return

        # ── Car panel: A confirms, B cancels ──
        if self._car_panel_active:
            if self._car_panel_input_delay > 0:
                return  # ignore input during delay
            menu_h = controller.get_menu_direction_horizontal()
            if menu_h != 0:
                sel = getattr(self, "_car_panel_selection", "accept")
                self._car_panel_selection = "cancel" if sel == "accept" else "accept"

            if controller.is_confirm_pressed():
                sel = getattr(self, "_car_panel_selection", "accept")
                if sel == "accept":
                    if self._can_end_school_day():
                        if self.multiplayer:
                            self.car_departure_voted = True
                        else:
                            self._car_panel_active = False
                            self._start_car_departure()
                    else:
                        self._car_panel_active = False
                        self._car_panel_cooldown = 1.0
                        self.ui.show_notification("You cannot leave school early.", NOTIF_ERROR)
                else:
                    self._car_panel_active = False
                    self.car_departure_voted = False
                    self._car_panel_cooldown = 1.0
            elif controller.is_cancel_pressed():
                self._car_panel_active = False
                self.car_departure_voted = False
                self._car_panel_cooldown = 1.0
            return

        # D-pad up or LB: open phone directly
        menu_v = controller.get_menu_direction()
        if menu_v == -1 or controller.is_block_pressed():
            self.phone.toggle_phone()
            self._hud_focus = None
            return

        # HUD focus navigation (D-pad left/right)
        menu_h = controller.get_menu_direction_horizontal()
        if menu_h != 0:
            hud_options = ["ff", "phone", "wallet"]
            if self._hud_focus not in hud_options:
                self._hud_focus = hud_options[0] if menu_h > 0 else hud_options[-1]
            else:
                idx = hud_options.index(self._hud_focus)
                idx = (idx + (1 if menu_h > 0 else -1)) % len(hud_options)
                self._hud_focus = hud_options[idx]

        handled_confirm = False
        if controller.is_confirm_pressed():
            if self._hud_focus == "wallet":
                self.previous_state = self.state
                self.state = GameState.WALLET
                self.active_wallet_item = None
                self.wallet_focus_item = None
                self._hud_focus = None
                handled_confirm = True
            elif self._hud_focus == "ff":
                self._ff_controller_active = True
                handled_confirm = True
            elif self._hud_focus == "phone":
                self.phone.toggle_phone()
                self._hud_focus = None
                handled_confirm = True

        # Maintain controller-based fast-forward while A is held
        if self._hud_focus == "ff" and controller.is_button_held(XBOX_A):
            self._ff_controller_active = True
        elif not controller.is_button_held(XBOX_A):
            self._ff_controller_active = False

        if not handled_confirm and self._hud_focus not in ("ff", "wallet", "phone"):
            # A = Interact only (dashing removed to resolve duplicate/overlapping dash controls)
            if controller.is_interact_pressed():
                if getattr(self, '_computer_prompt_active', False):
                    self._start_mainframe_login()
                    return
                if getattr(self, "_ava_phone_prompt_active", False):
                    self._try_interact()
                    return
                npc = self._nearest_npc(NPC_INTERACTION_RANGE)
                if npc:
                    self._try_interact()
                elif self._try_building_entry_confirm():
                    pass

            # RT dash is handled in player.update() via controller.rt_value
            # But we can also trigger dash on press for responsiveness
            if controller.is_dash_triggered():
                npc = self._nearest_npc(NPC_INTERACTION_RANGE)
                if not npc:  # Only dash if not interacting
                    self.player.start_dash()

        # RB = Light Attack (Aiden) or Hack (Lena)
        if controller.is_attack_pressed():
            if self.character == Character.AIDEN:
                self.player.start_attack()
            elif self.character == Character.LENA:
                hackable = self._get_hackable()
                if hackable:
                    self.hacking_game.start(hackable, self.player)
                    self.state = GameState.HACKING

    def _handle_controller_paused(self, controller):
        """Handle controller input during PAUSED state."""
        menu_dir = controller.get_menu_direction()
        option_count = len(self.pause_options)
        if menu_dir == -1:
            self.pause_sel = (getattr(self, 'pause_sel', 0) - 1) % option_count
        elif menu_dir == 1:
            self.pause_sel = (getattr(self, 'pause_sel', 0) + 1) % option_count

        if controller.is_confirm_pressed():
            sel = getattr(self, 'pause_sel', 0)
            if sel == 0:
                self.state = getattr(self, 'previous_state', GameState.PLAYING)
            elif sel == 1:
                self.state = GameState.MISSION_SELECT
                self.mission_select_sel = 0
                self.mission_select_confirm = False
            elif sel == 2:
                self._swap_character()
            elif sel == 3:  # Main Menu
                self.return_to_menu = True
                self.running = False
            else:  # Quit
                self.running = False

        if controller.is_cancel_pressed():
            self.state = getattr(self, 'previous_state', GameState.PLAYING)

    def _handle_controller_wallet(self, controller):
        """Handle controller input during WALLET state."""
        focus_cycle = ["id", "bill", "yearbook"]
        if self.inventory.has_item("Hacked Credentials"):
            focus_cycle.append("cred")

        if controller.is_cancel_pressed():
            if self.active_wallet_item:
                # Close detail view but keep focus on the same item
                self.wallet_focus_item = self.active_wallet_item
                self.active_wallet_item = None
            else:
                self.wallet_focus_item = None
                self.state = GameState.PLAYING
            return

        if controller.is_confirm_pressed():
            if self.active_wallet_item:
                # Return to wallet view from detail
                self.wallet_focus_item = self.active_wallet_item
                self.active_wallet_item = None
            elif self.wallet_focus_item:
                # Inspect the focused item
                self.active_wallet_item = self.wallet_focus_item
            else:
                # No focus yet – highlight the first card
                self.wallet_focus_item = focus_cycle[0]
            return

        if not self.active_wallet_item:
            move = controller.get_menu_direction_horizontal()
            if move != 0:
                if self.wallet_focus_item not in focus_cycle:
                    self.wallet_focus_item = focus_cycle[0] if move < 0 else focus_cycle[-1]
                else:
                    idx = focus_cycle.index(self.wallet_focus_item)
                    idx = (idx + move) % len(focus_cycle)
                    self.wallet_focus_item = focus_cycle[idx]
        elif self.active_wallet_item == "yearbook":
            move_v = controller.get_menu_direction()
            if move_v != 0:
                groups = ["Athletes", "Tech Club", "Populars", "Academics", "Rebels", "Outsiders"]
                cur_idx = groups.index(self.selected_yearbook_group) if self.selected_yearbook_group in groups else 0
                self.selected_yearbook_group = groups[(cur_idx + move_v) % len(groups)]
                self.yearbook_scroll_offset = 0
                print(f"[Yearbook] Controller cycled group to: {self.selected_yearbook_group}")

            # Page UP/DOWN inside the active Yearbook group's NPC list using LB and RB
            from src.controller import XBOX_LB, XBOX_RB
            if controller.is_button_pressed(XBOX_LB):
                self.yearbook_scroll_offset = max(0, self.yearbook_scroll_offset - 1)
                print(f"[Yearbook] Controller scrolled UP. Offset: {self.yearbook_scroll_offset}")
            elif controller.is_button_pressed(XBOX_RB):
                self.yearbook_scroll_offset += 1
                print(f"[Yearbook] Controller scrolled DOWN. Offset: {self.yearbook_scroll_offset}")

    def _handle_controller_map(self, controller):
        """Handle controller input during MAP state."""
        close = self.world_map.handle_controller(controller)
        if close:
            self.state = self.previous_state
            if self.phone.is_visible:
                self.phone.close()
            did_request_teleport = getattr(self.world_map, 'teleport_requested', False)
            if did_request_teleport:
                self.world_map.teleport_requested = False
                tfloor = self.world_map.teleport_floor
                tx, ty = self.world_map.teleport_pos
                self._try_teleport_to(tfloor, int(tx), int(ty))
            self.world_map.reset_teleport_state()

    def _handle_controller_combat(self, controller):
        """Handle controller input during COMBAT state."""
        # Pass to combat system if it has controller support
        if hasattr(self.combat_system, 'handle_controller'):
            self.combat_system.handle_controller(controller, self.player)

    def _handle_controller_hacking(self, controller):
        """Handle controller input during HACKING state."""
        if hasattr(self.hacking_game, 'handle_controller'):
            self.hacking_game.handle_controller(controller)

    def _handle_controller_pingpong(self, controller):
        """Handle controller input during PINGPONG state."""
        if hasattr(self.pingpong, 'handle_controller'):
            self.pingpong.handle_controller(controller)

    def _handle_controller_mainframe(self, controller):
        """Handle controller input for the MAINFRAME state."""
        if not hasattr(self, "mainframe_focus_idx"):
            self.mainframe_focus_idx = 4

        # Back button / B button to go back or cancel
        if controller.is_cancel_pressed():
            if self.mainframe_screen == "login":
                self.state = GameState.PLAYING
            elif self.mainframe_screen == "desktop":
                self.mainframe_screen = "alarm"
            elif self.mainframe_screen == "mail":
                self.mainframe_screen = "desktop"
                self.mainframe_focus_idx = 0
            elif self.mainframe_screen == "mail_view":
                self.mainframe_screen = "mail"
                self.mainframe_focus_idx = 0
            elif self.mainframe_screen == "alarm":
                self._exit_mainframe_success()
            return

        # D-pad Up / Down / Left / Right
        menu_v = controller.get_menu_direction()
        menu_h = controller.get_menu_direction_horizontal()

        if self.mainframe_screen == "login":
            # 5 focusable items: 0: User, 1: Pass, 2: Login, 3: Exit, 4: Autofill
            if menu_v != 0:
                self.mainframe_focus_idx = (self.mainframe_focus_idx + menu_v) % 5
            elif menu_h != 0:
                if self.mainframe_focus_idx == 2 and menu_h > 0:
                    self.mainframe_focus_idx = 3
                elif self.mainframe_focus_idx == 3 and menu_h < 0:
                    self.mainframe_focus_idx = 2

            if controller.is_confirm_pressed():
                if self.mainframe_focus_idx == 0:
                    self.mainframe_active_field = "user"
                elif self.mainframe_focus_idx == 1:
                    self.mainframe_active_field = "pass"
                elif self.mainframe_focus_idx == 2:
                    if self.mainframe_user_input == "admin_techlab" and self.mainframe_pass_input == "pWd_sMiLe_cLuB_99!":
                        self.mainframe_screen = "desktop"
                        self.mainframe_error = ""
                        self.mainframe_focus_idx = 0
                    else:
                        self.mainframe_error = "INVALID CREDENTIALS"
                elif self.mainframe_focus_idx == 3:
                    self.state = GameState.PLAYING
                elif self.mainframe_focus_idx == 4:
                    self.mainframe_user_input = "admin_techlab"
                    self.mainframe_pass_input = "pWd_sMiLe_cLuB_99!"
                    self.mainframe_screen = "desktop"
                    self.mainframe_error = ""
                    self.mainframe_focus_idx = 0

        elif self.mainframe_screen == "desktop":
            # 4 focusable items: 0: Mail, 1: Files, 2: Recycle, 3: Disconnect
            if menu_h != 0:
                self.mainframe_focus_idx = (self.mainframe_focus_idx + menu_h) % 4
            elif menu_v != 0:
                self.mainframe_focus_idx = (self.mainframe_focus_idx + menu_v) % 4

            if controller.is_confirm_pressed():
                if self.mainframe_focus_idx == 0:
                    self.mainframe_screen = "mail"
                    self.mainframe_focus_idx = 0
                elif self.mainframe_focus_idx == 3:
                    self.mainframe_screen = "alarm"
                    self.mainframe_focus_idx = 0

        elif self.mainframe_screen == "mail":
            # 6 focusable items:
            # 0: Back, 1: Disconnect, 2: Eli's Email, 3: Walsh, 4: Davis, 5: IT Support
            if menu_v != 0:
                self.mainframe_focus_idx = (self.mainframe_focus_idx + menu_v) % 6
            elif menu_h != 0:
                if self.mainframe_focus_idx == 0 and menu_h > 0:
                    self.mainframe_focus_idx = 1
                elif self.mainframe_focus_idx == 1 and menu_h < 0:
                    self.mainframe_focus_idx = 0

            if controller.is_confirm_pressed():
                if self.mainframe_focus_idx == 0:
                    self.mainframe_screen = "desktop"
                    self.mainframe_focus_idx = 0
                elif self.mainframe_focus_idx == 1:
                    self.mainframe_screen = "alarm"
                    self.mainframe_focus_idx = 0
                elif self.mainframe_focus_idx == 2:
                    self.mainframe_screen = "mail_view"
                    self.mainframe_selected_email = "eli"
                    self.mainframe_focus_idx = 0

        elif self.mainframe_screen == "mail_view":
            # 3 focusable items: 0: Back, 1: Disconnect, 2: Close
            if menu_v != 0:
                self.mainframe_focus_idx = (self.mainframe_focus_idx + menu_v) % 3
            elif menu_h != 0:
                if self.mainframe_focus_idx == 0 and menu_h > 0:
                    self.mainframe_focus_idx = 1
                elif self.mainframe_focus_idx == 1 and menu_h < 0:
                    self.mainframe_focus_idx = 0

            if controller.is_confirm_pressed():
                if self.mainframe_focus_idx in (0, 2):
                    self.mainframe_screen = "mail"
                    self.mainframe_focus_idx = 0
                elif self.mainframe_focus_idx == 1:
                    self.mainframe_screen = "alarm"
                    self.mainframe_focus_idx = 0

        elif self.mainframe_screen == "alarm":
            # Only 1 focusable item: 0: Acknowledge & Escape
            if controller.is_confirm_pressed():
                self._exit_mainframe_success()

    def _handle_controller_trading(self, controller):
        """Handle controller input during TRADING state."""
        self.trade_system.handle_controller(controller)

    def _handle_controller_inventory(self, controller):
        """Handle controller input in Inventory Screen."""
        # Press X or B to close and return to playing
        if controller.is_inventory_pressed() or controller.is_cancel_pressed():
            self.state = GameState.PLAYING
            return
        self.inventory.handle_controller(controller)

    def _handle_controller_skill_tree(self, controller):
        """Handle controller input in Skill Tree Screen."""
        # Press Y or B to close and return to playing
        if controller.is_skill_tree_pressed() or controller.is_cancel_pressed():
            self.state = GameState.PLAYING
            return
        self.skill_tree.handle_controller(controller, self.player)

    def _handle_controller_help(self, controller):
        """Handle controller input in Help Screen."""
        # Press B or Start or Back to close and return to previous state
        if controller.is_cancel_pressed() or controller.is_pause_pressed():
            self.state = getattr(self, 'previous_state', GameState.PLAYING)

    def _on_key_down(self, event: pygame.event.Event):
        # ── intro cinematic: allow pause + dialogue advance only ──
        if self.state == GameState.INTRO_CINEMATIC:
            if event.key == KEY_PAUSE:
                self.previous_state = GameState.INTRO_CINEMATIC
                self.state = GameState.PAUSED
                return
            self._keys_cinematic(event)
            return

        # ── universal keys ──
        if event.key == KEY_HELP:
            if self.state == GameState.HELP:
                self.state = self.previous_state
            else:
                self.previous_state = self.state
                self.state = GameState.HELP
            return

        if event.key == KEY_PAUSE:
            # When ping-pong is active, let the minigame handle ESC itself
            if self.state == GameState.PINGPONG:
                pass  # fall through to state-specific dispatch below
            elif self.state == GameState.SOCIAL_INTERACTION:
                # Close social interaction on ESC
                self.social_dialogue_manager.force_close()
                self.state = GameState.PLAYING
            elif self.state == GameState.PAUSED:
                self.state = getattr(self, 'previous_state', GameState.PLAYING)
            elif self.state in (GameState.PLAYING, GameState.BASKETBALL):
                if self.state == GameState.PLAYING and self._car_panel_active:
                    self._car_panel_active = False
                    self._car_panel_cooldown = 1.0
                    return
                self.previous_state = self.state
                self.state = GameState.PAUSED
            elif self.state in (GameState.INVENTORY_SCREEN,
                                GameState.SKILL_TREE_SCREEN,
                                GameState.HELP,
                                GameState.WALLET):
                if self.state == GameState.WALLET and self.active_wallet_item:
                    self.active_wallet_item = None
                else:
                    self.state = GameState.PLAYING
            elif self.state == GameState.MISSION_SELECT:
                if getattr(self, 'mission_select_confirm', False):
                    self.mission_select_confirm = False
                else:
                    self.state = GameState.PAUSED
                return
            else:
                return
            if self.state != GameState.PINGPONG:
                return

        if event.key == KEY_MAP:
            # Acceso directo al mapa: M abre directamente el mapa sin pasar por home
            if self.state == GameState.PLAYING:
                self.phone.open_map_direct()
            return

        # ── state-specific dispatch ──
        handler = {
            GameState.PLAYING:          self._keys_playing,
            GameState.INTRO_CINEMATIC:  self._keys_cinematic,
            GameState.DIALOGUE:         lambda e: self.dialogue_system.handle_input(e),
            GameState.SOCIAL_INTERACTION: lambda e: self.social_dialogue_manager.handle_input(e),
            GameState.PINGPONG:         lambda e: self.pingpong.handle_input(e),
            GameState.BASKETBALL:       lambda e: self.basketball.handle_input(e),
            GameState.COMBAT:           lambda e: self.combat_system.handle_input(e, self.player),
            GameState.HACKING:          lambda e: self.hacking_game.handle_input(e),
            GameState.TRADING:          lambda e: self.trade_system.handle_input(e),
            GameState.INVENTORY_SCREEN: lambda e: self.inventory.handle_input(e),
            GameState.SKILL_TREE_SCREEN:lambda e: self.player.skill_tree.handle_input(e, self.player),
            GameState.WALLET:           self._keys_wallet,
            GameState.PAUSED:           self._keys_paused,
            GameState.MISSION_SELECT:   self._keys_mission_select,
            GameState.GAME_OVER:        self._keys_game_over,
        }.get(self.state)
        if handler:
            handler(event)
    def _keys_wallet(self, event: pygame.event.Event):
        """Handle keyboard input while in the wallet view."""
        if self.active_wallet_item == "yearbook":
            groups = ["Athletes", "Tech Club", "Populars", "Academics", "Rebels", "Outsiders"]
            cur_idx = groups.index(self.selected_yearbook_group) if self.selected_yearbook_group in groups else 0
            if event.key in (pygame.K_UP, pygame.K_w):
                self.selected_yearbook_group = groups[(cur_idx - 1) % len(groups)]
                self.yearbook_scroll_offset = 0
                print(f"[Yearbook] Cycled group UP to: {self.selected_yearbook_group}")
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected_yearbook_group = groups[(cur_idx + 1) % len(groups)]
                self.yearbook_scroll_offset = 0
                print(f"[Yearbook] Cycled group DOWN to: {self.selected_yearbook_group}")
            elif event.key == pygame.K_PAGEUP:
                self.yearbook_scroll_offset = max(0, self.yearbook_scroll_offset - 1)
                print(f"[Yearbook] Keyboard scrolled UP. Offset: {self.yearbook_scroll_offset}")
            elif event.key == pygame.K_PAGEDOWN:
                self.yearbook_scroll_offset += 1
                print(f"[Yearbook] Keyboard scrolled DOWN. Offset: {self.yearbook_scroll_offset}")
            elif event.key in (pygame.K_ESCAPE, pygame.K_i):
                self.active_wallet_item = None

    # ── key handlers per state ────────────────────────────────

    def _keys_playing(self, event: pygame.event.Event):
        # ── Car panel active: E confirms, ESC dismisses ──
        if self._car_panel_active:
            if self._car_panel_input_delay > 0:
                return  # ignore input during delay
            if event.key == pygame.K_e:
                if self._can_end_school_day():
                    if self.multiplayer:
                        self.car_departure_voted = True
                    else:
                        self._car_panel_active = False
                        self._start_car_departure()
                else:
                    self._car_panel_active = False
                    self._car_panel_cooldown = 1.0
                    self.ui.show_notification("You cannot leave school early.", NOTIF_ERROR)
            elif event.key == KEY_PAUSE:
                self._car_panel_active = False
                self.car_departure_voted = False
                self._car_panel_cooldown = 1.0  # prevent re-trigger
            return

        # Interact/talk only with E.
        if event.key == KEY_INTERACT:
            # Priority 1: Computer Prompt (Mainframe Login)
            if getattr(self, '_computer_prompt_active', False):
                self._start_mainframe_login()
                return
            
            # Priority 1.5: Phone Check
            if getattr(self, "_ava_phone_prompt_active", False):
                self._try_interact()
                return

            # Priority 2: Building Entrance
            if self._try_building_entry_confirm():
                return
            
            # Priority 3: NPC Interaction
            npc = self._nearest_npc(NPC_INTERACTION_RANGE)
            if npc and npc.health > 0:
                self._try_interact()
                return

            return

        elif event.key == KEY_DASH:
            self.player.start_dash()

        elif event.key in (KEY_DASH_ALT, KEY_DASH_ALT2):
            self.player.start_dash()
        elif event.key == KEY_INVENTORY:
            # Inventory removed - open wallet instead
            self.previous_state = self.state
            self.state = GameState.WALLET
            self.active_wallet_item = None
            self.wallet_focus_item = None
        elif event.key == KEY_PHONE:
            self.phone.toggle_phone()
        elif event.key == KEY_HACK and self.character == Character.LENA:
            hackable = self._get_hackable()
            if hackable:
                self.hacking_game.start(hackable, self.player)
                self.state = GameState.HACKING
        elif (event.key == KEY_LIGHT_ATTACK
              and (self.character == Character.AIDEN or getattr(self, "_final_reveal_finished", False))):
            self.player.start_attack()
        

    def _keys_cinematic(self, event: pygame.event.Event):
        """Handle keyboard input during the intro cinematic."""
        if event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_e, KEY_INTERACT):
            if self.multiplayer:
                self.cinematic_continue_voted = True
            else:
                self._advance_cinematic_dialogue()
        elif event.key == pygame.K_q:  # Q key skips cinematic directly
            if self.multiplayer:
                self.cinematic_skip_voted = True
            else:
                self._skip_cinematic()

    def _keys_paused(self, event: pygame.event.Event):
        option_count = len(self.pause_options)
        if event.key in (pygame.K_UP, pygame.K_w):
            self.pause_sel = (getattr(self, 'pause_sel', 0) - 1) % option_count
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.pause_sel = (getattr(self, 'pause_sel', 0) + 1) % option_count
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            sel = getattr(self, 'pause_sel', 0)
            if sel == 0:  # Resume
                self.state = getattr(self, 'previous_state', GameState.PLAYING)
            elif sel == 1:  # Select Mission
                self.state = GameState.MISSION_SELECT
                self.mission_select_sel = 0
                self.mission_select_confirm = False
            elif sel == 2:  # Change Character
                self._swap_character()
            elif sel == 3:  # Main Menu — return to menu without closing the app
                self.return_to_menu = True
                self.running = False
            else:  # Quit — actually close the application
                self.running = False
        elif event.key == pygame.K_q:
            self.running = False

    def _keys_game_over(self, event: pygame.event.Event):
        if event.key == KEY_PAUSE:
            self.running = False

    def _get_mission_select_list(self):
        return [
            ("mission_first_day", 1, "Day 1: Follow Noah Carter around the school", "Mission 1: Follow Noah Carter through the school."),
            ("mission_strange_rumours", 1, "Day 1: Ping Pong match against Oscar Jimenez", "Mission 2: Go to the Ping Pong court to play against Oscar Jimenez."),
            ("mission_library_secrets", 1, "Day 1: Talk to Ava Thompson in the Library", "Mission 3: Go to the Library and talk to Ava Thompson."),
            ("mission_tech_lab_ava", 2, "Day 2: Meet Ava Thompson in Tech Lab", "Mission 4: Go to Tech Lab to meet Ava Thompson."),
            ("mission_alan_chen_bathroom", 2, "Day 2: Talk to Alan Chen", "Mission 5: Find Alan Chen in his discreet location."),
            ("mission_tech_club_rep", 2, "Day 2: Earn Alan's Trust", "Mission 6: Gain 70 Tech Club reputation, then return to Alan Chen."),
            ("mission_return_tech_lab", 2, "Day 2: Return to Ava Thompson", "Mission 7: Deliver the hacked credentials to Ava Thompson."),
            ("mission_high_school_mainframe", 2, "Day 2: High School Mainframe", "Mission 8: Switch to Lena, go to the computer marked with X in the Tech Lab and extract information."),
            ("mission_server_room", 3, "Day 3: Talk to Marcus Green", "Mission 9: Talk to Marcus Green in the Athletic Coliseum."),
            ("mission_rooftop_party", 4, "Day 4: Rooftop Party", "Mission 10: Go to the Rooftop party and hang out with the populars."),
            ("mission_talk_ava_rooftop", 4, "Day 4: Find Ava at the Rooftop Party", "Mission 11: Talk to Ava Thompson at the rooftop party."),
            ("mission_check_ava_phone", 4, "Day 4: Check Ava's Phone", "Mission 12: Check Ava Thompson's phone before she comes back (15 seconds!)."),
            ("mission_final_showdown", 4, "Day 4: Go to the Basement", "Mission 13: Go to the Basement and see what they're plotting!")
        ]

    def _get_current_mission_index(self) -> int:
        mission_list = self._get_mission_select_list()
        for i, m_info in enumerate(mission_list):
            m_obj = self.mission_manager.missions.get(m_info[0])
            if m_obj and m_obj.status in (MissionStatus.ACTIVE, MissionStatus.AVAILABLE):
                return i
        for i in range(len(mission_list) - 1, -1, -1):
            m_obj = self.mission_manager.missions.get(mission_list[i][0])
            if m_obj and m_obj.status == MissionStatus.COMPLETED:
                return min(i + 1, len(mission_list) - 1)
        return 0

    def _keys_mission_select(self, event: pygame.event.Event):
        mission_list = self._get_mission_select_list()
        if getattr(self, 'mission_select_confirm', False):
            if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                self.mission_confirm_sel = 1 - getattr(self, 'mission_confirm_sel', 0)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if getattr(self, 'mission_confirm_sel', 0) == 0:
                    self._execute_mission_jump()
                else:
                    self.mission_select_confirm = False
            elif event.key == pygame.K_ESCAPE:
                self.mission_select_confirm = False
        else:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.mission_select_sel = (getattr(self, 'mission_select_sel', 0) - 1) % len(mission_list)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.mission_select_sel = (getattr(self, 'mission_select_sel', 0) + 1) % len(mission_list)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                curr_idx = self._get_current_mission_index()
                if getattr(self, 'mission_select_sel', 0) < curr_idx:
                    self.ui.show_notification("You cannot jump back to previous missions.", NOTIF_ERROR)
                else:
                    self.mission_select_confirm = True
                    self.mission_confirm_sel = 0
            elif event.key == pygame.K_ESCAPE:
                self.state = GameState.PAUSED

    def _handle_controller_mission_select(self, controller):
        mission_list = self._get_mission_select_list()
        if getattr(self, 'mission_select_confirm', False):
            h_dir = controller.get_menu_direction_horizontal()
            if h_dir != 0:
                self.mission_confirm_sel = 1 - getattr(self, 'mission_confirm_sel', 0)
            if controller.is_confirm_pressed():
                if getattr(self, 'mission_confirm_sel', 0) == 0:
                    self._execute_mission_jump()
                else:
                    self.mission_select_confirm = False
            elif controller.is_cancel_pressed():
                self.mission_select_confirm = False
        else:
            menu_dir = controller.get_menu_direction()
            if menu_dir == -1:
                self.mission_select_sel = (getattr(self, 'mission_select_sel', 0) - 1) % len(mission_list)
            elif menu_dir == 1:
                self.mission_select_sel = (getattr(self, 'mission_select_sel', 0) + 1) % len(mission_list)
            if controller.is_confirm_pressed():
                curr_idx = self._get_current_mission_index()
                if getattr(self, 'mission_select_sel', 0) < curr_idx:
                    self.ui.show_notification("You cannot jump back to previous missions.", NOTIF_ERROR)
                else:
                    self.mission_select_confirm = True
                    self.mission_confirm_sel = 0
            elif controller.is_cancel_pressed():
                self.state = GameState.PAUSED

    def _execute_mission_jump(self):
        mission_list = self._get_mission_select_list()
        selected_m = mission_list[getattr(self, 'mission_select_sel', 0)]
        target_id = selected_m[0]
        target_day = selected_m[1]
        target_text = selected_m[3]

        self.day_number = target_day
        self.time_of_day_minutes = 7 * 60 # 7:00 AM
        self._last_time_minutes = 7 * 60
        self._school_day_ended = False

        found_target = False
        for m_info in mission_list:
            m_id = m_info[0]
            m_obj = self.mission_manager.missions.get(m_id)
            if not m_obj:
                continue
            if m_id == target_id:
                found_target = True
                m_obj.status = MissionStatus.ACTIVE
                for prereq in m_obj.prerequisites:
                    self.mission_manager.completed_ids.add(prereq)
            elif not found_target:
                m_obj.status = MissionStatus.COMPLETED
                for obj in m_obj.objectives:
                    obj.completed = True
                    obj.progress = obj.required
                self.mission_manager.completed_ids.add(m_id)
            else:
                m_obj.status = MissionStatus.LOCKED
                for obj in m_obj.objectives:
                    obj.completed = False
                    obj.progress = 0

        self.mission_manager._refresh_availability()

        self._current_main_mission_text = target_text
        if target_day >= 2 or target_id in ("mission_strange_rumours", "mission_library_secrets"):
            self._pingpong_unlocked = True
        if target_day >= 2 or target_id == "mission_library_secrets":
            self._rooftop_unlocked = True
        if target_day >= 2:
            self._day1_story_complete = True
        if target_id == "mission_final_showdown":
            self.inventory.add_item("Basement Key", ItemCategory.KEY, "Opens the door to the school basement")
            self._final_smile_room_ready = False
            self._final_reveal_started = False
            self._final_reveal_finished = False
            self._final_office_started = False
            self._final_reveal_active = False
            self._final_office_active = False
            self._setup_smile_club_room()
        if target_id in ("mission_return_tech_lab", "mission_high_school_mainframe", "mission_helping_mia", "mission_server_room", "mission_rooftop_party", "mission_final_showdown"):
            if not self.inventory.has_item("Hacked Credentials"):
                self.inventory.add_item("Hacked Credentials", ItemCategory.NOTE, "Hacked high school system credentials provided by Alan Chen.")
        if target_id == "mission_high_school_mainframe":
            self._ava_needs_to_walk_to_computer = True
        if target_id in ("mission_rooftop_party", "mission_talk_ava_rooftop", "mission_check_ava_phone"):
            self._place_day4_rooftop_npcs()
            if target_id == "mission_talk_ava_rooftop":
                # Mission 10 already done
                m10 = self.mission_manager.missions.get("mission_rooftop_party")
                if m10:
                    m10.status = MissionStatus.COMPLETED
                    self.mission_manager.completed_ids.add("mission_rooftop_party")
            if target_id == "mission_check_ava_phone":
                # Missions 10+11 done, Ava's phone already on chair
                self._ava_rooftop_dialogue_completed = True
                self._ava_phone_on_chair = True
                self._bad_feeling_active = False
                self._player_bad_feeling_shown = True
                
                # Remove Marcus, Noah, and Ava from the rooftop
                for nid in ("npc_marcus_green", "npc_noah_carter", "npc_ava_thompson"):
                    npc = self.npc_manager.get_npc_by_id(nid)
                    if npc:
                        npc.current_floor = FLOOR_1F
                        npc.rect.center = (1500, 500)
                        npc.ai_enabled = False


        if target_id in ("mission_rooftop_party", "mission_talk_ava_rooftop"):
            self.player.rect.center = (1600, 1600)  # Near rooftop stairs
            self.current_floor = FLOOR_ROOFTOP
        elif target_id == "mission_check_ava_phone":
            self.player.rect.center = (1520, 770)   # Near the phone chair
            self.current_floor = FLOOR_ROOFTOP
        elif target_id == "mission_final_showdown":
            self.player.rect.center = (800, 1760)   # Near basement stairs on 1F
            self.current_floor = FLOOR_1F
        elif target_id == "mission_server_room":
            self.player.rect.center = (900, 980)    # Athletic Coliseum interior
            self.current_floor = FLOOR_COLISEUM_INTERIOR
        elif target_id == "mission_strange_rumours":
            self.player.rect.center = (650, 900)    # Ping Pong court interior
            self.current_floor = FLOOR_PINGPONG_INTERIOR
        elif target_id == "mission_library_secrets":
            self.player.rect.center = (2650, 350)   # Library on 1F
            self.current_floor = FLOOR_1F
        elif target_id == "mission_tech_lab_ava":
            self.player.rect.center = (180, 350)    # Tech lab on 1F
            self.current_floor = FLOOR_1F
        else:
            self.player.rect.center = (2000, 2700)
            self.current_floor = FLOOR_CAMPUS

        floor = self.school_map.get_floor(self.current_floor)
        if floor:
            self._floor_w = floor.width
            self._floor_h = floor.height
            self.camera.set_bounds(floor.width, floor.height)
        self.camera.update(self.player)

        self._place_ava_for_story()

        self.state = GameState.PLAYING
        self.mission_select_confirm = False
        self.ui.show_notification(f"Jumped to Day {target_day}: {selected_m[2]}", NOTIF_SUCCESS)

    # ──────────────────────────────────────────────────────────
    #  INTERACTION HELPERS
    # ──────────────────────────────────────────────────────────

    def _start_mainframe_login(self):
        self.state = GameState.MAINFRAME
        self.mainframe_user_input = ""
        self.mainframe_pass_input = ""
        self.mainframe_active_field = "user"
        self.mainframe_screen = "login"
        self.mainframe_error = ""
        self.mainframe_alarm = False
        self.mainframe_selected_email = None
        self._computer_prompt_active = False
        self.mainframe_focus_idx = 4  # Start with focus on the Auto-Fill button for seamless controller play

    def _nearest_npc(self, radius: float, skip_siblings: bool = False):
        """Return the closest NPC within *radius*, or None."""
        npcs = self.npc_manager.get_npcs_on_floor(self.current_floor)
        px, py = self.player.rect.center
        best, best_d = None, radius
        for npc in npcs:
            if skip_siblings and npc.id in ("npc_aiden", "npc_lena"):
                continue
            if (npc.id in getattr(self, "_final_smile_ids", ())
                    and (getattr(self, "_is_final_showdown_active", lambda: False)()
                         or getattr(self, "_final_reveal_started", False))):
                continue
            if npc.id == "npc_noah_carter":
                continue
            d = ((npc.rect.centerx - px)**2 + (npc.rect.centery - py)**2) ** 0.5
            if d < best_d:
                best_d = d
                best   = npc
        return best

    def _get_hackable(self) -> dict | None:
        npc = self._nearest_npc(NPC_INTERACTION_RANGE)
        if npc:
            return {"type": "npc_chat", "target": npc, "difficulty": 2, "id": npc.id}
        floor = self.school_map.get_floor(self.current_floor)
        if floor:
            px, py = self.player.rect.center
            for obj in floor.hackable_objects:
                d = ((obj["x"] - px)**2 + (obj["y"] - py)**2) ** 0.5
                if d < NPC_INTERACTION_RANGE:
                    return obj
        return None

    def _try_interact(self):
        """Interact with nearest NPC or with Ava's phone on rooftop."""
        # Check phone on chair first (proximity ENTER)
        if (self.current_floor == FLOOR_ROOFTOP
                and getattr(self, "_ava_phone_on_chair", False)
                and getattr(self, "_ava_phone_prompt_active", False)
                and not getattr(self, "_ava_phone_spying", False)):
            self._start_ava_phone_check()
            return

        npc = self._nearest_npc(NPC_INTERACTION_RANGE)
        if npc and npc.health > 0:
            if npc.id == "npc_marcus_green" and self.current_floor != FLOOR_COLISEUM_INTERIOR:
                self.ui.show_notification("Marcus Green is not in the Sports Arena right now.", NOTIF_WARNING)
                return

            # Day 4: Ava at rooftop party — use custom cinematic dialogue
            if (self.current_floor == FLOOR_ROOFTOP
                    and npc.id == "npc_ava_thompson"
                    and self.day_number >= 4
                    and not getattr(self, "_ava_rooftop_dialogue_completed", False)):
                if self.multiplayer and not self.is_host:
                    self._pending_dialogue_request = {"special": "ava_rooftop", "npc_id": npc.id}
                    return
                self._begin_ava_rooftop_dialogue()
                self.player.vx = 0
                self.player.vy = 0
                return

            if npc.id == "npc_gordon":
                self.previous_state = self.state
                self.state = GameState.SKILL_TREE_SCREEN
                self.player.vx = 0
                self.player.vy = 0
                self.player._dashing = False
                return

            # Check if this NPC has a dialogue_id (story NPC using old system)
            dlg_id = npc.get_dialogue_id(self.character)
            if dlg_id:
                # Use old dialogue system for story NPCs
                if self.multiplayer:
                    if not self.is_host:
                        self._pending_dialogue_request = {"dialogue_id": dlg_id, "npc_id": npc.id}
                    else:
                        self.dialogue_system.start_dialogue(
                            dlg_id, npc, self.player, self.reputation,
                        )
                        self.state = GameState.DIALOGUE
                        self.mission_manager.advance_objective_event("talk_to", npc.id)
                        self.player.vx = 0
                        self.player.vy = 0
                        self.player._dashing = False
                else:
                    self.dialogue_system.start_dialogue(
                        dlg_id, npc, self.player, self.reputation,
                    )
                    self.state = GameState.DIALOGUE
                    self.mission_manager.advance_objective_event("talk_to", npc.id)
                    self.player.vx = 0
                    self.player.vy = 0
                    self.player._dashing = False
            else:
                # Co-op: Lena talks to party NPCs to add time to phone timer
                if (self.multiplayer and self.current_floor == FLOOR_ROOFTOP
                        and getattr(self, "_ava_phone_timer_active", False)
                        and npc.id not in getattr(self, "_coop_time_bonus_npcs", set())):
                    self._coop_time_bonus_npcs.add(npc.id)
                    self._ava_phone_timer = min(15.0, self._ava_phone_timer + 3.0)
                    self.ui.show_notification(f"{npc.name} is keeping Ava busy! +3s", NOTIF_SUCCESS, 2.5)

                # Use new social dialogue system for regular NPCs
                if self.social_dialogue_manager.try_start(npc, self.player):
                    self.state = GameState.SOCIAL_INTERACTION
                    self.player.vx = 0
                    self.player.vy = 0
                    self.player._dashing = False

    def _get_campus_entry_target(self):
        if self.current_floor != FLOOR_CAMPUS:
            return None
        if self._entry_prompt_cooldown > 0:
            return None
        px, py = self.player.rect.centerx, self.player.rect.centery
        entrances = [
            {
                "id": "main_building",
                "label": "Main Building",
                "zone": pygame.Rect(1880, 1960, 240, 110),
                "target_floor": FLOOR_1F,
                "spawn": (1600, 2200),
            },
            {
                "id": "athletic_coliseum",
                "label": "Athletic Coliseum",
                "zone": pygame.Rect(3190, 1060, 300, 90),
                "target_floor": FLOOR_COLISEUM_INTERIOR,
                "spawn": (900, 980),
            },
            {
                "id": "ping_pong_court",
                "label": "Ping Pong Court",
                "zone": pygame.Rect(3340, 2810, 300, 90),
                "target_floor": FLOOR_PINGPONG_INTERIOR,
                "spawn": (650, 900),
            },
        ]
        for entry in entrances:
            if entry["zone"].collidepoint(px, py):
                return entry
        return None

    def _update_entry_prompt_target(self):
        if self._entry_prompt_cooldown > 0:
            self._entry_prompt_target = None
            return
        self._entry_prompt_target = self._get_campus_entry_target()

    def _is_pingpong_unlocked(self) -> bool:
        if getattr(self, "_pingpong_unlocked", False):
            return True
        txt = getattr(self, "_current_main_mission_text", "")
        if not txt:
            return False
        if "Mission 2: Go to the Ping Pong court" in txt or "Mission 3:" in txt or "Day 1 all missions completed" in txt or self.day_number > 1:
            self._pingpong_unlocked = True
            return True
        return False

    def _is_coliseum_unlocked(self) -> bool:
        if getattr(self, "_coliseum_unlocked", False):
            return True
        txt = getattr(self, "_current_main_mission_text", "")
        if not txt:
            return False
        if "Mission 9:" in txt or "Mission 10:" in txt or "Mission 11:" in txt or "Side Mission:" in txt or self.day_number >= 3:
            self._coliseum_unlocked = True
            return True
        m = self.mission_manager.missions.get("mission_server_room")
        if m and m.status in (MissionStatus.AVAILABLE, MissionStatus.ACTIVE, MissionStatus.COMPLETED):
            self._coliseum_unlocked = True
            return True
        return False

    def _try_building_entry_confirm(self) -> bool:
        target = self._entry_prompt_target
        if not target:
            return False
            
        if target["id"] == "ping_pong_court":
            if not self._is_pingpong_unlocked():
                self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                self._entry_prompt_cooldown = 0.6
                self._entry_prompt_target = None
                return False
        if target["id"] == "athletic_coliseum":
            if not self._is_coliseum_unlocked():
                self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                self._entry_prompt_cooldown = 0.6
                self._entry_prompt_target = None
                return False

        sx, sy = target["spawn"]
        self._go_to_floor(target["target_floor"], sx, sy)
        self._transition_cooldown = 0.5
        self._entry_prompt_cooldown = 0.6
        self._entry_prompt_target = None
        return True

    def _is_basement_unlocked(self) -> bool:
        final_mission = self.mission_manager.missions.get("mission_final_showdown")
        if final_mission and getattr(final_mission.status, "value", str(final_mission.status)) in ("active", "completed"):
            return True
        return self.inventory.has_item("Basement Key")

    def _check_floor_transition(self):
        """Portal-type transitions (legacy — kept for future use)."""
        if self._transition_cooldown > 0:
            return
        # Campus building entries are now manual with confirmation prompt.
        if self.current_floor == FLOOR_CAMPUS:
            return
        floor = self.school_map.get_floor(self.current_floor)
        if not floor:
            return
        for tr in floor.transitions:
            if self.player.rect.colliderect(tr.rect):
                if tr.locked:
                    return
                if tr.target_floor == FLOOR_BASEMENT and not self._is_basement_unlocked():
                    if getattr(self, '_basement_block_timer', 0) <= 0:
                        self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                        self._basement_block_timer = 2.0
                    return
                self._go_to_floor(tr.target_floor, tr.spawn_x, tr.spawn_y)
                self._transition_cooldown = 0.5
                return

    def _check_seamless_stairs(self):
        """Seamless staircase/building transitions.

        Checks if the player crossed the transition-Y inside a staircase
        or the campus-building overlap zone.
        Only ``current_floor`` changes; player position stays the same.
        Camera snaps instantly to prevent jarring jumps.
        """
        px, py = self.player.rect.center
        for staircase in self.school_map.staircases:
            new_floor = staircase.check(px, py, self.current_floor)
            if new_floor is not None:
                if new_floor == FLOOR_ROOFTOP and not getattr(self, '_rooftop_unlocked', False):
                    if getattr(self, '_rooftop_block_timer', 0) <= 0:
                        self.ui.show_notification("You must talk to Axel Knight to access the rooftop.", NOTIF_ERROR)
                        self._rooftop_block_timer = 2.0
                    self.player.rect.centery = staircase.transition_y + 12
                    return
                if new_floor == FLOOR_BASEMENT and not self._is_basement_unlocked():
                    if getattr(self, '_basement_block_timer', 0) <= 0:
                        self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                        self._basement_block_timer = 2.0
                    self.player.rect.centery = staircase.transition_y - 12
                    return
                self.current_floor = new_floor
                floor = self.school_map.get_floor(new_floor)
                if floor:
                    self._floor_w = floor.width
                    self._floor_h = floor.height
                    self.camera.set_bounds(floor.width, floor.height)
                    # Snap camera immediately to player
                    self.camera.update(self.player)
                # Advance zone objectives
                from settings import ZONE_TO_FLOOR
                for old_zid, (fid, _, _) in ZONE_TO_FLOOR.items():
                    if fid == new_floor:
                        self.mission_manager.advance_objective_event(
                            "go_to_zone", str(old_zid))
                        break
                return

    def _enforce_cafeteria_access(self, floor, previous_rect, dt):
        """Prevent player from being in the cafeteria during non-lunch/break hours."""
        if self._cafeteria_block_timer > 0:
            self._cafeteria_block_timer -= dt
            
        if not floor or self.current_floor != FLOOR_1F:
            return

        # Check for bump against the locked cafeteria door
        for door in floor.doors:
            if getattr(door, "id", "") == "door_cafeteria" and door.locked:
                # Inflate player rect slightly to detect "bumping" against the door
                if self.player.rect.inflate(6, 6).colliderect(door.rect):
                    if self._cafeteria_block_timer <= 0:
                        self.ui.show_notification("Access prohibited, available from Break Time until the end of the day", NOTIF_WARNING)
                        self._cafeteria_block_timer = 2.0
                    return # Already showed notification

        room = floor.get_room_at(self.player.rect.centerx, self.player.rect.centery)
        prev_room = floor.get_room_at(previous_rect.centerx, previous_rect.centery)
        if room and room.id == "f1_cafeteria":
            if not self._is_cafeteria_open():
                if prev_room and prev_room.id == "f1_cafeteria":
                    return # Already inside, don't push out or show message
                # Push player back
                self.player.rect.update(previous_rect)
                if self._cafeteria_block_timer <= 0:
                    self.ui.show_notification("Access prohibited, available from Break Time until the end of the day", NOTIF_WARNING)
                    self._cafeteria_block_timer = 2.0
                return

    def _is_tech_lab_unlocked(self) -> bool:
        if getattr(self, "_tech_lab_unlocked", False):
            return True
        txt = getattr(self, "_current_main_mission_text", "")
        if not txt:
            return False
        if "Mission 4:" in txt or self.day_number >= 2:
            self._tech_lab_unlocked = True
            return True
        return False

    def _enforce_tech_lab_access(self, floor, previous_rect, dt):
        if not hasattr(self, '_tech_lab_block_timer'):
            self._tech_lab_block_timer = 0.0
        if self._tech_lab_block_timer > 0:
            self._tech_lab_block_timer -= dt

        if not floor or self.current_floor != FLOOR_1F or self._is_tech_lab_unlocked():
            return

        room = floor.get_room_at(self.player.rect.centerx, self.player.rect.centery)
        if room and room.id == "f1_computer_lab":
            self.player.rect.update(previous_rect)
            if self._tech_lab_block_timer <= 0:
                self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                self._tech_lab_block_timer = 2.0

    def _is_library_mission_unlocked(self) -> bool:
        if getattr(self, "_library_unlocked", False):
            return True
        txt = getattr(self, "_current_main_mission_text", "")
        if not txt:
            return False
        if "Mission 3:" in txt or "Day 1 all missions completed" in txt or self.day_number > 1:
            self._library_unlocked = True
            return True
        return False

    def _enforce_library_access(self, floor, previous_rect, dt):
        if self._library_block_timer > 0:
            self._library_block_timer -= dt

        if not floor or self.current_floor != FLOOR_1F or self._is_library_mission_unlocked():
            return

        room = floor.get_room_at(self.player.rect.centerx, self.player.rect.centery)
        if room and room.id == "f1_library":
            self.player.rect.update(previous_rect)
            if self._library_block_timer <= 0:
                self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                self._library_block_timer = 2.0

    def _enforce_bathroom_access(self, floor, previous_rect):
        """Prevent characters from entering the opposite-gender bathroom."""
        if not floor or self.current_floor != FLOOR_1F:
            return

        room = floor.get_room_at(
            self.player.rect.centerx,
            self.player.rect.centery,
        )
        if not room:
            return

        allowed, message = self._is_bathroom_access_allowed(room.id, self.player.character)

        if not allowed:
            self.player.rect.update(previous_rect)
            if (self._bathroom_block_timer <= 0.0 or
                    self._bathroom_blocked_room != room.id):
                self.ui.show_notification(message, NOTIF_WARNING)
                self._bathroom_block_timer = 1.0
                self._bathroom_blocked_room = room.id

    def _is_bathroom_access_allowed(self, room_id: str, character: Character) -> tuple[bool, str]:
        if room_id == "f1_men_bath":
            allowed = character == Character.AIDEN
            return allowed, "You can't enter. That's the men's bathroom."
        if room_id == "f1_women_bath":
            allowed = character == Character.LENA
            return allowed, "You can't enter. That's the women's bathroom."
        return True, ""

    def _try_teleport_to(self, floor_id: int, tx: int, ty: int) -> bool:
        if floor_id == FLOOR_PINGPONG_INTERIOR:
            if not self._is_pingpong_unlocked():
                self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                return False
        if floor_id == FLOOR_COLISEUM_INTERIOR:
            if not self._is_coliseum_unlocked():
                self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                return False
        if floor_id == FLOOR_ROOFTOP and not getattr(self, '_rooftop_unlocked', False):
            if getattr(self, '_rooftop_block_timer', 0) <= 0:
                self.ui.show_notification("You must talk to Axel Knight to access the rooftop.", NOTIF_ERROR)
                self._rooftop_block_timer = 2.0
            return False
        if floor_id == FLOOR_BASEMENT and not self._is_basement_unlocked():
            if getattr(self, '_basement_block_timer', 0) <= 0:
                self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                self._basement_block_timer = 2.0
            return False

        floor = self.school_map.get_floor(floor_id)
        if not floor:
            return False

        room = floor.get_room_at(tx, ty)
        if floor_id == FLOOR_CAMPUS and room:
            if room.id == "c_tennis":
                if not self._is_pingpong_unlocked():
                    self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                    return False
                self._go_to_floor(FLOOR_PINGPONG_INTERIOR, 650, 900)
                return True
            if room.id == "c_coliseum":
                if not self._is_coliseum_unlocked():
                    self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                    return False
                self._go_to_floor(FLOOR_COLISEUM_INTERIOR, 900, 980)
                return True
        if room:
            allowed_bath, msg_bath = self._is_bathroom_access_allowed(room.id, self.player.character)
            if not allowed_bath:
                self.ui.show_notification(msg_bath, NOTIF_WARNING)
                return False
            
            if room.id == "f1_cafeteria" and not self._is_cafeteria_open():
                self.ui.show_notification("Access prohibited, available from Break Time until the end of the day", NOTIF_WARNING)
                return False
            if room.id == "f1_computer_lab" and not self._is_tech_lab_unlocked():
                self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                return False
            if room.id == "f1_library" and not self._is_library_mission_unlocked():
                self.ui.show_notification("This location cannot be accessed until the corresponding mission is unlocked.", NOTIF_ERROR)
                return False

        self._go_to_floor(floor_id, tx, ty)
        return True

    def _go_to_floor(self, floor_id: int, sx: int, sy: int):
        """Transition the player to a different floor (portal-type)."""
        self.current_floor = floor_id
        floor = self.school_map.get_floor(floor_id)
        if floor:
            self._floor_w = floor.width
            self._floor_h = floor.height
            self.camera.set_bounds(floor.width, floor.height)
            self.player.rect.centerx = sx
            self.player.rect.centery = sy

            # Teleport remote player model in coop to prevent them from staying on the previous floor
            if self.multiplayer and self.remote_player:
                self.remote_player.rect.centerx = sx + 40
                self.remote_player.rect.centery = sy
                self.remote_player.current_floor = floor_id

            # Push out of walls to be safe if teleporting inside one
            for w in floor.walls:
                if self.player.rect.colliderect(w):
                    dl = self.player.rect.right - w.left
                    dr = w.right - self.player.rect.left
                    dt = self.player.rect.bottom - w.top
                    db = w.bottom - self.player.rect.top
                    m = min(dl, dr, dt, db)
                    if m == dl:
                        self.player.rect.right = w.left - 2
                    elif m == dr:
                        self.player.rect.left = w.right + 2
                    elif m == dt:
                        self.player.rect.bottom = w.top - 2
                    elif m == db:
                        self.player.rect.top = w.bottom + 2

            self.camera.update(self.player)  # snap camera
            # Advance "go_to_zone" objectives (map old zone IDs)
            for old_zid, (fid, _, _) in ZONE_TO_FLOOR.items():
                if fid == floor_id:
                    self.mission_manager.advance_objective_event(
                        "go_to_zone", str(old_zid))
                    break

    # ──────────────────────────────────────────────────────────
    #  UPDATE
    # ──────────────────────────────────────────────────────────

    def _update(self, dt: float):
        # Rooftop entry populars management
        from settings import FLOOR_ROOFTOP
        if self.current_floor == FLOOR_ROOFTOP:
            if not getattr(self, '_rooftop_populars_teleported', False):
                self._place_populars_on_rooftop()
                self._rooftop_populars_teleported = True
        else:
            if getattr(self, '_rooftop_populars_teleported', False):
                self._reset_populars_from_rooftop()
                self._rooftop_populars_teleported = False

        self._enforce_sibling_safe_location()
        if self.day_number == 2:
            floor1 = self.school_map.get_floor(FLOOR_1F)
            if floor1:
                room = floor1.rooms.get("f1_computer_lab")
                if room:
                    self._clear_tech_lab_for_ava(room)

        ambient_music_allowed = self.state not in (GameState.PINGPONG, GameState.BASKETBALL)

        if not ambient_music_allowed:
            self._normal_gameplay_music_playing = False
            self._pasillo_playing = False
        elif self.rooftop_party.is_party_active_on_floor(self.current_floor, self.day_number):
            if not getattr(self, '_rooftop_party_music_playing', False):
                try:
                    if pygame.mixer.get_init():
                        party_track = os.path.join(
                            "assets", "sounds",
                            "Hugel, SOLTO (FR) - Jamaican (Bam Bam) (Original Mix).mp3",
                        )
                        pygame.mixer.music.load(party_track)
                        pygame.mixer.music.set_volume(0.25)
                        pygame.mixer.music.play(-1)
                        self._rooftop_party_music_playing = True
                        self._basement_music_playing = False
                        self._pasillo_playing = False
                        self._normal_gameplay_music_playing = False
                except Exception:
                    pass
        elif self.current_floor == FLOOR_BASEMENT and self._is_final_showdown_active():
            self._normal_gameplay_music_playing = False
            self._pasillo_playing = False
        else:
            if not getattr(self, '_normal_gameplay_music_playing', False):
                try:
                    if pygame.mixer.get_init():
                        path = os.path.join("assets", "sounds", "pokemon and chill.mp3")
                        pygame.mixer.music.load(path)
                        pygame.mixer.music.set_volume(0.25)
                        pygame.mixer.music.play(-1)
                        self._normal_gameplay_music_playing = True
                        self._pasillo_playing = True
                        self._basement_music_playing = False
                        self._rooftop_party_music_playing = False
                except Exception:
                    pass

        # Fountain ambient audio logic for Campus (FLOOR_CAMPUS) near (2000, 2225)
        px, py = self.player.rect.center
        dist = math.hypot(px - 2000, py - 2225)
        if self.current_floor == FLOOR_CAMPUS and dist <= 1400:
            if not getattr(self, '_fountain_sound', None):
                try:
                    if pygame.mixer.get_init():
                        self._fountain_sound = pygame.mixer.Sound("sound/fuente.mp3")
                except Exception:
                    pass
            if getattr(self, '_fountain_sound', None):
                if not getattr(self, '_fountain_playing', False):
                    self._fountain_sound.play(-1)
                    self._fountain_playing = True
                vol = max(0.05, min(0.6, 0.6 * (1.0 - (dist / 1400.0))))
                self._fountain_sound.set_volume(vol)
        else:
            if getattr(self, '_fountain_playing', False) and getattr(self, '_fountain_sound', None):
                try:
                    self._fountain_sound.stop()
                    self._fountain_playing = False
                except Exception:
                    pass

        if self.state != GameState.INTRO_CINEMATIC:
            self.phone.update(dt)
            pt = self.phone.consume_pending_teleport()
            if pt:
                self._try_teleport_to(pt[0], pt[1], pt[2])
        # Always tick UI (notifications) and social UI
        self.ui.update(dt)
        self.social_ui.update(dt)

        if getattr(self, "_oscar_win_dialogue_active", False):
            if self.multiplayer and self.network:
                self._sync_network(dt)
            return
        
        # Check if the player viewed the mention in XSchool-Net
        if getattr(self, "_current_main_mission_text", None) == "Mission 2: Open Social app and click Oscar's post.":
            if getattr(self, "phone", None) and self.phone.is_visible and self.phone.current_app.value == "social":
                if getattr(self.phone, "active_post", None):
                    if self.phone.active_post.author_npc_id == "npc_oscar":
                        if self.multiplayer:
                            if self.is_host:
                                self._host_viewed_oscar_post = True
                            else:
                                self._client_viewed_oscar_post = True
                        else:
                            self._current_main_mission_text = "Mission 2: Go to the Ping Pong court to play against Oscar Jimenez."

        if self.multiplayer and getattr(self, "_current_main_mission_text", None) == "Mission 2: Open Social app and click Oscar's post.":
            if self.is_host:
                if self._host_viewed_oscar_post and self._remote_client_viewed_oscar_post:
                    self._current_main_mission_text = "Mission 2: Go to the Ping Pong court to play against Oscar Jimenez."

        if getattr(self, 'sibling_npc', None):
            col = (255, 180, 220) if self.character == Character.AIDEN else (100, 150, 255)
            self.world_map.set_marker(self.sibling_npc.name, self.sibling_npc.current_floor, self.sibling_npc.rect.centerx, self.sibling_npc.rect.centery, color=col)

        # Oscar marker logic for Mission 2
        mission_text = getattr(self, "_current_main_mission_text", None)
        if mission_text == "Mission 2: Go to the Ping Pong court to play against Oscar Jimenez.":
            # Floor 6 is Ping Pong Court Interior, Floor 0 is Campus
            self.world_map.set_marker("Oscar Jimenez", 6, 650, 450, color=(255, 50, 50))
            self.world_map.set_marker("Oscar Jimenez ", 0, 3490, 2475, color=(255, 50, 50)) # Space added for unique dict key
        elif "Oscar Jimenez" in getattr(self.world_map, "_markers", {}):
            self.world_map.clear_marker("Oscar Jimenez")
            self.world_map.clear_marker("Oscar Jimenez ")
            
        if self._bathroom_block_timer > 0:
            self._bathroom_block_timer = max(0.0, self._bathroom_block_timer - dt)
            if self._bathroom_block_timer == 0.0:
                self._bathroom_blocked_room = None

        # ── Day transition overlay (fullscreen "Day X") ──
        if self._day_transition_active:
            self._day_transition_timer -= dt
            if self._day_transition_timer <= 0:
                self._day_transition_active = False
                self._start_next_day()
            if self.multiplayer and self.network:
                self._sync_network(dt)
            return  # freeze everything else

        # ── Car departure cinematic ──
        if self._car_departure_active:
            self._update_car_departure(dt)
            if self.multiplayer and self.network:
                self._sync_network(dt)
            return  # freeze normal gameplay

        if not hasattr(self, '_last_known_level'):
            self._last_known_level = self.player.level

        if not hasattr(self, '_last_mission_text'):
            self._last_mission_text = getattr(self, '_current_main_mission_text', None)
        elif getattr(self, '_current_main_mission_text', None) != self._last_mission_text:
            old_text = self._last_mission_text
            new_text = getattr(self, '_current_main_mission_text', None)
            self._last_mission_text = new_text
            if old_text is not None and new_text is not None:
                if not (self.multiplayer and not self.is_host):
                    self.player.level += 1
                    from settings import SKILL_POINT_PER_LEVEL
                    self.player.skill_points += SKILL_POINT_PER_LEVEL
                    self.player.money += 10
                    if hasattr(self.ui, 'trigger_level_up'):
                        self.ui.trigger_level_up(10)
                    self._last_known_level = self.player.level

        if self.player.level > self._last_known_level:
            self._last_known_level = self.player.level
            if hasattr(self.ui, 'trigger_level_up'):
                self.ui.trigger_level_up(10)
        if self.state not in (GameState.PLAYING, GameState.INTRO_CINEMATIC):
            if hasattr(self.player, 'stop_audio'):
                self.player.stop_audio()

        if self.state == GameState.INTRO_CINEMATIC:
            self._update_cinematic(dt)
            if self.multiplayer and self.network:
                self._sync_network(dt)

            # NPCs keep moving normally during cinematic
            floor = self.school_map.get_floor(self.current_floor)
            npc_walls = list(floor.walls) if floor else []
            if self._player_spawned:
                npc_walls.append(self.player.rect)
            if self.current_floor == FLOOR_CAMPUS:
                npc_walls.extend(self._get_parked_vehicle_rects())
            if floor:
                for door in floor.doors:
                    if door.locked:
                        npc_walls.append(door.rect)
            # Block NPCs (except Noah) from staircases during cinematic
            stair_restricted = [
                "f1_stairs_2f", "f1_basement_stairs",
                "f2_stairs_1f", "f2_stairs_rooftop", "bs_stairs_1f",
            ]
            self.npc_manager.update_on_floor(
                dt, self.current_floor, floor, npc_walls,
                classrooms_restricted=True,
                restricted_rooms=stair_restricted,
                is_visible=self._is_npc_on_camera)

            # Camera: centre on Entrance Roundabout before player spawns
            if not self._player_spawned:
                class _FakeTarget:
                    rect = pygame.Rect(2000 - 10, 2700 - 10, 20, 20)
                self.camera.update(_FakeTarget())
            elif self._cine_phase in ("guide", "mission"):
                # Allow player movement during the guide and mission phases
                keys = pygame.key.get_pressed()
                p_walls = list(floor.walls) if floor else []
                npcs_on_floor = self.npc_manager.get_npcs_on_floor(self.current_floor)
                for npc in npcs_on_floor:
                    p_walls.append(npc.rect)
                if floor:
                    for door in floor.doors:
                        if door.locked:
                            p_walls.append(door.rect)
                in_main_building = self.current_floor in (FLOOR_1F, FLOOR_2F)
                speed_mult = 1.5 if in_main_building else 1.0
                self.player.update(keys, p_walls, dt, speed_multiplier=speed_mult)
                # Only allow seamless stairs once Noah has reached the switch point
                if self._cinematic_stairs_unlocked:
                    old_floor = self.current_floor
                    self._check_seamless_stairs()
                    if self.current_floor != old_floor:
                        # Player just transitioned — move Noah to the same floor
                        noah = self.npc_manager.get_npc_by_id("npc_noah_carter")
                        if noah:
                            noah.current_floor = self.current_floor
                self.camera.update(self.player)
            else:
                self.camera.update(self.player)
        elif self.state == GameState.PLAYING:
            self._update_playing(dt)
        elif self.state == GameState.COMBAT:
            result = self.combat_system.update(dt)
            # Ensure player dash is processed while in combat state
            if getattr(self.player, "_dashing", False):
                floor = self.school_map.get_floor(self.current_floor)
                walls = list(floor.walls) if floor else []
                npcs_on_floor = self.npc_manager.get_npcs_on_floor(self.current_floor)
                for npc in npcs_on_floor:
                    walls.append(npc.rect)
                # Update dash movement/trail even when combat owns the main loop
                self.player._update_dash(walls)

            if result is not None:
                self.state = GameState.PLAYING
                if result == "win":
                    self.player.gain_xp(25)
                    self.ui.show_notification("Combat won! +25 XP", NOTIF_SUCCESS)
                elif result == "lose":
                    self.ui.show_notification("You were knocked out…", NOTIF_ERROR)
                    self.player.health = self.player.max_health // 2
        elif self.state == GameState.PINGPONG:
            # Check coop exit consensus voting
            if self.multiplayer and self._pingpong_exit_voted and self._remote_pingpong_exit_voted:
                self.pingpong.finished = False
                self.pingpong.reset()
                self._spectating_pingpong = False
                # Do NOT reset won/exit flags here; wait for PLAYING state sync to avoid auto-trigger loops
                self.state = GameState.PLAYING
                try:
                    if pygame.mixer.get_init():
                        pygame.mixer.music.stop()
                except Exception:
                    pass
                self._pending_pingpong_result = None
                if self.is_host:
                    self._begin_oscar_win_dialogue()

            # Client fallback: transition if Host transitions to PLAYING
            if self.multiplayer and not self.is_host and getattr(self, "_remote_game_state", None) == GameState.PLAYING.value:
                self.pingpong.finished = False
                self.pingpong.reset()
                self._spectating_pingpong = False
                # Do NOT reset won/exit flags here; wait for PLAYING state sync to avoid auto-trigger loops
                self.state = GameState.PLAYING
                try:
                    if pygame.mixer.get_init():
                        pygame.mixer.music.stop()
                except Exception:
                    pass
                self._pending_pingpong_result = None

            # Symmetrical Waiting/Dismiss screen updates
            if self.multiplayer and self._pingpong_match_won:
                if self._remote_pingpong_match_won:
                    # Both have won! Show exit instruction
                    self.pingpong.end_message = "All Matches Won!\nPress SPACE/A to Exit"
                else:
                    # Waiting for the other player
                    self.pingpong.end_message = "Match Won!\nWaiting for Ally..."

                # Handle cheers while waiting
                keys = pygame.key.get_pressed()
                if not hasattr(self, "_cheer_cooldown"):
                    self._cheer_cooldown = 0.0
                if self._cheer_cooldown > 0:
                    self._cheer_cooldown -= dt
                
                cheer_pressed = False
                controller = get_controller()
                if self._cheer_cooldown <= 0:
                    if keys[pygame.K_SPACE] or keys[pygame.K_RETURN] or keys[pygame.K_c]:
                        cheer_pressed = True
                    elif controller and controller.connected and (controller.is_confirm_pressed() or controller.get_button_state("x")):
                        cheer_pressed = True
                
                if cheer_pressed:
                    self._cheer_cooldown = 0.4
                    import random
                    remote_name = "LENA"
                    if self.remote_player and "lena" in self.remote_player.character.value.lower():
                        remote_name = "LENA"
                    elif self.remote_player and "aiden" in self.remote_player.character.value.lower():
                        remote_name = "AIDEN"
                    cheers = [
                        f"✨ GO {remote_name}! ✨", f"❤️ KEEP IT UP! ❤️", f"🔥 UNSTOPPABLE! 🔥",
                        f"⚡ SHOT! ⚡", f"🌟 VAMOS! 🌟", f"🎉 YOU GOT THIS! 🎉"
                    ]
                    txt = random.choice(cheers)
                    self.pingpong.spawn_cheer(txt, is_local=True)
                    self._pending_pp_cheer = txt

            else:
                result = self.pingpong.update(dt)
                # 'settings' from the pause menu — exit minigame cleanly for now
                if result == 'settings':
                    self.pingpong.finished = False
                    self.pingpong.reset()
                    self.state = GameState.PLAYING
                    try:
                        if pygame.mixer.get_init():
                            pygame.mixer.music.stop()
                    except Exception:
                        pass
                    self.ui.show_notification("Settings not yet available in-game.", NOTIF_INFO)
                # When a match result arrives, show end-screen and apply reputation changes
                elif result is not None and not getattr(self.pingpong, 'waiting_for_dismiss', False):
                    if result == "win":
                        if self.multiplayer:
                            self._pingpong_match_won = True
                            if self._remote_pingpong_match_won:
                                self.pingpong.end_message = "All Matches Won!\nPress SPACE/A to Exit"
                            else:
                                self.pingpong.end_message = "Match Won!\nWaiting for Ally..."
                            self._pending_pingpong_result = "win"
                        else:
                            self.reputation.reputation_score = min(100, self.reputation.reputation_score + 20)
                            self.pingpong.end_message = "Win Match\n+20 Reputation"
                            self._pending_pingpong_result = "win"
                    elif result == "lose":
                        if self.multiplayer:
                            self._pending_pingpong_result = "lose"
                            self.pingpong.end_message = "Match Lost!\nPress SPACE/A to Retry"
                        else:
                            self._pending_pingpong_result = "lose"
                            if self.reputation.reputation_score > 0:
                                self.reputation.reputation_score = max(0, self.reputation.reputation_score - 10)
                                self.pingpong.end_message = "Lose Match\n-10 Reputation"
                            else:
                                self.pingpong.end_message = "Lose Match"
                    self.pingpong.waiting_for_dismiss = True

        elif self.state == GameState.BASKETBALL:
            # Fix camera to the center of the court (476 + 424, 258 + 347)
            class _CourtTarget:
                def __init__(self):
                    self.rect = pygame.Rect(0, 0, 0, 0)
                    self.rect.centerx = 900
                    self.rect.centery = 605
            self.camera.update(_CourtTarget())
            
            # Apply screen shake to camera offset in basketball mode
            if hasattr(self, "basketball") and getattr(self.basketball, "shake_timer", 0.0) > 0.0:
                intensity = getattr(self.basketball, "shake_intensity", 5)
                import random
                self.camera.offset.x += random.randint(-intensity, intensity)
                self.camera.offset.y += random.randint(-intensity, intensity)
            
            result = self.basketball.update(dt)
            if getattr(self.basketball, 'finished', False):
                self.basketball.finished = False
                player_won = self.basketball.player_score > self.basketball.opp_score
                if hasattr(self.basketball, 'floor') and self.basketball.floor:
                    self.basketball.floor.hide_hoops = False
                self.basketball.reset()
                self._stop_basketball_music()
                self.state = GameState.PLAYING
                if player_won:
                    self.reputation.reputation_score = min(100, self.reputation.reputation_score + 20)
                    if not (self.multiplayer and not self.is_host):
                        self.player.level += 1
                        from settings import SKILL_POINT_PER_LEVEL
                        self.player.skill_points += SKILL_POINT_PER_LEVEL
                        self.player.money += (self.player.level - 1) * 10
                        if hasattr(self.ui, 'trigger_level_up'):
                            self.ui.trigger_level_up()
                        self._last_known_level = self.player.level
                    self._begin_marcus_win_dialogue()
                else:
                    self.reputation.reputation_score = max(0, self.reputation.reputation_score - 10)
            # When player dismisses the end screen, finish the minigame and return to playing

        if self.state == GameState.HACKING:
            result = self.hacking_game.update(dt)
            if result is not None:
                self.state = GameState.PLAYING
                if result == "success":
                    self.player.gain_xp(30)
                    self.ui.show_notification("Hack successful! +30 XP", NOTIF_SUCCESS)
                    self.reputation.record_cyberbully_intercept()
                    # Advance hack objectives
                    tid = self.hacking_game.target_info.get("id", "")
                    self.mission_manager.advance_objective_event("hack_target", tid)
                else:
                    self.ui.show_notification("Hack failed!", NOTIF_ERROR)
        elif self.state == GameState.DIALOGUE:
            result = self.dialogue_system.update()
            if result is not None:
                self.state = GameState.PLAYING
                self._apply_dialogue_result(result)
        elif self.state == GameState.SOCIAL_INTERACTION:
            # Update social dialogue manager
            self.social_dialogue_manager.update(dt)
            # Check if interaction is finished
            if self.social_dialogue_manager.get_state().name == "IDLE":
                self.state = GameState.PLAYING
        elif self.state == GameState.TRADING:
            result = self.trade_system.update()
            if result is not None:
                self.state = GameState.PLAYING

        if self.state in (GameState.PLAYING, GameState.COMBAT, GameState.DIALOGUE, GameState.SOCIAL_INTERACTION, GameState.PINGPONG, GameState.BASKETBALL):
            self._tick_time(dt)
            self._update_class_schedule()

        if getattr(self.pingpong, 'finished', False):
            self.pingpong.finished = False

            # If in coop and they lost, retry immediately!
            if self.multiplayer and getattr(self, "_pending_pingpong_result", None) == "lose":
                self.pingpong.reset()
                self.pingpong.show_menu = True
                self.pingpong.player_score = 0
                self.pingpong.opponent_score = 0
                self.pingpong.active = True
                self.pingpong.finished = False
                self.pingpong.waiting_for_dismiss = False
                self._pending_pingpong_result = None
            # If in coop and they won:
            elif self.multiplayer and getattr(self, "_pending_pingpong_result", None) == "win":
                if self._remote_pingpong_match_won:
                    # Both have won! Vote to exit.
                    self._pingpong_exit_voted = True
                    self.pingpong.end_message = "Waiting for Ally..."
                    self.pingpong.waiting_for_dismiss = True
                    self.pingpong.finished = False
                else:
                    # Just keep waiting! Do not allow exit yet.
                    self.pingpong.waiting_for_dismiss = True
                    self.pingpong.end_message = "Match Won!\nWaiting for Ally..."
                    self.pingpong.finished = False
            else:
                # Single-player exit or default clean up
                pingpong_result = getattr(self, "_pending_pingpong_result", None)
                self.pingpong.reset()
                self._spectating_pingpong = False
                self._pingpong_match_won = False
                self._remote_pingpong_match_won = False
                self._pingpong_exit_voted = False
                self._remote_pingpong_exit_voted = False
                self.state = GameState.PLAYING
                try:
                    if pygame.mixer.get_init():
                        pygame.mixer.music.stop()
                except Exception:
                    pass
                self._pending_pingpong_result = None
                if pingpong_result == "win":
                    self._begin_oscar_win_dialogue()

        if getattr(self.basketball, 'finished', False):
            self.basketball.finished = False
            self.basketball.reset()
            self._stop_basketball_music()
            self.state = GameState.PLAYING

        # Reset pingpong match won/exit flags in PLAYING state once remote state is also PLAYING
        if self.multiplayer and self.state == GameState.PLAYING and (self._pingpong_match_won or self._pingpong_exit_voted):
            if getattr(self, "_remote_game_state", None) == GameState.PLAYING.value:
                self._pingpong_match_won = False
                self._remote_pingpong_match_won = False
                self._pingpong_exit_voted = False
                self._remote_pingpong_exit_voted = False

        # Network sync
        if self.multiplayer and self.network:
            self._sync_network(dt)

    def _update_playing(self, dt: float):
        if getattr(self, "_final_reveal_active", False):
            self._update_final_reveal(dt)
            return
        if getattr(self, "_final_office_active", False):
            self._update_final_office_scene(dt)
            return

        # ── Fast Forward Detection ──
        mouse_pos = pygame.mouse.get_pos()
        mouse_ff = (
            pygame.mouse.get_pressed()[0]
            and getattr(self.ui, 'ff_button_rect', None)
            and self.ui.ff_button_rect.collidepoint(mouse_pos)
        )
        is_ff = mouse_ff or self._ff_controller_active
        
        # Apply time scale (5x speed for FF)
        current_dt = dt * (5.0 if is_ff else 1.0)
        
        # Update clock with fast-forward dt
        self._tick_time(current_dt)
        self._update_class_schedule()
        
        # Update rooftop party for Day 4 event
        self.rooftop_party.update(dt, self.day_number)

        # Day 4 party cinematic state machine
        if getattr(self, "_party_exit_cinematic_active", False):
            self._update_party_exit_cinematic(dt)

        # Ava phone proximity check + countdown
        if self.current_floor == FLOOR_ROOFTOP and getattr(self, "_ava_phone_on_chair", False):
            px, py = self.player.rect.center
            cx, cy = self._ava_phone_chair_pos
            dist = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            self._ava_phone_prompt_active = dist < 80 and not self._ava_phone_spying
        else:
            self._ava_phone_prompt_active = False

        if getattr(self, "_ava_phone_timer_active", False):
            self._update_ava_phone_timer(dt)
        if not (self.multiplayer and not self.is_host):
            self._update_final_showdown(dt)
        if getattr(self, "_final_reveal_active", False) or getattr(self, "_final_office_active", False):
            return
        
        # Transition cooldown
        if self._transition_cooldown > 0:
            self._transition_cooldown -= dt
        if self._entry_prompt_cooldown > 0:
            self._entry_prompt_cooldown -= dt

        # Movement
        keys  = pygame.key.get_pressed()
        floor = self.school_map.get_floor(self.current_floor)
        walls = list(floor.walls) if floor else []
        
        # NPCs are NOT added as walls for the player — the player pushes them instead.
        # Exception: Gordon Ramsay is solid (collision).
        npcs_on_floor = self.npc_manager.get_npcs_on_floor(self.current_floor)
        for npc in npcs_on_floor:
            if npc.id == "npc_gordon":
                walls.append(npc.rect)
                continue
            if npc.id == "npc_axel_knight":
                if not getattr(self, '_rooftop_unlocked', False):
                    walls.append(npc.rect)
                continue
            if npc.id.startswith("npc_oscar_obs"):
                walls.append(npc.rect)
                continue
            
        previous_rect = self.player.rect.copy()
        
        # Add locked doors to collision walls
        if floor:
            if self._is_smile_club_room_locked():
                self._set_smile_club_room_locked(True)
            for door in floor.doors:
                if door.locked:
                    walls.append(door.rect)
        
        # Co-op: add remote player as a solid wall if they are on the same floor
        if self.multiplayer and getattr(self, "remote_player", None):
            if self.remote_player.current_floor == self.current_floor:
                walls.append(self.remote_player.rect)
                
                # If they are already overlapping, apply a small repulsion to prevent getting stuck
                if self.player.rect.colliderect(self.remote_player.rect):
                    pdx = self.player.rect.centerx - self.remote_player.rect.centerx
                    pdy = self.player.rect.centery - self.remote_player.rect.centery
                    if abs(pdx) >= abs(pdy):
                        if pdx >= 0: self.player.rect.x += 1
                        else: self.player.rect.x -= 1
                    else:
                        if pdy >= 0: self.player.rect.y += 1
                        else: self.player.rect.y -= 1

        # Parked car is solid on campus
        if self.current_floor == FLOOR_CAMPUS:
            walls.extend(self._get_parked_vehicle_rects())
        
        # Rooftop party collisions
        if self.current_floor == FLOOR_ROOFTOP and self.day_number >= 3:
            walls.extend(self.rooftop_party.get_collisions())
                    
        # Apply floor-specific speed boost (50% faster in main building) and faster trail decay
        in_main_building = self.current_floor in (FLOOR_1F, FLOOR_2F)
        speed_mult = 1.5 if in_main_building else 1.0
        decay = 2 if in_main_building else 1
        
        # We pass the original dt to the player so they don't speed up during fast-forward,
        # but we use speed_mult for the floor-based boost.
        if not self._car_panel_active:
            self.player.update(keys, walls, dt, trail_decay=decay, speed_multiplier=speed_mult)
        self._enforce_bathroom_access(floor, previous_rect)
        self._enforce_cafeteria_access(floor, previous_rect, dt)
        self._enforce_tech_lab_access(floor, previous_rect, dt)
        self._enforce_library_access(floor, previous_rect, dt)
        if (not (self.multiplayer and not self.is_host)
                and self.current_floor == FLOOR_BASEMENT
                and getattr(self, "_final_reveal_finished", False)
                and not getattr(self, "_final_office_started", False)):
            self._keep_player_in_smile_room()
        if getattr(self, '_basement_block_timer', 0) > 0:
            self._basement_block_timer -= dt
        if getattr(self, '_rooftop_block_timer', 0) > 0:
            self._rooftop_block_timer -= dt

        # ── Player Attacks NPCs ──
        if getattr(self.player, 'is_attacking', False):
            hitbox = self.player.get_attack_hitbox()
            if hitbox:
                for _npc in npcs_on_floor:
                    if _npc.health <= 0 or _npc.id in ("npc_aiden", "npc_lena"):
                        continue
                    if _npc.id not in getattr(self.player, '_hit_npcs', set()):
                        if hitbox.colliderect(_npc.rect):
                            self.player._hit_npcs.add(_npc.id)
                            _npc.health -= self.player.attack_damage
                            self.ui.show_notification(f"Hit {_npc.name} for {self.player.attack_damage} dmg!", NOTIF_SUCCESS)
                            if _npc.health <= 0:
                                _npc.health = 0
                                _npc.knockout_timer = 120.0
                                _npc.is_hostile = False
                                self.mission_manager.advance_objective_event("win_combat", _npc.id)
                                self.reputation.modify(_npc.group.value, -5)
                                self.ui.show_notification(f"Knocked out {_npc.name}! -5 reputation with {_npc.group.value.title()}", NOTIF_ERROR)
                            else:
                                _npc.is_hostile = True

        # ── Hostile NPCs chase & attack ──
        import math
        for _npc in npcs_on_floor:
            if getattr(_npc, 'is_hostile', False) and _npc.health > 0:
                dist = math.hypot(_npc.rect.centerx - self.player.rect.centerx, _npc.rect.centery - self.player.rect.centery)
                if _npc.id in getattr(self, "_final_smile_ids", ()) and getattr(self, "_final_reveal_finished", False):
                    _npc.is_hostile = True
                    self._keep_npc_in_smile_room(_npc)
                    _npc.target_pos = self.player.rect.center
                    _npc.ai_enabled = True
                elif dist > 400:
                    _npc.is_hostile = False
                    _npc.target_pos = None
                else:
                    _npc.target_pos = self.player.rect.center
                    _npc.ai_enabled = True
                    if dist < 60:
                        if getattr(_npc, 'attack_cooldown', 0) <= 0:
                            dmg = getattr(_npc, 'target_damage', 8)
                            self.player.take_damage(dmg)
                            _npc.attack_cooldown = 1.0
                            _npc.attack_timer = 0.2
                            _npc.state = "attack"
                            self.ui.show_notification(f"{_npc.name} attacked you!", NOTIF_ERROR)
                            controller = get_controller()
                            if controller.connected:
                                controller.rumble(0.5, 0.5, 200)

        # ── Player pushes NPCs on contact ──────────────────────────────────
        self._check_final_fight_complete()
        if getattr(self, "_final_office_active", False):
            return
        # Stationary NPCs = heavy resistance (1px nudge), moving NPCs = light push
        from settings import NPC_SIZE
        floor1_ref = self.school_map.get_floor(FLOOR_1F)
        for _npc in npcs_on_floor:
            if _npc.id in ("npc_gordon", "npc_axel_knight"):
                continue
            if _npc.id.startswith("npc_oscar_obs"):
                continue
            # Don't push NPCs that are seated in the cafeteria
            if getattr(_npc, 'stop_at_target', False) is False and _npc.ai_enabled is False:
                # NPC has arrived at target and stopped — treat as seated/immovable
                if floor1_ref:
                    caf_room = floor1_ref.rooms.get("f1_cafeteria")
                    if caf_room and caf_room.rect.collidepoint(_npc.rect.centerx, _npc.rect.centery):
                        continue
            if not self.player.rect.colliderect(_npc.rect):
                continue

            pdx = _npc.rect.centerx - self.player.rect.centerx
            pdy = _npc.rect.centery - self.player.rect.centery
            is_moving = (getattr(_npc, '_wander_dx', 0) != 0
                         or getattr(_npc, '_wander_dy', 0) != 0)
            # Heavy resistance for stationary NPCs (1px), lighter for moving (2px)
            push_amt = 2 if is_moving else 1

            if abs(pdx) >= abs(pdy):
                if pdx >= 0:
                    _npc.rect.x += push_amt
                    if walls and any(_npc.rect.colliderect(w) for w in walls):
                        _npc.rect.x -= push_amt
                else:
                    _npc.rect.x -= push_amt
                    if walls and any(_npc.rect.colliderect(w) for w in walls):
                        _npc.rect.x += push_amt
            else:
                if pdy >= 0:
                    _npc.rect.y += push_amt
                    if walls and any(_npc.rect.colliderect(w) for w in walls):
                        _npc.rect.y -= push_amt
                else:
                    _npc.rect.y -= push_amt
                    if walls and any(_npc.rect.colliderect(w) for w in walls):
                        _npc.rect.y += push_amt

            # Keep NPC in bounds
            if floor:
                _npc.rect.clamp_ip(pygame.Rect(30, 30, floor.width - NPC_SIZE - 30, floor.height - NPC_SIZE - 30))
            # Prevent player from overlapping (player stops at NPC edge)
            if self.player.rect.colliderect(_npc.rect):
                if abs(pdx) >= abs(pdy):
                    if pdx >= 0:
                        self.player.rect.right = _npc.rect.left
                    else:
                        self.player.rect.left = _npc.rect.right
                else:
                    if pdy >= 0:
                        self.player.rect.bottom = _npc.rect.top
                    else:
                        self.player.rect.top = _npc.rect.bottom
            _npc._wander_timer = 0.0

        # Seamless staircase detection (silent floor switch)
        self._check_seamless_stairs()

        # Portal-type transitions (campus entrance)
        self._check_floor_transition()
        self._update_entry_prompt_target()

        # Car interaction (campus parking lot)
        if self._car_panel_cooldown > 0:
            self._car_panel_cooldown -= dt
        if self._car_panel_input_delay > 0:
            self._car_panel_input_delay -= dt
        if self.current_floor == FLOOR_CAMPUS and not self._car_panel_active and self._car_panel_cooldown <= 0:
            if self.player.rect.inflate(12, 12).colliderect(self._parked_car_rect):
                if not self._can_end_school_day():
                    self.ui.show_notification("You cannot leave school early.", NOTIF_ERROR)
                    self._car_panel_cooldown = 1.0
                else:
                    self._car_panel_active = True
                    self._car_panel_input_delay = 0.4  # require a fresh key press
                # Push player out of the car rect
                px, py = self.player.rect.centerx, self.player.rect.centery
                cx, cy = self._parked_car_rect.center
                if abs(px - cx) >= abs(py - cy):
                    if px < cx:
                        self.player.rect.right = self._parked_car_rect.left - 2
                    else:
                        self.player.rect.left = self._parked_car_rect.right + 2
                else:
                    if py < cy:
                        self.player.rect.bottom = self._parked_car_rect.top - 2
                    else:
                        self.player.rect.top = self._parked_car_rect.bottom + 2

        # Camera
        self.camera.update(self.player)

        # NPC AI — only update NPCs on current floor
        npc_walls = list(floor.walls) if floor else []
        npc_walls.append(self.player.rect)
        if self.current_floor == FLOOR_CAMPUS:
            npc_walls.extend(self._get_parked_vehicle_rects())
        
        # Add locked doors to NPC walls to block them too
        if floor:
            if self._is_smile_club_room_locked():
                self._set_smile_club_room_locked(True)
            for door in floor.doors:
                if door.locked:
                    npc_walls.append(door.rect)
            
            # Physically block all stair rooms so generic NPCs can't wander into them
            stair_room_ids = {
                "f1_stairs_2f", "f1_basement_stairs", 
                "f2_stairs_1f", "f2_roof_stairs", 
                "b_stairs_up", "rt_stairs_down"
            }
            for rid in stair_room_ids:
                r = floor.rooms.get(rid)
                if r:
                    npc_walls.append(r.rect)
        
        # Staircase and building-entry restriction for generic NPCs
        restricted = [
            "f1_stairs_2f", "f1_basement_stairs", "f2_stairs_1f", "f2_roof_stairs", "b_stairs_up", "rt_stairs_down"
        ]
        if self.current_floor == FLOOR_CAMPUS:
            restricted += ["c_building", "c_tennis", "c_coliseum", "c_b_hall", "c_b_lab", "c_b_lib"]
        
        if self.multiplayer and not self.is_host:
            # Client: only update animations, positions are synced from host
            self.npc_manager.update_animations_on_floor(current_dt, self.current_floor)
        else:
            # Host or Solo: run full NPC AI
            self.npc_manager.update_on_floor(
                current_dt, self.current_floor, floor, npc_walls,
                classrooms_restricted=True,
                restricted_rooms=restricted,
                is_visible=self._is_npc_on_camera
            )
            # Host in coop: also update NPCs on remote player's floor if it's different
            if self.multiplayer and self.is_host and self.remote_player:
                r_floor_id = self.remote_player.current_floor
                if r_floor_id is not None and r_floor_id != self.current_floor:
                    r_floor = self.school_map.get_floor(r_floor_id)
                    if r_floor:
                        r_npc_walls = list(r_floor.walls) if r_floor else []
                        r_npc_walls.append(self.remote_player.rect)
                        if self.player.current_floor == r_floor_id:
                            r_npc_walls.append(self.player.rect)
                        if r_floor_id == FLOOR_CAMPUS:
                            r_npc_walls.extend(self._get_parked_vehicle_rects())
                        for door in r_floor.doors:
                            if door.locked:
                                r_npc_walls.append(door.rect)
                        stair_room_ids = {
                            "f1_stairs_2f", "f1_basement_stairs", 
                            "f2_stairs_1f", "f2_roof_stairs", 
                            "b_stairs_up", "rt_stairs_down"
                        }
                        for rid in stair_room_ids:
                            r = r_floor.rooms.get(rid)
                            if r:
                                r_npc_walls.append(r.rect)
                        r_restricted = [
                            "f1_stairs_2f", "f1_basement_stairs", "f2_stairs_1f", "f2_roof_stairs", "b_stairs_up", "rt_stairs_down"
                        ]
                        if r_floor_id == FLOOR_CAMPUS:
                            r_restricted += ["c_building", "c_tennis", "c_coliseum", "c_b_hall", "c_b_lab", "c_b_lib"]
                        
                        def is_near_remote(npc):
                            return (abs(npc.rect.centerx - self.remote_player.rect.centerx) < 600 and 
                                    abs(npc.rect.centery - self.remote_player.rect.centery) < 600)
                        
                        self.npc_manager.update_on_floor(
                            current_dt, r_floor_id, r_floor, r_npc_walls,
                            classrooms_restricted=True,
                            restricted_rooms=r_restricted,
                            is_visible=is_near_remote
                        )
        if (self.current_floor == FLOOR_BASEMENT
                and getattr(self, "_final_reveal_finished", False)
                and not getattr(self, "_final_office_started", False)):
            for npc_id in self._final_smile_ids:
                npc = self.npc_manager.get_npc_by_id(npc_id)
                if npc:
                    npc.current_floor = FLOOR_BASEMENT
                    npc.is_hostile = True
                    self._keep_npc_in_smile_room(npc)

        # NPC-NPC collision separation inside the cafeteria
        floor1_ref = self.school_map.get_floor(FLOOR_1F)
        if floor1_ref and self.current_floor == FLOOR_1F and not (self.multiplayer and not self.is_host):
            caf = floor1_ref.rooms.get("f1_cafeteria")
            if caf:
                caf_npcs = [
                    n for n in self.npc_manager.get_npcs_on_floor(FLOOR_1F)
                    if caf.rect.collidepoint(n.rect.centerx, n.rect.centery)
                    and n.id != "npc_gordon"
                ]
                for i in range(len(caf_npcs)):
                    for j in range(i + 1, len(caf_npcs)):
                        a, b = caf_npcs[i], caf_npcs[j]
                        if a.rect.colliderect(b.rect):
                            dx = b.rect.centerx - a.rect.centerx
                            dy = b.rect.centery - a.rect.centery
                            if dx == 0 and dy == 0:
                                dx, dy = 1, 0
                            if abs(dx) >= abs(dy):
                                if dx >= 0:
                                    b.rect.x += 1
                                    if any(b.rect.colliderect(w) for w in floor1_ref.walls):
                                        b.rect.x -= 1
                                    a.rect.x -= 1
                                    if any(a.rect.colliderect(w) for w in floor1_ref.walls):
                                        a.rect.x += 1
                                else:
                                    b.rect.x -= 1
                                    if any(b.rect.colliderect(w) for w in floor1_ref.walls):
                                        b.rect.x += 1
                                    a.rect.x += 1
                                    if any(a.rect.colliderect(w) for w in floor1_ref.walls):
                                        a.rect.x -= 1
                            else:
                                if dy >= 0:
                                    b.rect.y += 1
                                    if any(b.rect.colliderect(w) for w in floor1_ref.walls):
                                        b.rect.y -= 1
                                    a.rect.y -= 1
                                    if any(a.rect.colliderect(w) for w in floor1_ref.walls):
                                        a.rect.y += 1
                                else:
                                    b.rect.y -= 1
                                    if any(b.rect.colliderect(w) for w in floor1_ref.walls):
                                        b.rect.y += 1
                                    a.rect.y += 1
                                    if any(a.rect.colliderect(w) for w in floor1_ref.walls):
                                        a.rect.y -= 1

        if (not (self.multiplayer and not self.is_host)
                and self.current_floor == FLOOR_BASEMENT
                and getattr(self, "_final_reveal_finished", False)
                and not getattr(self, "_final_office_started", False)):
            self._keep_player_in_smile_room()
            for npc_id in self._final_smile_ids:
                npc = self.npc_manager.get_npc_by_id(npc_id)
                if npc:
                    self._keep_npc_in_smile_room(npc)
                    if npc.health > 0:
                        npc.is_hostile = True

        # Day timer (use current_dt for faster phase transitions)
        self.day_timer += current_dt
        if self.day_timer >= self.phase_duration:
            self._advance_phase()

        # mission objective checks (use legacy zone mapping)
        legacy_zone = 0
        for old_z, (fid, _, _) in ZONE_TO_FLOOR.items():
            if fid == self.current_floor:
                legacy_zone = old_z
                break
        completed = self.mission_manager.check_objectives(
            self.player, self.npc_manager, self.reputation,
            self.inventory, legacy_zone,
        )
        for mid in completed:
            rewards = self.mission_manager.complete_mission(mid)
            if rewards:
                self._apply_rewards(rewards)
                msg = self.mission_manager.get_motivational_message()
                self.ui.show_notification(f"✅ Mission complete! {msg}", NOTIF_SUCCESS, 5.0)
                # Auto-activate newly available missions
                for m in self.mission_manager.get_available():
                    self.mission_manager.activate_mission(m.id)
                    if m.id == "mission_talk_ava_rooftop":
                        self._current_main_mission_text = "Mission 11: Find Ava Thompson at the rooftop party."
                    elif m.id == "mission_check_ava_phone":
                        self._current_main_mission_text = "Mission 12: Check Ava's phone before she comes back! (15 seconds)"
                    elif m.id == "mission_final_showdown":
                        self._current_main_mission_text = "Mission 13: Go to the Basement and see what they're plotting!"

        # Update markers for key NPCs
        self._update_minimap_markers()

        # Check mainframe login collision for Mission 8
        self._computer_prompt_active = False
        if getattr(self, '_ava_needs_to_walk_to_computer', False):
            has_lena_on_f1 = (self.current_floor == FLOOR_1F and self.character == Character.LENA)
            if self.multiplayer and self.remote_player:
                r_char = getattr(self.remote_player, "character", None)
                r_char_name = ""
                if r_char:
                    if hasattr(r_char, "value"):
                        r_char_name = r_char.value.lower()
                    else:
                        r_char_name = str(r_char).lower()
                if self.remote_player.current_floor == FLOOR_1F and "lena" in r_char_name:
                    has_lena_on_f1 = True
            
            if has_lena_on_f1:
                if not (self.multiplayer and not self.is_host):
                    ava = self.npc_manager.get_npc_by_id("npc_ava_thompson")
                    if ava:
                        ava.ai_enabled = True
                        ava.ignore_schedule = True
                        ava.stop_at_target = True
                        ava.target_queue = [(180, 350)]
                        ava.target_pos = (180, 350)
                self._ava_needs_to_walk_to_computer = False

        if self.current_floor == FLOOR_1F:
            m_obj = self.mission_manager.missions.get("mission_high_school_mainframe")
            if m_obj and m_obj.status in (MissionStatus.ACTIVE, MissionStatus.AVAILABLE):
                if self.player.rect.colliderect(pygame.Rect(90, 320, 90, 64).inflate(50, 50)):
                    if self.character != Character.LENA:
                        if getattr(self, '_lena_hack_warn_timer', 0) <= 0:
                            if self.multiplayer:
                                self.ui.show_notification("Ava Thompson: 'Aiden, let Lena handle this computer!'", NOTIF_WARNING)
                            else:
                                self.ui.show_notification("Ava Thompson: 'Aiden, let Lena handle this computer. Switch characters!'", NOTIF_WARNING)
                            self._lena_hack_warn_timer = 2.0
                    else:
                        self._computer_prompt_active = True

        # Check game-over
        if not self.player.is_alive():
            self.state = GameState.GAME_OVER

        if getattr(self, '_lena_hack_warn_timer', 0) > 0:
            self._lena_hack_warn_timer -= dt

    # ── time of day ───────────────────────────────────────────

    def _tick_time(self, dt: float):
        if self._school_day_ended:
            return  # Clock frozen after 4 PM
        increment = dt * self._time_scale
        if increment <= 0:
            return
        self.time_of_day_minutes = (self.time_of_day_minutes + increment) % (24 * 60)

    def _update_class_schedule(self):
        previous = self._last_time_minutes
        current = self.time_of_day_minutes
        self._last_time_minutes = current

        # 4:00 PM (960 mins) — Freeze clock, notify player, NO NPC DEPARTURE
        if current >= 960:
            self.time_of_day_minutes = 960  # Freeze at exactly 4:00 PM
            if not self._school_day_ended:
                self._school_day_ended = True
                self.ui.trigger_announcement("SCHOOL'S OUT!", "Classes are over for the day.")
                self.ui.show_notification("School's out! (NPCs will stay in their assigned rooms)", NOTIF_INFO, 8.0)
                get_controller().rumble(0.7, 0.7, 500)
            return

        # Update ScheduleManager for NPC routines
        if hasattr(self, 'schedule_manager'):
            self.schedule_manager.update(
                current, self.npc_manager, self.school_map, self.current_floor,
                is_visible=self._is_npc_on_camera,
                day_number=self.day_number
            )
        if self.day_number >= 2:
            self._place_ava_for_story()

        # Update cafeteria door visual/physical state
        floor1 = self.school_map.get_floor(FLOOR_1F)
        if floor1:
            for door in floor1.doors:
                if getattr(door, "id", "") == "door_cafeteria":
                    door.locked = not self._is_cafeteria_open()

    def _trigger_npc_departure(self):
        """At 4:00 PM, all NPCs start walking towards the exit."""
        blocked_ids = {
            "npc_gordon", "npc_oscar", "npc_director",
            "npc_oscar_obs1", "npc_oscar_obs2", "npc_oscar_obs3", "npc_oscar_obs4",
            "npc_ava_thompson", "npc_bath_m_attendant", "npc_bath_f_attendant",
        }

        count = 0
        for npc in self.npc_manager.npcs.values():
            if npc.id in blocked_ids:
                continue
            if getattr(npc, "ignore_schedule", False):
                continue

            # Varied walk speed for organic feel (±15%)
            npc.speed_multiplier = random.uniform(0.85, 1.15)
            npc.start_delay = count * 0.3 + random.uniform(0, 2)
            npc.ai_enabled = True
            npc.stop_at_target = True
            npc.bound_rect = None

            # NPCs on other floors need to get to campus
            if npc.current_floor != FLOOR_CAMPUS:
                if self._is_npc_on_camera(npc):
                    # NPC is visible — walk to stairs first, then teleport
                    # after leaving the camera. Queue stair waypoints.
                    from src.stair_routes import build_multi_floor_route
                    route = build_multi_floor_route(npc.current_floor, FLOOR_CAMPUS)
                    if route:
                        first_wp = route[0] if not isinstance(route[0], str) else (
                            npc.rect.centerx, npc.rect.centery)
                        npc.target_pos = first_wp
                        # After floor switch, walk to the exit
                        exit_x = random.randint(100, 1100)
                        exit_y = 2850 + random.randint(0, 100)
                        npc.target_queue = route[1:] + [(exit_x, 2400), (exit_x, exit_y)]
                    else:
                        # Fallback: just walk offscreen on current floor
                        npc.target_pos = (npc.rect.centerx + 800, npc.rect.centery)
                        npc.target_queue = []
                else:
                    # NPC is NOT visible — safe to teleport
                    npc.current_floor = FLOOR_CAMPUS
                    npc.rect.center = (
                        2000 + random.randint(-200, 200),
                        2050 + random.randint(-50, 50),
                    )
                    # Walk to parking lot / road exit
                    exit_x = random.randint(100, 1100)
                    exit_y = 2850 + random.randint(0, 100)
                    npc.target_pos = (
                        npc.rect.centerx + random.randint(-30, 30),
                        npc.rect.centery + random.randint(-30, 30),
                    )
                    npc.target_queue = [
                        (exit_x, 2400),
                        (exit_x, exit_y),
                    ]
            else:
                # Already on campus — walk to exit
                exit_x = random.randint(100, 1100)
                exit_y = 2850 + random.randint(0, 100)
                npc.target_pos = (
                    npc.rect.centerx + random.randint(-30, 30),
                    npc.rect.centery + random.randint(-30, 30),
                )
                npc.target_queue = [
                    (exit_x, 2400),
                    (exit_x, exit_y),
                ]
            count += 1

    def _clear_noah_area(self, radius: int = 140):
        """Push random NPCs away from Noah's current position during the cinematic."""
        noah = self.npc_manager.get_npc_by_id("npc_noah_carter")
        if not noah:
            return

        floor = self.school_map.get_floor(noah.current_floor)
        if not floor:
            return

        radius_sq = radius * radius
        npcs = self.npc_manager.get_npcs_on_floor(noah.current_floor)
        for npc in npcs:
            if npc is noah or not is_generic_wanderer(npc.id):
                continue
            dx = npc.rect.centerx - noah.rect.centerx
            dy = npc.rect.centery - noah.rect.centery
            dist_sq = dx * dx + dy * dy
            if dist_sq < radius_sq:
                angle = random.uniform(0, math.tau)
                distance = radius + random.randint(60, 140)
                tx = noah.rect.centerx + int(distance * math.cos(angle))
                ty = noah.rect.centery + int(distance * math.sin(angle))
                tx = max(40, min(tx, floor.width - 40))
                ty = max(40, min(ty, floor.height - 40))
                current_target = getattr(npc, "target_pos", None)
                if current_target:
                    cx, cy = current_target
                    if (cx - tx) ** 2 + (cy - ty) ** 2 < 40 ** 2:
                        continue
                npc.target_queue = []
                npc.target_pos = (tx, ty)
                npc.ai_enabled = True
                npc.stop_at_target = True
                npc.speed_multiplier = 1.3

    def _spread_first_floor_npcs(self):
        """Scatter normal first-floor NPCs across the larger school map."""
        if self.current_phase not in (DayPhase.ARRIVAL, DayPhase.CLASS_1, DayPhase.CLASS_2):
            return

        floors = {
            FLOOR_CAMPUS: self.school_map.get_floor(FLOOR_CAMPUS),
            FLOOR_1F: self.school_map.get_floor(FLOOR_1F),
            FLOOR_2F: self.school_map.get_floor(FLOOR_2F),
            FLOOR_BASEMENT: self.school_map.get_floor(FLOOR_BASEMENT),
            FLOOR_ROOFTOP: self.school_map.get_floor(FLOOR_ROOFTOP),
            FLOOR_COLISEUM_INTERIOR: self.school_map.get_floor(FLOOR_COLISEUM_INTERIOR),
        }
        if any(floor is None for floor in floors.values()):
            return

        scatter_areas = [
            (FLOOR_CAMPUS, pygame.Rect(180, 180, 1050, 900), None),       # green zones / gardens
            (FLOOR_CAMPUS, pygame.Rect(2780, 1080, 980, 650), None),      # Athletic Coliseum campus side
            (FLOOR_COLISEUM_INTERIOR, pygame.Rect(320, 260, 1160, 650), None),
            (FLOOR_1F, pygame.Rect(1120, 120, 960, 1650), None),          # 1F main hall
            (FLOOR_1F, pygame.Rect(120, 120, 850, 720), None),            # lab / infirmary side
            (FLOOR_1F, pygame.Rect(2260, 120, 780, 480), None),           # library wing
            (FLOOR_2F, pygame.Rect(1120, 120, 960, 1650), None),          # 2F corridor
            (FLOOR_2F, pygame.Rect(120, 420, 850, 1300), None),           # 2F art/music/science wing
            (FLOOR_2F, pygame.Rect(2260, 120, 780, 1320), None),          # 2F admin wing
            (FLOOR_BASEMENT, pygame.Rect(360, 260, 680, 420), None),
            (FLOOR_BASEMENT, pygame.Rect(1210, 260, 680, 420), None),
            (FLOOR_BASEMENT, pygame.Rect(2050, 260, 560, 420), None),
            (FLOOR_1F, pygame.Rect(1180, 2020, 860, 280), None),          # reception (moved to end, less priority)
        ]

        from settings import NPC_SIZE, SocialGroup
        blocked_ids = {
            "npc_noah_carter",
            "npc_gordon",
            "npc_director",
            "npc_oscar",
            "npc_oscar_obs1",
            "npc_oscar_obs2",
            "npc_oscar_obs3",
            "npc_oscar_obs4",
            "npc_ava_thompson",
            "npc_bath_m_attendant",
            "npc_bath_f_attendant",
        }
        candidates = [
            npc for npc in self.npc_manager.npcs.values()
            if npc.id not in blocked_ids
            and not npc.id.startswith("npc_class_")
            and not getattr(npc, "ignore_schedule", False)
            and npc.current_zone != 3  # Don't teleport people heading to/in cafeteria
        ]

        occupied_by_floor = {
            floor_id: [
                npc.rect.copy()
                for npc in self.npc_manager.get_npcs_on_floor(floor_id)
                if npc.id not in blocked_ids and npc not in candidates
            ]
            for floor_id in floors
        }

        popular_candidates = [n for n in candidates if getattr(n, "group", None) == SocialGroup.POPULARS]
        rooftop_npcs = set(sorted(popular_candidates, key=lambda n: n.id)[:5])

        def choose_area(npc, start_idx):
            if npc in rooftop_npcs:
                return FLOOR_ROOFTOP, pygame.Rect(1250, 50, 1100, 900)
            for offset in range(len(scatter_areas)):
                floor_id, area, allowed_gender = scatter_areas[(start_idx + offset) % len(scatter_areas)]
                if allowed_gender is None or getattr(npc, "gender", "unspecified") == allowed_gender:
                    return floor_id, area
            floor_id, area, _ = scatter_areas[start_idx % len(scatter_areas)]
            return floor_id, area

        for idx, npc in enumerate(sorted(candidates, key=lambda n: n.id)):
            # NEVER teleport NPCs visible on camera
            if self._is_npc_on_camera(npc):
                continue

            floor_id, area = choose_area(npc, idx)
            floor = floors[floor_id]
            inner = area.inflate(-70, -70)

            placed = False
            for attempt in range(40):
                cols = 4
                rows = max(2, (len(candidates) // max(1, len(scatter_areas) * cols)) + 2)
                half = NPC_SIZE // 2
                cell_x = attempt % cols
                cell_y = (attempt // cols) % rows
                base_x = inner.left + int((cell_x + 0.5) * inner.width / cols)
                base_y = inner.top + int((cell_y + 0.5) * inner.height / rows)
                npc.rect.center = (
                    max(inner.left + half, min(base_x + random.randint(-24, 24), inner.right - half)),
                    max(inner.top + half, min(base_y + random.randint(-24, 24), inner.bottom - half)),
                )
                blockers = floor.walls + occupied_by_floor[floor_id]
                if not any(npc.rect.colliderect(w) for w in blockers):
                    placed = True
                    break

            if not placed:
                from src.npc import get_safe_spawn_point
                rx, ry = get_safe_spawn_point(inner, blockers, npc.rect.copy())
                npc.rect.center = (rx, ry)

            npc.current_floor = floor_id
            npc.current_zone = -1
            occupied_by_floor[floor_id].append(npc.rect.copy())
            npc.bound_rect = None
            npc.ai_enabled = True
            npc.stop_at_target = False
            npc.target_queue = []
            if random.random() < 0.75:
                from src.npc import get_safe_spawn_point
                tx, ty = get_safe_spawn_point(inner, blockers, npc.rect.copy())
                npc.target_pos = (tx, ty)
            else:
                npc.target_pos = None

    def _clear_bus_path(self):
        """Ensure no NPCs block the road during the bus cinematic and departure."""
        safe_road = pygame.Rect(-200, 2300, 1500, 300)
        for npc in self.npc_manager.get_npcs_on_floor(0):
            if npc.rect.colliderect(safe_road):
                npc.rect.y = 2100
                if getattr(npc, "target_pos", None) and npc.target_pos[1] > 2300:
                    npc.target_pos = (npc.target_pos[0], 2100)

    def _get_time_string(self) -> str:
        total_minutes = int(self.time_of_day_minutes)
        hours_24 = (total_minutes // 60) % 24
        minutes = total_minutes % 60
        suffix = "am" if hours_24 < 12 else "pm"
        hours_12 = hours_24 % 12
        if hours_12 == 0:
            hours_12 = 12
        return f"{hours_12:02d}:{minutes:02d} {suffix}"

    def _is_cafeteria_open(self) -> bool:
        """Check if current time is within cafeteria hours (9:30 AM - 4:00 PM)."""
        mins = self.time_of_day_minutes
        return (570 <= mins <= 960)

    def _update_minimap_markers(self):
        """Register specific NPCs on the world map for easier tracking."""
        key_npcs = {
            "npc_gordon":      ("El Gastroo",  (200, 100, 50)),
            "npc_dylan":       ("Dylan Brooks",   (200, 50, 50)),
            "npc_marcus_green":("Marcus Green",   (50, 100, 200)),
            "npc_director":    ("Director Walsh", (150, 50, 200)),
            "npc_noah_carter": ("Noah Carter",    (50, 180, 120)),
            "npc_ava_thompson": ("Ava Thompson",  (255, 180, 80)),
            "npc_axel_knight": ("Axel Knight",    (220, 50, 50)),
        }
        if getattr(self, '_alan_chen_map_unlocked', False):
            key_npcs["npc_alan_chen"] = ("Alan Chen", (100, 200, 255))
        for nid, (label, col) in key_npcs.items():
            npc = self.npc_manager.get_npc_by_id(nid)
            if npc:
                if (nid in getattr(self, "_final_smile_ids", ())
                        and getattr(self, "_is_final_showdown_active", lambda: False)()
                        and not getattr(self, "_final_reveal_finished", False)):
                    label = "Smile Club Member"
                    col = (245, 245, 245)
                self.world_map.set_marker(
                    label, npc.current_floor, 
                    npc.rect.centerx, npc.rect.centery, col
                )
        if getattr(self, "_is_final_showdown_active", lambda: False)() and not getattr(self, "_final_reveal_finished", False):
            for old_label in ("Ava Thompson", "Marcus Green", "Noah Carter"):
                self.world_map.clear_marker(old_label)

    def _get_cafeteria_seat(self) -> tuple[int, int]:
        """Return the next unique seat from the shuffled pool."""
        # Lazily init / refill the pool
        pool = getattr(self, '_caf_seat_pool', None)
        if not pool:
            floor1 = self.school_map.get_floor(FLOOR_1F)
            raw = getattr(floor1, 'cafeteria_seats', None) if floor1 else None
            if raw:
                # Duplicate the list 3× so we have enough for all NPCs
                expanded = list(raw) * 3
                random.shuffle(expanded)
                self._caf_seat_pool = expanded
            else:
                caf = floor1.rooms.get("f1_cafeteria") if floor1 else None
                if caf:
                    self._caf_seat_pool = [
                        (caf.rect.centerx + random.randint(-120, 120),
                         caf.rect.centery + random.randint(-80, 80))
                        for _ in range(30)
                    ]
                else:
                    self._caf_seat_pool = [(2700, 850)]
            pool = self._caf_seat_pool

        sx, sy = pool.pop()
        return (sx + random.randint(-12, 12), sy + random.randint(-12, 12))

    def _move_random_npcs_to_cafeteria(self):
        """Make random NPCs head to the cafeteria and sit at tables (walking, no teleport)."""
        self._caf_seat_pool = []  # reset pool so seats are freshly shuffled
        floor1 = self.school_map.get_floor(FLOOR_1F)
        if not floor1: return
        
        # Take all generic NPCs that are supposed to be in the cafeteria (Zone 3)
        npcs = [n for n in self.npc_manager.npcs.values() 
                if n.id.startswith("npc_rnd_") and n.current_zone == 3
                and not getattr(n, "ignore_schedule", False)]
        
        caf_room = floor1.rooms.get("f1_cafeteria")
        library_room = floor1.rooms.get("f1_library")
        if not caf_room: return

        # Cafeteria layout: tables at y=720..1020. Door at (2210, 780).
        below_tables_y = caf_room.rect.bottom - 40
        
        count = 0
        for npc in npcs:
            seat = self._get_cafeteria_seat()
            
            # Floor 2 to Floor 1 transition via stairs
            if npc.current_floor == FLOOR_2F:
                # Stairs on 2F are at (2150, 1720)
                npc.target_pos = (2100, 1720) # Near stairs
                npc.target_queue = [
                    (2150, 1720),      # At stairs
                    "SWITCH_TO_F1",    # Teleport to 1F stairs
                    (2100, 1720),      # At 1F stairs (outside)
                    (2100, 780),       # To cafeteria door level
                    (2210, 780),       # Through door
                    (2210 + random.randint(20, 60), below_tables_y),
                    (seat[0], below_tables_y),
                    seat
                ]
            else:
                # Floor 1 logic
                in_library = library_room and library_room.rect.collidepoint(npc.rect.centerx, npc.rect.centery)
                
                if in_library:
                    door_y = 420 + random.randint(-30, 30)
                    npc.target_pos = (2180, door_y)
                    npc.target_queue = [
                        (2140, door_y),
                        (2100, door_y),
                        (2100, 780 + random.randint(-15, 15)),
                        (2210, 780 + random.randint(-15, 15)),
                        (2210 + random.randint(20, 60), below_tables_y),
                        (seat[0], below_tables_y),
                        seat,
                    ]
                else:
                    # Default corridor walk
                    npc.target_pos = (npc.rect.centerx, npc.rect.centery) # start moving from where they are
                    npc.target_queue = [
                        (2100, npc.rect.centery),                      # move to center corridor
                        (2100, 780 + random.randint(-15, 15)),         # to door level
                        (2210, 780 + random.randint(-15, 15)),         # through door
                        (2210 + random.randint(20, 60), below_tables_y),
                        (seat[0], below_tables_y),
                        seat,
                    ]
            
            npc.start_delay = count * 0.4
            npc.stop_at_target = True
            npc.ai_enabled = True
            count += 1

    # Clear vertical lanes between cafeteria tables (gap centres)
    _CAF_EXIT_LANES = [2233, 2495, 2775, 3067]

    def _cafeteria_exit_waypoints(self, npc) -> list[tuple[int, int]]:
        """Build a collision-free waypoint list from an NPC's seat to the door.

        Tables span x 2300-2430, 2560-2690, 2860-2990  /  y 720-1020.
        Strategy: move to the nearest clear lane first, then go ABOVE
        all tables (exit via top), then slide left and exit through the door.
        """
        nx, ny = npc.rect.centerx, npc.rect.centery
        ABOVE_Y = 680  # Above all tables (tables start at y=720)
        DOOR_X  = 2200
        DOOR_Y  = 780 + random.randint(-15, 15)

        # Pick the nearest gap lane
        lane_x = min(self._CAF_EXIT_LANES, key=lambda lx: abs(lx - nx))

        wps: list[tuple[int, int]] = []

        # If the NPC is in the table zone (y 700-1040), side-step to the
        # gap first so they don't walk through a table.
        if 700 < ny < 1040 and abs(lane_x - nx) > 25:
            wps.append((lane_x, ny))           # sidestep to gap

        wps.append((lane_x, ABOVE_Y))          # up through gap (exit via top)
        wps.append((DOOR_X, ABOVE_Y))          # slide left above tables
        wps.append((DOOR_X, DOOR_Y))           # down to door height
        wps.append((2130, DOOR_Y))             # clear of door wall
        return wps

    def _move_npcs_out_of_cafeteria(self, instant: bool = False):
        """Clear the cafeteria - NPCs exit through the door then wander the main hall."""
        floor1 = self.school_map.get_floor(FLOOR_1F)
        if not floor1: return
        npcs = self.npc_manager.get_npcs_on_floor(FLOOR_1F)

        count = 0
        for npc in npcs:
            if getattr(npc, "ignore_schedule", False): continue

            room = floor1.get_room_at(npc.rect.centerx, npc.rect.centery)
            if room and room.id == "f1_cafeteria":
                hall_x = random.randint(1100, 2100)
                hall_y = random.randint(100, 1800)
                if instant:
                    npc.rect.centerx = hall_x
                    npc.rect.centery = hall_y
                    npc.target_queue = []
                    npc.target_pos = None
                    npc.ai_enabled = True
                    npc.stop_at_target = False
                else:
                    wps = self._cafeteria_exit_waypoints(npc)
                    npc.bound_rect = None
                    npc.target_pos = wps[0]
                    npc.target_queue = wps[1:] + [(hall_x, hall_y)]
                    npc.start_delay = count * 0.35
                    npc.stop_at_target = False
                    npc.ai_enabled = True
                    npc.speed_multiplier = 1.2
                    count += 1



    # ── day cycle ─────────────────────────────────────────────

    def _advance_phase(self):
        ev = self.event_queue.next_event()
        if ev:
            self.current_phase  = ev["phase"]
            self.phase_duration = ev["duration"]
            self.day_timer      = 0.0
            phase_label = self.current_phase.value.replace("_", " ").title()
            # If it's Day 2+, hide the "Arrival" tag to keep the UI clean as requested
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            day_name = days[(self.day_number - 1) % 5]
            
            # Ensure phone schedule is synced with current day number
            self.aiden_phone.update_day_schedule(self.day_number)
            self.lena_phone.update_day_schedule(self.day_number)

            # Silence "Arrival" notification for Day 2+ as requested
            if self.day_number > 1 and self.current_phase == DayPhase.ARRIVAL:
                pass
            else:
                msg = f"📅 {day_name} — {phase_label}"
                self.ui.show_notification(msg, NOTIF_INFO)
            if random.random() < 0.3:
                self._random_event()
        else:
            self.day_number += 1
            self.event_queue.load_day_schedule()
            self.aiden_phone.update_day_schedule(self.day_number)
            self.lena_phone.update_day_schedule(self.day_number)
            self.time_of_day_minutes = 7 * 60
            # Clear NPCs from cafeteria instantly before the new day
            self._move_npcs_out_of_cafeteria(instant=True)

            self._advance_phase()

    def _random_event(self):
        npcs = self.npc_manager.get_npcs_on_floor(self.current_floor)
        roll = random.randint(0, 2)
        if roll == 0 and len(npcs) >= 2:
            self.ui.show_notification("⚠ You notice something happening nearby…", NOTIF_WARNING)
        elif roll == 1 and npcs:
            npc = random.choice(npcs)
            npc.having_bad_day = True
            self.ui.show_notification(
                f"{npc.name} seems to be having a rough day…", NOTIF_INFO,
            )
        else:
            self.ui.show_notification("📢 A new rumour is spreading…", NOTIF_INFO)

    # ── rewards / consequences ────────────────────────────────

    def _get_yearbook_data(self) -> dict:
        """Prepare yearbook data: reputation by group and NPCs by group."""
        reputation_data = {}
        npc_groups = {}
        
        # Get reputation standings
        if self.reputation:
            for group_str, rep_value in self.reputation.standings.items():
                # Convert group string to display name
                group_display = group_str.replace("_", " ").title()
                reputation_data[group_str] = rep_value
        
        # Group NPCs by their social group
        from settings import SocialGroup
        for group in SocialGroup:
            group_name = group.value.replace("_", " ").title()
            npc_list = []
            
            for npc_id, npc in self.npc_manager.npcs.items():
                # Skip the player and sibling
                if npc_id in ("npc_aiden", "npc_lena"):
                    continue
                if npc.group == group:
                    # Get player→NPC relationship
                    player_key = f"player_{self.character.value}"
                    rel_edge = self.npc_manager.relationships.get_relationship(player_key, npc_id)
                    npc_rep = 50  # default neutral
                    if rel_edge:
                        # Use average of friendship and trust as a simple relationship score
                        npc_rep = (rel_edge.friendship + rel_edge.trust) // 2
                    
                    friendship = rel_edge.friendship if rel_edge else 50
                    respect = rel_edge.respect if rel_edge else 50
                    fear = rel_edge.fear if rel_edge else 0
                    trust = rel_edge.trust if rel_edge else 50
                    suspicion = rel_edge.suspicion if rel_edge else 0
                    
                    npc_list.append({
                        "name": npc.name,
                        "id": npc_id,
                        "reputation": npc_rep,
                        "gender": getattr(npc, "gender", "unspecified"),
                        "mask_revealed": getattr(npc, "mask_revealed", False),
                        "public_personality": getattr(npc, "public_personality", "Unknown"),
                        "private_personality": getattr(npc, "private_personality", "Unknown"),
                        "friendship": friendship,
                        "respect": respect,
                        "fear": fear,
                        "trust": trust,
                        "suspicion": suspicion,
                    })
            
            if npc_list:
                npc_groups[group_name] = npc_list
        
        # Clamp scroll offset
        selected_npcs = npc_groups.get(self.selected_yearbook_group, [])
        max_scroll = max(0, len(selected_npcs) - 4)
        self.yearbook_scroll_offset = max(0, min(self.yearbook_scroll_offset, max_scroll))
        
        return {
            "reputation_data": reputation_data,
            "npc_groups": npc_groups,
            "selected_group": self.selected_yearbook_group,
            "scroll_offset": self.yearbook_scroll_offset,
        }

    def _apply_rewards(self, rewards: dict):
        if "xp" in rewards:
            self.player.gain_xp(rewards["xp"])
        if "reputation" in rewards:
            for grp, delta in rewards["reputation"].items():
                self.reputation.modify(grp, delta)
        if "items" in rewards:
            for it in rewards["items"]:
                self.inventory.add_item(
                    it["name"],
                    ItemCategory(it.get("category", "special")),
                    it.get("description", ""),
                )
        if "unlock_zone" in rewards:
            self.school_map.unlock_zone(rewards["unlock_zone"])
            self.ui.show_notification("🔓 A new area has been unlocked!", NOTIF_SUCCESS)

    def _apply_dialogue_result(self, result: dict):
        if not result:
            return
        if "reputation_changes" in result:
            for grp, delta in result["reputation_changes"].items():
                self.reputation.modify(grp, delta)
        if "npc_stat_changes" in result:
            for npc_id, stats in result["npc_stat_changes"].items():
                npc = self.npc_manager.get_npc_by_id(npc_id)
                if npc:
                    rel = self.npc_manager.relationships.get_relationship(
                        f"player_{self.character.value}", npc_id,
                    )
                    if rel:
                        for st, val in stats.items():
                            rel.modify(st, val)
        if "item_received" in result:
            it = result["item_received"]
            self.inventory.add_item(
                it["name"], ItemCategory(it.get("category", "special")),
                it.get("description", ""),
            )
        if "mission_unlock" in result:
            self.mission_manager.unlock_mission(result["mission_unlock"])
            self.mission_manager.activate_mission(result["mission_unlock"])
            self.ui.show_notification("📋 New mission available!", NOTIF_INFO)
        if result.get("complete_tech_lab_ava"):
            m_obj = self.mission_manager.missions.get("mission_tech_lab_ava")
            if m_obj:
                m_obj.status = MissionStatus.COMPLETED
                for obj in m_obj.objectives:
                    obj.completed = True
                    obj.progress = obj.required
                self.mission_manager.completed_ids.add("mission_tech_lab_ava")
            self.mission_manager._refresh_availability()
            self._current_main_mission_text = "Mission 5: Open map to find Alan Chen's discreet location and talk to him."
        if result.get("show_alan_chen_map"):
            self._alan_chen_map_unlocked = True
        if result.get("talked_to_alan_chen_first"):
            m_obj = self.mission_manager.missions.get("mission_alan_chen_bathroom")
            if m_obj and m_obj.status != MissionStatus.COMPLETED:
                m_obj.status = MissionStatus.COMPLETED
                for obj in m_obj.objectives:
                    obj.completed = True
                    obj.progress = obj.required
                self.mission_manager.completed_ids.add("mission_alan_chen_bathroom")
                self.mission_manager.unlock_mission("mission_tech_club_rep")
                self.mission_manager.activate_mission("mission_tech_club_rep")
                self._current_main_mission_text = "Mission 6: Gain 70 Tech Club reputation, then return to Alan Chen in his discreet location."
        if "alan_chen_rep_check" in result:
            tech_rep = self.reputation.get("tech_club")
            overall_rep = self.reputation.reputation_score
            max_group_rep = max(self.reputation.standings.values()) if hasattr(self.reputation, 'standings') and self.reputation.standings else 0
            if tech_rep >= 70 or overall_rep >= 70 or max_group_rep >= 70:
                self.ui.show_notification("Alan Chen nods: 'You've earned my trust. Here are the hacked credentials.'", NOTIF_SUCCESS)
                m_obj = self.mission_manager.missions.get("mission_tech_club_rep")
                if m_obj:
                    m_obj.status = MissionStatus.COMPLETED
                    for obj in m_obj.objectives:
                        obj.completed = True
                        obj.progress = obj.required
                    self.mission_manager.completed_ids.add("mission_tech_club_rep")
                if not self.inventory.has_item("Hacked Credentials"):
                    self.inventory.add_item(
                        "Hacked Credentials", ItemCategory.NOTE,
                        "Hacked high school system credentials provided by Alan Chen.",
                    )
                self.mission_manager.unlock_mission("mission_return_tech_lab")
                self.mission_manager.activate_mission("mission_return_tech_lab")
                self._current_main_mission_text = "Mission 7: Return to the Tech Lab and give the hacked credentials to Ava Thompson."
            else:
                curr_disp = max(tech_rep, overall_rep, max_group_rep)
                self.ui.show_notification(f"Alan Chen shakes his head: 'You need 70 reputation (Current: {curr_disp}). I can't trust you yet.'", NOTIF_ERROR)
        if "give_hacked_credentials" in result:
            if self.inventory.has_item("Hacked Credentials"):
                if self.multiplayer:
                    self.ui.show_notification("Ava Thompson: 'We have the credentials, but I need someone who really knows their way around this system. Lena, can you help us with the mainframe computer?'", NOTIF_SUCCESS, 8.0)
                else:
                    self.ui.show_notification("Ava Thompson: 'We have the credentials, but I need someone who really knows their way around this system. Aiden, call your sister Lena to complete the inspection—she's the one who handles technology best.'", NOTIF_SUCCESS, 8.0)
                self._ava_needs_to_walk_to_computer = True
                m_obj = self.mission_manager.missions.get("mission_return_tech_lab")
                if m_obj and m_obj.status != MissionStatus.COMPLETED:
                    m_obj.status = MissionStatus.COMPLETED
                    for obj in m_obj.objectives:
                        obj.completed = True
                        obj.progress = obj.required
                    self.mission_manager.completed_ids.add("mission_return_tech_lab")
                    self.mission_manager.unlock_mission("mission_high_school_mainframe")
                    self.mission_manager.activate_mission("mission_high_school_mainframe")
                    self.mission_manager._refresh_availability()
                    if self.multiplayer:
                        self._current_main_mission_text = "Mission 8: Lena must go to the computer marked with X in the Tech Lab and extract information."
                    else:
                        self._current_main_mission_text = "Mission 8: Switch to Lena, go to the computer marked with X in the Tech Lab and extract information."
            else:
                self.ui.show_notification("Ava Thompson looks at you: 'You don't have the credentials yet. Go talk to Alan Chen.'", NOTIF_ERROR)
        if "rooftop_check" in result:
            pop_rep = self.reputation.get("populars")
            if pop_rep >= 60:
                self._rooftop_unlocked = True
                self.ui.show_notification("Axel Knight nods. Rooftop access unlocked!", NOTIF_SUCCESS)
                axel = self.npc_manager.get_npc_by_id("npc_axel_knight")
                if axel:
                    axel.ai_enabled = True
                    axel.target_pos = (1066, 180)  # Move up to step aside
                    axel.stop_at_target = True
            else:
                self.ui.show_notification(f"Axel sneers: 'You need 60 Popular reputation (Current: {pop_rep}). Get lost!'", NOTIF_ERROR)
        if result.get("day1_complete"):
            self._complete_day1_story()
        if "xp" in result:
            self.player.gain_xp(result["xp"])
        if "reveal_mask" in result:
            npc = self.npc_manager.get_npc_by_id(result["reveal_mask"])
            if npc:
                npc.reveal_mask()
                self.ui.show_notification(
                    f"You see {npc.name}'s true side…", NOTIF_WARNING,
                )
        if "start_pingpong" in result and result["start_pingpong"]:
            self.dialogue_system.active_tree = None
            opponent = self.npc_manager.get_npc_by_id("npc_oscar")
            self.pingpong.start(self.player, opponent)
            self.state = GameState.PINGPONG
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.load("assets/sounds/armin-van-buuren-ping-pong-official-music-video_imhWhjMW.mp3")
                    pygame.mixer.music.set_volume(0.25)
                    pygame.mixer.music.play(-1)
            except Exception:
                pass
        if "start_basketball" in result and result["start_basketball"]:
            self.dialogue_system.active_tree = None
            opponent = self.npc_manager.get_npc_by_id("npc_marcus_green")
            
            is_coop = getattr(self, "multiplayer", False)
            ally = None
            opp2 = None
            
            if is_coop:
                ally = getattr(self, "remote_player", None)
                opp2 = self.npc_manager.get_npc_by_id("npc_zachary_cole")

            # Clear other NPCs from the court
            try:
                floor = self.school_map.get_floor(self.current_floor)
                if floor and hasattr(floor, "basketball_court"):
                    bc = floor.basketball_court
                    for npc in self.npc_manager.get_npcs_on_floor(self.current_floor):
                        if npc not in (opponent, ally, opp2) and npc.rect.colliderect(bc):
                            # Teleport out of the court safely (to the left of it)
                            npc.rect.right = bc.left - 20
                            npc.target_pos = None
                            npc.target_queue = []
            except Exception:
                pass

            self.basketball.start(self.player, opponent, floor, is_coop=is_coop, ally=ally, opp2=opp2, is_host=self.is_host)
            self._play_basketball_music()
            self.state = GameState.BASKETBALL

    # ── network ───────────────────────────────────────────────

    def _play_basketball_music(self):
        try:
            if pygame.mixer.get_init():
                path = os.path.join("assets", "sounds", "Flashing Lights.mp3")
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(0.25)
                pygame.mixer.music.play(-1)
        except Exception:
            pass

    def _stop_basketball_music(self):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

    def _network_should_sync(self, dt: float) -> bool:
        """Throttle regular co-op updates while keeping minigames responsive."""
        state = self.state
        hz = 60.0 if state in (GameState.BASKETBALL, GameState.PINGPONG) or self._spectating_pingpong else 30.0
        self._net_sync_accum += dt
        interval = 1.0 / hz
        if self._net_force_sync or self._net_sync_accum >= interval:
            self._net_sync_accum = 0.0
            self._net_force_sync = False
            return True
        return False

    def _build_mission_sync_data(self) -> tuple[dict, tuple]:
        mission_data = {}
        signature = []
        for m_id, m in self.mission_manager.missions.items():
            objectives = [
                {
                    "progress": o.progress,
                    "completed": o.completed,
                    "host_completed": o.host_completed,
                    "client_completed": o.client_completed
                }
                for o in m.objectives
            ]
            mission_data[m_id] = {
                "status": m.status.value,
                "objectives": objectives
            }
            signature.append((
                m_id,
                m.status.value,
                tuple((o["progress"], o["completed"], o["host_completed"], o["client_completed"]) for o in objectives)
            ))
        return mission_data, tuple(signature)

    def _build_npc_sync_data(self) -> tuple[list, tuple]:
        npc_sync = []
        signature = []
        for n in self.npc_manager.npcs.values():
            item = (n.id, n.rect.x, n.rect.y, n.direction.value, n.state, n.current_floor)
            npc_sync.append(item)
            signature.append((n.id, n.direction.value, n.state, n.current_floor))
        return npc_sync, tuple(signature)

    def _build_global_sync_data(self) -> dict:
        """Authoritative co-op story/cinematic state owned by the host."""
        return {
            "host_player_level": self.player.level,
            "host_player_xp": self.player.xp,
            "host_player_skill_points": self.player.skill_points,
            "party_exit_cinematic_active": getattr(self, "_party_exit_cinematic_active", False),
            "party_exit_phase": getattr(self, "_party_exit_phase", ""),
            "party_exit_timer": getattr(self, "_party_exit_timer", 0.0),
            "day_number": self.day_number,
            "time_of_day_minutes": self.time_of_day_minutes,
            "day_timer": self.day_timer,
            "current_phase": self.current_phase.value,
            "school_day_ended": self._school_day_ended,
            "main_mission_text": self._current_main_mission_text,
            "day1_story_complete": self._day1_story_complete,
            "day2_story_complete": getattr(self, "_day2_story_complete", False),
            "day3_story_complete": getattr(self, "_day3_story_complete", False),
            "cine_phase": self._cine_phase,
            "cine_dlg_index": self._cine_dlg_index,
            "noah_final_dlg_index": self._noah_final_dlg_index,
            "day_transition_active": self._day_transition_active,
            "day_transition_target_day": self._day_transition_target_day,
            "day_transition_timer": self._day_transition_timer,
            "car_departure_active": self._car_departure_active,
            "car_depart_phase": self._car_depart_phase,
            "car_depart_wx": getattr(self, "_car_depart_wx", float(self._parked_car_rect.centerx)),
            "car_depart_wy": getattr(self, "_car_depart_wy", float(self._parked_car_rect.centery)),
            "ava_rooftop_dialogue_active": getattr(self, "_ava_rooftop_dialogue_active", False),
            "ava_rooftop_dialogue_index": getattr(self, "_ava_rooftop_dialogue_index", 0),
            "ava_rooftop_dialogue_completed": getattr(self, "_ava_rooftop_dialogue_completed", False),
            "ava_rooftop_dialogue_part2_active": getattr(self, "_ava_rooftop_dialogue_part2_active", False),
            "bad_feeling_active": getattr(self, "_bad_feeling_active", False),
            "bad_feeling_index": getattr(self, "_bad_feeling_index", 0),
            "player_bad_feeling_shown": getattr(self, "_player_bad_feeling_shown", False),
            "post_phone_active": getattr(self, "_post_phone_active", False),
            "post_phone_index": getattr(self, "_post_phone_index", 0),
            "ava_phone_on_chair": getattr(self, "_ava_phone_on_chair", False),
            "ava_phone_timer": getattr(self, "_ava_phone_timer", 15.0),
            "ava_phone_timer_active": getattr(self, "_ava_phone_timer_active", False),
            "ava_phone_completed": getattr(self, "_ava_phone_completed", False),
            "final_reveal_started": getattr(self, "_final_reveal_started", False),
            "final_reveal_finished": getattr(self, "_final_reveal_finished", False),
            "final_reveal_active": getattr(self, "_final_reveal_active", False),
            "final_reveal_phase": getattr(self, "_final_reveal_phase", "pan"),
            "final_reveal_index": getattr(self, "_final_reveal_index", 0),
            "final_office_started": getattr(self, "_final_office_started", False),
            "final_office_active": getattr(self, "_final_office_active", False),
            "final_office_index": getattr(self, "_final_office_index", 0),
        }

    def _apply_global_sync_data(self, data: dict):
        if not data:
            return

        # Synchronize player level authoritatively from host
        r_level = data.get("host_player_level")
        if r_level is not None and r_level != self.player.level:
            self.player.level = r_level
            self.player.xp = data.get("host_player_xp", self.player.xp)
            self.player.skill_points = data.get("host_player_skill_points", self.player.skill_points)
            if hasattr(self.ui, 'trigger_level_up'):
                self.ui.trigger_level_up(10)
            self._last_known_level = r_level

        host_day = data.get("day_number", self.day_number)
        if host_day > self.day_number:
            while self.day_number < host_day:
                self._start_next_day()
            self.aiden_phone.update_day_schedule(self.day_number)
            self.lena_phone.update_day_schedule(self.day_number)
            self._net_force_sync = True
        elif host_day < self.day_number:
            self.day_number = host_day
            self.aiden_phone.update_day_schedule(self.day_number)
            self.lena_phone.update_day_schedule(self.day_number)
            if hasattr(self, "schedule_manager"):
                self.schedule_manager.reset_day()
            self._net_force_sync = True

        self.time_of_day_minutes = data.get("time_of_day_minutes", self.time_of_day_minutes)
        self._last_time_minutes = self.time_of_day_minutes
        self.day_timer = data.get("day_timer", self.day_timer)
        self._school_day_ended = data.get("school_day_ended", self._school_day_ended)
        phase_value = data.get("current_phase")
        if phase_value:
            try:
                self.current_phase = DayPhase(phase_value)
            except ValueError:
                pass

        self._current_main_mission_text = data.get("main_mission_text", self._current_main_mission_text)
        self._last_mission_text = self._current_main_mission_text
        self._day1_story_complete = data.get("day1_story_complete", self._day1_story_complete)
        self._day2_story_complete = data.get("day2_story_complete", getattr(self, "_day2_story_complete", False))
        self._day3_story_complete = data.get("day3_story_complete", getattr(self, "_day3_story_complete", False))

        self._cine_phase = data.get("cine_phase", self._cine_phase)
        self._cine_dlg_index = data.get("cine_dlg_index", self._cine_dlg_index)
        self._noah_final_dlg_index = data.get("noah_final_dlg_index", self._noah_final_dlg_index)
        self._day_transition_active = data.get("day_transition_active", self._day_transition_active)
        self._day_transition_target_day = data.get("day_transition_target_day", self._day_transition_target_day)
        self._day_transition_timer = data.get("day_transition_timer", self._day_transition_timer)
        self._car_departure_active = data.get("car_departure_active", self._car_departure_active)
        self._car_depart_phase = data.get("car_depart_phase", self._car_depart_phase)
        self._car_depart_wx = data.get("car_depart_wx", getattr(self, "_car_depart_wx", float(self._parked_car_rect.centerx)))
        self._car_depart_wy = data.get("car_depart_wy", getattr(self, "_car_depart_wy", float(self._parked_car_rect.centery)))

        # Synchronize party exit cinematic
        r_party_exit = data.get("party_exit_cinematic_active", False)
        if r_party_exit and not getattr(self, "_party_exit_cinematic_active", False):
            self._start_party_exit_cinematic()
        
        new_phase = data.get("party_exit_phase", "")
        old_phase = getattr(self, "_party_exit_phase", "")
        if new_phase == "pan_back" and old_phase != "pan_back":
            self._party_exit_cam_origin = (self.camera.offset.x, self.camera.offset.y)
            
        self._party_exit_cinematic_active = r_party_exit
        self._party_exit_phase = new_phase
        self._party_exit_timer = data.get("party_exit_timer", getattr(self, "_party_exit_timer", 0.0))

        self._ava_rooftop_dialogue_completed = data.get("ava_rooftop_dialogue_completed", getattr(self, "_ava_rooftop_dialogue_completed", False))
        self._ava_rooftop_dialogue_part2_active = data.get("ava_rooftop_dialogue_part2_active", getattr(self, "_ava_rooftop_dialogue_part2_active", False))
        if data.get("ava_rooftop_dialogue_active", False) and not getattr(self, "_ava_rooftop_dialogue_active", False):
            if data.get("ava_rooftop_dialogue_part2_active", False):
                self._begin_ava_rooftop_dialogue_part2()
            else:
                self._begin_ava_rooftop_dialogue()
            if (getattr(self, "_pending_dialogue_request", None) or {}).get("special") == "ava_rooftop":
                self._pending_dialogue_request = None
        self._ava_rooftop_dialogue_active = data.get("ava_rooftop_dialogue_active", getattr(self, "_ava_rooftop_dialogue_active", False))
        self._ava_rooftop_dialogue_index = data.get("ava_rooftop_dialogue_index", getattr(self, "_ava_rooftop_dialogue_index", 0))
        if self._ava_rooftop_dialogue_completed and (getattr(self, "_pending_dialogue_request", None) or {}).get("special") == "ava_rooftop":
            self._pending_dialogue_request = None

        if data.get("bad_feeling_active", False) and not getattr(self, "_bad_feeling_active", False):
            self._show_bad_feeling_monologue()
        self._bad_feeling_active = data.get("bad_feeling_active", getattr(self, "_bad_feeling_active", False))
        self._bad_feeling_index = data.get("bad_feeling_index", getattr(self, "_bad_feeling_index", 0))
        self._player_bad_feeling_shown = data.get("player_bad_feeling_shown", getattr(self, "_player_bad_feeling_shown", False))

        if data.get("post_phone_active", False) and not getattr(self, "_post_phone_active", False):
            self._show_post_phone_monologue()
        self._post_phone_active = data.get("post_phone_active", getattr(self, "_post_phone_active", False))
        self._post_phone_index = data.get("post_phone_index", getattr(self, "_post_phone_index", 0))
        self._ava_phone_on_chair = data.get("ava_phone_on_chair", getattr(self, "_ava_phone_on_chair", False))
        self._ava_phone_timer = data.get("ava_phone_timer", getattr(self, "_ava_phone_timer", 15.0))
        self._ava_phone_timer_active = data.get("ava_phone_timer_active", getattr(self, "_ava_phone_timer_active", False))
        self._ava_phone_completed = data.get("ava_phone_completed", getattr(self, "_ava_phone_completed", False))

        self._final_reveal_started = data.get("final_reveal_started", getattr(self, "_final_reveal_started", False))
        self._final_reveal_finished = data.get("final_reveal_finished", getattr(self, "_final_reveal_finished", False))
        self._final_reveal_active = data.get("final_reveal_active", getattr(self, "_final_reveal_active", False))
        self._final_reveal_phase = data.get("final_reveal_phase", getattr(self, "_final_reveal_phase", "pan"))
        self._final_reveal_index = data.get("final_reveal_index", getattr(self, "_final_reveal_index", 0))
        if self._final_reveal_active and not getattr(self, "_final_reveal_lines", None):
            self._start_final_reveal()
            self._final_reveal_active = data.get("final_reveal_active", True)
            self._final_reveal_phase = data.get("final_reveal_phase", self._final_reveal_phase)
            self._final_reveal_index = data.get("final_reveal_index", self._final_reveal_index)

        self._final_office_started = data.get("final_office_started", getattr(self, "_final_office_started", False))
        self._final_office_active = data.get("final_office_active", getattr(self, "_final_office_active", False))
        self._final_office_index = data.get("final_office_index", getattr(self, "_final_office_index", 0))
        if self._final_office_active and not getattr(self, "_final_office_lines", None):
            self._start_final_office_scene()
            self._final_office_active = data.get("final_office_active", True)
            self._final_office_index = data.get("final_office_index", self._final_office_index)

    def _sync_network(self, dt: float = 0.016):
        if not self.network:
            return
        self._net_mission_refresh_timer += dt
        self._net_npc_refresh_timer += dt
        if not self._network_should_sync(dt):
            return
        try:
            player_data = self.player.to_dict()
            player_data["floor"] = self.current_floor
            player_data["game_state"] = self.state.value
            
            # Coop vote sync
            player_data["dialogue_continue"] = self.dialogue_continue_voted
            player_data["cinematic_continue"] = self.cinematic_continue_voted
            player_data["cinematic_skip"] = self.cinematic_skip_voted
            player_data["request_dialogue"] = self._pending_dialogue_request
            player_data["car_departure_voted"] = self.car_departure_voted
            player_data["day1_story_complete"] = self._day1_story_complete
            player_data["day2_story_complete"] = getattr(self, "_day2_story_complete", False)
            player_data["day3_story_complete"] = getattr(self, "_day3_story_complete", False)
            
            if self.state == GameState.BASKETBALL:
                bb_data = {
                    "z": self.basketball.player_z,
                    "shoot_bar": self.basketball.shoot_bar,
                    "shooting": self.basketball.shooting,
                    "blocking": self.basketball.blocking,
                    "pass_request": getattr(self.basketball, "pass_requested", False),
                }
                if getattr(self.basketball, "pass_requested", False):
                    self.basketball.pass_requested = False
                if self.is_host:
                    bb_data.update({
                        "ball_x": self.basketball.ball_x,
                        "ball_y": self.basketball.ball_y,
                        "ball_z": self.basketball.ball_z,
                        "ball_held_by": self.basketball.ball_held_by,
                        "possession": getattr(self.basketball, "possession", None),
                        "pass_in_flight": getattr(self.basketball, "pass_in_flight", False),
                        "opp_x": self.basketball.opponent.rect.centerx if self.basketball.opponent else 0,
                        "opp_y": self.basketball.opponent.rect.centery if self.basketball.opponent else 0,
                        "opp_z": self.basketball.opp_z,
                        "opp_shooting": getattr(self.basketball, "opp_shooting", False),
                        "opp_shoot_anim": getattr(self.basketball, "opp_shoot_anim", -1.0),
                        "opp2_x": self.basketball.opp2.rect.centerx if getattr(self.basketball, "opp2", None) else 0,
                        "opp2_y": self.basketball.opp2.rect.centery if getattr(self.basketball, "opp2", None) else 0,
                        "opp2_z": getattr(self.basketball, "opp2_z", 0),
                        "opp2_shooting": getattr(self.basketball, "opp2_shooting", False),
                        "opp2_shoot_anim": getattr(self.basketball, "opp2_shoot_anim", -1.0),
                        "p_score": self.basketball.player_score,
                        "o_score": self.basketball.opp_score,
                        "shake_timer": getattr(self.basketball, "shake_timer", 0.0),
                        "shake_intensity": getattr(self.basketball, "shake_intensity", 0),
                    })
                player_data["bb_data"] = bb_data
            
            # Host: sync dialogue, mission and cinematic details
            if self.is_host:
                if self.state == GameState.DIALOGUE and self.dialogue_system.active_tree:
                    # Find dialogue_id of active tree
                    active_id = None
                    for k, v in self.dialogue_system.trees.items():
                        if v == self.dialogue_system.active_tree:
                            active_id = k
                            break
                    player_data["active_dialogue_id"] = active_id
                    player_data["active_npc_id"] = self.dialogue_system.npc.id if self.dialogue_system.npc else None
                    player_data["active_node_id"] = self.dialogue_system.active_tree.current.id if self.dialogue_system.active_tree else None
                    player_data["dialogue_choice_index"] = self.dialogue_system._choice_index
                else:
                    player_data["active_dialogue_id"] = None
                    player_data["active_npc_id"] = None
                    player_data["active_node_id"] = None
                    player_data["dialogue_choice_index"] = 0

                # Sync mission data only when it changes, with a periodic refresh for safety.
                mission_data, mission_sig = self._build_mission_sync_data()
                mission_refresh_due = self._net_mission_refresh_timer >= self._net_mission_refresh_interval
                if mission_sig != self._net_last_mission_sig or mission_refresh_due:
                    player_data["mission_data"] = mission_data
                    self._net_last_mission_sig = mission_sig
                    self._net_mission_refresh_timer = 0.0
                player_data["main_mission_text"] = self._current_main_mission_text

                # Sync cinematic variables
                player_data["global_sync"] = self._build_global_sync_data()
                player_data["cine_phase"] = self._cine_phase
                player_data["cine_dlg_index"] = self._cine_dlg_index
                player_data["noah_final_dlg_index"] = self._noah_final_dlg_index
            
            # Host: also send NPC data for synchronization (skip in BASKETBALL state to save bandwidth & CPU)
            if self.is_host and self.state != GameState.BASKETBALL:
                # NPCs are the heaviest regular payload; send changed snapshots or periodic refreshes.
                npc_sync, npc_sig = self._build_npc_sync_data()
                npc_refresh_due = self._net_npc_refresh_timer >= self._net_npc_refresh_interval
                if npc_sig != self._net_last_npc_sig or npc_refresh_due:
                    player_data["npc_sync"] = npc_sync
                    self._net_last_npc_sig = npc_sig
                    self._net_npc_refresh_timer = 0.0

            # (Ping-pong spectator system removed, no pp_data packed)

            # Pack client mission progress to host
            if not self.is_host:
                client_mission_progress = {}
                for m_id, m in self.mission_manager.missions.items():
                    if m.status.value == "active":
                        client_mission_progress[m_id] = [o.client_completed for o in m.objectives]
                player_data["client_mission_progress"] = client_mission_progress
                player_data["client_viewed_oscar_post"] = self._client_viewed_oscar_post
                player_data["mainframe_completed"] = getattr(self, "_net_mainframe_completed", False)

            # Pack ping pong match won & cheers
            player_data["pp_match_won"] = self._pingpong_match_won
            player_data["pp_exit_voted"] = self._pingpong_exit_voted
            if self._pending_pp_cheer:
                player_data["pp_cheer"] = self._pending_pp_cheer
                self._pending_pp_cheer = False
            else:
                player_data["pp_cheer"] = None

            self.network.send_player_update(player_data)
            remote = self.network.get_remote_data()
            
            if remote and self.remote_player:
                self._last_remote_data = remote
                
                if self.is_host:
                    c_m_progress = remote.get("client_mission_progress")
                    if c_m_progress:
                        for m_id, m_objectives in c_m_progress.items():
                            m = self.mission_manager.missions.get(m_id)
                            if m and m.status.value == "active":
                                for idx, val in enumerate(m_objectives):
                                    if idx < len(m.objectives):
                                        m.objectives[idx].client_completed = val
                    self._remote_client_viewed_oscar_post = remote.get("client_viewed_oscar_post", False)
                    if remote.get("mainframe_completed"):
                        self._exit_mainframe_success()

                r_state = remote.get("game_state")
                self._remote_game_state = r_state
                
                # Update remote votes
                self.remote_dialogue_continue = remote.get("dialogue_continue", False)
                self.remote_cinematic_continue = remote.get("cinematic_continue", False)
                self.remote_cinematic_skip = remote.get("cinematic_skip", False)
                self.remote_car_departure_voted = remote.get("car_departure_voted", False)
                self._remote_day1_story_complete = remote.get("day1_story_complete", False)
                self._remote_day2_story_complete = remote.get("day2_story_complete", False)
                self._remote_day3_story_complete = remote.get("day3_story_complete", False)
                if not self.is_host:
                    self._apply_global_sync_data(remote.get("global_sync", {}))
                
                # Auto teleport to basketball (only client follows host)
                if not self.is_host and r_state == GameState.BASKETBALL.value and self.state != GameState.BASKETBALL:
                    self._apply_dialogue_result({"start_basketball": True})

                # Auto teleport to pingpong (only client follows host)
                if not self.is_host and r_state == GameState.PINGPONG.value and self.state != GameState.PINGPONG and not self._pingpong_match_won:
                    self._apply_dialogue_result({"start_pingpong": True})
                
                # Auto exit basketball (client follows host out of the game)
                if not self.is_host and self.state == GameState.BASKETBALL and r_state != GameState.BASKETBALL.value:
                    player_won = self.basketball.player_score > self.basketball.opp_score
                    self.basketball.finished = False
                    if hasattr(self.basketball, 'floor') and self.basketball.floor:
                        self.basketball.floor.hide_hoops = False
                    self.basketball.reset()
                    self._stop_basketball_music()
                    self.state = GameState.PLAYING
                    if player_won:
                        self._begin_marcus_win_dialogue()
                
                if self.state == GameState.BASKETBALL and "bb_data" in remote:
                    if hasattr(self, "basketball"):
                        self.basketball.sync_state(remote["bb_data"], self.is_host)
                
                # Apply dialogue/cinematic consensus voting resolution (HOST ONLY)
                if self.is_host:
                    if self.state == GameState.DIALOGUE and self.dialogue_system.active_tree:
                        if self.dialogue_continue_voted and self.remote_dialogue_continue:
                            choices = self.dialogue_system.active_tree.get_choices()
                            if choices:
                                cons = self.dialogue_system.active_tree.make_choice(self.dialogue_system._choice_index)
                                if cons:
                                    self.dialogue_system._all_consequences.append(cons)
                                self.dialogue_system._choice_index = 0
                                if not self.dialogue_system.active_tree.advance(self.dialogue_system._all_consequences):
                                    self.dialogue_system._finish()
                            else:
                                if not self.dialogue_system.active_tree.advance(self.dialogue_system._all_consequences):
                                    self.dialogue_system._finish()
                            self.dialogue_continue_voted = False

                    if self.state == GameState.INTRO_CINEMATIC and self._cine_phase in ("dialogue", "final_dialogue"):
                        if self.cinematic_continue_voted and self.remote_cinematic_continue:
                            self._advance_cinematic_dialogue()
                            self.cinematic_continue_voted = False

                    if self.state == GameState.INTRO_CINEMATIC:
                        if self.cinematic_skip_voted and self.remote_cinematic_skip:
                            self._skip_cinematic()
                            self.cinematic_skip_voted = False

                # Bus Travel/Day transition consensus resolution (BOTH - but triggered cooperatively)
                if self.car_departure_voted and self.remote_car_departure_voted:
                    self._car_panel_active = False
                    self._start_car_departure()
                    self.car_departure_voted = False
                
                # Client-specific authoritative sync from Host
                if not self.is_host:
                    # Sync dialogue state
                    r_dlg_id = remote.get("active_dialogue_id")
                    r_npc_id = remote.get("active_npc_id")
                    r_node_id = remote.get("active_node_id")
                    r_choice_idx = remote.get("dialogue_choice_index", 0)

                    if r_dlg_id:
                        if self.state != GameState.DIALOGUE:
                            npc = self.npc_manager.get_npc_by_id(r_npc_id) if r_npc_id else None
                            self.dialogue_system.start_dialogue(r_dlg_id, npc, self.player, self.reputation)
                            self.state = GameState.DIALOGUE
                            self.player.vx = 0
                            self.player.vy = 0
                            self.player._dashing = False
                            self._pending_dialogue_request = None
                        
                        # Clear Client's dialogue continue vote if node changed
                        if self.dialogue_system.active_tree and r_node_id and self.dialogue_system.active_tree.current.id != r_node_id:
                            self.dialogue_continue_voted = False
                            
                        if self.dialogue_system.active_tree and r_node_id:
                            self.dialogue_system.active_tree.set_current_by_id(r_node_id)
                        self.dialogue_system._choice_index = r_choice_idx
                    else:
                        if self.state == GameState.DIALOGUE:
                            self.dialogue_system.active_tree = None
                            self.state = GameState.PLAYING

                    # Sync mission data
                    if "mission_data" in remote:
                        for m_id, m_state in remote["mission_data"].items():
                            m = self.mission_manager.missions.get(m_id)
                            if m:
                                from settings import MissionStatus
                                old_status = m.status
                                m.status = MissionStatus(m_state["status"])
                                for idx, obj_state in enumerate(m_state["objectives"]):
                                    if idx < len(m.objectives):
                                        m.objectives[idx].progress = obj_state["progress"]
                                        m.objectives[idx].completed = obj_state["completed"]
                                        # Keep local client_completed if we already did it, until host merges it
                                        if obj_state.get("client_completed"):
                                            m.objectives[idx].client_completed = True
                                        m.objectives[idx].host_completed = obj_state.get("host_completed", False)
                                
                                if old_status == MissionStatus.ACTIVE and m.status == MissionStatus.COMPLETED:
                                    self.mission_manager.completed_ids.add(m_id)
                                    self.mission_manager._refresh_availability()
                                    if m_id == "mission_high_school_mainframe":
                                        self._net_mainframe_completed = False
                                    rewards = m.rewards
                                    if rewards:
                                        self._apply_rewards(rewards)
                                        msg = self.mission_manager.get_motivational_message()
                                        self.ui.show_notification(f"✅ Mission complete! {msg}", NOTIF_SUCCESS, 5.0)
                                        # Auto-activate newly available missions
                                        for new_m in self.mission_manager.get_available():
                                            self.mission_manager.activate_mission(new_m.id)
                                            if new_m.id == "mission_talk_ava_rooftop":
                                                self._current_main_mission_text = "Mission 11: Find Ava Thompson at the rooftop party."
                                            elif new_m.id == "mission_check_ava_phone":
                                                self._current_main_mission_text = "Mission 12: Check Ava's phone before she comes back! (15 seconds)"
                                            elif new_m.id == "mission_final_showdown":
                                                self._current_main_mission_text = "Mission 13: Go to the Basement and see what they're plotting!"
                                        
                    if "main_mission_text" in remote:
                        self._current_main_mission_text = remote["main_mission_text"]
                                        
                    # Sync intro cinematic variables
                    self._cine_phase = remote.get("cine_phase", self._cine_phase)
                    
                    r_cine_dlg_idx = remote.get("cine_dlg_index")
                    r_noah_final_idx = remote.get("noah_final_dlg_index")
                    
                    if r_cine_dlg_idx is not None and r_cine_dlg_idx != self._cine_dlg_index:
                        self.cinematic_continue_voted = False
                    self._cine_dlg_index = remote.get("cine_dlg_index", self._cine_dlg_index)
                    
                    if r_noah_final_idx is not None and r_noah_final_idx != self._noah_final_dlg_index:
                        self.cinematic_continue_voted = False
                    self._noah_final_dlg_index = remote.get("noah_final_dlg_index", self._noah_final_dlg_index)

                    # Authoritative state transition for intro cinematic skip/completion
                    if self.state == GameState.INTRO_CINEMATIC and r_state == GameState.PLAYING.value:
                        self._skip_cinematic()
                        self.cinematic_skip_voted = False
                        self.cinematic_continue_voted = False

                else:
                    # Host-specific processing: handle dialogue request from Client
                    r_req_dlg = remote.get("request_dialogue")
                    if r_req_dlg and self.state != GameState.DIALOGUE:
                        if r_req_dlg.get("special") == "ava_rooftop":
                            if (not getattr(self, "_ava_rooftop_dialogue_active", False)
                                    and self.current_floor == FLOOR_ROOFTOP
                                    and self.day_number >= 4
                                    and not getattr(self, "_ava_rooftop_dialogue_completed", False)):
                                self._begin_ava_rooftop_dialogue()
                                self.player.vx = 0
                                self.player.vy = 0
                                self.player._dashing = False
                        else:
                            r_dlg_id = r_req_dlg["dialogue_id"]
                            r_npc_id = r_req_dlg["npc_id"]
                            npc = self.npc_manager.get_npc_by_id(r_npc_id) if r_npc_id else None
                            self.dialogue_system.start_dialogue(r_dlg_id, npc, self.player, self.reputation)
                            self.state = GameState.DIALOGUE
                            self.mission_manager.advance_objective_event("talk_to", r_npc_id)
                            self.player.vx = 0
                            self.player.vy = 0
                            self.player._dashing = False

                # Auto teleport Client to Host's floor to keep them in perfect sync (decoupled in floor-free coop)
                # if not self.is_host and self.state not in (GameState.PINGPONG, GameState.BASKETBALL):
                #     rf = remote.get("floor", 1)
                #     if rf != self.current_floor:
                #         self._go_to_floor(rf, remote.get("x", self.player.rect.centerx), remote.get("y", self.player.rect.centery))

                # Unpack ping pong sync data
                self._remote_pingpong_match_won = remote.get("pp_match_won", False)
                self._remote_pingpong_exit_voted = remote.get("pp_exit_voted", False)
                r_cheer = remote.get("pp_cheer")
                if r_cheer and self.state == GameState.PINGPONG:
                    self.pingpong.spawn_cheer(r_cheer, is_local=False)

                # Client: Apply NPC updates from host
                if not self.is_host and "npc_sync" in remote:
                    for item in remote["npc_sync"]:
                        if len(item) == 6:
                            nid, nx, ny, ndir, nstate, nfloor = item
                        else:
                            nid, nx, ny, ndir, nstate = item
                            nfloor = None
                        npc = self.npc_manager.get_npc_by_id(nid)
                        if npc:
                            floor_changed = nfloor is not None and npc.current_floor != nfloor
                            far_away = abs(nx - npc.rect.x) > 600 or abs(ny - npc.rect.y) > 600
                            if floor_changed or far_away:
                                npc.rect.x = nx
                                npc.rect.y = ny
                            else:
                                npc.rect.x += int((nx - npc.rect.x) * 0.5)
                                npc.rect.y += int((ny - npc.rect.y) * 0.5)
                            from settings import Direction
                            try:
                                npc.direction = Direction(ndir)
                            except ValueError:
                                pass
                            npc.state = nstate
                            if nfloor is not None:
                                npc.current_floor = nfloor

            # Continuous remote player logic running every frame
            if getattr(self, "_last_remote_data", None) and self.remote_player:
                r_data = self._last_remote_data
                
                # Apply floor-specific decay for remote player
                in_main_building = self.current_floor in (FLOOR_1F, FLOOR_2F)
                decay = 2 if in_main_building else 1
                
                self.remote_player.update_remote(r_data, dt, trail_decay=decay)
                rf = r_data.get("floor", 1)
                self.remote_player.current_floor = rf

                # Update WorldMap with remote player position
                if hasattr(self, "world_map"):
                    rname = "Lena" if self.player.character.value == "aiden" else "Aiden"
                    self.world_map.set_remote_player_pos(rf, self.remote_player.rect.centerx, self.remote_player.rect.centery, rname)

                # Update health/stamina if provided
                self.remote_player.health = r_data.get("health", self.remote_player.health)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────
    #  DRAW
    # ──────────────────────────────────────────────────────────

    def _draw(self):
        self.screen.fill(BLACK)

        draw_table = {
            GameState.PLAYING:           self._draw_world,
            GameState.COMBAT:            lambda: (self._draw_world(), self.combat_system.draw(self.screen, self.camera)),
            GameState.HACKING:           lambda: self.hacking_game.draw(self.screen),
            GameState.DIALOGUE:          lambda: (self._draw_world(), self.dialogue_system.draw(self.screen)),
            GameState.SOCIAL_INTERACTION: lambda: (self._draw_world(), self.social_ui.draw(self.screen)),
            GameState.PINGPONG:          lambda: self.pingpong.draw(self.screen),
            GameState.BASKETBALL:        lambda: (self._draw_world(), self.basketball.draw(self.screen, self.camera)),
            GameState.TRADING:           lambda: (self._draw_world(), self.trade_system.draw(self.screen)),
            GameState.PAUSED:            lambda: (
                (self._draw_world(), self.basketball.draw(self.screen, self.camera)) if getattr(self, 'previous_state', None) == GameState.BASKETBALL else self._draw_world(),
                self.ui.draw_pause_menu(self.screen, getattr(self, 'pause_sel', 0), self.pause_options)
            ),
            GameState.MISSION_SELECT:    lambda: (
                (self._draw_world(), self.basketball.draw(self.screen, self.camera)) if getattr(self, 'previous_state', None) == GameState.BASKETBALL else self._draw_world(),
                self.ui.draw_mission_select_menu(
                    self.screen,
                    getattr(self, 'mission_select_sel', 0),
                    getattr(self, 'mission_select_confirm', False),
                    getattr(self, 'mission_confirm_sel', 0),
                    self._get_mission_select_list(),
                    self.mission_manager
                )
            ),
            GameState.INVENTORY_SCREEN:  lambda: self.ui.draw_inventory(self.screen, self.inventory),
            GameState.SKILL_TREE_SCREEN: lambda: self.ui.draw_skill_tree(self.screen, self.player.skill_tree, self.player),
            GameState.HELP:              lambda: self.ui.draw_help_screen(self.screen, self.character),
            GameState.WALLET:            lambda: (
                self._draw_world(),
                self.ui.draw_wallet(
                    self.screen,
                    self.active_wallet_item,
                    self.character,
                    self.controller.connected if self.controller else False,
                    self.wallet_focus_item if (self.controller and self.controller.connected) else None,
                    self._get_yearbook_data() if self.active_wallet_item == "yearbook" else None,
                    player=self.player,
                    inventory=self.inventory,
                ),
            ),
            GameState.MAINFRAME:         lambda: (self._draw_world(), self.ui.draw_mainframe(self.screen, self)),
            GameState.GAME_OVER:         lambda: self.ui.draw_game_over(self.screen, self.reputation.calculate_ending()),
            GameState.MAP:               lambda: self._draw_map(),

            GameState.INTRO_CINEMATIC:    lambda: self._draw_cinematic(),
        }
        fn = draw_table.get(self.state, self._draw_world)
        fn()

        if getattr(self, "phone", None) and self.phone.is_visible and self.phone.shows_embedded_world_map():
            self._draw_phone_world_map_layer()

        # HUD overlay
        if (
            self.state in (GameState.PLAYING, GameState.COMBAT, GameState.DIALOGUE, GameState.SOCIAL_INTERACTION)
            and not self.phone.is_fullscreen()
        ):
            floor = self.school_map.get_floor(self.current_floor)
            room = floor.get_room_at(
                self.player.rect.centerx,
                self.player.rect.centery,
            ) if floor else None
            self.ui.draw_hud(self.screen, self.player,
                             self.current_phase, self.day_number,
                             floor, room, self.reputation,
                             self._get_time_string(),
                             hud_focus=self._hud_focus,
                             car_rect=self._parked_car_rect if self.current_floor == 0 else None,
                             )
            # Phone HUD icon with unread badge (delegated to Phone)
            self.phone.draw_hud_icon(
                self.screen,
                self.ui.phone_icon_rect,
                unread=self.phone.unread_count,
            )
            # Building entry prompt
            if self.current_floor == FLOOR_CAMPUS and self._entry_prompt_target:
                self._draw_entry_prompt(self._entry_prompt_target["label"])
            if getattr(self, '_computer_prompt_active', False):
                is_controller = bool(self.controller and self.controller.connected and self.controller.last_input_method == "controller")
                key_hint = "[A]" if is_controller else "[ENTER]"
                self._draw_prompt_box(f"Press {key_hint} to turn on the computer")
                
            # Custom mission text overlay (matches cinematic mission box)
            if getattr(self, "_current_main_mission_text", None):
                self._draw_mission_box(self._current_main_mission_text)
        # Notifications always on top (suppress during cinematic)
        if self.state != GameState.INTRO_CINEMATIC:
            self.ui.draw_notifications(self.screen)

        self.phone.set_hud_anchor(self.ui.phone_icon_rect)
        self.phone.draw()

        if getattr(self, "_oscar_win_dialogue_active", False):
            self._draw_oscar_win_dialogue()
        if getattr(self, "_marcus_win_dialogue_active", False):
            self._draw_marcus_win_dialogue()
        if getattr(self, "_ava_rooftop_dialogue_active", False):
            self._draw_rooftop_party_dialogue()
        if getattr(self, "_bad_feeling_active", False):
            self._draw_rooftop_party_dialogue(feeling=True)
        if getattr(self, "_post_phone_active", False):
            self._draw_rooftop_party_dialogue(post_phone=True)
        if getattr(self, "_final_reveal_active", False) and getattr(self, "_final_reveal_phase", "") == "dialogue":
            self._draw_final_reveal_dialogue()
        if getattr(self, "_final_office_active", False):
            self._draw_final_office_dialogue()
        if getattr(self, "_ava_phone_spying", False):
            self._draw_ava_phone_spy_ui()

        # ── Fullscreen overlays (drawn on top of everything) ──
        if self._day_transition_active:
            self._draw_day_transition()
        elif self._car_panel_active:
            self._draw_car_panel()

        pygame.display.flip()

    def _draw_world(self):
        """Render floor, NPCs, player."""
        # Smooth camera zoom
        target_zoom = 1.0 if self.current_floor == FLOOR_CAMPUS else 1.25
        current_zoom = getattr(self.camera, 'zoom', 1.0)
        if abs(current_zoom - target_zoom) > 0.01:
            new_zoom = current_zoom + (target_zoom - current_zoom) * 0.05
        else:
            new_zoom = target_zoom
            
        self.camera.set_zoom(new_zoom)
        
        if self.camera.zoom != 1.0:
            view_w, view_h = self.camera.view_w, self.camera.view_h
            if not hasattr(self, '_zoom_surface') or self._zoom_surface.get_size() != (view_w, view_h):
                self._zoom_surface = pygame.Surface((view_w, view_h))
            target_surf = self._zoom_surface
            target_surf.fill(BLACK)
        else:
            target_surf = self.screen

        floor = self.school_map.get_floor(self.current_floor)
        if floor:
            npcs = self.npc_manager.get_npcs_on_floor(self.current_floor)
            floor.draw(target_surf, self.camera, self.player, npcs, draw_furniture=False)

        # Draw parked car on campus
        if self.current_floor == FLOOR_CAMPUS:
            self._draw_parked_car(target_surf)
            self._draw_extra_parked_cars(target_surf)

        # Draw rooftop party elements (Day 3 event)
        if self.day_number >= 3:
            self.rooftop_party.draw_on_rooftop(target_surf, self.camera, self.current_floor)

        if floor and hasattr(floor, 'draw_foreground'):
            floor.draw_foreground(target_surf, self.camera, self.player)

        # ── Y-SORTED RENDER LOOP (Furniture, NPCs, Player) ──
        drawables = []
        if floor:
            for furn in floor.furniture:
                drawables.append({
                    "type": "furn",
                    "obj": furn,
                    "bottom": furn["rect"].bottom
                })

        for npc in self.npc_manager.get_npcs_on_floor(self.current_floor):
            if self._is_npc_on_camera(npc):
                if self.state == GameState.BASKETBALL:
                    if hasattr(self.basketball, "opponent") and npc == self.basketball.opponent:
                        continue
                    if getattr(self.basketball, "is_coop", False):
                        if npc == getattr(self.basketball, "ally", None) or npc == getattr(self.basketball, "opp2", None):
                            continue
                drawables.append({
                    "type": "npc",
                    "obj": npc,
                    "bottom": npc.rect.bottom
                })

        if not (self._car_departure_active and self._car_depart_phase == "drive_away"):
            if self.state != GameState.BASKETBALL:
                drawables.append({
                    "type": "player",
                    "obj": self.player,
                    "bottom": self.player.rect.bottom
                })
            if getattr(self, "remote_player", None):
                # Ghosting bug fix: only draw if on same floor
                if self.remote_player.current_floor == self.current_floor and self.state != GameState.BASKETBALL:
                    drawables.append({
                        "type": "remote_player",
                        "obj": self.remote_player,
                        "bottom": self.remote_player.rect.bottom
                    })

        drawables.sort(key=lambda d: d["bottom"])

        for item in drawables:
            if item["type"] == "furn":
                floor.draw_single_furn(target_surf, self.camera, item["obj"])
            elif item["type"] == "npc":
                item["obj"].draw(target_surf, self.camera)
            elif item["type"] == "player":
                item["obj"].draw(target_surf, self.camera)
            elif item["type"] == "remote_player":
                item["obj"].draw(target_surf, self.camera)

        # Draw interaction prompt for nearest NPC in range
        if self.state == GameState.PLAYING:
            nearest_npc = self._nearest_npc(NPC_INTERACTION_RANGE)
            if nearest_npc:
                nearest_npc.draw_interaction_prompt(target_surf, self.camera)

        if self.current_floor == FLOOR_1F:
            m_obj = self.mission_manager.missions.get("mission_high_school_mainframe")
            if m_obj and m_obj.status == MissionStatus.ACTIVE:
                comp_rect = self.camera.apply_rect(pygame.Rect(90, 320, 90, 64))
                pulse = (math.sin(pygame.time.get_ticks() * 0.005) + 1) * 0.5
                x_col = (255, int(50 + 100 * pulse), 50)
                pygame.draw.line(target_surf, x_col, comp_rect.topleft, comp_rect.bottomright, 6)
                pygame.draw.line(target_surf, x_col, comp_rect.topright, comp_rect.bottomleft, 6)

        if floor and hasattr(floor, 'draw_roofs'):
            floor.draw_roofs(target_surf, self.camera, self.player)

        # ── Draw Top Layer (Trees, etc.) ──
        if floor and hasattr(floor, 'draw_top_layer'):
            floor.draw_top_layer(target_surf, self.camera)
            
        # Basement lighting overlay (covers walls, NPCs, everything)
        if self.current_floor == FLOOR_BASEMENT and floor and not self._should_disable_basement_lighting():
             floor._draw_basement_lighting(target_surf, self.camera, self.player)

        # Draw Ava's phone sitting on a chair (Rooftop, Day 4)
        if self.current_floor == FLOOR_ROOFTOP:
            self._draw_ava_phone_on_chair(target_surf, self.camera)
            self._apply_disco_filter(target_surf)
            
        if self.camera.zoom != 1.0:
            # Scale up to screen size and blit
            scaled = pygame.transform.scale(target_surf, (SCREEN_WIDTH, SCREEN_HEIGHT))
            self.screen.blit(scaled, (0, 0))

    def _apply_disco_filter(self, surface: pygame.Surface):
        """Draw dynamic shifting ambient lights and moving spotlights on the rooftop."""
        import math
        ticks = pygame.time.get_ticks()
        
        # 1. Shifting ambient color overlay
        cycle = (ticks * 0.001) % (2 * math.pi)
        r = int(127 + 127 * math.sin(cycle))
        g = int(50 + 50 * math.cos(cycle * 1.5))
        b = int(127 + 127 * math.sin(cycle + 2.0))
        
        ambient_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        ambient_surf.fill((r, g, b, 45))
        surface.blit(ambient_surf, (0, 0))
        
        # 2. Moving colored spotlights with soft radial concentric circles
        w, h = surface.get_size()
        cx, cy = w // 2, h // 2
        
        spotlights = [
            ((255, 0, 128), 120, ticks * 0.002, 0.4), # pink/magenta
            ((0, 255, 255), 140, ticks * -0.0015, 0.5), # cyan
            ((255, 255, 0), 100, ticks * 0.0025 + 1.0, 0.3) # yellow
        ]
        
        light_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for color, radius, angle, speed in spotlights:
            orbit_r = min(w, h) // 4
            lx = cx + int(math.cos(angle) * orbit_r)
            ly = cy + int(math.sin(angle * 1.2) * orbit_r)
            
            # Simulated gradient with concentric circles of decreasing alpha
            for r_offset in range(radius, 0, -8):
                alpha = int(35 * (1 - r_offset / radius))
                if alpha > 0:
                    pygame.draw.circle(light_surf, (*color, alpha), (lx, ly), r_offset)
                    
        surface.blit(light_surf, (0, 0))

    def _place_populars_on_rooftop(self):
        """Teleport all popular NPCs (except Ava, Marcus, Noah) to the rooftop and scatter them with free-roaming enabled."""
        from settings import FLOOR_ROOFTOP, SocialGroup
        import random
        
        excluded = {"npc_ava_thompson", "npc_marcus", "npc_noah_carter"}
        npcs_to_teleport = [
            npc for npc in self.npc_manager.npcs.values()
            if npc.group == SocialGroup.POPULARS and npc.id not in excluded
        ]
        
        for npc in npcs_to_teleport:
            npc.current_floor = FLOOR_ROOFTOP
            npc.ai_enabled = True # Keep wandering/AI active
            npc.ignore_schedule = True
            
            # Place randomly in rt_terrace: x in [1250, 2350], y in [550, 1650]
            placed = False
            for _ in range(100):
                rx = random.randint(1250, 2350)
                ry = random.randint(550, 1650)
                rect = pygame.Rect(rx, ry, npc.rect.width, npc.rect.height)
                
                # Check collision with floor walls/furniture
                floor = self.school_map.get_floor(FLOOR_ROOFTOP)
                collides = False
                if floor:
                    for wall in floor.walls:
                        if rect.colliderect(wall):
                            collides = True
                            break
                    if not collides:
                        for furn in floor.furniture:
                            if rect.colliderect(furn["rect"]):
                                collides = True
                                break
                if not collides:
                    npc.rect.x = rx
                    npc.rect.y = ry
                    placed = True
                    break
            
            if not placed:
                npc.rect.x = random.randint(1300, 2200)
                npc.rect.y = random.randint(600, 1500)

    def _reset_populars_from_rooftop(self):
        """Reset popular NPCs back to their normal schedules."""
        from settings import SocialGroup
        excluded = {"npc_ava_thompson", "npc_marcus", "npc_noah_carter"}
        for npc in self.npc_manager.npcs.values():
            if npc.group == SocialGroup.POPULARS and npc.id not in excluded:
                npc.ignore_schedule = False
                npc.ai_enabled = True
        
        # Force schedule update on next frame by resetting current block
        if hasattr(self, 'schedule_manager'):
            self.schedule_manager._current_block = None

    def _draw_entry_prompt(self, building_name: str):
        panel_w, panel_h = 520, 54
        panel = pygame.Rect(
            self.screen.get_width() // 2 - panel_w // 2,
            self.screen.get_height() - 120,
            panel_w,
            panel_h,
        )
        pygame.draw.rect(self.screen, (26, 30, 38), panel, border_radius=8)
        pygame.draw.rect(self.screen, (160, 170, 190), panel, 2, border_radius=8)
        is_controller = bool(self.controller and self.controller.connected and self.controller.last_input_method == "controller")
        key_hint = "[A]" if is_controller else "[E]"
        text = f"Enter {building_name}?  {key_hint} yes  |  move away to cancel"
        fnt = pygame.font.Font(VT323_PATH, 22)
        surf = fnt.render(text, True, (232, 236, 245))
        self.screen.blit(surf, (panel.centerx - surf.get_width() // 2,
                                panel.centery - surf.get_height() // 2))

    def _draw_prompt_box(self, text: str):
        panel_w, panel_h = 520, 54
        panel = pygame.Rect(
            self.screen.get_width() // 2 - panel_w // 2,
            self.screen.get_height() - 120,
            panel_w,
            panel_h,
        )
        pygame.draw.rect(self.screen, (26, 30, 38), panel, border_radius=8)
        pygame.draw.rect(self.screen, (160, 170, 190), panel, 2, border_radius=8)
        fnt = pygame.font.Font(VT323_PATH, 22)
        surf = fnt.render(text, True, (232, 236, 245))
        self.screen.blit(surf, (panel.centerx - surf.get_width() // 2,
                                panel.centery - surf.get_height() // 2))

    def _draw_map(self):
        """Render the interactive map viewer."""
        self.world_map.set_player_pos(
            self.current_floor,
            self.player.rect.centerx,
            self.player.rect.centery,
        )
        # Show Oscar marker on the mini-map if available
        try:
            oscar = self.npc_manager.get_npc_by_id("npc_oscar")
            if oscar:
                self.world_map.set_marker("Oscar Jimenez", oscar.current_floor, oscar.rect.centerx, oscar.rect.centery, color=(200, 120, 40))
        except Exception:
            pass
        self.world_map.set_marker("School Bus", 0, self._parked_car_rect.centerx, self._parked_car_rect.centery, color=(250, 160, 30))
        controller_connected = self.controller.connected if self.controller else False
        self.world_map.draw(self.screen, controller_connected)

    def _draw_phone_world_map_layer(self):
        """WorldMap fullscreen while keeping PLAYING state (opened from phone app)."""
        if self.phone.consume_embedded_map_initial_sync():
            map_floor = self.current_floor if self.current_floor in FLOOR_SIZES else FLOOR_CAMPUS
            self.world_map.current_tab = map_floor
            self.world_map._centre_on_floor(map_floor)
            self.world_map._refresh_room_selection(reset_index=True)
        self.world_map.set_player_pos(
            self.current_floor,
            self.player.rect.centerx,
            self.player.rect.centery,
        )
        try:
            oscar = self.npc_manager.get_npc_by_id("npc_oscar")
            if oscar:
                self.world_map.set_marker(
                    "Oscar Jimenez",
                    oscar.current_floor,
                    oscar.rect.centerx,
                    oscar.rect.centery,
                    color=(200, 120, 40),
                )
        except Exception:
            pass
        self.world_map.set_marker("School Bus", 0, self._parked_car_rect.centerx, self._parked_car_rect.centery, color=(250, 160, 30))
        controller_connected = self.controller.connected if self.controller else False
        self.world_map.draw(self.screen, controller_connected)
    # ──────────────────────────────────────────────────────────
    #  INTRO CINEMATIC
    # ──────────────────────────────────────────────────────────

    def _keep_noah_front_idle_at_entrance(self):
        """Keep Noah facing the camera while the intro is still at the entrance."""
        if self._cine_phase not in ("car", "exit", "dialogue"):
            return
        noah = self.npc_manager.get_npc_by_id("npc_noah_carter")
        if not noah or noah.current_floor != FLOOR_CAMPUS:
            return
        if abs(noah.rect.centerx - 2000) > 80 or abs(noah.rect.centery - 2650) > 80:
            return
        noah.direction = Direction.DOWN
        noah.state = "idle"
        noah._wander_dx = 0
        noah._wander_dy = 0
        if noah.animations.get("idle_down"):
            noah.image = noah.animations["idle_down"][noah.frame_index % len(noah.animations["idle_down"])]

    def _force_player_walk_up_animation(self, dt: float, player_obj=None):
        """Show the player walking away from the bus during the intro exit."""
        p = player_obj if player_obj else self.player
        p.direction = Direction.UP
        p.state = "walk"
        frames = p.animations.get("walk_up", [])
        if not frames:
            return
        p.animation_timer += dt * 12.0
        if p.animation_timer >= len(frames):
            p.animation_timer = 0.0
        p.frame_index = int(p.animation_timer) % len(frames)
        p.image = frames[p.frame_index]

    def _update_cinematic(self, dt: float):
        """Advance the intro-cinematic state machine."""
        # Do NOT advance in-game time during the cinematic
        phase = self._cine_phase

        self._keep_noah_front_idle_at_entrance()
        self._clear_noah_area()
        self._clear_bus_path()

        if phase == "car":
            # Slide car from right to centre
            self._car_x -= self._car_speed * dt
            # Controller vibration while car is moving
            if self.controller and self.controller.connected:
                self.controller.rumble(0.3, 0.6, 100)
            if self._car_x <= self._car_target_x:
                self._car_x = self._car_target_x
                self._cine_phase = "exit"
                self._exit_car_timer = 0.0
                # Spawn player at the car door (right side of car)
                # We use the fake target position (2000, 2700) to ensure reliable spawn even if camera is still lerping
                cam_y = 2700 - SCREEN_HEIGHT // 2
                wy = int(self._car_y + 70 + cam_y)
                self.player.rect.center = (2000, wy)
                if self.remote_player:
                    self.remote_player.rect.center = (2040, wy)
                self._exit_car_player_y = float(wy)
                self._player_spawned = True
                # Stop vibration when car stops
                if self.controller and self.controller.connected:
                    self.controller.stop_rumble()

        elif phase == "exit":
            # Player walks upward away from car for ~2 seconds
            self._exit_car_timer += dt
            self._exit_car_player_y -= 60 * dt  # walk up slowly
            self.player.rect.centery = int(self._exit_car_player_y)
            self._force_player_walk_up_animation(dt, self.player)
            if self.remote_player:
                self.remote_player.rect.centery = int(self._exit_car_player_y)
                self._force_player_walk_up_animation(dt, self.remote_player)
            # Car keeps driving away to the left
            self._car_x -= self._car_speed * dt
            self.camera.update(self.player)
            if self._exit_car_timer >= 2.0:
                self._cine_phase = "dialogue"
                self._cine_dlg_index = 0

        elif phase == "dialogue":
            # Dialogue advances on SPACE / ENTER
            pass  # input handled in _on_key_down / controller

        elif phase == "mission":
            self._update_noah_guide(dt)
            self._cine_mission_timer -= dt
            if self._cine_mission_timer <= 0:
                self._cine_phase = "guide"

        elif phase == "guide":
            self._update_noah_guide(dt)

    def _advance_cinematic_dialogue(self):
        """Called on SPACE/ENTER during the cinematic dialogue phase."""
        if self._cine_phase == "dialogue":
            self._cine_dlg_index += 1
            if self._cine_dlg_index >= len(self._cine_dlg_lines):
                # Show mission box
                self._cine_phase = "mission"
                self._cine_show_mission = True
                self._cine_mission_timer = 3.0
                self._start_noah_guide()

        elif self._cine_phase == "final_dialogue":
            self._noah_final_dlg_index += 1
            if self._noah_final_dlg_index >= len(self._noah_final_dlg_lines):
                # End cinematic → PLAYING
                self.state = GameState.PLAYING
                
                # Level Up 
                if not (self.multiplayer and not self.is_host):
                    self.player.level = 2
                    self.player.xp = 0
                    self.player.money += 10
                    self.ui.trigger_level_up(10)
                
                self._add_noah_contact()
                self._start_oscar_mission()
                self._noah_guide_active = False
                self._cinematic_stairs_unlocked = False
                noah = self.npc_manager.get_npc_by_id("npc_noah_carter")
                if noah:
                    noah.ai_enabled = True
                    noah.ignore_schedule = False
                    # Keep Noah in the 2F Corridor after the tour
                    floor2 = self.school_map.get_floor(FLOOR_2F)
                    if floor2:
                        corridor = floor2.rooms.get("f2_corridor")
                        if corridor:
                            noah.bound_rect = corridor.rect.inflate(-40, -40)

    def _skip_cinematic(self):
        """Immediately end the intro cinematic and jump to PLAYING state."""
        self.state = GameState.PLAYING
        
        # Level Up
        if not (self.multiplayer and not self.is_host):
            self.player.level = 2
            self.player.xp = 0
            self.player.money += 10
            self.ui.trigger_level_up(10)
        
        self._add_noah_contact()
        self._start_oscar_mission()
        self._noah_guide_active = False
        self._cinematic_stairs_unlocked = False
        self._cine_phase = "done"
        
        # Ensure player is placed at entrance if still off-screen
        if not self._player_spawned or self.player.rect.x < 0:
            f0 = self.school_map.get_floor(0)
            if f0:
                entrance = f0.rooms.get("c_roundabout")
                if entrance:
                    self.player.rect.center = entrance.rect.center
                    if self.remote_player:
                        self.remote_player.rect.center = (entrance.rect.centerx + 40, entrance.rect.centery)
                else:
                    self.player.rect.center = (2000, 2650)
                    if self.remote_player:
                        self.remote_player.rect.center = (2040, 2650)
            else:
                self.player.rect.center = (2000, 2650)
                if self.remote_player:
                    self.remote_player.rect.center = (2040, 2650)
            self._player_spawned = True

        # Free Noah and move him to Floor 2
        noah = self.npc_manager.get_npc_by_id("npc_noah_carter")
        if noah:
            noah.current_floor = FLOOR_2F
            noah.ai_enabled = True
            noah.ignore_schedule = False
            floor2 = self.school_map.get_floor(FLOOR_2F)
            if floor2:
                corridor = floor2.rooms.get("f2_corridor")
                if corridor:
                    noah.bound_rect = corridor.rect.inflate(-40, -40)
                    noah.rect.center = (corridor.rect.centerx - 200, corridor.rect.centery)
        
        self.camera.update(self.player)

    def _add_noah_contact(self):
        """Add Noah Carter to the phone's message list with a welcome text."""
        from src.phone import TextMessage
        import uuid
        msg = TextMessage(
            id=str(uuid.uuid4()),
            sender_npc_id="npc_noah_carter",
            sender_name="Noah Carter",
            content="Hey! Glad you're here. If you need anything during your first day, don't hesitate to ask. Good luck!",
            timestamp=self._get_time_string(),
            is_read=False,
            reply_options=["Thanks Noah!", "Got it, thanks!", "Who are you exactly?"]
        )
        self.phone.add_text_message("npc_noah_carter", msg)

    def _start_oscar_mission(self):
        """Add Oscar's challenge mention and start the phone check mission."""
        from src.phone import SocialPost
        import uuid
        
        player_name = self.player.character.value.capitalize()
        mention_str = f"@{player_name}Parker"
        
        post = SocialPost(
            id=str(uuid.uuid4()),
            author="Oscar Jimenez",
            author_npc_id="npc_oscar",
            content=f"I heard {mention_str} just arrived at Ravenside. I publicly challenge you to a game of Ping Pong. Let's see if you can prove yourself and raise your reputation!",
            timestamp=self._get_time_string(),
            is_anonymous=False,
            handle="oscar_j",
            likes=46,
            mentions=["aiden", "lena", mention_str],
            is_read=False
        )
        self.phone.add_social_post(post)
        self._current_main_mission_text = "Mission 2: Open Social app and click Oscar's post."
        m_obj = self.mission_manager.missions.get("mission_first_day")
        if m_obj:
            m_obj.status = MissionStatus.COMPLETED
            for obj in m_obj.objectives:
                obj.completed = True
                obj.progress = obj.required
            self.mission_manager.completed_ids.add("mission_first_day")
        self.mission_manager.unlock_mission("mission_strange_rumours")
        self.mission_manager._refresh_availability()

    def _begin_oscar_win_dialogue(self):
        if self._oscar_win_dialogue_completed:
            return
        player_name = self.player.character.value.capitalize()
        curious_line = (
            "Students meeting under the school? Oscar, tell me more about that."
        )
        self._oscar_win_dialogue_lines = [
            ("Oscar Jimenez", "I haven't had an opponent like that since Eli..."),
            ("Oscar Jimenez", "Eli left the school after online bullying got too bad. People acted like it was just drama, but it was not."),
            ("Oscar Jimenez", "I have also heard weird conversations about students meeting underneath the school."),
            (player_name, curious_line),
            ("Oscar Jimenez", "I do not know much more. But I can introduce you to Ava Thompson. She is always in the Library, and she knows more than I do."),
        ]
        self._oscar_win_dialogue_index = 0
        self._oscar_win_dialogue_active = True
        if hasattr(self.player, "stop_audio"):
            self.player.stop_audio()

    def _advance_oscar_win_dialogue(self):
        if not self._oscar_win_dialogue_active:
            return
        self._oscar_win_dialogue_index += 1
        if self._oscar_win_dialogue_index >= len(self._oscar_win_dialogue_lines):
            self._finish_oscar_win_dialogue()

    def _finish_oscar_win_dialogue(self):
        self._oscar_win_dialogue_active = False
        self._oscar_win_dialogue_completed = True
        self._current_main_mission_text = "Mission 3: Go to the Library and talk to Ava Thompson."
        self.mission_manager.unlock_mission("mission_library_secrets")
        self.mission_manager.activate_mission("mission_library_secrets")
        self._add_oscar_contact()
        self.ui.show_notification("New mission available!", NOTIF_INFO)

    def _begin_marcus_win_dialogue(self):
        if getattr(self, "_marcus_win_dialogue_completed", False):
            return
        player_name = self.player.character.value.capitalize()
        self._marcus_win_dialogue_lines = [
            ("Marcus Green", "Wow! You play incredible! I haven't seen skills like that in a long time."),
            (player_name, "Good game. Now, what about the email Eli sent you about the Smile Club?"),
            ("Marcus Green", "Look, man... I don't really know much about what you're talking about. Eli sends weird stuff."),
            ("Marcus Green", "But you know what? I really like your style. You're cool."),
            ("Marcus Green", "There's a big party tomorrow up on the Rooftop with the populars. You should definitely come!"),
            (player_name, "A rooftop party tomorrow? Sounds interesting. I'll be there."),
            ("Marcus Green", "Awesome! Enjoy the party tomorrow up on the Rooftop!"),
        ]
        self._marcus_win_dialogue_index = 0
        self._marcus_win_dialogue_active = True
        if hasattr(self.player, "stop_audio"):
            self.player.stop_audio()

    def _advance_marcus_win_dialogue(self):
        if not getattr(self, "_marcus_win_dialogue_active", False):
            return
        self._marcus_win_dialogue_index += 1
        if self._marcus_win_dialogue_index >= len(self._marcus_win_dialogue_lines):
            self._finish_marcus_win_dialogue()

    def _finish_marcus_win_dialogue(self):
        self._marcus_win_dialogue_active = False
        self._marcus_win_dialogue_completed = True
        
        m_obj = self.mission_manager.missions.get("mission_server_room")
        if m_obj:
            m_obj.status = MissionStatus.COMPLETED
            for obj in m_obj.objectives:
                obj.completed = True
                obj.progress = obj.required
            self.mission_manager.completed_ids.add("mission_server_room")
        
        # Trigger Level Up after conversation finishes
        if not (self.multiplayer and not self.is_host):
            self.player.level += 1
            from settings import SKILL_POINT_PER_LEVEL
            self.player.skill_points += SKILL_POINT_PER_LEVEL
            self.player.money += 10
            if hasattr(self.ui, 'trigger_level_up'):
                self.ui.trigger_level_up(10)
            self._last_known_level = self.player.level

        self._complete_day3_story()

    def _add_oscar_contact(self):
        from src.phone import TextMessage
        import uuid
        if "npc_oscar" in getattr(self.phone, "messages", {}):
            return
        msg = TextMessage(
            id=str(uuid.uuid4()),
            sender_npc_id="npc_oscar",
            sender_name="Oscar Jimenez",
            content="Reminder: whenever you want, you can play ping pong against me again.",
            timestamp=self._get_time_string(),
            is_read=False,
            reply_options=["I'll be there.", "Not right now.", "You really never stop, huh?"],
        )
        self.phone.add_text_message("npc_oscar", msg)

    def _complete_day1_story(self):
        self._day1_story_complete = True
        message = "Day 1 all missions completed, go take the School Bus to go home."
        self._current_main_mission_text = message
        self.ui.trigger_announcement("DAY 1 COMPLETE", message)
        self.ui.show_notification(message, NOTIF_SUCCESS, 8.0)

    def _complete_day2_story(self):
        self._day2_story_complete = True
        self.ui.show_notification("Ava Thompson: 'With this information, I will follow up on who is behind the Smile Club. In the meantime, dedicate yourself to gaining reputation.'", NOTIF_INFO, 10.0)
        message = "Day 2 all missions completed, go take the School Bus to go home."
        self._current_main_mission_text = message
        self.ui.trigger_announcement("DAY 2 COMPLETE", message)
        self.ui.show_notification(message, NOTIF_SUCCESS, 8.0)

    def _complete_day3_story(self):
        self._day3_story_complete = True
        message = "Day 3 all missions completed, go take the School Bus to go home."
        self._current_main_mission_text = message
        self.ui.trigger_announcement("DAY 3 COMPLETE", message)
        self.ui.show_notification(message, NOTIF_SUCCESS, 8.0)

    # ──────────────────────────────────────────────────────────
    #  DAY 4 — ROOFTOP PARTY SCENE
    # ──────────────────────────────────────────────────────────

    def _place_day4_rooftop_npcs(self):
        """Place Ava, Marcus, Noah and the sibling on the Rooftop for Day 4."""
        rooftop = self.school_map.get_floor(FLOOR_ROOFTOP)
        if not rooftop:
            return

        placements = [
            ("npc_ava_thompson",  (1560, 770),  "dlg_ava_rooftop_party"),
            ("npc_marcus_green",  (1280, 860),  None),
            ("npc_noah_carter",   (1280, 920),  None),
        ]
        for npc_id, pos, dlg in placements:
            npc = self.npc_manager.get_npc_by_id(npc_id)
            if not npc:
                continue
            npc.current_floor = FLOOR_ROOFTOP
            npc.rect.center   = pos
            npc.ai_enabled    = False
            npc.ignore_schedule = True
            npc.stop_at_target  = False
            npc.target_pos      = None
            npc.target_queue    = []
            npc.show_name       = True
            if dlg:
                npc.dialogue_ids = {"aiden": dlg, "lena": dlg}

        # Sibling also attends the party
        sib = getattr(self, "sibling_npc", None)
        if sib:
            sib.current_floor = FLOOR_ROOFTOP
            sib.rect.center   = (1900, 880)
            sib.ai_enabled    = True
            sib.ignore_schedule = True
            sib.bound_rect    = pygame.Rect(1250, 560, 1100, 900)

        self._day4_npcs_placed = True

    def _begin_ava_rooftop_dialogue(self):
        """Start Mission 11: greeting conversation with Ava at the rooftop."""
        if getattr(self, "_ava_rooftop_dialogue_completed", False):
            return
        pname = self.player.character.value.capitalize()
        self._ava_rooftop_dialogue_lines = [
            ("Ava Thompson", "Hey! You made it! I'm so glad you came."),
            (pname, "This place is incredible. I've never been up here before."),
            ("Ava Thompson", "Right? The view is perfect. Marcus throws the best parties."),
            (pname, "Where is Marcus, actually?"),
            ("Ava Thompson", "He's right over there with Noah... wait, where are they going?"),
        ]
        self._ava_rooftop_dialogue_index  = 0
        self._ava_rooftop_dialogue_active = True
        self._ava_rooftop_dialogue_part2_active = False

    def _begin_ava_rooftop_dialogue_part2(self):
        pname = self.player.character.value.capitalize()
        self._ava_rooftop_dialogue_lines = [
            ("Ava Thompson", "That's weird... Anyway, let me go grab us some drinks..."),
            ("Ava Thompson", "Actually — I'll be right back. Don't go anywhere!"),
        ]
        self._ava_rooftop_dialogue_index = 0
        self._ava_rooftop_dialogue_active = True
        self._ava_rooftop_dialogue_part2_active = True

    def _advance_ava_rooftop_dialogue(self):
        if not self._ava_rooftop_dialogue_active:
            return
        self._ava_rooftop_dialogue_index += 1
        if self._ava_rooftop_dialogue_index >= len(self._ava_rooftop_dialogue_lines):
            self._finish_ava_rooftop_dialogue()

    def _finish_ava_rooftop_dialogue(self):
        self._ava_rooftop_dialogue_active = False
        
        if getattr(self, "_ava_rooftop_dialogue_part2_active", False):
            self._ava_rooftop_dialogue_part2_active = False
            self._ava_rooftop_dialogue_completed = True

            # Complete Mission 11
            m = self.mission_manager.missions.get("mission_talk_ava_rooftop")
            if m:
                m.status = MissionStatus.COMPLETED
                for obj in m.objectives:
                    obj.completed = True
                    obj.progress  = obj.required
                self.mission_manager.completed_ids.add("mission_talk_ava_rooftop")

            # Ava disappears (walks off)
            ava = self.npc_manager.get_npc_by_id("npc_ava_thompson")
            if ava:
                ava.ai_enabled   = True
                ava.target_pos   = (1784, 400)   # walk north toward backstage
                ava.stop_at_target = True

            # Show Ava's phone on the chair
            self._ava_phone_on_chair = True
            # Show "bad feeling" monologue
            self._show_bad_feeling_monologue()
        else:
            # Start Marcus + Noah exit cinematic
            self._start_party_exit_cinematic()

    def _start_party_exit_cinematic(self):
        """Cinematic: camera pans to Marcus & Noah walking to the hallway gap."""
        marcus = self.npc_manager.get_npc_by_id("npc_marcus_green")
        noah   = self.npc_manager.get_npc_by_id("npc_noah_carter")

        if marcus:
            marcus.ai_enabled    = True
            marcus.stop_at_target = True
            marcus.target_pos    = (1280, 920)
            marcus.target_queue  = [(700, 920), "SWITCH_TO_F1", (1500, 500)]
            marcus.speed_multiplier = 3.5
        if noah:
            noah.ai_enabled      = True
            noah.stop_at_target  = True
            noah.target_pos      = (700, 920)
            noah.target_queue    = ["SWITCH_TO_F1", (1500, 500)]
            noah.speed_multiplier = 3.5

        # Camera pan target = midpoint of Marcus & Noah
        if marcus:
            self._party_exit_cam_target = marcus.rect.center
        self._party_exit_cam_origin = (self.camera.offset.x, self.camera.offset.y)
        self._party_exit_timer         = 0.0
        self._party_exit_phase         = "pan_to_npcs"
        self._party_exit_cinematic_active = True

    def _update_party_exit_cinematic(self, dt: float):
        """State machine for the Marcus/Noah exit cinematic."""
        if not self._party_exit_cinematic_active:
            return

        if self._party_exit_phase == "pan_to_npcs":
            self._party_exit_timer += dt
            # Smooth pan to Marcus over 1.5 s
            t = min(1.0, self._party_exit_timer / 1.5)
            t_ease = t * t * (3 - 2 * t)
            marcus = self.npc_manager.get_npc_by_id("npc_marcus_green")
            if marcus:
                tx = marcus.rect.centerx - SCREEN_WIDTH  // 2
                ty = marcus.rect.centery - SCREEN_HEIGHT // 2
                ox, oy = self._party_exit_cam_origin
                self.camera.offset.x = ox + (tx - ox) * t_ease
                self.camera.offset.y = oy + (ty - oy) * t_ease
            if self._party_exit_timer >= 1.5:
                self._party_exit_phase = "npcs_walking"
                self._party_exit_timer = 0.0

        elif self._party_exit_phase == "npcs_walking":
            self._party_exit_timer += dt
            marcus = self.npc_manager.get_npc_by_id("npc_marcus_green")
            if marcus:
                # Follow Marcus with camera as he walks to the hallway gap
                tx = marcus.rect.centerx - SCREEN_WIDTH  // 2
                ty = marcus.rect.centery - SCREEN_HEIGHT // 2
                self.camera.offset.x = tx
                self.camera.offset.y = ty

            reached = (not marcus) or (marcus.current_floor != FLOOR_ROOFTOP) or self._party_exit_timer > 6.0
            if reached:
                # Remove Marcus & Noah from rooftop if timer exceeded
                for nid in ("npc_marcus_green", "npc_noah_carter"):
                    npc = self.npc_manager.get_npc_by_id(nid)
                    if npc and npc.current_floor == FLOOR_ROOFTOP:
                        npc.current_floor = FLOOR_1F
                        npc.rect.center   = (1500, 500)
                        npc.ai_enabled    = False
                self._party_exit_phase = "pan_back"
                self._party_exit_timer = 0.0
                # Save camera origin for pan-back
                self._party_exit_cam_origin = (self.camera.offset.x, self.camera.offset.y)

        elif self._party_exit_phase == "pan_back":
            self._party_exit_timer += dt
            t = min(1.0, self._party_exit_timer / 1.5)
            t_ease = t * t * (3 - 2 * t)
            px = self.player.rect.centerx - SCREEN_WIDTH  // 2
            py = self.player.rect.centery - SCREEN_HEIGHT // 2
            ox, oy = self._party_exit_cam_origin
            self.camera.offset.x = ox + (px - ox) * t_ease
            self.camera.offset.y = oy + (py - oy) * t_ease
            if self._party_exit_timer >= 1.5:
                self._party_exit_phase         = "done"
                self._party_exit_cinematic_active = False
                # Start part 2 of dialogue
                if not (self.multiplayer and not self.is_host):
                    self._begin_ava_rooftop_dialogue_part2()

    def _show_bad_feeling_monologue(self):
        """Narrative text box: player senses something is wrong."""
        pname = self.player.character.value.capitalize()
        self._bad_feeling_lines = [
            (pname, "...Everyone left at the same time. That's weird."),
            (pname, "Marcus and Noah were whispering before they walked off."),
            (pname, "And Ava just... disappeared. Is something going on?"),
            (pname, "Wait — she left her phone on that chair."),
            (pname, "I know I shouldn't... but something doesn't feel right about all this."),
        ]
        self._bad_feeling_index  = 0
        self._bad_feeling_active = True

    def _advance_bad_feeling(self):
        if not getattr(self, '_bad_feeling_active', False):
            return
        self._bad_feeling_index += 1
        if self._bad_feeling_index >= len(self._bad_feeling_lines):
            self._bad_feeling_active = False
            self._player_bad_feeling_shown = True
            # Unlock Mission 12
            self.mission_manager.unlock_mission("mission_check_ava_phone")
            self.mission_manager.activate_mission("mission_check_ava_phone")
            self.mission_manager._refresh_availability()
            self._current_main_mission_text = "Mission 12: Check Ava's phone before she comes back! (15 seconds)"
            self.ui.show_notification("New mission! Check Ava's phone — you have 15 seconds!", NOTIF_WARNING, 5.0)

    def _start_ava_phone_check(self):
        """Player presses ENTER near the phone — start the spy mechanic."""
        self._ava_phone_spying      = True
        self._ava_phone_timer       = 15.0
        self._ava_phone_timer_active = True
        self._ava_phone_prompt_active = False
        # Build Ava's phone messages
        self._build_ava_phone_messages()

    def _build_ava_phone_messages(self):
        """Populate Ava's fake phone with lots of chats (including the secret group chat)."""
        import uuid
        msgs = {}

        def add(npc_id, name, lines):
            msgs[npc_id] = []
            for sender, text in lines:
                msgs[npc_id].append({
                    "sender": sender if sender != "ava" else "Ava Thompson",
                    "text": text,
                    "is_player": sender == "ava"
                })

        # Decoy chats
        add("npc_mia", "Mia Nakamura", [
            ("Mia Nakamura", "Hey Ava! Are you coming to the art fair next week?"),
            ("ava", "I'll try! It depends on the party this weekend."),
            ("Mia Nakamura", "Hope to see you there! 🎨"),
        ])
        add("npc_sophie", "Sophie Chen", [
            ("Sophie Chen", "Did you finish the chem assignment?"),
            ("ava", "Almost. The last problem is killing me lol"),
            ("Sophie Chen", "Same!! Let me know if you figure it out"),
        ])
        add("npc_dylan", "Dylan Brooks", [
            ("Dylan Brooks", "Party tonight was epic btw"),
            ("ava", "Right?! Best one yet."),
            ("Dylan Brooks", "We have to do this again next month."),
        ])
        add("npc_rnd_01", "Jayden Mills", [
            ("Jayden Mills", "Ava do you have the biology notes from Monday?"),
            ("ava", "Check the shared drive, I uploaded them."),
            ("Jayden Mills", "You're a lifesaver!!"),
        ])
        add("npc_rnd_02", "Camila Torres", [
            ("Camila Torres", "Hey, are you good? You seemed stressed at lunch."),
            ("ava", "Yeah just a lot going on. I'll explain later."),
            ("Camila Torres", "Okay, I'm here for you! 💜"),
        ])
        add("npc_rnd_03", "Ethan Ross", [
            ("Ethan Ross", "Love the fit today btw"),
            ("ava", "Thank you!! New jacket 😊"),
        ])
        add("npc_rnd_04", "Priya Sharma", [
            ("Priya Sharma", "Did you see what they posted on the school feed?"),
            ("ava", "No?? what happened"),
            ("Priya Sharma", "Drama as always lol. Someone got called out."),
            ("ava", "Of course."),
        ])
        add("npc_rnd_05", "Coach Reyes", [
            ("Coach Reyes", "Reminder: sports day registration closes Friday."),
            ("ava", "Got it, thanks Coach."),
        ])
        # THE SECRET GROUP CHAT — must be found by player
        chat_key = "group_smile_club"
        msgs[chat_key] = [
            {"sender": "Marcus Green",  "text": "Everything set for tonight?", "is_player": False},
            {"sender": "Noah Carter",   "text": "Yep. Files are ready to upload.", "is_player": False},
            {"sender": "Ava Thompson",  "text": "Perfect. Nobody suspects anything.", "is_player": True},
            {"sender": "Marcus Green",  "text": "Meet in the basement at midnight. Use the side stairs so no one sees.", "is_player": False},
            {"sender": "Noah Carter",   "text": "The new data on the populars should finish them. This is it.", "is_player": False},
            {"sender": "Ava Thompson",  "text": "Don't be late. We expose everything tonight.", "is_player": True},
        ]

        self._ava_phone_messages = msgs
        self._ava_phone_chats    = list(msgs.keys())
        self._ava_phone_active_chat = None
        self._ava_phone_scroll   = 0

    def _get_ava_phone_avatar(self, name):
        if not hasattr(self, "_ava_phone_avatars"):
            self._ava_phone_avatars = {}
        if name not in self._ava_phone_avatars:
            import os
            path = f"assets/Imagenes realistas personajes/{name}.png"
            if os.path.exists(path):
                try:
                    img = pygame.image.load(path).convert_alpha()
                    img = pygame.transform.smoothscale(img, (24, 24))
                    
                    # Circular mask
                    mask = pygame.Surface((24, 24), pygame.SRCALPHA)
                    pygame.draw.circle(mask, (255, 255, 255), (12, 12), 12)
                    img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                    
                    self._ava_phone_avatars[name] = img
                except:
                    self._ava_phone_avatars[name] = None
            else:
                self._ava_phone_avatars[name] = None
        return self._ava_phone_avatars[name]

    def _update_ava_phone_timer(self, dt: float):
        """Tick the 15-second countdown for Mission 12."""
        if not self._ava_phone_timer_active:
            return
        self._ava_phone_timer -= dt
        # Cooperative bonus: Lena talks to party NPCs → +3s each
        if self.multiplayer:
            sib = getattr(self, "remote_player", None)
            # remote_player talks to rooftop NPCs
            # (handled in _handle_interaction_press for sibling side)
            pass
        if self._ava_phone_timer <= 0.0:
            self._ava_phone_timer       = 0.0
            self._ava_phone_timer_active = False
            self._ava_phone_spying       = False
            self._ava_phone_on_chair = False
            
            if getattr(self, "_ava_phone_completed", False):
                self._show_post_phone_monologue()
            else:
                # Ava returns → mission fail
                self.ui.show_notification("Ava came back! You didn't have enough time...", NOTIF_ERROR, 5.0)
                # Respawn Ava
                ava = self.npc_manager.get_npc_by_id("npc_ava_thompson")
                if ava:
                    ava.current_floor = FLOOR_ROOFTOP
                    ava.rect.center   = (1784, 800)
                    ava.ai_enabled    = False

    def _complete_ava_phone_mission(self):
        """Player found the secret chat — Mission 12 complete."""
        self._ava_phone_found_chat   = True
        self._ava_phone_completed    = True
        self._ava_phone_on_chair     = False

        m = self.mission_manager.missions.get("mission_check_ava_phone")
        if m:
            m.status = MissionStatus.COMPLETED
            for obj in m.objectives:
                obj.completed = True
                obj.progress  = obj.required
            self.mission_manager.completed_ids.add("mission_check_ava_phone")

    def _show_post_phone_monologue(self):
        """Narrative text box: player reacts to Ava's phone."""
        pname = self.player.character.value.capitalize()
        self._post_phone_lines = [
            (pname, "Wow... I can't believe what I just read on Ava's phone."),
            (pname, "Marcus, Noah, and Ava are part of the Smile Club."),
            (pname, "They're meeting in the basement at midnight to upload files."),
            (pname, "I have to get down to the basement right now and see what they're plotting."),
        ]
        self._post_phone_index  = 0
        self._post_phone_active = True

    def _advance_post_phone(self):
        if not getattr(self, '_post_phone_active', False):
            return
        self._post_phone_index += 1
        if self._post_phone_index >= len(self._post_phone_lines):
            self._post_phone_active = False
            self.mission_manager.unlock_mission("mission_final_showdown")
            self.mission_manager.activate_mission("mission_final_showdown")
            self.mission_manager._refresh_availability()
            self._current_main_mission_text = "Mission 13: Go to the Basement and see what they're plotting!"
            self._setup_smile_club_room()
            self.ui.show_notification("New Mission: Go to the Basement!", NOTIF_WARNING, 5.0)

    def _is_final_showdown_active(self) -> bool:
        m = self.mission_manager.missions.get("mission_final_showdown")
        return bool(m and m.status == MissionStatus.ACTIVE)

    def _get_smile_club_room(self):
        floor = self.school_map.get_floor(FLOOR_BASEMENT)
        return floor.rooms.get("b_smile_club") if floor else None

    def _set_smile_club_room_locked(self, locked: bool):
        floor = self.school_map.get_floor(FLOOR_BASEMENT)
        if not floor:
            return
        for door in floor.doors:
            if getattr(door, "id", "") == "door_b_smile_terminal":
                door.locked = locked
                door.open_ratio = 0.0
                door.close_timer = 0.0
                break

    def _is_smile_club_room_locked(self) -> bool:
        return bool(
            self.current_floor == FLOOR_BASEMENT
            and getattr(self, "_final_reveal_started", False)
            and not getattr(self, "_final_office_started", False)
        )

    def _load_sprite_sheet_for_npc(self, npc, path: str):
        if not npc or not os.path.exists(path):
            return
        sheet = pygame.image.load(path).convert_alpha()
        frame_w, frame_h = 32, 64

        def frames(row: int, start: int):
            return [
                sheet.subsurface(pygame.Rect(col * frame_w, row * frame_h, frame_w, frame_h)).copy()
                for col in range(start, start + 6)
            ]

        npc.animations = {
            "idle_right": frames(1, 0), "idle_up": frames(1, 6),
            "idle_left": frames(1, 12), "idle_down": frames(1, 18),
            "walk_right": frames(2, 0), "walk_up": frames(2, 6),
            "walk_left": frames(2, 12), "walk_down": frames(2, 18),
        }
        npc.state = "idle"
        npc.frame_index = 0
        npc.animation_timer = 0.0
        npc.image = npc.animations["idle_down"][0]

    def _setup_smile_club_room(self):
        if getattr(self, "_final_smile_room_ready", False):
            return
        room = self._get_smile_club_room()
        if not room:
            return
        positions = [(room.rect.centerx - 110, room.rect.centery), (room.rect.centerx, room.rect.centery - 25), (room.rect.centerx + 110, room.rect.centery)]
        member_sprites = ["member1.png", "member2.png", "member3.png"]
        base_dir = os.path.dirname(os.path.dirname(__file__))
        base = os.path.join(base_dir, "assets", "Characters BEHIND THE SMILE", "smileclubmember")
        for npc_id, pos, sprite_name in zip(self._final_smile_ids, positions, member_sprites):
            npc = self.npc_manager.get_npc_by_id(npc_id)
            if not npc:
                continue
            self._final_real_names.setdefault(npc_id, npc.name)
            npc.name = "Smile Club Member"
            npc.current_floor = FLOOR_BASEMENT
            npc.rect.center = pos
            npc.direction = Direction.DOWN
            npc.ai_enabled = False
            npc.ignore_schedule = True
            npc.stop_at_target = True
            npc.target_pos = None
            npc.target_queue = []
            npc.is_hostile = False
            npc.health = max(npc.health, npc.max_health)
            npc.knockout_timer = 0.0
            npc.show_name = False
            self._load_sprite_sheet_for_npc(npc, os.path.join(base, sprite_name))
        self._final_smile_room_ready = True

    def _reveal_smile_club_identities(self):
        for npc_id in self._final_smile_ids:
            npc = self.npc_manager.get_npc_by_id(npc_id)
            if npc:
                npc.name = self._final_real_names.get(npc_id, npc.name)
                npc.show_name = True
                npc._load_sprites()

    def _keep_npc_in_smile_room(self, npc):
        room = self._get_smile_club_room()
        if not room or not npc:
            return
        arena = room.rect.inflate(-110, -90)
        npc.rect.clamp_ip(arena)

    def _set_final_hostiles(self):
        room = self._get_smile_club_room()
        arena = room.rect.inflate(-120, -100) if room else None
        anchor_positions = [
            (room.rect.centerx - 95, room.rect.centery - 10) if room else None,
            (room.rect.centerx, room.rect.centery + 30) if room else None,
            (room.rect.centerx + 95, room.rect.centery - 10) if room else None,
        ]
        for npc_id, anchor in zip(self._final_smile_ids, anchor_positions):
            npc = self.npc_manager.get_npc_by_id(npc_id)
            if not npc:
                continue
            npc.current_floor = FLOOR_BASEMENT
            npc.is_hostile = True
            npc.ai_enabled = True
            npc.ignore_schedule = True
            npc.stop_at_target = False
            npc.health = npc.max_health
            npc.bound_rect = arena
            if anchor and arena and not arena.collidepoint(npc.rect.center):
                npc.rect.center = anchor
            self._keep_npc_in_smile_room(npc)

    def _keep_player_in_smile_room(self):
        room = self._get_smile_club_room()
        if room:
            self.player.rect.clamp_ip(room.rect.inflate(-24, -24))

    def _should_disable_basement_lighting(self) -> bool:
        if self.current_floor != FLOOR_BASEMENT:
            return False
        room = self._get_smile_club_room()
        if not room:
            return False
        if room.rect.collidepoint(self.player.rect.center):
            return True
        return bool(getattr(self, "_final_reveal_active", False) or getattr(self, "_final_reveal_finished", False))

    def _play_basement_mission_music(self):
        if getattr(self, "_basement_mission_music_playing", False):
            return
        try:
            if pygame.mixer.get_init():
                path = os.path.join("assets", "sounds", "Pokemon BlueRed - Lavender Town.mp3")
                if os.path.exists(path):
                    pygame.mixer.music.load(path)
                    pygame.mixer.music.set_volume(0.28)
                    pygame.mixer.music.play(-1)
                    self._basement_mission_music_playing = True
                    self._normal_gameplay_music_playing = False
                    self._pasillo_playing = False
                    self._basement_music_playing = False
                    self._rooftop_party_music_playing = False
        except Exception as e:
            print(f"[Game] Could not play basement mission music: {e}")
            self._basement_mission_music_playing = False

    def _stop_basement_mission_music(self):
        if not getattr(self, "_basement_mission_music_playing", False):
            return
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception as e:
            print(f"[Game] Could not stop basement mission music: {e}")
        self._basement_mission_music_playing = False

    def _update_final_showdown(self, dt: float):
        if not self._is_final_showdown_active() or getattr(self, "_final_office_started", False):
            self._stop_basement_mission_music()
            return
        if not getattr(self, "_final_reveal_started", False):
            self._setup_smile_club_room()
        if self.current_floor == FLOOR_BASEMENT:
            self._play_basement_mission_music()
            if not getattr(self, "_final_reveal_finished", False):
                self._current_main_mission_text = "Explore the Labyrinth"
            room = self._get_smile_club_room()
            if room and room.rect.collidepoint(self.player.rect.center) and not getattr(self, "_final_reveal_started", False):
                self._start_final_reveal()
        else:
            self._stop_basement_mission_music()

    def _start_final_reveal(self):
        self._setup_smile_club_room()
        self._set_smile_club_room_locked(True)
        self._final_reveal_started = True
        self._final_reveal_active = True
        self._final_reveal_phase = "pan"
        self._final_reveal_timer = 0.0
        self._final_reveal_index = 0
        self.player.vx = self.player.vy = 0
        self.player._dashing = False
        self._final_reveal_lines = [
            ("Smile Club Member", "Yeah... we are the Smile Club."),
            ("Smile Club Member", "Not a rumor. Not a warning. Us."),
            ("Smile Club Member", "Every message, every setup, every scared whisper in the halls... we pushed it from here."),
            ("Smile Club Member", "You kept looking for a secret group hidden somewhere in the school."),
            ("Smile Club Member", "The joke is that you already knew us."),
            ("Smile Club Member", "So let's stop pretending."),
            ("Ava Thompson", "Ava planned the leaks. I used trust and attention to move people where we needed them."),
            ("Noah Carter", "And I made sure you trusted the wrong faces from the first day."),
            ("Marcus Green", "I used my popularity to spread rumors and keep everyone looking the other way."),
            ("Ava Thompson", "We were behind everything: the meetings, the phone messages, the pressure campaigns."),
            ("Marcus Green", "Nobody else is taking the blame for us."),
            ("Noah Carter", "You want this to end? Then make us stop."),
        ]

    def _update_final_reveal(self, dt: float):
        room = self._get_smile_club_room()
        if not room:
            self._final_reveal_active = False
            return
        for npc_id in self._final_smile_ids:
            npc = self.npc_manager.get_npc_by_id(npc_id)
            if npc:
                npc._advance_animation(dt)
        target = type("_CamTarget", (), {"rect": pygame.Rect(room.rect.centerx - 10, room.rect.centery - 10, 20, 20)})()
        self.camera.update(target)
        if self._final_reveal_phase == "pan":
            self._final_reveal_timer += dt
            if self._final_reveal_timer >= 1.7:
                self._final_reveal_phase = "dialogue"

    def _advance_final_reveal(self):
        if not getattr(self, "_final_reveal_active", False) or self._final_reveal_phase != "dialogue":
            return
        self._final_reveal_index += 1
        if self._final_reveal_index == 6:
            self._reveal_smile_club_identities()
        if self._final_reveal_index >= len(self._final_reveal_lines):
            self._final_reveal_active = False
            self._final_reveal_finished = True
            self._current_main_mission_text = "Attack Ava, Marcus, and Noah"
            self.ui.show_notification("Attack them! Use your punch combat controls.", NOTIF_WARNING, 4.0)
            self._set_final_hostiles()

    def _check_final_fight_complete(self):
        if not getattr(self, "_final_reveal_finished", False) or getattr(self, "_final_office_started", False):
            return
        if all((self.npc_manager.get_npc_by_id(nid) and self.npc_manager.get_npc_by_id(nid).health <= 0) for nid in self._final_smile_ids):
            self._start_final_office_scene()

    def _start_final_office_scene(self):
        self._stop_basement_mission_music()
        self._final_office_started = True
        self._final_office_active = True
        self._set_smile_club_room_locked(False)
        self._final_office_index = 0
        self.current_floor = FLOOR_2F
        floor = self.school_map.get_floor(FLOOR_2F)
        if floor:
            self._floor_w = floor.width
            self._floor_h = floor.height
            self.camera.set_bounds(floor.width, floor.height)
        self.player.rect.center = (2660, 360)
        placements = {
            "npc_director": (2660, 150),
            "npc_ava_thompson": (2470, 320),
            "npc_marcus_green": (2585, 320),
            "npc_noah_carter": (2700, 320),
        }
        for npc_id, pos in placements.items():
            npc = self.npc_manager.get_npc_by_id(npc_id)
            if npc:
                npc.current_floor = FLOOR_2F
                npc.rect.center = pos
                npc.direction = Direction.DOWN if npc_id == "npc_director" else Direction.UP
                npc.ai_enabled = False
                npc.ignore_schedule = True
                npc.is_hostile = False
                npc.health = max(1, npc.max_health)
                npc.knockout_timer = 0.0
                npc.show_name = True
                if npc_id in self._final_smile_ids:
                    npc._load_sprites()
        self.camera.update(self.player)
        pname = self.player.character.value.capitalize()
        self._final_office_lines = [
            ("Director Walsh", "Start at the beginning. No masks, no excuses."),
            ("Ava Thompson", "It was us. We built the Smile Club operation and used it to control the school."),
            ("Marcus Green", "I recruited people, spread rumors, and helped keep everyone scared enough to stay quiet."),
            ("Noah Carter", "I lied to you from the first morning. I made myself look safe so nobody would suspect me."),
            ("Ava Thompson", "The messages, the meetings, the pressure, everything that happened... we take responsibility."),
            (pname, "Then the Smile Club is finished."),
            ("Director Walsh", "It is. This ends now, and the three of you will answer for all of it."),
        ]
        self._current_main_mission_text = "Smile Club resolved"

    def _update_final_office_scene(self, dt: float):
        self.player.vx = self.player.vy = 0
        self.player._dashing = False
        self.camera.update(self.player)
        for npc_id in ("npc_director",) + self._final_smile_ids:
            npc = self.npc_manager.get_npc_by_id(npc_id)
            if npc:
                npc._advance_animation(dt)

    def _advance_final_office_scene(self):
        if not getattr(self, "_final_office_active", False):
            return
        self._final_office_index += 1
        if self._final_office_index >= len(self._final_office_lines):
            self._final_office_active = False
            m = self.mission_manager.missions.get("mission_final_showdown")
            if m:
                m.status = MissionStatus.COMPLETED
                for obj in m.objectives:
                    obj.completed = True
                    obj.progress = obj.required
                self.mission_manager.completed_ids.add("mission_final_showdown")
            self.ui.show_notification("Smile Club storyline resolved.", NOTIF_SUCCESS, 5.0)

    def _draw_final_reveal_dialogue(self):
        if self._final_reveal_index < len(self._final_reveal_lines):
            speaker, text = self._final_reveal_lines[self._final_reveal_index]
            self._draw_cinematic_dialogue(text, speaker)

    def _draw_final_office_dialogue(self):
        if self._final_office_index < len(self._final_office_lines):
            speaker, text = self._final_office_lines[self._final_office_index]
            self._draw_cinematic_dialogue(text, speaker)

    def _draw_ava_phone_spy_ui(self):
        """Draw Ava's phone overlay with pink background, chat list, and countdown bar."""
        sw, sh = self.screen.get_width(), self.screen.get_height()

        # Dim background
        ov = pygame.Surface((sw, sh), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 180))
        self.screen.blit(ov, (0, 0))

        # Phone frame (pink)
        from settings import VT323_PATH
        ph_w, ph_h = 340, 560
        ph_x = (sw - ph_w) // 2
        ph_y = (sh - ph_h) // 2

        pygame.draw.rect(self.screen, (30, 10, 20), (ph_x, ph_y, ph_w, ph_h), border_radius=20)
        pygame.draw.rect(self.screen, (255, 100, 180), (ph_x, ph_y, ph_w, ph_h), 3, border_radius=20)

        # Status bar
        fnt_sm = pygame.font.Font(VT323_PATH, 14)
        fnt_md = pygame.font.Font(VT323_PATH, 16)
        fnt_lg = pygame.font.Font(VT323_PATH, 18)

        bar_surf = pygame.Surface((ph_w, 24), pygame.SRCALPHA)
        bar_surf.fill((255, 100, 180, 80))
        self.screen.blit(bar_surf, (ph_x, ph_y + 4))
        owner_lbl = fnt_sm.render("📱  Ava Thompson's Phone", True, (255, 200, 230))
        self.screen.blit(owner_lbl, (ph_x + 8, ph_y + 7))

        # Countdown bar
        bar_y = ph_y + 30
        bar_total_w = ph_w - 16
        ratio = max(0.0, self._ava_phone_timer / 15.0)
        bar_color = (
            int(255 * (1 - ratio)),
            int(220 * ratio),
            60
        )
        pygame.draw.rect(self.screen, (40, 20, 30), (ph_x + 8, bar_y, bar_total_w, 12), border_radius=6)
        pygame.draw.rect(self.screen, bar_color, (ph_x + 8, bar_y, int(bar_total_w * ratio), 12), border_radius=6)
        time_lbl = fnt_sm.render(f"{self._ava_phone_timer:.1f}s", True, bar_color)
        self.screen.blit(time_lbl, (ph_x + ph_w - 40, bar_y - 1))

        content_y = bar_y + 18

        if self._ava_phone_active_chat is None:
            # Chat list
            header = fnt_md.render("Messages", True, (255, 200, 230))
            self.screen.blit(header, (ph_x + 10, content_y))
            content_y += 22

            chat_names = {
                "npc_mia":      "Mia Nakamura",
                "npc_sophie":   "Sophie Chen",
                "npc_dylan":    "Dylan Brooks",
                "npc_rnd_01":   "Jayden Mills",
                "npc_rnd_02":   "Camila Torres",
                "npc_rnd_03":   "Ethan Ross",
                "npc_rnd_04":   "Priya Sharma",
                "npc_rnd_05":   "Coach Reyes",
                "group_smile_club": "📍 Group Chat",
            }
            self._ava_phone_chat_rects = []
            for key, label in chat_names.items():
                row_rect = pygame.Rect(ph_x + 6, content_y, ph_w - 12, 34)
                col = (70, 20, 50) if key == "group_smile_club" else (40, 15, 30)
                bd  = (255, 80, 160) if key == "group_smile_club" else (80, 30, 60)
                pygame.draw.rect(self.screen, col, row_rect, border_radius=6)
                pygame.draw.rect(self.screen, bd, row_rect, 1, border_radius=6)
                
                # Avatar
                avatar = self._get_ava_phone_avatar(label)
                if avatar:
                    self.screen.blit(avatar, (row_rect.x + 5, row_rect.y + 5))
                    text_x = row_rect.x + 35
                else:
                    text_x = row_rect.x + 8
                    
                lbl = fnt_md.render(label, True, (255, 200, 230) if key == "group_smile_club" else (200, 160, 190))
                self.screen.blit(lbl, (text_x, row_rect.y + 8))
                self._ava_phone_chat_rects.append((row_rect, key))
                content_y += 38
                if content_y > ph_y + ph_h - 30:
                    break

            hint = fnt_sm.render("Click a chat to open  |  ESC close", True, (120, 80, 110))
            self.screen.blit(hint, (ph_x + 8, ph_y + ph_h - 20))

        else:
            # Open chat view
            key = self._ava_phone_active_chat
            is_secret = key == "group_smile_club"
            chat_names = {
                "npc_mia": "Mia Nakamura", "npc_sophie": "Sophie Chen",
                "npc_dylan": "Dylan Brooks", "npc_rnd_01": "Jayden Mills",
                "npc_rnd_02": "Camila Torres", "npc_rnd_03": "Ethan Ross",
                "npc_rnd_04": "Priya Sharma", "npc_rnd_05": "Coach Reyes",
                "group_smile_club": "Group Chat",
            }
            header = fnt_md.render(f"← {chat_names.get(key, key)}", True, (255, 180, 220))
            self.screen.blit(header, (ph_x + 8, content_y))
            content_y += 24

            msgs = self._ava_phone_messages.get(key, [])
            for msg in msgs:
                is_p = msg.get("is_player", False)
                bubble_col = (60, 20, 50) if is_p else (35, 15, 35)
                full_text = f"{msg['sender']}: {msg['text']}"
                
                # Word wrap
                words = full_text.split(' ')
                lines = []
                current_line = ""
                max_width = ph_w - 40
                for word in words:
                    test_line = current_line + word + " "
                    if fnt_sm.size(test_line)[0] < max_width:
                        current_line = test_line
                    else:
                        lines.append(current_line)
                        current_line = word + " "
                if current_line:
                    lines.append(current_line)
                
                # Render lines
                box_h = max(len(lines) * 16 + 4, 28) # Min height for avatar
                max_lw = max([fnt_sm.size(l)[0] for l in lines] + [0])
                
                avatar = self._get_ava_phone_avatar(msg['sender'])
                avatar_w = 30 if avatar else 0
                tw = min(max_lw + 12, ph_w - 20 - avatar_w)
                
                if is_p:
                    bx = ph_x + ph_w - tw - 10 - avatar_w
                    if avatar:
                        self.screen.blit(avatar, (bx + tw + 6, content_y))
                else:
                    bx = ph_x + 10 + avatar_w
                    if avatar:
                        self.screen.blit(avatar, (ph_x + 8, content_y))
                
                pygame.draw.rect(self.screen, bubble_col, (bx - 4, content_y - 2, tw + 4, box_h), border_radius=4)
                for i, l in enumerate(lines):
                    text_surf = fnt_sm.render(l.strip(), True, (230, 180, 210))
                    self.screen.blit(text_surf, (bx, content_y + i * 16))
                
                content_y += box_h + 6
                if content_y > ph_y + ph_h - 35:
                    break

            back_hint = fnt_sm.render("ESC: back to chat list", True, (120, 80, 110))
            self.screen.blit(back_hint, (ph_x + 8, ph_y + ph_h - 20))

            # If secret chat opened → complete mission
            if is_secret and not self._ava_phone_completed:
                self._complete_ava_phone_mission()

    def _draw_ava_phone_on_chair(self, target_surf, camera):
        """Draw the phone icon on the chair world position."""
        if not self._ava_phone_on_chair:
            return
        cx, cy = camera.apply_pos(*self._ava_phone_chair_pos)
        sw, sh = target_surf.get_width(), target_surf.get_height()
        if not (-20 < cx < sw + 20 and -20 < cy < sh + 20):
            return
        # Phone shadow
        pygame.draw.ellipse(target_surf, (0, 0, 0, 80), (cx - 10, cy + 14, 20, 6))
        # Phone body
        pygame.draw.rect(target_surf, (30, 10, 25), (cx - 8, cy - 14, 16, 28), border_radius=3)
        pygame.draw.rect(target_surf, (255, 100, 180), (cx - 8, cy - 14, 16, 28), 2, border_radius=3)
        # Screen
        pygame.draw.rect(target_surf, (200, 60, 140), (cx - 5, cy - 11, 10, 18), border_radius=1)
        # Pulsing prompt if in range
        import math, time
        pulse = abs(math.sin(time.time() * 3))
        if self._ava_phone_prompt_active:
            from settings import VT323_PATH
            fnt = pygame.font.Font(VT323_PATH, 13)
            lbl = fnt.render("ENTER: Check phone", True, (255, int(150 + 100 * pulse), 200))
            target_surf.blit(lbl, (cx - lbl.get_width() // 2, cy - 30))

    def _start_noah_guide(self):
        """Set up Noah Carter's walking route through the school."""
        self._noah_guide_active = True
        noah = self.npc_manager.get_npc_by_id("npc_noah_carter")
        if not noah:
            self.state = GameState.PLAYING
            return

        # Route using actual doorway gaps + full staircase U-turn:
        # Staircase (2150,1720,500,280): centre wall y=1860, gap x=2570-2650
        # 1F stair door: y=1896-1976 on x=2150
        # 2F stair door: y=1750-1830 on x=2150
        self._noah_route = [
            ("campus", (2000, 2400)),      # Walk up from entrance
            ("campus", (2250, 2350)),      # Go right to avoid fountain (east side)
            ("campus", (2250, 2150)),      # Go up past fountain
            ("campus", (2000, 2050)),      # Then left towards building entrance
            ("portal_1f", None),            # Trigger floor switch to 1F
            ("1f", (1600, 2100)),           # Reception area
            ("1f", (1600, 1936)),           # Just past reception→main hall door
            ("1f", (2180, 1936)),           # RIGHT to stair door (gap y=1896-1976)
            # ── 1F Staircase: walk to midpoint (gap at x=2400) then switch ──
            ("1f", (2420, 1936)),           # Walk right to gap (wall ends at x=2400)
            ("1f", (2420, 1860)),           # Reach centre wall y=1860 via gap
            ("switch_2f", None),            # Floor switch at midpoint
            # ── 2F Staircase: continue from midpoint to exit ──
            ("2f", (2420, 1790)),           # Continue up to top half
            ("2f", (2200, 1790)),           # Walk left along top half
            ("2f", (2180, 1790)),           # Reach stair exit door (y=1750-1830)
            # ── 2F Corridor ──
            ("2f", (1600, 1790)),           # Walk left into 2F corridor
            ("2f", (1600, 1000)),           # 2F corridor centre
            ("final", None),                # Final dialogue in corridor
        ]
        self._noah_route_idx = 0
        noah.ai_enabled = False

    def _update_noah_guide(self, dt: float):
        """Move Noah along the route, waiting if the player falls behind."""
        noah = self.npc_manager.get_npc_by_id("npc_noah_carter")
        if not noah or self._noah_route_idx >= len(self._noah_route):
            return

        # Check proximity — wait if player is too far away (> 250 px)
        if self._player_spawned and self._noah_route_idx > 0:
            px, py = self.player.rect.center
            nx, ny = noah.rect.center
            dist = ((px - nx)**2 + (py - ny)**2) ** 0.5
            if dist > 250 and noah.current_floor == self.current_floor:
                self._noah_wait_for_player = True
                noah.state = "idle"
                return
            self._noah_wait_for_player = False

        tag, pos = self._noah_route[self._noah_route_idx]

        if tag == "portal_1f":
            # Teleport Noah to 1F reception
            noah.current_floor = FLOOR_1F
            noah.rect.center = (1600, 2200)
            noah.state = "idle"
            self._go_to_floor(FLOOR_1F, 1600, 2200)
            self._noah_route_idx += 1
            return

        if tag == "switch_2f":
            # Don't change Noah's floor yet — keep him visible on 1F.
            # Noah will switch to 2F when the player transitions via
            # seamless stairs (handled in the guide movement block).
            self._cinematic_stairs_unlocked = True
            noah.state = "idle"
            self._noah_route_idx += 1
            return

        if tag == "final":
            noah.state = "idle"
            self._cine_phase = "final_dialogue"
            self._noah_final_dlg_index = 0
            self._noah_final_dialogue = True
            return

        # Move Noah towards the waypoint
        tx, ty = pos
        dx_r = tx - noah.rect.centerx
        dy_r = ty - noah.rect.centery
        dist = (dx_r**2 + dy_r**2) ** 0.5

        if dist > 8:
            speed = NPC_SPEED * 2.5 * 30 * dt
            noah.rect.centerx += int((dx_r / dist) * speed)
            noah.rect.centery += int((dy_r / dist) * speed)
            noah.state = "walk"
            noah._wander_dx = dx_r / dist
            noah._wander_dy = dy_r / dist
            # Update facing direction
            if abs(dx_r) > abs(dy_r):
                noah.direction = Direction.RIGHT if dx_r > 0 else Direction.LEFT
            else:
                noah.direction = Direction.DOWN if dy_r > 0 else Direction.UP
        else:
            noah.rect.center = pos
            noah.state = "idle"
            noah._wander_dx = 0
            noah._wander_dy = 0
            self._noah_route_idx += 1

    def _draw_cinematic(self):
        """Render the intro cinematic overlay."""
        if not self._player_spawned:
            self.camera.offset.x = max(0, min(2000 - SCREEN_WIDTH // 2, self.camera.map_width - SCREEN_WIDTH))
            self.camera.offset.y = max(0, min(2900 - SCREEN_HEIGHT // 2, self.camera.map_height - SCREEN_HEIGHT))

        self._draw_world()

        if not self._player_spawned:
            dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 100))
            self.screen.blit(dim, (0, 0))
            font_sm = pygame.font.Font(VT323_PATH, 20)
            lbl = font_sm.render("Ravenside High — Entrance", True, (180, 180, 180))
            self.screen.blit(lbl, lbl.get_rect(center=(SCREEN_WIDTH // 2, 40)))

        # ── Car ──
        if self._cine_phase in ("car", "exit"):
            cx = int(self._car_x)
            cy = int(self._car_y)
            # Use the same school bus sprite as the parked car
            car_surf = self._build_car_surface()
            self.screen.blit(car_surf, (cx, cy))

        # ── Dialogue box ──
        if self._cine_phase == "dialogue" and self._cine_dlg_index < len(self._cine_dlg_lines):
            self._draw_cinematic_dialogue(
                self._cine_dlg_lines[self._cine_dlg_index], "Noah Carter")

        # ── Mission text ──
        if self._cine_phase == "mission" and self._cine_show_mission:
            self._draw_mission_box("Mission 1: Follow Noah Carter through the school.")

        # ── Guide phase: persistent mission box + waiting indicator ──
        if self._cine_phase == "guide":
            self._draw_mission_box("Mission 1: Follow Noah Carter through the school.")
            if self._noah_wait_for_player:
                font = pygame.font.Font(VT323_PATH, 22)
                txt = font.render("Noah is waiting for you...", True, (255, 220, 100))
                self.screen.blit(txt, txt.get_rect(center=(SCREEN_WIDTH // 2, 150)))

        # ── Final dialogue ──
        if self._cine_phase == "final_dialogue" and self._noah_final_dlg_index < len(self._noah_final_dlg_lines):
            self._draw_cinematic_dialogue(
                self._noah_final_dlg_lines[self._noah_final_dlg_index], "Noah Carter")

        # ── Prompt to advance ──
        if self._cine_phase in ("dialogue", "final_dialogue"):
            font_hint = pygame.font.Font(VT323_PATH, 16)
            is_controller = bool(self.controller and self.controller.connected and getattr(self.controller, "last_input_method", "keyboard") == "controller")
            if self.multiplayer:
                total_votes = (1 if self.cinematic_continue_voted else 0) + (1 if getattr(self, "remote_cinematic_continue", False) else 0)
                msg = f"Continue {total_votes}/2 (Press {'A' if is_controller else 'SPACE'})"
                color = (50, 255, 120) if total_votes == 2 else ((50, 200, 100) if total_votes == 1 else (160, 160, 160))
            else:
                msg = "Press A to continue" if is_controller else "Press SPACE to continue"
                color = (160, 160, 160)
            hint = font_hint.render(msg, True, color)
            self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30)))

        # ── Skip button (top-right corner) ──
        skip_w, skip_h = 110, 36
        skip_x = SCREEN_WIDTH - skip_w - 18
        skip_y = 18
        skip_rect = pygame.Rect(skip_x, skip_y, skip_w, skip_h)
        # Draw button background
        skip_surf = pygame.Surface((skip_w, skip_h), pygame.SRCALPHA)
        skip_surf.fill((20, 20, 30, 200))
        self.screen.blit(skip_surf, (skip_x, skip_y))
        pygame.draw.rect(self.screen, (180, 180, 200), skip_rect, 2, border_radius=8)
        font_skip = pygame.font.Font(VT323_PATH, 15)
        
        if self.multiplayer:
            total_skips = (1 if self.cinematic_skip_voted else 0) + (1 if getattr(self, "remote_cinematic_skip", False) else 0)
            skip_text = f"Skip {total_skips}/2"
            color = (255, 220, 80) if total_skips >= 1 else (220, 220, 240)
        else:
            skip_text = "Skip  >>>"
            color = (220, 220, 240)
            
        skip_label = font_skip.render(skip_text, True, color)
        self.screen.blit(skip_label, skip_label.get_rect(center=skip_rect.center))
        # Yellow selection frame when focused (same style as wallet/FF button)
        mouse_hover = skip_rect.collidepoint(pygame.mouse.get_pos())
        if self._cine_skip_focused or mouse_hover:
            pygame.draw.rect(self.screen, (255, 220, 80), skip_rect.inflate(8, 8), 2, border_radius=8)
        # Store rect for click detection
        self._skip_btn_rect = skip_rect

    def _draw_cinematic_dialogue(self, text: str, speaker: str):
        """Draw cinematic dialogue using the same template as regular NPC dialogue (Oscar Jimenez style)."""
        from settings import UI_PANEL, UI_ACCENT, UI_TEXT, UI_TEXT_DIM, WHITE, BLACK

        # Same dimensions as regular NPC dialogue in dialogue.py
        box_w_offset = 140  # Space for portrait on the left
        box_h = 130
        # Box positioned to the right to make room for portrait on the left
        # Moved 50px to the right (was 30, now 80) as requested
        box_x = 80 + box_w_offset
        # Reduced width to match the shorter dialogue box style
        box = pygame.Rect(box_x, SCREEN_HEIGHT - box_h - 60,
                          SCREEN_WIDTH - 160 - box_w_offset, box_h)

        # Draw dialogue box background and border
        pygame.draw.rect(self.screen, UI_PANEL, box, border_radius=12)
        pygame.draw.rect(self.screen, UI_ACCENT, box, 2, border_radius=12)

        # NPC Portrait on the left (Template matching Oscar Jimenez)
        av_radius = 72
        # Positioned to the left of the box, attached
        av_cx = box.left - 87
        av_cy = box.centery

        # Circular frame (Light Blue UI_ACCENT)
        pygame.draw.circle(self.screen, UI_ACCENT, (av_cx, av_cy), av_radius + 4)
        pygame.draw.circle(self.screen, BLACK, (av_cx, av_cy), av_radius)

        avatar_ids = {
            "Noah Carter": "npc_noah_carter",
            "Oscar Jimenez": "npc_oscar",
            "Marcus Green": "npc_marcus_green",
            "Ava Thompson": "npc_ava_thompson",
            "Aiden": "npc_aiden",
            "Lena": "npc_lena",
            "Aiden Parker": "npc_aiden",
            "Lena Parker": "npc_lena",
        }
        avatar_id = avatar_ids.get(speaker, "npc_noah_carter")

        # Draw the speaker avatar when available.
        avatar_drawn = False
        if speaker == "Smile Club Member":
            if not hasattr(self, "_smile_club_logo_img"):
                try:
                    self._smile_club_logo_img = pygame.image.load("assets/UI/smile club.png").convert_alpha()
                except Exception as e:
                    print(f"Could not load smile club.png: {e}")
                    self._smile_club_logo_img = None
            if self._smile_club_logo_img:
                img = self._smile_club_logo_img
                size = av_radius * 2
                av_surf = pygame.Surface((size, size), pygame.SRCALPHA)
                pygame.draw.circle(av_surf, (255, 255, 255), (av_radius, av_radius), av_radius)
                scaled = pygame.transform.smoothscale(img, (size, size))
                av_surf.blit(scaled, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                self.screen.blit(av_surf, (av_cx - av_radius, av_cy - av_radius))
                avatar_drawn = True
        elif hasattr(self, "phone") and avatar_id in self.phone.avatars:
            img = self.phone.avatars[avatar_id]
            size = av_radius * 2
            av_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(av_surf, (255, 255, 255), (av_radius, av_radius), av_radius)
            scaled = pygame.transform.smoothscale(img, (size, size))
            av_surf.blit(scaled, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            self.screen.blit(av_surf, (av_cx - av_radius, av_cy - av_radius))
            avatar_drawn = True

        if not avatar_drawn:
            # Fallback: Draw initials in a stylized circle
            pygame.draw.circle(self.screen, (40, 50, 70), (av_cx, av_cy), av_radius - 2)
            initial = speaker[0].upper() if speaker else "?"
            f_init = pygame.font.Font(VT323_PATH, 48)
            txt = f_init.render(initial, True, UI_ACCENT)
            self.screen.blit(txt, txt.get_rect(center=(av_cx, av_cy)))

        # Speaker name (same style as dialogue.py)
        font_name = pygame.font.Font(VT323_PATH, 22)
        self.screen.blit(font_name.render(speaker, True, UI_ACCENT),
                         (box.x + 18, box.y + 12))

        # Dialogue text (with word wrap, same as dialogue.py)
        font_text = pygame.font.Font(VT323_PATH, 20)
        self._draw_cinematic_wrapped_text(text, font_text, UI_TEXT,
                                           box.x + 18, box.y + 42, box.width - 36)

    def _draw_oscar_win_dialogue(self):
        if not self._oscar_win_dialogue_lines:
            return
        idx = min(self._oscar_win_dialogue_index, len(self._oscar_win_dialogue_lines) - 1)
        speaker, text = self._oscar_win_dialogue_lines[idx]
        dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 65))
        self.screen.blit(dim, (0, 0))
        self._draw_cinematic_dialogue(text, speaker)
        font_hint = pygame.font.Font(VT323_PATH, 16)
        is_controller = bool(self.controller and self.controller.connected and getattr(self.controller, "last_input_method", "keyboard") == "controller")
        msg = "Press A to continue" if is_controller else "Press SPACE to continue"
        hint = font_hint.render(msg, True, (160, 160, 160))
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30)))

    def _draw_marcus_win_dialogue(self):
        if not self._marcus_win_dialogue_lines:
            return
        idx = min(self._marcus_win_dialogue_index, len(self._marcus_win_dialogue_lines) - 1)
        speaker, text = self._marcus_win_dialogue_lines[idx]
        dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 65))
        self.screen.blit(dim, (0, 0))
        self._draw_cinematic_dialogue(text, speaker)
        font_hint = pygame.font.Font(VT323_PATH, 16)
        is_controller = bool(self.controller and self.controller.connected and getattr(self.controller, "last_input_method", "keyboard") == "controller")
        msg = "Press A to continue" if is_controller else "Press SPACE to continue"
        hint = font_hint.render(msg, True, (160, 160, 160))
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30)))

    def _draw_rooftop_party_dialogue(self, feeling: bool = False, post_phone: bool = False):
        """Draw Ava's rooftop greeting OR the bad-feeling monologue OR post-phone monologue."""
        if post_phone:
            lines = getattr(self, "_post_phone_lines", [])
            idx   = getattr(self, "_post_phone_index", 0)
        elif feeling:
            lines = getattr(self, "_bad_feeling_lines", [])
            idx   = getattr(self, "_bad_feeling_index", 0)
        else:
            lines = self._ava_rooftop_dialogue_lines
            idx   = self._ava_rooftop_dialogue_index
        if not lines:
            return
        idx = min(idx, len(lines) - 1)
        speaker, text = lines[idx]
        dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 65))
        self.screen.blit(dim, (0, 0))
        self._draw_cinematic_dialogue(text, speaker)
        font_hint = pygame.font.Font(VT323_PATH, 16)
        is_ctrl = bool(self.controller and self.controller.connected
                       and getattr(self.controller, "last_input_method", "keyboard") == "controller")
        msg = "Press A to continue" if is_ctrl else "Press SPACE to continue"
        hint = font_hint.render(msg, True, (160, 160, 160))
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30)))

    def _draw_cinematic_wrapped_text(self, text: str, font, colour, x: int, y: int, max_w: int):
        """Render text with simple word-wrap for cinematic dialogue."""
        words = text.split()
        line = ""
        for word in words:
            test = f"{line} {word}".strip()
            tw, _ = font.size(test)
            if tw > max_w:
                self.screen.blit(font.render(line, True, colour), (x, y))
                y += font.get_linesize()
                line = word
            else:
                line = test
        if line:

            self.screen.blit(font.render(line, True, colour), (x, y))

    def _draw_mission_box(self, mission_text: str):
        """Draw a mission objective text box below the stats."""
        box_w, box_h = 420, 60
        bx = 16
        by = 110

        surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        surf.fill((10, 30, 50, 220))
        pygame.draw.rect(surf, (100, 180, 255, 180), surf.get_rect(), 2, border_radius=10)
        self.screen.blit(surf, (bx, by))

        icon_font = pygame.font.Font(VT323_PATH, 16)
        icon = icon_font.render("MISSION", True, (100, 180, 255))
        self.screen.blit(icon, (bx + 15, by + 8))

        txt_font = pygame.font.Font(VT323_PATH, 16)
        txt = txt_font.render(mission_text, True, WHITE)
        self.screen.blit(txt, (bx + 15, by + 30))


    def _begin_day_transition(self):
        """Show the 'Day X' fullscreen transition, then start the next day."""
        self._day_transition_target_day = self.day_number + 1
        self._day_transition_active = True
        self._day_transition_timer = 3.0  # show for 3 seconds

    def _start_next_day(self):
        """Reset the day, increment counter, and respawn player while keeping stats."""
        self.day_number += 1
        self.time_of_day_minutes = 7 * 60 # 7:00 AM
        self._last_time_minutes = 7 * 60

        # Clear cafeteria of any remaining NPCs from previous day
        self._move_npcs_out_of_cafeteria(instant=True)

        # Reset dash state so the visual trail works on new days
        self.player._dashing = False
        self.player._dash_timer = 0
        self.player._dash_trail.clear()
        
        # Respawn player at Entrance
        self.player.rect.center = (2000, 2700)
        self.current_floor = FLOOR_CAMPUS
        
        # Snap camera to new player position immediately
        floor = self.school_map.get_floor(self.current_floor)
        if floor:
            self._floor_w = floor.width
            self._floor_h = floor.height
            self.camera.set_bounds(floor.width, floor.height)
        goal_x = self.player.rect.centerx - SCREEN_WIDTH // 2
        goal_y = self.player.rect.centery - SCREEN_HEIGHT // 2
        self.camera.offset.x = max(0, min(goal_x, self.camera.map_width - SCREEN_WIDTH))
        self.camera.offset.y = max(0, min(goal_y, self.camera.map_height - SCREEN_HEIGHT))
        
        # Reset school systems for a new day
        self.event_queue.load_day_schedule()
        self._school_day_ended = False
        self._advance_phase() # Triggers notifications
        
        # Re-init NPCs for the new day positions
        self._place_ava_for_story()
        if self.day_number == 2:
            self._current_main_mission_text = "Mission 4: Go to Tech Lab to meet Ava Thompson."
        elif self.day_number == 3:
            self.mission_manager.unlock_mission("mission_server_room")
            self.mission_manager.activate_mission("mission_server_room")
            self.mission_manager._refresh_availability()
            self._current_main_mission_text = "Mission 9: Talk to Marcus Green in the Athletic Coliseum."
        elif self.day_number == 4:
            self.mission_manager.unlock_mission("mission_rooftop_party")
            self.mission_manager.activate_mission("mission_rooftop_party")
            self.mission_manager._refresh_availability()
            self._current_main_mission_text = "Mission 10: Go to the Rooftop party and hang out with the populars."
            # Place key NPCs on the rooftop for Day 4
            self._place_day4_rooftop_npcs()
            # Reset party scene state
            self._ava_rooftop_dialogue_completed = False
            self._ava_phone_on_chair = False
            self._ava_phone_spying = False
            self._ava_phone_timer = 15.0
            self._ava_phone_timer_active = False
            self._ava_phone_completed = False
            self._ava_phone_found_chat = False
            self._party_bad_feeling_shown = False
            self._coop_time_bonus_npcs = set()
        if hasattr(self, 'schedule_manager'):
            self.schedule_manager.reset_day()
        
        # Close cafeteria
        floor1 = self.school_map.get_floor(FLOOR_1F)
        if floor1:
            for door in floor1.doors:
                if getattr(door, "id", "") == "door_cafeteria":
                    door.locked = True
        
        self.state = GameState.PLAYING

    # ──────────────────────────────────────────────────────────
    #  CAR DEPARTURE CINEMATIC
    # ──────────────────────────────────────────────────────────

    def _start_car_departure(self):
        """Begin the cinematic: player walks to car, gets in, car drives left off-map."""
        self._car_departure_active = True
        self._car_depart_phase = "walk_to_car"
        self._car_depart_timer = 0.0
        # Car world position (tracks where the car is during the drive)
        self._car_depart_wx = float(self._parked_car_rect.centerx)
        self._car_depart_wy = float(self._parked_car_rect.centery)

    def _update_car_departure(self, dt: float):
        """Tick the car departure cinematic state machine."""
        self._clear_bus_path()
        if self._car_depart_phase == "walk_to_car":
            # Move player toward the car
            car_cx = self._parked_car_rect.centerx
            car_cy = self._parked_car_rect.centery
            dx = car_cx - self.player.rect.centerx
            dy = car_cy - self.player.rect.centery
            dist = (dx**2 + dy**2) ** 0.5
            if dist > 10:
                speed = 200 * dt
                self.player.rect.centerx += int((dx / dist) * speed)
                self.player.rect.centery += int((dy / dist) * speed)
            else:
                # Player reached the car — switch to driving
                self._car_depart_phase = "drive_away"
                self._car_depart_timer = 0.0
            self.camera.update(self.player)

        elif self._car_depart_phase == "drive_away":
            # Drive straight left until off-map
            self._car_depart_wx -= 400 * dt
            self.player.rect.centerx = int(self._car_depart_wx)
            self.player.rect.centery = int(self._car_depart_wy)
            self.camera.update(self.player)

            # Controller vibration while driving
            if self.controller and self.controller.connected:
                self.controller.rumble(0.3, 0.5, 100)

            # Off the left edge of the map
            if self._car_depart_wx < -200:
                self._car_departure_active = False
                if self.controller and self.controller.connected:
                    self.controller.stop_rumble()
                self._begin_day_transition()

    def _build_car_surface(self) -> pygame.Surface:
        """Load the school bus sprite from data/tiles."""
        import os
        sprite_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "tiles", "ME_Singles_Vehicles_32x32_Bus_Left_1.png"
        )
        try:
            bus_sprite = pygame.image.load(sprite_path).convert_alpha()
            # Scale to appropriate size (300x135 for consistency with parking lot)
            scaled_bus = pygame.transform.scale(bus_sprite, (300, 135))
            return scaled_bus
        except Exception as e:
            print(f"Failed to load bus sprite from {sprite_path}: {e}")
            # Fallback: return a yellow placeholder if sprite not found
            w, h = 300, 135
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            bus_yellow = (250, 160, 30)
            pygame.draw.rect(surf, bus_yellow, (0, 30, w, 75), border_radius=9)
            pygame.draw.rect(surf, bus_yellow, (0, 0, w, 38), border_radius=6)
            return surf

    def _draw_parked_car(self, surface=None):
        surface = surface or self.screen
        """Draw the parking-lot school bus rotated to match its collision box."""
        car_surf = self._build_car_surface()

        if self._car_departure_active and self._car_depart_phase == "drive_away":
            sx, sy = self.camera.apply_pos(self._car_depart_wx, self._car_depart_wy)
            rect = car_surf.get_rect(center=(sx, sy))
            surface.blit(car_surf, rect)
        else:
            cr = self.camera.apply_rect(self._parked_car_rect)
            car_surf = pygame.transform.flip(car_surf, True, False)
            surface.blit(car_surf, (cr.x, cr.y - 10))

    def _build_regular_car_surface(self, color: tuple) -> pygame.Surface:
        """Create a regular car sprite surface (200x90)."""
        w, h = 200, 90
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        # Body
        pygame.draw.rect(surf, color, (0, 20, w, 50), border_radius=12)
        # Roof
        roof_color = (max(0, color[0]-20), max(0, color[1]-20), max(0, color[2]-20))
        pygame.draw.rect(surf, roof_color, (40, 0, 120, 25), border_radius=8)
        # Windows
        pygame.draw.rect(surf, (80, 130, 180), (50, 5, 45, 18), border_radius=4)
        pygame.draw.rect(surf, (80, 130, 180), (105, 5, 45, 18), border_radius=4)
        # Wheels
        pygame.draw.circle(surf, (25, 25, 25), (40, 70), 14)
        pygame.draw.circle(surf, (25, 25, 25), (w - 40, 70), 14)
        # Headlights
        pygame.draw.rect(surf, (255, 220, 80), (w - 6, 35, 6, 12), border_radius=2)
        pygame.draw.rect(surf, (255, 220, 80), (w - 6, 55, 6, 12), border_radius=2)
        # Tail lights
        pygame.draw.rect(surf, (220, 40, 40), (0, 35, 6, 12), border_radius=2)
        pygame.draw.rect(surf, (220, 40, 40), (0, 55, 6, 12), border_radius=2)
        return surf

    def _draw_extra_parked_cars(self, surface=None):
        surface = surface or self.screen
        """Draw additional cars parked in the lot using new sprites."""
        if self.current_floor != 0:
            return
            
        if not hasattr(self, '_extra_car_sprites'):
            self._extra_car_sprites = {}
            
        for rect, sprite_name, angle in self._extra_parked_cars:
            if sprite_name not in self._extra_car_sprites:
                import os
                path = os.path.join("data", "tiles", sprite_name)
                try:
                    img = pygame.image.load(path).convert_alpha()
                    # Scale the sprite to perfectly fit the collision rectangle
                    img = pygame.transform.scale(img, (rect.width, rect.height))
                    self._extra_car_sprites[sprite_name] = img
                except Exception as e:
                    print(f"Failed to load car sprite {sprite_name}: {e}")
                    self._extra_car_sprites[sprite_name] = self._build_regular_car_surface((100, 100, 100))
                    
            car_surf = self._extra_car_sprites[sprite_name]
            cr = self.camera.apply_rect(rect)
            # The sprites already face left or right natively, no flipping needed!
            surface.blit(car_surf, (cr.x, cr.y))

    def _draw_car_panel(self):
        """Draw the 'End the day?' confirmation panel overlay."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        # Panel box (larger to hold multiplayer voting status nicely)
        box_w, box_h = 500, 230
        bx = (SCREEN_WIDTH - box_w) // 2
        by = (SCREEN_HEIGHT - box_h) // 2
        pygame.draw.rect(self.screen, (30, 30, 45), (bx, by, box_w, box_h), border_radius=16)
        pygame.draw.rect(self.screen, WHITE, (bx, by, box_w, box_h), 3, border_radius=16)

        # Title
        title_font = pygame.font.Font(VT323_PATH, 28)
        title = title_font.render("End the day and go home?", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, by + 45)))

        # Co-op voting status
        if self.multiplayer:
            votes = (1 if self.car_departure_voted else 0) + (1 if self.remote_car_departure_voted else 0)
            v_font = pygame.font.Font(VT323_PATH, 20)
            v_color = (50, 255, 120) if votes == 2 else ((50, 200, 100) if votes == 1 else (180, 180, 200))
            v_lbl = v_font.render(f"Ready: {votes}/2", True, v_color)
            self.screen.blit(v_lbl, v_lbl.get_rect(center=(SCREEN_WIDTH // 2, by + 90)))

        # Draw buttons
        btn_y = by + 145
        accept_rect = pygame.Rect(bx + 60, btn_y, 160, 44)
        cancel_rect = pygame.Rect(bx + 280, btn_y, 160, 44)
        
        mouse_pos = pygame.mouse.get_pos()
        hover_accept = accept_rect.collidepoint(mouse_pos)
        hover_cancel = cancel_rect.collidepoint(mouse_pos)

        sel = getattr(self, "_car_panel_selection", "accept")
        controller_connected = self.controller and self.controller.connected
        
        acc_active = hover_accept or (controller_connected and sel == "accept")
        can_active = hover_cancel or (controller_connected and sel == "cancel")

        accept_color = (100, 150, 255) if acc_active else (60, 100, 200)
        cancel_color = (100, 150, 255) if can_active else (60, 100, 200)
        acc_outline = (255, 220, 50) if acc_active else WHITE
        can_outline = (255, 220, 50) if can_active else WHITE

        pygame.draw.rect(self.screen, accept_color, accept_rect, border_radius=10)
        pygame.draw.rect(self.screen, acc_outline, accept_rect, 3, border_radius=10)

        pygame.draw.rect(self.screen, cancel_color, cancel_rect, border_radius=10)
        pygame.draw.rect(self.screen, can_outline, cancel_rect, 3, border_radius=10)

        font = pygame.font.Font(VT323_PATH, 20)
        acc_text = font.render("\u24B6 Accept" if controller_connected and sel == "accept" else "Accept", True, WHITE)
        can_text = font.render("\u24B7 Cancel" if controller_connected and sel == "cancel" else "Cancel", True, WHITE)

        self.screen.blit(acc_text, acc_text.get_rect(center=accept_rect.center))
        self.screen.blit(can_text, can_text.get_rect(center=cancel_rect.center))

        # Handle mouse clicks
        if pygame.mouse.get_pressed()[0] and getattr(self, "_car_panel_input_delay", 0) <= 0:
            if hover_accept:
                if self._can_end_school_day():
                    if self.multiplayer:
                        self.car_departure_voted = True
                    else:
                        self._car_panel_active = False
                        self._start_car_departure()
                else:
                    self._car_panel_active = False
                    self._car_panel_cooldown = 1.0
                    self.ui.show_notification("You cannot leave school early.", NOTIF_ERROR)
            elif hover_cancel:
                self._car_panel_active = False
                self.car_departure_voted = False
                self._car_panel_cooldown = 1.0

    def _can_end_school_day(self) -> bool:
        """Return True when the current day can advance, including co-op host progress."""
        if self.time_of_day_minutes >= 16 * 60:
            return True
        story_flags = {
            1: (
                self._day1_story_complete,
                getattr(self, "_remote_day1_story_complete", False),
            ),
            2: (
                getattr(self, "_day2_story_complete", False),
                getattr(self, "_remote_day2_story_complete", False),
            ),
            3: (
                getattr(self, "_day3_story_complete", False),
                getattr(self, "_remote_day3_story_complete", False),
            ),
        }
        local_done, remote_done = story_flags.get(self.day_number, (False, False))
        return local_done or (self.multiplayer and remote_done)

    def _draw_day_transition(self):
        """Draw fullscreen black screen with 'Day X' text."""
        self.screen.fill((0, 0, 0))

        # "Day X" title
        day_font = pygame.font.Font(VT323_PATH, 80)
        day_text = day_font.render(f"Day {self._day_transition_target_day}", True, WHITE)
        self.screen.blit(day_text, day_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 20)))

        # Subtitle
        sub_font = pygame.font.Font(VT323_PATH, 28)
        sub_text = sub_font.render("A new day begins...", True, (160, 160, 180))
        self.screen.blit(sub_text, sub_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 50)))
        # Subtitle
        sub_font = pygame.font.Font(VT323_PATH, 28)
        sub_text = sub_font.render("A new day begins...", True, (160, 160, 180))
        self.screen.blit(sub_text, sub_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 50)))
