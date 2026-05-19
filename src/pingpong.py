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
import os
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
    DASH_DURATION, VT323_PATH)
from src.controller import get_controller, XBOX_START


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
        self.sprite_size = 80
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
        self._dash_pressed_controller = False  # Track A button dash for this frame
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
        # Character sprites for hit/attack animations
        self._player_sprites = {"aiden": {}, "lena": {}}
        self._opp_sprites = {}
        self.active_cheers = []
        self._player_hit_timer = 0.0
        self._opp_hit_timer = 0.0
        self._bounce_sound = None
        self._point_sound = None
        self._player_anim_timer = 0.0
        self._opp_anim_timer = 0.0
        self._sprite_disp_w = 80
        self._sprite_disp_h = 160
        self._sprites_loaded = False
        # Ping pong racket vertical offset (pixels from top of sprite when drawn)
        # Adjust this value if you want the racket higher or lower.
        self.racket_offset = 138
        self._bg = None
        self._bg_loaded = False

    def start(self, player, opponent):
        self.player = player
        self.opponent = opponent
        self._load_sprites(player, opponent)
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
        self._player_hit_timer = 0.0
        self._opp_hit_timer = 0.0
        self._player_anim_timer = 0.0
        self._opp_anim_timer = 0.0

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

    def _load_sprites(self, player_obj, opponent_obj):
        """Load idle and attack frames from spritesheets for the ping pong minigame."""
        import os
        try:
            fw, fh = 32, 64
            sw, sh = self._sprite_disp_w, self._sprite_disp_h

            def get_frames(sheet, row, cols):
                frames = []
                for c in cols:
                    rect = pygame.Rect(c * fw, row * fh, fw, fh)
                    frame = sheet.subsurface(rect).copy()
                    frames.append(pygame.transform.scale(frame, (sw, sh)))
                return frames

            self._player_sprites = {"aiden": {}, "lena": {}}

            # Load Aiden
            a_path = os.path.join("assets", "Characters BEHIND THE SMILE", "PROTAGONISTS", "Aiden Parker.png")
            a_sheet = pygame.image.load(a_path).convert_alpha()
            self._player_sprites["aiden"]["idle"]   = get_frames(a_sheet, 1, range(0, 6))
            self._player_sprites["aiden"]["attack"] = get_frames(a_sheet, 3, range(0, 6))

            # Load Lena
            l_path = os.path.join("assets", "Characters BEHIND THE SMILE", "PROTAGONISTS", "Lena Parker.png")
            l_sheet = pygame.image.load(l_path).convert_alpha()
            self._player_sprites["lena"]["idle"]   = get_frames(l_sheet, 1, range(0, 6))
            self._player_sprites["lena"]["attack"] = get_frames(l_sheet, 3, range(0, 6))

            o_path = os.path.join("assets", "Characters BEHIND THE SMILE", "POPULARS", "Oscar Jimenez.png")
            o_sheet = pygame.image.load(o_path).convert_alpha()
            # Oscar faces LEFT → cols 12-17
            self._opp_sprites["idle"]   = get_frames(o_sheet, 1, range(12, 18))
            self._opp_sprites["attack"] = get_frames(o_sheet, 3, range(12, 18))

            self._sprites_loaded = True
        except Exception as e:
            print(f"[PingPong] Sprite load failed: {e}")
            self._sprites_loaded = False

    def _load_sound(self, attr_name: str, filename: str):
        if not pygame.mixer.get_init():
            return None
        sound = getattr(self, attr_name, None)
        if sound is not None:
            return sound
        path = os.path.join("assets", "sounds", filename)
        try:
            sound = pygame.mixer.Sound(path)
            sound.set_volume(0.055)
        except Exception as e:
            print(f"[PingPong] Failed to load sound {path}: {e}")
            sound = None
        setattr(self, attr_name, sound)
        return sound

    def _play_bounce_sound(self):
        sound = self._load_sound("_bounce_sound", "sonido_rebote_pp.mp3")
        if sound:
            sound.play()

    def _play_point_sound(self):
        sound = self._load_sound("_point_sound", "sonido_punto_PP.mp3")
        if sound:
            sound.play()

    def spawn_cheer(self, text: str, is_local: bool = False):
        import random
        color = (255, 100, 200) if ("GO" in text or "❤️" in text) else (255, 220, 60)
        self.active_cheers.append({
            "text": text,
            "x": random.randint(120, 360) if is_local else random.randint(300, 500),
            "y": SCREEN_HEIGHT - 60,
            "color": color,
            "timer": 1.5,
            "vy": -120.0
        })
        try:
            if pygame.mixer.get_init():
                sound = self._load_sound("_cheer_sound", "sonido_punto_PP.mp3")
                if sound:
                    sound.play()
        except Exception:
            pass

    def _draw_character_sprite(self, screen: pygame.Surface, x: int, y: int, is_player: bool, active_char: str = "aiden"):
        """Draw idle sprite plus racket overlay."""
        hit_timer = self._player_hit_timer if is_player else self._opp_hit_timer
        anim_timer = self._player_anim_timer if is_player else self._opp_anim_timer

        if is_player:
            char_sprites = self._player_sprites.get(active_char, {})
            frames = char_sprites.get("idle", []) if self._sprites_loaded else []
        else:
            frames = self._opp_sprites.get("idle", []) if self._sprites_loaded else []

        cx = x + self.sprite_size // 2
        cy = y + self.sprite_size // 2

        if frames:
            idx = int(anim_timer * 8.0) % len(frames)
            frame = frames[idx]
            sw, sh = self._sprite_disp_w, self._sprite_disp_h
            blit_x = cx - sw // 2
            blit_y = cy - sh // 2
            screen.blit(frame, (blit_x, blit_y))
            self._draw_racket(screen, blit_x, blit_y, sw, sh,
                              facing_right=is_player,
                              is_hitting=(hit_timer > 0))
        else:
            color = (240, 200, 120) if is_player else UI_ACCENT
            pygame.draw.rect(screen, color, (x, y, self.sprite_size, self.sprite_size))
            self._draw_racket(screen, x, y, self.sprite_size, self.sprite_size,
                              facing_right=is_player,
                              is_hitting=(hit_timer > 0))

    def _draw_racket(self, screen: pygame.Surface,
                     sprite_left: int, sprite_top: int,
                     sprite_w: int, sprite_h: int,
                     facing_right: bool, is_hitting: bool = False):
        """Draw a horizontal ping pong racket aligned to the sprite."""
        handle_color = (60, 30, 10)
        paddle_rim = (15, 15, 15)
        paddle_face = (210, 35, 35)

        swing = 8 if is_hitting else 0
        hy_offset = getattr(self, "racket_offset", sprite_h // 2)
        hy = sprite_top + hy_offset

        # ── ADJUST HORIZONTAL OFFSET HERE ─────────────────────────
        # Negative = closer to body, Positive = further from body
        offset_right = -40   # Oscar (right side) - negative moves left toward body
        offset_left = 40     # Player (left side) - positive moves right toward body
        # Move paddle face forward (toward the table) - increase to extend further
        paddle_forward = 40
        # ────────────────────────────────────────────────────────────

        if facing_right:
            hx = sprite_left + sprite_w + swing + offset_right
            handle_rect = pygame.Rect(hx, hy - 3, 22, 6)
            px = hx + 22 + 12 + offset_right + paddle_forward
        else:
            hx = sprite_left - swing + offset_left
            handle_rect = pygame.Rect(hx - 22, hy - 3, 22, 6)
            px = hx - 22 - 12 + offset_left - paddle_forward
        
        # Move paddle face upward (negative = up, positive = down)
        paddle_up_offset = -6
        py = hy + paddle_up_offset

        pygame.draw.rect(screen, handle_color, handle_rect, border_radius=2)

        # Oval racket shape (elliptical)
        pr_w, pr_h = 36, 22
        paddle_surf = pygame.Surface((pr_w, pr_h), pygame.SRCALPHA)
        
        # Outer rim (ellipse)
        pygame.draw.ellipse(paddle_surf, paddle_rim, (0, 0, pr_w, pr_h))
        # Red face (ellipse)
        pygame.draw.ellipse(paddle_surf, paddle_face, (2, 2, pr_w - 4, pr_h - 4))
        # Center highlight for 2D depth
        pygame.draw.ellipse(paddle_surf, (230, 60, 60), (5, 5, pr_w - 10, pr_h - 10))
        
        # Rotate slightly upward (+25 for player facing right, -25 for opponent facing left)
        angle = 25 if facing_right else -25
        rotated = pygame.transform.rotate(paddle_surf, angle)
        r_rect = rotated.get_rect(center=(px, py))
        screen.blit(rotated, r_rect.topleft)

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
        # Also check controller for joystick.device_index event (hot-swap detection)
        if event.type == pygame.JOYDEVICEADDED or event.type == pygame.JOYDEVICEREMOVED:
            return  # Controller hot-swap handled by ControllerManager
            
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

    def handle_controller(self, controller):
        """Handle Xbox controller input for ping pong.
        
        Left stick: Move player
        RT (Right Trigger): Dash
        A Button: Dash (alternative)
        Menu (three lines / Start): Pause / Resume
        D-pad: Navigate pause menu
        A: Select / Confirm / Dash
        """
        # Reset controller dash flag at start of frame
        self._dash_pressed_controller = False
        
        if not controller or not controller.connected:
            return

        # Menu button (three lines / hamburger / Start) toggles pause
        if controller.is_pause_pressed():
            if getattr(self, 'waiting_for_dismiss', False):
                self.waiting_for_dismiss = False
                self.finished = True
                return
            
            if getattr(self, 'show_menu', False):
                # Start game from menu
                self.show_menu = False
                self.countdown_active = True
                self.countdown_timer = 3.0
                self.countdown_go_shown = False
                return
            
            # Toggle pause
            if not getattr(self, 'waiting_for_dismiss', False):
                self.paused = not self.paused
                if self.paused:
                    self._pause_sel = 0
                    self._pause_action = None
            return

        # A button to confirm when waiting for dismiss
        if getattr(self, 'waiting_for_dismiss', False):
            if controller.is_confirm_pressed():
                self.waiting_for_dismiss = False
                self.finished = True
            return

        # Handle pause menu navigation with D-pad
        if self.paused:
            menu_dir = controller.get_menu_direction()
            if menu_dir == -1:
                self._pause_sel = (self._pause_sel - 1) % 3
            elif menu_dir == 1:
                self._pause_sel = (self._pause_sel + 1) % 3
            
            if controller.is_confirm_pressed():
                sel = self._pause_sel
                if sel == 0:                 # Resume
                    self.paused = False
                elif sel == 1:               # Settings
                    self.paused = False
                    self._pause_action = 'settings'
                else:                        # Quit
                    self.paused = False
                    self.active = False
                    self.finished = True
            return

        # A button to start game from menu
        if getattr(self, 'show_menu', False):
            if controller.is_confirm_pressed():
                self.show_menu = False
                self.countdown_active = True
                self.countdown_timer = 3.0
                self.countdown_go_shown = False
            return
        
        # A button for dash during gameplay (when not paused, not in menu)
        if not self.paused and not getattr(self, 'show_menu', False) and not getattr(self, 'waiting_for_dismiss', False):
            if controller.is_confirm_pressed():
                self._dash_pressed_controller = True

    def update(self, dt: float) -> str | None:
        # Update active cheers
        for c in list(self.active_cheers):
            c["y"] += c["vy"] * dt
            c["timer"] -= dt
            if c["timer"] <= 0:
                self.active_cheers.remove(c)

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
        # Tick hit animation timers
        if self._player_hit_timer > 0:
            self._player_hit_timer = max(0.0, self._player_hit_timer - dt)
        if self._opp_hit_timer > 0:
            self._opp_hit_timer = max(0.0, self._opp_hit_timer - dt)
        self._player_anim_timer += dt
        self._opp_anim_timer += dt
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

        # player movement via WASD + controller left stick + dash (tuned a bit faster for arcade feel)
        keys = pygame.key.get_pressed()
        controller = get_controller()
        
        move_speed = 280.0
        
        # Dash: SPACE or RT (Right Trigger) or A button (controller)
        dash_triggered = keys[KEY_DASH] or (controller.connected and controller.rt_value > 0.5) or self._dash_pressed_controller
        if dash_triggered and self.dash_timer <= 0:
            self.dash_active = True
            self.dash_timer = DASH_DURATION / 60.0
        if self.dash_active:
            move_speed *= 2.0
            self.dash_timer -= dt
            if self.dash_timer <= 0:
                self.dash_active = False
                self.dash_timer = 0
        
        # Movement: Keyboard WASD + Controller left stick
        dx, dy = 0.0, 0.0
        
        # Keyboard input
        if keys[KEY_LEFT]:
            dx -= 1.0
        if keys[KEY_RIGHT]:
            dx += 1.0
        if keys[KEY_UP]:
            dy -= 1.0
        if keys[KEY_DOWN]:
            dy += 1.0
        
        # Controller left stick input (combine with keyboard)
        if controller.connected:
            cx, cy = controller.get_movement_vector()
            if abs(cx) > 0.01 or abs(cy) > 0.01:
                dx += cx
                dy += cy
        
        # Normalize combined movement
        if dx or dy:
            mag = math.hypot(dx, dy) or 1.0
            # Clamp to max speed (don't exceed 1.0 normalized)
            if mag > 1.0:
                dx /= mag
                dy /= mag
            self.player_x += dx * move_speed * dt
            self.player_y += dy * move_speed * dt
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
        # player and opponent full body rects matching 80x160 visual sprite
        player_rect = pygame.Rect(int(self.player_x - self._sprite_disp_w // 2), int(self.player_y - self._sprite_disp_h // 2), self._sprite_disp_w, self._sprite_disp_h)
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
                self._play_bounce_sound()
                self.super_points_spent += 6
                self._player_hit_timer = 0.5
                # Controller rumble feedback for Super Shot
                controller = get_controller()
                if controller.connected:
                    controller.rumble(0.7, 0.9, 300)  # Stronger rumble for Super Shot

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
        opp_rect = pygame.Rect(int(court.right + 12), int(self.opp_y - self._sprite_disp_h // 2), self._sprite_disp_w, self._sprite_disp_h)

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
            self._player_hit_timer = 0.5
            self._play_bounce_sound()
            # Light rumble for regular ball hit
            controller = get_controller()
            if controller.connected:
                controller.rumble(0.3, 0.4, 100)
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
                self._opp_hit_timer = 0.5
                self._play_bounce_sound()
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
                self._player_hit_timer = 0.4
                self._play_bounce_sound()
                # Light rumble for extra ball hit
                controller = get_controller()
                if controller.connected:
                    controller.rumble(0.25, 0.35, 80)
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
                    self._opp_hit_timer = 0.4
                    self._play_bounce_sound()

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
            self._play_point_sound()
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
            self.ball_color = (255, 140, 0)
            self.ball_trail_color = (255, 140, 0)
            self.ball_dash_timer = 0.0
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
                self._play_point_sound()
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
                self._play_point_sound()
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

    def _draw_table_legs(self, screen, bot_l, bot_r, leg_color=(18, 18, 18)):
        """Draw two legs — one centred on each short end of the table."""
        leg_h = 40  # taller legs for stronger presence
        leg_w = 26  # much wider legs per request
        # One leg per side, centred horizontally between bot_l and bot_r extremes
        left_cx  = bot_l[0] + 36   # inset from left corner
        right_cx = bot_r[0] - 36   # inset from right corner
        for cx, cy in [(left_cx, bot_l[1]), (right_cx, bot_r[1])]:
            pygame.draw.rect(screen, leg_color,
                             (cx - leg_w // 2, cy, leg_w, leg_h))
            # small foot shadow (darker, matching leg size)
            pygame.draw.rect(screen, (8, 8, 8),
                             (cx - leg_w // 2 - 5, cy + leg_h - 5, leg_w + 10, 6))

    def draw(self, screen: pygame.Surface, remote_pp_data: dict | None = None):
        is_spectating = remote_pp_data is not None
        local_char = "aiden"
        if self.player:
            local_char = self.player.__class__.__name__.lower()
        active_char = ("lena" if local_char == "aiden" else "aiden") if is_spectating else local_char

        orig_self_fields = {}
        if is_spectating:
            orig_self_fields = {
                "player_score": self.player_score,
                "opponent_score": self.opponent_score,
                "player_x": self.player_x,
                "player_y": self.player_y,
                "opp_x": self.opp_x,
                "opp_y": self.opp_y,
                "ball_center": self.ball.center,
                "ball_z": self.ball_z,
                "ball_color": self.ball_color,
                "ball_trail_color": self.ball_trail_color,
                "ball_dash_timer": self.ball_dash_timer,
                "super_points_spent": self.super_points_spent,
                "countdown_active": self.countdown_active,
                "countdown_timer": self.countdown_timer,
                "countdown_go_shown": getattr(self, "countdown_go_shown", False),
                "show_menu": self.show_menu,
                "waiting_for_dismiss": self.waiting_for_dismiss,
                "end_message": self.end_message,
                "extra_balls": list(self.extra_balls),
            }

            self.player_score = remote_pp_data.get("player_score", 0)
            self.opponent_score = remote_pp_data.get("opponent_score", 0)
            self.player_x = remote_pp_data.get("player_x", 0.0)
            self.player_y = remote_pp_data.get("player_y", 0.0)
            self.opp_x = remote_pp_data.get("opp_x", 0.0)
            self.opp_y = remote_pp_data.get("opp_y", 0.0)
            self.ball.center = (remote_pp_data.get("ball_cx", SCREEN_WIDTH // 2), remote_pp_data.get("ball_cy", SCREEN_HEIGHT // 2))
            self.ball_z = remote_pp_data.get("ball_z", 0.0)
            self.ball_color = remote_pp_data.get("ball_color", (255, 140, 0))
            self.ball_trail_color = remote_pp_data.get("ball_trail_color", (255, 140, 0))
            self.ball_dash_timer = remote_pp_data.get("ball_dash_timer", 0.0)
            self.super_points_spent = remote_pp_data.get("super_points_spent", 0)
            self.countdown_active = remote_pp_data.get("countdown_active", False)
            self.countdown_timer = remote_pp_data.get("countdown_timer", 0.0)
            self.countdown_go_shown = remote_pp_data.get("countdown_go_shown", False)
            self.show_menu = remote_pp_data.get("show_menu", False)
            self.waiting_for_dismiss = remote_pp_data.get("waiting_for_dismiss", False)
            self.end_message = remote_pp_data.get("end_message", None)
            
            # Map extra balls
            self.extra_balls = []
            for b in remote_pp_data.get("extra_balls", []):
                self.extra_balls.append({
                    "rect": pygame.Rect(b["cx"] - self.ball.width // 2, b["cy"] - self.ball.height // 2, self.ball.width, self.ball.height),
                    "z": b.get("z", 0.0),
                    "trail_color": b.get("trail_color", (255, 140, 0)),
                    "dash_timer": b.get("dash_timer", 0.0),
                    "vel": b.get("vel", [0.0, 0.0])
                })

        # Allow drawing the end screen, menu, or countdown even when `active` is False
        if not is_spectating and not self.active and not getattr(self, 'waiting_for_dismiss', False) and not getattr(self, 'show_menu', False) and not getattr(self, 'countdown_active', False):
            return
        controller = get_controller()
        # Background image (lazy load)
        if not self._bg_loaded:
            try:
                import os
                # Tile the floor using the orange vertical planks tile from the Room Builder tileset
                tp = os.path.join("assets", "BehindTheSmile_Assets", "BehindTheSmile_Assets", "campus", "Room_Builder_free_32x32.png")
                tileset = pygame.image.load(tp).convert()
                # Row 12 (0-indexed) corresponds to the tan vertical planks floor without top border (Y = 12 * 32 = 384)
                # Using X=0 to include the plank border
                tile = tileset.subsurface(pygame.Rect(0, 384, 32, 32))
                
                self._bg = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
                for tx in range(0, SCREEN_WIDTH, 32):
                    for ty in range(0, SCREEN_HEIGHT, 32):
                        self._bg.blit(tile, (tx, ty))
            except Exception as e:
                print(f"[PingPong] Failed to tile floor background: {e}")
                self._bg = None
            self._bg_loaded = True
        if self._bg:
            screen.blit(self._bg, (0, 0))
        else:
            screen.fill((0, 0, 10))

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
            net_rect = pygame.Rect(net_x - 4, top_l[1] - 6, 8, bot_l[1] - top_l[1] + 12)
            pygame.draw.rect(screen, (220, 220, 220), net_rect)

            post_color = (200, 200, 200)
            top_post = pygame.Rect(net_x - 6, top_l[1] - 18, 12, 22)
            bottom_post = pygame.Rect(net_x - 8, bot_l[1] - 12, 16, 32)
            pygame.draw.rect(screen, post_color, top_post)
            pygame.draw.rect(screen, post_color, bottom_post)

            def lerp_point(a, b, t: float):
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

            line_colour = (230, 230, 230)
            # Horizontal center line
            left_pt = lerp_point(top_l, bot_l, 0.5)
            right_pt = lerp_point(top_r, bot_r, 0.5)
            pygame.draw.line(
                screen,
                line_colour,
                (int(left_pt[0]), int(left_pt[1])),
                (int(right_pt[0]), int(right_pt[1])),
                width=3,
            )

            self._draw_table_legs(screen, bot_l, bot_r)
            # draw characters
            player_sprite_x = int(self.player_x - self.sprite_size // 2)
            player_sprite_y = int(self.player_y - self.sprite_size // 2)
            self._draw_character_sprite(screen, player_sprite_x, player_sprite_y, is_player=True, active_char=active_char)
            opp_sprite_x = int(court.right + 12)
            opp_sprite_y = int(self.opp_y - self.sprite_size // 2)
            self._draw_character_sprite(screen, opp_sprite_x, opp_sprite_y, is_player=False)
            # Blur/dim the background so this UI sits in front of the court and players
            snapshot = screen.copy()
            small = pygame.transform.smoothscale(snapshot, (max(1, SCREEN_WIDTH // 6), max(1, SCREEN_HEIGHT // 6)))
            blurred = pygame.transform.smoothscale(small, (SCREEN_WIDTH, SCREEN_HEIGHT))
            screen.blit(blurred, (0, 0))
            fog = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            fog.fill((10, 10, 18, 130))
            screen.blit(fog, (0, 0))

            using_controller = controller.connected if controller else False

            panel_w = 560
            panel_h = 220
            panel_x = (SCREEN_WIDTH - panel_w) // 2
            panel_y = (SCREEN_HEIGHT - panel_h) // 2
            pygame.draw.rect(screen, (16, 16, 28), (panel_x, panel_y, panel_w, panel_h), border_radius=14)
            pygame.draw.rect(screen, UI_ACCENT, (panel_x, panel_y, panel_w, panel_h), 2, border_radius=14)

            title_font = pygame.font.Font(VT323_PATH, 34)
            title = "Ping Pong - Controls"
            screen.blit(title_font.render(title, True, UI_ACCENT), (SCREEN_WIDTH // 2 - title_font.size(title)[0] // 2, panel_y + 18))

            # prompt to start / controls hint
            hint_font = pygame.font.Font(VT323_PATH, 28)
            small = pygame.font.Font(VT323_PATH, 18)

            if using_controller:
                hint = "Press A to Start"
                ctrl = "Left Stick - Move    RT - Dash"
            else:
                hint = "Press Enter to Start"
                ctrl = "WASD - Move    SPACE - Dash"

            screen.blit(hint_font.render(hint, True, UI_ACCENT), (SCREEN_WIDTH // 2 - hint_font.size(hint)[0] // 2, panel_y + 148))
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
            net_rect = pygame.Rect(net_x - 4, top_l[1] - 6, 8, bot_l[1] - top_l[1] + 12)
            pygame.draw.rect(screen, (220, 220, 220), net_rect)

            post_color = (200, 200, 200)
            top_post = pygame.Rect(net_x - 6, top_l[1] - 18, 12, 22)
            bottom_post = pygame.Rect(net_x - 8, bot_l[1] - 12, 16, 32)
            pygame.draw.rect(screen, post_color, top_post)
            pygame.draw.rect(screen, post_color, bottom_post)

            def lerp_point(a, b, t: float):
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

            line_colour = (230, 230, 230)
            # Horizontal center line
            left_pt = lerp_point(top_l, bot_l, 0.5)
            right_pt = lerp_point(top_r, bot_r, 0.5)
            pygame.draw.line(
                screen,
                line_colour,
                (int(left_pt[0]), int(left_pt[1])),
                (int(right_pt[0]), int(right_pt[1])),
                width=3,
            )

            self._draw_table_legs(screen, bot_l, bot_r)

            # draw characters
            player_sprite_x = int(self.player_x - self.sprite_size // 2)
            player_sprite_y = int(self.player_y - self.sprite_size // 2)
            self._draw_character_sprite(screen, player_sprite_x, player_sprite_y, is_player=True, active_char=active_char)
            opp_sprite_x = int(court.right + 12)
            opp_sprite_y = int(self.opp_y - self.sprite_size // 2)
            self._draw_character_sprite(screen, opp_sprite_x, opp_sprite_y, is_player=False)
            # draw countdown number on top
            ctimer = max(0.0, self.countdown_timer)
            if getattr(self, 'countdown_go_shown', False):
                txt = "Let's Go!"
                font = pygame.font.Font(VT323_PATH, 64)
                surf = font.render(txt, True, UI_ACCENT)
                screen.blit(surf, surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2)))
            else:
                num = int(math.ceil(ctimer)) if ctimer > 0 else 1
                font = pygame.font.Font(VT323_PATH, 128)
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
        net_rect = pygame.Rect(net_x - 4, top_l[1] - 6, 8, bot_l[1] - top_l[1] + 12)
        pygame.draw.rect(screen, (220, 220, 220), net_rect)

        # Net support posts (top/back and bottom/front)
        post_color = (200, 200, 200)
        top_post = pygame.Rect(net_x - 6, top_l[1] - 18, 12, 22)
        bottom_post = pygame.Rect(net_x - 8, bot_l[1] - 12, 16, 32)
        pygame.draw.rect(screen, post_color, top_post)
        pygame.draw.rect(screen, post_color, bottom_post)

        # Sideline division lines (horizontal doubles guides)
        def lerp_point(a, b, t: float):
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

        line_colour = (230, 230, 230)
        # Horizontal center line
        left_pt = lerp_point(top_l, bot_l, 0.5)
        right_pt = lerp_point(top_r, bot_r, 0.5)
        pygame.draw.line(
            screen,
            line_colour,
            (int(left_pt[0]), int(left_pt[1])),
            (int(right_pt[0]), int(right_pt[1])),
            width=3,
        )

        self._draw_table_legs(screen, bot_l, bot_r)

        # draw characters with sprite animations
        player_sprite_x = int(self.player_x - self.sprite_size // 2)
        player_sprite_y = int(self.player_y - self.sprite_size // 2)
        self._draw_character_sprite(screen, player_sprite_x, player_sprite_y, is_player=True, active_char=active_char)
        opp_sprite_x = int(court.right + 12)
        opp_sprite_y = int(self.opp_y - self.sprite_size // 2)
        self._draw_character_sprite(screen, opp_sprite_x, opp_sprite_y, is_player=False)

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
        smallf = pygame.font.Font(VT323_PATH, 18)
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
        sfont = pygame.font.Font(VT323_PATH, 16)
        if self._super_shot_available():
            st = "Super Shot READY (Auto on hit)"
            scol = (255, 230, 80)
        else:
            need = max(0, 6 - (self.player_score - self.super_points_spent))
            st = f"Super Shot Auto ({need} points to charge)"
            scol = WHITE
        sw = sfont.size(st)[0]
        screen.blit(sfont.render(st, True, scol), (SCREEN_WIDTH // 2 - sw // 2, sy - 20))


        # taunt
        if self._taunt_msg:
            tfont = pygame.font.Font(VT323_PATH, 20)
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
            title_font = pygame.font.Font(VT323_PATH, 36)
            msg_font = pygame.font.Font(VT323_PATH, 22)
            lines = str(self.end_message).split("\n")
            y = by + 20
            for i, line in enumerate(lines):
                font = title_font if i == 0 else msg_font
                surf = font.render(line, True, WHITE)
                screen.blit(surf, surf.get_rect(center=(SCREEN_WIDTH // 2, y + (i * 36))))
            hint = self.font_hint if hasattr(self, 'font_hint') else pygame.font.Font(VT323_PATH, 16)
            is_controller = bool(controller and controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller")
            msg = "Press A to exit" if is_controller else "Press SPACE to exit"
            screen.blit(hint.render(msg, True, UI_TEXT_DIM), (SCREEN_WIDTH // 2 - 110, by + box_h - 32))

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

            ptitle_font = pygame.font.Font(VT323_PATH, 30)
            ptitle = "PAUSED"
            tw = ptitle_font.size(ptitle)[0]
            screen.blit(ptitle_font.render(ptitle, True, UI_ACCENT),
                        (pm_x + (pm_w - tw) // 2, pm_y + 20))

            options = ["Resume", "Settings", "Quit"]
            opt_font = pygame.font.Font(VT323_PATH, 24)
            dim_font = pygame.font.Font(VT323_PATH, 24)
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

            nav_font = pygame.font.Font(VT323_PATH, 14)
            nav = "↑↓ Navigate   Enter - Select   ESC - Resume"
            nw = nav_font.size(nav)[0]
            screen.blit(nav_font.render(nav, True, UI_TEXT_DIM),
                        (pm_x + (pm_w - nw) // 2, pm_y + pm_h - 28))

        # ─── Draw active cheers (both spec and local) ───
        cheer_font = pygame.font.Font(VT323_PATH, 24)
        for c in self.active_cheers:
            alpha = int(255 * (c["timer"] / 1.5))
            surf = cheer_font.render(c["text"], True, c["color"])
            surf.set_alpha(alpha)
            # Draw shadow
            shadow = cheer_font.render(c["text"], True, (10, 10, 10))
            shadow.set_alpha(alpha)
            screen.blit(shadow, (c["x"] + 2, c["y"] + 2))
            screen.blit(surf, (c["x"], c["y"]))

        # ─── Spectating overlay & state restoration ───
        if is_spectating:
            # 1. Neon borders / CRT vignette
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            # Subtle scanline overlay
            for sy in range(0, SCREEN_HEIGHT, 4):
                pygame.draw.line(overlay, (10, 10, 20, 18), (0, sy), (SCREEN_WIDTH, sy), 2)
            # Neon border highlight
            pygame.draw.rect(overlay, (245, 60, 120, 45), (10, 10, SCREEN_WIDTH - 20, SCREEN_HEIGHT - 20), 4, border_radius=12)
            screen.blit(overlay, (0, 0))

            # 2. Glowing glassmorphic banner at the top center
            banner_w = 400
            banner_h = 42
            bx = (SCREEN_WIDTH - banner_w) // 2
            by = 38
            # Dark glassmorphic background
            bg_surf = pygame.Surface((banner_w, banner_h), pygame.SRCALPHA)
            bg_surf.fill((16, 16, 28, 190))
            pygame.draw.rect(bg_surf, (245, 60, 120), (0, 0, banner_w, banner_h), 2, border_radius=8)
            screen.blit(bg_surf, (bx, by))

            # LIVE indicator (blinking red circle)
            import time
            if int(time.time() * 2) % 2 == 0:
                pygame.draw.circle(screen, (255, 40, 40), (bx + 26, by + banner_h // 2), 6)
            else:
                pygame.draw.circle(screen, (100, 20, 20), (bx + 26, by + banner_h // 2), 6)

            # Text
            b_font = pygame.font.Font(VT323_PATH, 22)
            ally_name = active_char.upper()
            text_str = f"LIVE SPECTATING: {ally_name}"
            tw = b_font.size(text_str)[0]
            screen.blit(b_font.render(text_str, True, (255, 255, 255)), (bx + 50, by + 8))

            # Cheering hint at the bottom
            h_font = pygame.font.Font(VT323_PATH, 20)
            hint_str = "Press SPACE/ENTER/C to Cheer for your ally!"
            hw = h_font.size(hint_str)[0]
            # Draw shadow
            screen.blit(h_font.render(hint_str, True, (10, 10, 10)), ((SCREEN_WIDTH - hw) // 2 + 1, SCREEN_HEIGHT - 75))
            screen.blit(h_font.render(hint_str, True, (245, 220, 60)), ((SCREEN_WIDTH - hw) // 2, SCREEN_HEIGHT - 76))

            # Restore original self fields
            self.player_score = orig_self_fields["player_score"]
            self.opponent_score = orig_self_fields["opponent_score"]
            self.player_x = orig_self_fields["player_x"]
            self.player_y = orig_self_fields["player_y"]
            self.opp_x = orig_self_fields["opp_x"]
            self.opp_y = orig_self_fields["opp_y"]
            self.ball.center = orig_self_fields["ball_center"]
            self.ball_z = orig_self_fields["ball_z"]
            self.ball_color = orig_self_fields["ball_color"]
            self.ball_trail_color = orig_self_fields["ball_trail_color"]
            self.ball_dash_timer = orig_self_fields["ball_dash_timer"]
            self.super_points_spent = orig_self_fields["super_points_spent"]
            self.countdown_active = orig_self_fields["countdown_active"]
            self.countdown_timer = orig_self_fields["countdown_timer"]
            self.countdown_go_shown = orig_self_fields["countdown_go_shown"]
            self.show_menu = orig_self_fields["show_menu"]
            self.waiting_for_dismiss = orig_self_fields["waiting_for_dismiss"]
            self.end_message = orig_self_fields["end_message"]
            self.extra_balls = orig_self_fields["extra_balls"]


