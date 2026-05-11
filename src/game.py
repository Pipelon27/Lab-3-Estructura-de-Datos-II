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
import pygame
from collections import deque

from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS,
    BLACK, WHITE,
    FLOOR_1F, FLOOR_2F, FLOOR_CAMPUS, FLOOR_BASEMENT, FLOOR_ROOFTOP, FLOOR_SIZES, ZONE_TO_FLOOR,
    PLAYER_SIZE, NPC_INTERACTION_RANGE, ATTACK_RANGE, NPC_SPEED,
    GameState, Character, DayPhase, ItemCategory, Ending, SocialGroup, Direction,
    NOTIF_SUCCESS, NOTIF_WARNING, NOTIF_ERROR, NOTIF_INFO,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
    KEY_INTERACT, KEY_USE, KEY_INVENTORY, KEY_SKILL_TREE,
    KEY_HELP, KEY_PAUSE, KEY_MAP,
    KEY_LIGHT_ATTACK, KEY_HEAVY_ATTACK, KEY_BLOCK, KEY_DASH, KEY_DASH_ALT, KEY_DASH_ALT2,
    KEY_HACK, KEY_PHONE,
    MOTIVATIONAL_MESSAGES,
)
from src.phone      import Phone
from src.map        import SchoolMap
from src.player     import Aiden, Lena
from src.npc        import NPCManager, NPC
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
from src.controller import get_controller, init_controller, update_controller, XBOX_A

FLOOR_COLISEUM_INTERIOR = 5
FLOOR_PINGPONG_INTERIOR = 6


# Pools for dynamically generated classroom NPC names
CLASS_FIRST_NAMES = [
    # Hispanic/Latin
    "Adrian", "Brianna", "Carlos", "Daniela", "Elena", "Felipe",
    "Gabriela", "Hector", "Isabella", "Javier", "Karina", "Lorenzo",
    "Mariana", "Nicolas", "Olivia", "Pablo", "Renata", "Santiago",
    "Tatiana", "Valeria",
    # Asian
    "Yuki", "Kenji", "Mei", "Chen", "Ji-soo", "Haruto", "Aoi", "Wei", "Sora", "Min-ho",
    # African
    "Amara", "Kwame", "Zuri", "Nala", "Kofi", "Imani", "Jabari", "Keisha", "Tunde", "Zola",
    # Middle Eastern / Arabic
    "Fatima", "Omar", "Aaliyah", "Zaid", "Layla", "Hassan", "Inaya", "Malik", "Soraya", "Idris",
    # European / Other
    "Sven", "Lars", "Dimitri", "Matteo", "Chloe", "Hans", "Ingrid", "Luca", "Olga", "Stefan"
]

