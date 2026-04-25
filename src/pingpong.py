"""
src/pingpong.py — Arcade-style ping-pong minigame adapted to user requests.
Changes made:
 - Dash mapped to SPACE (context-sensitive with Super Shot)
 - Much smaller court
 - Characters are larger square sprites (no invisible paddle rectangles)
 - Balls are orange and Oscar can spawn many real balls per volley
 - Some balls are "strong" (red trail) and returning them creates a purple rapid effect
 - Score limit set to 30 and UI bars added (top left/right)
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
        self.score_limit = 30
        self.taunts = [
            "Keep missing, everyone's watching",
            "You're making this too easy",
            "Too slow, new kid!",
        ]
        self._taunt_index = 0
        self._taunt_msg = ""
        self._taunt_timer = 0.0
        # characters are now square sprites (larger)
        self.sprite_size = 64
        # will be positioned relative to court in reset()
        self.opp_x = 0
        self.opp_y = 0
        # opponent AI speed (tuned faster for arcade)
        self.opp_speed = 540
        # player position (float for smooth movement)
        self.player_x = 0.0
        self.player_y = 0.0
        # dash state (SPACE triggers dash)
        self.dash_timer = 0
        self.dash_active = False
        # who last touched the ball: 'player' or 'opponent'
        self.last_touch = None
        # ball color (default orange)
        self.ball_color = (255, 140, 0)
        # per-ball dash visual timer (used per-ball now)
        # Per-point base speed and per-hit speed multiplier (faster arcade)
        # start slightly faster and ramp up more slowly
        self.base_vx = 420.0
        self.base_vy = 260.0
        # multiplier applied after each paddle hit (slower ramp)
        self.hit_speed_mult = 1.12
        # ball dash multiplier base
        self.ball_dash_multiplier = 1.0
        # Oscar multi-ball ability: extra real balls (list)
        self.extra_balls = []  # list of dicts: {rect, vel, strong, dash_timer, trail_color}
        # spawn_queue: holds balls to spawn with delays so they appear one-by-one
        self.spawn_queue = []  # list of dicts: {delay, rect, vel, strong, trail_color}
        # main ball flags
        self.dup_spawned_this_point = False
        # court margins for a much smaller court
        self._court_margin_left = 240
        self._court_margin_top = 160
        self._court_margin_right = 240
        self._court_margin_bottom = 220
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
        # Place main ball near opponent (Oscar) side instead of centre
        court = self.court_rect()
        spawn_x = int(court.right - self.sprite_size - 12)
        spawn_y = int(court.top + court.h // 2)
        self.ball.center = (spawn_x, spawn_y)
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
        # reset extra-balls state for the new point
        self.extra_balls.clear()
        self.spawn_queue.clear()
        self.dup_spawned_this_point = False
        # reset any per-ball dash/visual state
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
            # SPACE is context-sensitive: if super is fully charged and player is colliding with a ball,
            # activate Super Shot. Otherwise it triggers dash (handled in update via key state).
            if event.key == pygame.K_SPACE:
                # SPACE triggers dash (handled in update via key state);
                # Super Shot removed — no special action on KEYDOWN here.
                pass
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
        # move main ball
        self.ball.x += int(self.ball_vel[0] * dt)
        self.ball.y += int(self.ball_vel[1] * dt)
        # process spawn queue: decrement delays and spawn balls one-by-one
        if self.spawn_queue:
            for q in list(self.spawn_queue):
                q["delay"] -= dt
                if q["delay"] <= 0:
                    # spawn into extra_balls
                    self.extra_balls.append({"rect": q["rect"], "vel": q["vel"], "strong": q.get("strong", False), "dash_timer": q.get("dash_timer", 0.0), "trail_color": q.get("trail_color", (255,140,0))})
                    try:
                        self.spawn_queue.remove(q)
                    except ValueError:
                        pass
        # move extra balls and update their dash timers
        for b in list(self.extra_balls):
            # update dash_timer and apply possible trail multiplier
            dtimer = b.get("dash_timer", 0)
            if dtimer > 0:
                b["dash_timer"] = max(0, dtimer - dt)
                mult = 1.35
            else:
                mult = 1.0
            b["rect"].x += int(b["vel"][0] * mult * dt)
            b["rect"].y += int(b["vel"][1] * mult * dt)

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
        # player and opponent square sprite rects (no invisible paddles)
        player_rect = pygame.Rect(int(self.player_x - self.sprite_size // 2), int(self.player_y - self.sprite_size // 2), self.sprite_size, self.sprite_size)

        # opponent AI: choose behavior based on incoming balls
        # Prefer staying still; only move when a ball (non-purple) is clearly approaching
        target_y = self.ball.centery
        # If main ball is purple and moving toward Oscar, try to avoid it by moving away
        purple_color = (160, 60, 200)
        if self.ball_color == purple_color and self.ball_vel[0] > 0:
            # move away from the ball by setting a distant target
            if self.ball.centery < self.opp_y:
                target_y = self.opp_y + 80
            else:
                target_y = self.opp_y - 80
        else:
            # check extra balls for purple threats heading to Oscar
            for b in self.extra_balls:
                if b.get("trail_color") == purple_color and b["vel"][0] > 0:
                    if b["rect"].centery < self.opp_y:
                        target_y = self.opp_y + 80
                    else:
                        target_y = self.opp_y - 80
                    break

        # Smooth movement: only move if distance exceeds a small deadzone to avoid jitter
        half_h = self.sprite_size // 2
        deadzone = 8
        diff = target_y - self.opp_y
        if abs(diff) > deadzone:
            # move toward target but don't overshoot; use dt-scaled speed
            move = math.copysign(min(self.opp_speed * dt, abs(diff)), diff)
            self.opp_y += move
        # clamp opponent sprite center inside court vertical span
        self.opp_y = max(court.top + half_h, min(court.bottom - half_h, self.opp_y))
        opp_rect = pygame.Rect(int(court.right + 12), int(self.opp_y - half_h), self.sprite_size, self.sprite_size)

        # collisions for main ball
        if self.ball.colliderect(player_rect) and self.ball_vel[0] < 0:
            # small offset for vertical deflection
            offset = (self.ball.centery - player_rect.centery) / (player_rect.height / 2)
            self.ball_vel[1] += offset * 120
            # apply dash effect if player was dashing
            if self.dash_active:
                self.ball_vel[0] *= 1.6
                self.ball_vel[1] *= 1.6
                # give main ball a trail effect color blue
                self.ball_color = (120, 200, 255)
            # reflect to right and increase speed
            self.ball_vel[0] = abs(self.ball_vel[0]) * self.hit_speed_mult
            self.ball_vel[1] *= self.hit_speed_mult
            self.last_touch = 'player'
        if self.ball.colliderect(opp_rect) and self.ball_vel[0] > 0:
            # if main ball is purple, Oscar avoids it and does not return it
            if self.ball_color == (160, 60, 200):
                # do not reflect; allow ball to pass
                pass
            else:
                offset = (self.ball.centery - opp_rect.centery) / (opp_rect.height / 2)
                self.ball_vel[1] += offset * 80
                self.ball_vel[0] = -abs(self.ball_vel[0]) * self.hit_speed_mult
                self.last_touch = 'opponent'
            # On opponent hit, spawn multiple real balls aimed to the player
            if not self.dup_spawned_this_point:
                # enqueue balls to spawn one-by-one with small delays and varied directions
                num = 6
                main_speed = math.hypot(self.ball_vel[0], self.ball_vel[1]) or 1.0
                # spawn balls paced: at least 1.5s between each
                delay_step = 1.5
                for i in range(num):
                    dupe_rect = pygame.Rect(0, 0, self.ball.width, self.ball.height)
                    # spawn slightly outside opponent sprite to avoid overlapping the main ball
                    dupe_rect.centerx = opp_rect.centerx + (self.sprite_size // 2) + 12
                    dupe_rect.centery = opp_rect.centery + (i - num//2) * 18
                    px = player_rect.centerx
                    py = player_rect.centery
                    vx = px - dupe_rect.centerx + (i - num//2) * 12
                    vy = py - dupe_rect.centery + (i - num//2) * 6
                    mag = math.hypot(vx, vy) or 1.0
                    dupe_vx = (vx / mag) * main_speed * (1.0 + (i % 2) * 0.15)
                    dupe_vy = (vy / mag) * main_speed * (1.0 + (i % 3) * 0.08)
                    strong = (i % 3 == 0)
                    trail = (220, 40, 40) if strong else (255, 140, 0)
                    self.spawn_queue.append({"delay": i * delay_step, "rect": dupe_rect, "vel": [dupe_vx, dupe_vy], "strong": strong, "dash_timer": 0.0, "trail_color": trail})
                self.dup_spawned_this_point = True

        # Side/top/bottom walls reflect
        if self.ball.top <= court.top:
            self.ball.top = court.top
            self.ball_vel[1] = abs(self.ball_vel[1])
        if self.ball.bottom >= court.bottom:
            self.ball.bottom = court.bottom
            self.ball_vel[1] = -abs(self.ball_vel[1])

        # update extra balls collisions and bounds
        for b in list(self.extra_balls):
            # reflect on court top/bottom
            if b["rect"].top <= court.top:
                b["rect"].top = court.top
                b["vel"][1] = abs(b["vel"][1])
            if b["rect"].bottom >= court.bottom:
                b["rect"].bottom = court.bottom
                b["vel"][1] = -abs(b["vel"][1])
            # collisions with player
            if b["rect"].colliderect(player_rect) and b["vel"][0] < 0:
                # if ball is strong, hitting it returns it much stronger with purple effect
                if b.get("strong"):
                    b["vel"][0] = abs(b["vel"][0]) * 2.2
                    b["vel"][1] *= 1.6
                    b["dash_timer"] = 0.6
                    b["trail_color"] = (160, 60, 200)
                else:
                    b["vel"][0] = abs(b["vel"][0]) * self.hit_speed_mult
                    b["vel"][1] *= self.hit_speed_mult
                # apply player dash effect
                if self.dash_active:
                    b["vel"][0] *= 1.6
                    b["vel"][1] *= 1.6
                    b["dash_timer"] = 0.35
                self.last_touch = 'player'
            # collisions with opponent
            if b["rect"].colliderect(opp_rect) and b["vel"][0] > 0:
                # if this extra ball is purple, Oscar avoids it and won't return it
                if b.get("trail_color") == (160, 60, 200):
                    pass
                else:
                    b["vel"][0] = -abs(b["vel"][0]) * self.hit_speed_mult
                    b["vel"][1] *= self.hit_speed_mult
                    self.last_touch = 'opponent'

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
            # After a score we leave main ball in center and allow rally to continue with extra balls
            pass

        # handle taunt timer
        if self._taunt_timer > 0:
            self._taunt_timer -= dt
            if self._taunt_timer <= 0:
                self._taunt_msg = ""

        # Check scoring for main ball
        scored = False
        scorer_side = None
        if self.ball.right < 0:
            scored = True
            scorer_side = 'left'
        elif self.ball.left > SCREEN_WIDTH:
            scored = True
            scorer_side = 'right'

        if scored:
            if scorer_side == 'right':
                # player scored
                self.player_score += 1
            else:
                self.opponent_score += 1
                self._taunt_msg = self.taunts[self._taunt_index % len(self.taunts)]
                self._taunt_index += 1
                self._taunt_timer = 2.0
            # reset main ball near opponent (Oscar) side and slow base speed
            court = self.court_rect()
            spawn_x = int(court.right - self.sprite_size - 12)
            spawn_y = int(court.top + court.h // 2)
            self.ball.center = (spawn_x, spawn_y)
            # send ball away from Oscar (to player)
            self.ball_vel[0] = -abs(self.base_vx)
            self.ball_vel[1] = 0.0
            # clear extra balls for new rally
            self.extra_balls.clear()
            self.dup_spawned_this_point = False

        # Check scoring for extra balls (ensure correct side -> correct scorer)
        for b in list(self.extra_balls):
            if b["rect"].right < 0:
                # ball exited left side -> opponent scored
                self.opponent_score += 1
                self._taunt_msg = self.taunts[self._taunt_index % len(self.taunts)]
                self._taunt_index += 1
                self._taunt_timer = 2.0
                try:
                    self.extra_balls.remove(b)
                except ValueError:
                    pass
            elif b["rect"].left > SCREEN_WIDTH:
                # ball exited right side -> player scored
                self.player_score += 1
                try:
                    self.extra_balls.remove(b)
                except ValueError:
                    pass

        # (Super Shot removed)

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
            # draw the court and characters as the pre-match backdrop (simple, no separate UI box)
            border_color = (30, 30, 40)
            pygame.draw.rect(screen, border_color, (court.left - 8, court.top - 8, court.width + 16, court.height + 16), 6, border_radius=6)
            # corner posts
            post_w = 12
            pygame.draw.rect(screen, UI_ACCENT, (court.left - 20, court.top - 20, post_w, post_w))
            pygame.draw.rect(screen, UI_ACCENT, (court.right + 8, court.top - 20, post_w, post_w))
            pygame.draw.rect(screen, UI_ACCENT, (court.left - 20, court.bottom + 8, post_w, post_w))
            pygame.draw.rect(screen, UI_ACCENT, (court.right + 8, court.bottom + 8, post_w, post_w))
            # draw table (same look as during play)
            top_l = (court.left + 40, court.top + 24)
            top_r = (court.right - 40, court.top + 24)
            bot_r = (court.right - 12, court.bottom - 18)
            bot_l = (court.left + 12, court.bottom - 18)
            pygame.draw.polygon(screen, (50, 90, 60), [top_l, top_r, bot_r, bot_l])
            inner = [
                (top_l[0] + 24, top_l[1] + 8),
                (top_r[0] - 24, top_r[1] + 8),
                (bot_r[0] - 24, bot_r[1] - 8),
                (bot_l[0] + 24, bot_l[1] - 8),
            ]
            pygame.draw.polygon(screen, (80, 130, 90), inner)
            net_x = (top_l[0] + top_r[0]) // 2
            pygame.draw.rect(screen, (220, 220, 220), (net_x - 4, top_l[1] - 6, 8, bot_l[1] - top_l[1] + 12))
            # draw characters
            player_sprite_x = int(self.player_x - self.sprite_size // 2)
            player_sprite_y = int(self.player_y - self.sprite_size // 2)
            pygame.draw.rect(screen, (240, 200, 120), (player_sprite_x, player_sprite_y, self.sprite_size, self.sprite_size))
            opp_sprite_x = int(court.right + 12)
            opp_sprite_y = int(self.opp_y - self.sprite_size // 2)
            pygame.draw.rect(screen, UI_ACCENT, (opp_sprite_x, opp_sprite_y, self.sprite_size, self.sprite_size))
            # prompt to start
            hint_font = pygame.font.SysFont("arial", 28, bold=True)
            hint = "Press Enter to Start"
            screen.blit(hint_font.render(hint, True, UI_ACCENT), (SCREEN_WIDTH//2 - hint_font.size(hint)[0]//2, court.bottom + 8))
            # small controls hint
            small = pygame.font.SysFont("arial", 18)
            ctrl = "WASD - Move    SPACE - Dash"
            screen.blit(small.render(ctrl, True, WHITE), (SCREEN_WIDTH//2 - small.size(ctrl)[0]//2, court.bottom + 40))
            return
        # draw countdown overlay if active
        if getattr(self, 'countdown_active', False):
            # draw the court + characters as backdrop for countdown
            top_l = (court.left + 40, court.top + 24)
            top_r = (court.right - 40, court.top + 24)
            bot_r = (court.right - 12, court.bottom - 18)
            bot_l = (court.left + 12, court.bottom - 18)
            pygame.draw.polygon(screen, (50, 90, 60), [top_l, top_r, bot_r, bot_l])
            inner = [
                (top_l[0] + 24, top_l[1] + 8),
                (top_r[0] - 24, top_r[1] + 8),
                (bot_r[0] - 24, bot_r[1] - 8),
                (bot_l[0] + 24, bot_l[1] - 8),
            ]
            pygame.draw.polygon(screen, (80, 130, 90), inner)
            net_x = (top_l[0] + top_r[0]) // 2
            pygame.draw.rect(screen, (220, 220, 220), (net_x - 4, top_l[1] - 6, 8, bot_l[1] - top_l[1] + 12))
            # draw characters
            player_sprite_x = int(self.player_x - self.sprite_size // 2)
            player_sprite_y = int(self.player_y - self.sprite_size // 2)
            pygame.draw.rect(screen, (240, 200, 120), (player_sprite_x, player_sprite_y, self.sprite_size, self.sprite_size))
            opp_sprite_x = int(court.right + 12)
            opp_sprite_y = int(self.opp_y - self.sprite_size // 2)
            pygame.draw.rect(screen, UI_ACCENT, (opp_sprite_x, opp_sprite_y, self.sprite_size, self.sprite_size))
            # draw countdown number on top
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

        # draw characters as larger squares
        player_sprite_x = int(self.player_x - self.sprite_size // 2)
        player_sprite_y = int(self.player_y - self.sprite_size // 2)
        pygame.draw.rect(screen, (240, 200, 120), (player_sprite_x, player_sprite_y, self.sprite_size, self.sprite_size))
        opp_sprite_x = int(court.right + 12)
        opp_sprite_y = int(self.opp_y - self.sprite_size // 2)
        pygame.draw.rect(screen, UI_ACCENT, (opp_sprite_x, opp_sprite_y, self.sprite_size, self.sprite_size))

        # draw main ball (with optional trail)
        if getattr(self, 'ball_dash_timer', 0) > 0:
            pass
        pygame.draw.circle(screen, self.ball_color, (self.ball.centerx, self.ball.centery), self.ball.width // 2)

        # draw extra balls with trails
        for b in self.extra_balls:
            # trail: if dash_timer > 0 draw a faded trail in b['trail_color']
            if b.get('dash_timer', 0) > 0:
                bvx = b['vel'][0]
                bvy = b['vel'][1]
                mag = math.hypot(bvx, bvy) or 1.0
                nx = -bvx / mag
                ny = -bvy / mag
                for i, a in enumerate((0.3, 0.18, 0.08), start=1):
                    ox = int(nx * (6 * i))
                    oy = int(ny * (6 * i))
                    surf = pygame.Surface((b['rect'].width * 2, b['rect'].height * 2), pygame.SRCALPHA)
                    col = b.get('trail_color', (255, 140, 0))
                    pygame.draw.circle(surf, (col[0], col[1], col[2], int(200 * a)), (b['rect'].width, b['rect'].height), b['rect'].width)
                    screen.blit(surf, (b['rect'].centerx - b['rect'].width + ox, b['rect'].centery - b['rect'].height + oy))
            # draw ball
            col = b.get('trail_color', (255, 140, 0))
            pygame.draw.circle(screen, col, (b['rect'].centerx, b['rect'].centery), b['rect'].width // 2)

        # Top score bars (left: player green, right: opponent red) with numeric fraction
        bar_w = 220
        bar_h = 18
        # player bar (left)
        px = 32
        py = 12
        pygame.draw.rect(screen, (40, 40, 40), (px, py, bar_w, bar_h), border_radius=6)
        filled = int((self.player_score / self.score_limit) * (bar_w - 4))
        pygame.draw.rect(screen, (40, 200, 80), (px + 2, py + 2, max(0, filled), bar_h - 4), border_radius=6)
        # numeric
        smallf = pygame.font.SysFont("arial", 18, bold=True)
        text = f"{self.player_score} / {self.score_limit}"
        screen.blit(smallf.render(text, True, (255, 255, 255)), (px + 6, py - 2))
        # opponent bar (right)
        rx = SCREEN_WIDTH - 32 - bar_w
        ry = 12
        pygame.draw.rect(screen, (40, 40, 40), (rx, ry, bar_w, bar_h), border_radius=6)
        filled = int((self.opponent_score / self.score_limit) * (bar_w - 4))
        pygame.draw.rect(screen, (200, 40, 40), (rx + 2 + (bar_w - 4 - filled), ry + 2, max(0, filled), bar_h - 4), border_radius=6)
        text2 = f"{self.opponent_score} / {self.score_limit}"
        tw = smallf.size(text2)[0]
        screen.blit(smallf.render(text2, True, (255, 255, 255)), (rx + bar_w - tw - 6, ry - 2))

        # (Super Shot removed — no bottom bar)

        # opponent name (above opponent sprite)
        name_font = pygame.font.SysFont("arial", 18, bold=True)
        opp_name = self.opponent.name if self.opponent else "Oscar"
        screen.blit(name_font.render(opp_name, True, WHITE), (opp_sprite_x, opp_sprite_y - 20))

        # taunt
        if self._taunt_msg:
            tfont = pygame.font.SysFont("arial", 20)
            tw = tfont.size(self._taunt_msg)[0]
            screen.blit(tfont.render(self._taunt_msg, True, (240, 200, 60)), ((SCREEN_WIDTH - tw) // 2, SCREEN_HEIGHT - 80))

        # (Super messages removed)

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

