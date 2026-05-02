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
    FLOOR_1F, FLOOR_CAMPUS, FLOOR_SIZES, ZONE_TO_FLOOR,
    PLAYER_SIZE, NPC_INTERACTION_RANGE, ATTACK_RANGE,
    GameState, Character, DayPhase, ItemCategory, Ending,
    NOTIF_SUCCESS, NOTIF_WARNING, NOTIF_ERROR, NOTIF_INFO,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
    KEY_INTERACT, KEY_USE, KEY_INVENTORY, KEY_SKILL_TREE,
    KEY_HELP, KEY_PAUSE, KEY_MAP,
    KEY_LIGHT_ATTACK, KEY_HEAVY_ATTACK, KEY_BLOCK, KEY_DASH, KEY_DASH_ALT, KEY_DASH_ALT2,
    KEY_HACK,
    MOTIVATIONAL_MESSAGES,
)
from src.map        import SchoolMap
from src.player     import Aiden, Lena
from src.npc        import NPCManager
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
from src.controller import get_controller, init_controller, update_controller


class Game:
    """Central game controller.

    Parameters
    ----------
    screen      : pygame display surface
    character   : which character the local player controls
    multiplayer : co-op mode enabled?
    is_host     : True → server (Aiden), False → client (Lena)
    """

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
        self.state          = GameState.PLAYING
        self.previous_state = GameState.PLAYING
        self.active_wallet_item = None
        self.wallet_focus_item = None
        self.pause_sel      = 0

        # Transition cooldown (prevents rapid re-triggering)
        self._transition_cooldown: float = 0.0

        # Day-cycle
        self.day_number     = 1
        self.event_queue    = EventQueue()
        self.day_timer: float = 0.0
        self.current_phase  = DayPhase.ARRIVAL
        self.phase_duration: float = 0.0

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
        # Spawn in the Entrance Roundabout (Campus)
        cx, cy = 2000, 2700
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
        
        from src.npc import NPC
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
        random_names = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Sam", "Jamie", "Drew", "Avery", "Cameron", "Dakota", "Quinn", "Skyler", "Harper", "Finley"]
        groups = list(SocialGroup)
        for floor_id, floor in self.school_map.floors.items():
            rooms = list(floor.rooms.values())
            for i in range(10):  # 10 random NPCs per floor
                if not rooms: continue
                room = random.choice(rooms)
                nid = f"npc_rnd_{floor_id}_{i}"
                npc_name = random.choice(random_names)
                npc_group = random.choice(groups)
                npc = NPC(nid, npc_name, npc_group, "Walking", "Walking")
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
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            update_controller(dt)  # Update controller input
            self._handle_controller_input()  # Process controller buttons
            self._handle_events()
            self._update(dt)
            self._draw()
        # Cleanup
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
            # MAP state delegates to WorldMap
            if self.state == GameState.MAP:
                close = self.world_map.handle_event(event)
                if close:
                    self.state = self.previous_state
                    if getattr(self.world_map, 'teleport_requested', False):
                        self.world_map.teleport_requested = False
                        tfloor = self.world_map.teleport_floor
                        tx, ty = self.world_map.teleport_pos
                        self._go_to_floor(tfloor, int(tx), int(ty))
                continue
            if event.type == pygame.KEYDOWN:
                self._on_key_down(event)
            elif event.type == pygame.KEYUP:
                pass  # movement uses get_pressed()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if self.state == GameState.TRADING:
                    self.trade_system.handle_click(event.pos)
                elif self.state == GameState.PLAYING:
                    if self.ui.wallet_icon_rect.collidepoint(event.pos):
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
        # Start = Pause
        if controller.is_pause_pressed():
            self._toggle_pause()
            return

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
        if self.state == GameState.PLAYING:
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

    def _toggle_pause(self):
        """Toggle pause state."""
        if self.state == GameState.PAUSED:
            self.state = GameState.PLAYING
        elif self.state == GameState.PLAYING:
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
        # A = Interact or Dash
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
        if menu_dir == -1:
            self.pause_sel = (getattr(self, 'pause_sel', 0) - 1) % 3
        elif menu_dir == 1:
            self.pause_sel = (getattr(self, 'pause_sel', 0) + 1) % 3

        if controller.is_confirm_pressed():
            sel = getattr(self, 'pause_sel', 0)
            if sel == 0:
                self.state = GameState.PLAYING
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
                self.state = GameState.PLAYING
            else:
                self.running = False

        if controller.is_cancel_pressed():
            self.state = GameState.PLAYING

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
                self._go_to_floor(tfloor, int(tx), int(ty))

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
                self.state = GameState.PLAYING
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
        

    def _keys_paused(self, event: pygame.event.Event):
        if event.key in (pygame.K_UP, pygame.K_w):
            self.pause_sel = (getattr(self, 'pause_sel', 0) - 1) % 3
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.pause_sel = (getattr(self, 'pause_sel', 0) + 1) % 3
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            sel = getattr(self, 'pause_sel', 0)
            if sel == 0:
                self.state = GameState.PLAYING
            elif sel == 1:
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
                self.state = GameState.PLAYING
            else:
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
        # Always tick UI (notifications)
        self.ui.update(dt)

        if not hasattr(self, '_last_known_level'):
            self._last_known_level = self.player.level
        if self.player.level > self._last_known_level:
            self._last_known_level = self.player.level
            if hasattr(self.ui, 'trigger_level_up'):
                self.ui.trigger_level_up()

        if self.state == GameState.PLAYING:
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
            if getattr(self.pingpong, 'finished', False):
                self.pingpong.finished = False
                self.pingpong.reset()
                self.state = GameState.PLAYING

        elif self.state == GameState.HACKING:
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

        # Network sync
        if self.multiplayer and self.network:
            self._sync_network()

    def _update_playing(self, dt: float):
        # Transition cooldown
        if self._transition_cooldown > 0:
            self._transition_cooldown -= dt

        # Movement
        keys  = pygame.key.get_pressed()
        floor = self.school_map.get_floor(self.current_floor)
        walls = list(floor.walls) if floor else []
        
        npcs_on_floor = self.npc_manager.get_npcs_on_floor(self.current_floor)
        for npc in npcs_on_floor:
            walls.append(npc.rect)
            
        self.player.update(keys, walls, dt)

        # Seamless staircase detection (silent floor switch)
        self._check_seamless_stairs()

        # Portal-type transitions (campus entrance)
        self._check_floor_transition()

        # Camera
        self.camera.update(self.player)

        # NPC AI — only update NPCs on current floor
        npc_walls = list(floor.walls) if floor else []
        npc_walls.append(self.player.rect)
        self.npc_manager.update_on_floor(dt, self.current_floor, floor, npc_walls)

        # Day timer
        self.day_timer += dt
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

        # Check game-over
        if not self.player.is_alive():
            self.state = GameState.GAME_OVER

    # ── day cycle ─────────────────────────────────────────────

    def _advance_phase(self):
        ev = self.event_queue.next_event()
        if ev:
            self.current_phase  = ev["phase"]
            self.phase_duration = ev["duration"]
            self.day_timer      = 0.0
            phase_label = self.current_phase.value.replace("_", " ").title()
            self.ui.show_notification(
                f"📅 Day {self.day_number} — {phase_label}", NOTIF_INFO,
            )
            self.npc_manager.update_schedules(self.current_phase)
            if random.random() < 0.3:
                self._random_event()
        else:
            self.day_number += 1
            self.event_queue.load_day_schedule()
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
            GameState.PAUSED:            lambda: (self._draw_world(), self.ui.draw_pause_menu(self.screen, getattr(self, 'pause_sel', 0))),
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
        }
        fn = draw_table.get(self.state, self._draw_world)
        fn()

        # HUD overlay
        if self.state in (GameState.PLAYING, GameState.COMBAT, GameState.DIALOGUE):
            floor = self.school_map.get_floor(self.current_floor)
            room = floor.get_room_at(
                self.player.rect.centerx, self.player.rect.centery
            ) if floor else None
            self.ui.draw_hud(self.screen, self.player,
                             self.current_phase, self.day_number,
                             floor, room, self.reputation)

        # Notifications always on top
        self.ui.draw_notifications(self.screen)

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
