"""
src/pingpong.py — Simple Pong minigame where cursor is paddle.
First to 10 points wins. On player miss Oscar taunts.
"""
from __future__ import annotations

import pygame
import math
from settings import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    UI_ACCENT,
    WHITE,
    UI_TEXT_DIM,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_UP,
    KEY_DOWN,
    KEY_DASH,
    DASH_SPEED,
    DASH_DURATION,
)


class PingPongGame:
    def __init__(self):
        self.active = False
        self.player = None  # NPC instance for opponent
        self.ball = pygame.Rect(SCREEN_WIDTH // 2 - 8, SCREEN_HEIGHT // 2 - 8, 16, 16)
        # tuned ball speed (faster arcade feel)
        self.ball_vel = [420.0, 240.0]
        self.player_score = 0
        self.opponent_score = 0
        self.score_limit = 10
        self.taunts = [
            "Keep missing, everyone's watching",
            "You're making this too easy",
            "Too slow, new kid!",
        ]
        self._taunt_index = 0
        self._taunt_msg = ""
        self._taunt_timer = 0.0
        # paddles — convert to top-down (left/right) layout
        self.player_w = 18
        self.player_h = 120
        self.opp_w = 18
        self.opp_h = 120
        # will be positioned relative to court in reset()
        self.opp_x = 0
        self.opp_y = 0
        # opponent AI speed (tuned faster for arcade)
        self.opp_speed = 540
        # player position (float for smooth movement)
        self.player_x = 0.0
        self.player_y = 0.0
        # dash state
        self.dash_timer = 0
        self.dash_active = False
        # who last touched the ball: 'player' or 'opponent'
        self.last_touch = None
        # Super Shot system
        self.super_cooldown = 5.0
        self.super_ready = False
        # message shown when player presses Super Shot incorrectly
        self.super_msg = ""
        self.super_msg_timer = 0.0
        self.super_prompt_timer = 0.0
        self.super_armed = False
        self.super_effect_timer = 0.0
        self.ball_color = WHITE
        # short visual/speed dash effect on ball when hit by a dashing player
        self.ball_dash_timer = 0.0
        # Per-point base speed and per-hit speed multiplier (faster arcade)
        # start slightly faster and ramp up more slowly
        self.base_vx = 420.0
        self.base_vy = 260.0
        # multiplier applied after each paddle hit (slower ramp)
        self.hit_speed_mult = 1.12
        # ball dash multiplier & timer (visual + movement boost)
        self.ball_dash_timer = 0.0
        self.ball_dash_multiplier = 1.0
        # Oscar duplicate-ball ability
        self.opp_dup_cooldown = 3.0
        self.opp_dup_timer = 3.0
        self.duplicate = None  # dict with keys: rect, vel
        self.dupe_color = (180, 180, 200, 180)
        # per-point flag to ensure we spawn duplicate once per opponent first-hit
        self.dup_spawned_this_point = False
        # court margins for a smaller court (use via self.court_rect())
        self._court_margin_left = 120
        self._court_margin_top = 80
        self._court_margin_right = 120
        self._court_margin_bottom = 140
        # countdown state for starting the match
        self.countdown_active = False
        self.countdown_timer = 0.0
        self.countdown_go_time = 0.8

    def start(self, player, opponent):
        self.player = player
        self.opponent = opponent
        self.reset()
        # show start/menu first with controls and Start button
        self.show_menu = True
        self.active = False
        self.end_message = None
        self.waiting_for_dismiss = False
        self.finished = False
        self.countdown_active = False
        self.countdown_timer = 0.0

    def court_rect(self) -> pygame.Rect:
        return pygame.Rect(
            self._court_margin_left,
            self._court_margin_top,
            SCREEN_WIDTH - (self._court_margin_left + self._court_margin_right),
            SCREEN_HEIGHT - (self._court_margin_top + self._court_margin_bottom),
        )

    def reset(self):
        self.ball.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        # reset to per-point base speed (starts slow each point)
        self.ball_vel = [self.base_vx, self.base_vy]
        self.player_score = 0
        self.opponent_score = 0
        self._taunt_index = 0
        self._taunt_msg = ""
        self._taunt_timer = 0.0
        self.last_touch = None
        self.end_message = None
        self.waiting_for_dismiss = False
        self.finished = False
        # reset duplicate state for the new point
        self.duplicate = None
        self.dup_spawned_this_point = False
        # Reposition paddles for a top-down view
        court = self.court_rect()
        # place characters outside the court edges (left and right)
        self.player_x = court.left - 72
        self.player_y = court.top + court.h // 2
        self.opp_x = court.right + 40
        self.opp_y = court.top + court.h // 2
        self.dash_timer = 0
        self.dash_active = False
        self.show_menu = getattr(self, 'show_menu', True)

    def handle_input(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN:
            # Super Shot activation — only if pressing F exactly when ball collides with player's paddle
            if event.key == pygame.K_f and self.super_ready:
                court = self.court_rect()
                # construct player paddle rect at court left edge (same as in update)
                player_rect_now = pygame.Rect(court.left, int(self.player_y - self.player_h // 2), self.player_w, self.player_h)
                # must be colliding right now to allow Super Shot
                if self.ball.colliderect(player_rect_now) and self.ball_vel[0] < 0:
                    # perform Super Shot immediately
                    opp_cx = court.right - (self.opp_w // 2)
                    left_dist = abs(opp_cx - court.left)
                    right_dist = abs(opp_cx - court.right)
                    target_x = court.left + 12 if left_dist > right_dist else court.right - 12
                    target_y = court.top + 8
                    vx = target_x - self.ball.centerx
                    vy = target_y - self.ball.centery
                    mag = math.hypot(vx, vy) or 1.0
                    speed = 700.0
                    self.ball_vel[0] = (vx / mag) * speed
                    self.ball_vel[1] = (vy / mag) * speed
                    self.ball_color = (220, 40, 40)
                    self.super_effect_timer = 0.8
                    self.super_ready = False
                    self.super_armed = False
                    self.super_prompt_timer = 0.0
                    self.super_cooldown = 5.0
                else:
                    # incorrect timing
                    self.super_msg = "Remember to hit the ball correctly to activate the super shot"
                    self.super_msg_timer = 2.2
            elif getattr(self, 'waiting_for_dismiss', False):
                # any key dismisses the end screen
                self.waiting_for_dismiss = False
                self.finished = True
            elif event.key == pygame.K_ESCAPE:
                self.active = False
        # ignore mouse clicks for starting — require Enter/Space to start
        if event.type == pygame.MOUSEBUTTONDOWN and getattr(self, 'show_menu', False):
            pass
        if event.type == pygame.KEYDOWN and getattr(self, 'show_menu', False):
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                # begin countdown 3..2..1 then activate
                self.show_menu = False
                self.countdown_active = True
                self.countdown_timer = 3.0
                self.countdown_go_shown = False

    def update(self, dt: float) -> str | None:
        # handle countdown before match starts
        if self.countdown_active:
            self.countdown_timer -= dt
            # when timer crosses zero, show "Let's Go!" briefly then activate
            if self.countdown_timer <= 0 and not getattr(self, 'countdown_go_shown', False):
                self.countdown_go_shown = True
                self.countdown_timer = self.countdown_go_time
            elif getattr(self, 'countdown_go_shown', False) and self.countdown_timer <= 0:
                self.countdown_active = False
                self.countdown_go_shown = False
                self.active = True
            return None
        if not self.active:
            return None
        # ball dash multiplier handling
        if self.ball_dash_timer > 0:
            self.ball_dash_timer -= dt
            self.ball_dash_multiplier = 1.35
            if self.ball_dash_timer <= 0:
                self.ball_dash_multiplier = 1.0
                self.ball_dash_timer = 0
        # move ball (apply dash multiplier)
        self.ball.x += int(self.ball_vel[0] * self.ball_dash_multiplier * dt)
        self.ball.y += int(self.ball_vel[1] * self.ball_dash_multiplier * dt)

        # court rectangle (smaller)
        court = self.court_rect()

        # player movement via WASD + dash (tuned a bit faster for arcade feel)
        keys = pygame.key.get_pressed()
        move_speed = 280.0
        if keys[KEY_DASH] and self.dash_timer <= 0:
            self.dash_active = True
            self.dash_timer = DASH_DURATION / 60.0  # convert frames to seconds approx
        if self.dash_active:
            move_speed *= 2.0
            self.dash_timer -= dt
            if self.dash_timer <= 0:
                self.dash_active = False
                self.dash_timer = 0
        dx = 0.0
        dy = 0.0
        if keys[KEY_LEFT]:
            dx -= 1.0
        if keys[KEY_RIGHT]:
            dx += 1.0
        if keys[KEY_UP]:
            dy -= 1.0
        if keys[KEY_DOWN]:
            dy += 1.0
        if dx or dy:
            mag = math.hypot(dx, dy) or 1.0
            self.player_x += (dx / mag) * move_speed * dt
            self.player_y += (dy / mag) * move_speed * dt
        # prevent player from entering the court: if player center is inside court, push to nearest outside edge
        if court.collidepoint(self.player_x, self.player_y):
            left_dist = abs(self.player_x - court.left)
            right_dist = abs(self.player_x - court.right)
            top_dist = abs(self.player_y - court.top)
            bottom_dist = abs(self.player_y - court.bottom)
            md = min(left_dist, right_dist, top_dist, bottom_dist)
            if md == left_dist:
                self.player_x = court.left - 72
            elif md == right_dist:
                self.player_x = court.right + 72
            elif md == top_dist:
                self.player_y = court.top - 72
            else:
                self.player_y = court.bottom + 72
        # keep player within a rim area around the court (stay near edges, outside the green)
        rim = 96
        # left rim
        if self.player_x < court.left:
            self.player_x = max(court.left - rim, min(court.left - 12, self.player_x))
            self.player_y = max(court.top - rim, min(court.bottom + rim, self.player_y))
        # right rim
        elif self.player_x > court.right:
            self.player_x = max(court.right + 12, min(court.right + rim, self.player_x))
            self.player_y = max(court.top - rim, min(court.bottom + rim, self.player_y))
        else:
            # above or below the court
            if self.player_y < court.top:
                self.player_y = max(court.top - rim, min(court.top - 12, self.player_y))
                self.player_x = max(court.left - rim, min(court.right + rim, self.player_x))
            elif self.player_y > court.bottom:
                self.player_y = max(court.bottom + 12, min(court.bottom + rim, self.player_y))
                self.player_x = max(court.left - rim, min(court.right + rim, self.player_x))
        # paddle rects are positioned at the court edges (paddles interact with the ball inside court)
        player_rect = pygame.Rect(court.left, int(self.player_y - self.player_h // 2), self.player_w, self.player_h)

        # opponent AI: follow ball vertically (paddle lives at right court edge)
        target_y = self.ball.centery
        if target_y < self.opp_y:
            self.opp_y -= int(self.opp_speed * dt)
        else:
            self.opp_y += int(self.opp_speed * dt)
        # clamp opponent paddle center inside court vertical span
        half_h = self.opp_h // 2
        self.opp_y = max(court.top + half_h, min(court.bottom - half_h, self.opp_y))
        opp_rect = pygame.Rect(court.right - self.opp_w, int(self.opp_y - half_h), self.opp_w, self.opp_h)

        # paddle collisions
        # collision for left/right paddles: reflect horizontally when hit
        if self.ball.colliderect(player_rect) and self.ball_vel[0] < 0:
            # If Super Shot armed, apply powerful effect on contact
            if self.super_armed:
                # shorter, less extreme Super Shot: lasts until next point
                self.super_effect_timer = 0.6
                self.ball_color = (220, 40, 40)  # red
                mult = 2.0
                offset = (self.ball.centerx - player_rect.centerx) / (player_rect.width / 2)
                self.ball_vel[0] = (self.ball_vel[0] + offset * 80) * mult if offset else self.ball_vel[0] * mult
                self.ball_vel[1] = -abs(self.ball_vel[1]) * mult
                self.super_armed = False
            else:
                # reflect to right
                self.ball_vel[0] = abs(self.ball_vel[0])
                offset = (self.ball.centery - player_rect.centery) / (player_rect.height / 2)
                self.ball_vel[1] += offset * 120
                # apply dash effect if player was dashing at the moment of hit
                if self.dash_active:
                    self.ball_vel[0] *= 1.6
                    self.ball_vel[1] *= 1.6
                    self.ball_dash_timer = 0.35
                    self.ball_color = (120, 200, 255)
                # increase speed after each hit
                self.ball_vel[0] *= self.hit_speed_mult
                self.ball_vel[1] *= self.hit_speed_mult
            self.last_touch = 'player'
        if self.ball.colliderect(opp_rect) and self.ball_vel[0] > 0:
            # reflect to left
            self.ball_vel[0] = -abs(self.ball_vel[0])
            offset = (self.ball.centery - (opp_rect.centery)) / (opp_rect.height / 2)
            self.ball_vel[1] += offset * 80
            # increase speed after each hit
            self.ball_vel[0] *= self.hit_speed_mult
            self.ball_vel[1] *= self.hit_speed_mult
            self.last_touch = 'opponent'
            # Spawn duplicate immediately from Oscar's paddle on his first hit this point
            # Only spawn duplicate on even rounds (round numbering starts at 1)
            total_points = self.player_score + self.opponent_score
            # even round means total_points % 2 == 1 (because total_points = round-1)
            if not self.duplicate and not self.dup_spawned_this_point and (total_points % 2 == 1):
                dupe_rect = pygame.Rect(0, 0, self.ball.width, self.ball.height)
                dupe_rect.centerx = opp_rect.centerx + opp_rect.width // 2 + 4
                dupe_rect.centery = opp_rect.centery
                # aim dupe towards player's paddle center
                px = player_rect.centerx
                py = player_rect.centery
                vx = px - dupe_rect.centerx
                vy = py - dupe_rect.centery
                mag = math.hypot(vx, vy) or 1.0
                main_speed = math.hypot(self.ball_vel[0], self.ball_vel[1]) or 1.0
                dupe_vx = (vx / mag) * main_speed
                dupe_vy = (vy / mag) * main_speed
                # if too similar to main ball, rotate a bit
                dmag = math.hypot(dupe_vx, dupe_vy) or 1.0
                mvx = self.ball_vel[0] / (math.hypot(self.ball_vel[0], self.ball_vel[1]) or 1.0)
                mvy = self.ball_vel[1] / (math.hypot(self.ball_vel[0], self.ball_vel[1]) or 1.0)
                dvx = dupe_vx / dmag
                dvy = dupe_vy / dmag
                dot = dvx * mvx + dvy * mvy
                if abs(dot) > 0.9:
                    angle = math.radians(25)
                    cos_a = math.cos(angle)
                    sin_a = math.sin(angle)
                    rvx = dvx * cos_a - dvy * sin_a
                    rvy = dvx * sin_a + dvy * cos_a
                    dupe_vx = rvx * dmag
                    dupe_vy = rvy * dmag
                self.duplicate = {"rect": dupe_rect, "vel": [dupe_vx, dupe_vy]}
                self.dup_spawned_this_point = True

        # Side/top/bottom walls reflect
        if self.ball.top <= court.top:
            self.ball.top = court.top
            self.ball_vel[1] = abs(self.ball_vel[1])
        if self.ball.bottom >= court.bottom:
            self.ball.bottom = court.bottom
            self.ball_vel[1] = -abs(self.ball_vel[1])

        # Opponent duplicate-ball timer still reduces but spawn now only from opponent paddle
        self.opp_dup_timer -= dt
        if self.opp_dup_timer <= 0:
            self.opp_dup_timer = 0

        # update duplicate if present
        if self.duplicate:
            d = self.duplicate
            # keep duplicate's speed magnitude equal to main ball's speed
            main_speed = math.hypot(self.ball_vel[0], self.ball_vel[1]) or 1.0
            dvx, dvy = d["vel"][0], d["vel"][1]
            dmag = math.hypot(dvx, dvy) or 1.0
            d["vel"][0] = (dvx / dmag) * main_speed
            d["vel"][1] = (dvy / dmag) * main_speed
            d["rect"].x += int(d["vel"][0] * dt)
            d["rect"].y += int(d["vel"][1] * dt)
            # reflect on side walls
            if d["rect"].left <= court.left:
                d["rect"].left = court.left
                d["vel"][0] = abs(d["vel"][0])
            if d["rect"].right >= court.right:
                d["rect"].right = court.right
                d["vel"][0] = -abs(d["vel"][0])
            # if duplicate crosses top or bottom, simply remove it (no score)
            if d["rect"].top <= court.top or d["rect"].bottom >= court.bottom:
                self.duplicate = None
            else:
                # if player touches the duplicate, remove it (decoy)
                if d["rect"].colliderect(player_rect):
                    self.duplicate = None

        # Scoring only when the ball fully exits the screen (more arcade feel)
        scored = False
        if self.ball.right < 0:
            scored = True
            scorer_side = 'left'
        elif self.ball.left > SCREEN_WIDTH:
            scored = True
            scorer_side = 'right'

        if scored:
            if scorer_side == 'right':
                # player scored (ball crossed opponent side)
                self.player_score += 1
            else:
                # opponent scored
                self.opponent_score += 1
                # opponent scored — taunt Oscar
                self._taunt_msg = self.taunts[self._taunt_index % len(self.taunts)]
                self._taunt_index += 1
                self._taunt_timer = 2.0
            # reset ball near center but bias slightly toward last scorer's side
            self.ball.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
            # initial velocity aimed away from the scorer
            if scorer_side == 'right':
                # send ball toward opponent
                self.ball_vel[0] = abs(self.base_vx)
            else:
                self.ball_vel[0] = -abs(self.base_vx)
            # small vertical randomness
            self.ball_vel[1] = 0.0
            # Reset Super Shot when a point is scored: effect lasts only for that point
            self.super_armed = False
            self.super_ready = False
            self.super_prompt_timer = 0.0
            self.super_effect_timer = 0.0
            self.ball_color = WHITE
            # restart cooldown
            self.super_cooldown = 5.0

        if self._taunt_timer > 0:
            self._taunt_timer -= dt
            if self._taunt_timer <= 0:
                self._taunt_msg = ""

        # Super Shot incorrect-press message timer
        if self.super_msg_timer > 0:
            self.super_msg_timer -= dt
            if self.super_msg_timer <= 0:
                self.super_msg = ""

        # ball dash visual timer
        if self.ball_dash_timer > 0:
            self.ball_dash_timer -= dt
            if self.ball_dash_timer <= 0:
                self.ball_dash_timer = 0
                self.ball_color = WHITE

        # Super Shot cooldown/timer handling
        if not self.super_ready:
            self.super_cooldown -= dt
            if self.super_cooldown <= 0:
                self.super_ready = True

        # Super effect timer decrement
        if self.super_effect_timer > 0:
            self.super_effect_timer -= dt
            if self.super_effect_timer <= 0:
                self.super_effect_timer = 0
                self.ball_color = WHITE

        if self.player_score >= self.score_limit:
            self.active = False
            return "win"
        if self.opponent_score >= self.score_limit:
            self.active = False
            return "lose"

        return None

    def draw(self, screen: pygame.Surface):
        # Allow drawing the end screen, menu, or countdown even when `active` is False
        if not self.active and not getattr(self, 'waiting_for_dismiss', False) and not getattr(self, 'show_menu', False) and not getattr(self, 'countdown_active', False):
            return
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        court = self.court_rect()
        if getattr(self, 'show_menu', False):
            # show only court borders while in the controls/menu UI
            border_color = (30, 30, 40)
            pygame.draw.rect(screen, border_color, (court.left - 8, court.top - 8, court.width + 16, court.height + 16), 6, border_radius=6)
            # small corner posts for style
            post_w = 12
            pygame.draw.rect(screen, UI_ACCENT, (court.left - 20, court.top - 20, post_w, post_w))
            pygame.draw.rect(screen, UI_ACCENT, (court.right + 8, court.top - 20, post_w, post_w))
            pygame.draw.rect(screen, UI_ACCENT, (court.left - 20, court.bottom + 8, post_w, post_w))
            pygame.draw.rect(screen, UI_ACCENT, (court.right + 8, court.bottom + 8, post_w, post_w))
            # menu box (separate interface)
            box_w = 560
            box_h = 320
            bx = (SCREEN_WIDTH - box_w) // 2
            by = (SCREEN_HEIGHT - box_h) // 2
            pygame.draw.rect(screen, (18, 18, 26), (bx, by, box_w, box_h), border_radius=8)
            pygame.draw.rect(screen, UI_ACCENT, (bx, by, box_w, box_h), 3, border_radius=8)
            title_font = pygame.font.SysFont("arial", 48, bold=True)
            title = title_font.render("PING PONG ARCADE", True, UI_ACCENT)
            screen.blit(title, title.get_rect(center=(SCREEN_WIDTH//2, by + 48)))
            # controls shown inside the menu box
            small = pygame.font.SysFont("arial", 22)
            controls = ["Controles:", "WASD - Mover (moverte alrededor de la cancha)", "SHIFT - Dash", "F - Super Shot (debe golpear la pelota)", "ENTER / Click - Start"]
            for i, line in enumerate(controls):
                surf = small.render(line, True, WHITE)
                screen.blit(surf, (bx + 36, by + 110 + i*34))
            # hint to start (use keyboard)
            hint_font = pygame.font.SysFont("arial", 20, bold=True)
            hint = "Press Enter to Start"
            screen.blit(hint_font.render(hint, True, UI_ACCENT), (bx + 36, by + box_h - 56))
            return
        # draw countdown overlay if active
        if getattr(self, 'countdown_active', False):
            # draw dim overlay and big number
            ctimer = max(0.0, self.countdown_timer)
            if getattr(self, 'countdown_go_shown', False):
                txt = "Let's Go!"
                font = pygame.font.SysFont("arial", 64, bold=True)
                surf = font.render(txt, True, UI_ACCENT)
                screen.blit(surf, surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2)))
            else:
                num = int(math.ceil(ctimer)) if ctimer > 0 else 1
                font = pygame.font.SysFont("arial", 128, bold=True)
                surf = font.render(str(num), True, UI_ACCENT)
                screen.blit(surf, surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2)))
            return
        # draw pseudo-3D table (top-down with perspective)
        top_l = (court.left + 40, court.top + 24)
        top_r = (court.right - 40, court.top + 24)
        bot_r = (court.right - 12, court.bottom - 18)
        bot_l = (court.left + 12, court.bottom - 18)
        pygame.draw.polygon(screen, (50, 90, 60), [top_l, top_r, bot_r, bot_l])
        # table centre highlight
        inner = [
            (top_l[0] + 24, top_l[1] + 8),
            (top_r[0] - 24, top_r[1] + 8),
            (bot_r[0] - 24, bot_r[1] - 8),
            (bot_l[0] + 24, bot_l[1] - 8),
        ]
        pygame.draw.polygon(screen, (80, 130, 90), inner)
        # net (center vertical)
        net_x = (top_l[0] + top_r[0]) // 2
        pygame.draw.rect(screen, (220, 220, 220), (net_x - 4, top_l[1] - 6, 8, bot_l[1] - top_l[1] + 12))

        # draw characters slightly outside the court for an arcade look
        player_sprite_x = int(self.player_x) - 18
        player_sprite_y = int(self.player_y) - 18
        pygame.draw.ellipse(screen, (240, 200, 120), (player_sprite_x, player_sprite_y, 36, 36))
        opp_sprite_x = int(self.opp_x)
        opp_sprite_y = int(self.opp_y) - 18
        pygame.draw.ellipse(screen, UI_ACCENT, (opp_sprite_x, opp_sprite_y, 40, 40))
        # NOTE: rackets (collision rects) remain for gameplay but are intentionally not drawn

        # ball (may change color during Super Shot)
        # draw dash trail when ball is dashing
        if self.ball_dash_multiplier > 1.0:
            # approximate trail along reverse velocity
            bvx = self.ball_vel[0]
            bvy = self.ball_vel[1]
            mag = math.hypot(bvx, bvy) or 1.0
            nx = -bvx / mag
            ny = -bvy / mag
            for i, a in enumerate((0.18, 0.12, 0.06), start=1):
                ox = int(nx * (8 * i))
                oy = int(ny * (8 * i))
                col = (120, 200, 255, int(180 * a))
                surf = pygame.Surface((self.ball.width * 2, self.ball.height * 2), pygame.SRCALPHA)
                pygame.draw.circle(surf, (120, 200, 255, int(160 * a)), (self.ball.width, self.ball.height), self.ball.width)
                screen.blit(surf, (self.ball.centerx - self.ball.width + ox, self.ball.centery - self.ball.height + oy))
        pygame.draw.circle(screen, self.ball_color, (self.ball.centerx, self.ball.centery), self.ball.width // 2)
        # draw duplicate if present (identical to main ball)
        if self.duplicate:
            d = self.duplicate
            pygame.draw.circle(screen, self.ball_color, (d["rect"].centerx, d["rect"].centery), d["rect"].width // 2)

        # scores (arcade style)
        font = pygame.font.SysFont("arial", 36, bold=True)
        left_score = font.render(str(self.player_score), True, WHITE)
        right_score = font.render(str(self.opponent_score), True, WHITE)
        # score shadow for style
        screen.blit(font.render(str(self.player_score), True, (10, 10, 10)), (SCREEN_WIDTH // 2 - 140 + 2, 28 + 2))
        screen.blit(left_score, (SCREEN_WIDTH // 2 - 140, 28))
        screen.blit(font.render(str(self.opponent_score), True, (10, 10, 10)), (SCREEN_WIDTH // 2 + 100 + 2, 28 + 2))
        screen.blit(right_score, (SCREEN_WIDTH // 2 + 100, 28))

        # opponent name (above opponent sprite)
        name_font = pygame.font.SysFont("arial", 18, bold=True)
        opp_name = self.opponent.name if self.opponent else "Oscar"
        screen.blit(name_font.render(opp_name, True, WHITE), (opp_sprite_x, opp_sprite_y - 20))
        # player label under player sprite
        label_font = pygame.font.SysFont("arial", 18, bold=True)
        label = label_font.render("Aiden", True, (240, 230, 200))
        screen.blit(label, (player_sprite_x + 4, player_sprite_y + 40))

        # taunt
        if self._taunt_msg:
            tfont = pygame.font.SysFont("arial", 20)
            tw = tfont.size(self._taunt_msg)[0]
            screen.blit(tfont.render(self._taunt_msg, True, (240, 200, 60)), ((SCREEN_WIDTH - tw) // 2, SCREEN_HEIGHT - 80))

        # Super Shot incorrect-press reminder (comic bubble top-right)
        if self.super_msg:
            smf = pygame.font.SysFont("arial", 18, bold=True)
            padding = 12
            sw, sh = smf.size(self.super_msg)
            bw = sw + padding * 2
            bh = sh + padding * 2
            bx = SCREEN_WIDTH - bw - 24
            by = 18
            # shadow
            pygame.draw.rect(screen, (10, 10, 12), (bx + 4, by + 4, bw, bh), border_radius=10)
            # bubble
            pygame.draw.rect(screen, (255, 250, 220), (bx, by, bw, bh), border_radius=10)
            pygame.draw.rect(screen, (220, 150, 60), (bx, by, bw, bh), 2, border_radius=10)
            screen.blit(smf.render(self.super_msg, True, (40, 30, 10)), (bx + padding, by + padding))

        # Super Shot prompt (persistent until used)
        if self.super_ready:
            pf = pygame.font.SysFont("arial", 22, bold=True)
            prompt = "Press F for Super Shot"
            pw = pf.size(prompt)[0]
            # draw prompt centered near bottom
            pygame.draw.rect(screen, (30, 30, 40), (SCREEN_WIDTH//2 - pw//2 - 12, SCREEN_HEIGHT - 120, pw + 24, 36))
            screen.blit(pf.render(prompt, True, UI_ACCENT), (SCREEN_WIDTH//2 - pw//2, SCREEN_HEIGHT - 116))

        # End-of-match message overlay (waiting for player to dismiss)
        if getattr(self, 'waiting_for_dismiss', False) and getattr(self, 'end_message', None):
            box_w = 520
            box_h = 160
            bx = (SCREEN_WIDTH - box_w) // 2
            by = (SCREEN_HEIGHT - box_h) // 2
            pygame.draw.rect(screen, (20, 20, 30), (bx, by, box_w, box_h))
            pygame.draw.rect(screen, UI_ACCENT, (bx, by, box_w, box_h), 2)
            title_font = pygame.font.SysFont("arial", 36, bold=True)
            msg_font = pygame.font.SysFont("arial", 22)
            lines = str(self.end_message).split("\n")
            y = by + 20
            for i, line in enumerate(lines):
                font = title_font if i == 0 else msg_font
                surf = font.render(line, True, WHITE)
                screen.blit(surf, surf.get_rect(center=(SCREEN_WIDTH // 2, y + (i * 36))))
            hint = self.font_hint if hasattr(self, 'font_hint') else pygame.font.SysFont("arial", 16)
            screen.blit(hint.render("Press any key to continue", True, UI_TEXT_DIM), (SCREEN_WIDTH // 2 - 110, by + box_h - 32))
        
