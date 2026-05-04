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
    FLOOR_1F, FLOOR_2F, FLOOR_CAMPUS, FLOOR_SIZES, ZONE_TO_FLOOR,
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
                 is_host: bool = True):
        self.screen      = screen
        self.clock       = pygame.time.Clock()
        self.character   = character
        self.multiplayer = multiplayer
        self.is_host     = is_host

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
        self._time_scale: float = 2.0   # minutes advanced per real-time second
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
        self._car_y: float = float(SCREEN_HEIGHT - 120)
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

        # ── init subsystems (order matters) ──
        self._init_map()
        self._init_players()
        self._init_npcs()
        self._init_systems()
        self._init_ui()
        self._init_controller()

        # Network (optional)
        self.network = None
        if self.multiplayer:
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
        if self.character == Character.AIDEN:
            self.player = Aiden(cx, cy)
        else:
            self.player = Lena(cx, cy)

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
        
        # Position Oscar and observers inside the Ping Pong Courts on the campus floor
        oscar = self.npc_manager.get_npc_by_id("npc_oscar")
        if oscar:
            oscar.current_floor = FLOOR_CAMPUS
            oscar.ai_enabled = True
            oscar.bound_rect = pygame.Rect(3100 + 30, 2100 + 30, 780 - 60 - NPC_SIZE, 750 - 60 - NPC_SIZE)
            # Place Oscar near the centre of the court
            oscar.rect.centerx = 3490
            oscar.rect.centery = 2375
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
                obs.current_floor = FLOOR_CAMPUS
                obs.ai_enabled = True
                obs.bound_rect = pygame.Rect(3100 + 30, 2100 + 30, 780 - 60 - NPC_SIZE, 750 - 60 - NPC_SIZE)
                obs.name = "Club Member"
                obs.show_name = True
                angle = (i / len(obs_ids)) * (2 * math.pi)
                obs.rect.centerx = oscar.rect.centerx + int(math.cos(angle) * radius)
                obs.rect.centery = oscar.rect.centery + int(math.sin(angle) * radius)

        # Create additional random NPCs across all floors
        random_names = [
            ("Alex", "male"), ("Jordan", "male"), ("Taylor", "female"), ("Morgan", "female"),
            ("Casey", "female"), ("Riley", "male"), ("Sam", "male"), ("Jamie", "female"),
            ("Drew", "male"), ("Avery", "female"), ("Cameron", "male"), ("Dakota", "female"),
            ("Quinn", "female"), ("Skyler", "male"), ("Harper", "female"), ("Finley", "male")
        ]
        groups = list(SocialGroup)
        for floor_id, floor in self.school_map.floors.items():
            rooms = list(floor.rooms.values())
            # Increase population on 1F (35) and 2F (25) for more natural room entry/exit
            limit = 35 if floor_id == FLOOR_1F else (25 if floor_id == FLOOR_2F else 10)
            
            # Exclude cafeteria from random spawns so only Gordon starts there
            valid_rooms = [r for r in rooms if r.id != "f1_cafeteria"]
            if not valid_rooms: valid_rooms = rooms
            
            for i in range(limit):
                room = random.choice(valid_rooms)
                nid = f"npc_rnd_{floor_id}_{i}"
                npc_name, gender = random.choice(random_names)
                npc_group = random.choice(groups)
                npc = NPC(nid, npc_name, npc_group, "Walking", "Walking", gender=gender)
                npc.current_floor = floor_id
                npc.ai_enabled = True
                npc.speed_multiplier = 2.5 # Make them move faster
                for _ in range(10):
                    if room.rect.width > 60 and room.rect.height > 60:
                        npc.rect.x = room.rect.x + random.randint(30, room.rect.width - 60)
                        npc.rect.y = room.rect.y + random.randint(30, room.rect.height - 60)
                    else:
                        npc.rect.x = room.rect.x
                        npc.rect.y = room.rect.y
                    if not any(npc.rect.colliderect(w) for w in floor.walls):
                        break
                self.npc_manager.npcs[nid] = npc
                self.npc_manager.relationships.add_node(nid)

        # Dedicated bathroom occupants to reinforce gender-specific presence
        floor1 = self.school_map.get_floor(FLOOR_1F)
        if floor1:
            men_room = floor1.rooms.get("f1_men_bath")
            women_room = floor1.rooms.get("f1_women_bath")
            if men_room:
                male_attendant = NPC(
                    "npc_bath_m_attendant", "Leo",
                    SocialGroup.OUTSIDERS,
                    "Friendly classmate", "Just hanging out",
                    gender="male",
                )
                male_attendant.current_floor = FLOOR_1F
                male_attendant.rect.center = men_room.rect.center
                male_attendant.bound_rect = men_room.rect.inflate(-160, -160)
                male_attendant.ignore_schedule = True
                self.npc_manager.npcs[male_attendant.id] = male_attendant
                self.npc_manager.relationships.add_node(male_attendant.id)
            if women_room:
                female_attendant = NPC(
                    "npc_bath_f_attendant", "Lia",
                    SocialGroup.OUTSIDERS,
                    "Friendly classmate", "Just hanging out",
                    gender="female",
                )
                female_attendant.current_floor = FLOOR_1F
                female_attendant.rect.center = women_room.rect.center
                female_attendant.bound_rect = women_room.rect.inflate(-160, -160)
                female_attendant.ignore_schedule = True
                self.npc_manager.npcs[female_attendant.id] = female_attendant
                self.npc_manager.relationships.add_node(female_attendant.id)

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
            gordon.bound_rect = pygame.Rect(
                caf.rect.right  - NPC_SIZE - 80,
                caf.rect.bottom - NPC_SIZE - 80,
                60, 60,
            )
            gordon.ignore_schedule = True  # He belongs in the kitchen
            gordon.ai_enabled = False
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
                    if getattr(self.world_map, 'teleport_requested', False):
                        self.world_map.teleport_requested = False
                        tfloor = self.world_map.teleport_floor
                        tx, ty = self.world_map.teleport_pos
                        if not self._try_teleport_to(tfloor, int(tx), int(ty)):
                            continue
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

        if self.state == GameState.INTRO_CINEMATIC:
            # Block map/inventory/skill tree during cinematic
            pass
        else:
            # Back/View = Map
            if controller.is_map_pressed():
                self._toggle_map()
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
                self._start_next_day()

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
            self.world_map.current_tab = self.current_floor
            self.world_map._centre_on_floor(self.current_floor)
            self.world_map._refresh_room_selection(reset_index=True)
        elif self.state == GameState.MAP:
            self.state = self.previous_state

    def _handle_controller_playing(self, controller):
        """Handle controller input during PLAYING state."""
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
            if getattr(self.world_map, 'teleport_requested', False):
                self.world_map.teleport_requested = False
                tfloor = self.world_map.teleport_floor
                tx, ty = self.world_map.teleport_pos
                self._try_teleport_to(tfloor, int(tx), int(ty))

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
            if self.state == GameState.PLAYING:
                self.previous_state = self.state
                self.state = GameState.MAP
                # Sync map viewer to current floor
                self.world_map.current_tab = self.current_floor
                self.world_map._centre_on_floor(self.current_floor)
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
        # If SPACE (KEY_INTERACT) and an NPC is nearby, open dialogue;
        # otherwise treat SPACE (and dash aliases) as dash.
        if event.key == KEY_INTERACT:
            npc = self._nearest_npc(NPC_INTERACTION_RANGE)
            if npc:
                self._try_interact()
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

    def _check_floor_transition(self):
        """Portal-type transitions (legacy — kept for future use)."""
        if self._transition_cooldown > 0:
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
        if room and room.id == "f1_cafeteria":
            if not self._is_cafeteria_open():
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
        self.phone.update(dt)
        # Always tick UI (notifications)
        self.ui.update(dt)
        if self._bathroom_block_timer > 0:
            self._bathroom_block_timer = max(0.0, self._bathroom_block_timer - dt)
            if self._bathroom_block_timer == 0.0:
                self._bathroom_blocked_room = None

        if not hasattr(self, '_last_known_level'):
            self._last_known_level = self.player.level
        if self.player.level > self._last_known_level:
            self._last_known_level = self.player.level
            if hasattr(self.ui, 'trigger_level_up'):
                self.ui.trigger_level_up()

        if self.state == GameState.INTRO_CINEMATIC:
            self._update_cinematic(dt)

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
            elif self._cine_phase == "guide":
                # Allow player movement during the guide phase
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
                # Do NOT check seamless stairs during cinematic —
                # floor switches are controlled by the route tags
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
            self._sync_network()

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
            
        previous_rect = self.player.rect.copy()
        
        # Add locked doors to collision walls
        if floor:
            for door in floor.doors:
                if door.locked:
                    walls.append(door.rect)
                    
        # Apply floor-specific speed boost (50% faster in main building) and faster trail decay
        in_main_building = self.current_floor in (FLOOR_1F, FLOOR_2F)
        speed_mult = 1.5 if in_main_building else 1.0
        decay = 2 if in_main_building else 1
        
        # We pass the original dt to the player so they don't speed up during fast-forward,
        # but we use speed_mult for the floor-based boost.
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
        
        self.npc_manager.update_on_floor(
            current_dt, self.current_floor, floor, npc_walls,
            classrooms_restricted=is_class_session,
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
        """Make random NPCs on Floor 1 head to the cafeteria and sit at tables."""
        self._caf_seat_pool = []  # reset pool so seats are freshly shuffled
        floor1 = self.school_map.get_floor(FLOOR_1F)
        if not floor1: return
        npcs = self.npc_manager.get_npcs_on_floor(FLOOR_1F)
        caf_room = floor1.rooms.get("f1_cafeteria")
        if not caf_room: return

        # Cafeteria layout: tables at y=720..1020. Door at (2210, 780).
        # Route NPCs BELOW the tables (y~1050) before reaching seats.
        below_tables_y = caf_room.rect.bottom - 40  # ~1060, below all table bottoms
        
        count = 0
        for npc in npcs:
            if npc.id.startswith("npc_rnd_") and not getattr(npc, "ignore_schedule", False):
                seat = self._get_cafeteria_seat()
                # Route: main hall → door → below tables corridor → seat
                npc.target_pos = (1600, 800 + random.randint(-50, 50))
                npc.target_queue = [
                    (2210, 780 + random.randint(-15, 15)),         # through door
                    (2210 + random.randint(20, 60), below_tables_y),  # go below tables
                    (seat[0], below_tables_y),                     # align x with seat
                    seat,                                          # final seat
                ]
                npc.start_delay = count * 0.6
                npc.stop_at_target = True
                npc.ai_enabled = True
                count += 1

    def _move_npcs_out_of_cafeteria(self, instant: bool = False):
        """Clear the cafeteria — NPCs exit through the door then wander the main hall."""
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
                    # Instantly teleport out of cafeteria (used for day reset)
                    npc.rect.centerx = hall_x
                    npc.rect.centery = hall_y
                    npc.target_queue = []
                    npc.target_pos = None
                    npc.ai_enabled = True
                    npc.stop_at_target = False
                else:
                    # 1) Go to the door first
                    door_x = 2150 - 30
                    door_y = 780 + random.randint(-20, 20)
                    # 2) Then disperse into main hall
                    npc.target_pos = (door_x, door_y)
                    npc.target_queue = [(hall_x, hall_y)]
                    npc.start_delay = count * 0.4
                    npc.stop_at_target = False  # resume wandering after
                    npc.ai_enabled = True
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
            if self.day_number > 1 and self.current_phase == DayPhase.ARRIVAL:
                msg = f"📅 Day {self.day_number}"
            else:
                msg = f"📅 Day {self.day_number} — {phase_label}"
                
            self.ui.show_notification(msg, NOTIF_INFO)
            self.npc_manager.update_schedules(self.current_phase)
            if random.random() < 0.3:
                self._random_event()
        else:
            self.day_number += 1
            self.event_queue.load_day_schedule()
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

    def _sync_network(self):
        if not self.network:
            return
        try:
            self.network.send_player_update(self.player.to_dict())
            remote = self.network.get_remote_data()
            if remote:
                pass  # TODO: render remote player sprite
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

        # HUD overlay
        if self.state in (GameState.PLAYING, GameState.COMBAT, GameState.DIALOGUE):
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
                             )
            # Phone HUD icon with unread badge (delegated to Phone)
            self.phone.draw_hud_icon(
                self.screen,
                self.ui.phone_icon_rect,
                unread=self.phone.get_unread_messages_count(),
            )

        # Notifications always on top
        self.ui.draw_notifications(self.screen)

        self.phone.draw()

        pygame.display.flip()

    def _draw_world(self):
        """Render floor, NPCs, player."""
        floor = self.school_map.get_floor(self.current_floor)
        if floor:
            floor.draw(self.screen, self.camera)
        for npc in self.npc_manager.get_npcs_on_floor(self.current_floor):
            npc.draw(self.screen, self.camera)
        self.player.draw(self.screen, self.camera)

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
        controller_connected = self.controller.connected if self.controller else False
        self.world_map.draw(self.screen, controller_connected)
    # ──────────────────────────────────────────────────────────
    #  INTRO CINEMATIC
    # ──────────────────────────────────────────────────────────

    def _update_cinematic(self, dt: float):
        """Advance the intro-cinematic state machine."""
        # Do NOT advance in-game time during the cinematic
        phase = self._cine_phase

        self._clear_noah_area()

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
                car_screen_cx = int(self._car_x) + 160
                car_screen_cy = int(self._car_y) + 70
                # Convert screen → world
                wx = int(car_screen_cx + self.camera.offset.x)
                wy = int(car_screen_cy + self.camera.offset.y)
                self.player.rect.center = (wx, wy)
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
            self._cine_mission_timer -= dt
            if self._cine_mission_timer <= 0:
                self._cine_phase = "guide"
                self._start_noah_guide()

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

        elif self._cine_phase == "final_dialogue":
            self._noah_final_dlg_index += 1
            if self._noah_final_dlg_index >= len(self._noah_final_dlg_lines):
                # End cinematic → PLAYING
                self.state = GameState.PLAYING
                self._noah_guide_active = False
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
        self._noah_guide_active = False
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
        # Ensure player is placed at entrance if still off-screen
        if not self._player_spawned or self.player.rect.x < 0:
            f0 = self.school_map.get_floor(0)
            if f0:
                entrance = f0.rooms.get("campus_entrance_roundabout")
                if entrance:
                    self.player.rect.center = entrance.rect.center
                else:
                    self.player.rect.center = (2000, 2650)
            else:
                self.player.rect.center = (2000, 2650)
            self._player_spawned = True
        self.camera.update(self.player)

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
            ("campus", (2000, 2000)),      # Towards building entrance
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
                return
            self._noah_wait_for_player = False

        tag, pos = self._noah_route[self._noah_route_idx]

        if tag == "portal_1f":
            # Teleport Noah to 1F reception
            noah.current_floor = FLOOR_1F
            noah.rect.center = (1600, 2200)
            self._go_to_floor(FLOOR_1F, 1600, 2200)
            self._noah_route_idx += 1
            return

        if tag == "switch_2f":
            noah.current_floor = FLOOR_2F
            noah.rect.center = (2420, 1860)
            self._go_to_floor(FLOOR_2F, 2420, 1860)
            self._noah_route_idx += 1
            return

        if tag == "final":
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
            # Update facing direction
            if abs(dx_r) > abs(dy_r):
                noah.direction = Direction.RIGHT if dx_r > 0 else Direction.LEFT
            else:
                noah.direction = Direction.DOWN if dy_r > 0 else Direction.UP
        else:
            noah.rect.center = pos
            self._noah_route_idx += 1

    def _draw_cinematic(self):
        """Render the intro cinematic overlay."""
        if self._player_spawned:
            self._draw_world()
        else:
            # Dark campus background
            self.screen.fill((25, 35, 25))
            # Draw entrance area label
            font_sm = pygame.font.SysFont("Arial", 20)
            lbl = font_sm.render("Ravenside High — Entrance", True, (180, 180, 180))
            self.screen.blit(lbl, lbl.get_rect(center=(SCREEN_WIDTH // 2, 40)))

        # ── Car ──
        if self._cine_phase in ("car", "exit"):
            car_w, car_h = 200, 70
            cx = int(self._car_x)
            cy = int(self._car_y)
            # Car body
            pygame.draw.rect(self.screen, (40, 40, 60), (cx, cy, car_w, car_h), border_radius=12)
            # Roof
            pygame.draw.rect(self.screen, (30, 30, 50), (cx + 40, cy - 25, 120, 30), border_radius=8)
            # Windows
            pygame.draw.rect(self.screen, (120, 160, 200), (cx + 50, cy - 20, 45, 20), border_radius=4)
            pygame.draw.rect(self.screen, (120, 160, 200), (cx + 105, cy - 20, 45, 20), border_radius=4)
            # Wheels
            pygame.draw.circle(self.screen, (20, 20, 20), (cx + 45, cy + car_h), 16)
            pygame.draw.circle(self.screen, (20, 20, 20), (cx + car_w - 45, cy + car_h), 16)
            pygame.draw.circle(self.screen, (60, 60, 60), (cx + 45, cy + car_h), 8)
            pygame.draw.circle(self.screen, (60, 60, 60), (cx + car_w - 45, cy + car_h), 8)
            # Headlights
            pygame.draw.circle(self.screen, (255, 230, 120), (cx + 5, cy + 20), 8)
            pygame.draw.circle(self.screen, (255, 50, 50), (cx + car_w - 5, cy + 20), 8)

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
        """Large dialogue box with NPC portrait circle."""
        box_w, box_h = 700, 180
        bx = (SCREEN_WIDTH - box_w) // 2
        by = SCREEN_HEIGHT - box_h - 60

        # Semi-transparent background
        surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        surf.fill((20, 20, 30, 230))
        pygame.draw.rect(surf, (255, 255, 255, 80), surf.get_rect(), 2, border_radius=14)
        self.screen.blit(surf, (bx, by))

        # Portrait circle (white circle with initial)
        portrait_cx = bx + 60
        portrait_cy = by + box_h // 2
        pygame.draw.circle(self.screen, (255, 255, 255), (portrait_cx, portrait_cy), 40, 3)
        pygame.draw.circle(self.screen, (50, 80, 120), (portrait_cx, portrait_cy), 37)
        init_font = pygame.font.SysFont("Arial", 30, bold=True)
        init_txt = init_font.render(speaker[0], True, WHITE)
        self.screen.blit(init_txt, init_txt.get_rect(center=(portrait_cx, portrait_cy)))

        # Speaker name
        name_font = pygame.font.SysFont("Arial", 18, bold=True)
        name_surf = name_font.render(speaker, True, (200, 220, 255))
        self.screen.blit(name_surf, (bx + 110, by + 20))

        # Dialogue text (word-wrapped)
        dlg_font = pygame.font.SysFont("Arial", 20)
        max_w = box_w - 130
        words = text.split(" ")
        lines = []
        current = ""
        for w in words:
            test = (current + " " + w).strip()
            if dlg_font.size(test)[0] <= max_w:
                current = test
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        for i, line in enumerate(lines):
            dlg_surf = dlg_font.render(line, True, WHITE)
            self.screen.blit(dlg_surf, (bx + 110, by + 50 + i * 26))

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
            self._start_next_day()

    def _start_next_day(self):
        """Reset the day, increment counter, and respawn player while keeping stats."""
        self.day_number += 1
        self.time_of_day_minutes = 7 * 60 # 7:00 AM
        self._last_time_minutes = 7 * 60
        
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
        self.npc_manager.update_schedules(self.current_phase)
        
        # Close cafeteria
        floor1 = self.school_map.get_floor(FLOOR_1F)
        if floor1:
            for door in floor1.doors:
                if getattr(door, "id", "") == "door_cafeteria":
                    door.locked = True
        
        self.state = GameState.PLAYING
