import pygame
import math
import random
from settings import SCREEN_WIDTH, SCREEN_HEIGHT, UI_ACCENT, WHITE, BLACK, KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, VT323_PATH

class BasketballGame:
    def __init__(self):
        self.active = False
        self.finished = False
        self.paused = False
        self._pause_sel = 0
        self.waiting_for_dismiss = False
        self.end_message = None
        self.show_menu = True

        self.player_score = 0
        self.opp_score = 0

        self.player_x = 200.0
        self.player_y = 500.0
        self.player_vy = 0.0
        self.opp_x = 1080.0
        self.opp_y = 500.0
        self.opp_vy = 0.0
        self.gravity = 1500.0
        self.jump_speed = -700.0
        self.move_speed = 300.0
        self.ground_y = 600.0

        self.ball_x = 640.0
        self.ball_y = 400.0
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.ball_radius = 12
        self.ball_held_by = None  # 'player' or 'opp' or None

        self.hoop_left = pygame.Rect(50, 350, 40, 10)
        self.hoop_right = pygame.Rect(1190, 350, 40, 10)

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

        self.possession = None

        self._font = None

    def start(self, player, opponent):
        self.player = player
        self.opponent = opponent
        self.reset()
        self.show_menu = True
        self.active = False
        pygame.font.init()
        self._font = pygame.font.Font(VT323_PATH, 32) if VT323_PATH else pygame.font.SysFont(None, 32)

    def reset(self):
        self.player_score = 0
        self.opp_score = 0
        self.player_x = 200.0
        self.player_y = self.ground_y
        self.player_vy = 0.0
        self.opp_x = 1080.0
        self.opp_y = self.ground_y
        self.opp_vy = 0.0
        
        self.ball_x = SCREEN_WIDTH // 2
        self.ball_y = 200.0
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.ball_held_by = None
        self.possession = None

        self.shooting = False
        self.shoot_bar = 0.0
        self.opp_shooting = False
        self.opp_shoot_bar = 0.0
        self.blocking = False
        self.block_timer = 0.0
        self.opp_blocking = False
        self.opp_block_timer = 0.0

        self.finished = False
        self.end_message = None
        self.waiting_for_dismiss = False

    def handle_input(self, event: pygame.event.Event):
        if self.paused:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.paused = False
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.paused = False
            return
            
        if event.type == pygame.KEYDOWN:
            if self.show_menu and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.show_menu = False
                self.active = True
            elif self.waiting_for_dismiss and event.key == pygame.K_SPACE:
                self.waiting_for_dismiss = False
                self.finished = True
        
        if self.active and not self.show_menu and not self.waiting_for_dismiss:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                if self.ball_held_by != 'player':
                    self.blocking = True
                    self.block_timer = 0.2
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.ball_held_by == 'player':
                    self.shooting = True
                    self.shoot_bar = 0.0
                    self.shoot_dir = 1
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.shooting and self.ball_held_by == 'player':
                    self._shoot_ball('player', self.shoot_bar)
                    self.shooting = False

    def handle_controller(self, controller):
        pass

    def _shoot_ball(self, shooter, power_bar):
        # power_bar is 0.0 to 1.0. Optimal is around 0.8.
        quality = 1.0 - abs(power_bar - 0.8) * 2.0  # 1.0 is perfect, <0 is bad
        
        self.ball_held_by = None
        
        if shooter == 'player':
            target_x = self.hoop_right.centerx
            target_y = self.hoop_right.centery
            start_x = self.player_x
            start_y = self.player_y - 40
        else:
            target_x = self.hoop_left.centerx
            target_y = self.hoop_left.centery
            start_x = self.opp_x
            start_y = self.opp_y - 40
            
        self.ball_x = start_x
        self.ball_y = start_y
        
        dx = target_x - start_x
        dy = target_y - start_y
        
        dist = math.hypot(dx, dy)
        time_to_target = 1.2
        
        vx = dx / time_to_target
        vy = (dy - 0.5 * self.gravity * time_to_target**2) / time_to_target
        
        # Add error based on quality
        if quality < 0.8:
            error_x = random.uniform(-100, 100) * (1.0 - quality)
            error_y = random.uniform(-100, 100) * (1.0 - quality)
            vx += error_x
            vy += error_y
            
        self.ball_vx = vx
        self.ball_vy = vy

    def update(self, dt: float):
        if self.show_menu or self.waiting_for_dismiss or not self.active:
            return None

        keys = pygame.key.get_pressed()
        
        # Player movement
        if keys[KEY_LEFT]:
            self.player_x -= self.move_speed * dt
        if keys[KEY_RIGHT]:
            self.player_x += self.move_speed * dt
        if keys[KEY_UP] and self.player_y >= self.ground_y:
            self.player_vy = self.jump_speed

        self.player_vy += self.gravity * dt
        self.player_y += self.player_vy * dt
        if self.player_y >= self.ground_y:
            self.player_y = self.ground_y
            self.player_vy = 0

        self.player_x = max(20, min(SCREEN_WIDTH - 20, self.player_x))

        # Opponent AI
        target_x = self.ball_x if self.ball_held_by is None else (self.hoop_left.centerx if self.ball_held_by == 'opp' else self.player_x - 100)
        
        if self.opp_x < target_x - 10:
            self.opp_x += self.move_speed * 0.8 * dt
        elif self.opp_x > target_x + 10:
            self.opp_x -= self.move_speed * 0.8 * dt

        self.opp_vy += self.gravity * dt
        self.opp_y += self.opp_vy * dt
        if self.opp_y >= self.ground_y:
            self.opp_y = self.ground_y
            self.opp_vy = 0
            
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
                    self._shoot_ball('opp', self.opp_shoot_bar)
                    self.opp_shooting = False
            
            # Opponent auto-block
            if not self.opp_blocking and self.ball_held_by is None and self.ball_vy > 0:
                # If ball is near opponent and player shot it
                if self.possession == 'player' and math.hypot(self.ball_x - self.opp_x, self.ball_y - self.opp_y) < 80:
                    if random.random() < 0.3:
                        self.opp_blocking = True
                        self.opp_block_timer = 0.2

        # Shooting bar logic
        if self.shooting:
            self.shoot_bar += self.shoot_dir * dt * 1.5
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
            self.ball_x = self.player_x + 20
            self.ball_y = self.player_y - 20
            self.ball_vx = 0
            self.ball_vy = 0
        elif self.ball_held_by == 'opp':
            self.ball_x = self.opp_x - 20
            self.ball_y = self.opp_y - 20
            self.ball_vx = 0
            self.ball_vy = 0
        else:
            self.ball_vy += self.gravity * dt
            self.ball_x += self.ball_vx * dt
            self.ball_y += self.ball_vy * dt

            # Bouncing
            if self.ball_y >= self.ground_y:
                self.ball_y = self.ground_y
                self.ball_vy *= -0.7
                self.ball_vx *= 0.9

            if self.ball_x <= 0 or self.ball_x >= SCREEN_WIDTH:
                self.ball_vx *= -0.8
                self.ball_x = max(0, min(SCREEN_WIDTH, self.ball_x))

            p_dist = math.hypot(self.ball_x - self.player_x, self.ball_y - self.player_y)
            o_dist = math.hypot(self.ball_x - self.opp_x, self.ball_y - self.opp_y)

            # Blocking logic
            if self.blocking and p_dist < 60 and self.ball_held_by is None:
                self.ball_vx *= -1.2
                self.ball_vy = -300
                self.blocking = False
                self.possession = None
            
            if self.opp_blocking and o_dist < 60 and self.ball_held_by is None:
                self.ball_vx *= -1.2
                self.ball_vy = -300
                self.opp_blocking = False
                self.possession = None

            # Catching
            if p_dist < 40 and self.ball_vy > 0 and self.possession != 'player':
                self.ball_held_by = 'player'
                self.possession = 'player'
            elif o_dist < 40 and self.ball_vy > 0 and self.possession != 'opp':
                self.ball_held_by = 'opp'
                self.possession = 'opp'

            # Scoring
            if self.hoop_right.collidepoint(self.ball_x, self.ball_y) and self.ball_vy > 0:
                self.player_score += 1
                self.reset_positions()
            elif self.hoop_left.collidepoint(self.ball_x, self.ball_y) and self.ball_vy > 0:
                self.opp_score += 1
                self.reset_positions()

        if self.player_score >= 5:
            self.end_message = "You Win!"
            self.waiting_for_dismiss = True
        elif self.opp_score >= 5:
            self.end_message = "Opponent Wins!"
            self.waiting_for_dismiss = True

        return None

    def reset_positions(self):
        self.player_x = 200.0
        self.player_y = self.ground_y
        self.opp_x = 1080.0
        self.opp_y = self.ground_y
        self.ball_x = SCREEN_WIDTH // 2
        self.ball_y = 200.0
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.ball_held_by = None
        self.possession = None
        self.shooting = False
        self.opp_shooting = False

    def draw(self, screen: pygame.Surface):
        screen.fill((40, 40, 50))
        
        # Ground
        pygame.draw.rect(screen, (100, 100, 100), (0, self.ground_y, SCREEN_WIDTH, SCREEN_HEIGHT - self.ground_y))
        
        # Hoops
        pygame.draw.rect(screen, (200, 50, 50), self.hoop_left)
        pygame.draw.rect(screen, (200, 50, 50), self.hoop_right)

        # Player & Opp
        if self.blocking:
            pygame.draw.rect(screen, (100, 200, 255), (self.player_x - 30, self.player_y - 90, 60, 100))
        else:
            pygame.draw.rect(screen, (50, 150, 250), (self.player_x - 20, self.player_y - 80, 40, 80))
            
        if self.opp_blocking:
            pygame.draw.rect(screen, (255, 150, 100), (self.opp_x - 30, self.opp_y - 90, 60, 100))
        else:
            pygame.draw.rect(screen, (250, 100, 50), (self.opp_x - 20, self.opp_y - 80, 40, 80))

        # Ball
        pygame.draw.circle(screen, (255, 140, 0), (int(self.ball_x), int(self.ball_y)), self.ball_radius)

        # Scores
        score_text = self._font.render(f"Player: {self.player_score}  |  Opp: {self.opp_score}", True, WHITE)
        screen.blit(score_text, (SCREEN_WIDTH // 2 - score_text.get_width() // 2, 20))

        # Shooting Bar
        if self.shooting:
            bar_w = 100
            bar_h = 10
            bar_x = self.player_x - bar_w // 2
            bar_y = self.player_y - 100
            pygame.draw.rect(screen, BLACK, (bar_x, bar_y, bar_w, bar_h))
            
            fill_w = int(bar_w * self.shoot_bar)
            color = (255, 0, 0)
            if 0.7 < self.shoot_bar < 0.9:
                color = (0, 255, 0)
            elif 0.5 < self.shoot_bar < 0.95:
                color = (255, 255, 0)
                
            pygame.draw.rect(screen, color, (bar_x, bar_y, fill_w, bar_h))
            pygame.draw.rect(screen, WHITE, (bar_x + int(bar_w * 0.8) - 2, bar_y - 2, 4, bar_h + 4))

        if self.show_menu:
            menu_text = self._font.render("Press SPACE to start Basketball!", True, WHITE)
            controls_text = self._font.render("Arrows to move | Click & release to shoot | SPACE to block", True, (200, 200, 200))
            screen.blit(menu_text, (SCREEN_WIDTH // 2 - menu_text.get_width() // 2, SCREEN_HEIGHT // 2 - 20))
            screen.blit(controls_text, (SCREEN_WIDTH // 2 - controls_text.get_width() // 2, SCREEN_HEIGHT // 2 + 40))

        if self.waiting_for_dismiss:
            end_text = self._font.render(self.end_message + " (Press SPACE)", True, WHITE)
            screen.blit(end_text, (SCREEN_WIDTH // 2 - end_text.get_width() // 2, SCREEN_HEIGHT // 2))


