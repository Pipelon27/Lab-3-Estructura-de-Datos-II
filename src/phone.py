"""
src/phone.py  —  GTA-style phone: HUD compact + map fullscreen
===============================================================
HUD mode: bottom right corner, ≤25% width, 9:16, margins ~2.5%.
Map mode: single 300ms transition — ease-in-out quint + ease-out-back
light rotation; zoom, center shift and crossfade with map at end. Symmetric close.
"""

from __future__ import annotations

import math
import random
import pygame
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable

from settings import SCREEN_WIDTH, SCREEN_HEIGHT, WHITE, BLACK, KEY_MAP


# ═══════════════════════════════════════════════════════════════
#  LAYOUT  — HUD bottom right (≈25% width, 9:16, margins 2–3%)
# ═══════════════════════════════════════════════════════════════

_MARGIN_X = max(8, int(SCREEN_WIDTH * 0.025))
_MARGIN_Y = max(8, int(SCREEN_HEIGHT * 0.025))

_PH_MAX_W = int(SCREEN_WIDTH * 0.25)
_PH_H = int(_PH_MAX_W * 16 / 9)
_MAX_H = SCREEN_HEIGHT - 2 * _MARGIN_Y
if _PH_H > _MAX_H:
    _PH_H = _MAX_H
    _PH_MAX_W = int(_PH_H * 9 / 16)

PHONE_W = _PH_MAX_W
PHONE_H = _PH_H

HUD_PHONE_X = SCREEN_WIDTH - PHONE_W - _MARGIN_X
HUD_PHONE_Y = SCREEN_HEIGHT - PHONE_H - _MARGIN_Y

_BZ     = 8    # bezel
_STAT_H = 28   # status-bar height
_APP_HOME_H = 28  # in-app home chrome row
_PAD    = 12   # content padding
_GAP    = 8    # gap between cards

# content rect inside phone surface (no bottom nav — space for wallpaper / apps)
_CX = _BZ
_CY = _BZ + _STAT_H
_CW = PHONE_W - _BZ * 2
_CH = PHONE_H - _BZ * 2 - _STAT_H

# animation (GTA-style transitions)
_DUR_OPEN  = 0.26   # s
_DUR_CLOSE = 0.26   # s
_DUR_MAP_EXPAND = 0.50   # Step 1: Initial animation (400-550ms)
_DUR_MAP_LOADING = 0.35  # Step 2: Static loading screen (300-400ms)
_DUR_MAP_CONTRACT = 0.50  # Step 3: Inverse exit
# final stretch: map under frame + phone fade (single gesture)
_MAP_BLEND_FRAC = 0.22
_SPLASH_MIN = 1.0
_SPLASH_MAX = 3.0

# overlay: light HUD; darker map / transition
_OVERLAY_ALPHA_HUD = 72
_OVERLAY_ALPHA_MAP_T = 200

# icon colours (home grid)
_ICON_COL = {
    "academic": (80, 140, 255),
    "social": (255, 80, 150),
    "messages": (50, 210, 120),
    "schedule": (255, 180, 40),
    "map": (100, 200, 180),
}


# ═══════════════════════════════════════════════════════════════
#  COLOUR PALETTE
# ═══════════════════════════════════════════════════════════════

PH_BODY      = (10,  10,  16)
PH_SCREEN    = (16,  16,  26)
PH_CARD      = (24,  24,  38)
PH_CARD2     = (30,  30,  48)
PH_STAT_BG   = ( 8,   8,  13)
PH_NAV_BG    = (12,  12,  20)
PH_BD        = (46,  46,  70)
PH_BD_LT     = (68,  68,  98)

PH_CYAN      = ( 90, 195, 255)
PH_CYAN_DIM  = ( 45,  98, 128)
PH_GREEN     = ( 57, 255,  20)  # Neón
PH_AMBER     = (240, 185,  60)
PH_RED       = (220,  60,  80)
PH_PINK      = (255,  95, 145)

PH_TEXT      = (235, 235, 242)
PH_TEXT_S    = (145, 145, 165)
PH_TEXT_D    = ( 85,  85, 108)

PH_ANON_BG   = (28,  14,  14)
PH_ANON_BD   = (90,  35,  35)
PH_MENC_BG   = (14,  26,  38)
PH_MENC_BD   = PH_CYAN

PH_BUB_P     = (45, 100, 195)   # player bubble
PH_BUB_N     = (32,  32,  52)   # NPC bubble

_SC = {"pending": PH_TEXT_D, "in_progress": PH_AMBER, "completed": PH_GREEN}
_SL = {"pending": "Pendiente", "in_progress": "En progreso", "completed": "Completada"}


# ═══════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class SocialPost:
    id: str
    author: str
    author_npc_id: Optional[str]
    content: str
    timestamp: str
    is_anonymous: bool
    likes: int = 0
    mentions: list = field(default_factory=list)
    image_tag: Optional[str] = None
    affects_reputation: bool = False
    reputation_target: Optional[str] = None
    _liked: bool = False


@dataclass
class TextMessage:
    id: str
    sender_npc_id: str
    sender_name: str
    content: str
    timestamp: str
    is_read: bool = False
    is_player: bool = False
    attachment: Optional[str] = None
    reply_options: list = field(default_factory=list)


@dataclass
class AcademicTask:
    id: str
    title: str
    description: str
    issuer: str
    status: str          # "pending" | "in_progress" | "completed"
    deadline: Optional[str] = None
    progress: float = 0.0
    is_main_mission: bool = False


@dataclass
class ScheduleEvent:
    hour: int            # 0-23
    name: str
    location: str
    description: str


# ═══════════════════════════════════════════════════════════════
#  ENUMS
# ═══════════════════════════════════════════════════════════════

class PhoneState(Enum):
    CLOSED  = 0
    OPENING = 1
    OPEN    = 2
    CLOSING = 3


class PhoneApp(Enum):
    ACADEMIC = "academic"
    SOCIAL   = "social"
    MESSAGES = "messages"
    SCHEDULE = "schedule"
    MAP      = "map"


# ═══════════════════════════════════════════════════════════════
#  PHONE
# ═══════════════════════════════════════════════════════════════

