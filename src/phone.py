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

from settings import SCREEN_WIDTH, SCREEN_HEIGHT, WHITE, BLACK, KEY_MAP, VT323_PATH


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

# Display target (Large & Centered)
DISPLAY_PHONE_H = int(SCREEN_HEIGHT * 0.85)
DISPLAY_PHONE_W = int(DISPLAY_PHONE_H * 9 / 16)
DISPLAY_PHONE_X = (SCREEN_WIDTH - DISPLAY_PHONE_W) // 2
DISPLAY_PHONE_Y = (SCREEN_HEIGHT - DISPLAY_PHONE_H) // 2

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
_OVERLAY_ALPHA_HUD = 180
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

PH_BUB_P     = ( 20,  60,  45)   # player bubble (Darker Neon Green)
PH_BUB_N     = ( 40,  42,  56)   # NPC bubble (Darker Blue-Grey)
WA_HEADER    = ( 15,  15,  22)   # Sleek Dark Header
WA_BG        = PH_SCREEN         # Matches overall phone background
WA_TEXT_P    = PH_TEXT           # White text on dark bubbles
WA_TEXT_N    = PH_TEXT

_SC = {"pending": PH_TEXT_D, "in_progress": PH_AMBER, "completed": PH_GREEN}
_SL = {"pending": "Pending", "in_progress": "In Progress", "completed": "Completed"}


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
    handle: str = ""
    is_read: bool = True
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
        self.active_post: Optional[SocialPost] = None

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
        self._social_notif_timer = 0.0
        self._social_notif_interval = 20.0 # New post every 20s
        self._social_likes_timer = 0.0
        self._social_likes_interval = 5.0 # Update likes every 5s
        self._notif_toast = None # {title, body, icon, t}
        self._toast_duration = 4.0
        
        self.pending_photo_posts: list[SocialPost] = []
        self.photo_posts_released_today = 0
        self._photo_post_timer = 0.0
        self._photo_post_interval = 15.0 # First photo post on Day 1 appears after 15s

        self._current_day_for_schedule = -1
        self._refresh_weekly_schedule(1)

        # Off-screen surface for smooth animation
        self._surf = pygame.Surface((PHONE_W, PHONE_H))

        # Fonts
        self._f_stat  = pygame.font.Font(VT323_PATH, 10)
        self._f_sec   = pygame.font.Font(VT323_PATH, 12)
        self._f_title = pygame.font.Font(VT323_PATH, 12)
        self._f_body  = pygame.font.Font(VT323_PATH, 11)
        self._f_sub   = pygame.font.Font(VT323_PATH, 10)
        self._f_badge = pygame.font.Font(VT323_PATH, 9)
        try:
            self._f_ico = pygame.font.Font(VT323_PATH, 15)
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
        
        self.avatars = {}
        self._load_avatars()

        self.social_images = {}
        self._load_social_images()

        self._load_initial_social_posts()
        self._load_initial_messages()

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
        
        # Clear notifications for the opened app
        if app == PhoneApp.SOCIAL:
            for p in self.social_posts:
                if not p.is_read:
                    p.is_read = True
                    self.unread_count = max(0, self.unread_count - 1)
            if self.unread_count == 0: self.show_unread = False

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

        # Update schedule if day changed
        # We need to know the day_number. Since Phone doesn't own it, 
        # we'll assume it's updated externally or we can add a check.
        # For now, let's just make sure the method is available.

        # Social notification system
        self._social_notif_timer += dt
        if self._social_notif_timer >= self._social_notif_interval:
            self._social_notif_timer = 0.0
            self._generate_random_social_post()

        # Scheduled photo posts (2 per day over 4 days)
        if self._current_day_for_schedule <= 4 and self.pending_photo_posts:
            if self.photo_posts_released_today < 2:
                self._photo_post_timer += dt
                if self._photo_post_timer >= self._photo_post_interval:
                    self._photo_post_timer = 0.0
                    self._photo_post_interval = random.uniform(30.0, 60.0)
                    post = self.pending_photo_posts.pop(0)
                    post.timestamp = "1m"
                    self.add_social_post(post)
                    self.photo_posts_released_today += 1

        # Update likes over time
        self._social_likes_timer += dt
        if self._social_likes_timer >= self._social_likes_interval:
            self._social_likes_timer = 0.0
            self._simulate_social_engagement()

        # Toast notification animation
        if self._notif_toast:
            self._notif_toast["t"] += dt
            if self._notif_toast["t"] >= self._toast_duration:
                self._notif_toast = None

    def consume_embedded_map_initial_sync(self) -> bool:
        if self._embedded_map_need_sync:
            self._embedded_map_need_sync = False
            return True
        return False

    # Data helpers
    def add_social_post(self, post: SocialPost):
        self.social_posts.insert(0, post)
        if not post.is_read:
            self.unread_count += 1
            self.show_unread = True
            # Trigger toast
            self._notif_toast = {
                "title": "Phone:",
                "body": post.content[:40] + "...",
                "icon": "X",
                "t": 0.0
            }

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

    def update_day_schedule(self, day_number: int):
        """Update the internal schedule based on the game day (Monday-Friday cycle)."""
        if day_number == self._current_day_for_schedule:
            return
        self.photo_posts_released_today = 0
        self._photo_post_timer = 0.0
        self._photo_post_interval = random.uniform(20.0, 45.0)
        self._refresh_weekly_schedule(day_number)

    def _refresh_weekly_schedule(self, day_number: int):
        self._current_day_for_schedule = day_number
        # cycle 1-5 (Mon-Fri)
        idx = (day_number - 1) % 5
        
        schedules = [
            # Monday
            [
                ScheduleEvent(7,  "Mathematics", "Room 201", "Advanced calculus and logic."),
                ScheduleEvent(8,  "English", "Room 105", "Literary analysis and essay writing."),
                ScheduleEvent(9,  "Science", "Lab A", "Physics and chemistry foundations."),
                ScheduleEvent(9,  "Break Time", "Cafeteria", "30min morning break."), # overlapping 9am slots show correctly
                ScheduleEvent(11, "History", "Room 203", "Modern world history."),
                ScheduleEvent(12, "Computer Science", "Lab B", "Python programming and algorithms."),
                ScheduleEvent(13, "Lunch Time", "Cafeteria", "Main lunch break."),
                ScheduleEvent(15, "Art", "Studio", "Visual arts and design."),
            ],
            # Tuesday
            [
                ScheduleEvent(7,  "Biology", "Lab C", "Cellular structures and genetics."),
                ScheduleEvent(8,  "Mathematics", "Room 201", "Statistics and probability."),
                ScheduleEvent(9,  "Geography", "Room 108", "Global climates and ecosystems."),
                ScheduleEvent(9,  "Break Time", "Cafeteria", "30min morning break."),
                ScheduleEvent(11, "English", "Room 105", "Creative writing workshop."),
                ScheduleEvent(12, "Music", "Music Room", "Theory and performance."),
                ScheduleEvent(13, "Lunch Time", "Cafeteria", "Main lunch break."),
                ScheduleEvent(15, "Physical Education", "Gym", "Team sports and fitness."),
            ],
            # Wednesday
            [
                ScheduleEvent(7,  "Chemistry", "Lab A", "Organic compounds and reactions."),
                ScheduleEvent(8,  "History", "Room 203", "Ancient civilizations."),
                ScheduleEvent(9,  "English", "Room 105", "Shakespearean studies."),
                ScheduleEvent(9,  "Break Time", "Cafeteria", "30min morning break."),
                ScheduleEvent(11, "Mathematics", "Room 201", "Geometry and trigonometry."),
                ScheduleEvent(12, "Art", "Studio", "History of Art."),
                ScheduleEvent(13, "Lunch Time", "Cafeteria", "Main lunch break."),
                ScheduleEvent(15, "Computer Science", "Lab B", "Database systems."),
            ],
            # Thursday
            [
                ScheduleEvent(7,  "Physics", "Lab B", "Quantum mechanics intro."),
                ScheduleEvent(8,  "Biology", "Lab C", "Human anatomy."),
                ScheduleEvent(9,  "Mathematics", "Room 201", "Algebraic structures."),
                ScheduleEvent(9,  "Break Time", "Cafeteria", "30min morning break."),
                ScheduleEvent(11, "Music", "Music Room", "Music history."),
                ScheduleEvent(12, "English", "Room 105", "Public speaking."),
                ScheduleEvent(13, "Lunch Time", "Cafeteria", "Main lunch break."),
                ScheduleEvent(15, "Geography", "Room 108", "Political geography."),
            ],
            # Friday
            [
                ScheduleEvent(7,  "English", "Room 105", "Modern literature."),
                ScheduleEvent(8,  "Chemistry", "Lab A", "Lab experiments day."),
                ScheduleEvent(9,  "History", "Room 203", "Local history project."),
                ScheduleEvent(9,  "Break Time", "Cafeteria", "30min morning break."),
                ScheduleEvent(11, "Physical Education", "Gym", "Outdoor activities."),
                ScheduleEvent(12, "Computer Science", "Lab B", "Web development."),
                ScheduleEvent(13, "Lunch Time", "Cafeteria", "Main lunch break."),
                ScheduleEvent(15, "Music", "Music Room", "Ensemble practice."),
            ]
        ]
        self.schedule_events = schedules[idx]

    def get_unread_messages_count(self) -> int:
        return sum(1 for ml in self.messages.values()
                   for m in ml if not m.is_read and not m.is_player)

    def mark_messages_read(self, npc_id: str):
        for m in self.messages.get(npc_id, []):
            m.is_read = True

    def _load_initial_messages(self):
        import uuid
        msg_id = str(uuid.uuid4())
        
        if self.player_name == "aiden":
            msg = TextMessage(
                id=msg_id,
                sender_npc_id="npc_lena",
                sender_name="Lena Parker",
                content="Hi brother, write me if you need anything!",
                timestamp="08:00am",
                is_read=False,
                is_player=False,
                reply_options=["Hey Lena, thanks!", "Sure, I'll let you know.", "I'm busy right now."]
            )
            self.add_text_message("npc_lena", msg)
        elif self.player_name == "lena":
            msg = TextMessage(
                id=msg_id,
                sender_npc_id="npc_aiden",
                sender_name="Aiden Parker",
                content="Hi sister, write me if you need anything!",
                timestamp="08:00am",
                is_read=False,
                is_player=False,
                reply_options=["Hey Aiden, thanks!", "Sure, I'll let you know.", "I'm busy right now."]
            )
            self.add_text_message("npc_aiden", msg)

    # ──────────────────────────────────────────────────────────
    #  DRAW
    # ──────────────────────────────────────────────────────────

    def draw(self):
        # Draw toast regardless of phone visibility
        self._draw_notification_toast()

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

        hx, hy, hw, hh = DISPLAY_PHONE_X, DISPLAY_PHONE_Y, DISPLAY_PHONE_W, DISPLAY_PHONE_H
        cx0 = hx + hw // 2
        cy0 = hy + hh // 2
        cx = int(cx0 + (SCREEN_WIDTH // 2 - cx0) * w)
        cy = int(cy0 + (SCREEN_HEIGHT // 2 - cy0) * w)
        scale_end = max(
            SCREEN_WIDTH / max(1, DISPLAY_PHONE_W),
            SCREEN_HEIGHT / max(1, DISPLAY_PHONE_H),
        ) * 1.015
        sc = 1.0 + (scale_end - 1.0) * w
        nw = max(2, int(DISPLAY_PHONE_W * sc))
        nh = max(2, int(DISPLAY_PHONE_H * sc))

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
        """Del icono HUD → rectángulo final grande y centrado."""
        tx, ty, tw, th = DISPLAY_PHONE_X, DISPLAY_PHONE_Y, DISPLAY_PHONE_W, DISPLAY_PHONE_H
        if self._hud_anchor and self._hud_anchor.width > 2:
            hx, hy, hw, hh = (
                self._hud_anchor.x,
                self._hud_anchor.y,
                self._hud_anchor.w,
                self._hud_anchor.h,
            )
            tx = int(hx + (DISPLAY_PHONE_X - hx) * p_anim)
            ty = int(hy + (DISPLAY_PHONE_Y - hy) * p_anim)
            tw = int(hw + (DISPLAY_PHONE_W - hw) * p_anim)
            th = int(hh + (DISPLAY_PHONE_H - hh) * p_anim)
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
                    self._badge(s, str(u), ir.right - 4, ir.y + 4)
            if app == PhoneApp.SOCIAL:
                # Show badge for any unread post, not just mentions
                sc = sum(1 for p in self.social_posts if not p.is_read)
                if sc > 0:
                    self._badge(s, str(sc), ir.right - 4, ir.y + 4)

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
        pygame.draw.rect(s, PH_CARD, ir, border_radius=20)
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
        if self.active_post:
            self._app_social_detail(s, cx, cy, cw, ch, self.active_post)
            return

        self._post_rects  = []
        self._like_rects  = []
        self._filter_rects= []

        y = cy + _PAD
        self._text(s, "X - SchoolNet", self._f_sec, PH_PINK, cx + _PAD, y)
        y += 16

        # Filter tabs
        filters = [("all", "All"), ("anonymous", "Anonymous"), ("mentions", "Mentions")]
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
        yoff = y - sc

        for post in posts:
            text_h = self._measure_wrap_text(post.content, self._f_body, cw - _PAD * 2 - 54, 14)
            PH = 16 + text_h + 28
            
            has_img = post.image_tag and post.image_tag in self.social_images
            if has_img:
                PH += 210 + 12

            if yoff + PH < cy:
                yoff += PH + _GAP
                continue
            if yoff > cy + ch:
                break

            card = pygame.Rect(cx + _PAD, yoff, cw - _PAD * 2, PH)
            self._rrect(s, PH_CARD, card, 0, PH_BD, 1) # Flat Twitter-like cards

            # Profile Pic (Left)
            av_radius = 16
            av_center = (card.x + 24, card.y + 24)
            p_name = post.author if not post.is_anonymous else "Anon"
            self._draw_avatar(s, post.author_npc_id, p_name, av_center, av_radius)

            # Header: Name @handle · time
            tx = card.x + 46
            ty = card.y + 6
            
            # Name (Bold)
            a_str = "Anonymous" if post.is_anonymous else post.author
            name_t = self._f_title.render(a_str, True, PH_TEXT)
            s.blit(name_t, (tx, ty))
            
            # Handle & Time
            handle_str = f" @{post.handle or 'anon'} · {post.timestamp}"
            ht_t = self._f_sub.render(handle_str, True, PH_TEXT_D)
            s.blit(ht_t, (tx + name_t.get_width(), ty + 2))

            # Content
            curr_y = self._wrap_text(s, post.content, self._f_body, PH_TEXT, tx, ty + 18, cw - _PAD * 2 - 54, 14)

            # Image attachment
            if has_img:
                curr_y += 6
                img = self.social_images[post.image_tag]
                img_w = cw - _PAD * 2 - 54
                img_h = 210
                scaled = pygame.transform.smoothscale(img, (img_w, img_h))
                img_rect = pygame.Rect(tx, curr_y, img_w, img_h)
                s.blit(scaled, img_rect.topleft)
                pygame.draw.rect(s, PH_BD, img_rect, width=1, border_radius=8)

            # Action icons (Like only for now)
            lk_col = PH_PINK if post._liked else PH_TEXT_D
            lk = self._f_sub.render(f"♥ {post.likes}", True, lk_col)
            lk_r = pygame.Rect(tx, card.bottom - 20, 48, 14)
            s.blit(lk, lk_r.topleft)
            self._like_rects.append((lk_r, post))

            # Mentions tag
            is_m = player in [m.lower() for m in post.mentions]
            if is_m:
                mb = self._f_sub.render("Mentioned you", True, PH_CYAN)
                s.blit(mb, (card.right - mb.get_width() - 8, card.bottom - 20))

            self._post_rects.append((card, post))
            yoff += PH + _GAP

    def _app_social_detail(self, s, cx, cy, cw, ch, post):
        br = pygame.Rect(cx + _PAD, cy + _PAD, 54, 20)
        self._rrect(s, PH_CARD2, br, 6)
        bk = self._f_sub.render("← Back", True, PH_PINK)
        s.blit(bk, bk.get_rect(center=br.center))
        self._back_rect = br

        y = cy + _PAD + 32
        
        # Profile Section
        av_radius = 24
        self._draw_avatar(s, post.author_npc_id, post.author, (cx + _PAD + av_radius, y + av_radius), av_radius)
        
        tx = cx + _PAD + av_radius * 2 + 10
        self._text(s, post.author if not post.is_anonymous else "Anonymous", self._f_title, PH_TEXT, tx, y + 4)
        self._text(s, f"@{post.handle or 'anon'}", self._f_sub, PH_TEXT_D, tx, y + 18)
        
        y += av_radius * 2 + 16
        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP
        
        y = self._wrap_text(s, post.content, self._f_body, PH_TEXT, cx + _PAD, y, cw - _PAD * 2, 14)
        y += _GAP

        if post.image_tag and post.image_tag in self.social_images:
            img = self.social_images[post.image_tag]
            img_w = cw - _PAD * 2
            img_h = 260
            scaled = pygame.transform.smoothscale(img, (img_w, img_h))
            img_rect = pygame.Rect(cx + _PAD, y, img_w, img_h)
            s.blit(scaled, img_rect.topleft)
            pygame.draw.rect(s, PH_BD, img_rect, width=1, border_radius=8)
            y += img_h + _GAP
        
        ts_s = self._f_sub.render(f"Posted {post.timestamp} ago · SchoolNet for Mobile", True, PH_TEXT_D)
        s.blit(ts_s, (cx + _PAD, y))
        y += 20
        
        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP
        
        # Engagement
        self._text(s, f"♥ {post.likes} Likes", self._f_title, PH_PINK, cx + _PAD, y)

    # ══════════════════════════════════════════════════════════
    #  APP — MESSAGES
    # ══════════════════════════════════════════════════════════

    def _app_messages(self, s, cx, cy, cw, ch):
        self._chat_rects  = []
        self._back_rect   = None
        self._reply_rects = []

        # WhatsApp-style main screen
        # Header (Top)
        header_h = 54
        header_rect = pygame.Rect(cx, cy, cw, header_h)
        pygame.draw.rect(s, WA_HEADER, header_rect)
        
        self._text(s, "WhatsApp", self._f_sec, WHITE, cx + _PAD, cy + 12)
        
        # Tabs bar (Simulated)
        tab_y = cy + header_h
        tab_h = 32
        pygame.draw.rect(s, WA_HEADER, (cx, tab_y, cw, tab_h))
        self._text(s, "CHATS", self._f_badge, WHITE, cx + cw // 2 - 20, tab_y + 10)
        pygame.draw.rect(s, PH_GREEN, (cx + cw // 2 - 30, tab_y + tab_h - 3, 60, 3)) # Active tab indicator (Green)
        
        y_list = tab_y + tab_h
        avail_h = ch - (y_list - cy)

        # Dark background for the list
        pygame.draw.rect(s, PH_SCREEN, (cx, y_list, cw, avail_h))

        if self.active_chat is not None:
            self._chat_view(s, cx, cy, cw, ch)
        else:
            self._conv_list(s, cx, y_list, cw, avail_h)

    def _conv_list(self, s, cx, y, cw, avail_h):
        if not self.messages:
            self._text(s, "Sin mensajes.", self._f_body, PH_TEXT_D, cx + _PAD, y + 20)
            return

        sc = self._scroll[PhoneApp.MESSAGES]
        IH = 64 # Taller items for WhatsApp look
        yoff = y - sc

        for npc_id, msgs in self.messages.items():
            if not msgs:
                continue
            
            # Find the contact name (the first message NOT from the player)
            contact_name = "Contact"
            for m in msgs:
                if not m.is_player:
                    contact_name = m.sender_name
                    break
            
            last   = msgs[-1]
            unread = sum(1 for m in msgs if not m.is_read and not m.is_player)

            card = pygame.Rect(cx, yoff, cw, IH)
            if card.bottom < y or card.top > y + avail_h:
                yoff += IH
                continue

            # Hover/Selected effect could go here
            # Separator line (Darker for dark mode)
            pygame.draw.line(s, PH_BD, (cx + 70, card.bottom - 1), (cx + cw, card.bottom - 1))
            
            # Avatar
            avc = (cx + 35, card.centery)
            self._draw_avatar(s, npc_id, contact_name, avc, 24)

            # Name (Contact Name, never "Tú")
            self._text(s, contact_name, self._f_title, PH_TEXT, cx + 70, card.y + 12)
            
            # Preview (Last message content)
            prev_text = last.content
            if last.is_player:
                prev_text = "✓ " + prev_text # Checkmark for player messages
            
            prev = prev_text[:30] + ("…" if len(prev_text) > 30 else "")
            self._text(s, prev, self._f_sub, PH_TEXT_S, cx + 70, card.y + 32)

            # Time on the right
            time_s = self._f_badge.render(last.timestamp, True, PH_TEXT_D)
            s.blit(time_s, (cx + cw - time_s.get_width() - 12, card.y + 14))

            if unread > 0:
                self._badge(s, str(min(unread, 9)), cx + cw - 20, card.y + 38)

            self._chat_rects.append((card, npc_id))
            yoff += IH

            self._chat_rects.append((card, npc_id))
            yoff += IH + _GAP

    def _chat_view(self, s, cx, y, cw, avail_h):
        msgs = self.messages.get(self.active_chat, [])
        npc_name = msgs[0].sender_name if msgs else "Chat"

        # Background
        bg_rect = pygame.Rect(cx, y, cw, avail_h)
        pygame.draw.rect(s, WA_BG, bg_rect)

        # Header Bar (WhatsApp style)
        header_h = 44
        header_rect = pygame.Rect(cx, y, cw, header_h)
        pygame.draw.rect(s, WA_HEADER, header_rect)

        # Back btn
        br = pygame.Rect(cx + 8, y + (header_h - 22) // 2, 36, 22)
        bk = self._f_sub.render("←", True, WHITE)
        s.blit(bk, bk.get_rect(center=br.center))
        self._back_rect = br

        # NPC Avatar in header
        avc = (br.right + 20, y + header_h // 2)
        self._draw_avatar(s, self.active_chat, npc_name, avc, 16)

        nm = self._f_title.render(npc_name, True, WHITE)
        s.blit(nm, (avc[0] + 20, y + 8))
        st = self._f_sub.render("Online", True, PH_GREEN)
        s.blit(st, (avc[0] + 20, y + 24))

        y_content = y + header_h
        avail_content_h = avail_h - header_h

        # Reply options at bottom
        reply_opts = []
        if msgs:
            # Only show replies if the last message is NOT from the player
            if not msgs[-1].is_player:
                reply_opts = msgs[-1].reply_options or []

        reply_h = (len(reply_opts) * 30 + _PAD) if reply_opts else 0
        chat_area_h = avail_content_h - reply_h

        # Bubbles (scroll from bottom up)
        sc = self._scroll[PhoneApp.MESSAGES]
        BH = 30
        total = 0
        bubble_datas = []
        
        # Calculate heights for all bubbles first
        for msg in msgs:
            mw = cw - _PAD * 2 - 20
            words = msg.content.split()
            line, lines = "", []
            for w in words:
                test = (line + " " + w).strip()
                if self._f_body.size(test)[0] <= mw - 20:
                    line = test
                else:
                    if line: lines.append(line)
                    line = w
            if line: lines.append(line)
            
            bh = max(BH, len(lines) * 14 + 18)
            bw = min(mw, max(60, max((self._f_body.size(l)[0] for l in lines), default=60) + 20))
            bubble_datas.append((lines, bw, bh))
            total += bh + _GAP

        start_y = y_content + max(_GAP, chat_area_h - total) - sc
        
        # Clip chat area
        old_clip = s.get_clip()
        s.set_clip((cx, y_content, cw, chat_area_h))

        for idx, msg in enumerate(msgs):
            lines, bw, bh = bubble_datas[idx]
            my = start_y
            is_p = msg.is_player
            bg   = PH_BUB_P if is_p else PH_BUB_N
            tx_col = WA_TEXT_P if is_p else WA_TEXT_N

            if is_p:
                bx = cx + cw - _PAD - bw
            else:
                bx = cx + _PAD

            bub = pygame.Rect(bx, my, bw, bh)
            if bub.bottom >= y_content and bub.top <= y_content + chat_area_h:
                self._rrect(s, bg, bub, 10, (0,0,0,20), 1)
                
                # Bubble shadow/depth
                pygame.draw.line(s, (0,0,0,30), (bub.left, bub.bottom), (bub.right, bub.bottom))

                for li, ln in enumerate(lines):
                    lt = self._f_body.render(ln, True, tx_col)
                    s.blit(lt, (bub.x + 10, bub.y + 8 + li * 14))

                # Timestamp inside bubble
                ts_s = self._f_badge.render(msg.timestamp, True, (120, 120, 120))
                s.blit(ts_s, (bub.right - ts_s.get_width() - 8, bub.bottom - 12))

            start_y += bh + _GAP
        
        s.set_clip(old_clip)

        # Reply options drawer
        if reply_opts:
            ry = y_content + chat_area_h
            pygame.draw.rect(s, PH_NAV_BG, (cx, ry, cw, reply_h))
            pygame.draw.line(s, PH_BD, (cx, ry), (cx + cw, ry))
            self._reply_rects = []
            for i, opt in enumerate(reply_opts):
                rr = pygame.Rect(cx + _PAD, ry + 8 + i * 30, cw - _PAD * 2, 26)
                is_hover = False # Could add hover effect if tracking mouse
                self._rrect(s, PH_CARD, rr, 13, PH_GREEN, 1)
                ot = self._f_sub.render(opt, True, PH_GREEN)
                s.blit(ot, ot.get_rect(center=rr.center))
                self._reply_rects.append((rr, opt))

    # ══════════════════════════════════════════════════════════
    #  APP — SCHEDULE
    # ══════════════════════════════════════════════════════════

    def _app_schedule(self, s, cx, cy, cw, ch):
        y = cy + _PAD
        
        # Day header logic
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        day_idx = (max(1, self._current_day_for_schedule) - 1) % 5
        day_name = days[day_idx]
        
        self._text(s, "School Schedule", self._f_sec, PH_CYAN, cx + _PAD, y)
        y += 16
        self._text(s, f"Today: {day_name}", self._f_sub, PH_TEXT, cx + _PAD, y)
        y += 13
        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP

        cur_mins = int(self.time_source()) if self.time_source else -1
        cur_h    = cur_mins // 60 if cur_mins >= 0 else -1

        if not self.schedule_events:
            self._text(s, "No events scheduled.", self._f_body, PH_TEXT_D, cx + _PAD, y + 20)
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
                tag = self._f_badge.render("NOW", True, PH_CYAN)
                s.blit(tag, (card.right - tag.get_width() - 6, card.y + 6))
            elif is_next:
                tag = self._f_badge.render("NEXT", True, PH_AMBER)
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
            bt = pygame.font.Font(VT323_PATH, 9).render(
                str(unread), True, WHITE)
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
            # Let world_map handle the event first (handles both teleport cancel and map exit)
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
                self.active_post = None
                return True

            if self.current_app == PhoneApp.ACADEMIC:
                for rect, task in self._task_rects:
                    if rect.collidepoint((lx, ly)):
                        self.active_task = task
                        return True

            elif self.current_app == PhoneApp.SOCIAL:
                if self.active_post:
                    # Already in detail, check back button handled above
                    pass
                else:
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
                    for rect, post in self._post_rects:
                        if rect.collidepoint((lx, ly)):
                            self.active_post = post
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

    def _load_avatars(self):
        """Pre-load NPC avatar images."""
        import os
        try:
            # Noah Carter - Realistic image as requested
            path = "assets/Imagenes realistas personajes/Noah Carter.png"
            if os.path.exists(path):
                img = pygame.image.load(path).convert_alpha()
                self.avatars["npc_noah_carter"] = img
                
            path_aiden = "assets/Imagenes realistas personajes/Aiden Parker.png"
            if os.path.exists(path_aiden):
                self.avatars["npc_aiden"] = pygame.image.load(path_aiden).convert_alpha()
                
            path_lena = "assets/Imagenes realistas personajes/Lena Aiden.png"
            path_lena2 = "assets/Imagenes realistas personajes/Lena Parker.png"
            if os.path.exists(path_lena2):
                self.avatars["npc_lena"] = pygame.image.load(path_lena2).convert_alpha()
            elif os.path.exists(path_lena):
                self.avatars["npc_lena"] = pygame.image.load(path_lena).convert_alpha()
                
            path_oscar = "assets/Imagenes realistas personajes/Oscar Jimenez.png"
            if os.path.exists(path_oscar):
                self.avatars["npc_oscar"] = pygame.image.load(path_oscar).convert_alpha()

            path_axel = "assets/Imagenes realistas personajes/Axel Knight.png"
            if os.path.exists(path_axel):
                self.avatars["npc_axel_knight"] = pygame.image.load(path_axel).convert_alpha()

            path_ava = "assets/Imagenes realistas personajes/Ava Thompson.png"
            if os.path.exists(path_ava):
                self.avatars["npc_ava_thompson"] = pygame.image.load(path_ava).convert_alpha()
        except Exception:
            pass

    def _load_social_images(self):
        """Pre-load images for social posts."""
        import os
        for i in range(1, 9):
            path = f"assets/Social/{i}.png"
            if os.path.exists(path):
                try:
                    img = pygame.image.load(path).convert_alpha()
                    self.social_images[path] = img
                except Exception:
                    pass

    def _measure_wrap_text(self, text, font, max_w, line_h) -> int:
        words = str(text).split()
        line = ""
        lines = 0
        for w in words:
            test = (line + " " + w).strip()
            if font.size(test)[0] <= max_w:
                line = test
            else:
                if line:
                    lines += 1
                line = w
        if line:
            lines += 1
        return lines * line_h

    def _draw_avatar(self, surf, npc_id, name, center, radius):
        """Draw a circular avatar image or fallback to initials."""
        if npc_id in self.avatars:
            img = self.avatars[npc_id]
            # Create a circular mask for the avatar
            size = radius * 2
            av_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(av_surf, (255, 255, 255), (radius, radius), radius)
            scaled = pygame.transform.smoothscale(img, (size, size))
            av_surf.blit(scaled, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            surf.blit(av_surf, (center[0] - radius, center[1] - radius))
        else:
            pygame.draw.circle(surf, (200, 210, 220), center, radius)
            init_txt = name[0].upper() if name else "?"
            init = self._f_title.render(init_txt, True, WHITE)
            surf.blit(init, init.get_rect(center=center))

    # ══════════════════════════════════════════════════════════
    #  UTILITIES
    # ══════════════════════════════════════════════════════════

    def _simulate_social_engagement(self):
        """Randomly adds likes to existing posts to simulate virality."""
        if not self.social_posts:
            return
        
        # Pick up to 3 random posts to gain likes
        # We prioritize recent posts (first 10)
        sample_size = min(len(self.social_posts), 10)
        targets = random.sample(self.social_posts[:sample_size], min(sample_size, 3))
        
        for post in targets:
            # Random chance to gain 1-3 likes
            if random.random() < 0.7:
                post.likes += random.randint(1, 3)

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

    def _draw_notification_toast(self):
        if not self._notif_toast:
            return
        
        t = self._notif_toast["t"]
        dur = self._toast_duration
        
        # Slide down/up animation
        y_off = -60
        if t < 0.5: # slide down
            y_off = -60 + (80 * (t/0.5))
        elif t > dur - 0.5: # slide up
            y_off = 20 - (80 * ((t - (dur-0.5))/0.5))
        else:
            y_off = 20
            
        tw, th = 240, 44
        tx = (SCREEN_WIDTH - tw) // 2
        rect = pygame.Rect(tx, y_off, tw, th)
        
        # Shadow
        shadow_rect = rect.move(2, 2)
        pygame.draw.rect(self.screen, (0, 0, 0, 80), shadow_rect, border_radius=10)
        # Body
        self._rrect(self.screen, (30, 32, 44), rect, 10, PH_CYAN, 1)
        
        # Content
        self._text(self.screen, self._notif_toast["icon"], self._f_ico, PH_CYAN, tx + 10, y_off + 12)
        self._text(self.screen, self._notif_toast["title"], self._f_badge, PH_PINK, tx + 32, y_off + 8)
        self._clip_text(self.screen, self._notif_toast["body"], self._f_sub, WHITE, tx + 32, y_off + 22, tw - 42)

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

    def _load_initial_social_posts(self):
        """Populate the social feed with initial gossip and bullying posts."""
        gossip = [
            SocialPost("g1", "Anonymous", None, "Someone wake up Justin Cole 💀 Bro is catching flies in AP Chem. Snoring like a whole lawnmower in the back row, the drool is crazy standard. Who wants to drop a piece of chalk in there? 😭😂 #RavensideSleepers #CloseYourMouth #Outsiders", "2m", True, 12, ["Justin"], image_tag="assets/Social/1.png", handle="chem_spy"),
            SocialPost("g2", "Anonymous", None, "The way the entire row cleared out when Eric Stone sat down... locker room smells better than this. Someone drop a body spray in his locker ASAP. 🤢 #HygieneCheck #Outsiders #Ravenside", "5m", True, 45, ["Eric"], image_tag="assets/Social/2.png", handle="hallway_patrol"),
            SocialPost("g3", "Anonymous", None, "Spotted: Mason Carter and Leo Carter getting way too close and personal by the lockers today. Just admit it already boys, the closet door is wide open. 👬👀 #CaughtInTheAct #RavensideRumors #Athletes", "15m", True, 89, ["Mason", "Leo"], image_tag="assets/Social/3.png", handle="gossip_king"),
            SocialPost("g4", "Mia Thompson", "npc_mia_thompson", "Ravenside is literally Cheater Central. Don't trust anyone. Case in point: Chloe Adams was seen holding hands with Tyler Grant behind the gym, but isn't she supposed to be with Jake Turner? ☕🐸 #Exposed #Drama #Populars", "1h", False, 134, ["Chloe", "Tyler", "Jake"], image_tag="assets/Social/4.png", handle="mia_spills"),
            SocialPost("g5", "Brandon Cole", "npc_brandon_cole", "Who let Daniel Kim on the court? 😭 Bro missed a layup so bad it almost hit the cheerleaders. Please stick to video games, Daniel. #BenchWarmer #Airball #Athletes #Nerds", "2h", False, 67, ["Daniel"], image_tag="assets/Social/5.png", handle="brandon_v"),
            SocialPost("g6", "Anonymous", None, "Imagine Caleb Ross losing a ping pong match to Oscar Jimenez... literally the easiest dub of the season and you choked, Caleb. Embarrassing. 🏓🤡 #PingPongFlop #Athletes #Outsiders", "3h", True, 156, ["Caleb", "Oscar"], image_tag="assets/Social/6.png", handle="pingpong_pro"),
            SocialPost("g7", "Anonymous", None, "Look at Grace White trying to blend into the wall. It’s been three months and she still speaks to literally nobody. Sad. 😂💀 #NoFriends #Outsiders #Loner", "4h", True, 31, ["Grace"], image_tag="assets/Social/7.png", handle="shadow_watcher"),
            SocialPost("g8", "Anonymous", None, "Table for one! The cafeteria is packed but nobody wants to sit anywhere near Liam Hayes. Total social rejection. 🕊️💔 #LoserTable #Outsiders #Sad", "5h", True, 99, ["Liam"], image_tag="assets/Social/8.png", handle="cafeteria_cam"),
        ]
        random.shuffle(gossip)
        self.pending_photo_posts = gossip
        self._generate_random_social_post()

    def _generate_random_social_post(self):
        """Generates a random gossip post from the NPC pool."""
        random_npc_names = [
            ("Alexander Hill", "npc_alexander_hill", "alex_h"),
            ("Emma Watson", "npc_emma_watson", "emma_w"),
            ("Brandon Cole", "npc_brandon_cole", "brandon_c"),
            ("Amelia Clark", "npc_amelia_clark", "amelia_sky"),
            ("Dylan Price", "npc_dylan_price", "price_tag"),
            ("Sophie Turner", "npc_sophie_turner", "sophie_t"),
        ]
        random_gossip = [
            "Just saw someone eating lunch completely alone in the corner of the cafeteria. How embarrassing for them! 💀",
            "Did anyone else see that pathetic display in the gym earlier? Some people have absolutely zero coordination. Total joke.",
            "Imagine thinking you're popular just because you hang out near the fountain. You guys look ridiculous and everyone is laughing at you.",
            "Whoever wrote that essay in English today needs to go back to elementary school. Worst presentation I have ever heard.",
            "Nice haircut today... if you were trying to look like a wet rat! 🐀 Seriously, do you not own a mirror?",
            "If you value your reputation, don't even bother showing up to the Ping Pong court tonight. You'll just get humiliated in front of everyone.",
        ]
        
        name, nid, handle = random.choice(random_npc_names)
        content = random.choice(random_gossip)
        is_anon = random.random() < 0.4
        
        post = SocialPost(
            id=f"rnd_{pygame.time.get_ticks()}",
            author="Anonymous" if is_anon else name,
            author_npc_id=None if is_anon else nid,
            content=content,
            timestamp="1m",
            is_anonymous=is_anon,
            handle="anon_user" if is_anon else handle,
            is_read=False
        )
        self.add_social_post(post)