CLASS_LAST_NAMES = [
    "Alvarez", "Benitez", "Castillo", "Dominguez", "Espinoza",
    "Fernandez", "Garcia", "Herrera", "Ibarra", "Juarez",
    "Lopez", "Martinez", "Navarro", "Ortega", "Paredes",
    "Quintero", "Ramirez", "Serrano", "Torres", "Vargas"
]


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
        self.pause_sel      = 0

        # Transition cooldown (prevents rapid re-triggering)
        self._transition_cooldown: float = 0.0
        self._bathroom_block_timer: float = 0.0
        self._bathroom_blocked_room: str | None = None
        self._cafeteria_block_timer: float = 0.0

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

        # Classroom simulation state
        self._classroom_groups: list[dict] = []
        self._class_cycle_index: int = 0
        self._class_phase: str = "classroom"
        self._class_event_schedule = [
            (570, "cafeteria"),   # 09:30 AM
            (660, "classroom"),   # 11:00 AM (Break ends)
            (810, "cafeteria"),   # 01:30 PM (Lunch starts)
            (900, "classroom"),   # 03:00 PM (Lunch ends)
        ]
        self._classroom_room_defs = [
            ("f2_classrooms", "General Studies", 8),
            ("f2_music_room", "Music Ensemble", 6),
            ("f2_art_room", "Art Studio", 6),
            ("f2_conference", "Faculty Seminar", 5),
        ]
        self._cafeteria_rect: pygame.Rect | None = None
        self._class_spawn_counter: int = 0
        self._class_used_names: set[str] = set()

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
        self.pause_options: list[str] = ["Resume", "Change Character", "Main Menu", "Quit"]
        self.return_to_menu: bool = False

        # ── Day transition screen ──
        self._day_transition_active: bool = False
        self._day_transition_timer: float = 0.0
        self._day_transition_target_day: int = 2

        # ── Parked car (parking lot) ──
        self._parked_car_rect = pygame.Rect(900, 2400, 300, 105)
        self._extra_parked_cars = [
            (pygame.Rect(350, 2600, 200, 90), (180, 50, 50), 180),    # Red, faces LEFT
            (pygame.Rect(700, 2100, 200, 90), (50, 100, 180), 0),     # Blue, faces RIGHT
            (pygame.Rect(600, 2750, 200, 90), (50, 180, 80), 180),    # Green, faces LEFT
            (pygame.Rect(350, 2150, 200, 90), (150, 150, 160), 0),    # Silver, faces RIGHT
            (pygame.Rect(1000, 2600, 200, 90), (45, 45, 50), 180),    # Soft black, faces LEFT
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

        if self.character == Character.AIDEN:
            self.player = Aiden(cx, cy)
            if self.multiplayer:
                self.remote_player = Lena(cx, cy)
        else:
            self.player = Lena(cx, cy)
            if self.multiplayer:
                self.remote_player = Aiden(cx, cy)

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

        # ── Gordon Ramsay (The Chef) ──
        f1 = self.school_map.get_floor(FLOOR_1F)
        caf = f1.rooms.get("f1_cafeteria")
        if caf:
            gordon = NPC(
                "npc_gordon", "Gordon Ramsay", 
                SocialGroup.FACULTY, "Chef", "Gordon is shouting about undercooked lamb.",
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

        # Ensure fixed story NPC placement and classroom simulation seeds
        self._initialize_director_office()
        self._setup_classroom_groups()

        # ── Position Noah Carter in the Entrance for the intro cinematic ──
        noah_carter = self.npc_manager.get_npc_by_id("npc_noah_carter")
        if noah_carter:
            noah_carter.current_floor = FLOOR_CAMPUS
            noah_carter.rect.center = (2000, 2650)
            noah_carter.ai_enabled = False
            noah_carter.ignore_schedule = True
            noah_carter.show_name = True

        # ── Push random NPCs out of staircase rooms during cinematic ──
        stair_ids = {"f1_stairs_2f", "f1_basement_stairs",
                     "f2_stairs_1f", "f2_stairs_rooftop", "bs_stairs_1f"}
        for npc in self.npc_manager.npcs.values():
            if npc.id.startswith("npc_rnd_"):
                fl = self.school_map.get_floor(npc.current_floor)
                if fl:
                    room = fl.get_room_at(npc.rect.centerx, npc.rect.centery)
                    if room and room.id in stair_ids:
                        # Move to centre of the floor's main corridor
                        npc.rect.center = (1600, 1000)

        # Ensure Noah's spawn area is clear
        self._clear_noah_area(radius=160)

    def _init_systems(self):
        self.reputation      = ReputationSystem()
        self.mission_manager = MissionManager()
        self.mission_manager.load_missions_from_json()
        self.combat_system   = CombatSystem()
        self.hacking_game    = HackingMinigame()
        self.trade_system    = TradeSystem()
        self.dialogue_system = DialogueSystem()
        self.dialogue_system.load_dialogues_from_json()
        self.camera = Camera(self._floor_w, self._floor_h)
        # Snap camera to entrance for intro cinematic to prevent lerp-from-zero spawn bugs
        target_x = 2000 - SCREEN_WIDTH // 2
        target_y = 2700 - SCREEN_HEIGHT // 2
        self.camera.offset.x = max(0, min(target_x, self.camera.map_width - SCREEN_WIDTH))
        self.camera.offset.y = max(0, min(target_y, self.camera.map_height - SCREEN_HEIGHT))
        # Ping-pong minigame
        self.pingpong = PingPongGame()
        self.phone = Phone(self.screen,
                          time_source=lambda: self.time_of_day_minutes,
                          player_name=self.character.value)

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

    def _setup_classroom_groups(self):
        floor2 = self.school_map.get_floor(FLOOR_2F)
        floor1 = self.school_map.get_floor(FLOOR_1F)
        if not floor2:
            return
        cafeteria = floor1.rooms.get("f1_cafeteria") if floor1 else None
        self._cafeteria_rect = cafeteria.rect.inflate(-120, -120) if cafeteria else None

        groups: list[dict] = []
        for room_id, topic, count in self._classroom_room_defs:
            room = floor2.rooms.get(room_id)
            if not room:
                continue
            
            # Setup initial classroom layout: Teacher on the left 25%, Students in the rest
            teacher_area_w = int(room.rect.width * 0.25)
            student_area_w = room.rect.width - teacher_area_w
            
            teacher = self._create_class_npc(role="Teacher")
            teacher.show_name = True
            teacher.current_floor = FLOOR_2F
            teacher.rect.centerx = room.rect.x + teacher_area_w // 2
            teacher.rect.centery = room.rect.centery
            # Restrict teacher to a narrow vertical strip to simulate patrolling
            teacher.bound_rect = pygame.Rect(room.rect.x + 20, room.rect.y + 40, teacher_area_w - 40, room.rect.height - 80)
            teacher.ignore_schedule = True
            teacher.ai_enabled = True
            teacher_home = (teacher.rect.centerx, teacher.rect.centery)

            students = []
            student_homes = []
            cols = 4 if count > 6 else 3
            rows = (count + cols - 1) // cols
            for i in range(count):
                student = self._create_class_npc(role="Student")
                student.current_floor = FLOOR_2F
                
                r, c = i // cols, i % cols
                cell_w = (student_area_w - 100) // cols
                cell_h = (room.rect.height - 100) // rows
                
                student.rect.centerx = room.rect.x + teacher_area_w + 50 + c * cell_w + cell_w // 2
                student.rect.centery = room.rect.y + 50 + r * cell_h + cell_h // 2
                
                student.bound_rect = room.rect.inflate(-60, -60)
                student.ignore_schedule = True
                student.ai_enabled = False # Students stay still in class
                students.append(student)
                student_homes.append((student.rect.centerx, student.rect.centery))

            groups.append({
                "room_id": room_id,
                "topic": topic,
                "teacher": teacher,
                "students": students,
                "teacher_home": teacher_home,
                "student_homes": student_homes,
            })

        # Register NPCs into manager
        for group in groups:
            teacher = group["teacher"]
            tid = f"npc_class_teacher_{group['room_id']}"
            teacher.id = tid
            # Removed topic suffix to keep only the name as requested
            self._register_npc(teacher)
            for idx, student in enumerate(group["students"], start=1):
                student.id = f"npc_class_student_{group['room_id']}_{idx}"
                self._register_npc(student)

        self._classroom_groups = groups
        self._class_phase = "classroom"

    def _create_class_npc(self, role: str) -> NPC:
        from settings import NPC_SIZE
        gender = random.choice(["male", "female"])
        first = random.choice(CLASS_FIRST_NAMES)
        
        if role == "Teacher":
            # User requested to use 'Teacher' instead of Mr/Mrs
            name = f"Teacher {first}"
        else:
            # Students only get the first name
            name = first
            
        while name in self._class_used_names:
            first = random.choice(CLASS_FIRST_NAMES)
            if role == "Teacher":
                name = f"Teacher {first}"
            else:
                name = first
                
        self._class_used_names.add(name)
        group = random.choice(list(SocialGroup))
        npc = NPC(f"temp_{role.lower()}_{self._class_spawn_counter}", name, group,
                  f"{role} in class", f"{role} secrets", gender=gender)
        self._class_spawn_counter += 1
        npc.ai_enabled = True
        npc.show_name = True
        return npc

    def _register_npc(self, npc: NPC):
        self.npc_manager.npcs[npc.id] = npc
        self.npc_manager.relationships.add_node(npc.id)

    def _init_ui(self):
        self.ui = UI(self.screen)
        self.world_map = WorldMap(self.school_map)
        self.phone._map_ref = self.world_map

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

    # ──────────────────────────────────────────────────────────
    #  EVENT HANDLING
    # ──────────────────────────────────────────────────────────

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
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
            if event.type == pygame.KEYDOWN:
                self._on_key_down(event)
            elif event.type == pygame.KEYUP:
                pass  # movement uses get_pressed()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Skip button in cinematic
                if self.state == GameState.INTRO_CINEMATIC:
                    skip_rect = getattr(self, '_skip_btn_rect', None)
                    if skip_rect and skip_rect.collidepoint(event.pos):
                        self._skip_cinematic()
                        continue
                if self.state == GameState.TRADING:
                    self.trade_system.handle_click(event.pos)
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
                        # Click anywhere to go back to wallet view
                        self.active_wallet_item = None
                        self.wallet_focus_item = None
                    else:
                        if self.ui.wallet_id_rect.collidepoint(event.pos):
                            self.active_wallet_item = "id"
                            self.wallet_focus_item = "id"
                        elif self.ui.wallet_bill_rect.collidepoint(event.pos):
                            self.active_wallet_item = "bill"
                            self.wallet_focus_item = "bill"
                        elif not self.ui.wallet_bg_rect.collidepoint(event.pos) and not self.ui.wallet_bill_rect.collidepoint(event.pos):
                            self.state = GameState.PLAYING
                            self.wallet_focus_item = None

    def _handle_controller_input(self):
        """Handle Xbox controller button input (called every frame)."""
        if not self.controller or not self.controller.connected:
            return

        controller = self.controller

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
            # D-pad toggles focus on Skip button
            menu_h = controller.get_menu_direction_horizontal()
            menu_v = controller.get_menu_direction()
            if menu_h != 0 or menu_v != 0:
                self._cine_skip_focused = not self._cine_skip_focused
            # A button: if skip is focused, skip; otherwise advance dialogue
            if controller.is_confirm_pressed() or controller.is_interact_pressed():
                if self._cine_skip_focused:
                    self._skip_cinematic()
                else:
                    self._advance_cinematic_dialogue()
        elif self.state == GameState.PLAYING:
            self._handle_controller_playing(controller)
        elif self.state == GameState.PAUSED:
            self._handle_controller_paused(controller)
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
        elif self.state == GameState.DAY_OVER:
            if controller.is_confirm_pressed():
                self._begin_day_transition()

    def _toggle_pause(self):
        """Toggle pause state."""
        if self.state == GameState.PAUSED:
            self.state = getattr(self, 'previous_state', GameState.PLAYING)
        elif self.state in (GameState.PLAYING, GameState.INTRO_CINEMATIC):
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
                self._car_panel_active = False
                if sel == "accept":
                    self._start_car_departure()
                else:
                    self._car_panel_cooldown = 1.0
            elif controller.is_cancel_pressed():
                self._car_panel_active = False
                self._car_panel_cooldown = 1.0
            return

        # D-pad up: open phone directly
        menu_v = controller.get_menu_direction()
        if menu_v == -1:  # up
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
            # A = Interact or Dash when no HUD focus
            if controller.is_interact_pressed():
                npc = self._nearest_npc(NPC_INTERACTION_RANGE)
                if npc:
                    self._try_interact()
                elif self._try_building_entry_confirm():
                    pass
                else:
                    self.player.start_dash()

            # RT dash is handled in player.update() via controller.rt_value
            # But we can also trigger dash on press for responsiveness
            if controller.is_dash_triggered():
                npc = self._nearest_npc(NPC_INTERACTION_RANGE)
                if not npc:  # Only dash if not interacting
                    self.player.start_dash()

        # RB = Light Attack (Aiden) or Hack (Lena)
        if controller.is_attack_pressed():
            if self.character == Character.AIDEN:
                target = self._nearest_npc(ATTACK_RANGE)
                if target:
                    self.combat_system.start_combat(self.player, target)
                    self.state = GameState.COMBAT
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
                if self.multiplayer:
                    self.ui.show_notification("Cannot change character: Roles are already established in co-op mode.", NOTIF_ERROR)
                    return
                # Character swap logic (same as keyboard)
                from settings import Character, NOTIF_INFO
                from src.player import Aiden, Lena

                self.character = Character.LENA if self.character == Character.AIDEN else Character.AIDEN

                old_level = self.player.level
                old_xp = self.player.xp
                old_sp = getattr(self.player, 'skill_points', 0)
                old_hp = self.player.health
                old_max_hp = self.player.max_health

                old_x, old_y = self.player.rect.center
                if self.character == Character.AIDEN:
                    self.player = Aiden(old_x, old_y)
                else:
                    self.player = Lena(old_x, old_y)

                self.player.level = old_level
                self.player.xp = old_xp
                self.player.skill_points = old_sp
                self.player.max_health = old_max_hp
                self.player.health = min(old_hp, self.player.max_health)
                self._last_known_level = self.player.level

                self.ui.show_notification(f"Swapped to {self.character.value.title()}", NOTIF_INFO)
                self.state = getattr(self, 'previous_state', GameState.PLAYING)
            elif sel == 2:  # Main Menu
                self.return_to_menu = True
                self.running = False
            else:  # Quit
                self.running = False

        if controller.is_cancel_pressed():
            self.state = getattr(self, 'previous_state', GameState.PLAYING)

    def _handle_controller_wallet(self, controller):
        """Handle controller input during WALLET state."""
        focus_cycle = ["id", "bill"]

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
            elif self.state == GameState.PAUSED:
                self.state = getattr(self, 'previous_state', GameState.PLAYING)
            elif self.state == GameState.PLAYING:
                if self._car_panel_active:
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
            GameState.PINGPONG:        lambda e: self.pingpong.handle_input(e),
            GameState.COMBAT:           lambda e: self.combat_system.handle_input(e, self.player),
            GameState.HACKING:          lambda e: self.hacking_game.handle_input(e),
            GameState.TRADING:          lambda e: self.trade_system.handle_input(e),
            GameState.INVENTORY_SCREEN: lambda e: self.inventory.handle_input(e),
            GameState.SKILL_TREE_SCREEN:lambda e: self.player.skill_tree.handle_input(e, self.player),
            GameState.PAUSED:           self._keys_paused,
            GameState.GAME_OVER:        self._keys_game_over,
        }.get(self.state)
        if handler:
            handler(event)

    # ── key handlers per state ────────────────────────────────

    def _keys_playing(self, event: pygame.event.Event):
        # ── Car panel active: SPACE confirms, ESC dismisses ──
        if self._car_panel_active:
            if self._car_panel_input_delay > 0:
                return  # ignore input during delay
            if event.key == KEY_INTERACT:
                self._car_panel_active = False
                self._start_car_departure()
            elif event.key == KEY_PAUSE:
                self._car_panel_active = False
                self._car_panel_cooldown = 1.0  # prevent re-trigger
            return

        # If SPACE (KEY_INTERACT) and an NPC is nearby, open dialogue;
        # otherwise treat SPACE (and dash aliases) as dash.
        if event.key == KEY_INTERACT:
            npc = self._nearest_npc(NPC_INTERACTION_RANGE)
            if npc:
                self._try_interact()
            elif self._try_building_entry_confirm():
                pass
            else:
                self.player.start_dash()
        elif event.key in (KEY_DASH_ALT, KEY_DASH_ALT2):
            # alt dash keys still trigger dash
            self.player.start_dash()
        elif event.key == KEY_INVENTORY:
            # Inventory removed - open wallet instead
            self.previous_state = self.state
            self.state = GameState.WALLET
            self.active_wallet_item = None
            self.wallet_focus_item = None
        elif event.key == KEY_SKILL_TREE:
            self.previous_state = self.state
            self.state = GameState.SKILL_TREE_SCREEN
        elif event.key == KEY_PHONE:
            self.phone.toggle_phone()
        elif event.key == KEY_LIGHT_ATTACK and self.character == Character.AIDEN:
            target = self._nearest_npc(ATTACK_RANGE)
            if target:
                self.combat_system.start_combat(self.player, target)
                self.state = GameState.COMBAT
        elif event.key == KEY_HACK and self.character == Character.LENA:
            hackable = self._get_hackable()
            if hackable:
                self.hacking_game.start(hackable, self.player)
                self.state = GameState.HACKING
        

    def _keys_cinematic(self, event: pygame.event.Event):
        """Handle keyboard input during the intro cinematic."""
        if event.key in (pygame.K_SPACE, pygame.K_RETURN):
            self._advance_cinematic_dialogue()

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
            elif sel == 1:  # Change Character
                if self.multiplayer:
                    self.ui.show_notification("Cannot change character: Roles are already established in co-op mode.", NOTIF_ERROR)
                    return
                from settings import Character, NOTIF_INFO
                from src.player import Aiden, Lena
                
                self.character = Character.LENA if self.character == Character.AIDEN else Character.AIDEN
                
                # Preserve stats so swapping doesn't reset progress!
                old_level = self.player.level
                old_xp = self.player.xp
                old_sp = getattr(self.player, 'skill_points', 0)
                old_hp = self.player.health
                old_max_hp = self.player.max_health

                old_x, old_y = self.player.rect.center
                if self.character == Character.AIDEN:
                    self.player = Aiden(old_x, old_y)
                else:
                    self.player = Lena(old_x, old_y)
                
                self.player.level = old_level
                self.player.xp = old_xp
                self.player.skill_points = old_sp
                self.player.max_health = old_max_hp
                self.player.health = min(old_hp, self.player.max_health)
                self._last_known_level = self.player.level
                    
                self.ui.show_notification(f"Swapped to {self.character.value.title()}", NOTIF_INFO)
                self.state = getattr(self, 'previous_state', GameState.PLAYING)
            elif sel == 2:  # Main Menu — return to menu without closing the app
                self.return_to_menu = True
                self.running = False
            else:  # Quit — actually close the application
                self.running = False
        elif event.key == pygame.K_q:
            self.running = False

    def _keys_game_over(self, event: pygame.event.Event):
        if event.key == KEY_PAUSE:
            self.running = False

    # ──────────────────────────────────────────────────────────
    #  INTERACTION HELPERS
    # ──────────────────────────────────────────────────────────

    def _nearest_npc(self, radius: float):
        """Return the closest NPC within *radius*, or None."""
        npcs = self.npc_manager.get_npcs_on_floor(self.current_floor)
        px, py = self.player.rect.center
        best, best_d = None, radius
        for npc in npcs:
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
        """Interact with nearest NPC."""
        npc = self._nearest_npc(NPC_INTERACTION_RANGE)
        if npc:
            dlg_id = npc.get_dialogue_id(self.character)
            if dlg_id:
                self.dialogue_system.start_dialogue(
                    dlg_id, npc, self.player, self.reputation,
                )
                self.state = GameState.DIALOGUE
                self.mission_manager.advance_objective_event("talk_to", npc.id)

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
                "spawn": (650, 640),
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

    def _try_building_entry_confirm(self) -> bool:
        target = self._entry_prompt_target
        if not target:
            return False
        sx, sy = target["spawn"]
        self._go_to_floor(target["target_floor"], sx, sy)
        self._transition_cooldown = 0.5
        self._entry_prompt_cooldown = 0.6
        self._entry_prompt_target = None
        return True

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
        floor = self.school_map.get_floor(floor_id)
        if not floor:
            return False

        room = floor.get_room_at(tx, ty)
        if floor_id == FLOOR_CAMPUS and room:
            if room.id == "c_tennis":
                self._go_to_floor(FLOOR_PINGPONG_INTERIOR, 650, 640)
                return True
            if room.id == "c_coliseum":
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
        if self.state != GameState.INTRO_CINEMATIC:
            self.phone.update(dt)
            pt = self.phone.consume_pending_teleport()
            if pt:
                self._try_teleport_to(pt[0], pt[1], pt[2])
        # Always tick UI (notifications)
        self.ui.update(dt)
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
            return  # freeze everything else

        # ── Car departure cinematic ──
        if self._car_departure_active:
            self._update_car_departure(dt)
            return  # freeze normal gameplay

        if not hasattr(self, '_last_known_level'):
            self._last_known_level = self.player.level
        if self.player.level > self._last_known_level:
            self._last_known_level = self.player.level
            if hasattr(self.ui, 'trigger_level_up'):
                self.ui.trigger_level_up()

        if self.state == GameState.INTRO_CINEMATIC:
            self._update_cinematic(dt)
            if self.multiplayer and self.network:
                self._sync_network(dt)

            # NPCs keep moving normally during cinematic
            floor = self.school_map.get_floor(self.current_floor)
            npc_walls = list(floor.walls) if floor else []
            if self._player_spawned:
                npc_walls.append(self.player.rect)
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
                restricted_rooms=stair_restricted)

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
            result = self.pingpong.update(dt)
            # 'settings' from the pause menu — exit minigame cleanly for now
            if result == 'settings':
                self.pingpong.finished = False
                self.pingpong.reset()
                self.state = GameState.PLAYING
                self.ui.show_notification("Settings not yet available in-game.", NOTIF_INFO)
            # When a match result arrives, show end-screen and apply reputation changes
            elif result is not None and not getattr(self.pingpong, 'waiting_for_dismiss', False):
                if result == "win":
                    # add +20 reputation
                    self.reputation.reputation_score = min(100, self.reputation.reputation_score + 20)
                    self.player.level += 1
                    from settings import SKILL_POINT_PER_LEVEL
                    self.player.skill_points += SKILL_POINT_PER_LEVEL
                    self.pingpong.end_message = "Win Match\n+20 Reputation\nLevel Up!"
                    if hasattr(self.ui, 'trigger_level_up'):
                        self.ui.trigger_level_up()
                    self._last_known_level = self.player.level
                elif result == "lose":
                    if self.reputation.reputation_score > 0:
                        self.reputation.reputation_score = max(0, self.reputation.reputation_score - 10)
                        self.pingpong.end_message = "Lose Match\n-10 Reputation"
                    else:
                        self.pingpong.end_message = "Lose Match"
                self.pingpong.waiting_for_dismiss = True
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
        elif self.state == GameState.TRADING:
            result = self.trade_system.update()
            if result is not None:
                self.state = GameState.PLAYING

        if self.state in (GameState.PLAYING, GameState.COMBAT, GameState.DIALOGUE, GameState.PINGPONG):
            self._tick_time(dt)
            self._update_class_schedule()

        if getattr(self.pingpong, 'finished', False):
            self.pingpong.finished = False
            self.pingpong.reset()
            self.state = GameState.PLAYING

        # Network sync
        if self.multiplayer and self.network:
            self._sync_network(dt)

    def _update_playing(self, dt: float):
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
            if npc.id.startswith("npc_oscar_obs"):
                walls.append(npc.rect)
                continue
            
        previous_rect = self.player.rect.copy()
        
        # Add locked doors to collision walls
        if floor:
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
            walls.append(self._parked_car_rect)
            for rect, _, _ in self._extra_parked_cars:
                walls.append(rect)
                    
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

        # ── Player pushes NPCs on contact ──────────────────────────────────
        # Stationary NPCs = heavy resistance (1px nudge), moving NPCs = light push
        from settings import NPC_SIZE
        floor1_ref = self.school_map.get_floor(FLOOR_1F)
        for _npc in npcs_on_floor:
            if _npc.id == "npc_gordon":
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
                else:
                    _npc.rect.x -= push_amt
            else:
                if pdy >= 0:
                    _npc.rect.y += push_amt
                else:
                    _npc.rect.y -= push_amt

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
        
        # Add locked doors to NPC walls to block them too
        if floor:
            for door in floor.doors:
                if door.locked:
                    npc_walls.append(door.rect)
        
        # Classroom and Staircase restriction for generic NPCs
        is_class_session = (self._class_phase == "classroom")
        restricted = [
            "f2_art_room", "f2_music_room", "f2_conference", "f2_classrooms",
            "f1_stairs_2f", "f1_basement_stairs", "f2_stairs_1f", "f2_stairs_rooftop", "bs_stairs_1f"
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
                classrooms_restricted=(is_class_session or self.current_floor == FLOOR_CAMPUS),
                restricted_rooms=restricted
            )

        # Apply pending bound_rect for classroom NPCs that have stopped
        for group in self._classroom_groups:
            for npc in [group["teacher"]] + group["students"]:
                pending = getattr(npc, '_pending_bound_rect', None)
                if pending and not npc.ai_enabled and npc.target_pos is None:
                    npc.bound_rect = pending
                    npc._pending_bound_rect = None

        # NPC-NPC collision separation inside the cafeteria
        floor1_ref = self.school_map.get_floor(FLOOR_1F)
        if floor1_ref and self.current_floor == FLOOR_1F:
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
                                    a.rect.x -= 1
                                else:
                                    b.rect.x -= 1
                                    a.rect.x += 1
                            else:
                                if dy >= 0:
                                    b.rect.y += 1
                                    a.rect.y -= 1
                                else:
                                    b.rect.y -= 1
                                    a.rect.y += 1

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

        # Update markers for key NPCs
        self._update_minimap_markers()

        # Check game-over
        if not self.player.is_alive():
            self.state = GameState.GAME_OVER

    # ── time of day ───────────────────────────────────────────

    def _tick_time(self, dt: float):
        increment = dt * self._time_scale
        if increment <= 0:
            return
        self.time_of_day_minutes = (self.time_of_day_minutes + increment) % (24 * 60)

    def _update_class_schedule(self):
        previous = self._last_time_minutes
        current = self.time_of_day_minutes
        self._last_time_minutes = current
        if not self._classroom_groups:
            return

        # --- Staggered entry/exit for non-classroom NPCs ---
        # 09:30 AM (570 mins) - Move random 1F NPCs to cafeteria (Break Time starts)
        if previous < 570 <= current:
            self._move_random_npcs_to_cafeteria()
        
        # 11:00 AM (660 mins) - Break Time is Over notification & leaving
        if previous < 660 <= current:
            self.ui.show_notification("Break Time is Over! Head back to class", NOTIF_WARNING, 4.0)
            get_controller().rumble(0.5, 0.5, 400)
            self._move_npcs_out_of_cafeteria()
        
        # 01:30 PM (810 mins) - Return to cafeteria for lunch
        if previous < 810 <= current:
            self._move_random_npcs_to_cafeteria()

        # 03:00 PM (900 mins) - Lunch Time is Over notification & leaving
        if previous < 900 <= current:
            self.ui.show_notification("Lunch Time is Over! Head back to class", NOTIF_WARNING, 4.0)
            get_controller().rumble(0.5, 0.5, 400)
            self._move_npcs_out_of_cafeteria()

        # Check for School Day Over (4:00 PM = 960 mins)
        if current >= 960 and self.state == GameState.PLAYING:
            self.state = GameState.DAY_OVER
            return

        for trigger_minutes, destination in self._class_event_schedule:
            # handle wrap-around midnight: detect crossing by comparing ranges
            if previous <= current:
                crossed = previous < trigger_minutes <= current
            else:
                crossed = previous < trigger_minutes or trigger_minutes <= current
            
            if crossed and self._class_phase != destination:
                # Visual announcements for major schedule shifts
                if trigger_minutes == 570: # 09:30 AM
                    self.ui.trigger_announcement("BREAK TIME!", "Class dismissed - Cafeteria is now open")
                    get_controller().rumble(0.7, 0.7, 500) # Vibrate for 0.5s
                elif trigger_minutes == 810: # 01:30 PM
                    self.ui.trigger_announcement("LUNCH TIME!", "Today's lunch is: Hamburger with French fries")
                    get_controller().rumble(0.7, 0.7, 500) # Vibrate for 0.5s

                # Disable students going to cafeteria during morning break (9:30 AM)
                if destination == "cafeteria" and trigger_minutes == 570:
                    self._move_class_groups("break")
                    continue
                
                self._move_class_groups(destination)
            
        # Update cafeteria door visual/physical state
        floor1 = self.school_map.get_floor(FLOOR_1F)
        if floor1:
            for door in floor1.doors:
                if getattr(door, "id", "") == "door_cafeteria":
                    door.locked = not self._is_cafeteria_open()

    def _move_class_groups(self, destination: str):
        """Move classroom NPC groups between classrooms, corridor break, and cafeteria."""
        if not self._classroom_groups:
            return

        floor2 = self.school_map.get_floor(FLOOR_2F)
        floor1 = self.school_map.get_floor(FLOOR_1F)
        corridor = floor2.rooms.get("f2_corridor") if floor2 else None
        cafeteria_rect = self._cafeteria_rect

        # Each room has: inside_door (inside the room near exit) and
        # corridor_pos (just outside in the corridor). NPCs walk:
        #   exit:  home → inside_door → corridor_pos → destination
        #   enter: origin → corridor_pos → inside_door → home seat
        _room_waypoints = {
            # f2_classrooms: triple-door gap at x=1480..1720 in wall at y=1950
            "f2_classrooms": {
                "inside":  (1600, 1970),
                "corridor": (1600, 1930),
            },
            # f2_art_room: double-door gap at y=456..616 in wall at x=1050
            "f2_art_room": {
                "inside":  (1030, 536),
                "corridor": (1080, 536),
            },
            # f2_music_room: double-door gap at y=1106..1266 in wall at x=1050
            "f2_music_room": {
                "inside":  (1030, 1186),
                "corridor": (1080, 1186),
            },
            # f2_conference: double-door gap at y=600..760 in wall at x=2150
            "f2_conference": {
                "inside":  (2170, 680),
                "corridor": (2130, 680),
            },
        }

        valid_phase = destination if destination in {"classroom", "cafeteria", "break"} else "classroom"
        self._class_phase = valid_phase

        for group in self._classroom_groups:
            teacher: NPC = group["teacher"]
            students: list[NPC] = group["students"]
            room_id = group["room_id"]
            room = floor2.rooms.get(room_id) if floor2 else None
            wp = _room_waypoints.get(room_id, {})
            inside_door = wp.get("inside")
            corridor_pos = wp.get("corridor")

            if valid_phase == "classroom":
                # Return to classroom: corridor_pos → inside_door → home seat
                # DON'T restore bound_rect now — NPCs are still in corridor.
                # Store pending bound_rect; it'll be applied after they stop.
                home = group.get("teacher_home")
                if home:
                    teacher.bound_rect = None  # free to walk back
                    teacher.ai_enabled = True
                    teacher.stop_at_target = True
                    teacher.speed_multiplier = 1.0
                    teacher._pending_bound_rect = pygame.Rect(
                        room.rect.x + 20, room.rect.y + 40,
                        int(room.rect.width * 0.25) - 40, room.rect.height - 80) if room else None
                    if corridor_pos and inside_door:
                        teacher.target_pos = corridor_pos
                        teacher.target_queue = [inside_door, home]
                    else:
                        teacher.target_pos = home
                        teacher.target_queue = []
                for idx, (npc, home_pos) in enumerate(zip(students, group.get("student_homes", []))):
                    npc.bound_rect = None  # free to walk back
                    npc.ai_enabled = True
                    npc.stop_at_target = True
                    npc.speed_multiplier = 1.0
                    npc.start_delay = (idx + 1) * 0.5
                    npc._pending_bound_rect = room.rect.inflate(-60, -60) if room else None
                    if corridor_pos and inside_door:
                        npc.target_pos = corridor_pos
                        npc.target_queue = [inside_door, home_pos]
                    else:
                        npc.target_pos = home_pos
                        npc.target_queue = []

            elif valid_phase == "cafeteria" and cafeteria_rect:
                self._caf_seat_pool = []  # fresh seats
                # Remove bound_rect so students can leave the room
                teacher.bound_rect = None
                seat = self._get_cafeteria_seat()
                teacher.ai_enabled = True
                teacher.stop_at_target = True
                teacher.speed_multiplier = 1.4
                if inside_door and corridor_pos:
                    teacher.target_pos = inside_door
                    teacher.target_queue = [corridor_pos, seat]
                else:
                    teacher.target_pos = seat
                    teacher.target_queue = []
                for idx, npc in enumerate(students):
                    npc.bound_rect = None  # free from room
                    seat = self._get_cafeteria_seat()
                    npc.ai_enabled = True
                    npc.stop_at_target = True
                    npc.speed_multiplier = 1.2
                    npc.start_delay = (idx + 1) * 0.5
                    if inside_door and corridor_pos:
                        npc.target_pos = inside_door
                        npc.target_queue = [corridor_pos, seat]
                    else:
                        npc.target_pos = seat
                        npc.target_queue = []

            elif valid_phase == "break" and corridor:
                # Remove bound_rect so students can leave the room
                # Exit: inside_door → corridor_pos → random spot in corridor
                break_rect = corridor.rect.inflate(-160, -160)
                for idx, npc in enumerate([teacher] + students):
                    npc.bound_rect = None  # free from room
                    npc.ai_enabled = True
                    npc.stop_at_target = True
                    npc.speed_multiplier = 1.1
                    npc.start_delay = idx * 0.5
                    tx = random.randint(break_rect.left + 20, break_rect.right - 20)
                    ty = random.randint(break_rect.top + 20, break_rect.bottom - 20)
                    if inside_door and corridor_pos:
                        npc.target_pos = inside_door
                        npc.target_queue = [corridor_pos, (tx, ty)]
                    else:
                        npc.target_pos = (tx, ty)
                        npc.target_queue = []

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
            if npc is noah or not npc.id.startswith("npc_rnd_"):
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
            (FLOOR_ROOFTOP, pygame.Rect(1250, 50, 1100, 900), None),      # ROOFTOP (favoring rooftop over reception)
            (FLOOR_ROOFTOP, pygame.Rect(1250, 50, 1100, 900), None),      # ROOFTOP (double weight)
            (FLOOR_1F, pygame.Rect(120, 1780, 820, 420), "male"),         # men's bathroom
            (FLOOR_1F, pygame.Rect(2260, 2020, 780, 300), "female"),      # women's bathroom
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

        from settings import NPC_SIZE
        blocked_ids = {
            "npc_noah_carter",
            "npc_gordon",
            "npc_director",
            "npc_oscar",
            "npc_oscar_obs1",
            "npc_oscar_obs2",
            "npc_oscar_obs3",
            "npc_oscar_obs4",
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

        def choose_area(npc, start_idx):
            for offset in range(len(scatter_areas)):
                floor_id, area, allowed_gender = scatter_areas[(start_idx + offset) % len(scatter_areas)]
                if allowed_gender is None or getattr(npc, "gender", "unspecified") == allowed_gender:
                    return floor_id, area
            floor_id, area, _ = scatter_areas[start_idx % len(scatter_areas)]
            return floor_id, area

        for idx, npc in enumerate(sorted(candidates, key=lambda n: n.id)):
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
                npc.rect.center = inner.center

            npc.current_floor = floor_id
            npc.current_zone = -1
            occupied_by_floor[floor_id].append(npc.rect.copy())
            npc.bound_rect = None
            npc.ai_enabled = True
            npc.stop_at_target = False
            npc.target_queue = []
            npc.target_pos = (
                random.randint(inner.left, inner.right),
                random.randint(inner.top, inner.bottom),
            ) if random.random() < 0.75 else None

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
            "npc_gordon":      ("Gordon Ramsay",  (200, 100, 50)),
            "npc_dylan":       ("Dylan Brooks",   (200, 50, 50)),
            "npc_marcus":      ("Marcus Rivera",  (50, 100, 200)),
            "npc_director":    ("Director Walsh", (150, 50, 200)),
            "npc_noah_carter": ("Noah Carter",    (50, 180, 120)),
        }
        for nid, (label, col) in key_npcs.items():
            npc = self.npc_manager.get_npc_by_id(nid)
            if npc:
                self.world_map.set_marker(
                    label, npc.current_floor, 
                    npc.rect.centerx, npc.rect.centery, col
                )

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

        # Also handle classroom-group NPCs that are seated in the cafeteria
        for group in self._classroom_groups:
            for npc in [group["teacher"]] + group["students"]:
                if getattr(npc, "ignore_schedule", False): continue
                if instant: continue
                room = floor1.get_room_at(npc.rect.centerx, npc.rect.centery)
                if room and room.id == "f1_cafeteria":
                    wps = self._cafeteria_exit_waypoints(npc)
                    npc.bound_rect = None
                    npc.target_pos = wps[0]
                    npc.target_queue = wps[1:]
                    npc.start_delay = count * 0.35
                    npc.stop_at_target = True
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
            self.phone.update_day_schedule(self.day_number)

            # Silence "Arrival" notification for Day 2+ as requested
            if self.day_number > 1 and self.current_phase == DayPhase.ARRIVAL:
                pass
            else:
                msg = f"📅 {day_name} — {phase_label}"
                self.ui.show_notification(msg, NOTIF_INFO)
            self.npc_manager.update_schedules(self.current_phase, self.school_map)
            self._spread_first_floor_npcs()
            if random.random() < 0.3:
                self._random_event()
        else:
            self.day_number += 1
            self.event_queue.load_day_schedule()
            self.phone.update_day_schedule(self.day_number)
            self.time_of_day_minutes = 7 * 60
            # Clear NPCs from cafeteria instantly before the new day
            self._move_npcs_out_of_cafeteria(instant=True)
            # Return classroom students to their seats
            self._move_class_groups("classroom")
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
            opponent = self.npc_manager.get_npc_by_id("npc_oscar")
            self.pingpong.start(self.player, opponent)
            self.state = GameState.PINGPONG

    # ── network ───────────────────────────────────────────────

    def _sync_network(self, dt: float = 0.016):
        if not self.network:
            return
        try:
            player_data = self.player.to_dict()
            player_data["floor"] = self.current_floor
            
            # Host: also send NPC data for synchronization
            if self.is_host:
                npcs = self.npc_manager.get_npcs_on_floor(self.current_floor)
                # Pack minimal NPC data to save bandwidth
                player_data["npc_sync"] = [
                    (n.id, n.rect.x, n.rect.y, n.direction.value, n.state) 
                    for n in npcs
                ]

            self.network.send_player_update(player_data)
            remote = self.network.get_remote_data()
            
            if remote and self.remote_player:
                # Apply floor-specific decay for remote player
                in_main_building = self.current_floor in (FLOOR_1F, FLOOR_2F)
                decay = 2 if in_main_building else 1
                
                self.remote_player.update_remote(remote, dt, trail_decay=decay)
                rf = remote.get("floor", 1)
                self.remote_player.current_floor = rf
                
                # Update WorldMap with remote player position
                if hasattr(self, "world_map"):
                    rname = "Lena" if self.player.character.value == "aiden" else "Aiden"
                    self.world_map.set_remote_player_pos(rf, self.remote_player.rect.centerx, self.remote_player.rect.centery, rname)

                # Update health/stamina if provided
                self.remote_player.health = remote.get("health", self.remote_player.health)

                # Client: Apply NPC updates from host
                if not self.is_host and "npc_sync" in remote:
                    for nid, nx, ny, ndir, nstate in remote["npc_sync"]:
                        npc = self.npc_manager.get_npc_by_id(nid)
                        if npc:
                            # Use simple LERP for NPCs too to keep them smooth
                            npc.rect.x += (nx - npc.rect.x) * 0.5
                            npc.rect.y += (ny - npc.rect.y) * 0.5
                            from settings import Direction
                            try:
                                npc.direction = Direction(ndir)
                            except ValueError:
                                pass
                            npc.state = nstate
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
            GameState.PINGPONG:          lambda: self.pingpong.draw(self.screen),
            GameState.TRADING:           lambda: (self._draw_world(), self.trade_system.draw(self.screen)),
            GameState.PAUSED:            lambda: (self._draw_world(), self.ui.draw_pause_menu(self.screen, getattr(self, 'pause_sel', 0), self.pause_options)),
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
                ),
            ),
            GameState.GAME_OVER:         lambda: self.ui.draw_game_over(self.screen, self.reputation.calculate_ending()),
            GameState.MAP:               lambda: self._draw_map(),
            GameState.DAY_OVER:           lambda: self._draw_day_over(),
            GameState.INTRO_CINEMATIC:    lambda: self._draw_cinematic(),
        }
        fn = draw_table.get(self.state, self._draw_world)
        fn()

        if getattr(self, "phone", None) and self.phone.is_visible and self.phone.shows_embedded_world_map():
            self._draw_phone_world_map_layer()

        # HUD overlay
        if (
            self.state in (GameState.PLAYING, GameState.COMBAT, GameState.DIALOGUE)
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
        # Notifications always on top (suppress during cinematic)
        if self.state != GameState.INTRO_CINEMATIC:
            self.ui.draw_notifications(self.screen)

        self.phone.set_hud_anchor(self.ui.phone_icon_rect)
        self.phone.draw()

        # ── Fullscreen overlays (drawn on top of everything) ──
        if self._day_transition_active:
            self._draw_day_transition()
        elif self._car_panel_active:
            self._draw_car_panel()

        pygame.display.flip()

    def _draw_world(self):
        """Render floor, NPCs, player."""
        # Smooth camera zoom
        target_zoom = 1.0 if self.current_floor == FLOOR_CAMPUS else 1.5
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
            floor.draw(target_surf, self.camera)

        # Draw parked car on campus
        if self.current_floor == FLOOR_CAMPUS:
            self._draw_parked_car(target_surf)
            self._draw_extra_parked_cars(target_surf)

        if floor and hasattr(floor, 'draw_foreground'):
            floor.draw_foreground(target_surf, self.camera, self.player)

        for npc in self.npc_manager.get_npcs_on_floor(self.current_floor):
            npc.draw(target_surf, self.camera)

        # Hide player sprite during drive_away phase (player is "inside" the car)
        if not (self._car_departure_active and self._car_depart_phase == "drive_away"):
            self.player.draw(target_surf, self.camera)
            if getattr(self, "remote_player", None):
                # Ghosting bug fix: only draw if on same floor
                if self.remote_player.current_floor == self.current_floor:
                    self.remote_player.draw(target_surf, self.camera)

        # ── Draw Top Layer (Trees, etc.) ──
        if floor and hasattr(floor, 'draw_top_layer'):
            floor.draw_top_layer(target_surf, self.camera)
            
        if self.camera.zoom != 1.0:
            # Scale up to screen size and blit
            scaled = pygame.transform.scale(target_surf, (SCREEN_WIDTH, SCREEN_HEIGHT))
            self.screen.blit(scaled, (0, 0))

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
        is_controller = bool(self.controller and self.controller.connected)
        key_hint = "[A]" if is_controller else "[SPACE]"
        text = f"Enter {building_name}?  {key_hint} yes  |  move away to cancel"
        fnt = pygame.font.SysFont("arial", 22, bold=True)
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
                self._add_noah_contact()
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
        self._add_noah_contact()
        self._noah_guide_active = False
        self._cinematic_stairs_unlocked = False
        self._cine_phase = "done"
        # Make sure Noah Carter is freed from the cinematic role
        noah = self.npc_manager.get_npc_by_id("npc_noah_carter")
        if noah:
            noah.ai_enabled = True
            noah.ignore_schedule = False
            floor2 = self.school_map.get_floor(FLOOR_2F)
            if floor2:
                corridor = floor2.rooms.get("f2_corridor")
                if corridor:
                    noah.bound_rect = corridor.rect.inflate(-40, -40)
                    # Place Noah in the corridor away from doors (center-left of corridor)
                    noah.rect.center = (corridor.rect.centerx - 200, corridor.rect.centery)
        # Ensure player is placed at entrance if still off-screen
        if not self._player_spawned or self.player.rect.x < 0:
            f0 = self.school_map.get_floor(0)
            if f0:
                entrance = f0.rooms.get("campus_entrance_roundabout")
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
            font_sm = pygame.font.SysFont("Arial", 20)
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
            self._draw_mission_box("Follow Noah Carter through the school.")

        # ── Guide phase: persistent mission box + waiting indicator ──
        if self._cine_phase == "guide":
            self._draw_mission_box("Follow Noah Carter through the school.")
            if self._noah_wait_for_player:
                font = pygame.font.SysFont("Arial", 22, bold=True)
                txt = font.render("Noah is waiting for you...", True, (255, 220, 100))
                self.screen.blit(txt, txt.get_rect(center=(SCREEN_WIDTH // 2, 150)))

        # ── Final dialogue ──
        if self._cine_phase == "final_dialogue" and self._noah_final_dlg_index < len(self._noah_final_dlg_lines):
            self._draw_cinematic_dialogue(
                self._noah_final_dlg_lines[self._noah_final_dlg_index], "Noah Carter")

        # ── Prompt to advance ──
        if self._cine_phase in ("dialogue", "final_dialogue"):
            font_hint = pygame.font.SysFont("Arial", 16)
            hint = font_hint.render("Press SPACE to continue", True, (160, 160, 160))
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
        font_skip = pygame.font.SysFont("Arial", 15, bold=True)
        skip_label = font_skip.render("Skip  >>>", True, (220, 220, 240))
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

        # Draw Noah Carter's avatar
        avatar_drawn = False
        if hasattr(self, "phone") and "npc_noah_carter" in self.phone.avatars:
            img = self.phone.avatars["npc_noah_carter"]
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
            f_init = pygame.font.SysFont("arial", 48, bold=True)
            txt = f_init.render(initial, True, UI_ACCENT)
            self.screen.blit(txt, txt.get_rect(center=(av_cx, av_cy)))

        # Speaker name (same style as dialogue.py)
        font_name = pygame.font.SysFont("arial", 22, bold=True)
        self.screen.blit(font_name.render(speaker, True, UI_ACCENT),
                         (box.x + 18, box.y + 12))

        # Dialogue text (with word wrap, same as dialogue.py)
        font_text = pygame.font.SysFont("arial", 20)
        self._draw_cinematic_wrapped_text(text, font_text, UI_TEXT,
                                           box.x + 18, box.y + 42, box.width - 36)

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
        """Draw a mission objective text box at the top of the screen."""
        box_w, box_h = 500, 60
        bx = (SCREEN_WIDTH - box_w) // 2
        by = 80

        surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        surf.fill((10, 30, 50, 220))
        pygame.draw.rect(surf, (100, 180, 255, 180), surf.get_rect(), 2, border_radius=10)
        self.screen.blit(surf, (bx, by))

        icon_font = pygame.font.SysFont("Arial", 16, bold=True)
        icon = icon_font.render("MISSION", True, (100, 180, 255))
        self.screen.blit(icon, (bx + 15, by + 8))

        txt_font = pygame.font.SysFont("Arial", 20)
        txt = txt_font.render(mission_text, True, WHITE)
        self.screen.blit(txt, (bx + 15, by + 30))

    def _draw_day_over(self):
        """Draw the end-of-day overlay with a 'Next Day' button."""
        self._draw_world() # Keep game visible in background
        
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        title_font = pygame.font.SysFont("Arial", 64, bold=True)
        btn_font = pygame.font.SysFont("Arial", 32)
        
        # Title
        text = title_font.render("School Day Is Over!", True, WHITE)
        rect = text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50))
        self.screen.blit(text, rect)
        
        # Button
        btn_rect = pygame.Rect(0, 0, 300, 60)
        btn_rect.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 50)
        
        mouse_pos = pygame.mouse.get_pos()
        controller_connected = self.controller and self.controller.connected
        hover = btn_rect.collidepoint(mouse_pos)
        color = (100, 150, 255) if (hover or controller_connected) else (60, 100, 200)
        
        pygame.draw.rect(self.screen, color, btn_rect, border_radius=10)
        outline_col = (255, 220, 50) if controller_connected else WHITE
        pygame.draw.rect(self.screen, outline_col, btn_rect, 3, border_radius=10)
        
        label = "Go to next day"
        if controller_connected:
            label = "\u24B6  Go to next day"  # circled A symbol
        btn_text = btn_font.render(label, True, WHITE)
        self.screen.blit(btn_text, btn_text.get_rect(center=btn_rect.center))
        
        # Handle button click
        if pygame.mouse.get_pressed()[0] and hover:
            self._begin_day_transition()

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
        self._class_phase = "arrival"
        self._advance_phase() # Triggers notifications
        
        # Re-init NPCs for the new day positions
        self.npc_manager.update_schedules(self.current_phase, self.school_map)
        self._spread_first_floor_npcs()
        
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
        """Create a school bus sprite surface (300x135, transparent bg)."""
        w, h = 300, 135
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        bus_yellow = (250, 160, 30)
        # Body
        pygame.draw.rect(surf, bus_yellow, (0, 30, w, 75), border_radius=9)
        # Roof (higher than car)
        pygame.draw.rect(surf, bus_yellow, (0, 0, w, 38), border_radius=6)
        # Windows
        pygame.draw.rect(surf, (80, 130, 180), (15, 8, 45, 27), border_radius=3)
        pygame.draw.rect(surf, (80, 130, 180), (75, 8, 45, 27), border_radius=3)
        pygame.draw.rect(surf, (80, 130, 180), (135, 8, 45, 27), border_radius=3)
        pygame.draw.rect(surf, (80, 130, 180), (195, 8, 45, 27), border_radius=3)
        # Windshield (right side)
        pygame.draw.rect(surf, (80, 130, 180), (255, 8, 30, 27), border_radius=3)
        # Wheels
        pygame.draw.circle(surf, (25, 25, 25), (60, 105), 21)
        pygame.draw.circle(surf, (25, 25, 25), (w - 60, 105), 21)
        # Headlights (right side = front)
        pygame.draw.rect(surf, (255, 220, 80), (w - 9, 68, 9, 18), border_radius=3)
        # Tail lights (left side)
        pygame.draw.rect(surf, (220, 40, 40), (0, 68, 9, 18), border_radius=3)
        # Black stripe
        pygame.draw.rect(surf, (20, 20, 20), (0, 60, w, 6))
        return surf

    def _draw_parked_car(self, surface=None):
        surface = surface or self.screen
        """Draw the parked car in the campus parking lot (facing left)."""
        car_surf = self._build_car_surface()
        # Flip horizontally so the car faces left
        car_surf = pygame.transform.flip(car_surf, True, False)

        if self._car_departure_active and self._car_depart_phase == "drive_away":
            sx, sy = self.camera.apply_pos(self._car_depart_wx, self._car_depart_wy)
            rect = car_surf.get_rect(center=(sx, sy))
            surface.blit(car_surf, rect)
        else:
            cr = self.camera.apply_rect(self._parked_car_rect)
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
        """Draw additional cars parked in the lot."""
        if self.current_floor != 0:
            return
        for rect, color, angle in self._extra_parked_cars:
            car_surf = self._build_regular_car_surface(color)
            if angle == 180:
                car_surf = pygame.transform.flip(car_surf, True, False)
            elif angle != 0:
                car_surf = pygame.transform.rotate(car_surf, angle)
            cr = self.camera.apply_rect(rect)
            surface.blit(car_surf, (cr.x, cr.y - 10))

    def _draw_car_panel(self):
        """Draw the 'End the day?' confirmation panel overlay."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        # Panel box
        box_w, box_h = 500, 200
        bx = (SCREEN_WIDTH - box_w) // 2
        by = (SCREEN_HEIGHT - box_h) // 2
        pygame.draw.rect(self.screen, (30, 30, 45), (bx, by, box_w, box_h), border_radius=16)
        pygame.draw.rect(self.screen, WHITE, (bx, by, box_w, box_h), 3, border_radius=16)

        # Title
        title_font = pygame.font.SysFont("Arial", 28, bold=True)
        title = title_font.render("End the day and go home?", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, by + 60)))

        # Draw buttons
        btn_y = by + 120
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

        font = pygame.font.SysFont("Arial", 20, bold=True)
        acc_text = font.render("\u24B6 Accept" if controller_connected and sel == "accept" else "Accept", True, WHITE)
        can_text = font.render("\u24B7 Cancel" if controller_connected and sel == "cancel" else "Cancel", True, WHITE)

        self.screen.blit(acc_text, acc_text.get_rect(center=accept_rect.center))
        self.screen.blit(can_text, can_text.get_rect(center=cancel_rect.center))

        # Handle mouse clicks
        if pygame.mouse.get_pressed()[0] and getattr(self, "_car_panel_input_delay", 0) <= 0:
            if hover_accept:
                self._car_panel_active = False
                self._start_car_departure()
            elif hover_cancel:
                self._car_panel_active = False
                self._car_panel_cooldown = 1.0

    def _draw_day_transition(self):
        """Draw fullscreen black screen with 'Day X' text."""
        self.screen.fill((0, 0, 0))

        # "Day X" title
        day_font = pygame.font.SysFont("Arial", 80, bold=True)
        day_text = day_font.render(f"Day {self._day_transition_target_day}", True, WHITE)
        self.screen.blit(day_text, day_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 20)))

        # Subtitle
        sub_font = pygame.font.SysFont("Arial", 28)
        sub_text = sub_font.render("A new day begins...", True, (160, 160, 180))
        self.screen.blit(sub_text, sub_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 50)))
        # Subtitle
        sub_font = pygame.font.SysFont("Arial", 28)
        sub_text = sub_font.render("A new day begins...", True, (160, 160, 180))
        self.screen.blit(sub_text, sub_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 50)))
