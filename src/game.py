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
import pygame
from collections import deque

from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS,
    BLACK, WHITE,
    FLOOR_1F, FLOOR_SIZES, ZONE_TO_FLOOR,
    PLAYER_SIZE, NPC_INTERACTION_RANGE, ATTACK_RANGE,
    GameState, Character, DayPhase, ItemCategory, Ending,
    NOTIF_SUCCESS, NOTIF_WARNING, NOTIF_ERROR, NOTIF_INFO,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
    KEY_INTERACT, KEY_USE, KEY_INVENTORY, KEY_SKILL_TREE,
    KEY_HELP, KEY_PAUSE, KEY_MAP,
    KEY_LIGHT_ATTACK, KEY_HEAVY_ATTACK, KEY_BLOCK, KEY_DASH,
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
        self.current_floor = FLOOR_1F
        floor = self.school_map.get_floor(self.current_floor)
        self._floor_w = floor.width  if floor else 3200
        self._floor_h = floor.height if floor else 2400

    def _init_players(self):
        # Spawn in the Main Hall (centre of 1F corridor)
        cx, cy = 1600, 1000
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

    def _init_ui(self):
        self.ui = UI(self.screen)
        self.world_map = WorldMap(self.school_map)

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
                continue
            if event.type == pygame.KEYDOWN:
                self._on_key_down(event)
            elif event.type == pygame.KEYUP:
                pass  # movement uses get_pressed()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if self.state == GameState.TRADING:
                    self.trade_system.handle_click(event.pos)

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
            if self.state == GameState.PAUSED:
                self.state = GameState.PLAYING
            elif self.state == GameState.PLAYING:
                self.state = GameState.PAUSED
            elif self.state in (GameState.INVENTORY_SCREEN,
                                GameState.SKILL_TREE_SCREEN,
                                GameState.HELP):
                self.state = GameState.PLAYING
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
        if event.key == KEY_INTERACT:
            self._try_interact()
        elif event.key == KEY_INVENTORY:
            self.previous_state = self.state
            self.state = GameState.INVENTORY_SCREEN
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
        elif event.key == KEY_DASH:
            self.player.start_dash()

    def _keys_paused(self, event: pygame.event.Event):
        if event.key == pygame.K_q:
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

        if self.state == GameState.PLAYING:
            self._update_playing(dt)
        elif self.state == GameState.COMBAT:
            result = self.combat_system.update(dt)
            if result is not None:
                self.state = GameState.PLAYING
                if result == "win":
                    self.player.gain_xp(25)
                    self.ui.show_notification("Combat won! +25 XP", NOTIF_SUCCESS)
                elif result == "lose":
                    self.ui.show_notification("You were knocked out…", NOTIF_ERROR)
                    self.player.health = self.player.max_health // 2
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
        walls = floor.walls if floor else []
        self.player.update(keys, walls, dt)

        # Seamless staircase detection (silent floor switch)
        self._check_seamless_stairs()

        # Portal-type transitions (campus entrance)
        self._check_floor_transition()

        # Camera
        self.camera.update(self.player)

        # NPC AI — only update NPCs on current floor
        self.npc_manager.update_on_floor(dt, self.current_floor, floor)

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
            GameState.TRADING:           lambda: (self._draw_world(), self.trade_system.draw(self.screen)),
            GameState.PAUSED:            lambda: (self._draw_world(), self.ui.draw_pause_menu(self.screen)),
            GameState.INVENTORY_SCREEN:  lambda: self.ui.draw_inventory(self.screen, self.inventory),
            GameState.SKILL_TREE_SCREEN: lambda: self.ui.draw_skill_tree(self.screen, self.player.skill_tree, self.player),
            GameState.HELP:              lambda: self.ui.draw_help_screen(self.screen, self.character),
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
                             floor, room)

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
        self.world_map.draw(self.screen)
