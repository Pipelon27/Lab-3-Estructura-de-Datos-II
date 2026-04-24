"""
src/pingpong.py — Simple Pong minigame where cursor is paddle.
First to 10 points wins. On player miss Oscar taunts.
"""
from __future__ import annotations

import pygame
import math
from settings import SCREEN_WIDTH, SCREEN_HEIGHT, UI_ACCENT, WHITE, UI_TEXT_DIM


class PingPongGame:
    def __init__(self):
        self.active = False
        self.player = None  # NPC instance for opponent
        self.ball = pygame.Rect(SCREEN_WIDTH // 2 - 8, SCREEN_HEIGHT // 2 - 8, 16, 16)
        # tuned ball speed (slightly reduced per user request)
        self.ball_vel = [480.0, 360.0]
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
        # paddles
        self.player_w = 160
        self.player_h = 12
        self.opp_w = 160
        self.opp_h = 12
        self.opp_x = SCREEN_WIDTH // 2 - self.opp_w // 2
        self.opp_y = 80
        # opponent AI speed (tuned: Oscar moves a bit more)
        self.opp_speed = 420
        # make it easier: slightly wider player paddle
        self.player_w = 200
        # position player paddle symmetrically inside the court
        # court bottom = SCREEN_HEIGHT - 140; place paddle 40px above bottom
        self.player_y = SCREEN_HEIGHT - 180
        # who last touched the ball: 'player' or 'opponent'
        self.last_touch = None
        # Super Shot system
        self.super_cooldown = 5.0
        self.super_ready = False
        self.super_prompt_timer = 0.0
        self.super_armed = False
        self.super_effect_timer = 0.0
        self.ball_color = WHITE
        # Per-point base speed and per-hit speed multiplier
        # start a bit faster and ramp faster per hit
        self.base_vx = 300.0
        self.base_vy = 240.0
        # multiplier applied after each paddle hit (faster ramp)
        self.hit_speed_mult = 1.25
        # Oscar duplicate-ball ability
        self.opp_dup_cooldown = 3.0
        self.opp_dup_timer = 3.0
        self.duplicate = None  # dict with keys: rect, vel
        self.dupe_color = (180, 180, 200, 180)
        # per-point flag to ensure we spawn duplicate once per opponent first-hit
        self.dup_spawned_this_point = False

    def start(self, player, opponent):
        self.player = player
        self.opponent = opponent
        self.reset()
        self.active = True
        self.end_message = None
        self.waiting_for_dismiss = False
        self.finished = False

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

    def handle_input(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN:
            # Super Shot activation — direct the ball to an inescapable corner when pressed
            if event.key == pygame.K_f and self.super_ready:
                # compute court and opponent position to pick a far corner
                court_left = 40
                court_right = SCREEN_WIDTH - 40
                court_top = 40
                opp_cx = self.opp_x + self.opp_w / 2
                # choose corner farther from opponent
                left_dist = abs(opp_cx - court_left)
                right_dist = abs(opp_cx - court_right)
                target_x = court_left + 12 if left_dist > right_dist else court_right - 12
                target_y = court_top + 8
                # direction vector from ball to target
                vx = target_x - self.ball.centerx
                vy = target_y - self.ball.centery
                mag = math.hypot(vx, vy) or 1.0
                # set a high speed toward that corner (immediate effect)
                speed = 700.0
                self.ball_vel[0] = (vx / mag) * speed
                self.ball_vel[1] = (vy / mag) * speed
                self.ball_color = (220, 40, 40)
                self.super_effect_timer = 0.8
                self.super_ready = False
                self.super_armed = False
                self.super_prompt_timer = 0.0
                self.super_cooldown = 5.0
            elif getattr(self, 'waiting_for_dismiss', False):
                # any key dismisses the end screen
                self.waiting_for_dismiss = False
                self.finished = True
            elif event.key == pygame.K_ESCAPE:
                self.active = False

    def update(self, dt: float) -> str | None:
        if not self.active:
            return None
        # move ball
        self.ball.x += int(self.ball_vel[0] * dt)
        self.ball.y += int(self.ball_vel[1] * dt)

        # player paddle follows mouse
        mx, _ = pygame.mouse.get_pos()
        player_x = mx - self.player_w // 2
        player_rect = pygame.Rect(player_x, self.player_y, self.player_w, self.player_h)

        # opponent AI: follow ball (Oscar moves much faster)
        if self.ball.centerx < self.opp_x + self.opp_w // 2:
            self.opp_x -= int(self.opp_speed * dt)
        else:
            self.opp_x += int(self.opp_speed * dt)
        self.opp_x = max(40, min(SCREEN_WIDTH - 40 - self.opp_w, self.opp_x))
        opp_rect = pygame.Rect(self.opp_x, self.opp_y, self.opp_w, self.opp_h)

        # paddle collisions
        if self.ball.colliderect(player_rect) and self.ball_vel[1] > 0:
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
                self.ball_vel[1] = -abs(self.ball_vel[1])
                offset = (self.ball.centerx - player_rect.centerx) / (player_rect.width / 2)
                self.ball_vel[0] += offset * 120
                # increase speed after each hit
                self.ball_vel[0] *= self.hit_speed_mult
                self.ball_vel[1] *= self.hit_speed_mult
            self.last_touch = 'player'
        if self.ball.colliderect(opp_rect) and self.ball_vel[1] < 0:
            self.ball_vel[1] = abs(self.ball_vel[1])
            offset = (self.ball.centerx - opp_rect.centerx) / (opp_rect.width / 2)
            self.ball_vel[0] += offset * 80
            # increase speed after each hit
            self.ball_vel[0] *= self.hit_speed_mult
            self.ball_vel[1] *= self.hit_speed_mult
            self.last_touch = 'opponent'
            # Spawn duplicate immediately from Oscar's paddle on his first hit this point
            if not self.duplicate and not self.dup_spawned_this_point:
                dupe_rect = pygame.Rect(0, 0, self.ball.width, self.ball.height)
                dupe_rect.centerx = opp_rect.centerx
                dupe_rect.centery = opp_rect.centery + opp_rect.height // 2 + 4
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

        # court rectangle
        court = pygame.Rect(40, 40, SCREEN_WIDTH - 80, SCREEN_HEIGHT - 140)

        # Side walls reflect horizontally (no scoring)
        if self.ball.left <= court.left:
            self.ball.left = court.left
            self.ball_vel[0] = abs(self.ball_vel[0])
        if self.ball.right >= court.right:
            self.ball.right = court.right
            self.ball_vel[0] = -abs(self.ball_vel[0])

        # --- Opponent duplicate-ball ability timer/spawn ---
        self.opp_dup_timer -= dt
        if self.opp_dup_timer <= 0 and self.duplicate is None:
            # spawn duplicate only on alternate rounds (every other point)
            total_points = self.player_score + self.opponent_score
            # spawn when total_points is odd (i.e., rounds 2,4,6...)
            if total_points % 2 == 1:
                # spawn duplicate at current main ball location and direct it to the player
                dupe_rect = pygame.Rect(self.ball.x, self.ball.y, self.ball.width, self.ball.height)
                # aim towards player's paddle center
                px = player_rect.centerx
                py = player_rect.centery
                vx = px - dupe_rect.centerx
                vy = py - dupe_rect.centery
                mag = math.hypot(vx, vy) or 1.0
                # set duplicate speed similar to current ball speed magnitude
                base_speed = math.hypot(self.ball_vel[0], self.ball_vel[1])
                speed = max(220.0, base_speed * 0.9)
                # initial dupe velocity aimed at player
                dupe_vx = (vx / mag) * speed
                dupe_vy = (vy / mag) * speed
                # ensure duplicate direction differs from main ball direction
                main_mag = math.hypot(self.ball_vel[0], self.ball_vel[1]) or 1.0
                mvx = self.ball_vel[0] / main_mag
                mvy = self.ball_vel[1] / main_mag
                dmag = math.hypot(dupe_vx, dupe_vy) or 1.0
                dvx = dupe_vx / dmag
                dvy = dupe_vy / dmag
                dot = dvx * mvx + dvy * mvy
                if abs(dot) > 0.9:
                    # rotate dupe velocity by 25 degrees to make it distinct
                    angle = math.radians(25)
                    cos_a = math.cos(angle)
                    sin_a = math.sin(angle)
                    rvx = dvx * cos_a - dvy * sin_a
                    rvy = dvx * sin_a + dvy * cos_a
                    dupe_vx = rvx * dmag
                    dupe_vy = rvy * dmag
                dupe_vel = [dupe_vx, dupe_vy]
                self.duplicate = {"rect": dupe_rect, "vel": dupe_vel}
                self.opp_dup_timer = self.opp_dup_cooldown
            else:
                # try again shortly (wait until round parity flips)
                self.opp_dup_timer = 0.5

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

        # Scoring only when crossing top or bottom
        scored = False
        if self.ball.top <= court.top:
            scored = True
            scorer_side = 'top'
        elif self.ball.bottom >= court.bottom:
            scored = True
            scorer_side = 'bottom'

        if scored:
            if self.last_touch == 'player':
                self.player_score += 1
            else:
                self.opponent_score += 1
                # opponent scored — taunt Oscar
                self._taunt_msg = self.taunts[self._taunt_index % len(self.taunts)]
                self._taunt_index += 1
                self._taunt_timer = 2.0
            # reset ball to centre and give initial velocity pointing away from last scorer
            self.ball.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
            # set vertical velocity pointing away from last touch and reset horizontal
            if self.last_touch == 'player':
                self.ball_vel[1] = self.base_vy
            else:
                self.ball_vel[1] = -self.base_vy
            # reset horizontal to base (small/random if desired)
            self.ball_vel[0] = 0.0
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
        # Allow drawing the end screen even when `active` is False
        if not self.active and not getattr(self, 'waiting_for_dismiss', False):
            return
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        # court
        court = pygame.Rect(40, 40, SCREEN_WIDTH - 80, SCREEN_HEIGHT - 140)
        pygame.draw.rect(screen, (30, 30, 40), court)
        # horizontal centre line (court midline)
        pygame.draw.line(screen, WHITE, (40, SCREEN_HEIGHT // 2), (SCREEN_WIDTH - 40, SCREEN_HEIGHT // 2), 1)

        # opponent
        pygame.draw.rect(screen, UI_ACCENT, (self.opp_x, self.opp_y, self.opp_w, self.opp_h))
        # player paddle
        mx, _ = pygame.mouse.get_pos()
        player_x = mx - self.player_w // 2
        pygame.draw.rect(screen, UI_ACCENT, (player_x, self.player_y, self.player_w, self.player_h))

        # ball (may change color during Super Shot)
        pygame.draw.ellipse(screen, self.ball_color, self.ball)
        # draw duplicate if present (identical to main ball)
        if self.duplicate:
            d = self.duplicate
            pygame.draw.ellipse(screen, self.ball_color, d["rect"]) 

        # scores
        font = pygame.font.SysFont("arial", 28, bold=True)
        screen.blit(font.render(str(self.player_score), True, WHITE), (SCREEN_WIDTH // 2 + 40, 40))
        screen.blit(font.render(str(self.opponent_score), True, WHITE), (SCREEN_WIDTH // 2 - 80, 40))

        # opponent name
        name_font = pygame.font.SysFont("arial", 20, bold=True)
        opp_name = self.opponent.name if self.opponent else "Oscar"
        screen.blit(name_font.render(opp_name, True, WHITE), (self.opp_x, self.opp_y - 24))

        # taunt
        if self._taunt_msg:
            tfont = pygame.font.SysFont("arial", 20)
            tw = tfont.size(self._taunt_msg)[0]
            screen.blit(tfont.render(self._taunt_msg, True, (240, 200, 60)), ((SCREEN_WIDTH - tw) // 2, SCREEN_HEIGHT - 80))

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
