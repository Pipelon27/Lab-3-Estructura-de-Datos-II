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
        # Oscar idle detection: track how long he stays near the same Y
        self._oscar_idle_timer = 0.0
        self._oscar_last_y = 0.0
        self._oscar_idle_threshold = 2.5   # seconds before forced move
        self._oscar_idle_nudge = 0.0       # remaining forced-move time
        self._oscar_nudge_dir = 1          # +1 or -1
        # Pause menu state
        self.paused = False
        self._pause_sel = 0   # 0=Resume 1=Settings 2=Quit
        # ball color (default orange)
        self.ball_color = (255, 140, 0)
        self.ball_trail_color = (255, 140, 0)
        self.ball_dash_timer = 0.0
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
        # Progressive multiball over time (starts with only one ball)
        self.match_elapsed = 0.0
        self.spawn_timer = 0.0
        self.oscar_spawn_lock_timer = 0.0
        # Visual bounce arc values (pseudo 3D parabola)
        self.ball_z = 0.0
        self.ball_vz = 0.0
        self.z_gravity = 1400.0
        self.ball_bounce_count = 0
        self.ball_first_bounce_side = "player"
        self.min_ball_speed = 390.0
        self.max_return_speed = 700.0
        self.super_shot_speed = 950.0
        # Super Shot (auto): unlocks every 6 player points
        self.super_points_spent = 0

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
        self.match_elapsed = 0.0
        self.spawn_timer = 0.0
        self.oscar_spawn_lock_timer = 0.0
        self.paused = False
        self._pause_sel = 0

    def court_rect(self) -> pygame.Rect:
        return pygame.Rect(
            self._court_margin_left,
            self._court_margin_top,
            SCREEN_WIDTH - (self._court_margin_left + self._court_margin_right),
            SCREEN_HEIGHT - (self._court_margin_top + self._court_margin_bottom),
        )

    def reset(self):
        # Place main ball from Oscar's current position
        spawn_x, spawn_y = self._get_oscar_spawn_center()
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
        self.match_elapsed = 0.0
        self.spawn_timer = 0.0
        self.oscar_spawn_lock_timer = 0.0
        self.ball_z = 0.0
        self.ball_vz = 0.0
        self.ball_bounce_count = 0
        self.ball_first_bounce_side = "player"
        self.ball_dash_timer = 0.0
        self.ball_trail_color = (255, 140, 0)
        self.super_points_spent = 0

    def _get_oscar_spawn_center(self) -> tuple[int, int]:
        """Spawn from Oscar's live rendered position and keep the ball fully visible."""
        court = self.court_rect()
        half_h = self.sprite_size // 2
        opp_y = int(getattr(self, "opp_y", court.top + court.h // 2))
        opp_y = max(court.top + half_h, min(court.bottom - half_h, opp_y))
        opp_rect = pygame.Rect(int(court.right + 12), int(opp_y - half_h), self.sprite_size, self.sprite_size)

        radius = self.ball.width // 2
        spawn_x = opp_rect.centerx - (self.sprite_size // 2) - radius - 2
        spawn_y = opp_rect.centery
        spawn_x = max(radius, min(SCREEN_WIDTH - radius, spawn_x))
        spawn_y = max(radius, min(SCREEN_HEIGHT - radius, spawn_y))
        return spawn_x, spawn_y

    def _arm_ball_bounce(self, ball_state: dict | None = None, first_bounce_side: str | None = None):
        """Initialize a new arc so balls visually bounce over the table."""
        if ball_state is None:
            self.ball_z = 0.0
            self.ball_vz = 640.0
            self.ball_bounce_count = 0
            self.ball_first_bounce_side = first_bounce_side
        else:
            ball_state["z"] = 0.0
            ball_state["vz"] = 640.0
            ball_state["bounce_count"] = 0
            ball_state["first_bounce_side"] = first_bounce_side

    def _update_ball_bounce(self, dt: float, court: pygame.Rect, rect: pygame.Rect, ball_state: dict | None = None):
        if ball_state is None:
            self.ball_vz -= self.z_gravity * dt
            self.ball_z += self.ball_vz * dt
            if self.ball_z < 0:
                self.ball_z = 0
                self.ball_vz = abs(self.ball_vz) * 0.72
                self.ball_bounce_count += 1
                if self.ball_vz < 120:
                    self.ball_vz = 460.0
            return
        vz = ball_state.get("vz", 0.0) - self.z_gravity * dt
        z = ball_state.get("z", 0.0) + vz * dt
        if z < 0:
            z = 0
            vz = abs(vz) * 0.72
            ball_state["bounce_count"] = ball_state.get("bounce_count", 0) + 1
            if vz < 120:
                vz = 460.0
        ball_state["z"] = z
        ball_state["vz"] = vz

    def _get_super_shot_progress(self) -> float:
        earned = max(0, self.player_score - self.super_points_spent)
        return min(1.0, earned / 6.0)

    def _super_shot_available(self) -> bool:
        return (self.player_score - self.super_points_spent) >= 6

    def _enforce_min_speed(self, vel: list[float], min_speed: float | None = None):
        ms = self.min_ball_speed if min_speed is None else min_speed
        speed = math.hypot(vel[0], vel[1]) or 0.0
        if speed >= ms or speed <= 0.0:
            return
        scale = ms / speed
        vel[0] *= scale
        vel[1] *= scale

    def _cap_speed(self, vel: list[float], max_speed: float | None = None):
        ms = self.max_return_speed if max_speed is None else max_speed
        speed = math.hypot(vel[0], vel[1]) or 0.0
        if speed <= ms or speed <= 0.0:
            return
        scale = ms / speed
        vel[0] *= scale
        vel[1] *= scale

    def _steer_for_first_bounce(self, rect: pygame.Rect, vel: list[float], first_bounce_side: str, court: pygame.Rect):
        """Adjust horizontal speed so first floor contact lands on opposite side."""
        t_first = max(0.45, (2.0 * 640.0) / self.z_gravity)
        net_x = (court.left + court.right) // 2
        if first_bounce_side == "player":
            target_x = (court.left + net_x) // 2
        else:
            target_x = (net_x + court.right) // 2
        desired_vx = (target_x - rect.centerx) / t_first
        if abs(vel[0]) < abs(desired_vx):
            vel[0] = desired_vx

    def _queue_oscar_extra_ball(self, player_rect: pygame.Rect, delay: float = 0.0, strong: bool = False):
        """Spawn an extra ball from Oscar's current position."""
        spawn_x, spawn_y = self._get_oscar_spawn_center()
        court = self.court_rect()
        dupe_rect = pygame.Rect(0, 0, self.ball.width, self.ball.height)
        dupe_rect.center = (spawn_x, spawn_y)
        px = player_rect.centerx
        py = player_rect.centery
        vx = px - dupe_rect.centerx
        vy = py - dupe_rect.centery
        mag = math.hypot(vx, vy) or 1.0
        speed = max(300.0, min(820.0, math.hypot(self.ball_vel[0], self.ball_vel[1])))
        if strong:
            speed *= 1.35
        trail = (220, 40, 40) if strong else (255, 140, 0)
        dupe_vel = [-(abs(vx / mag) * speed), (vy / mag) * speed]
        self._enforce_min_speed(dupe_vel, self.min_ball_speed * 0.95)
        self._cap_speed(dupe_vel, self.max_return_speed * 0.95)
        self._steer_for_first_bounce(dupe_rect, dupe_vel, "player", court)

        self.spawn_queue.append({
            "delay": delay,
            "rect": dupe_rect,
            "vel": dupe_vel,
            "strong": strong,
            "dash_timer": 0.0,
            "trail_color": trail,
            "z": 0.0,
            "vz": 640.0,
            "bounce_count": 0,
            "first_bounce_side": "player",
        })
        # lock Oscar briefly so ball clearly appears from his current position
        self.oscar_spawn_lock_timer = 0.15

    def handle_input(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN:
            # ── Pause menu navigation ────────────────────────────
            if getattr(self, 'paused', False):
                if event.key == pygame.K_ESCAPE:
                    self.paused = False          # Resume
                elif event.key in (pygame.K_UP, pygame.K_w):
                    self._pause_sel = (self._pause_sel - 1) % 3
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self._pause_sel = (self._pause_sel + 1) % 3
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    sel = self._pause_sel
                    if sel == 0:                 # Resume
                        self.paused = False
                    elif sel == 1:               # Settings — signal caller
                        self.paused = False
                        self._pause_action = 'settings'
                    else:                        # Quit minigame
                        self.paused = False
                        self.active = False
                        self.finished = True
                return
            # ── ESC toggles pause from any in-game state ──
            if event.key == pygame.K_ESCAPE:
                if not getattr(self, 'waiting_for_dismiss', False):
                    self.paused = True
                    self._pause_sel = 0
                    self._pause_action = None
                return
            if getattr(self, 'waiting_for_dismiss', False):
                if event.key == pygame.K_SPACE:
                    self.waiting_for_dismiss = False
                    self.finished = True
                return
            if event.key == pygame.K_SPACE:
                # SPACE triggers dash in update via key state.
                pass
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
        # If paused, do nothing
        if getattr(self, 'paused', False):
            return None
        # If a pause action was signalled (e.g. settings), return it and clear
        action = getattr(self, '_pause_action', None)
        if action:
            self._pause_action = None
            return action
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
        court = self.court_rect()
        self.match_elapsed += dt
        self.spawn_timer -= dt
        if self.oscar_spawn_lock_timer > 0:
            self.oscar_spawn_lock_timer = max(0.0, self.oscar_spawn_lock_timer - dt)
        if self.ball_dash_timer > 0:
            self.ball_dash_timer = max(0.0, self.ball_dash_timer - dt)
        # move main ball
        self.ball.x += int(self.ball_vel[0] * dt)
        self.ball.y += int(self.ball_vel[1] * dt)
        self._enforce_min_speed(self.ball_vel)
        self._update_ball_bounce(dt, court, self.ball)
        # process spawn queue: decrement delays and spawn balls one-by-one
        if self.spawn_queue:
            for q in list(self.spawn_queue):
                q["delay"] -= dt
                if q["delay"] <= 0:
                    # spawn into extra_balls
                    self.extra_balls.append({
                        "rect": q["rect"],
                        "vel": q["vel"],
                        "strong": q.get("strong", False),
                        "dash_timer": q.get("dash_timer", 0.0),
                        "trail_color": q.get("trail_color", (255, 140, 0)),
                        "z": q.get("z", 0.0),
                        "vz": q.get("vz", 640.0),
                        "bounce_count": q.get("bounce_count", 0),
                        "first_bounce_side": q.get("first_bounce_side", "player"),
                    })
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
            self._enforce_min_speed(b["vel"], self.min_ball_speed * 0.95)
            self._update_ball_bounce(dt, court, b["rect"], b)

        # player movement via WASD + dash (tuned a bit faster for arcade feel)
        keys = pygame.key.get_pressed()
        move_speed = 280.0
        if keys[KEY_DASH] and self.dash_timer <= 0:
            self.dash_active = True
            self.dash_timer = DASH_DURATION / 60.0
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
        # Start with only one ball, then progressively add more over time.
        allowed_extra = min(8, int(self.match_elapsed // 8.0))
        if self.spawn_timer <= 0 and (len(self.extra_balls) + len(self.spawn_queue)) < allowed_extra:
            strong = (int(self.match_elapsed) % 3 == 0)
            self._queue_oscar_extra_ball(player_rect, delay=0.0, strong=strong)
            self.spawn_timer = max(1.3, 3.8 - min(2.3, self.match_elapsed / 18.0))

        # Super Shot auto-activates on valid contact every 6 points.
        if self._super_shot_available():
            used = False
            if self.ball.colliderect(player_rect) and self.ball_vel[0] < 0:
                self.ball_vel[0] = abs(self.ball_vel[0]) * 2.8
                self.ball_vel[1] *= 1.4
                self.ball_color = (245, 220, 60)
                self.ball_trail_color = (245, 220, 60)
                self.ball_dash_timer = 0.65
                self._arm_ball_bounce(first_bounce_side="oscar")
                self._enforce_min_speed(self.ball_vel, self.super_shot_speed)
                self._steer_for_first_bounce(self.ball, self.ball_vel, "oscar", court)
                used = True
            else:
                for b in self.extra_balls:
                    if b["rect"].colliderect(player_rect) and b["vel"][0] < 0:
                        b["vel"][0] = abs(b["vel"][0]) * 2.8
                        b["vel"][1] *= 1.4
                        b["trail_color"] = (245, 220, 60)
                        b["dash_timer"] = 0.65
                        self._arm_ball_bounce(b, first_bounce_side="oscar")
                        self._enforce_min_speed(b["vel"], self.super_shot_speed)
                        self._steer_for_first_bounce(b["rect"], b["vel"], "oscar", court)
                        used = True
                        break
            if used:
                self.super_points_spent += 6

        # opponent AI: choose behavior based on incoming balls
        # Prefer staying still; only move when a ball (non-purple) is clearly approaching
        target_y = self.ball.centery
        # If main ball is purple and moving toward Oscar, try to avoid it by moving away
        purple_color = (160, 60, 200)
        yellow_color = (245, 220, 60)
        if self.ball_color in (purple_color, yellow_color) and self.ball_vel[0] > 0:
            # move away from the ball by setting a distant target
            if self.ball.centery < self.opp_y:
                target_y = self.opp_y + 80
            else:
                target_y = self.opp_y - 80
        else:
            # check extra balls for purple threats heading to Oscar
            for b in self.extra_balls:
                if b.get("trail_color") in (purple_color, yellow_color) and b["vel"][0] > 0:
                    if b["rect"].centery < self.opp_y:
                        target_y = self.opp_y + 80
                    else:
                        target_y = self.opp_y - 80
                    break

        # Smooth movement: only move if distance exceeds a small deadzone to avoid jitter
        half_h = self.sprite_size // 2
        deadzone = 8
        diff = target_y - self.opp_y
        # ── Oscar idle detection: force a random nudge if he stays put too long ──
        if abs(self.opp_y - self._oscar_last_y) > 6:
            self._oscar_last_y = self.opp_y
            self._oscar_idle_timer = 0.0
        else:
            self._oscar_idle_timer += dt
        if self._oscar_idle_nudge > 0:
            # apply forced movement
            self._oscar_idle_nudge -= dt
            nudge_move = self._oscar_nudge_dir * self.opp_speed * 0.55 * dt
            self.opp_y += nudge_move
        elif self._oscar_idle_timer >= self._oscar_idle_threshold:
            # start a forced nudge
            self._oscar_idle_timer = 0.0
            self._oscar_idle_nudge = 0.45
            # alternate direction each time
            self._oscar_nudge_dir *= -1
        elif self.oscar_spawn_lock_timer <= 0 and abs(diff) > deadzone:
            # normal AI movement toward ball
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
            # player hit keeps orange ball but with energized translucent effect
            self.ball_color = (255, 140, 0)
            self.ball_trail_color = (255, 140, 0)
            self.ball_dash_timer = 0.5
            # reflect to right and increase speed
            self.ball_vel[0] = abs(self.ball_vel[0]) * self.hit_speed_mult
            self.ball_vel[1] *= self.hit_speed_mult
            self._arm_ball_bounce(first_bounce_side="oscar")
            self._enforce_min_speed(self.ball_vel)
            self._cap_speed(self.ball_vel)
            self._steer_for_first_bounce(self.ball, self.ball_vel, "oscar", court)
            self.last_touch = 'player'
        if self.ball.colliderect(opp_rect) and self.ball_vel[0] > 0:
            # if main ball is purple, Oscar avoids it and does not return it
            if self.ball_color in ((160, 60, 200), (245, 220, 60)):
                # do not reflect; allow ball to pass
                pass
            else:
                offset = (self.ball.centery - opp_rect.centery) / (opp_rect.height / 2)
                self.ball_vel[1] += offset * 80
                self.ball_vel[0] = -abs(self.ball_vel[0]) * self.hit_speed_mult
                self.ball_color = (255, 140, 0)
                self.ball_trail_color = (255, 140, 0)
                self.ball_dash_timer = 0.45
                self._arm_ball_bounce(first_bounce_side="player")
                self._enforce_min_speed(self.ball_vel)
                self._cap_speed(self.ball_vel, self.max_return_speed * 0.95)
                self._steer_for_first_bounce(self.ball, self.ball_vel, "player", court)
                self.last_touch = 'opponent'
            # extra balls are now generated progressively by time (not instant volley bursts)

        # Side/top/bottom walls reflect
        # No hard bounces on extreme table edges: softly keep balls inside vertical bounds.
        inner_top = court.top + 22
        inner_bottom = court.bottom - 22
        if self.ball.top <= inner_top:
            self.ball.top = inner_top
            self.ball_vel[1] = abs(self.ball_vel[1]) * 0.45
        if self.ball.bottom >= inner_bottom:
            self.ball.bottom = inner_bottom
            self.ball_vel[1] = -abs(self.ball_vel[1]) * 0.45

        # update extra balls collisions and bounds
        for b in list(self.extra_balls):
            # avoid hard edge rebounds for extras too
            if b["rect"].top <= inner_top:
                b["rect"].top = inner_top
                b["vel"][1] = abs(b["vel"][1]) * 0.45
            if b["rect"].bottom >= inner_bottom:
                b["rect"].bottom = inner_bottom
                b["vel"][1] = -abs(b["vel"][1]) * 0.45
            # collisions with player
            if b["rect"].colliderect(player_rect) and b["vel"][0] < 0:
                # if ball is strong, hitting it returns it much stronger with purple effect
                if b.get("strong"):
                    b["vel"][0] = abs(b["vel"][0]) * 2.2
                    b["vel"][1] *= 1.6
                    b["trail_color"] = (160, 60, 200)
                    self._arm_ball_bounce(b, first_bounce_side="oscar")
                else:
                    b["vel"][0] = abs(b["vel"][0]) * self.hit_speed_mult
                    b["vel"][1] *= self.hit_speed_mult
                    self._arm_ball_bounce(b, first_bounce_side="oscar")
                # red/strong returns stay purple; normal returns stay orange
                if not b.get("strong"):
                    b["trail_color"] = (255, 140, 0)
                b["dash_timer"] = 0.5
                self._enforce_min_speed(b["vel"], self.min_ball_speed * 0.95)
                self._cap_speed(b["vel"])
                self._steer_for_first_bounce(b["rect"], b["vel"], "oscar", court)
                # apply player dash effect
                if self.dash_active:
                    b["vel"][0] *= 1.6
                    b["vel"][1] *= 1.6
                    b["dash_timer"] = 0.6
                    self._cap_speed(b["vel"], self.max_return_speed * 1.1)
                self.last_touch = 'player'
            # collisions with opponent
            if b["rect"].colliderect(opp_rect) and b["vel"][0] > 0:
                # if this extra ball is purple, Oscar avoids it and won't return it
                if b.get("trail_color") in ((160, 60, 200), (245, 220, 60)):
                    pass
                else:
                    b["vel"][0] = -abs(b["vel"][0]) * self.hit_speed_mult
                    b["vel"][1] *= self.hit_speed_mult
                    b["trail_color"] = (255, 140, 0)
                    b["dash_timer"] = 0.45
                    self._arm_ball_bounce(b, first_bounce_side="player")
                    self._cap_speed(b["vel"], self.max_return_speed * 0.95)
                    self._steer_for_first_bounce(b["rect"], b["vel"], "player", court)
                    self.last_touch = 'opponent'

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
            # reset main ball from Oscar's current side and slow base speed
            spawn_x, spawn_y = self._get_oscar_spawn_center()
            self.ball.center = (spawn_x, spawn_y)
            # send ball away from Oscar (to player)
            self.ball_vel[0] = -abs(self.base_vx)
            self.ball_vel[1] = 0.0
            self._arm_ball_bounce(first_bounce_side="player")
            self._steer_for_first_bounce(self.ball, self.ball_vel, "player", court)
            self._enforce_min_speed(self.ball_vel)
            self._cap_speed(self.ball_vel, self.max_return_speed * 0.95)
            self.oscar_spawn_lock_timer = 0.2
            # keep extra balls alive after a point; only reset main-ball duplicate trigger
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

    def _draw_table_legs(self, screen, bot_l, bot_r, leg_color=(55, 38, 20)):
        """Draw two legs — one centred on each short end of the table."""
        leg_h = 22
        leg_w = 8
        # One leg per side, centred horizontally between bot_l and bot_r extremes
        left_cx  = bot_l[0] + 36   # inset from left corner
        right_cx = bot_r[0] - 36   # inset from right corner
        for cx, cy in [(left_cx, bot_l[1]), (right_cx, bot_r[1])]:
            pygame.draw.rect(screen, leg_color,
                             (cx - leg_w // 2, cy, leg_w, leg_h))
            # small foot shadow
            pygame.draw.rect(screen, (30, 20, 10),
                             (cx - leg_w // 2 - 2, cy + leg_h - 3, leg_w + 4, 4))

    def draw(self, screen: pygame.Surface):
        # Allow drawing the end screen, menu, or countdown even when `active` is False
        if not self.active and not getattr(self, 'waiting_for_dismiss', False) and not getattr(self, 'show_menu', False) and not getattr(self, 'countdown_active', False):
            return
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        court = self.court_rect()
        if getattr(self, 'show_menu', False):
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
            self._draw_table_legs(screen, bot_l, bot_r)
            # draw characters
            player_sprite_x = int(self.player_x - self.sprite_size // 2)
            player_sprite_y = int(self.player_y - self.sprite_size // 2)
            pygame.draw.rect(screen, (240, 200, 120), (player_sprite_x, player_sprite_y, self.sprite_size, self.sprite_size))
            opp_sprite_x = int(court.right + 12)
            opp_sprite_y = int(self.opp_y - self.sprite_size // 2)
            pygame.draw.rect(screen, UI_ACCENT, (opp_sprite_x, opp_sprite_y, self.sprite_size, self.sprite_size))
            # Blur/dim the background so this UI sits in front of the court and players
            snapshot = screen.copy()
            small = pygame.transform.smoothscale(snapshot, (max(1, SCREEN_WIDTH // 6), max(1, SCREEN_HEIGHT // 6)))
            blurred = pygame.transform.smoothscale(small, (SCREEN_WIDTH, SCREEN_HEIGHT))
            screen.blit(blurred, (0, 0))
            fog = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            fog.fill((10, 10, 18, 130))
            screen.blit(fog, (0, 0))

            panel_w = 560
            panel_h = 220
            panel_x = (SCREEN_WIDTH - panel_w) // 2
            panel_y = (SCREEN_HEIGHT - panel_h) // 2
            pygame.draw.rect(screen, (16, 16, 28), (panel_x, panel_y, panel_w, panel_h), border_radius=14)
            pygame.draw.rect(screen, UI_ACCENT, (panel_x, panel_y, panel_w, panel_h), 2, border_radius=14)

            title_font = pygame.font.SysFont("arial", 34, bold=True)
            title = "Ping Pong - Controls"
            screen.blit(title_font.render(title, True, UI_ACCENT), (SCREEN_WIDTH // 2 - title_font.size(title)[0] // 2, panel_y + 18))

            # prompt to start
            hint_font = pygame.font.SysFont("arial", 28, bold=True)
            hint = "Press Enter to Start"
            screen.blit(hint_font.render(hint, True, UI_ACCENT), (SCREEN_WIDTH // 2 - hint_font.size(hint)[0] // 2, panel_y + 148))
            # small controls hint
            small = pygame.font.SysFont("arial", 18)
            ctrl = "WASD - Move    SPACE - Dash"
            screen.blit(small.render(ctrl, True, WHITE), (SCREEN_WIDTH // 2 - small.size(ctrl)[0] // 2, panel_y + 90))
            ctrl2 = "Super Shot auto-triggers every 6 points on hit"
            screen.blit(small.render(ctrl2, True, WHITE), (SCREEN_WIDTH // 2 - small.size(ctrl2)[0] // 2, panel_y + 116))
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
            self._draw_table_legs(screen, bot_l, bot_r)
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
        self._draw_table_legs(screen, bot_l, bot_r)

        # draw characters as larger squares
        player_sprite_x = int(self.player_x - self.sprite_size // 2)
        player_sprite_y = int(self.player_y - self.sprite_size // 2)
        pygame.draw.rect(screen, (240, 200, 120), (player_sprite_x, player_sprite_y, self.sprite_size, self.sprite_size))
        opp_sprite_x = int(court.right + 12)
        opp_sprite_y = int(self.opp_y - self.sprite_size // 2)
        pygame.draw.rect(screen, UI_ACCENT, (opp_sprite_x, opp_sprite_y, self.sprite_size, self.sprite_size))

        # draw main ball trail
        ball_draw_y = int(self.ball.centery - self.ball_z * 0.22)
        if self.ball_dash_timer > 0:
            bvx = self.ball_vel[0]
            bvy = self.ball_vel[1]
            mag = math.hypot(bvx, bvy) or 1.0
            nx = -bvx / mag
            ny = -bvy / mag
            for i, a in enumerate((0.3, 0.18, 0.08), start=1):
                ox = int(nx * (6 * i))
                oy = int(ny * (6 * i))
                surf = pygame.Surface((self.ball.width * 2, self.ball.height * 2), pygame.SRCALPHA)
                col = self.ball_trail_color
                pygame.draw.circle(surf, (col[0], col[1], col[2], int(200 * a)), (self.ball.width, self.ball.height), self.ball.width)
                screen.blit(surf, (self.ball.centerx - self.ball.width + ox, ball_draw_y - self.ball.height + oy))
            # translucent halo around the ball on energized hits
            glow = pygame.Surface((self.ball.width * 4, self.ball.height * 4), pygame.SRCALPHA)
            col = self.ball_trail_color
            pygame.draw.circle(glow, (col[0], col[1], col[2], 70), (self.ball.width * 2, self.ball.height * 2), int(self.ball.width * 1.6))
            screen.blit(glow, (self.ball.centerx - self.ball.width * 2, ball_draw_y - self.ball.height * 2))
        pygame.draw.circle(screen, self.ball_color, (self.ball.centerx, ball_draw_y), self.ball.width // 2)

        # draw extra balls with trails
        for b in self.extra_balls:
            bz = b.get("z", 0.0)
            draw_y = int(b['rect'].centery - bz * 0.22)
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
                    screen.blit(surf, (b['rect'].centerx - b['rect'].width + ox, draw_y - b['rect'].height + oy))
                glow = pygame.Surface((b['rect'].width * 4, b['rect'].height * 4), pygame.SRCALPHA)
                col = b.get('trail_color', (255, 140, 0))
                pygame.draw.circle(glow, (col[0], col[1], col[2], 70), (b['rect'].width * 2, b['rect'].height * 2), int(b['rect'].width * 1.6))
                screen.blit(glow, (b['rect'].centerx - b['rect'].width * 2, draw_y - b['rect'].height * 2))
            # draw ball
            col = b.get('trail_color', (255, 140, 0))
            pygame.draw.circle(screen, col, (b['rect'].centerx, draw_y), b['rect'].width // 2)

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

        # Super Shot bar (fills yellow, 1 charge each 6 points)
        super_w = 380
        super_h = 22
        sx = (SCREEN_WIDTH - super_w) // 2
        sy = SCREEN_HEIGHT - 40
        pygame.draw.rect(screen, (35, 35, 35), (sx, sy, super_w, super_h), border_radius=6)
        progress = self._get_super_shot_progress()
        fill_w = int((super_w - 4) * progress)
        pygame.draw.rect(screen, (240, 210, 60), (sx + 2, sy + 2, max(0, fill_w), super_h - 4), border_radius=6)
        sfont = pygame.font.SysFont("arial", 16, bold=True)
        if self._super_shot_available():
            st = "Super Shot READY (Auto on hit)"
            scol = (255, 230, 80)
        else:
            need = max(0, 6 - (self.player_score - self.super_points_spent))
            st = f"Super Shot Auto ({need} points to charge)"
            scol = WHITE
        sw = sfont.size(st)[0]
        screen.blit(sfont.render(st, True, scol), (SCREEN_WIDTH // 2 - sw // 2, sy - 20))

        # opponent name (above opponent sprite)
        name_font = pygame.font.SysFont("arial", 18, bold=True)
        opp_name = self.opponent.name if self.opponent else "Oscar"
        screen.blit(name_font.render(opp_name, True, WHITE), (opp_sprite_x, opp_sprite_y - 20))
        # player name (below player sprite)
        player_name = self.player.__class__.__name__ if getattr(self, 'player', None) else "Aiden"
        pw = name_font.size(player_name)[0]
        screen.blit(name_font.render(player_name, True, WHITE), (player_sprite_x + (self.sprite_size - pw) // 2, player_sprite_y + self.sprite_size + 8))

        # taunt
        if self._taunt_msg:
            tfont = pygame.font.SysFont("arial", 20)
            tw = tfont.size(self._taunt_msg)[0]
            screen.blit(tfont.render(self._taunt_msg, True, (240, 200, 60)), ((SCREEN_WIDTH - tw) // 2, SCREEN_HEIGHT - 115))

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
            screen.blit(hint.render("Press SPACE to exit", True, UI_TEXT_DIM), (SCREEN_WIDTH // 2 - 110, by + box_h - 32))

        # ──── ESC Pause Menu ─────────────────────────────────────────────────
        if getattr(self, 'paused', False):
            fog = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            fog.fill((0, 0, 0, 140))
            screen.blit(fog, (0, 0))

            pm_w = 340
            pm_h = 260
            pm_x = (SCREEN_WIDTH - pm_w) // 2
            pm_y = (SCREEN_HEIGHT - pm_h) // 2
            pygame.draw.rect(screen, (14, 14, 24), (pm_x, pm_y, pm_w, pm_h), border_radius=16)
            pygame.draw.rect(screen, UI_ACCENT, (pm_x, pm_y, pm_w, pm_h), 2, border_radius=16)

            ptitle_font = pygame.font.SysFont("arial", 30, bold=True)
            ptitle = "PAUSED"
            tw = ptitle_font.size(ptitle)[0]
            screen.blit(ptitle_font.render(ptitle, True, UI_ACCENT),
                        (pm_x + (pm_w - tw) // 2, pm_y + 20))

            options = ["Resume", "Settings", "Quit"]
            opt_font = pygame.font.SysFont("arial", 24, bold=True)
            dim_font = pygame.font.SysFont("arial", 24)
            sel = getattr(self, '_pause_sel', 0)
            for i, label in enumerate(options):
                oy = pm_y + 90 + i * 52
                if i == sel:
                    # highlight selected item
                    pygame.draw.rect(screen, (40, 60, 80),
                                     (pm_x + 30, oy - 6, pm_w - 60, 38), border_radius=8)
                    pygame.draw.rect(screen, UI_ACCENT,
                                     (pm_x + 30, oy - 6, pm_w - 60, 38), 2, border_radius=8)
                    lw = opt_font.size(label)[0]
                    screen.blit(opt_font.render(label, True, UI_ACCENT),
                                (pm_x + (pm_w - lw) // 2, oy))
                    # arrow indicator
                    screen.blit(opt_font.render("\u25ba", True, UI_ACCENT),
                                (pm_x + 38, oy))
                else:
                    lw = dim_font.size(label)[0]
                    screen.blit(dim_font.render(label, True, UI_TEXT_DIM),
                                (pm_x + (pm_w - lw) // 2, oy))

            nav_font = pygame.font.SysFont("arial", 14)
            nav = "↑↓ Navigate   Enter - Select   ESC - Resume"
            nw = nav_font.size(nav)[0]
            screen.blit(nav_font.render(nav, True, UI_TEXT_DIM),
                        (pm_x + (pm_w - nw) // 2, pm_y + pm_h - 28))


