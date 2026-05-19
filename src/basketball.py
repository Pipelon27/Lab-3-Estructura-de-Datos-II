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

        self.player_score = 0
        self.opp_score = 0
        
        self.reset_timer = 0.0
        self.swish_effect = None

        self.player_z = 0.0
        self.player_vz = 0.0
        self.opp_z = 0.0
        self.opp_vz = 0.0
        self.gravity = -1500.0
        self.jump_speed = 500.0

        self.ball_x = 900.0
        self.ball_y = 605.0
        self.ball_z = 200.0
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.ball_vz = 0.0
        self.ball_radius = 8
        self.ball_held_by = None  # 'player', 'opp', or None
        self.possession = None

        # Court & Physics Constants
        self.court_rect = pygame.Rect(490, 258, 1070, 694)
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
        
        self.blocking = False
        self.block_timer = 0.0
        self.opp_blocking = False
        self.opp_block_timer = 0.0
        
        self.opp_shooting = False
        self.opp_shoot_bar = 0.0
        self.opp_shoot_dir = 1
        self.opp_target_bar = 0.0

        self.last_shot_x = None
        self.last_shot_y = None
        self.last_shot_team = None
        
        self.player_shoot_anim = -1.0
        self.opp_shoot_anim = -1.0
        self.player_pending_shot = None
        self.opp_pending_shot = None

        self._font = None
        self.player = None
        self.opponent = None
        
        # Load custom ball sprite
        import os
        base_dir = os.path.dirname(os.path.dirname(__file__))
        ball_path = os.path.join(base_dir, "assets", "ball.png")
        if os.path.exists(ball_path):
            self.ball_img = pygame.image.load(ball_path).convert_alpha()
            self.ball_img = pygame.transform.scale(self.ball_img, (40, 40))
        else:
            self.ball_img = None

    def start(self, player, opponent, floor):
        self.player = player
        self.opponent = opponent
        self.floor = floor
        if self.floor:
            self.floor.hide_hoops = True
        # Temporarily disable NPC AI while playing basketball
        self.opponent.ai_enabled = False
        
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

        self.ball_x = 900.0
        self.ball_y = 605.0
        self.ball_z = 200.0
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.ball_vz = 0.0
        
        self.ball_held_by = None
        self.possession = None

        self.shooting = False
        self.opp_shooting = False
        self.blocking = False
        self.opp_blocking = False

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
                if event.button == 1: # Left Click -> Shoot
                    if self.ball_held_by == 'player':
                        self.shooting = True
                        self.shoot_bar = 0.0
                        self.shoot_dir = 1
                elif event.button == 3: # Right Click -> Block/Steal
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

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.shooting and self.ball_held_by == 'player':
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

    def _shoot_ball(self, shooter, power_bar):
        self.last_shot_team = shooter
        
        target_quality = 0.8
        if shooter == 'player':
            self.last_shot_x = self.player.rect.centerx
            self.last_shot_y = self.player.rect.centery
            target_x, target_y = self.right_rim
            dist = math.hypot(self.last_shot_x - target_x, self.last_shot_y - target_y)
            is_3pt = dist > self.three_point_radius
            spread = 4.0 if is_3pt else 2.0
            quality = 1.0 - abs(power_bar - target_quality) * spread
            start_x = self.player.rect.centerx
            start_y = self.player.rect.centery
            start_z = self.player_z + 40
        else:
            self.last_shot_x = self.opponent.rect.centerx
            self.last_shot_y = self.opponent.rect.centery
            target_x, target_y = self.left_rim
            dist = math.hypot(self.last_shot_x - target_x, self.last_shot_y - target_y)
            is_3pt = dist > self.three_point_radius
            quality = 1.0 - abs(power_bar - target_quality) * 2.0
            start_x = self.opponent.rect.centerx
            start_y = self.opponent.rect.centery
            start_z = self.opp_z + 40
            
        self.ball_held_by = None
        self.ball_x = start_x
        self.ball_y = start_y
        self.ball_z = start_z
        
        dx = target_x - start_x
        dy = target_y - start_y
        
        time_to_target = 1.1
        
        vx = dx / time_to_target
        vy = dy / time_to_target
        vz = (self.hoop_z - start_z - 0.5 * self.gravity * time_to_target**2) / time_to_target
        
        # Add error based on quality
        if quality < 0.8:
            error_x = random.uniform(-100, 100) * (1.0 - quality)
            error_y = random.uniform(-100, 100) * (1.0 - quality)
            vx += error_x
            vy += error_y
            
        self.ball_vx = vx
        self.ball_vy = vy
        self.ball_vz = vz

    def update(self, dt: float):
        if not self.active or self.show_menu or self.waiting_for_dismiss:
            return {"status": "running"}
            
        if self.reset_timer > 0:
            self.reset_timer -= dt
            if self.reset_timer <= 0:
                self.reset_positions()
                
        keys = pygame.key.get_pressed()
        
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

        # Opponent AI (Top-Down Chase)
        target_x = self.ball_x
        target_y = self.ball_y
        if self.ball_held_by == 'opp':
            target_x, target_y = self.left_rim
        elif self.ball_held_by == 'player':
            # Defend the player
            target_x = self.player.rect.centerx - 40
            target_y = self.player.rect.centery
            
        o_dx = target_x - self.opponent.rect.centerx
        o_dy = target_y - self.opponent.rect.centery
        dist = math.hypot(o_dx, o_dy)
        
        speed = 200.0 * dt
        if dist > 5:
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

        # Restrict Opponent to Court
        self.opponent.rect.clamp_ip(self.court_rect)

        # Opponent Z-physics
        self.opp_vz += self.gravity * dt
        self.opp_z += self.opp_vz * dt
        if self.opp_z <= 0:
            self.opp_z = 0
            self.opp_vz = 0
            
        # Opponent AI Shooting/Blocking
        if self.ball_held_by == 'opp':
            if not self.opp_shooting:
                if random.random() < 0.01:
                    self.opp_shooting = True
                    self.opp_shoot_bar = 0.0
                    self.opp_shoot_dir = 1
                    self.opp_target_bar = random.uniform(0.7, 0.9)
            else:
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
            
            if not self.opp_blocking and self.ball_held_by == 'player' and self.shooting:
                if math.hypot(self.player.rect.centerx - self.opponent.rect.centerx, 
                              self.player.rect.centery - self.opponent.rect.centery) < 60:
                    if random.random() < 0.02:
                        self.opp_blocking = True
                        self.opp_block_timer = 0.3
                        self.shooting = False
                        self.ball_held_by = 'opp'
                        self.possession = 'opp'

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

        if self.block_timer > 0:
            self.block_timer -= dt
            if self.block_timer <= 0:
                self.blocking = False
                
        if self.opp_block_timer > 0:
            self.opp_block_timer -= dt
            if self.opp_block_timer <= 0:
                self.opp_blocking = False

        # Ball physics
        if self.ball_held_by == 'player':
            self.ball_x = self.player.rect.centerx
            self.ball_y = self.player.rect.centery
            self.ball_z = self.player_z + 40
            self.ball_vx = 0
            self.ball_vy = 0
            self.ball_vz = 0
        elif self.ball_held_by == 'opp':
            self.ball_x = self.opponent.rect.centerx
            self.ball_y = self.opponent.rect.centery
            self.ball_z = self.opp_z + 40
            self.ball_vx = 0
            self.ball_vy = 0
            self.ball_vz = 0
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
            
            if self.opp_blocking and o_dist < 50 and self.ball_z < self.opp_z + 80 and self.ball_held_by is None:
                self.ball_vx *= -1.2
                self.ball_vy *= -1.2
                self.ball_vz = 300
                self.opp_blocking = False
                self.possession = None

            # Catching (only if ball is low or player jumps)
            if p_dist < 40 and abs(self.ball_z - self.player_z) < 50 and self.possession != 'player':
                self.ball_held_by = 'player'
                self.possession = 'player'
            elif o_dist < 40 and abs(self.ball_z - self.opp_z) < 50 and self.possession != 'opp':
                self.ball_held_by = 'opp'
                self.possession = 'opp'

            # Scoring (Check 2.5D intersection with hoop rim area)
            # We assume the ball falls THROUGH the hoop (vz < 0) near the rim coordinates
            if self.ball_vz < 0 and abs(self.ball_z - self.hoop_z) < 20:
                dist_right = math.hypot(self.ball_x - self.right_rim[0], self.ball_y - self.right_rim[1])
                dist_left = math.hypot(self.ball_x - self.left_rim[0], self.ball_y - self.left_rim[1])
                
                if dist_right < 20 and self.reset_timer <= 0:
                    pts = 3 if (self.last_shot_team == 'player' and math.hypot(self.last_shot_x - self.right_rim[0], self.last_shot_y - self.right_rim[1]) > self.three_point_radius) else 2
                    self.player_score += pts
                    self.reset_timer = 1.0 # Wait 1 second before resetting
                    self.swish_effect = {
                        "x": self.right_rim[0],
                        "y": self.right_rim[1],
                        "text": "SWISH!" if pts == 3 else "2 PTS!",
                        "text_y": float(self.right_rim[1] - 40),
                        "color": (255, 215, 0) if pts == 3 else (100, 255, 100),
                        "particles": [{"x": self.right_rim[0] + random.uniform(-15, 15), "y": self.right_rim[1] - 30, "vx": random.uniform(-40, 40), "vy": random.uniform(80, 200), "life": 0.8} for _ in range(18)],
                        "timer": 1.0
                    }
                elif dist_left < 20 and self.reset_timer <= 0:
                    pts = 3 if (self.last_shot_team == 'opp' and math.hypot(self.last_shot_x - self.left_rim[0], self.last_shot_y - self.left_rim[1]) > self.three_point_radius) else 2
                    self.opp_score += pts
                    self.reset_timer = 1.0
                    self.swish_effect = {
                        "x": self.left_rim[0],
                        "y": self.left_rim[1],
                        "text": "SWISH!" if pts == 3 else "2 PTS!",
                        "text_y": float(self.left_rim[1] - 40),
                        "color": (255, 69, 0),
                        "particles": [{"x": self.left_rim[0] + random.uniform(-15, 15), "y": self.left_rim[1] - 30, "vx": random.uniform(-40, 40), "vy": random.uniform(80, 200), "life": 0.8} for _ in range(18)],
                        "timer": 1.0
                    }

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

        if self.player_score >= 10:
            self.end_message = "You Win!"
            self.waiting_for_dismiss = True
        elif self.opp_score >= 10:
            self.end_message = "Opponent Wins!"
            self.waiting_for_dismiss = True

        return None

    def draw(self, screen: pygame.Surface, camera):
        # We don't fill the background. The actual map is drawn behind this!
        
        # 1. Draw Shadows (at ground level, z=0)
        shadow_color = (0, 0, 0, 80)
        shadow_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        
        px, py = camera.apply_pos(self.player.rect.centerx, self.player.rect.centery)
        pygame.draw.ellipse(shadow_surf, shadow_color, (px - 15, py - 5, 30, 10))
        
        ox, oy = camera.apply_pos(self.opponent.rect.centerx, self.opponent.rect.centery)
        pygame.draw.ellipse(shadow_surf, shadow_color, (ox - 15, oy - 5, 30, 10))
        
        bx, by = camera.apply_pos(self.ball_x, self.ball_y)
        ball_shadow_w = max(4, 16 - (self.ball_z * 0.05))
        pygame.draw.ellipse(shadow_surf, shadow_color, (bx - ball_shadow_w/2, by - ball_shadow_w/4, ball_shadow_w, ball_shadow_w/2))
        
        screen.blit(shadow_surf, (0, 0))

        # 2. Draw Entities with Z-offset applied to their screen rendering!
        # Temporarily modify centery to simulate Z-height
        old_py = self.player.rect.centery
        old_oy = self.opponent.rect.centery
        
        self.player.rect.centery = old_py - int(self.player_z)
        self.opponent.rect.centery = old_oy - int(self.opp_z)
        
        def draw_scaled_player():
            if self.player.image:
                scaled = pygame.transform.scale_by(self.player.image, 1.5)
                rect = scaled.get_rect(midbottom=camera.apply(self.player).midbottom)
                screen.blit(scaled, rect)
                
        def draw_scaled_opp():
            if self.opponent.image:
                scaled = pygame.transform.scale_by(self.opponent.image, 1.5)
                rect = scaled.get_rect(midbottom=camera.apply(self.opponent).midbottom)
                screen.blit(scaled, rect)

        def draw_left_hoop():
            if hasattr(self, 'floor') and self.floor and hasattr(self.floor, '_left_hoop_surface') and self.floor._left_hoop_surface:
                rect = self.floor._left_hoop_surface.get_rect(topleft=(516, 510))
                screen.blit(self.floor._left_hoop_surface, camera.apply_rect(rect))

        def draw_right_hoop():
            if hasattr(self, 'floor') and self.floor and hasattr(self.floor, '_right_hoop_surface') and self.floor._right_hoop_surface:
                rect = self.floor._right_hoop_surface.get_rect(topleft=(1417, 510))
                screen.blit(self.floor._right_hoop_surface, camera.apply_rect(rect))
        
        def draw_ball():
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
            
        # Draw block aura effect
        if self.blocking:
            pygame.draw.circle(screen, (100, 200, 255, 128), camera.apply_pos(self.player.rect.centerx, self.player.rect.centery), 30, 4)
        if self.opp_blocking:
            pygame.draw.circle(screen, (255, 150, 100, 128), camera.apply_pos(self.opponent.rect.centerx, self.opponent.rect.centery), 30, 4)

        # Restore original Y coordinates so physics aren't broken!
        self.player.rect.centery = old_py
        self.opponent.rect.centery = old_oy

        # 3. Draw UI
        score_text = self._font.render(f"Player: {self.player_score}  |  Opp: {self.opp_score}", True, WHITE)
        # Draw background rect for score for readability over world
        s_rect = score_text.get_rect(center=(SCREEN_WIDTH // 2, 30))
        pygame.draw.rect(screen, (0, 0, 0, 150), s_rect.inflate(20, 10))
        screen.blit(score_text, s_rect)

        # Opponent Shooting Bar
        if self.opp_shooting:
            bar_w = 60
            bar_h = 8
            bx, by = camera.apply_pos(self.opponent.rect.centerx, old_oy - self.opp_z - 80)
            bar_x = bx - bar_w // 2
            bar_y = by
            pygame.draw.rect(screen, BLACK, (bar_x, bar_y, bar_w, bar_h))
            
            fill_w = int(bar_w * self.opp_shoot_bar)
            color = (255, 0, 0)
            if 0.7 < self.opp_shoot_bar < 0.9:
                color = (0, 255, 0)
            elif 0.5 < self.opp_shoot_bar < 0.95:
                color = (255, 255, 0)
                
            pygame.draw.rect(screen, color, (bar_x, bar_y, fill_w, bar_h))
            pygame.draw.rect(screen, WHITE, (bar_x + int(bar_w * 0.8) - 2, bar_y - 2, 4, bar_h + 4))

        # Shooting Bar
        if self.shooting:
            dist = math.hypot(self.player.rect.centerx - self.right_rim[0], self.player.rect.centery - self.right_rim[1])
            is_3pt = dist > self.three_point_radius
            
            bar_w = 60
            bar_h = 8
            bx, by = camera.apply_pos(self.player.rect.centerx, old_py - self.player_z - 80)
            bar_x = bx - bar_w // 2
            bar_y = by
            pygame.draw.rect(screen, BLACK, (bar_x, bar_y, bar_w, bar_h))
            
            fill_w = int(bar_w * self.shoot_bar)
            color = (255, 0, 0)
            
            green_min, green_max = (0.75, 0.85) if is_3pt else (0.7, 0.9)
            if green_min < self.shoot_bar < green_max:
                color = (0, 255, 0)
            elif 0.5 < self.shoot_bar < 0.95:
                color = (255, 255, 0)
                
            pygame.draw.rect(screen, color, (bar_x, bar_y, fill_w, bar_h))
            pygame.draw.rect(screen, WHITE, (bar_x + int(bar_w * 0.8) - 2, bar_y - 2, 4, bar_h + 4))

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
