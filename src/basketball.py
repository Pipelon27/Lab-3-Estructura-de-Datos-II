import pygame
import math
import random
from settings import SCREEN_WIDTH, SCREEN_HEIGHT, UI_ACCENT, WHITE, BLACK, KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, VT323_PATH, Direction

class BasketballGame:
    def __init__(self):
        self.active = False
        self.finished = False
        self.paused = False
        self.show_menu = True
        self.waiting_for_dismiss = False
        self.end_message = None
        self.is_coop = False

        self.player_score = 0
        self.opp_score = 0
        self.win_score = 10  # 10 for normal, 21 for coop
        
        self.reset_timer = 0.0
        self.swish_effect = None

        self.player_z = 0.0
        self.player_vz = 0.0
        self.opp_z = 0.0
        self.opp_vz = 0.0
        self.ally_z = 0.0
        self.ally_vz = 0.0
        self.opp2_z = 0.0
        self.opp2_vz = 0.0
        self.gravity = -1500.0
        self.jump_speed = 500.0

        self.ball_x = 900.0
        self.ball_y = 605.0
        self.ball_z = 0.0
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.ball_vz = 0.0
        self.ball_radius = 8
        self.ball_held_by = None  # 'player', 'opp', 'ally', 'opp2', or None
        self.possession = None

        # Court & Physics Constants
        self.court_rect = pygame.Rect(490, 258, 1070, 694)
        self.court_center = (900, 605)
        self.hoop_z = 30.0
        self.left_rim = (605, 605)
        self.right_rim = (1460, 605)
        self.three_point_radius = 209.0

        # Create bounding walls to keep players on court
        self.court_walls = [
            pygame.Rect(0, 0, 4000, 258), # Top
            pygame.Rect(0, 952, 4000, 3000), # Bottom
            pygame.Rect(0, 0, 490, 4000), # Left
            pygame.Rect(1560, 0, 4000, 4000), # Right
        ]

        self.shooting = False
        self.shoot_bar = 0.0
        self.shoot_dir = 1
        self._click_hold_timer = 0.0  # For pass vs shoot detection
        self._mouse_held = False
        
        self.blocking = False
        self.block_timer = 0.0
        self.opp_blocking = False
        self.opp_block_timer = 0.0
        
        self.opp_shooting = False
        self.opp_shoot_bar = 0.0
        self.opp_shoot_dir = 1
        self.opp_target_bar = 0.0

        # Opp2 shooting state (coop)
        self.opp2_shooting = False
        self.opp2_shoot_bar = 0.0
        self.opp2_shoot_dir = 1
        self.opp2_target_bar = 0.0
        self.opp2_blocking = False
        self.opp2_block_timer = 0.0
        self.opp2_shoot_anim = -1.0
        self.opp2_pending_shot = None

        self.last_shot_x = None
        self.last_shot_y = None
        self.last_shot_team = None
        self.shake_timer = 0.0
        self.shake_intensity = 0
        self.target_ball_x = 0.0
        self.target_ball_y = 0.0
        
        self.player_shoot_anim = -1.0
        self.opp_shoot_anim = -1.0
        self.ally_shoot_anim = -1.0
        self.player_pending_shot = None
        self.opp_pending_shot = None
        self.ally_pending_shot = None

        # Pass state
        self.pass_in_flight = False
        self.pass_requested = False
        self.pass_start_x = 0.0
        self.pass_start_y = 0.0
        self.pass_target_entity = None  # 'ally' or 'player'
        self.pass_target_x = 0.0
        self.pass_target_y = 0.0
        self.pass_speed = 600.0
        self.pass_team = None  # 'player_team' or 'opp_team'

        self._font = None
        self.player = None
        self.opponent = None
        self.ally = None      # Teammate (coop)
        self.opp2 = None      # Second opponent (coop)

        # AI difficulty
        self.ai_speed = 280.0
        self.ai_shoot_chance = 0.025
        self.ai_block_chance = 0.04
        self.ai_steal_range = 35
        
        # AI restructuring variables
        self.opp_ai_goal = 'drive'
        self.opp2_ai_goal = 'shoot_3'
        self.opp_ai_target = (580, 605)
        self.opp2_ai_target = (700, 605)
        self.opp_pass_cooldown = 0.0
        
        # Load custom ball sprite
        import os
        base_dir = os.path.dirname(os.path.dirname(__file__))
        ball_path = os.path.join(base_dir, "assets", "ball.png")
        if os.path.exists(ball_path):
            self.ball_img = pygame.image.load(ball_path).convert_alpha()
            self.ball_img = pygame.transform.scale(self.ball_img, (40, 40))
        else:
            self.ball_img = None

    def start(self, player, opponent, floor, is_coop=False, ally=None, opp2=None, is_host=True):
        self.player = player
        self.opponent = opponent
        self.floor = floor
        self.is_coop = is_coop
        self.is_host = is_host
        self.ally = ally
        self.opp2 = opp2
        self.win_score = 21 if is_coop else 10
        if self.floor:
            self.floor.hide_hoops = True
        # Temporarily disable NPC AI while playing basketball
        self.opponent.ai_enabled = False
        if self.ally:
            self.ally.ai_enabled = False
        if self.opp2:
            self.opp2.ai_enabled = False
        
        self.reset()
        self.show_menu = True
        self.active = False
        pygame.font.init()
        self._font = pygame.font.Font(VT323_PATH, 32) if VT323_PATH else pygame.font.SysFont(None, 32)

    def reset(self):
        self.player_score = 0
        self.opp_score = 0
        self.reset_positions()
        
        self.finished = False
        self.end_message = None
        self.waiting_for_dismiss = False
        self.ball_trail = []
        self.opp_pass_cooldown = 0.0
        self.select_offensive_goals()
        
        self.cheer_emojis = []
        self.particles = []
        self.player_streak = 0
        self.opp_streak = 0
        self.player_on_fire = False
        self.opp_on_fire = False
        self.opp_hold_timer = 0.0
        self.opp2_hold_timer = 0.0

    def reset_positions(self):
        # Place player on left, opp on right
        self.player.rect.centerx = 600
        self.player.rect.centery = 605
        self.player.direction = Direction.RIGHT
        self.player_z = 0.0
        self.player_vz = 0.0

        self.opponent.rect.centerx = 1200
        self.opponent.rect.centery = 605
        self.opponent.direction = Direction.LEFT
        self.opp_z = 0.0
        self.opp_vz = 0.0

        # Coop positions
        if self.is_coop and self.ally:
            self.ally.rect.centerx = 650
            self.ally.rect.centery = 450
            self.ally.direction = Direction.RIGHT
            self.ally_z = 0.0
            self.ally_vz = 0.0
        if self.is_coop and self.opp2:
            self.opp2.rect.centerx = 1150
            self.opp2.rect.centery = 450
            self.opp2.direction = Direction.LEFT
            self.opp2_z = 0.0
            self.opp2_vz = 0.0

        # Ball always at center of court, on the floor
        self.ball_x = float(self.court_center[0])
        self.ball_y = float(self.court_center[1])
        self.ball_z = 0.0
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.ball_vz = 0.0
        
        self.ball_held_by = None
        self.possession = None

        self.shooting = False
        self.opp_shooting = False
        self.blocking = False
        self.opp_blocking = False
        self.opp2_shooting = False
        self.opp2_blocking = False
        self.pass_in_flight = False
        self._mouse_held = False
        self._click_hold_timer = 0.0

    def sync_state(self, bb_data: dict, is_host: bool):
        """Synchronize state with the remote player."""
        if is_host:
            # Host receives client inputs
            if "z" in bb_data and self.ally:
                self.ally_z = bb_data["z"]
            if bb_data.get("pass_request", False):
                self._initiate_pass('ally', 'player')
            if "shooting" in bb_data:
                # The ally's shooting state is the client's shooting state
                if bb_data["shooting"]:
                    if not getattr(self, "ally_shooting", False):
                        self.ally_shooting = True
                    self.ally_shoot_bar = bb_data.get("shoot_bar", 0.0)
                else:
                    if getattr(self, "ally_shooting", False):
                        self.ally_shooting = False
                        self.ally_shoot_anim = 0.0
                        self.ally_pending_shot = bb_data.get("shoot_bar", 0.0)
        else:
            # Client receives authoritative state from Host
            self.target_ball_x = bb_data.get("ball_x", self.ball_x)
            self.target_ball_y = bb_data.get("ball_y", self.ball_y)
            self.ball_z = bb_data.get("ball_z", self.ball_z)
            
            raw_held = bb_data.get("ball_held_by", self.ball_held_by)
            if raw_held == 'player':
                self.ball_held_by = 'ally'
            elif raw_held == 'ally':
                self.ball_held_by = 'player'
            else:
                self.ball_held_by = raw_held

            raw_possession = bb_data.get("possession", self.possession)
            if raw_possession == 'player':
                self.possession = 'ally'
            elif raw_possession == 'ally':
                self.possession = 'player'
            else:
                self.possession = raw_possession

            self.pass_in_flight = bb_data.get("pass_in_flight", self.pass_in_flight)
            
            self.opp_z = bb_data.get("opp_z", self.opp_z)
            if self.opponent:
                if not hasattr(self, "opp_float_x"):
                    self.opp_float_x = float(self.opponent.rect.centerx)
                    self.opp_float_y = float(self.opponent.rect.centery)
                tx = bb_data.get("opp_x", self.opponent.rect.centerx)
                ty = bb_data.get("opp_y", self.opponent.rect.centery)
                self.opp_float_x += (tx - self.opp_float_x) * 0.4
                self.opp_float_y += (ty - self.opp_float_y) * 0.4
                self.opponent.rect.centerx = int(self.opp_float_x)
                self.opponent.rect.centery = int(self.opp_float_y)
            self.opp_shooting = bb_data.get("opp_shooting", False)
            self.opp_shoot_anim = bb_data.get("opp_shoot_anim", -1.0)
            
            if self.opp2:
                self.opp2_z = bb_data.get("opp2_z", self.opp2_z)
                if not hasattr(self, "opp2_float_x"):
                    self.opp2_float_x = float(self.opp2.rect.centerx)
                    self.opp2_float_y = float(self.opp2.rect.centery)
                tx2 = bb_data.get("opp2_x", self.opp2.rect.centerx)
                ty2 = bb_data.get("opp2_y", self.opp2.rect.centery)
                self.opp2_float_x += (tx2 - self.opp2_float_x) * 0.4
                self.opp2_float_y += (ty2 - self.opp2_float_y) * 0.4
                self.opp2.rect.centerx = int(self.opp2_float_x)
                self.opp2.rect.centery = int(self.opp2_float_y)
                self.opp2_shooting = bb_data.get("opp2_shooting", False)
                self.opp2_shoot_anim = bb_data.get("opp2_shoot_anim", -1.0)
                
            # Score and swish effect triggering on Client
            new_p_score = bb_data.get("p_score", self.player_score)
            new_o_score = bb_data.get("o_score", self.opp_score)
            
            if new_p_score > self.player_score:
                diff = new_p_score - self.player_score
                self.swish_effect = {
                    "x": self.right_rim[0],
                    "y": self.right_rim[1],
                    "text": "SWISH!" if diff == 3 else "2 PTS!",
                    "text_y": float(self.right_rim[1] - 40),
                    "color": (255, 215, 0) if diff == 3 else (100, 255, 100),
                    "particles": [{"x": self.right_rim[0] + random.uniform(-15, 15), "y": self.right_rim[1] - 30, "vx": random.uniform(-40, 40), "vy": random.uniform(80, 200), "life": 0.8} for _ in range(18)],
                    "timer": 1.0
                }
                self.shake_timer = 0.3
                self.shake_intensity = 8
                
                # Client Streak & On Fire sync
                self.player_streak = getattr(self, "player_streak", 0) + 1
                self.opp_streak = 0
                self.opp_on_fire = False
                if self.player_streak >= 2 and not getattr(self, "player_on_fire", False):
                    self.player_on_fire = True
                    self.swish_effect["text"] = "PLAYER IS ON FIRE!!!"
                    self.swish_effect["color"] = (255, 69, 0)
                    
                # Client: spawn cheering arcade words
                cheers = ["BOOM!", "FIRE!", "CLUTCH!", "INSANE!", "WOW!", "NICE!"]
                colors = [(255, 69, 0), (255, 215, 0), (50, 255, 50), (0, 255, 255), (255, 20, 147)]
                for _ in range(6):
                    self.cheer_emojis.append({
                        "x": random.uniform(self.court_rect.left + 50, self.court_rect.right - 50),
                        "y": random.uniform(self.court_rect.top + 50, self.court_rect.bottom - 50),
                        "text": random.choice(cheers),
                        "vy": random.uniform(-80, -40),
                        "color": random.choice(colors),
                        "life": 1.2
                    })
                
            if new_o_score > self.opp_score:
                diff = new_o_score - self.opp_score
                self.swish_effect = {
                    "x": self.left_rim[0],
                    "y": self.left_rim[1],
                    "text": "SWISH!" if diff == 3 else "2 PTS!",
                    "text_y": float(self.left_rim[1] - 40),
                    "color": (255, 69, 0),
                    "particles": [{"x": self.left_rim[0] + random.uniform(-15, 15), "y": self.left_rim[1] - 30, "vx": random.uniform(-40, 40), "vy": random.uniform(80, 200), "life": 0.8} for _ in range(18)],
                    "timer": 1.0
                }
                self.shake_timer = 0.3
                self.shake_intensity = 8
                
                # Client Streak & On Fire sync
                self.opp_streak = getattr(self, "opp_streak", 0) + 1
                self.player_streak = 0
                self.player_on_fire = False
                if self.opp_streak >= 2 and not getattr(self, "opp_on_fire", False):
                    self.opp_on_fire = True
                    self.swish_effect["text"] = "OPPONENTS ON FIRE!!!"
                    self.swish_effect["color"] = (255, 69, 0)
                    
                # Client: spawn cheering arcade words
                cheers = ["BOOM!", "FIRE!", "CLUTCH!", "INSANE!", "WOW!", "NICE!"]
                colors = [(255, 69, 0), (255, 215, 0), (50, 255, 50), (0, 255, 255), (255, 20, 147)]
                for _ in range(6):
                    self.cheer_emojis.append({
                        "x": random.uniform(self.court_rect.left + 50, self.court_rect.right - 50),
                        "y": random.uniform(self.court_rect.top + 50, self.court_rect.bottom - 50),
                        "text": random.choice(cheers),
                        "vy": random.uniform(-80, -40),
                        "color": random.choice(colors),
                        "life": 1.2
                    })
                
            self.player_score = new_p_score
            self.opp_score = new_o_score
            
            # Sync screen shake from Host
            h_shake = bb_data.get("shake_timer", 0.0)
            if h_shake > self.shake_timer:
                self.shake_timer = h_shake
                self.shake_intensity = bb_data.get("shake_intensity", 0)
            
            # Client ally is the Host
            if "z" in bb_data and self.ally:
                self.ally_z = bb_data["z"]
            if "shooting" in bb_data:
                if bb_data["shooting"]:
                    if not getattr(self, "ally_shooting", False):
                        self.ally_shooting = True
                    self.ally_shoot_bar = bb_data.get("shoot_bar", 0.0)
                else:
                    if getattr(self, "ally_shooting", False):
                        self.ally_shooting = False
                        self.ally_shoot_anim = 0.0
                        self.ally_pending_shot = bb_data.get("shoot_bar", 0.0)

    def handle_input(self, event: pygame.event.Event):
        if self.paused:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                    self.paused = False
            return
            
        if event.type == pygame.KEYDOWN:
            if self.show_menu and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.show_menu = False
                self.active = True
            elif self.waiting_for_dismiss and event.key == pygame.K_SPACE:
                self.waiting_for_dismiss = False
                self.finished = True
                self.opponent.ai_enabled = True # Restore NPC AI
                if self.ally:
                    self.ally.ai_enabled = True
                if self.opp2:
                    self.opp2.ai_enabled = True
        
        if self.active and not self.show_menu and not self.waiting_for_dismiss:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    # Jump
                    if self.player_z == 0:
                        self.player_vz = self.jump_speed
                elif getattr(event, 'key', None) in (pygame.K_LSHIFT, getattr(pygame, 'K_LSHIFT', 1073742049)): # KEY_DASH fallback
                    # Import KEY_DASH from settings to be safe
                    from settings import KEY_DASH, KEY_DASH_ALT
                    if event.key in (KEY_DASH, KEY_DASH_ALT, pygame.K_LSHIFT):
                        self.player.start_dash()
                    
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1: # Left Click -> Start hold timer for pass vs shoot
                    if self.ball_held_by == 'player':
                        self._mouse_held = True
                        self._click_hold_timer = 0.0
                elif event.button == 3: # Right Click -> Block/Steal
                    if self.ball_held_by != 'player' and self.player_z == 0:
                        self.blocking = True
                        self.block_timer = 0.3
                        # Steal check
                        opp_holders = ['opp', 'opp2']
                        for holder in opp_holders:
                            if self.ball_held_by == holder:
                                target = self.opponent if holder == 'opp' else self.opp2
                                if target and (holder == 'opp' and self.opp_shooting or holder == 'opp2' and self.opp2_shooting):
                                    dist = math.hypot(self.player.rect.centerx - target.rect.centerx, 
                                                      self.player.rect.centery - target.rect.centery)
                                    if dist < 60:
                                        if holder == 'opp':
                                            self.opp_shooting = False
                                        else:
                                            self.opp2_shooting = False
                                        self.ball_held_by = 'player'
                                        self.possession = 'player'

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self._mouse_held and self.ball_held_by == 'player':
                    if self.shooting:
                        # Was holding long enough -> shoot
                        self.player_shoot_anim = 0.0
                        self.player_pending_shot = self.shoot_bar
                        self.shooting = False
                    elif self.is_coop and self.ally and self._click_hold_timer < 0.15:
                        # Short click in coop -> pass to ally
                        self._initiate_pass('player', 'ally')
                self._mouse_held = False
                self._click_hold_timer = 0.0
                if self.shooting:
                    self.player_shoot_anim = 0.0
                    self.player_pending_shot = self.shoot_bar
                    self.shooting = False

    def handle_controller(self, controller):
        if self.paused:
            if controller.is_confirm_pressed() or controller.is_cancel_pressed():
                self.paused = False
            return
            
        if self.show_menu:
            if controller.is_confirm_pressed() or controller.is_pause_pressed():
                self.show_menu = False
                self.active = True
            return
            
        if self.waiting_for_dismiss:
            if controller.is_confirm_pressed() or controller.is_cancel_pressed():
                self.waiting_for_dismiss = False
                self.finished = True
                if self.opponent:
                    self.opponent.ai_enabled = True # Restore NPC AI
            return

        if self.active and not self.show_menu and not self.waiting_for_dismiss:
            # Jump with A button
            if controller.is_confirm_pressed():
                if self.player_z == 0:
                    self.player_vz = self.jump_speed

            # Shoot with X button (Hold to build power, Release to shoot)
            if controller.is_button_pressed(2): # XBOX_X is button index 2
                if self.ball_held_by == 'player':
                    self.shooting = True
                    self.shoot_bar = 0.0
                    self.shoot_dir = 1
            elif controller.is_button_released(2): # XBOX_X released
                if self.shooting and self.ball_held_by == 'player':
                    self.player_shoot_anim = 0.0
                    self.player_pending_shot = self.shoot_bar
                    self.shooting = False

            # Block/Steal with B button
            if controller.is_button_pressed(1): # XBOX_B is button index 1
                if self.ball_held_by != 'player' and self.player_z == 0:
                    self.blocking = True
                    self.block_timer = 0.3
                    # Steal check
                    if self.ball_held_by == 'opp' and self.opp_shooting:
                        dist = math.hypot(self.player.rect.centerx - self.opponent.rect.centerx, 
                                          self.player.rect.centery - self.opponent.rect.centery)
                        if dist < 60:
                            self.opp_shooting = False
                            self.ball_held_by = 'player'
                            self.possession = 'player'

    def _initiate_pass(self, from_entity, to_entity):
        """Start a pass from from_entity to to_entity."""
        if not self.is_host and from_entity == 'player':
            self.pass_requested = True
            
        if from_entity == 'player':
            sx, sy = self.player.rect.centerx, self.player.rect.centery
        elif from_entity == 'ally' and self.ally:
            sx, sy = self.ally.rect.centerx, self.ally.rect.centery
        elif from_entity == 'opp' and self.opponent:
            sx, sy = self.opponent.rect.centerx, self.opponent.rect.centery
        elif from_entity == 'opp2' and self.opp2:
            sx, sy = self.opp2.rect.centerx, self.opp2.rect.centery
        else:
            return
        self.ball_held_by = None
        self.pass_in_flight = True
        self.pass_start_x = sx
        self.pass_start_y = sy
        self.pass_target_entity = to_entity
        self.ball_x = sx
        self.ball_y = sy
        self.ball_z = 30.0
        self.ball_vz = 0.0
        # Determine team
        self.pass_team = 'player_team' if from_entity in ('player', 'ally') else 'opp_team'

    def _shoot_ball(self, shooter, power_bar):
        self.last_shot_team = shooter
        
        target_quality = 0.8
        is_perfect = (shooter in ('player', 'ally') and abs(power_bar - target_quality) < 0.02)
        
        is_dunk = False
        is_layup = False
        
        if shooter == 'player':
            self.last_shot_x = self.player.rect.centerx
            self.last_shot_y = self.player.rect.centery
            target_x, target_y = self.right_rim
            dist = math.hypot(self.last_shot_x - target_x, self.last_shot_y - target_y)
            if dist < 95:
                if self.player_z > 5:
                    is_dunk = True
                else:
                    is_layup = True
            is_3pt = dist > self.three_point_radius
            spread = 4.0 if is_3pt else 2.0
            quality = 1.0 if (is_perfect or is_dunk or is_layup) else (1.0 - abs(power_bar - target_quality) * spread)
            start_x = self.player.rect.centerx
            start_y = self.player.rect.centery
            start_z = self.player_z + 40
        elif shooter == 'ally' and self.ally:
            self.last_shot_x = self.ally.rect.centerx
            self.last_shot_y = self.ally.rect.centery
            target_x, target_y = self.right_rim
            dist = math.hypot(self.last_shot_x - target_x, self.last_shot_y - target_y)
            if dist < 95:
                if self.ally_z > 5:
                    is_dunk = True
                else:
                    is_layup = True
            is_3pt = dist > self.three_point_radius
            quality = 1.0 if (is_perfect or is_dunk or is_layup) else (1.0 - abs(power_bar - target_quality) * 2.5)
            start_x = self.ally.rect.centerx
            start_y = self.ally.rect.centery
            start_z = self.ally_z + 40
        elif shooter == 'opp2' and self.opp2:
            self.last_shot_x = self.opp2.rect.centerx
            self.last_shot_y = self.opp2.rect.centery
            target_x, target_y = self.left_rim
            dist = math.hypot(self.last_shot_x - target_x, self.last_shot_y - target_y)
            if dist < 95:
                if self.opp2_z > 5 or random.random() < 0.5:
                    is_dunk = True
                else:
                    is_layup = True
            is_3pt = dist > self.three_point_radius
            quality = 1.0 if (is_dunk or is_layup) else (1.0 - abs(power_bar - target_quality) * 2.0)
            start_x = self.opp2.rect.centerx
            start_y = self.opp2.rect.centery
            start_z = self.opp2_z + 40
        else:
            self.last_shot_x = self.opponent.rect.centerx
            self.last_shot_y = self.opponent.rect.centery
            target_x, target_y = self.left_rim
            dist = math.hypot(self.last_shot_x - target_x, self.last_shot_y - target_y)
            if dist < 95:
                if self.opp_z > 5 or random.random() < 0.5:
                    is_dunk = True
                else:
                    is_layup = True
            is_3pt = dist > self.three_point_radius
            quality = 1.0 if (is_dunk or is_layup) else (1.0 - abs(power_bar - target_quality) * 2.0)
            start_x = self.opponent.rect.centerx
            start_y = self.opponent.rect.centery
            start_z = self.opp_z + 40
            
        self.ball_held_by = None
        self.ball_x = start_x
        self.ball_y = start_y
        self.ball_z = start_z
        
        dx = target_x - start_x
        dy = target_y - start_y
        
        time_to_target = 0.55 if is_dunk else (0.75 if is_layup else 1.1)
        
        vx = dx / time_to_target
        vy = dy / time_to_target
        vz = (self.hoop_z - start_z - 0.5 * self.gravity * time_to_target**2) / time_to_target
        
        # Add error based on quality
        if not is_perfect and not is_dunk and not is_layup and quality < 0.8:
            error_x = random.uniform(-100, 100) * (1.0 - quality)
            error_y = random.uniform(-100, 100) * (1.0 - quality)
            vx += error_x
            vy += error_y
            
        self.ball_vx = vx
        self.ball_vy = vy
        self.ball_vz = vz

        if is_dunk or is_layup:
            self.shake_timer = 0.25
            self.shake_intensity = 7
            txt = "SLAM DUNK!" if is_dunk else "LAYUP!"
            self.swish_effect = {
                "x": start_x,
                "y": start_y,
                "text": txt,
                "text_y": float(start_y - 60),
                "color": (255, 69, 0) if is_dunk else (255, 215, 0),
                "particles": [{"x": start_x + random.uniform(-15, 15), "y": start_y - 10, "vx": random.uniform(-60, 60), "vy": random.uniform(-140, -60), "life": 0.6} for _ in range(16)],
                "timer": 0.8
            }
        elif is_perfect:
            self.swish_effect = {
                "x": start_x,
                "y": start_y,
                "text": "PERFECT RELEASE!",
                "text_y": float(start_y - 60),
                "color": (50, 255, 50),
                "particles": [{"x": start_x + random.uniform(-10, 10), "y": start_y - 10, "vx": random.uniform(-60, 60), "vy": random.uniform(-120, -40), "life": 0.6} for _ in range(12)],
                "timer": 0.8
            }
            self.shake_timer = 0.2
            self.shake_intensity = 4

    def get_ai_position_target(self, goal, entity):
        # Left rim is (530, 605)
        rx, ry = self.left_rim
        if goal == 'drive':
            # Target close to the hoop for a layup/dunk or close shot
            tx = rx + random.uniform(30, 70)
            ty = ry + random.uniform(-40, 40)
        elif goal == 'shoot_3':
            # Target outside 3pt line (three_point_radius is 150)
            tx = rx + self.three_point_radius + random.uniform(20, 50)
            ty = ry + random.uniform(-100, 100)
        else: # mid_range
            # Target between hoop and 3pt line
            tx = rx + random.uniform(80, 120)
            ty = ry + random.uniform(-60, 60)
        return (tx, ty)

    def select_offensive_goals(self):
        # Decide goals for both opponents
        self.opp_ai_goal = random.choice(['drive', 'shoot_3', 'mid_range'])
        if self.is_coop and self.opp2:
            if self.opp_ai_goal == 'drive':
                self.opp2_ai_goal = random.choice(['shoot_3', 'mid_range'])
            elif self.opp_ai_goal == 'shoot_3':
                self.opp2_ai_goal = random.choice(['drive', 'mid_range'])
            else:
                self.opp2_ai_goal = random.choice(['drive', 'shoot_3'])
        
        self.opp_ai_target = self.get_ai_position_target(self.opp_ai_goal, 'opp')
        if self.is_coop and self.opp2:
            self.opp2_ai_target = self.get_ai_position_target(self.opp2_ai_goal, 'opp2')

    def update(self, dt: float):
        if not self.active or self.show_menu or self.waiting_for_dismiss:
            return {"status": "running"}
            
        # Update ball trail
        if self.ball_held_by is None or getattr(self, "pass_in_flight", False):
            self.ball_trail.append((self.ball_x, self.ball_y, self.ball_z))
            if len(self.ball_trail) > 8:
                self.ball_trail.pop(0)
        else:
            if self.ball_trail:
                self.ball_trail.pop(0)
                
        # Update particles
        if not hasattr(self, "particles"): self.particles = []
        for p in self.particles[:]:
            p["life"] -= dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            if p["life"] <= 0:
                self.particles.remove(p)
                
        # Update cheer emojis
        if not hasattr(self, "cheer_emojis"): self.cheer_emojis = []
        for emoji in self.cheer_emojis[:]:
            emoji["life"] -= dt
            emoji["y"] += emoji["vy"] * dt
            if emoji["life"] <= 0:
                self.cheer_emojis.remove(emoji)
                
        # Spawn flame trail if player/ally is on fire
        if getattr(self, "player_on_fire", False):
            self.particles.append({
                "x": self.player.rect.centerx + random.uniform(-10, 10),
                "y": self.player.rect.centery + random.uniform(-5, 5) - self.player_z,
                "vx": random.uniform(-15, 15),
                "vy": random.uniform(-30, -10),
                "color": (255, random.randint(120, 200), 0),
                "size": random.randint(3, 5),
                "life": 0.35,
                "max_life": 0.35
            })
            if self.is_coop and self.ally:
                self.particles.append({
                    "x": self.ally.rect.centerx + random.uniform(-10, 10),
                    "y": self.ally.rect.centery + random.uniform(-5, 5) - self.ally_z,
                    "vx": random.uniform(-15, 15),
                    "vy": random.uniform(-30, -10),
                    "color": (255, random.randint(120, 200), 0),
                    "size": random.randint(3, 5),
                    "life": 0.35,
                    "max_life": 0.35
                })
        
        # Spawn flame trail if opponents are on fire
        if getattr(self, "opp_on_fire", False):
            self.particles.append({
                "x": self.opponent.rect.centerx + random.uniform(-10, 10),
                "y": self.opponent.rect.centery + random.uniform(-5, 5) - self.opp_z,
                "vx": random.uniform(-15, 15),
                "vy": random.uniform(-30, -10),
                "color": (255, random.randint(50, 120), 0),
                "size": random.randint(3, 5),
                "life": 0.35,
                "max_life": 0.35
            })
            if self.is_coop and self.opp2:
                self.particles.append({
                    "x": self.opp2.rect.centerx + random.uniform(-10, 10),
                    "y": self.opp2.rect.centery + random.uniform(-5, 5) - self.opp2_z,
                    "vx": random.uniform(-15, 15),
                    "vy": random.uniform(-30, -10),
                    "color": (255, random.randint(50, 120), 0),
                    "size": random.randint(3, 5),
                    "life": 0.35,
                    "max_life": 0.35
                })

        # Spawn flame trail behind ball if shot/passed by "On Fire" team
        if (self.ball_held_by is None or getattr(self, "pass_in_flight", False)) and getattr(self, "possession", None) is not None:
            is_p_team = self.possession in ('player', 'ally')
            is_o_team = self.possession in ('opp', 'opp2')
            if (is_p_team and getattr(self, "player_on_fire", False)) or (is_o_team and getattr(self, "opp_on_fire", False)):
                self.particles.append({
                    "x": self.ball_x + random.uniform(-5, 5),
                    "y": self.ball_y + random.uniform(-5, 5) - self.ball_z,
                    "vx": random.uniform(-10, 10),
                    "vy": random.uniform(-10, 10),
                    "color": (255, random.randint(140, 220), 20) if is_p_team else (255, random.randint(60, 120), 0),
                    "size": random.randint(4, 6),
                    "life": 0.25,
                    "max_life": 0.25
                })
            
        if self.reset_timer > 0:
            self.reset_timer -= dt
            if self.reset_timer <= 0:
                self.reset_positions()
                
        keys = pygame.key.get_pressed()

        # Click-hold timer: if held long enough, start shooting bar
        if self._mouse_held and self.ball_held_by == 'player' and not self.shooting:
            self._click_hold_timer += dt
            if self._click_hold_timer >= 0.15:
                self.shooting = True
                self.shoot_bar = 0.0
                self.shoot_dir = 1
        
        # Player Shooting Animation logic
        if self.player_shoot_anim >= 0:
            self.player_shoot_anim += dt * 10.0
            if self.player_shoot_anim >= 6.0:
                self.player_shoot_anim = -1.0
            elif self.player_shoot_anim >= 3.0 and self.player_pending_shot is not None:
                self._shoot_ball('player', self.player_pending_shot)
                self.player_pending_shot = None
                
        # Opponent Shooting Animation logic
        if self.opp_shoot_anim >= 0:
            self.opp_shoot_anim += dt * 10.0
            if self.opp_shoot_anim >= 6.0:
                self.opp_shoot_anim = -1.0
            elif self.opp_shoot_anim >= 3.0 and self.opp_pending_shot is not None:
                self._shoot_ball('opp', self.opp_pending_shot)
                self.opp_pending_shot = None

        # Opp2 Shooting Animation logic
        if getattr(self, "opp2_shoot_anim", -1.0) >= 0:
            self.opp2_shoot_anim += dt * 10.0
            if self.opp2_shoot_anim >= 6.0:
                self.opp2_shoot_anim = -1.0
            elif self.opp2_shoot_anim >= 3.0 and getattr(self, "opp2_pending_shot", None) is not None:
                self._shoot_ball('opp2', self.opp2_pending_shot)
                self.opp2_pending_shot = None

        # Ally Shooting Animation logic
        if self.ally_shoot_anim >= 0:
            self.ally_shoot_anim += dt * 10.0
            if self.ally_shoot_anim >= 6.0:
                self.ally_shoot_anim = -1.0
            elif self.ally_shoot_anim >= 3.0 and getattr(self, "ally_pending_shot", None) is not None:
                self._shoot_ball('ally', self.ally_pending_shot)
                self.ally_pending_shot = None
        
        # Player Movement (using top-down WASD logic from player)
        # To reuse animations and collisions:
        self.player.update(keys, self.court_walls, dt)
        if self.player_shoot_anim >= 0:
            self.player.state = "shoot"
            anim_key = f"shoot_{self.player.direction.value}"
            frames = self.player.animations.get(anim_key, [])
            if frames:
                self.player.image = frames[min(int(self.player_shoot_anim), len(frames)-1)]
        elif self.shooting:
            self.player.state = "shoot"
            anim_key = f"shoot_{self.player.direction.value}"
            frames = self.player.animations.get(anim_key, [])
            if frames:
                self.player.image = frames[0]
        
        # Player Jump Z-physics
        self.player_vz += self.gravity * dt
        self.player_z += self.player_vz * dt
        if self.player_z <= 0:
            self.player_z = 0
            self.player_vz = 0

        # AI and Physics are authoritative on the Host
        if self.is_host:
            # Decrement pass cooldown
            if getattr(self, "opp_pass_cooldown", 0.0) > 0.0:
                self.opp_pass_cooldown -= dt

            # Opponent AI (Restructured offensive movement & positioning)
            target_x = self.ball_x
            target_y = self.ball_y
            
            if self.ball_held_by == 'opp':
                # Opponent has the ball -> move to assigned offensive target zone
                target_x, target_y = self.opp_ai_target
                
                # Check for passing to teammate (coop mode)
                if self.is_coop and self.opp2 and getattr(self, "opp_pass_cooldown", 0.0) <= 0.0 and not getattr(self, "opp_shooting", False):
                    def_dist = math.hypot(self.opponent.rect.centerx - self.player.rect.centerx, self.opponent.rect.centery - self.player.rect.centery)
                    if self.ally:
                        def_dist = min(def_dist, math.hypot(self.opponent.rect.centerx - self.ally.rect.centerx, self.opponent.rect.centery - self.ally.rect.centery))
                    tm_def_dist = math.hypot(self.opp2.rect.centerx - self.player.rect.centerx, self.opp2.rect.centery - self.player.rect.centery)
                    if self.ally:
                        tm_def_dist = min(tm_def_dist, math.hypot(self.opp2.rect.centerx - self.ally.rect.centerx, self.opp2.rect.centery - self.ally.rect.centery))
                    
                    if def_dist < 70 and tm_def_dist > 100 and random.random() < 0.05:
                        self._initiate_pass('opp', 'opp2')
                        self.opp_pass_cooldown = 2.0
                        self.select_offensive_goals()
            elif self.ball_held_by == 'opp2' and self.opp2:
                # Teammate has ball -> off-ball movement to clear space/cut
                target_x, target_y = self.opp_ai_target
            elif self.ball_held_by in ('player', 'ally'):
                # Defense: Defend the player or ally depending on who has the ball
                p = self.player if self.ball_held_by == 'player' else self.ally
                if p:
                    target_x = p.rect.centerx - 40
                    target_y = p.rect.centery
                
            o_dx = target_x - self.opponent.rect.centerx
            o_dy = target_y - self.opponent.rect.centery
            dist = math.hypot(o_dx, o_dy)
            
            speed = self.ai_speed * dt
            if dist > 20:
                self.opponent.rect.centerx += int((o_dx / dist) * speed)
                self.opponent.rect.centery += int((o_dy / dist) * speed)
                
                # Simple direction assignment for animation
                if abs(o_dx) > abs(o_dy):
                    self.opponent.direction = Direction.RIGHT if o_dx > 0 else Direction.LEFT
                else:
                    self.opponent.direction = Direction.DOWN if o_dy > 0 else Direction.UP
                self.opponent.is_moving = True
            else:
                self.opponent.is_moving = False
                
            self.opponent._advance_animation(dt)
            self.opponent.rect.clamp_ip(self.court_rect)

            # Opp2 AI (if coop)
            if self.is_coop and self.opp2:
                o2_target_x = self.ball_x
                o2_target_y = self.ball_y
                if self.ball_held_by == 'opp2':
                    o2_target_x, o2_target_y = self.opp2_ai_target
                    
                    # Check for passing to teammate
                    if getattr(self, "opp_pass_cooldown", 0.0) <= 0.0 and not getattr(self, "opp2_shooting", False):
                        def_dist = math.hypot(self.opp2.rect.centerx - self.player.rect.centerx, self.opp2.rect.centery - self.player.rect.centery)
                        if self.ally:
                            def_dist = min(def_dist, math.hypot(self.opp2.rect.centerx - self.ally.rect.centerx, self.opp2.rect.centery - self.ally.rect.centery))
                        tm_def_dist = math.hypot(self.opponent.rect.centerx - self.player.rect.centerx, self.opponent.rect.centery - self.player.rect.centery)
                        if self.ally:
                            tm_def_dist = min(tm_def_dist, math.hypot(self.opponent.rect.centerx - self.ally.rect.centerx, self.opponent.rect.centery - self.ally.rect.centery))
                        
                        if def_dist < 70 and tm_def_dist > 100 and random.random() < 0.05:
                            self._initiate_pass('opp2', 'opp')
                            self.opp_pass_cooldown = 2.0
                            self.select_offensive_goals()
                elif self.ball_held_by == 'opp':
                    # Teammate has ball -> off-ball movement to clear space/cut
                    o2_target_x, o2_target_y = self.opp2_ai_target
                elif self.ball_held_by in ('player', 'ally'):
                    # Opp2 defends whoever the opponent is NOT defending
                    p = self.ally if self.ball_held_by == 'player' else self.player
                    if p:
                        o2_target_x = p.rect.centerx - 40
                        o2_target_y = p.rect.centery
                o2_dx = o2_target_x - self.opp2.rect.centerx
                o2_dy = o2_target_y - self.opp2.rect.centery
                dist2 = math.hypot(o2_dx, o2_dy)
                if dist2 > 20:
                    self.opp2.rect.centerx += int((o2_dx / dist2) * speed)
                    self.opp2.rect.centery += int((o2_dy / dist2) * speed)
                    if abs(o2_dx) > abs(o2_dy):
                        self.opp2.direction = Direction.RIGHT if o2_dx > 0 else Direction.LEFT
                    else:
                        self.opp2.direction = Direction.DOWN if o2_dy > 0 else Direction.UP
                    self.opp2.is_moving = True
                else:
                    self.opp2.is_moving = False
                self.opp2._advance_animation(dt)
                self.opp2.rect.clamp_ip(self.court_rect)

            # Opponent Z-physics
            self.opp_vz += self.gravity * dt
            self.opp_z += self.opp_vz * dt
            if self.opp_z <= 0:
                self.opp_z = 0
                self.opp_vz = 0
                
            if self.is_coop and self.opp2:
                self.opp2_vz = getattr(self, "opp2_vz", 0) + self.gravity * dt
                self.opp2_z = getattr(self, "opp2_z", 0) + self.opp2_vz * dt
                if self.opp2_z <= 0:
                    self.opp2_z = 0
                    self.opp2_vz = 0
            
            # Opponent AI Shooting
            if self.ball_held_by == 'opp':
                if not self.opp_shooting:
                    self.opp_hold_timer = getattr(self, "opp_hold_timer", 0.0) + dt
                    dist_to_target = math.hypot(self.opponent.rect.centerx - self.opp_ai_target[0], self.opponent.rect.centery - self.opp_ai_target[1])
                    
                    should_shoot = False
                    if dist_to_target < 65:
                        should_shoot = True
                    elif self.opp_hold_timer > 0.6:
                        should_shoot = True
                    elif random.random() < 0.06:
                        should_shoot = True
                        
                    if should_shoot and not getattr(self, "pass_in_flight", False):
                        self.opp_shooting = True
                        self.opp_shoot_bar = 0.0
                        self.opp_shoot_dir = 1
                        self.opp_target_bar = random.uniform(0.75, 0.85)
                        self.opp_hold_timer = 0.0
                else:
                    self.opp_hold_timer = 0.0
                    self.opp_shoot_bar += self.opp_shoot_dir * dt * 1.5
                    if self.opp_shoot_bar >= 1.0:
                        self.opp_shoot_bar = 1.0
                        self.opp_shoot_dir = -1
                    elif self.opp_shoot_bar <= 0.0:
                        self.opp_shoot_bar = 0.0
                        self.opp_shoot_dir = 1
                        
                    if self.opp_shoot_dir == 1 and self.opp_shoot_bar >= self.opp_target_bar:
                        self.opp_shoot_anim = 0.0
                        self.opp_pending_shot = self.opp_shoot_bar
                        self.opp_shooting = False
                
            # Opp2 AI Shooting
            if self.is_coop and self.opp2 and self.ball_held_by == 'opp2':
                if not getattr(self, "opp2_shooting", False):
                    self.opp2_hold_timer = getattr(self, "opp2_hold_timer", 0.0) + dt
                    dist_to_target2 = math.hypot(self.opp2.rect.centerx - self.opp2_ai_target[0], self.opp2.rect.centery - self.opp2_ai_target[1])
                    
                    should_shoot2 = False
                    if dist_to_target2 < 65:
                        should_shoot2 = True
                    elif self.opp2_hold_timer > 0.6:
                        should_shoot2 = True
                    elif random.random() < 0.06:
                        should_shoot2 = True
                        
                    if should_shoot2 and not getattr(self, "pass_in_flight", False):
                        self.opp2_shooting = True
                        self.opp2_shoot_bar = 0.0
                        self.opp2_shoot_dir = 1
                        self.opp2_target_bar = random.uniform(0.75, 0.85)
                        self.opp2_hold_timer = 0.0
                else:
                    self.opp2_hold_timer = 0.0
                    self.opp2_shoot_bar += self.opp2_shoot_dir * dt * 1.5
                    if self.opp2_shoot_bar >= 1.0:
                        self.opp2_shoot_bar = 1.0
                        self.opp2_shoot_dir = -1
                    elif self.opp2_shoot_bar <= 0.0:
                        self.opp2_shoot_bar = 0.0
                        self.opp2_shoot_dir = 1
                        
                    if self.opp2_shoot_dir == 1 and self.opp2_shoot_bar >= self.opp2_target_bar:
                        self.opp2_shoot_anim = 0.0
                        self.opp2_pending_shot = self.opp2_shoot_bar
                        self.opp2_shooting = False

            # AI actively blocks when player is shooting nearby
            holder = self.ball_held_by
            if holder in ('player', 'ally'):
                target_ent = self.player if holder == 'player' else self.ally
                if target_ent:
                    pdist = math.hypot(target_ent.rect.centerx - self.opponent.rect.centerx,
                                       target_ent.rect.centery - self.opponent.rect.centery)
                    if pdist < 60 and random.random() < self.ai_block_chance:
                        self.opp_blocking = True
                        self.opp_block_timer = 0.3
                        if getattr(self, "shooting", False) and holder == 'player':
                            self.shooting = False
                        if getattr(self, "ally_shooting", False) and holder == 'ally':
                            self.ally_shooting = False
                        self.ball_held_by = 'opp'
                        self.possession = 'opp'
                    
                    if self.is_coop and self.opp2:
                        pdist2 = math.hypot(target_ent.rect.centerx - self.opp2.rect.centerx,
                                            target_ent.rect.centery - self.opp2.rect.centery)
                        if pdist2 < 60 and random.random() < self.ai_block_chance:
                            self.opp2_blocking = True
                            self.opp2_block_timer = 0.3
                            if getattr(self, "shooting", False) and holder == 'player':
                                self.shooting = False
                            if getattr(self, "ally_shooting", False) and holder == 'ally':
                                self.ally_shooting = False
                            self.ball_held_by = 'opp2'
                            self.possession = 'opp2'

            # AI steals when very close
            if self.ball_held_by in ('player', 'ally') and not self.opp_blocking:
                steal_target = self.player if self.ball_held_by == 'player' else (self.ally if self.ally else None)
                if steal_target:
                    sdist = math.hypot(steal_target.rect.centerx - self.opponent.rect.centerx,
                                       steal_target.rect.centery - self.opponent.rect.centery)
                    if sdist < self.ai_steal_range and random.random() < 0.03:
                        self.ball_held_by = 'opp'
                        self.possession = 'opp'
            
            # AI passes to opp2 in coop
            if self.is_coop and self.opp2 and self.ball_held_by == 'opp' and not self.opp_shooting:
                if random.random() < 0.008:
                    self._initiate_pass('opp', 'opp2')
            if self.is_coop and self.opponent and self.ball_held_by == 'opp2' and not getattr(self, "opp2_shooting", False):
                if random.random() < 0.008:
                    self._initiate_pass('opp2', 'opp')

        # Opponent Image Override for Shooting
        if self.opp_shoot_anim >= 0:
            self.opponent.state = "shoot"
            anim_key = f"shoot_{self.opponent.direction.value}"
            frames = self.opponent.animations.get(anim_key, [])
            if frames:
                self.opponent.image = frames[min(int(self.opp_shoot_anim), len(frames)-1)]
        elif getattr(self, 'opp_shooting', False):
            self.opponent.state = "shoot"
            anim_key = f"shoot_{self.opponent.direction.value}"
            frames = self.opponent.animations.get(anim_key, [])
            if frames:
                self.opponent.image = frames[0]

        # Opp2 Image Override for Shooting
        if self.is_coop and self.opp2:
            if getattr(self, 'opp2_shoot_anim', -1.0) >= 0:
                self.opp2.state = "shoot"
                anim_key = f"shoot_{self.opp2.direction.value}"
                frames = self.opp2.animations.get(anim_key, [])
                if frames:
                    self.opp2.image = frames[min(int(self.opp2_shoot_anim), len(frames)-1)]
            elif getattr(self, 'opp2_shooting', False):
                self.opp2.state = "shoot"
                anim_key = f"shoot_{self.opp2.direction.value}"
                frames = self.opp2.animations.get(anim_key, [])
                if frames:
                    self.opp2.image = frames[0]

        # Ally Image Override for Shooting
        if self.is_coop and self.ally:
            if self.ally_shoot_anim >= 0:
                self.ally.state = "shoot"
                anim_key = f"shoot_{self.ally.direction.value}"
                frames = self.ally.animations.get(anim_key, [])
                if frames:
                    self.ally.image = frames[min(int(self.ally_shoot_anim), len(frames)-1)]
            elif getattr(self, 'ally_shooting', False):
                self.ally.state = "shoot"
                anim_key = f"shoot_{self.ally.direction.value}"
                frames = self.ally.animations.get(anim_key, [])
                if frames:
                    self.ally.image = frames[0]

        # Shooting bar logic
        if self.shooting:
            dist = math.hypot(self.player.rect.centerx - self.right_rim[0], self.player.rect.centery - self.right_rim[1])
            is_3pt = dist > self.three_point_radius
            bar_speed = 2.5 if is_3pt else 1.5
            self.shoot_bar += self.shoot_dir * dt * bar_speed
            if self.shoot_bar >= 1.0:
                self.shoot_bar = 1.0
                self.shoot_dir = -1
            elif self.shoot_bar <= 0.0:
                self.shoot_bar = 0.0
                self.shoot_dir = 1

            # Pulsing tactile vibration during charging
            from src.controller import get_controller
            controller = get_controller()
            if controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller":
                controller.rumble(0.1, 0.15 + self.shoot_bar * 0.15, 50)

        if self.block_timer > 0:
            self.block_timer -= dt
            if self.block_timer <= 0:
                self.blocking = False
                
        if self.opp_block_timer > 0:
            self.opp_block_timer -= dt
            if self.opp_block_timer <= 0:
                self.opp_blocking = False

        # Ball physics
        if self.is_host:
            if self.ball_held_by == 'player':
                self.ball_x = self.player.rect.centerx
                self.ball_y = self.player.rect.centery
                self.ball_z = self.player_z + 40
                self.ball_vx = 0
                self.ball_vy = 0
                self.ball_vz = 0
            elif self.ball_held_by == 'ally' and self.ally:
                self.ball_x = self.ally.rect.centerx
                self.ball_y = self.ally.rect.centery
                self.ball_z = self.ally_z + 40
                self.ball_vx = 0
                self.ball_vy = 0
                self.ball_vz = 0
            elif self.ball_held_by == 'opp2' and self.opp2:
                self.ball_x = self.opp2.rect.centerx
                self.ball_y = self.opp2.rect.centery
                self.ball_z = self.opp2_z + 40
                self.ball_vx = 0
                self.ball_vy = 0
                self.ball_vz = 0
            elif self.pass_in_flight:
                target_ent = None
                if self.pass_target_entity == 'ally': target_ent = self.ally
                elif self.pass_target_entity == 'player': target_ent = self.player
                elif self.pass_target_entity == 'opp': target_ent = self.opponent
                elif self.pass_target_entity == 'opp2': target_ent = self.opp2
    
                if target_ent:
                    tx, ty = target_ent.rect.centerx, target_ent.rect.centery
                    dx = tx - self.ball_x
                    dy = ty - self.ball_y
                    dist = math.hypot(dx, dy)
                    if dist < 20:
                        self.pass_in_flight = False
                        self.ball_held_by = self.pass_target_entity
                        self.possession = self.pass_target_entity
                    else:
                        self.ball_vx = (dx / dist) * self.pass_speed
                        self.ball_vy = (dy / dist) * self.pass_speed
                        self.ball_x += self.ball_vx * dt
                        self.ball_y += self.ball_vy * dt
                else:
                    self.pass_in_flight = False
            else:
                self.ball_vz += self.gravity * dt
                self.ball_x += self.ball_vx * dt
                self.ball_y += self.ball_vy * dt
                self.ball_z += self.ball_vz * dt
    
                # Bouncing
                if self.ball_z <= 0:
                    self.ball_z = 0
                    self.ball_vz *= -0.7
                    self.ball_vx *= 0.9
                    self.ball_vy *= 0.9
    
                # Court bounds bouncing
                if self.ball_x <= self.court_rect.left or self.ball_x >= self.court_rect.right:
                    self.ball_vx *= -0.8
                    self.ball_x = max(self.court_rect.left, min(self.court_rect.right, self.ball_x))
                if self.ball_y <= self.court_rect.top or self.ball_y >= self.court_rect.bottom:
                    self.ball_vy *= -0.8
                    self.ball_y = max(self.court_rect.top, min(self.court_rect.bottom, self.ball_y))
    
                p_dist = math.hypot(self.ball_x - self.player.rect.centerx, self.ball_y - self.player.rect.centery)
                o_dist = math.hypot(self.ball_x - self.opponent.rect.centerx, self.ball_y - self.opponent.rect.centery)
    
                # Blocking logic (mid-air)
                if self.blocking and p_dist < 50 and self.ball_z < self.player_z + 80 and self.ball_held_by is None:
                    self.ball_vx *= -1.2
                    self.ball_vy *= -1.2
                    self.ball_vz = 300
                    self.blocking = False
                    self.possession = None
                    from src.controller import get_controller
                    controller = get_controller()
                    if controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller":
                        controller.rumble(0.6, 0.7, 150)
                
                if self.opp_blocking and o_dist < 50 and self.ball_z < self.opp_z + 80 and self.ball_held_by is None:
                    self.ball_vx *= -1.2
                    self.ball_vy *= -1.2
                    self.ball_vz = 300
                    self.opp_blocking = False
                    self.possession = None
    
                # Catching (only if ball is low or player jumps)
                if p_dist < 40 and abs(self.ball_z - self.player_z) < 50 and self.possession != 'player':
                    was_held_by_opp = (self.ball_held_by == 'opp')
                    self.ball_held_by = 'player'
                    self.possession = 'player'
                    from src.controller import get_controller
                    controller = get_controller()
                    if controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller":
                        if was_held_by_opp:
                             controller.rumble(0.6, 0.6, 150)
                        else:
                             controller.rumble(0.3, 0.3, 80)
                elif o_dist < 40 and abs(self.ball_z - self.opp_z) < 50 and self.possession != 'opp':
                    was_held_by_player = (self.ball_held_by == 'player')
                    self.ball_held_by = 'opp'
                    self.possession = 'opp'
                    self.select_offensive_goals()
                elif self.is_coop and self.ally and math.hypot(self.ball_x - self.ally.rect.centerx, self.ball_y - self.ally.rect.centery) < 40 and abs(self.ball_z - self.ally_z) < 50 and self.possession != 'ally':
                    self.ball_held_by = 'ally'
                    self.possession = 'ally'
                elif self.is_coop and self.opp2 and math.hypot(self.ball_x - self.opp2.rect.centerx, self.ball_y - self.opp2.rect.centery) < 40 and abs(self.ball_z - self.opp2_z) < 50 and self.possession != 'opp2':
                    self.ball_held_by = 'opp2'
                    self.possession = 'opp2'
                    self.select_offensive_goals()
    
                 # Scoring (Check 2.5D intersection with hoop rim area)
                # We assume the ball falls THROUGH the hoop (vz < 0) near the rim coordinates
                if self.ball_vz < 0 and abs(self.ball_z - self.hoop_z) < 20:
                    dist_right = math.hypot(self.ball_x - self.right_rim[0], self.ball_y - self.right_rim[1])
                    dist_left = math.hypot(self.ball_x - self.left_rim[0], self.ball_y - self.left_rim[1])
                    
                    if dist_right < 20 and self.reset_timer <= 0:
                        pts = 3 if (self.last_shot_team in ('player', 'ally') and math.hypot(self.last_shot_x - self.right_rim[0], self.last_shot_y - self.right_rim[1]) > self.three_point_radius) else 2
                        self.player_score += pts
                        self.reset_timer = 1.0 # Wait 1 second before resetting
                        self.shake_timer = 0.3
                        self.shake_intensity = 8
                        self.swish_effect = {
                            "x": self.right_rim[0],
                            "y": self.right_rim[1],
                            "text": "SWISH!" if pts == 3 else "2 PTS!",
                            "text_y": float(self.right_rim[1] - 40),
                            "color": (255, 215, 0) if pts == 3 else (100, 255, 100),
                            "particles": [{"x": self.right_rim[0] + random.uniform(-15, 15), "y": self.right_rim[1] - 30, "vx": random.uniform(-40, 40), "vy": random.uniform(80, 200), "life": 0.8} for _ in range(18)],
                            "timer": 1.0
                        }
                        
                        # Streak and On Fire mechanics
                        self.player_streak = getattr(self, "player_streak", 0) + 1
                        self.opp_streak = 0
                        self.opp_on_fire = False
                        if self.player_streak >= 2 and not getattr(self, "player_on_fire", False):
                            self.player_on_fire = True
                            self.swish_effect["text"] = "PLAYER IS ON FIRE!!!"
                            self.swish_effect["color"] = (255, 69, 0)
                            
                        # Spawn arcade cheering words
                        cheers = ["BOOM!", "FIRE!", "CLUTCH!", "INSANE!", "WOW!", "NICE!"]
                        colors = [(255, 69, 0), (255, 215, 0), (50, 255, 50), (0, 255, 255), (255, 20, 147)]
                        for _ in range(6):
                            self.cheer_emojis.append({
                                "x": random.uniform(self.court_rect.left + 50, self.court_rect.right - 50),
                                "y": random.uniform(self.court_rect.top + 50, self.court_rect.bottom - 50),
                                "text": random.choice(cheers),
                                "vy": random.uniform(-80, -40),
                                "color": random.choice(colors),
                                "life": 1.2
                            })
                            
                        from src.controller import get_controller
                        controller = get_controller()
                        if controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller":
                            controller.rumble(0.8, 0.8, 300)
                    elif dist_left < 20 and self.reset_timer <= 0:
                        pts = 3 if (self.last_shot_team in ('opp', 'opp2') and math.hypot(self.last_shot_x - self.left_rim[0], self.left_rim[1] - 605) > self.three_point_radius) else 2
                        self.opp_score += pts
                        self.reset_timer = 1.0
                        self.shake_timer = 0.3
                        self.shake_intensity = 8
                        self.swish_effect = {
                            "x": self.left_rim[0],
                            "y": self.left_rim[1],
                            "text": "SWISH!" if pts == 3 else "2 PTS!",
                            "text_y": float(self.left_rim[1] - 40),
                            "color": (255, 69, 0),
                            "particles": [{"x": self.left_rim[0] + random.uniform(-15, 15), "y": self.left_rim[1] - 30, "vx": random.uniform(-40, 40), "vy": random.uniform(80, 200), "life": 0.8} for _ in range(18)],
                            "timer": 1.0
                        }
                        
                        # Streak and On Fire mechanics
                        self.opp_streak = getattr(self, "opp_streak", 0) + 1
                        self.player_streak = 0
                        self.player_on_fire = False
                        if self.opp_streak >= 2 and not getattr(self, "opp_on_fire", False):
                            self.opp_on_fire = True
                            self.swish_effect["text"] = "OPPONENTS ON FIRE!!!"
                            self.swish_effect["color"] = (255, 69, 0)
                            
                        # Spawn arcade cheering words
                        cheers = ["BOOM!", "FIRE!", "CLUTCH!", "INSANE!", "WOW!", "NICE!"]
                        colors = [(255, 69, 0), (255, 215, 0), (50, 255, 50), (0, 255, 255), (255, 20, 147)]
                        for _ in range(6):
                            self.cheer_emojis.append({
                                "x": random.uniform(self.court_rect.left + 50, self.court_rect.right - 50),
                                "y": random.uniform(self.court_rect.top + 50, self.court_rect.bottom - 50),
                                "text": random.choice(cheers),
                                "vy": random.uniform(-80, -40),
                                "color": random.choice(colors),
                                "life": 1.2
                            })
                            
                        from src.controller import get_controller
                        controller = get_controller()
                        if controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller":
                            controller.rumble(0.8, 0.2, 400)

        else:
            # Client smoothly LERPs the ball position
            self.ball_x += (getattr(self, "target_ball_x", self.ball_x) - self.ball_x) * 0.4
            self.ball_y += (getattr(self, "target_ball_y", self.ball_y) - self.ball_y) * 0.4

        # Update screen shake
        if getattr(self, "shake_timer", 0.0) > 0.0:
            self.shake_timer -= dt

        # Update swish effect
        if self.swish_effect:
            self.swish_effect["timer"] -= dt
            self.swish_effect["text_y"] -= dt * 60 # Float the text upwards!
            for p in self.swish_effect["particles"]:
                p["x"] += p["vx"] * dt
                p["y"] += p["vy"] * dt
                p["life"] -= dt
            if self.swish_effect["timer"] <= 0:
                self.swish_effect = None

        if self.player_score >= self.win_score:
            self.end_message = "You Win!"
            self.waiting_for_dismiss = True
        elif self.opp_score >= self.win_score:
            self.end_message = "Opponent Wins!"
            self.waiting_for_dismiss = True

        return None

    def _draw_premium_shoot_bar(self, screen, camera, x, y, z, value, smooth_val_attr, is_3pt):
        # Retrieve or initialize the smooth value
        if not hasattr(self, smooth_val_attr):
            setattr(self, smooth_val_attr, 0.0)
        curr_smooth = getattr(self, smooth_val_attr)
        
        # Smoothly LERP towards target
        curr_smooth += (value - curr_smooth) * 0.35
        curr_smooth = max(0.0, min(1.0, curr_smooth))
        setattr(self, smooth_val_attr, curr_smooth)

        # Apply camera position
        bx, by = camera.apply_pos(x, y - z - 85)
        
        bar_w = 70
        bar_h = 10
        bar_x = bx - bar_w // 2
        bar_y = by

        # 1. Draw outer border/shadow
        shadow_rect = pygame.Rect(bar_x - 3, bar_y - 3, bar_w + 6, bar_h + 6)
        pygame.draw.rect(screen, (10, 10, 20, 180), shadow_rect, border_radius=4)
        
        # 2. Draw background panel
        bg_rect = pygame.Rect(bar_x, bar_y, bar_w, bar_h)
        pygame.draw.rect(screen, (30, 30, 45), bg_rect, border_radius=3)
        pygame.draw.rect(screen, (60, 60, 85), bg_rect, width=1, border_radius=3)

        # 3. Draw Sweet Spot
        green_min, green_max = (0.75, 0.85) if is_3pt else (0.7, 0.9)
        green_x = bar_x + int(bar_w * green_min)
        green_w = int(bar_w * (green_max - green_min))
        
        green_rect = pygame.Rect(green_x, bar_y + 1, green_w, bar_h - 2)
        pygame.draw.rect(screen, (0, 220, 100), green_rect)
        
        # 4. Fill progress bar with dynamic color transitions
        fill_w = int(bar_w * curr_smooth)
        if fill_w > 0:
            if green_min < curr_smooth < green_max:
                color = (0, 255, 120)  # Neon Green
            elif 0.5 < curr_smooth < 0.95:
                color = (255, 220, 0)  # Vibrant Yellow
            else:
                color = (255, 70, 70)  # Bright Coral Red
            
            fill_rect = pygame.Rect(bar_x + 1, bar_y + 1, fill_w - 2, bar_h - 2)
            pygame.draw.rect(screen, color, fill_rect, border_radius=2)
            
            # Gloss overlay sheen
            try:
                sheen = pygame.Surface((fill_w - 2, (bar_h - 2) // 2), pygame.SRCALPHA)
                sheen.fill((255, 255, 255, 60))
                screen.blit(sheen, (bar_x + 1, bar_y + 1))
            except Exception:
                pass

        # 5. Draw target marker line
        perfect_release_x = bar_x + int(bar_w * 0.8)
        pygame.draw.line(screen, (255, 255, 255), (perfect_release_x, bar_y - 2), (perfect_release_x, bar_y + bar_h + 2), 2)

    def draw(self, screen: pygame.Surface, camera):
        # We don't fill the background. The actual map is drawn behind this!
        
        # 1. Draw Shadows (at ground level, z=0)
        shadow_color = (0, 0, 0, 80)
        shadow_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        
        px, py = camera.apply_pos(self.player.rect.centerx, self.player.rect.centery)
        pygame.draw.ellipse(shadow_surf, shadow_color, (px - 15, py - 5, 30, 10))
        
        ox, oy = camera.apply_pos(self.opponent.rect.centerx, self.opponent.rect.centery)
        pygame.draw.ellipse(shadow_surf, shadow_color, (ox - 15, oy - 5, 30, 10))
        
        if self.is_coop and self.ally:
            ax, ay = camera.apply_pos(self.ally.rect.centerx, self.ally.rect.centery)
            pygame.draw.ellipse(shadow_surf, shadow_color, (ax - 15, ay - 5, 30, 10))
        if self.is_coop and self.opp2:
            o2x, o2y = camera.apply_pos(self.opp2.rect.centerx, self.opp2.rect.centery)
            pygame.draw.ellipse(shadow_surf, shadow_color, (o2x - 15, o2y - 5, 30, 10))
        
        bx, by = camera.apply_pos(self.ball_x, self.ball_y)
        ball_shadow_w = max(4, 16 - (self.ball_z * 0.05))
        pygame.draw.ellipse(shadow_surf, shadow_color, (bx - ball_shadow_w/2, by - ball_shadow_w/4, ball_shadow_w, ball_shadow_w/2))
        
        screen.blit(shadow_surf, (0, 0))

        # 2. Draw Entities with Z-offset applied to their screen rendering!
        # Temporarily modify centery to simulate Z-height
        old_py = self.player.rect.centery
        old_oy = self.opponent.rect.centery
        old_ay = self.ally.rect.centery if self.ally else 0
        old_o2y = self.opp2.rect.centery if self.opp2 else 0
        
        self.player.rect.centery = old_py - int(self.player_z)
        self.opponent.rect.centery = old_oy - int(self.opp_z)
        if self.is_coop and self.ally:
            self.ally.rect.centery = old_ay - int(self.ally_z)
        if self.is_coop and self.opp2:
            self.opp2.rect.centery = old_o2y - int(self.opp2_z)
        
        def draw_scaled_player():
            if self.player.image:
                scaled = pygame.transform.scale_by(self.player.image, 1.5)
                rect = scaled.get_rect(midbottom=camera.apply(self.player).midbottom)
                screen.blit(scaled, rect)
                if self.is_coop:
                    font = pygame.font.Font(VT323_PATH, 14) if VT323_PATH else pygame.font.SysFont(None, 14)
                    name = font.render(getattr(self.player, 'character', getattr(self.player, 'name', "P1")).value.title() if hasattr(getattr(self.player, 'character', None), 'value') else "Player", True, (100, 255, 100))
                    screen.blit(name, name.get_rect(center=(rect.centerx, rect.top - 5)))
                
        def draw_scaled_opp():
            if self.opponent.image:
                scaled = pygame.transform.scale_by(self.opponent.image, 1.5)
                rect = scaled.get_rect(midbottom=camera.apply(self.opponent).midbottom)
                screen.blit(scaled, rect)
                if self.is_coop:
                    font = pygame.font.Font(VT323_PATH, 14) if VT323_PATH else pygame.font.SysFont(None, 14)
                    name = font.render(getattr(self.opponent, 'name', "Opp1"), True, (255, 100, 100))
                    screen.blit(name, name.get_rect(center=(rect.centerx, rect.top - 5)))

        def draw_scaled_ally():
            if self.is_coop and self.ally and self.ally.image:
                scaled = pygame.transform.scale_by(self.ally.image, 1.5)
                rect = scaled.get_rect(midbottom=camera.apply(self.ally).midbottom)
                screen.blit(scaled, rect)
                font = pygame.font.Font(VT323_PATH, 14) if VT323_PATH else pygame.font.SysFont(None, 14)
                name_str = getattr(self.ally, 'character', getattr(self.ally, 'name', "P2")).value.title() if hasattr(getattr(self.ally, 'character', None), 'value') else "Ally"
                name = font.render(name_str, True, (100, 255, 100))
                screen.blit(name, name.get_rect(center=(rect.centerx, rect.top - 5)))

        def draw_scaled_opp2():
            if self.is_coop and self.opp2 and self.opp2.image:
                scaled = pygame.transform.scale_by(self.opp2.image, 1.5)
                rect = scaled.get_rect(midbottom=camera.apply(self.opp2).midbottom)
                screen.blit(scaled, rect)
                font = pygame.font.Font(VT323_PATH, 14) if VT323_PATH else pygame.font.SysFont(None, 14)
                name = font.render(getattr(self.opp2, 'name', "Opp2"), True, (255, 100, 100))
                screen.blit(name, name.get_rect(center=(rect.centerx, rect.top - 5)))

        def draw_left_hoop():
            if hasattr(self, 'floor') and self.floor and hasattr(self.floor, '_left_hoop_surface') and self.floor._left_hoop_surface:
                rect = self.floor._left_hoop_surface.get_rect(topleft=(516, 510))
                screen.blit(self.floor._left_hoop_surface, camera.apply_rect(rect))

        def draw_right_hoop():
            if hasattr(self, 'floor') and self.floor and hasattr(self.floor, '_right_hoop_surface') and self.floor._right_hoop_surface:
                rect = self.floor._right_hoop_surface.get_rect(topleft=(1417, 510))
                screen.blit(self.floor._right_hoop_surface, camera.apply_rect(rect))
        
        def draw_ball():
            # Draw trail first
            if getattr(self, "ball_trail", None):
                for idx, (tx, ty, tz) in enumerate(self.ball_trail):
                    bx_t, by_t = camera.apply_pos(tx, ty - tz)
                    alpha = int(120 * (idx + 1) / len(self.ball_trail))
                    trail_color = (255, 165, 0, alpha)
                    trail_surf = pygame.Surface((30, 30), pygame.SRCALPHA)
                    radius = int(8 * (idx + 1) / len(self.ball_trail))
                    radius = max(2, radius)
                    pygame.draw.circle(trail_surf, trail_color, (15, 15), radius)
                    screen.blit(trail_surf, (bx_t - 15, by_t - 15))
            
            bx, by = camera.apply_pos(self.ball_x, self.ball_y - self.ball_z)
            if hasattr(self, 'ball_img') and self.ball_img:
                screen.blit(self.ball_img, (bx - self.ball_img.get_width()//2, by - self.ball_img.get_height()//2))
            else:
                pygame.draw.circle(screen, (255, 140, 0), (bx, by), self.ball_radius)
                
        # We must draw them based on Y-sorting.
        entities = [
            (old_py + self.player.rect.height // 2, draw_scaled_player),
            (old_oy + self.opponent.rect.height // 2, draw_scaled_opp),
            (700, draw_left_hoop),
            (700, draw_right_hoop),
            (self.ball_y + 10, draw_ball)
        ]
        if self.is_coop and self.ally:
            entities.append((old_ay + self.ally.rect.height // 2, draw_scaled_ally))
        if self.is_coop and self.opp2:
            entities.append((old_o2y + self.opp2.rect.height // 2, draw_scaled_opp2))
        entities.sort(key=lambda x: x[0])
        for _, draw_func in entities:
            draw_func()
            
        # Draw swish particles and floating text
        if self.swish_effect:
            for p in self.swish_effect["particles"]:
                if p["life"] > 0:
                    px, py = camera.apply_pos(p["x"], p["y"])
                    alpha = int(255 * (p["life"] / 0.8))
                    color = (255, 255, 255, alpha)
                    particle_surf = pygame.Surface((6, 6), pygame.SRCALPHA)
                    pygame.draw.circle(particle_surf, color, (3, 3), 3)
                    screen.blit(particle_surf, (px - 3, py - 3))
            
            if self._font and self.swish_effect["timer"] > 0:
                text_surf = self._font.render(self.swish_effect["text"], True, self.swish_effect["color"])
                px, py = camera.apply_pos(self.swish_effect["x"], self.swish_effect["text_y"])
                screen.blit(text_surf, (px - text_surf.get_width()//2, py))
            
        # Draw general particles (with blending / transparent alpha)
        if getattr(self, "particles", None):
            for p in self.particles:
                px, py = camera.apply_pos(p["x"], p["y"])
                alpha = int(255 * max(0.0, min(1.0, p["life"] / p["max_life"])))
                color = p["color"]
                if len(color) == 3:
                    color = color + (alpha,)
                else:
                    color = (color[0], color[1], color[2], alpha)
                particle_surf = pygame.Surface((p["size"]*2, p["size"]*2), pygame.SRCALPHA)
                pygame.draw.circle(particle_surf, color, (p["size"], p["size"]), p["size"])
                screen.blit(particle_surf, (px - p["size"], py - p["size"]))
                
        # Draw cheering arcade words popups
        if getattr(self, "cheer_emojis", None) and self._font:
            for emoji in self.cheer_emojis:
                ex, ey = camera.apply_pos(emoji["x"], emoji["y"])
                alpha = int(255 * max(0.0, min(1.0, emoji["life"] / 1.2)))
                text_surf = self._font.render(emoji["text"], True, emoji["color"])
                if alpha < 255:
                    text_surf.set_alpha(alpha)
                screen.blit(text_surf, (ex - text_surf.get_width()//2, ey))
            
        # Draw block aura effect
        if self.blocking:
            pygame.draw.circle(screen, (100, 200, 255, 128), camera.apply_pos(self.player.rect.centerx, self.player.rect.centery), 30, 4)
        if self.opp_blocking:
            pygame.draw.circle(screen, (255, 150, 100, 128), camera.apply_pos(self.opponent.rect.centerx, self.opponent.rect.centery), 30, 4)

        # Restore original Y coordinates so physics aren't broken!
        self.player.rect.centery = old_py
        self.opponent.rect.centery = old_oy
        if self.is_coop and self.ally:
            self.ally.rect.centery = old_ay
        if self.is_coop and self.opp2:
            self.opp2.rect.centery = old_o2y

        # 3. Draw UI
        score_text = self._font.render(f"Player: {self.player_score}  |  Opp: {self.opp_score}", True, WHITE)
        # Draw background rect for score for readability over world
        s_rect = score_text.get_rect(center=(SCREEN_WIDTH // 2, 30))
        pygame.draw.rect(screen, (0, 0, 0, 150), s_rect.inflate(20, 10))
        screen.blit(score_text, s_rect)

        # Draw all active shooting bars with smooth local LERP interpolation
        # 1. Local Player
        if self.shooting:
            dist = math.hypot(self.player.rect.centerx - self.right_rim[0], self.player.rect.centery - self.right_rim[1])
            is_3pt = dist > self.three_point_radius
            self._draw_premium_shoot_bar(screen, camera, self.player.rect.centerx, old_py, self.player_z, self.shoot_bar, "smooth_shoot_bar", is_3pt)
            
        # 2. Remote Ally Teammate (Coop)
        if self.is_coop and self.ally and getattr(self, "ally_shooting", False):
            dist = math.hypot(self.ally.rect.centerx - self.right_rim[0], self.ally.rect.centery - self.right_rim[1])
            is_3pt = dist > self.three_point_radius
            self._draw_premium_shoot_bar(screen, camera, self.ally.rect.centerx, old_ay, self.ally_z, getattr(self, "ally_shoot_bar", 0.0), "smooth_ally_shoot_bar", is_3pt)

        # 3. Main Opponent AI
        if self.opp_shooting:
            dist = math.hypot(self.opponent.rect.centerx - self.left_rim[0], self.opponent.rect.centery - self.left_rim[1])
            is_3pt = dist > self.three_point_radius
            self._draw_premium_shoot_bar(screen, camera, self.opponent.rect.centerx, old_oy, self.opp_z, self.opp_shoot_bar, "smooth_opp_shoot_bar", is_3pt)

        # 4. Teammate Opponent AI (Coop)
        if self.is_coop and self.opp2 and getattr(self, "opp2_shooting", False):
            dist = math.hypot(self.opp2.rect.centerx - self.left_rim[0], self.opp2.rect.centery - self.left_rim[1])
            is_3pt = dist > self.three_point_radius
            self._draw_premium_shoot_bar(screen, camera, self.opp2.rect.centerx, old_o2y, getattr(self, "opp2_z", 0.0), getattr(self, "opp2_shoot_bar", 0.0), "smooth_opp2_shoot_bar", is_3pt)

        # Check if a controller is connected to show dynamic button prompts
        controller_connected = False
        try:
            from src.controller import get_controller
            controller_connected = get_controller().connected
        except:
            pass

        if self.show_menu:
            if controller_connected:
                menu_text = self._font.render("Press A or START to start Basketball!", True, WHITE)
                controls_text = self._font.render("Left Stick to Move | Hold/Release X to Shoot | B to Block | A to Jump", True, (200, 200, 200))
            else:
                menu_text = self._font.render("Press SPACE to start Basketball!", True, WHITE)
                controls_text = self._font.render("WASD to move | Left Click hold to shoot | Right Click to block | Space to Jump", True, (200, 200, 200))
            
            bg_rect = menu_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 20)).inflate(40, 20)
            pygame.draw.rect(screen, (0, 0, 0, 200), bg_rect)
            bg_rect2 = controls_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30)).inflate(40, 20)
            pygame.draw.rect(screen, (0, 0, 0, 200), bg_rect2)
            
            screen.blit(menu_text, menu_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 20)))
            screen.blit(controls_text, controls_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30)))

        if self.waiting_for_dismiss:
            btn_prompt = "A Button" if controller_connected else "SPACE"
            end_text = self._font.render(self.end_message + f" (Press {btn_prompt})", True, WHITE)
            e_rect = end_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
            pygame.draw.rect(screen, (0, 0, 0, 200), e_rect.inflate(20, 10))
            screen.blit(end_text, e_rect)