class Phone:
    """Smartphone overlay: home grid, optional fullscreen map."""

    _HOME_APPS = [
        (PhoneApp.ACADEMIC, "Academic"),
        (PhoneApp.SOCIAL,   "Social"),
        (PhoneApp.MESSAGES, "Messages"),
        (PhoneApp.SCHEDULE, "Schedule"),
        (PhoneApp.MAP,      "Map"),
    ]

    # ------------------------------------------------------------------
    def __init__(self, screen: pygame.Surface,
                 time_source: Optional[Callable[[], float]] = None,
                 player_name: str = "player"):
        self.screen      = screen
        self.time_source = time_source      # () → float minutes of day
        self.player_name = player_name.lower()

        self.state      = PhoneState.CLOSED
        self._anim_t    = 0.0
        self.is_visible = False

        self._view = "closed"   # home | splash | app | map_loading | map_expand | map | map_contract
        self.current_app   = PhoneApp.ACADEMIC
        self._pending_splash_app: Optional[PhoneApp] = None
        self._splash_t = 0.0
        self._splash_duration = 1.5
        self._map_loading_t = 0.0  # pantalla de carga
        self._map_expand_t = 0.0
        self._map_contract_t = 0.0
        self._map_direct_access = False  # acceso directo por M/View

        self._map_ref = None   # WorldMap — injected from Game after UI init

        self._scroll       = {app: 0 for app in PhoneApp}
        self.social_filter = "all"           # "all" | "anonymous" | "mentions"
        self.active_chat: Optional[str]    = None   # npc_id
        self.active_task: Optional[object] = None

        self._hud_anchor: Optional[pygame.Rect] = None
        self._pending_teleport: Optional[tuple] = None
        self._embedded_map_need_sync = False

        # Data
        self.social_posts:    list[SocialPost]              = []
        self.messages:        dict[str, list[TextMessage]]  = {}
        self.academic_tasks:  list[AcademicTask]            = []
        self.schedule_events: list[ScheduleEvent]           = []
        self.unread_count     = 0
        self.show_unread      = False

        # Off-screen surface for smooth animation
        self._surf = pygame.Surface((PHONE_W, PHONE_H))

        # Fonts
        self._f_stat  = pygame.font.SysFont("arial", 10, bold=True)
        self._f_sec   = pygame.font.SysFont("arial", 12, bold=True)
        self._f_title = pygame.font.SysFont("arial", 12, bold=True)
        self._f_body  = pygame.font.SysFont("arial", 11)
        self._f_sub   = pygame.font.SysFont("arial", 10)
        self._f_badge = pygame.font.SysFont("arial",  9, bold=True)
        try:
            self._f_ico = pygame.font.SysFont("seguiemj", 15)
        except Exception:
            self._f_ico = self._f_sec

        # Click rects (phone-surface local coords, set each frame)
        self._home_icon_rects: list[tuple[pygame.Rect, PhoneApp]] = []
        self._home_btn_rect: Optional[pygame.Rect] = None
        self._task_rects:   list[tuple[pygame.Rect, object]]   = []
        self._post_rects:   list[tuple[pygame.Rect, object]]   = []
        self._like_rects:   list[tuple[pygame.Rect, object]]   = []
        self._chat_rects:   list[tuple[pygame.Rect, str]]      = []
        self._filter_rects: list[tuple[pygame.Rect, str]]      = []
        self._reply_rects:  list[tuple[pygame.Rect, str]]      = []
        self._back_rect: Optional[pygame.Rect]                 = None

        self._map_transition_buf: Optional[pygame.Surface] = None

    # ──────────────────────────────────────────────────────────
    #  PUBLIC API
    # ──────────────────────────────────────────────────────────

    def toggle_phone(self):
        if self.state in (PhoneState.CLOSED, PhoneState.CLOSING):
            self.state = PhoneState.OPENING
            self._anim_t = 0.0
            self.is_visible = True
            self._view = "home"
            self.active_task = None
            self.active_chat = None
            self._map_direct_access = False
            self.selected_app = None
            for app in PhoneApp:
                self._scroll[app] = 0
        else:
            self.state = PhoneState.CLOSING
            self._anim_t = 1.0
    
    def open_map_direct(self):
        """Direct map access (M key / View button) without passing through home.
        
        Correct flow:
        Step 1: map_expand (400-550ms): Phone rotates 0° → 90°, exits HUD to fullscreen
        Step 2: map_loading (300-400ms): Static loading screen in fullscreen
        Step 3: map: Active map without rotation
        """
        if self.state in (PhoneState.CLOSED, PhoneState.CLOSING):
            self.state = PhoneState.OPENING
            self._anim_t = 0.0
            self.is_visible = True
            self._view = "map_expand"  # STEP 1: transition with rotation
            self._map_expand_t = 0.0
            self._map_direct_access = True
            self.active_task = None
            self.active_chat = None
            for app in PhoneApp:
                self._scroll[app] = 0

    def close(self):
        if self.state in (PhoneState.OPEN, PhoneState.OPENING):
            self.state = PhoneState.CLOSING
            self._anim_t = 1.0

    def set_hud_anchor(self, rect: pygame.Rect):
        """Screen-space HUD phone icon — used for open/close animation."""
        self._hud_anchor = pygame.Rect(rect)

    def go_home(self):
        """Leave map / app chrome and show home grid; keeps phone open."""
        self._view = "home"
        self.active_task = None
        self.active_chat = None
        self._map_expand_t = 0.0
        self._map_contract_t = 0.0
        self._map_loading_t = 0.0
        self._pending_splash_app = None
        self._splash_t = 0.0
        self._map_direct_access = False
        self.selected_app = None
        if self._map_ref:
            self._map_ref._confirm_teleport = False
            self._map_ref._teleport_target = None
            self._map_ref.teleport_requested = False

    def push_island_event(self, text: str, duration: float = 3.0):
        """Visual-only hook (optional expansion later)."""
        del text, duration

    def hides_game_hud(self) -> bool:
        """Oculta HUD del juego solo en mapa fullscreen y transiciones del mapa."""
        return self._view in ("map", "map_expand", "map_loading", "map_contract")

    def is_fullscreen(self) -> bool:
        """Compat: mismo criterio que hides_game_hud."""
        return self.hides_game_hud()

    def is_map_fullscreen(self) -> bool:
        """Mapa interactivo a pantalla completa (WorldMap activo)."""
        return self._view == "map"

    def shows_embedded_world_map(self) -> bool:
        """Dibuja WorldMap detrás (mapa estable o mientras contrae el marco)."""
        return self._view in ("map", "map_loading", "map_contract")

    def consume_pending_teleport(self) -> Optional[tuple]:
        t = self._pending_teleport
        self._pending_teleport = None
        return t

    def _start_app_splash(self, app: PhoneApp):
        # Map app → skip splash entirely, go straight to map_expand transition
        if app == PhoneApp.MAP:
            self._view = "map_expand"
            self._map_expand_t = 0.0
            return
        self._pending_splash_app = app
        self._splash_t = 0.0
        self._splash_duration = random.uniform(_SPLASH_MIN, _SPLASH_MAX)
        self._view = "splash"

    def _map_close_to_home(self):
        wm = self._map_ref
        if wm and getattr(wm, "teleport_requested", False):
            self._pending_teleport = (
                wm.teleport_floor,
                int(wm.teleport_pos[0]),
                int(wm.teleport_pos[1]),
            )
            wm.teleport_requested = False
        self._view = "map_contract"
        self._map_contract_t = 0.0

    def _screen_to_local(self, screen_pos: tuple[int, int]) -> tuple[int, int]:
        p = self._ease_out(self._anim_t)
        sx, sy, sw, sh = self._screen_phone_rect(p)
        if sw <= 0 or sh <= 0:
            return 0, 0
        lx = int((screen_pos[0] - sx) * PHONE_W / sw)
        ly = int((screen_pos[1] - sy) * PHONE_H / sh)
        return lx, ly

    def update(self, dt: float):
        if self.state == PhoneState.OPENING:
            self._anim_t = min(1.0, self._anim_t + dt / _DUR_OPEN)
            if self._anim_t >= 1.0:
                self.state = PhoneState.OPEN
        elif self.state == PhoneState.CLOSING:
            self._anim_t = max(0.0, self._anim_t - dt / _DUR_CLOSE)
            if self._anim_t <= 0.0:
                self.state = PhoneState.CLOSED
                self.is_visible = False
                self._view = "closed"
                self._map_expand_t = 0.0

        if self.state == PhoneState.OPEN and self._view == "splash":
            self._splash_t += dt
            if self._splash_t >= self._splash_duration:
                app = self._pending_splash_app
                self._pending_splash_app = None
                # Map app should never reach here (bypassed in _start_app_splash),
                # but keep as safety net with immediate transition (no extra delay).
                if app == PhoneApp.MAP:
                    self._view = "map_expand"
                    self._map_expand_t = 0.0
                else:
                    self.current_app = app or PhoneApp.ACADEMIC
                    self._view = "app"

        # STEP 1: Transition with clockwise rotation (0° → 90°, 400-550ms)
        if self._view == "map_expand":
            self._map_expand_t = min(1.0, self._map_expand_t + dt / _DUR_MAP_EXPAND)
            if self._map_expand_t >= 1.0:
                # Transition completed → show loading screen
                self._view = "map_loading"
                self._map_loading_t = 0.0

        # STEP 2: Loading screen (static centered icon, 300-400ms)
        if self._view == "map_loading":
            self._map_loading_t += dt
            if self._map_loading_t >= _DUR_MAP_LOADING:
                # Loading completed → show map
                self._view = "map"
                self._embedded_map_need_sync = True

        # STEP 3: Contraction (inverse of map_expand, 400-550ms)
        if self._view == "map_contract":
            self._map_contract_t = min(1.0, self._map_contract_t + dt / _DUR_MAP_CONTRACT)
            if self._map_contract_t >= 1.0:
                self.close()

    def consume_embedded_map_initial_sync(self) -> bool:
        if self._embedded_map_need_sync:
            self._embedded_map_need_sync = False
            return True
        return False

    # Data helpers
    def add_social_post(self, post: SocialPost):
        self.social_posts.insert(0, post)

    def add_text_message(self, npc_id: str, msg: TextMessage):
        self.messages.setdefault(npc_id, []).append(msg)
        if not msg.is_read and not msg.is_player:
            self.unread_count += 1
            self.show_unread   = True

    def add_academic_task(self, task: AcademicTask):
        self.academic_tasks.append(task)

    def update_academic_task(self, task_id: str, **kwargs):
        for t in self.academic_tasks:
            if t.id == task_id:
                for k, v in kwargs.items():
                    if hasattr(t, k):
                        setattr(t, k, v)
                break

    def set_schedule_events(self, events: list):
        self.schedule_events = events

    def get_unread_messages_count(self) -> int:
        return sum(1 for ml in self.messages.values()
                   for m in ml if not m.is_read and not m.is_player)

    def mark_messages_read(self, npc_id: str):
        for m in self.messages.get(npc_id, []):
            m.is_read = True

    # ──────────────────────────────────────────────────────────
    #  DRAW
    # ──────────────────────────────────────────────────────────

    def draw(self):
        if not self.is_visible and self.state == PhoneState.CLOSED:
            return

        if self._view == "map":
            return
        
        if self._view == "map_loading":
            self._draw_map_loading_screen()
            return

        if self._view == "map_expand":
            self._draw_map_expand_transition()
            return

        if self._view == "map_contract":
            self._draw_map_contract_transition()
            return

        p = self._ease_out(self._anim_t)

        ov = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, int(_OVERLAY_ALPHA_HUD * p)))
        self.screen.blit(ov, (0, 0))

        self._render_to_surface()

        sx, sy, sw, sh = self._screen_phone_rect(p)
        if sw > 0 and sh > 0:
            scaled = pygame.transform.smoothscale(self._surf, (sw, sh))
            self.screen.blit(scaled, (sx, sy))

    def _draw_map_expand_transition(self):
        """HUD vertical → fullscreen mapa: un solo gesto (quint + back + crossfade)."""
        self._render_to_surface()
        self._draw_unified_map_transition(self._map_expand_t, forward=True)

    def _draw_map_contract_transition(self):
        """Inversa exacta: mapa → marco reaparece, rotación horaria, vuelta al HUD."""
        self._render_to_surface()
        self._draw_unified_map_transition(self._map_contract_t, forward=False)

    def _ensure_map_transition_buffer(self) -> pygame.Surface:
        if self._map_transition_buf is None:
            self._map_transition_buf = pygame.Surface(
                (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA
            )
        return self._map_transition_buf

    def _draw_unified_map_transition(self, t_lin: float, *, forward: bool):
        """t_lin linear 0→1; forward expands (clockwise), False contracts (counter-clockwise).
        
        CLOCKWISE ROTATION CORRECTED:
        - Forward: 0° → 90° (clockwise)
        - Everything rotates: phone, UI, text, icons - NOTHING stays vertical
        """
        t_lin = min(1.0, max(0.0, t_lin))
        # Single spatial clock (ease-in-out quint) for position + scale
        if forward:
            w = self._ease_in_out_quint(t_lin)
            u_rot = t_lin
        else:
            w = self._ease_in_out_quint(1.0 - t_lin)
            u_rot = 1.0 - t_lin

        hx, hy, hw, hh = HUD_PHONE_X, HUD_PHONE_Y, PHONE_W, PHONE_H
        cx0 = hx + hw // 2
        cy0 = hy + hh // 2
        cx = int(cx0 + (SCREEN_WIDTH // 2 - cx0) * w)
        cy = int(cy0 + (SCREEN_HEIGHT // 2 - cy0) * w)
        scale_end = max(
            SCREEN_WIDTH / max(1, PHONE_W),
            SCREEN_HEIGHT / max(1, PHONE_H),
        ) * 1.015
        sc = 1.0 + (scale_end - 1.0) * w
        nw = max(2, int(PHONE_W * sc))
        nh = max(2, int(PHONE_H * sc))

        # CLOCKWISE ROTATION CORRECTED
        # Forward: 0° → 90° (clockwise)
        # Reverse: 90° → 0° (counter-clockwise)
        ang_prog = self._ease_out_back_light(u_rot)
        angle = 90.0 * ang_prog if forward else 90.0 * (1.0 - ang_prog)

        bf = _MAP_BLEND_FRAC
        if forward:
            if t_lin <= 1.0 - bf:
                blend = 0.0
            else:
                blend = self._smoothstep(
                    (t_lin - (1.0 - bf)) / max(1e-6, bf)
                )
        else:
            if t_lin >= bf:
                blend = 0.0
            else:
                blend = 1.0 - self._smoothstep(t_lin / max(1e-6, bf))

        ov = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim = int(40 + 160 * w)
        ov.fill((0, 0, 0, min(235, dim)))
        self.screen.blit(ov, (0, 0))

        # Map under frame (final stretch): scale from "window" to screen
        if self._map_ref and blend > 0.02:
            buf = self._ensure_map_transition_buffer()
            self._map_ref.draw(buf, False)
            map_scale = 0.42 + 0.58 * blend
            mw = max(2, int(SCREEN_WIDTH * map_scale))
            mh = max(2, int(SCREEN_HEIGHT * map_scale))
            map_s = pygame.transform.smoothscale(buf, (mw, mh))
            map_s.set_alpha(int(255 * blend))
            self.screen.blit(
                map_s,
                map_s.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)),
            )

        # ALL PHONE CONTENT ROTATES TOGETHER - NOTHING stays vertical
        scaled = pygame.transform.smoothscale(self._surf, (nw, nh))
        rot = pygame.transform.rotate(scaled, angle)
        phone_alpha = int(255 * (1.0 - 0.96 * blend))
        if phone_alpha < 255:
            rot = rot.convert_alpha()
            rot.set_alpha(phone_alpha)
        rect = rot.get_rect(center=(cx, cy))
        self.screen.blit(rot, rect.topleft)

    def _screen_phone_rect(self, p_anim: float):
        """Del icono HUD → rectángulo final esquina inferior derecha."""
        tx, ty, tw, th = HUD_PHONE_X, HUD_PHONE_Y, PHONE_W, PHONE_H
        if self._hud_anchor and self._hud_anchor.width > 2:
            hx, hy, hw, hh = (
                self._hud_anchor.x,
                self._hud_anchor.y,
                self._hud_anchor.w,
                self._hud_anchor.h,
            )
            tx = int(hx + (HUD_PHONE_X - hx) * p_anim)
            ty = int(hy + (HUD_PHONE_Y - hy) * p_anim)
            tw = int(hw + (PHONE_W - hw) * p_anim)
            th = int(hh + (PHONE_H - hh) * p_anim)
        tw = max(24, tw)
        th = max(42, th)
        return tx, ty, tw, th

    def _render_to_surface(self):
        s = self._surf
        s.fill(PH_BODY)

        # phone body
        self._rrect(s, PH_BODY, pygame.Rect(0, 0, PHONE_W, PHONE_H), 16, PH_BD, 1)
        # screen glass
        self._rrect(s, PH_SCREEN, pygame.Rect(_BZ, _BZ, _CW, PHONE_H - _BZ * 2), 12)

        self._draw_status_bar(s)
        self._draw_dynamic_island(s)

        old = s.get_clip()
        s.set_clip((_CX, _CY, _CW, _CH))

        if self._view == "home":
            self._draw_home_screen(s)
        elif self._view == "splash":
            self._draw_app_splash(s)
        elif self._view == "map_expand":
            self._draw_map_expand_preview(s)
        elif self._view == "map_contract":
            self._draw_map_expand_preview(s)
        elif self._view == "app":
            cy_eff = _CY + _APP_HOME_H
            ch_eff = _CH - _APP_HOME_H
            self._draw_home_chrome(s)
            s.set_clip((_CX, cy_eff, _CW, ch_eff))
            self._draw_content(s, cy_eff, ch_eff)

        s.set_clip(old)

    def _draw_dynamic_island(self, s):
        """Purely decorative pill (no gameplay coupling)."""
        pw = min(_CW - 24, 120)
        ph = 22
        px = _BZ + (_CW - pw) // 2
        py = _BZ + 4
        pill = pygame.Rect(px, py, pw, ph)
        pygame.draw.rect(s, (6, 6, 10), pill, border_radius=ph // 2)
        pygame.draw.rect(s, PH_BD, pill, border_radius=ph // 2, width=1)

    def _draw_home_screen(self, s):
        """Wallpaper + app icon grid."""
        r = pygame.Rect(_CX, _CY, _CW, _CH)
        for y in range(r.h):
            t = y / max(1, r.h)
            c = (
                int(18 + t * 40),
                int(22 + t * 30),
                int(48 + t * 25),
            )
            pygame.draw.line(s, c, (r.x, r.y + y), (r.right - 1, r.y + y))

        cols = 4
        labels = ["Academic", "Social", "Msgs", "Schedule", "Map"]
        apps_order = [
            PhoneApp.ACADEMIC,
            PhoneApp.SOCIAL,
            PhoneApp.MESSAGES,
            PhoneApp.SCHEDULE,
            PhoneApp.MAP,
        ]
        pad_x = 14
        pad_y = 28
        cell_w = (_CW - pad_x * 2) // cols
        cell_h = 88
        self._home_icon_rects = []

        mouse_pos = pygame.mouse.get_pos()
        lx, ly = self._screen_to_local(mouse_pos)

        for idx, app in enumerate(apps_order):
            row, col = divmod(idx, cols)
            ix = _CX + pad_x + col * cell_w
            iy = _CY + pad_y + row * (cell_h + 18)
            ir = pygame.Rect(ix + 8, iy, cell_w - 16, 62)
            col_rgb = _ICON_COL.get(app.value, PH_CYAN)
            pygame.draw.rect(s, col_rgb, ir, border_radius=14)
            
            hit = pygame.Rect(ir.x - 4, iy - 4, ir.w + 8, ir.height + 22)
            self._home_icon_rects.append((hit, app))

            is_hovered = hit.collidepoint((lx, ly))
            is_selected = getattr(self, "selected_app", None) == app
            
            bd_col = PH_GREEN if (is_hovered or is_selected) else PH_BD
            bd_w = 3 if (is_hovered or is_selected) else 1
            pygame.draw.rect(s, bd_col, ir, border_radius=14, width=bd_w)

            self._draw_app_glyph(s, app, ir)
            lb = self._f_sub.render(labels[idx], True, PH_TEXT)
            s.blit(lb, lb.get_rect(midtop=(ir.centerx, ir.bottom + 4)))

            if app == PhoneApp.MESSAGES:
                u = self.get_unread_messages_count()
                if u > 0:
                    self._badge(s, str(min(u, 9)), ir.right - 4, ir.y + 4)
            if app == PhoneApp.SOCIAL:
                mc = self._mention_post_count()
                if mc > 0:
                    self._badge(s, str(min(mc, 9)), ir.right - 4, ir.y + 4)

    def _mention_post_count(self) -> int:
        player = self.player_name
        return sum(
            1
            for p in self.social_posts
            if player in [m.lower() for m in p.mentions]
        )

    def _draw_app_glyph(self, s, app: PhoneApp, ir: pygame.Rect):
        cx, cy = ir.center
        if app == PhoneApp.ACADEMIC:
            pygame.draw.rect(s, WHITE, (cx - 14, cy - 10, 28, 18), border_radius=3)
            pygame.draw.line(s, _ICON_COL["academic"], (cx - 8, cy + 2), (cx + 8, cy + 2), 2)
        elif app == PhoneApp.SOCIAL:
            pygame.draw.circle(s, WHITE, (cx - 6, cy), 7)
            pygame.draw.circle(s, WHITE, (cx + 8, cy), 9)
        elif app == PhoneApp.MESSAGES:
            env = pygame.Rect(cx - 14, cy - 8, 28, 20)
            pygame.draw.rect(s, WHITE, env, border_radius=3)
            pygame.draw.polygon(s, _ICON_COL["messages"], [(cx, cy - 2), (cx - 6, cy + 6), (cx + 6, cy + 6)])
        elif app == PhoneApp.SCHEDULE:
            for i in range(3):
                for j in range(3):
                    pygame.draw.rect(
                        s,
                        WHITE,
                        (cx - 12 + j * 8, cy - 10 + i * 7, 6, 5),
                        border_radius=1,
                    )
        elif app == PhoneApp.MAP:
            pygame.draw.circle(s, WHITE, (cx, cy + 4), 12, 2)
            pygame.draw.polygon(s, WHITE, [(cx, cy - 10), (cx - 5, cy - 4), (cx + 5, cy - 4)])

    def _draw_app_splash(self, s):
        """Full glass-area splash before app content."""
        app = self._pending_splash_app or self.current_app
        r = pygame.Rect(_CX, _CY, _CW, _CH)
        col = _ICON_COL.get(app.value, PH_CARD)
        for y in range(r.h):
            t = y / max(1, r.h)
            c = (int(col[0] * t), int(col[1] * t), int(col[2] * t))
            pygame.draw.line(s, c, (r.x, r.y + y), (r.right - 1, r.y + y))

        ir = r.inflate(-80, -120)
        ir.center = r.center
        pygame.draw.rect(s, WHITE, ir, border_radius=20)
        self._draw_app_glyph(s, app, ir)
        name = next((lb for a, lb in self._HOME_APPS if a == app), "App")
        tt = self._f_sec.render(name, True, PH_TEXT)
        s.blit(tt, tt.get_rect(midbottom=(r.centerx, r.bottom - 40)))

    def _draw_map_expand_preview(self, s):
        """Visual held inside phone while map prepares fullscreen."""
        r = pygame.Rect(_CX, _CY, _CW, _CH)
        p = self._ease_out(self._map_expand_t)
        inset = int(40 * (1.0 - p))
        inner = r.inflate(-inset * 2, -inset * 2)
        pygame.draw.rect(s, (12, 28, 32), inner, border_radius=12)
        te = self._f_sec.render("Opening map…", True, PH_CYAN)
        s.blit(te, te.get_rect(center=inner.center))

    def _draw_home_chrome(self, s):
        """Top row with Home — returns to grid."""
        bar = pygame.Rect(_CX, _CY, _CW, _APP_HOME_H)
        pygame.draw.rect(s, PH_STAT_BG, bar)
        pygame.draw.line(s, PH_BD, bar.bottomleft, bar.bottomright)

        btn = pygame.Rect(_CX + 8, _CY + 4, 72, _APP_HOME_H - 8)
        self._rrect(s, PH_CARD2, btn, 6)
        ht = self._f_sub.render("⌂ Home", True, PH_CYAN)
        s.blit(ht, ht.get_rect(center=btn.center))
        self._home_btn_rect = btn

    def _draw_map_loading_screen(self):
        """Loading screen: large centered STATIC icon. No spinner, no animation.
        
        Step 2 of sequence: appears after rotation (map_expand),
        disappears when map is ready. Duration: 300-400ms.
        """
        # Total black background
        self.screen.fill((0, 0, 0))
        
        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2
        
        # STATIC and large map icon — perfectly centered, NO rotation
        icon_size = 160  # large, occupies significant screen portion
        icon_surf = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
        half = icon_size // 2
        
        # Outer circle (compass)
        pygame.draw.circle(icon_surf, PH_CYAN, (half, half), half - 6, 4)
        # Inner cross
        pygame.draw.line(icon_surf, PH_CYAN, (half, 12), (half, half + 16), 4)
        pygame.draw.line(icon_surf, PH_CYAN, (12, half), (icon_size - 12, half), 3)
        # North triangle (compass tip) — points up
        pygame.draw.polygon(icon_surf, PH_CYAN, [
            (half, 4),
            (half - 10, 26),
            (half + 10, 26),
        ])
        # Center dot
        pygame.draw.circle(icon_surf, PH_CYAN, (half, half), 6)
        
        # Draw icon perfectly centered on screen
        icon_rect = icon_surf.get_rect(center=(cx, cy))
        self.screen.blit(icon_surf, icon_rect.topleft)

    # The map_back_button method has been removed as per request

    def _draw_content(self, s, cy: int, ch: int):
        {
            PhoneApp.ACADEMIC: self._app_academic,
            PhoneApp.SOCIAL:   self._app_social,
            PhoneApp.MESSAGES: self._app_messages,
            PhoneApp.SCHEDULE: self._app_schedule,
        }.get(self.current_app, lambda *_: None)(s, _CX, cy, _CW, ch)

    # ── Status bar ─────────────────────────────────────────────────

    def _draw_status_bar(self, s):
        pygame.draw.rect(s, PH_STAT_BG, (_BZ, _BZ, _CW, _STAT_H))

        if self.time_source:
            mins = int(self.time_source()) % 1440
            h, m = divmod(mins, 60)
            sfx = "am" if h < 12 else "pm"
            h12 = h % 12 or 12
            ts = f"{h12}:{m:02d}{sfx}"
        else:
            ts = "00:00"

        t = self._f_stat.render(ts, True, PH_TEXT)
        s.blit(t, t.get_rect(midleft=(_BZ + 4, _BZ + _STAT_H // 2)))

        sig = self._f_stat.render("●●●  ▓", True, PH_TEXT_S)
        s.blit(sig, sig.get_rect(midright=(_BZ + _CW - 4, _BZ + _STAT_H // 2)))

    # ══════════════════════════════════════════════════════════
    #  APP — ACADEMIC
    # ══════════════════════════════════════════════════════════

    def _app_academic(self, s, cx, cy, cw, ch):
        self._task_rects = []
        self._back_rect  = None

        if self.active_task:
            self._academic_detail(s, cx, cy, cw, ch, self.active_task)
            return

        y = cy + _PAD
        self._text(s, "Portal Académico", self._f_sec, PH_CYAN, cx + _PAD, y)
        y += 16

        p = sum(1 for t in self.academic_tasks if t.status == "pending")
        i = sum(1 for t in self.academic_tasks if t.status == "in_progress")
        d = sum(1 for t in self.academic_tasks if t.status == "completed")
        self._text(s, f"{p} pend.  {i} en progreso  {d} hechas",
                   self._f_sub, PH_TEXT_S, cx + _PAD, y)
        y += 13

        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP

        sc = self._scroll[PhoneApp.ACADEMIC]
        IH = 58
        yoff = y - sc

        for task in self.academic_tasks:
            if yoff + IH < cy:
                yoff += IH + _GAP
                continue
            if yoff > cy + ch:
                break

            card = pygame.Rect(cx + _PAD, yoff, cw - _PAD * 2, IH)
            self._rrect(s, PH_CARD, card, 8)

            col = _SC.get(task.status, PH_TEXT_D)
            pygame.draw.rect(s, col, (card.x, card.y + 4, 3, IH - 8), border_radius=2)

            tx, ty2 = card.x + 10, card.y + 6
            self._clip_text(s, task.title, self._f_title, PH_TEXT, tx, ty2, cw - _PAD * 2 - 20)
            ty2 += 14
            self._text(s, f"de {task.issuer}", self._f_sub, PH_TEXT_S, tx, ty2)

            if task.deadline:
                dl = self._f_sub.render(f"⏰ {task.deadline}", True, PH_AMBER)
                s.blit(dl, (card.right - dl.get_width() - 6, card.y + 6))

            bx2, bary = tx, card.bottom - 10
            bw = card.w - 20
            pygame.draw.rect(s, PH_BD, (bx2, bary, bw, 4), border_radius=2)
            fw = int(bw * max(0.0, min(1.0, task.progress)))
            if fw > 0:
                pygame.draw.rect(s, col, (bx2, bary, fw, 4), border_radius=2)
            if task.status == "completed":
                ck = self._f_sub.render("✓", True, PH_GREEN)
                s.blit(ck, (card.right - 14, card.bottom - 14))

            self._task_rects.append((card, task))
            yoff += IH + _GAP

    def _academic_detail(self, s, cx, cy, cw, ch, task):
        br = pygame.Rect(cx + _PAD, cy + _PAD, 54, 20)
        self._rrect(s, PH_CARD2, br, 6)
        bk = self._f_sub.render("← Volver", True, PH_CYAN)
        s.blit(bk, bk.get_rect(center=br.center))
        self._back_rect = br

        y = cy + _PAD + 28
        col = _SC.get(task.status, PH_TEXT_D)
        slbl = _SL.get(task.status, "")
        sr = pygame.Rect(cx + _PAD, y, 82, 18)
        pygame.draw.rect(s, col, sr, border_radius=4, width=1)
        sl = self._f_sub.render(slbl, True, col)
        s.blit(sl, sl.get_rect(center=sr.center))
        y += 24

        self._text(s, task.title, self._f_title, PH_TEXT, cx + _PAD, y)
        y += 16
        self._text(s, f"Por: {task.issuer}", self._f_sub, PH_TEXT_S, cx + _PAD, y)
        y += 13
        if task.deadline:
            self._text(s, f"Entrega: {task.deadline}", self._f_sub, PH_AMBER, cx + _PAD, y)
            y += 13
        y += _GAP
        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP
        y = self._wrap_text(s, task.description, self._f_body, PH_TEXT_S,
                            cx + _PAD, y, cw - _PAD * 2, 13)
        y += _GAP
        if task.status != "completed":
            self._text(s, f"Progreso: {int(task.progress * 100)}%",
                       self._f_sub, PH_TEXT_S, cx + _PAD, y)
            y += 13
            bw = cw - _PAD * 2
            pygame.draw.rect(s, PH_BD, (cx + _PAD, y, bw, 6), border_radius=3)
            fw = int(bw * task.progress)
            if fw > 0:
                pygame.draw.rect(s, col, (cx + _PAD, y, fw, 6), border_radius=3)

    # ══════════════════════════════════════════════════════════
    #  APP — SOCIAL
    # ══════════════════════════════════════════════════════════

    def _app_social(self, s, cx, cy, cw, ch):
        self._post_rects  = []
        self._like_rects  = []
        self._filter_rects= []

        y = cy + _PAD
        self._text(s, "EscuelaNet", self._f_sec, PH_PINK, cx + _PAD, y)
        y += 16

        # Filter tabs
        filters = [("all", "Todo"), ("anonymous", "Anónimos"), ("mentions", "Menciones")]
        tw = (cw - _PAD * 2) // len(filters)
        for i, (fid, flbl) in enumerate(filters):
            tr = pygame.Rect(cx + _PAD + i * tw, y, tw - 2, 18)
            active_f = (fid == self.social_filter)
            self._rrect(s, PH_CARD2 if active_f else PH_CARD, tr, 5)
            if active_f:
                pygame.draw.rect(s, PH_PINK, tr, border_radius=5, width=1)
            fl = self._f_sub.render(flbl, True, PH_PINK if active_f else PH_TEXT_S)
            s.blit(fl, fl.get_rect(center=tr.center))
            self._filter_rects.append((tr, fid))
        y += 24

        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP

        player = self.player_name
        posts = [p for p in self.social_posts if
                 self.social_filter == "all" or
                 (self.social_filter == "anonymous" and p.is_anonymous) or
                 (self.social_filter == "mentions" and
                  player in [m.lower() for m in p.mentions])]

        sc = self._scroll[PhoneApp.SOCIAL]
        PH = 72
        yoff = y - sc

        for post in posts:
            if yoff + PH < cy:
                yoff += PH + _GAP
                continue
            if yoff > cy + ch:
                break

            is_m = player in [m.lower() for m in post.mentions]
            if is_m:
                bg, bd = PH_MENC_BG, PH_MENC_BD
            elif post.is_anonymous:
                bg, bd = PH_ANON_BG, PH_ANON_BD
            else:
                bg, bd = PH_CARD, PH_BD

            card = pygame.Rect(cx + _PAD, yoff, cw - _PAD * 2, PH)
            self._rrect(s, bg, card, 8, bd, 1)

            # Author
            a_str = "Anónimo" if post.is_anonymous else post.author
            a_col = PH_TEXT_D if post.is_anonymous else PH_TEXT
            at = self._f_title.render(a_str, True, a_col)
            s.blit(at, (card.x + 8, card.y + 6))

            # Timestamp
            ts_s = self._f_sub.render(post.timestamp, True, PH_TEXT_D)
            s.blit(ts_s, (card.right - ts_s.get_width() - 6, card.y + 7))

            # Content
            self._clip_text(s, post.content, self._f_body, PH_TEXT,
                            card.x + 8, card.y + 20, cw - _PAD * 2 - 16)

            # Second line of content
            if len(post.content) > 38:
                cont2 = post.content[38:72] + ("…" if len(post.content) > 72 else "")
                self._clip_text(s, cont2, self._f_body, PH_TEXT_S,
                                card.x + 8, card.y + 32, cw - _PAD * 2 - 16)

            # Like btn
            lk_col = PH_PINK if post._liked else PH_TEXT_D
            lk = self._f_sub.render(f"♥ {post.likes}", True, lk_col)
            lk_r = pygame.Rect(card.x + 8, card.bottom - 16, 48, 14)
            s.blit(lk, lk_r.topleft)
            self._like_rects.append((lk_r, post))

            if is_m:
                mb = self._f_sub.render("@ te mencionó", True, PH_CYAN)
                s.blit(mb, (card.right - mb.get_width() - 6, card.bottom - 16))

            self._post_rects.append((card, post))
            yoff += PH + _GAP

    # ══════════════════════════════════════════════════════════
    #  APP — MESSAGES
    # ══════════════════════════════════════════════════════════

    def _app_messages(self, s, cx, cy, cw, ch):
        self._chat_rects  = []
        self._back_rect   = None
        self._reply_rects = []

        y = cy + _PAD
        self._text(s, "Mensajes", self._f_sec, PH_CYAN, cx + _PAD, y)
        y += 16
        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP

        if self.active_chat is not None:
            self._chat_view(s, cx, y, cw, cy + ch - y)
        else:
            self._conv_list(s, cx, y, cw, cy + ch - y)

    def _conv_list(self, s, cx, y, cw, avail_h):
        if not self.messages:
            self._text(s, "Sin mensajes.", self._f_body, PH_TEXT_D, cx + _PAD, y + 20)
            return

        sc = self._scroll[PhoneApp.MESSAGES]
        IH = 52
        yoff = y - sc

        for npc_id, msgs in self.messages.items():
            if not msgs:
                continue
            last   = msgs[-1]
            unread = sum(1 for m in msgs if not m.is_read and not m.is_player)

            card = pygame.Rect(cx + _PAD, yoff, cw - _PAD * 2, IH)
            if card.bottom < y or card.top > y + avail_h:
                yoff += IH + _GAP
                continue

            self._rrect(s, PH_CARD2 if unread else PH_CARD, card, 8)

            # Avatar
            avc = (card.x + 22, card.centery)
            pygame.draw.circle(s, PH_CYAN_DIM, avc, 16)
            init = self._f_title.render(last.sender_name[0].upper(), True, PH_TEXT)
            s.blit(init, init.get_rect(center=avc))

            # Name + preview
            self._text(s, last.sender_name, self._f_title, PH_TEXT, card.x + 44, card.y + 7)
            prev = last.content[:24] + ("…" if len(last.content) > 24 else "")
            self._text(s, prev, self._f_sub, PH_TEXT_S, card.x + 44, card.y + 22)

            if unread > 0:
                self._badge(s, str(min(unread, 9)), card.right - 18, card.y + 8)

            self._chat_rects.append((card, npc_id))
            yoff += IH + _GAP

    def _chat_view(self, s, cx, y, cw, avail_h):
        msgs = self.messages.get(self.active_chat, [])
        npc_name = msgs[0].sender_name if msgs else "Chat"

        # Back btn
        br = pygame.Rect(cx + _PAD, y, 40, 18)
        self._rrect(s, PH_CARD2, br, 5)
        bk = self._f_sub.render("←", True, PH_CYAN)
        s.blit(bk, bk.get_rect(center=br.center))
        self._back_rect = br

        nm = self._f_title.render(npc_name, True, PH_TEXT)
        s.blit(nm, nm.get_rect(midleft=(br.right + 6, br.centery)))
        y += 26

        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP

        # Reply options at bottom
        reply_opts = []
        if msgs:
            last_npc = [m for m in msgs if not m.is_player]
            if last_npc:
                reply_opts = last_npc[-1].reply_options or []

        reply_h = (len(reply_opts) * 22 + _PAD) if reply_opts else 0
        chat_area_h = avail_h - (y - (y)) - reply_h  # fix: use full remaining
        chat_area_h = avail_h - reply_h

        # Bubbles (scroll from bottom up)
        sc = self._scroll[PhoneApp.MESSAGES]
        BH = 30
        total = len(msgs) * (BH + _GAP)
        start_y = y + max(0, chat_area_h - total) - sc

        for msg in msgs:
            my = start_y
            mw = cw - _PAD * 2 - 16
            is_p = msg.is_player
            bg   = PH_BUB_P if is_p else PH_BUB_N
            words = msg.content.split()
            line, lines = "", []
            for w in words:
                test = (line + " " + w).strip()
                if self._f_body.size(test)[0] <= mw - 16:
                    line = test
                else:
                    if line:
                        lines.append(line)
                    line = w
            if line:
                lines.append(line)

            bh = max(BH, len(lines) * 13 + 10)
            bw = min(mw, max(60, max((self._f_body.size(l)[0] for l in lines), default=60) + 16))

            if is_p:
                bx = cx + cw - _PAD - bw
            else:
                bx = cx + _PAD

            bub = pygame.Rect(bx, my, bw, bh)
            corner = 10
            self._rrect(s, bg, bub, corner)

            for li, ln in enumerate(lines):
                lt = self._f_body.render(ln, True, PH_TEXT)
                s.blit(lt, (bub.x + 8, bub.y + 5 + li * 13))

            # Timestamp
            ts_s = self._f_sub.render(msg.timestamp, True, PH_TEXT_D)
            if is_p:
                s.blit(ts_s, (bub.left - ts_s.get_width() - 4, bub.centery))
            else:
                s.blit(ts_s, (bub.right + 4, bub.centery))

            start_y += bh + _GAP

        # Reply options
        if reply_opts:
            ry = y + chat_area_h
            self._reply_rects = []
            for i, opt in enumerate(reply_opts[:3]):
                rr = pygame.Rect(cx + _PAD, ry + i * 22, cw - _PAD * 2, 20)
                self._rrect(s, PH_CARD2, rr, 5, PH_CYAN, 1)
                ot = self._f_sub.render(opt[:38], True, PH_CYAN)
                s.blit(ot, ot.get_rect(midleft=(rr.x + 6, rr.centery)))
                self._reply_rects.append((rr, opt))

    # ══════════════════════════════════════════════════════════
    #  APP — SCHEDULE
    # ══════════════════════════════════════════════════════════

    def _app_schedule(self, s, cx, cy, cw, ch):
        y = cy + _PAD
        self._text(s, "Horario Escolar", self._f_sec, PH_CYAN, cx + _PAD, y)
        y += 16
        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP

        cur_mins = int(self.time_source()) if self.time_source else -1
        cur_h    = cur_mins // 60 if cur_mins >= 0 else -1

        if not self.schedule_events:
            self._text(s, "Sin eventos programados.", self._f_body, PH_TEXT_D, cx + _PAD, y + 20)
            return

        sc   = self._scroll[PhoneApp.SCHEDULE]
        EH   = 52
        yoff = y - sc

        # Find current / next event
        cur_idx  = -1
        next_idx = -1
        for ei, ev in enumerate(self.schedule_events):
            if ev.hour <= cur_h:
                cur_idx = ei
            elif next_idx == -1:
                next_idx = ei

        for ei, ev in enumerate(self.schedule_events):
            if yoff + EH < cy:
                yoff += EH + _GAP
                continue
            if yoff > cy + ch:
                break

            is_cur  = (ei == cur_idx)
            is_next = (ei == next_idx)

            bd_col = PH_CYAN if is_cur else (PH_AMBER if is_next else PH_BD)
            bg_col = (16, 28, 40) if is_cur else ((26, 24, 14) if is_next else PH_CARD)

            card = pygame.Rect(cx + _PAD, yoff, cw - _PAD * 2, EH)
            self._rrect(s, bg_col, card, 8, bd_col, 1)

            # Hour badge
            h12 = ev.hour % 12 or 12
            sfx = "am" if ev.hour < 12 else "pm"
            hr_str = f"{h12}{sfx}"
            hr_s = self._f_title.render(hr_str, True, bd_col)
            s.blit(hr_s, (card.x + 8, card.y + 6))

            # Event name + location
            self._text(s, ev.name, self._f_title, PH_TEXT, card.x + 56, card.y + 6)
            self._text(s, ev.location, self._f_sub, PH_TEXT_S, card.x + 56, card.y + 22)

            if ev.description:
                self._clip_text(s, ev.description, self._f_sub, PH_TEXT_D,
                                card.x + 56, card.y + 34, cw - _PAD * 2 - 60)

            if is_cur:
                tag = self._f_badge.render("AHORA", True, PH_CYAN)
                s.blit(tag, (card.right - tag.get_width() - 6, card.y + 6))
            elif is_next:
                tag = self._f_badge.render("PRÓXIMO", True, PH_AMBER)
                s.blit(tag, (card.right - tag.get_width() - 6, card.y + 6))

            yoff += EH + _GAP

    # ══════════════════════════════════════════════════════════
    #  HUD ICON  (called from ui.py draw_hud)
    # ══════════════════════════════════════════════════════════

    def draw_hud_icon(self, screen: pygame.Surface, rect: pygame.Rect,
                      unread: int = 0):
        """Draw phone HUD icon (call this from UI.draw_hud)."""
        # Body
        pygame.draw.rect(screen, (22, 22, 32), rect, border_radius=7)
        pygame.draw.rect(screen, PH_CYAN, rect, border_radius=7, width=2)
        # Screen
        scr = rect.inflate(-8, -10)
        scr.y += 2
        pygame.draw.rect(screen, (12, 12, 20), scr, border_radius=4)
        # Home button dot
        hb_x, hb_y = rect.centerx, rect.bottom - 5
        pygame.draw.circle(screen, PH_CYAN, (hb_x, hb_y), 3)
        # Badge
        if unread > 0:
            bx = rect.right - 8
            by = rect.top - 2
            pygame.draw.circle(screen, PH_RED, (bx, by), 7)
            bt = pygame.font.SysFont("arial", 9, bold=True).render(
                str(min(unread, 9)), True, WHITE)
            screen.blit(bt, bt.get_rect(center=(bx, by)))
        # Hover glow
        if rect.collidepoint(pygame.mouse.get_pos()):
            glow = rect.inflate(6, 6)
            pygame.draw.rect(screen, (255, 220, 80), glow, border_radius=9, width=2)

    # ══════════════════════════════════════════════════════════
    #  INPUT HANDLING
    # ══════════════════════════════════════════════════════════

    def handle_controller(self, controller):
        """Handle controller input for the phone."""
        if not self.is_visible:
            return

        if controller.is_cancel_pressed():
            if self._view == "app":
                self.go_home()
            elif self._view == "map":
                self._map_close_to_home()
            else:
                self.close()
            return
            
        if self._view == "home":
            apps_order = [
                PhoneApp.ACADEMIC, PhoneApp.SOCIAL, PhoneApp.MESSAGES,
                PhoneApp.SCHEDULE, PhoneApp.MAP
            ]
            
            menu_h = controller.get_menu_direction_horizontal()
            if menu_h != 0:
                if getattr(self, "selected_app", None) not in apps_order:
                    self.selected_app = apps_order[0] if menu_h > 0 else apps_order[-1]
                else:
                    idx = apps_order.index(self.selected_app)
                    idx = (idx + menu_h) % len(apps_order)
                    self.selected_app = apps_order[idx]
                
            if controller.is_confirm_pressed() and getattr(self, "selected_app", None) in apps_order:
                self._scroll[self.selected_app] = 0
                self._start_app_splash(self.selected_app)
                
        elif self._view == "app":
            menu_v = controller.get_menu_direction()
            if menu_v == -1:  # up
                self._scroll[self.current_app] = max(0, self._scroll[self.current_app] - 30)
            elif menu_v == 1: # down
                self._scroll[self.current_app] += 30

    def handle_input(self, event: pygame.event.Event) -> bool:
        """Return True if event was consumed."""
        if not self.is_visible:
            return False

        if self._view == "map" and self._map_ref:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._map_close_to_home()
                return True
            # Direct exit from map without clicking button (handled by world_map.py ESC/B button)
            close = self._map_ref.handle_event(event)
            if close:
                self._map_close_to_home()
            return True

        if self._view in ("map_expand", "map_loading", "map_contract"):
            return True

        if event.type == pygame.MOUSEWHEEL:
            if self._view == "app":
                self._scroll[self.current_app] = max(
                    0, self._scroll[self.current_app] - event.y * 20
                )
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self._on_click(event.pos)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
                return True
            if event.key == KEY_MAP:
                # Acceso directo al mapa (M)
                if self.state == PhoneState.CLOSED:
                    # Teléfono cerrado → abrirlo con acceso directo al mapa
                    self.open_map_direct()
                    return True
                elif self._view in ("home", "app", "splash"):
                    # Teléfono abierto en HUD → iniciar transición a mapa
                    self._view = "map_expand"
                    self._map_expand_t = 0.0
                    self.active_task = None
                    self.active_chat = None
                    return True
                elif self._view == "map":
                    # Mapa abierto → cerrar
                    self._map_close_to_home()
                    return True
            if self._view == "app":
                if event.key == pygame.K_UP:
                    self._scroll[self.current_app] = max(
                        0, self._scroll[self.current_app] - 30
                    )
                    return True
                if event.key == pygame.K_DOWN:
                    self._scroll[self.current_app] += 30
                    return True

        return False

    def _on_click(self, screen_pos: tuple) -> bool:
        """Map screen click to phone-local coords and dispatch."""
        if self.state != PhoneState.OPEN:
            return False

        if self._view in ("splash", "map_loading", "map_expand", "map_contract"):
            return True

        p = self._ease_out(self._anim_t)
        sx, sy, sw, sh = self._screen_phone_rect(p)
        phone_rect = pygame.Rect(sx, sy, sw, sh)
        if not phone_rect.collidepoint(screen_pos):
            self.close()
            return True

        lx, ly = self._screen_to_local(screen_pos)

        if self._view == "home":
            for rect, app in self._home_icon_rects:
                if rect.collidepoint((lx, ly)):
                    self._scroll[app] = 0
                    # Reset selected app when using mouse
                    self.selected_app = None
                    self._start_app_splash(app)
                    return True
            return True

        if self._view == "app":
            if self._home_btn_rect and self._home_btn_rect.collidepoint((lx, ly)):
                self.go_home()
                return True

            if self._back_rect and self._back_rect.collidepoint((lx, ly)):
                self.active_task = None
                self.active_chat = None
                return True

            if self.current_app == PhoneApp.ACADEMIC:
                for rect, task in self._task_rects:
                    if rect.collidepoint((lx, ly)):
                        self.active_task = task
                        return True

            elif self.current_app == PhoneApp.SOCIAL:
                for rect, fid in self._filter_rects:
                    if rect.collidepoint((lx, ly)):
                        self.social_filter = fid
                        self._scroll[PhoneApp.SOCIAL] = 0
                        return True
                for rect, post in self._like_rects:
                    if rect.collidepoint((lx, ly)):
                        if not post._liked:
                            post._liked = True
                            post.likes += 1
                        return True

            elif self.current_app == PhoneApp.MESSAGES:
                for rect, npc_id in self._chat_rects:
                    if rect.collidepoint((lx, ly)):
                        self.active_chat = npc_id
                        self.mark_messages_read(npc_id)
                        self._scroll[PhoneApp.MESSAGES] = 0
                        return True
                for rect, opt in self._reply_rects:
                    if rect.collidepoint((lx, ly)):
                        self._send_reply(opt)
                        return True

        return True

    def _send_reply(self, text: str):
        """Record a player reply in the active chat."""
        if not self.active_chat:
            return
        npc_msgs = self.messages.get(self.active_chat, [])
        reply_id = f"reply_{len(npc_msgs)}"
        msg = TextMessage(
            id=reply_id,
            sender_npc_id="player",
            sender_name="Tú",
            content=text,
            timestamp="ahora",
            is_read=True,
            is_player=True,
        )
        self.messages.setdefault(self.active_chat, []).append(msg)

    # ══════════════════════════════════════════════════════════
    #  UTILITIES
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _ease_out(t: float) -> float:
        return 1.0 - (1.0 - t) ** 3

    @staticmethod
    def _ease_in_out_quint(t: float) -> float:
        """Ease-in-out cúbica/quintica — arranque y aterrizaje suaves."""
        t = min(1.0, max(0.0, t))
        if t < 0.5:
            return 16.0 * t * t * t * t * t
        p = -2.0 * t + 2.0
        return 1.0 - 0.5 * p * p * p * p * p

    @staticmethod
    def _ease_out_back_light(t: float) -> float:
        """Ease-out-back leve: micro pasada de inercia y retorno a 1 (≈ -93° → -90°)."""
        t = min(1.0, max(0.0, t))
        c1 = 1.45
        u = t - 1.0
        return 1.0 + u * u * ((c1 + 1.0) * u + c1)

    @staticmethod
    def _smoothstep(t: float) -> float:
        t = min(1.0, max(0.0, t))
        return t * t * (3.0 - 2.0 * t)

    def _rrect(self, surf, color, rect, radius, border_color=None, bw=0):
        pygame.draw.rect(surf, color, rect, border_radius=radius)
        if border_color and bw > 0:
            pygame.draw.rect(surf, border_color, rect,
                             border_radius=radius, width=bw)

    def _text(self, surf, text, font, color, x, y):
        t = font.render(str(text), True, color)
        surf.blit(t, (x, y))

    def _clip_text(self, surf, text, font, color, x, y, max_w):
        t = font.render(str(text), True, color)
        if t.get_width() > max_w:
            clip = surf.get_clip()
            surf.set_clip(pygame.Rect(x, y, max_w, t.get_height()).clip(clip))
            surf.blit(t, (x, y))
            surf.set_clip(clip)
        else:
            surf.blit(t, (x, y))

    def _wrap_text(self, surf, text, font, color, x, y, max_w, line_h) -> int:
        words = str(text).split()
        line = ""
        for w in words:
            test = (line + " " + w).strip()
            if font.size(test)[0] <= max_w:
                line = test
            else:
                if line:
                    self._text(surf, line, font, color, x, y)
                    y += line_h
                line = w
        if line:
            self._text(surf, line, font, color, x, y)
            y += line_h
        return y

    def _badge(self, surf, text, cx, cy):
        pygame.draw.circle(surf, PH_RED, (cx, cy), 7)
        t = self._f_badge.render(str(text), True, WHITE)
        surf.blit(t, t.get_rect(center=(cx, cy)))
